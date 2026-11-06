"""Physics adapter contract: check -> compile -> simulate.

Adapters only ever see a :class:`~vw.ir.SceneIR` and only ever return a
:class:`SimResult`. Everything engine-specific (MJCF, USD, URDF, bpy scenes,
solver settings) stays inside the adapter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable

import numpy as np

from vw.ir import BodyKind, Level, Mesh, SceneIR


class Device(str, Enum):
    CPU = "cpu"
    CUDA = "cuda"
    METAL = "metal"


class Feature(str, Enum):
    """Scene features an IR may require and an adapter may support."""

    RIGID = "rigid"  # dynamic rigid bodies
    KINEMATIC = "kinematic"  # bodies driven by a prescribed trajectory
    MESH_COLLISION = "mesh_collision"  # non-primitive collision geometry
    TRACE_REPLAY = "trace_replay"  # level=trace scenes (pose playback, no dynamics)
    ARTICULATED = "articulated"  # reserved: joints (not in IR v0.1)
    DEFORMABLE = "deformable"  # reserved: cloth/soft (not in IR v0.1)


@dataclass(frozen=True)
class Capabilities:
    features: frozenset[Feature]
    devices: frozenset[Device]


def required_features(ir: SceneIR) -> set[Feature]:
    """Features a backend must support to handle ``ir`` faithfully."""
    req: set[Feature] = set()
    if ir.level is Level.TRACE:
        req.add(Feature.TRACE_REPLAY)
    for b in ir.bodies:
        if b.kind is BodyKind.DYNAMIC and ir.level is Level.PHYSICAL:
            req.add(Feature.RIGID)
        if b.kind is BodyKind.KINEMATIC:
            req.add(Feature.KINEMATIC)
        if isinstance(b.geometry, Mesh):
            req.add(Feature.MESH_COLLISION)
    return req


def check_capabilities(ir: SceneIR, caps: Capabilities, device: Device) -> list[str]:
    """Shared implementation of ``PhysicsAdapter.check``. Non-empty => refuse."""
    problems = [f"unsupported feature: {f.value}" for f in sorted(required_features(ir) - caps.features, key=lambda f: f.value)]
    if device not in caps.devices:
        problems.append(f"unsupported device: {device.value}")
    return problems


class UnsupportedSceneError(RuntimeError):
    """Raised when an adapter is asked to compile a scene its check() rejects."""

    def __init__(self, adapter: str, problems: list[str]):
        self.adapter = adapter
        self.problems = problems
        super().__init__(f"{adapter} cannot handle scene: " + "; ".join(problems))


# --------------------------------------------------------------------------- results


@dataclass(frozen=True)
class BackendInfo:
    name: str
    version: str
    device: Device
    solver_config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ContactEvent:
    t: float  # seconds
    obj_a: str
    obj_b: str
    point: tuple[float, float, float]
    impulse: float  # N*s, magnitude


# A trajectory passed to simulate(): (T, 7) array of pos (3) + quat wxyz (4).
Trajectory = np.ndarray


@dataclass
class SimResult:
    fps: int
    poses: dict[str, np.ndarray]  # obj_id -> (T, 7) pos + quat (w, x, y, z)
    velocities: dict[str, np.ndarray]  # obj_id -> (T, 6) linear + angular
    contacts: list[ContactEvent]
    backend: BackendInfo

    def __post_init__(self) -> None:
        if self.fps <= 0:
            raise ValueError("fps must be > 0")
        lengths = set()
        for oid, p in self.poses.items():
            if p.ndim != 2 or p.shape[1] != 7:
                raise ValueError(f"poses['{oid}'] must be (T, 7), got {p.shape}")
            lengths.add(p.shape[0])
        for oid, v in self.velocities.items():
            if oid not in self.poses:
                raise ValueError(f"velocities['{oid}'] has no matching poses entry")
            if v.shape != (self.poses[oid].shape[0], 6):
                raise ValueError(f"velocities['{oid}'] must be (T, 6), got {v.shape}")
        if len(lengths) > 1:
            raise ValueError(f"all pose arrays must share T, got {sorted(lengths)}")

    @property
    def num_frames(self) -> int:
        return next(iter(self.poses.values())).shape[0] if self.poses else 0


# --------------------------------------------------------------------------- protocol


NativeScene = Any  # MJCF string / USD stage / URDF / bpy scene; opaque outside the adapter


@runtime_checkable
class PhysicsAdapter(Protocol):
    name: str
    capabilities: Capabilities

    def check(self, ir: SceneIR) -> list[str]:
        """Unsupported features; non-empty => refuse."""
        ...

    def compile(self, ir: SceneIR) -> NativeScene:
        """IR -> engine-native scene. Must raise UnsupportedSceneError if check() fails."""
        ...

    def simulate(self, native: NativeScene, kinematic: dict[str, Trajectory] | None = None) -> SimResult:
        """Run the scene. ``kinematic`` overrides bodies with prescribed (T, 7) poses."""
        ...

    def param_map(self) -> dict[str, Any]:
        """IR param -> engine param mapping, incl. approximations. Written to the manifest."""
        ...
