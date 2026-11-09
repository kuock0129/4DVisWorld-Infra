"""MuJoCo physics adapter (CPU).

Timing: frame k is sampled at t = k / fps (frame 0 = initial state). The requested
``timestep`` is shrunk so an integer number of steps fits each frame period; the
effective value is recorded in ``SimResult.backend.solver_config``.

Kinematic bodies are MJCF mocap bodies. Their pose is set every step from the IR
trajectory, or from the ``kinematic`` override passed to simulate() (e.g. replayed
baseline poses for the non-causal member). Overriding a dynamic body recompiles it
as kinematic; static bodies cannot be overridden.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from vw.ir import BodyKind, SceneIR
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
from vw.physics.mujoco_mjcf import MJCFScene, ir_to_mjcf
from vw.physics.stubs import _AdapterBase
from vw.physics.util import effective_timestep, interp_pose as _interp_pose, quat_to_mat as _quat_to_mat
from vw.registry import register_physics

_OPTION_KEYS = ("integrator", "solver", "iterations", "cone", "tolerance", "noslip_iterations")


def _import_mujoco():
    try:
        import mujoco
    except ImportError as e:  # pragma: no cover - exercised only without the extra
        raise ImportError("MuJoCo adapter needs the 'mujoco' package: pip install -e '.[mujoco]'") from e
    return mujoco


@register_physics("mujoco")
class MuJoCoAdapter(_AdapterBase):
    """Config: timestep (s, default 0.002), integrator (Euler|implicitfast|implicit|RK4),
    solver (Newton|CG|PGS), iterations, cone (pyramidal|elliptic), contact_timeconst (s),
    record_contacts (bool, default True)."""

    name = "mujoco"
    capabilities = Capabilities(
        frozenset({Feature.RIGID, Feature.KINEMATIC, Feature.MESH_COLLISION}), frozenset({Device.CPU})
    )

    @property
    def version(self) -> str:  # type: ignore[override]
        try:
            return _import_mujoco().__version__
        except ImportError:
            return "not-installed"

    # ------------------------------------------------------------------ compile

    def compile(self, ir: SceneIR) -> NativeScene:
        self._require(ir)
        dt, _ = effective_timestep(float(self.config.get("timestep", 0.002)), ir.timing.fps)
        options = {k: self.config[k] for k in _OPTION_KEYS if k in self.config}
        return ir_to_mjcf(ir, timestep=dt, options=options, contact_timeconst=self.config.get("contact_timeconst"))

    def _with_overrides(self, scene: MJCFScene, kinematic: dict[str, Trajectory]) -> tuple[MJCFScene, dict]:
        ir, T = scene.ir, scene.ir.timing.frames
        arrays: dict[str, np.ndarray] = {}
        for bid, traj in kinematic.items():
            body = ir.body(bid)  # KeyError for unknown ids
            if body.kind is BodyKind.STATIC:
                raise UnsupportedSceneError(self.name, [f"cannot override static body '{bid}'"])
            arr = np.asarray(traj, dtype=float)
            if arr.shape != (T, 7):
                raise ValueError(f"kinematic['{bid}'] must be ({T}, 7), got {arr.shape}")
            arrays[bid] = arr
        need_recompile = [b for b in arrays if b not in scene.mocap_bodies]
        if not need_recompile:
            return scene, arrays
        data = ir.model_dump(mode="python")
        for b in data["bodies"]:
            if b["id"] in need_recompile:
                arr = arrays[b["id"]]
                b["kind"] = "kinematic"
                b["trajectory"] = {"positions": arr[:, :3].tolist(), "orientations": arr[:, 3:].tolist()}
                b["initial_pose"] = {"position": arr[0, :3].tolist(), "orientation": arr[0, 3:].tolist()}
        new_ir = SceneIR.model_validate(data)
        opts = {k: v for k, v in scene.options.items() if k != "contact_timeconst"}
        return ir_to_mjcf(new_ir, scene.timestep, opts, scene.options.get("contact_timeconst")), arrays

    # ------------------------------------------------------------------ simulate

    def simulate(self, native: NativeScene, kinematic: dict[str, Trajectory] | None = None) -> SimResult:
        mujoco = _import_mujoco()
        scene: MJCFScene = native
        scene, overrides = self._with_overrides(scene, kinematic or {})
        ir = scene.ir
        T, fps = ir.timing.frames, ir.timing.fps
        dt, n = scene.timestep, round(1.0 / (fps * scene.timestep))
        record_contacts = bool(self.config.get("record_contacts", True))

        m = mujoco.MjModel.from_xml_string(scene.xml)
        d = mujoco.MjData(m)

        # Initial velocities (IR: world frame; MuJoCo free joint: linear world, angular local).
        free_adr: dict[str, tuple[int, int]] = {}
        for bid in scene.free_bodies:
            j = m.joint(f"{bid}__free").id
            qa, va = int(m.jnt_qposadr[j]), int(m.jnt_dofadr[j])
            free_adr[bid] = (qa, va)
            b = ir.body(bid)
            R = _quat_to_mat(np.asarray(b.initial_pose.orientation))
            d.qvel[va : va + 3] = b.initial_linear_velocity
            d.qvel[va + 3 : va + 6] = R.T @ np.asarray(b.initial_angular_velocity)

        # Mocap trajectories.
        mocap: dict[str, tuple[int, np.ndarray]] = {}
        for bid in scene.mocap_bodies:
            traj = overrides.get(bid)
            if traj is None:
                tr = ir.body(bid).trajectory
                traj = np.hstack([np.asarray(tr.positions), np.asarray(tr.orientations)])
            mocap[bid] = (int(m.body_mocapid[m.body(bid).id]), traj)

        def set_mocap(frame_f: float) -> None:
            for mid, traj in mocap.values():
                pos, q = _interp_pose(traj, frame_f)
                d.mocap_pos[mid], d.mocap_quat[mid] = pos, q

        set_mocap(0.0)
        mujoco.mj_forward(m, d)

        geom_names = [mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, i) for i in range(m.ngeom)]
        poses = {b.id: np.zeros((T, 7)) for b in ir.bodies}
        vels = {b.id: np.zeros((T, 6)) for b in ir.bodies}
        static = {b.id: np.array([*b.initial_pose.position, *b.initial_pose.orientation]) for b in ir.bodies
                  if b.kind is BodyKind.STATIC}
        contacts: list[ContactEvent] = []
        f6 = np.zeros(6)

        def record(k: int) -> None:
            for bid, (qa, va) in free_adr.items():
                q = d.qpos[qa : qa + 7]
                poses[bid][k] = q
                vels[bid][k, :3] = d.qvel[va : va + 3]
                vels[bid][k, 3:] = _quat_to_mat(q[3:]) @ d.qvel[va + 3 : va + 6]
            for bid, (_, traj) in mocap.items():
                poses[bid][k] = traj[k]
            for bid, p in static.items():
                poses[bid][k] = p

        record(0)
        for k in range(1, T):
            acc: dict[tuple[str, str], list] = {}
            for s in range(n):
                set_mocap((k - 1) + (s + 1) / n)
                mujoco.mj_step(m, d)
                if record_contacts:
                    for i in range(d.ncon):
                        c = d.contact[i]
                        mujoco.mj_contactForce(m, d, i, f6)
                        imp = float(f6[0]) * dt
                        if imp <= 0.0:
                            continue
                        key = tuple(sorted((geom_names[c.geom1], geom_names[c.geom2])))
                        a = acc.setdefault(key, [0.0, np.zeros(3)])
                        a[0] += imp
                        a[1] += imp * c.pos
            record(k)
            for (ga, gb), (imp, wpos) in acc.items():
                contacts.append(ContactEvent(k / fps, ga, gb, tuple((wpos / imp).tolist()), imp))

        # Mocap bodies have no generalized velocity; finite-difference their positions.
        for bid in mocap:
            if T > 1:
                vels[bid][:, :3] = np.gradient(poses[bid][:, :3], 1.0 / fps, axis=0)

        info = self.backend_info()
        solver = {
            "timestep": dt,
            "timestep_requested": float(self.config.get("timestep", 0.002)),
            "steps_per_frame": n,
            "integrator": scene.options.get("integrator", "Euler"),
            "solver": scene.options.get("solver", "Newton"),
            "iterations": scene.options.get("iterations", 100),
            "cone": scene.options.get("cone", "pyramidal"),
            "contact_timeconst": scene.options["contact_timeconst"],
        }
        info = type(info)(info.name, self.version, info.device, solver)
        return SimResult(fps, poses, vels, contacts, info)

    def param_map(self) -> dict[str, Any]:
        return {
            "geometry.box.extents": {"to": "geom.size", "note": "exact: half-sizes = extents / 2"},
            "geometry.plane.extents": {"to": "geom.size[0:2]", "note": "exact: extents / 2; collision plane is infinite"},
            "geometry.cylinder|capsule.height": {"to": "geom.size[1]", "note": "exact: half-length = height / 2"},
            "material.friction": {
                "to": "geom.friction[0]",
                "note": "sliding only; torsional/rolling use MuJoCo defaults; pair value = max of the two geoms",
            },
            "material.restitution": {
                "to": "geom.solref[1] (dampratio)",
                "note": "approximation: zeta = -ln(e)/sqrt(pi^2+ln(e)^2), timeconst = max(0.02, 2*dt); "
                "pair value = mean of the two geoms",
            },
            "mass": {"to": "geom.mass", "note": "inertia from geometry, uniform density"},
            "linear_damping|angular_damping": {"to": "joint(free).damping", "note": "approximation: max of the two"},
            "initial_linear_velocity": {"to": "qvel[0:3] (world)", "note": "exact"},
            "initial_angular_velocity": {"to": "qvel[3:6] (body frame)", "note": "exact: rotated from world frame"},
            "kind=kinematic": {"to": "body.mocap", "note": "pose set every step; lerp/nlerp between frames"},
            "timing": {"to": "option.timestep", "note": "shrunk so an integer number of steps fits 1/fps"},
        }
