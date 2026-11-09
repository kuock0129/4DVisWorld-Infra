"""NVIDIA PhysX 5 adapter via SAPIEN 3 (CPU).

SAPIEN's ``PhysxCpuSystem`` wraps one PhysX scene with no renderer attached. PhysX
settings in SAPIEN are process-global (scene, body and shape configs), so every
simulate() sets them before building its scene.

GPU PhysX (``PhysxGpuSystem``) uses a batched tensor API and is not wired up yet; for
GPU, use the ``newton`` adapter.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any

import numpy as np

from vw.ir import BodyKind, Box, Capsule, Cylinder, Plane, SceneIR, Sphere
from vw.physics.base import (
    Capabilities,
    ContactEvent,
    Device,
    Feature,
    NativeScene,
    SimResult,
    Trajectory,
    UnsupportedSceneError,
)
from vw.physics.stubs import _AdapterBase
from vw.physics.util import contact_key, effective_timestep, finite_diff_velocities, interp_pose
from vw.registry import register_physics

# SAPIEN's cylinder / capsule axis and plane normal are local +X; the IR uses local +Z.
_X_TO_Z = (math.sqrt(0.5), 0.0, -math.sqrt(0.5), 0.0)  # rotation about y by -90 deg: x -> +z


def _import_sapien():
    try:
        import sapien
    except ImportError as e:  # pragma: no cover - exercised only without the extra
        raise ImportError("PhysX adapter needs SAPIEN: pip install -e '.[physx]'") from e
    return sapien


def _volume(g) -> float:
    if isinstance(g, Box):
        return float(np.prod(g.extents))
    if isinstance(g, Sphere):
        return 4.0 / 3.0 * math.pi * g.radius**3
    if isinstance(g, Cylinder):
        return math.pi * g.radius**2 * g.height
    if isinstance(g, Capsule):
        return math.pi * g.radius**2 * g.height + 4.0 / 3.0 * math.pi * g.radius**3
    raise TypeError(type(g).__name__)


@dataclass
class PhysXScene:
    ir: SceneIR
    config: dict[str, Any]  # resolved solver settings


@register_physics("physx")
class PhysXAdapter(_AdapterBase):
    """Config: timestep (s, default 0.002), solver (tgs|pgs, default tgs), position_iterations
    (default 4), velocity_iterations (default 1), bounce_threshold (m/s, default 0.05; PhysX's own
    default of 2 m/s would drop most bounces), enable_pcm (default True), enable_ccd (default
    False), contact_offset (m, default 0.01), max_depenetration_velocity (m/s, default PhysX's own,
    effectively unbounded: caps how fast deep overlaps are pushed apart), record_contacts (default True)."""

    name = "physx"
    capabilities = Capabilities(frozenset({Feature.RIGID, Feature.KINEMATIC}), frozenset({Device.CPU}))

    @property
    def version(self) -> str:  # type: ignore[override]
        try:
            sapien = _import_sapien()
        except ImportError:
            return "not-installed"
        return f"{sapien.physx.version().split('-', 1)[-1]} (sapien {sapien.__version__})"

    def check(self, ir: SceneIR) -> list[str]:
        problems = super().check(ir)
        if any(not isinstance(b.geometry, (Box, Sphere, Cylinder, Capsule, Plane)) for b in ir.bodies):
            problems.append("unsupported feature: mesh_collision (not implemented in the PhysX adapter yet)")
        return sorted(set(problems))

    def compile(self, ir: SceneIR) -> NativeScene:
        self._require(ir)
        c = self.config
        dt, n = effective_timestep(float(c.get("timestep", 0.002)), ir.timing.fps)
        cfg = {
            "timestep": dt,
            "timestep_requested": float(c.get("timestep", 0.002)),
            "steps_per_frame": n,
            "solver": str(c.get("solver", "tgs")).lower(),
            "position_iterations": int(c.get("position_iterations", 4)),
            "velocity_iterations": int(c.get("velocity_iterations", 1)),
            "bounce_threshold": float(c.get("bounce_threshold", 0.05)),
            "enable_pcm": bool(c.get("enable_pcm", True)),
            "enable_ccd": bool(c.get("enable_ccd", False)),
            "contact_offset": float(c.get("contact_offset", 0.01)),
            "max_depenetration_velocity": c.get("max_depenetration_velocity"),
        }
        if cfg["solver"] not in ("tgs", "pgs"):
            raise ValueError(f"physx solver must be 'tgs' or 'pgs', got {cfg['solver']!r}")
        return PhysXScene(ir, cfg)

    # ------------------------------------------------------------------ simulate

    def _build(self, sapien, scene_cfg: dict, ir: SceneIR, kinematic_ids: set[str]):
        px = sapien.physx
        px.set_scene_config(
            gravity=np.asarray(ir.gravity, dtype=np.float32),
            bounce_threshold=scene_cfg["bounce_threshold"],
            enable_pcm=scene_cfg["enable_pcm"],
            enable_tgs=scene_cfg["solver"] == "tgs",
            enable_ccd=scene_cfg["enable_ccd"],
            enable_enhanced_determinism=True,
        )
        px.set_body_config(
            sleep_threshold=0.0,
            solver_position_iterations=scene_cfg["position_iterations"],
            solver_velocity_iterations=scene_cfg["velocity_iterations"],
        )
        px.set_shape_config(contact_offset=scene_cfg["contact_offset"], rest_offset=0.0)
        scene = sapien.Scene([px.PhysxCpuSystem()])
        scene.set_timestep(scene_cfg["timestep"])

        entities, bodies = {}, {}
        for b in ir.bodies:
            g = b.geometry
            mu = b.material.friction
            mat = px.PhysxMaterial(mu, mu, b.material.restitution)
            builder = scene.create_actor_builder()
            dynamic = b.kind is BodyKind.DYNAMIC and b.id not in kinematic_ids
            density = (b.mass / _volume(g)) if dynamic else 1000.0
            axis = sapien.Pose(q=list(_X_TO_Z))
            if isinstance(g, Box):
                builder.add_box_collision(half_size=[e / 2 for e in g.extents], material=mat, density=density)
            elif isinstance(g, Sphere):
                builder.add_sphere_collision(radius=g.radius, material=mat, density=density)
            elif isinstance(g, Cylinder):
                builder.add_cylinder_collision(axis, radius=g.radius, half_length=g.height / 2, material=mat, density=density)
            elif isinstance(g, Capsule):
                builder.add_capsule_collision(axis, radius=g.radius, half_length=g.height / 2, material=mat, density=density)
            elif isinstance(g, Plane):
                builder.add_plane_collision(axis, material=mat)
            p = b.initial_pose
            builder.set_initial_pose(sapien.Pose(list(p.position), list(p.orientation)))
            if b.kind is BodyKind.STATIC:
                ent = builder.build_static(name=b.id)
            elif dynamic:
                ent = builder.build(name=b.id)
            else:
                ent = builder.build_kinematic(name=b.id)
            entities[b.id] = ent
            if b.kind is not BodyKind.STATIC:
                body = ent.find_component_by_type(px.PhysxRigidDynamicComponent)
                if dynamic:
                    if scene_cfg["max_depenetration_velocity"] is not None:
                        body.set_max_depenetration_velocity(float(scene_cfg["max_depenetration_velocity"]))
                    body.set_linear_damping(b.linear_damping)
                    body.set_angular_damping(b.angular_damping)
                    body.set_linear_velocity(list(b.initial_linear_velocity))
                    body.set_angular_velocity(list(b.initial_angular_velocity))  # world frame in PhysX
                bodies[b.id] = body
        return scene, entities, bodies

    def simulate(self, native: NativeScene, kinematic: dict[str, Trajectory] | None = None) -> SimResult:
        sapien = _import_sapien()
        job: PhysXScene = native
        ir, cfg = job.ir, job.config
        T, fps, n = ir.timing.frames, ir.timing.fps, cfg["steps_per_frame"]
        record_contacts = bool(self.config.get("record_contacts", True))

        tracks: dict[str, np.ndarray] = {}
        for bid, traj in (kinematic or {}).items():
            body = ir.body(bid)  # KeyError for unknown ids
            if body.kind is BodyKind.STATIC:
                raise UnsupportedSceneError(self.name, [f"cannot override static body '{bid}'"])
            arr = np.asarray(traj, dtype=float)
            if arr.shape != (T, 7):
                raise ValueError(f"kinematic['{bid}'] must be ({T}, 7), got {arr.shape}")
            tracks[bid] = arr
        for b in ir.bodies:
            if b.kind is BodyKind.KINEMATIC and b.id not in tracks:
                tracks[b.id] = np.hstack([np.asarray(b.trajectory.positions), np.asarray(b.trajectory.orientations)])

        scene, entities, bodies = self._build(sapien, cfg, ir, set(tracks))
        poses = {b.id: np.zeros((T, 7)) for b in ir.bodies}
        vels = {b.id: np.zeros((T, 6)) for b in ir.bodies}
        static = {b.id: np.array([*b.initial_pose.position, *b.initial_pose.orientation]) for b in ir.bodies
                  if b.kind is BodyKind.STATIC}
        dynamic = {bid: body for bid, body in bodies.items() if bid not in tracks}
        contacts: list[ContactEvent] = []

        def record(k: int) -> None:
            for bid, body in dynamic.items():
                pose = entities[bid].pose
                poses[bid][k, :3], poses[bid][k, 3:] = pose.p, pose.q
                vels[bid][k, :3], vels[bid][k, 3:] = body.linear_velocity, body.angular_velocity
            for bid, traj in tracks.items():
                poses[bid][k] = traj[k]
            for bid, p in static.items():
                poses[bid][k] = p

        t0 = time.perf_counter()
        record(0)
        for k in range(1, T):
            acc: dict[tuple[str, str], list] = {}
            for s in range(n):
                for bid, traj in tracks.items():
                    pos, q = interp_pose(traj, (k - 1) + (s + 1) / n)
                    bodies[bid].set_kinematic_target(sapien.Pose(pos, q))
                scene.step()
                if record_contacts:
                    for c in scene.get_contacts():
                        imp, wpos = 0.0, np.zeros(3)
                        for pt in c.points:
                            m = float(np.linalg.norm(pt.impulse))
                            imp += m
                            wpos += m * np.asarray(pt.position)
                        if imp <= 0.0:
                            continue
                        key = contact_key(c.bodies[0].entity.name, c.bodies[1].entity.name)
                        a = acc.setdefault(key, [0.0, np.zeros(3)])
                        a[0] += imp
                        a[1] += wpos
            record(k)
            for (ga, gb), (imp, wpos) in acc.items():
                contacts.append(ContactEvent(k / fps, ga, gb, tuple((wpos / imp).tolist()), imp))
        sim_wall = time.perf_counter() - t0

        for bid in tracks:
            vels[bid] = finite_diff_velocities(poses[bid], fps)
        info = self.backend_info()
        solver = {**cfg, "sim_wall_s": sim_wall}
        return SimResult(fps, poses, vels, contacts, type(info)(info.name, self.version, info.device, solver))

    def param_map(self) -> dict[str, Any]:
        return {
            "geometry.box.extents": {"to": "PxBoxGeometry half extents", "note": "exact: extents / 2"},
            "geometry.cylinder|capsule": {"to": "PxCapsule / convex cylinder", "note": "exact; axis rotated from X to Z, half_length = height / 2"},
            "geometry.plane": {"to": "PxPlane", "note": "exact (infinite); normal rotated from X to Z"},
            "material.friction": {"to": "PxMaterial static = dynamic friction", "note": "PhysX averages the pair"},
            "material.restitution": {"to": "PxMaterial restitution", "note": "PhysX averages the pair; no bounce below bounce_threshold"},
            "mass": {"to": "shape density = mass / volume", "note": "inertia from the shape"},
            "linear_damping|angular_damping": {"to": "PxRigidDynamic damping", "note": "approximation: PhysX damping is v *= 1 / (1 + dt * d)"},
            "initial_linear_velocity|initial_angular_velocity": {"to": "setLinearVelocity / setAngularVelocity", "note": "exact, world frame"},
            "kind=kinematic": {"to": "kinematic actor, setKinematicTarget every step", "note": "lerp/nlerp between frames"},
            "timing": {"to": "scene timestep", "note": "shrunk so an integer number of steps fits 1/fps"},
            "sleeping": {"to": "sleep_threshold = 0", "note": "bodies never sleep"},
            "determinism": {"to": "enable_enhanced_determinism", "note": "on"},
        }
