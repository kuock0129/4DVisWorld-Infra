"""Built-in physics adapters.

``replay`` is fully implemented (trace-level pose playback; used for non-causal
counterfactuals). The engine adapters are M0 stubs: check() and param_map() are
real, so capability routing works today; compile()/simulate() land in later milestones.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from vw.ir import BodyKind, SceneIR
from vw.physics.base import (
    BackendInfo,
    Capabilities,
    Device,
    Feature,
    NativeScene,
    SimResult,
    Trajectory,
    UnsupportedSceneError,
    check_capabilities,
)
from vw.registry import register_physics, resolve_device


class _AdapterBase:
    name: str = ""
    version: str = "unimplemented"
    capabilities: Capabilities

    def __init__(self, device: str = "auto", **config: Any):
        self.device: Device = resolve_device(device, self.capabilities.devices)
        self.config = config

    def check(self, ir: SceneIR) -> list[str]:
        return check_capabilities(ir, self.capabilities, self.device)

    def _require(self, ir: SceneIR) -> None:
        problems = self.check(ir)
        if problems:
            raise UnsupportedSceneError(self.name, problems)

    def backend_info(self) -> BackendInfo:
        return BackendInfo(self.name, self.version, self.device, dict(self.config))

    def param_map(self) -> dict[str, Any]:
        return {}


class _EngineStub(_AdapterBase):
    milestone = "a later milestone"

    def compile(self, ir: SceneIR) -> NativeScene:
        self._require(ir)
        raise NotImplementedError(f"{self.name}.compile is a stub (planned for {self.milestone})")

    def simulate(self, native: NativeScene, kinematic: dict[str, Trajectory] | None = None) -> SimResult:
        raise NotImplementedError(f"{self.name}.simulate is a stub (planned for {self.milestone})")


_RIGID = frozenset({Feature.RIGID, Feature.KINEMATIC, Feature.MESH_COLLISION})


@register_physics("mujoco")
class MuJoCoAdapter(_EngineStub):
    """compile() is real (IR -> MJCF); simulate() lands in M1.

    Kinematic bodies are MJCF mocap bodies; simulate() will write their pose from the
    trajectory (or the ``kinematic`` override, e.g. replayed baseline poses) every step.
    """

    name = "mujoco"
    milestone = "M1"
    capabilities = Capabilities(_RIGID, frozenset({Device.CPU}))

    def compile(self, ir: SceneIR) -> NativeScene:
        from vw.physics.mujoco_mjcf import ir_to_mjcf

        self._require(ir)
        return ir_to_mjcf(ir, timestep=float(self.config.get("timestep", 0.002)))

    def param_map(self) -> dict[str, Any]:
        return {
            "geometry.box.extents": {"to": "geom.size", "note": "exact: half-sizes = extents / 2"},
            "geometry.plane.extents": {"to": "geom.size[0:2]", "note": "exact: extents / 2; collision plane is infinite"},
            "geometry.cylinder|capsule.height": {"to": "geom.size[1]", "note": "exact: half-length = height / 2"},
            "material.friction": {"to": "geom.friction[0]", "note": "sliding only; torsional/rolling use MuJoCo defaults"},
            "material.restitution": {"to": "geom.solref", "note": "NOT applied yet (M1): needs solref approximation"},
            "mass": {"to": "geom.mass", "note": "inertia from geometry, uniform density"},
            "linear_damping|angular_damping": {"to": "joint(free).damping", "note": "approximation: max of the two"},
            "initial_*_velocity": {"to": "data.qvel", "note": "set at simulate() time (M1)"},
            "kind=kinematic": {"to": "body.mocap", "note": "pose set from trajectory every step"},
        }


@register_physics("newton")
class NewtonAdapter(_EngineStub):
    """Newton / MuJoCo Warp (GPU batch)."""

    name = "newton"
    capabilities = Capabilities(_RIGID, frozenset({Device.CUDA}))


@register_physics("physx")
class PhysXAdapter(_EngineStub):
    name = "physx"
    capabilities = Capabilities(_RIGID, frozenset({Device.CPU, Device.CUDA}))


@register_physics("bullet_blender")
class BulletBlenderAdapter(_EngineStub):
    """Blender's built-in Bullet rigid-body world, run headless."""

    name = "bullet_blender"
    capabilities = Capabilities(_RIGID, frozenset({Device.CPU}))


@register_physics("replay")
class ReplayAdapter(_AdapterBase):
    """Plays back trajectories with no dynamics. Handles level=trace and pure-kinematic scenes."""

    name = "replay"
    version = "0.1"
    capabilities = Capabilities(
        frozenset({Feature.TRACE_REPLAY, Feature.KINEMATIC, Feature.MESH_COLLISION}),
        frozenset({Device.CPU}),
    )

    def compile(self, ir: SceneIR) -> NativeScene:
        self._require(ir)
        return ir

    def simulate(self, native: NativeScene, kinematic: dict[str, Trajectory] | None = None) -> SimResult:
        ir: SceneIR = native
        T = ir.timing.frames
        poses: dict[str, np.ndarray] = {}
        for b in ir.bodies:
            if kinematic and b.id in kinematic:
                arr = np.asarray(kinematic[b.id], dtype=float)
                if arr.shape != (T, 7):
                    raise ValueError(f"kinematic['{b.id}'] must be ({T}, 7), got {arr.shape}")
            elif b.kind is BodyKind.STATIC or b.trajectory is None:
                p = b.initial_pose
                arr = np.tile(np.array([*p.position, *p.orientation], dtype=float), (T, 1))
            else:
                arr = np.hstack([np.array(b.trajectory.positions), np.array(b.trajectory.orientations)])
            poses[b.id] = arr
        velocities = {oid: _finite_diff(p, ir.timing.fps) for oid, p in poses.items()}
        return SimResult(ir.timing.fps, poses, velocities, contacts=[], backend=self.backend_info())


def _finite_diff(poses: np.ndarray, fps: int) -> np.ndarray:
    """Linear velocity by finite difference; angular left at zero (replay has no dynamics)."""
    v = np.zeros((poses.shape[0], 6))
    if poses.shape[0] > 1:
        v[:, :3] = np.gradient(poses[:, :3], 1.0 / fps, axis=0)
    return v
