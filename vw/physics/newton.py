"""Newton adapter (NVIDIA Warp; GPU or CPU).

Newton is a GPU physics engine built on Warp. It ships several rigid-body solvers;
this adapter exposes ``xpbd`` (position-based, supports restitution), ``mujoco``
(MuJoCo Warp: MuJoCo's soft-contact solver on the GPU) and ``semi_implicit``.

Execution: one Warp "frame" = ``steps_per_frame`` x (collide + solver step) followed by
a kernel that writes the state into a device-side history buffer, so the CPU never
waits on the GPU until the end. On CUDA the frame is captured once as a CUDA graph and
replayed. Frame 1 runs uncaptured, which also JIT-compiles the kernels; the reported
``sim_wall_s`` covers frames 2..T-1 only (scaled to the full run) so it measures
stepping, not compilation.

Kinematic bodies (IR ``kind=kinematic`` and ``simulate(kinematic=...)`` overrides) are
Newton kinematic bodies. Their free-joint coordinates are written from a precomputed
per-substep track each substep and pushed to the body state with ``eval_fk``.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any

import numpy as np

from vw.ir import BodyKind, Box, Capsule, Cylinder, Plane, SceneIR, Sphere
from vw.physics.base import Capabilities, Device, Feature, NativeScene, SimResult, Trajectory, UnsupportedSceneError
from vw.physics.stubs import _AdapterBase
from vw.physics.util import effective_timestep, finite_diff_velocities, interp_pose
from vw.registry import register_physics

SOLVERS = ("xpbd", "mujoco", "semi_implicit")


def _import_newton():
    try:
        import newton
        import warp as wp
    except ImportError as e:  # pragma: no cover - exercised only without the extra
        raise ImportError("Newton adapter needs newton + warp: pip install -e '.[newton]'") from e
    wp.config.quiet = True
    return newton, wp


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


def _wxyz_to_xyzw(q) -> list[float]:
    return [q[1], q[2], q[3], q[0]]


@dataclass
class NewtonScene:
    ir: SceneIR
    config: dict[str, Any]


def _kernels(wp):
    """Warp kernels live in a separate module (no postponed annotations, which Warp needs)."""
    from vw.physics import _newton_kernels as k

    return {"set_kinematic": k.set_kinematic, "advance": k.advance, "record": k.record}


@register_physics("newton")
class NewtonAdapter(_AdapterBase):
    """Config: solver (xpbd|mujoco|semi_implicit, default xpbd), timestep (s, default 0.002),
    iterations (XPBD iterations, default 8), deterministic (default True: run-to-run deterministic
    atomics and contact sorting; GPU runs are otherwise not reproducible), cuda_graph (default True on CUDA), worlds (default 1:
    N independent copies of the scene in one model, for throughput; world 0 is returned)."""

    name = "newton"
    capabilities = Capabilities(frozenset({Feature.RIGID, Feature.KINEMATIC}), frozenset({Device.CUDA, Device.CPU}))

    @property
    def version(self) -> str:  # type: ignore[override]
        try:
            newton, wp = _import_newton()
        except ImportError:
            return "not-installed"
        return f"{newton.__version__} (warp {wp.__version__})"

    def check(self, ir: SceneIR) -> list[str]:
        problems = super().check(ir)
        if any(not isinstance(b.geometry, (Box, Sphere, Cylinder, Capsule, Plane)) for b in ir.bodies):
            problems.append("unsupported feature: mesh_collision (not implemented in the Newton adapter yet)")
        if any(b.linear_damping or b.angular_damping for b in ir.bodies):
            problems.append("unsupported: per-body damping (Newton solvers have no per-body damping)")
        return sorted(set(problems))

    def compile(self, ir: SceneIR) -> NativeScene:
        self._require(ir)
        c = self.config
        solver = str(c.get("solver", "xpbd")).lower()
        if solver not in SOLVERS:
            raise ValueError(f"newton solver must be one of {SOLVERS}, got {solver!r}")
        dt, n = effective_timestep(float(c.get("timestep", 0.002)), ir.timing.fps)
        cfg = {
            "solver": solver,
            "timestep": dt,
            "timestep_requested": float(c.get("timestep", 0.002)),
            "steps_per_frame": n,
            "iterations": int(c.get("iterations", 8)) if solver == "xpbd" else None,
            "cuda_graph": bool(c.get("cuda_graph", True)) and self.device is Device.CUDA,
            "worlds": int(c.get("worlds", 1)),
            # MuJoCo Warp cannot run in Warp's deterministic mode (see _solver): reported honestly.
            "deterministic": bool(c.get("deterministic", True)) and solver != "mujoco",
        }
        if cfg["worlds"] < 1:
            raise ValueError("worlds must be >= 1")
        return NewtonScene(ir, cfg)

    # ------------------------------------------------------------------ build

    def _build(self, newton, wp, ir: SceneIR, kinematic_ids: set[str], device: str, mu_min: float = 0.0):
        builder = newton.ModelBuilder(gravity=tuple(ir.gravity))
        body_index: dict[str, int] = {}
        for b in ir.bodies:
            g = b.geometry
            p = b.initial_pose
            xform = wp.transform(tuple(p.position), tuple(_wxyz_to_xyzw(p.orientation)))
            dynamic = b.kind is BodyKind.DYNAMIC and b.id not in kinematic_ids
            cfg = newton.ModelBuilder.ShapeConfig(
                mu=max(b.material.friction, mu_min),
                restitution=b.material.restitution,
                density=(b.mass / _volume(g)) if dynamic else 1000.0,
            )
            if b.kind is BodyKind.STATIC:
                body, shape_xform = -1, xform
            else:
                body = builder.add_body(xform=xform, label=b.id, is_kinematic=not dynamic)
                body_index[b.id] = body
                shape_xform = None
            kw = {"xform": shape_xform, "cfg": cfg, "label": b.id}
            if isinstance(g, Box):
                builder.add_shape_box(body, hx=g.extents[0] / 2, hy=g.extents[1] / 2, hz=g.extents[2] / 2, **kw)
            elif isinstance(g, Sphere):
                builder.add_shape_sphere(body, radius=g.radius, **kw)
            elif isinstance(g, Cylinder):
                builder.add_shape_cylinder(body, radius=g.radius, half_height=g.height / 2, **kw)
            elif isinstance(g, Capsule):
                builder.add_shape_capsule(body, radius=g.radius, half_height=g.height / 2, **kw)
            elif isinstance(g, Plane):
                builder.add_shape_plane(plane=None, xform=xform, width=0.0, length=0.0, body=-1, cfg=cfg, label=b.id)
        worlds = self.config.get("worlds", 1)
        if int(worlds) > 1:
            # Independent copies of the scene in one model (throughput benchmarking); world 0 is reported.
            top = newton.ModelBuilder(gravity=tuple(ir.gravity))
            top.replicate(builder, int(worlds))
            builder = top
        return builder.finalize(device=device), body_index

    def _solver(self, newton, wp, model, cfg):
        det = wp.DeterministicMode.RUN_TO_RUN if cfg["deterministic"] else wp.DeterministicMode.NOT_GUARANTEED
        if cfg["solver"] == "xpbd":
            return newton.solvers.SolverXPBD(model, iterations=cfg["iterations"], enable_restitution=True,
                                             deterministic=det)
        if cfg["solver"] == "mujoco":
            # Default contact buffers overflow on a 5-box stack (boxes sink through each other).
            # Not run-to-run deterministic: Newton 1.7 cannot build MuJoCo Warp's contact conversion
            # kernel in deterministic mode (WarpDeterminismError), so compile() reports deterministic=False.
            return newton.solvers.SolverMuJoCo(model, nconmax=256, njmax=1024)
        return newton.solvers.SolverSemiImplicit(model)

    # ------------------------------------------------------------------ simulate

    def simulate(self, native: NativeScene, kinematic: dict[str, Trajectory] | None = None) -> SimResult:
        newton, wp = _import_newton()
        job: NewtonScene = native
        ir, cfg = job.ir, job.config
        T, fps, n, dt = ir.timing.frames, ir.timing.fps, cfg["steps_per_frame"], cfg["timestep"]
        device = "cuda:0" if self.device is Device.CUDA else "cpu"

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

        with wp.ScopedDevice(device):
            # MuJoCo Warp produces NaNs on frictionless contacts (pyramidal cone with mu = 0).
            mu_min = 1e-3 if cfg["solver"] == "mujoco" else 0.0
            model, body_index = self._build(newton, wp, ir, set(tracks), device, mu_min)
            solver = self._solver(newton, wp, model, cfg)
            s0, s1, control = model.state(), model.state(), model.control()
            # MuJoCo Warp runs its own collision detection; the others use Newton's pipeline.
            use_pipe = cfg["solver"] != "mujoco"
            pipe = newton.CollisionPipeline(model, deterministic=cfg["deterministic"]) if use_pipe else None
            contacts = pipe.contacts() if use_pipe else None

            # Initial velocities (world frame; body origin = COM for the IR primitives).
            W = cfg["worlds"]
            nb_local = len(body_index)
            qd = s0.body_qd.numpy()
            for b in ir.bodies:
                if b.id in body_index and b.id not in tracks:
                    for w in range(W):
                        qd[w * nb_local + body_index[b.id]] = [*b.initial_linear_velocity, *b.initial_angular_velocity]
            s0.body_qd.assign(qd)
            newton.eval_ik(model, s0, s0.joint_q, s0.joint_qd)

            # Per-substep kinematic track (free-joint q/qd) on the device.
            K = len(tracks)
            kern = _kernels(wp)
            step_ctr = wp.zeros(1, dtype=wp.int32)
            frame_ctr = wp.zeros(1, dtype=wp.int32)
            nb = nb_local  # world 0 occupies body indices [0, nb_local)
            hist_q = wp.zeros((T, nb), dtype=wp.transform)
            hist_qd = wp.zeros((T, nb), dtype=wp.spatial_vector)
            if K:
                S = (T - 1) * n
                tq = np.zeros((S, K * 7), dtype=np.float32)
                tqd = np.zeros((S, K * 6), dtype=np.float32)
                jstart_q = model.joint_q_start.numpy()
                jstart_qd = model.joint_qd_start.numpy()
                jchild = model.joint_child.numpy()
                q_start, qd_start = [], []
                for w in range(W):
                    for bid in tracks:
                        j = int(np.flatnonzero(jchild == w * nb_local + body_index[bid])[0])
                        q_start.append(int(jstart_q[j]))
                        qd_start.append(int(jstart_qd[j]))
                for k, (bid, traj) in enumerate(tracks.items()):
                    vel = finite_diff_velocities(traj, fps)
                    for s in range(S):
                        f = (s + 1) / n
                        pos, q = interp_pose(traj, f)
                        i = min(int(f), T - 2)
                        tq[s, k * 7 : k * 7 + 7] = [*pos, *_wxyz_to_xyzw(q)]
                        tqd[s, k * 6 : k * 6 + 6] = (1 - (f - i)) * vel[i] + (f - i) * vel[i + 1]
                track_q = wp.array(np.tile(tq, (1, W)), dtype=wp.float32)
                track_qd = wp.array(np.tile(tqd, (1, W)), dtype=wp.float32)
                q_start_w = wp.array(q_start, dtype=wp.int32)
                qd_start_w = wp.array(qd_start, dtype=wp.int32)
                # Frame 0 pose of kinematic bodies.
                jq = s0.joint_q.numpy()
                for w in range(W):
                    for k, traj in enumerate(tracks.values()):
                        qs = q_start[w * K + k]
                        jq[qs : qs + 7] = [*traj[0, :3], *_wxyz_to_xyzw(traj[0, 3:])]
                s0.joint_q.assign(jq)
                newton.eval_fk(model, s0.joint_q, s0.joint_qd, s0)

            states = [s0, s1]

            def frame():
                for _ in range(n):
                    a, b_ = states[0], states[1]
                    a.clear_forces()
                    if K:
                        wp.launch(kern["set_kinematic"], dim=K * W,
                                  inputs=[track_q, track_qd, q_start_w, qd_start_w, step_ctr],
                                  outputs=[a.joint_q, a.joint_qd])
                        newton.eval_fk(model, a.joint_q, a.joint_qd, a, body_flag_filter=newton.BodyFlags.KINEMATIC)
                        wp.launch(kern["advance"], dim=1, inputs=[step_ctr])
                    if use_pipe:
                        pipe.collide(a, contacts)
                    solver.step(a, b_, control, contacts if use_pipe else None, dt)
                    states.reverse()
                wp.launch(kern["advance"], dim=1, inputs=[frame_ctr])
                wp.launch(kern["record"], dim=nb, inputs=[states[0].body_q, states[0].body_qd, frame_ctr],
                          outputs=[hist_q, hist_qd])

            wp.launch(kern["record"], dim=nb, inputs=[s0.body_q, s0.body_qd, frame_ctr], outputs=[hist_q, hist_qd])
            if T > 1:
                frame()  # frame 1: uncaptured, compiles kernels
            wp.synchronize()
            graphs = []
            if cfg["cuda_graph"] and T > 2:
                # A captured frame bakes in which state buffer it starts from. With an odd substep
                # count the start buffer alternates, so capture one graph per parity.
                for _ in range(1 if n % 2 == 0 else 2):
                    with wp.ScopedCapture() as cap:
                        frame()
                    graphs.append(cap.graph)
            t0 = time.perf_counter()
            for i in range(T - 2):
                if graphs:
                    wp.capture_launch(graphs[i % len(graphs)])
                else:
                    frame()
            wp.synchronize()
            loop = time.perf_counter() - t0
            sim_wall = loop * (T - 1) / max(T - 2, 1)
            hq = hist_q.numpy()
            hqd = hist_qd.numpy()

        poses, vels = {}, {}
        for b in ir.bodies:
            if b.kind is BodyKind.STATIC:
                poses[b.id] = np.tile([*b.initial_pose.position, *b.initial_pose.orientation], (T, 1)).astype(float)
                vels[b.id] = np.zeros((T, 6))
                continue
            if b.id in tracks:
                poses[b.id] = tracks[b.id].copy()
                vels[b.id] = finite_diff_velocities(poses[b.id], fps)
                continue
            i = body_index[b.id]
            x = hq[:, i].astype(float)  # (T, 7): p, q xyzw
            p = np.hstack([x[:, :3], x[:, 6:7], x[:, 3:6]])
            p[:, 3:] /= np.linalg.norm(p[:, 3:], axis=1, keepdims=True)
            poses[b.id] = p
            vels[b.id] = hqd[:, i].astype(float)
        info = self.backend_info()
        solver_cfg = {**cfg, "cuda_graph": bool(graphs), "sim_wall_s": sim_wall, "contacts": "not recorded"}
        return SimResult(fps, poses, vels, [], type(info)(info.name, self.version, info.device, solver_cfg))

    def param_map(self) -> dict[str, Any]:
        return {
            "geometry.box|sphere|cylinder|capsule": {"to": "Newton shapes", "note": "exact; half sizes, Z axis"},
            "geometry.plane": {"to": "add_shape_plane(width=0, length=0)", "note": "exact (infinite)"},
            "material.friction": {"to": "ShapeConfig.mu", "note": "XPBD averages the pair; mujoco solver follows MuJoCo (max) and clamps mu >= 1e-3 (mu below about 1e-4 gives NaNs)"},
            "material.restitution": {"to": "ShapeConfig.restitution", "note": "used by XPBD (enable_restitution=True) only; the mujoco and semi_implicit solvers ignore it"},
            "mass": {"to": "ShapeConfig.density = mass / volume", "note": "inertia from the shape"},
            "linear_damping|angular_damping": {"to": "none", "note": "refused by check(): no per-body damping"},
            "initial_linear_velocity|initial_angular_velocity": {"to": "State.body_qd (world) + eval_ik", "note": "exact"},
            "kind=kinematic": {"to": "is_kinematic body; free-joint q/qd set every substep + eval_fk", "note": "lerp/nlerp between frames"},
            "timing": {"to": "solver dt", "note": "shrunk so an integer number of steps fits 1/fps"},
            "contacts": {"to": "none", "note": "not recorded yet; SimResult.contacts is empty"},
        }
