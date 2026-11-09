"""Scene IR v0.1: the canonical, simulator-agnostic scene description.

Conventions
-----------
* SI units throughout (meters, kilograms, seconds).
* Right-handed, Z-up world frame (matches Blender and MuJoCo).
* Quaternions are (w, x, y, z) and must be unit length.
* Cameras look along their local -Z axis with local +Y up (Blender / OpenGL).
* Geometry dimensions are named per shape. Box / plane ``extents`` are FULL edge
  lengths in meters (Blender primitive / UsdGeomCube convention); adapters that
  want half-sizes (MuJoCo, PhysX) divide by 2 themselves. Cylinder / capsule
  ``height`` is the full length along local Z (capsule: excluding the end caps).

Rules (see docs/HANDOFF.md)
---------------------------
1. Physical semantics only. Solver parameters (substeps, iterations, margins)
   belong in adapter config, never here. ``extra="forbid"`` enforces it.
2. ``level=physical`` can be re-simulated (causal interventions).
   ``level=trace`` carries geometry + per-frame poses only (render / non-causal).
"""

from __future__ import annotations

import hashlib
import json
import math
from enum import Enum
from pathlib import Path
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

IR_VERSION = "0.1"

Vec3 = tuple[float, float, float]
Quat = tuple[float, float, float, float]

_QUAT_TOL = 1e-4


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=False)


class Level(str, Enum):
    PHYSICAL = "physical"
    TRACE = "trace"


class BodyKind(str, Enum):
    DYNAMIC = "dynamic"
    STATIC = "static"
    KINEMATIC = "kinematic"


# --------------------------------------------------------------------------- geometry

PositiveFloat = Annotated[float, Field(gt=0.0)]


class Box(_Model):
    type: Literal["box"] = "box"
    extents: tuple[PositiveFloat, PositiveFloat, PositiveFloat] = Field(
        description="Full edge lengths in meters [x, y, z] (NOT half-sizes)"
    )


class Sphere(_Model):
    type: Literal["sphere"] = "sphere"
    radius: PositiveFloat


class Cylinder(_Model):
    type: Literal["cylinder"] = "cylinder"
    radius: PositiveFloat
    height: PositiveFloat = Field(description="Full length along local Z, meters")


class Capsule(_Model):
    type: Literal["capsule"] = "capsule"
    radius: PositiveFloat
    height: PositiveFloat = Field(description="Full length of the cylindrical part along local Z, meters")


class Plane(_Model):
    """Infinite collision plane (normal = local +Z); extents bound the visual only."""

    type: Literal["plane"] = "plane"
    extents: tuple[PositiveFloat, PositiveFloat] = Field(description="Full visual edge lengths [x, y], meters")


Primitive = Union[Box, Sphere, Cylinder, Capsule, Plane]


class Mesh(_Model):
    type: Literal["mesh"] = "mesh"
    path: str = Field(description="Visual mesh, relative to the IR file")
    collision_path: str | None = Field(
        default=None, description="Collision mesh (convex or decomposed); defaults to visual mesh"
    )
    scale: Vec3 = (1.0, 1.0, 1.0)


Geometry = Annotated[Union[Box, Sphere, Cylinder, Capsule, Plane, Mesh], Field(discriminator="type")]


# --------------------------------------------------------------------------- state


def _check_quat(q: Quat, where: str) -> None:
    n = math.sqrt(sum(c * c for c in q))
    if abs(n - 1.0) > _QUAT_TOL:
        raise ValueError(f"{where}: quaternion must be unit length (|q|={n:.6f})")


class Pose(_Model):
    position: Vec3 = (0.0, 0.0, 0.0)
    orientation: Quat = (1.0, 0.0, 0.0, 0.0)

    @model_validator(mode="after")
    def _unit(self) -> Pose:
        _check_quat(self.orientation, "pose")
        return self


class Trajectory(_Model):
    """Per-frame poses, one entry per frame of ``timing.frames``."""

    positions: list[Vec3]
    orientations: list[Quat]

    @model_validator(mode="after")
    def _consistent(self) -> Trajectory:
        if len(self.positions) != len(self.orientations):
            raise ValueError("trajectory positions/orientations length mismatch")
        if not self.positions:
            raise ValueError("trajectory must have at least one frame")
        for i, q in enumerate(self.orientations):
            _check_quat(q, f"trajectory frame {i}")
        return self

    def __len__(self) -> int:
        return len(self.positions)


class Material(_Model):
    friction: float = Field(default=0.5, ge=0.0)
    restitution: float = Field(default=0.0, ge=0.0, le=1.0)


class Appearance(_Model):
    """Render-only hints; physics adapters must ignore these."""

    color: tuple[float, float, float] | None = None
    material_ref: str | None = None


class Body(_Model):
    id: str = Field(min_length=1)
    kind: BodyKind
    geometry: Geometry
    mass: float | None = Field(default=None, gt=0.0, description="kg; required for dynamic bodies")
    material: Material = Material()
    initial_pose: Pose = Pose()
    initial_linear_velocity: Vec3 = Field(default=(0.0, 0.0, 0.0), description="m/s, world frame")
    initial_angular_velocity: Vec3 = Field(default=(0.0, 0.0, 0.0), description="rad/s, world frame")
    linear_damping: float = Field(default=0.0, ge=0.0)
    angular_damping: float = Field(default=0.0, ge=0.0)
    trajectory: Trajectory | None = Field(
        default=None, description="Required for kinematic bodies and for non-static bodies at trace level"
    )
    appearance: Appearance = Appearance()

    @model_validator(mode="after")
    def _kind_rules(self) -> Body:
        if self.kind is BodyKind.KINEMATIC and self.trajectory is None:
            raise ValueError(f"body '{self.id}': kinematic bodies need a trajectory")
        if self.kind is BodyKind.STATIC and self.trajectory is not None:
            raise ValueError(f"body '{self.id}': static bodies must not have a trajectory")
        return self


# --------------------------------------------------------------------------- view


class Camera(_Model):
    id: str = Field(min_length=1)
    pose: Pose
    fov_deg: float = Field(default=50.0, gt=0.0, lt=180.0, description="Vertical field of view")
    resolution: tuple[int, int] = Field(default=(512, 512), description="(width, height)")
    trajectory: Trajectory | None = None


class Light(_Model):
    id: str = Field(min_length=1)
    type: Literal["sun", "point", "area", "spot"]
    pose: Pose
    intensity: float = Field(gt=0.0, description="W for point/area/spot, W/m^2 for sun")
    color: tuple[float, float, float] = (1.0, 1.0, 1.0)


class Timing(_Model):
    fps: int = Field(default=24, gt=0)
    frames: int = Field(default=48, gt=0)


# --------------------------------------------------------------------------- scene


class SceneIR(_Model):
    ir_version: Literal["0.1"] = IR_VERSION
    level: Level
    gravity: Vec3 = (0.0, 0.0, -9.81)
    timing: Timing = Timing()
    bodies: list[Body]
    cameras: list[Camera] = Field(min_length=1)
    lights: list[Light] = []
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Provenance only (source video, agent run); never semantics"
    )

    @model_validator(mode="after")
    def _scene_rules(self) -> SceneIR:
        ids = [b.id for b in self.bodies] + [c.id for c in self.cameras] + [l.id for l in self.lights]
        dup = sorted({i for i in ids if ids.count(i) > 1})
        if dup:
            raise ValueError(f"duplicate ids: {dup}")

        n = self.timing.frames
        for b in self.bodies:
            if b.trajectory is not None and len(b.trajectory) != n:
                raise ValueError(
                    f"body '{b.id}': trajectory has {len(b.trajectory)} frames, timing.frames={n}"
                )
            if self.level is Level.PHYSICAL and b.kind is BodyKind.DYNAMIC and b.mass is None:
                raise ValueError(f"body '{b.id}': dynamic bodies need mass at level=physical")
            if self.level is Level.TRACE and b.kind is not BodyKind.STATIC and b.trajectory is None:
                raise ValueError(f"body '{b.id}': non-static bodies need a trajectory at level=trace")
        for c in self.cameras:
            if c.trajectory is not None and len(c.trajectory) != n:
                raise ValueError(f"camera '{c.id}': trajectory length != timing.frames")
        return self

    # ---- helpers

    def body(self, body_id: str) -> Body:
        for b in self.bodies:
            if b.id == body_id:
                return b
        raise KeyError(body_id)

    def canonical_json(self) -> str:
        """Deterministic serialization (sorted keys, defaults included) used for hashing."""
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))

    def content_hash(self) -> str:
        return "sha256:" + hashlib.sha256(self.canonical_json().encode()).hexdigest()

    @classmethod
    def load(cls, path: str | Path) -> SceneIR:
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))

    def save(self, path: str | Path) -> None:
        Path(path).write_text(self.model_dump_json(indent=2), encoding="utf-8")
