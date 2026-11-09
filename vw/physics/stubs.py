"""Built-in physics adapters and the shared adapter base.

``replay`` is fully implemented (trace-level pose playback). ``newton`` is a stub:
check() is real, so capability routing works today; compile()/simulate() land in a
later milestone. Engine adapters live in their own modules (``vw.physics.mujoco``,
``vw.physics.bullet_blender``, ``vw.physics.physx``).
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


@register_physics("newton")
class NewtonAdapter(_EngineStub):
    """Newton / MuJoCo Warp (GPU batch)."""

    name = "newton"
    capabilities = Capabilities(_RIGID, frozenset({Device.CUDA}))


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
