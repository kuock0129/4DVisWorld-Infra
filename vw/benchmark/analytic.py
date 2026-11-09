"""Analytic physics test suite: scenes with closed-form answers.

Every case builds a Scene IR, runs it through a physics adapter, and compares a
measured quantity against the textbook value. Combination rules matter: each case
gives BOTH bodies in a contact the same friction / restitution, so the result does
not depend on whether a backend combines pairs by max, mean or product (see the
benchmark report for why this is still an open IR question).

Pendulum period is not included: IR v0.1 has no joints. ``roll`` checks that rolling
contact does not lose energy.
"""

from __future__ import annotations

import math
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

import numpy as np

from vw.ir import SceneIR
from vw.physics.base import PhysicsAdapter, SimResult

G = 9.81
FPS = 250  # 4 ms frames: fine enough to resolve contacts, divides 4/2/1/0.5 ms steps exactly


@dataclass
class CaseResult:
    case: str
    metric: str
    unit: str
    expected: float
    measured: float
    params: dict[str, Any] = field(default_factory=dict)
    sim_wall_s: float = 0.0

    @property
    def abs_err(self) -> float:
        return abs(self.measured - self.expected)

    @property
    def rel_err(self) -> float | None:
        return self.abs_err / abs(self.expected) if self.expected != 0 else None

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "abs_err": self.abs_err, "rel_err": self.rel_err}


# --------------------------------------------------------------------------- scene helpers

_CAMERA = {"id": "cam", "pose": {"position": [0, -5, 1], "orientation": [0.7071068, 0.7071068, 0, 0]}}


def _ground(friction: float = 0.5, restitution: float = 0.0) -> dict:
    return {
        "id": "ground",
        "kind": "static",
        "geometry": {"type": "plane", "extents": [20.0, 20.0]},
        "material": {"friction": friction, "restitution": restitution},
    }


def _sphere(bid: str, pos, radius=0.1, mass=1.0, vel=(0, 0, 0), friction=0.5, restitution=0.0) -> dict:
    return {
        "id": bid,
        "kind": "dynamic",
        "mass": mass,
        "geometry": {"type": "sphere", "radius": radius},
        "material": {"friction": friction, "restitution": restitution},
        "initial_pose": {"position": list(pos)},
        "initial_linear_velocity": list(vel),
    }


def _box(bid: str, pos, edge=0.2, mass=1.0, vel=(0, 0, 0), friction=0.5, restitution=0.0) -> dict:
    return {
        "id": bid,
        "kind": "dynamic",
        "mass": mass,
        "geometry": {"type": "box", "extents": [edge, edge, edge]},
        "material": {"friction": friction, "restitution": restitution},
        "initial_pose": {"position": list(pos)},
        "initial_linear_velocity": list(vel),
    }


def scene(name: str, bodies: list[dict], duration: float, gravity=(0.0, 0.0, -G)) -> SceneIR:
    frames = int(round(duration * FPS)) + 1
    return SceneIR.model_validate(
        {
            "level": "physical",
            "gravity": list(gravity),
            "timing": {"fps": FPS, "frames": frames},
            "bodies": bodies,
            "cameras": [_CAMERA],
            "metadata": {"name": name, "source": "vw.benchmark.analytic"},
        }
    )


REPEATS = 1  # wall-clock = min over this many simulate() calls; the runner raises it


def sim_wall(sim: SimResult, measured: float) -> float:
    """Stepping time: the backend's own figure when it reports one (process-based adapters
    such as Blender would otherwise be charged their start-up cost), else ``measured``."""
    return float(sim.backend.solver_config.get("sim_wall_s", measured))


def run(adapter: PhysicsAdapter, ir: SceneIR) -> tuple[SimResult, float]:
    """Compile once, simulate REPEATS times; return the last result and the fastest wall time.

    Adapters with ``single_shot_timing`` (one process per run) are simulated once."""
    native = adapter.compile(ir)
    best = math.inf
    repeats = 1 if getattr(adapter, "single_shot_timing", False) else max(1, REPEATS)
    for _ in range(repeats):
        t0 = time.perf_counter()
        sim = adapter.simulate(native)
        best = min(best, sim_wall(sim, time.perf_counter() - t0))
    return sim, best


def _t(sim: SimResult) -> np.ndarray:
    return np.arange(sim.num_frames) / sim.fps


# --------------------------------------------------------------------------- cases


def free_fall(adapter: PhysicsAdapter) -> list[CaseResult]:
    """Sphere in free fall, no ground: z(t) = z0 - g t^2 / 2 and time to drop 1 m = sqrt(2/g)."""
    z0, dur = 10.0, 1.0
    ir = scene("free_fall", [_sphere("ball", (0, 0, z0))], dur)
    sim, wall = run(adapter, ir)
    t, z = _t(sim), sim.poses["ball"][:, 2]
    traj_err = float(np.max(np.abs(z - (z0 - 0.5 * G * t**2))))
    drop = z0 - z
    i = int(np.argmax(drop >= 1.0))
    t_cross = t[i - 1] + (1.0 - drop[i - 1]) / (drop[i] - drop[i - 1]) * (t[i] - t[i - 1])
    return [
        CaseResult("free_fall", "max position error over 1 s", "m", 0.0, traj_err, {"z0": z0}, wall),
        CaseResult("free_fall", "time to drop 1 m", "s", math.sqrt(2.0 / G), float(t_cross), {"z0": z0}, wall),
    ]


def bounce(adapter: PhysicsAdapter, restitutions=(0.0, 0.3, 0.6, 0.9)) -> list[CaseResult]:
    """Sphere dropped from h onto the ground: rebound height = e^2 h."""
    h, r = 1.0, 0.1
    out = []
    for e in restitutions:
        ir = scene(
            f"bounce_e{e}", [_ground(restitution=e), _sphere("ball", (0, 0, h + r), radius=r, restitution=e)], 1.4
        )
        sim, wall = run(adapter, ir)
        gap = sim.poses["ball"][:, 2] - r  # height of the sphere's bottom
        # First impact = first local minimum of the height. (Rigid-contact engines never reach
        # gap <= 0, so a penetration test would miss the impact.)
        rising = np.diff(gap) > 1e-9
        first = int(np.argmax(rising)) if rising.any() else len(gap) - 1
        rebound = float(max(gap[first:].max() - max(gap[first], 0.0), 0.0))
        out.append(CaseResult("bounce", f"rebound height (e={e})", "m", e * e * h, rebound, {"e": e, "h": h}, wall))
    return out


def slide(adapter: PhysicsAdapter, frictions=(0.2, 0.5)) -> list[CaseResult]:
    """Box launched along the ground at v0: stopping distance = v0^2 / (2 mu g)."""
    v0 = 2.0
    out = []
    for mu in frictions:
        ir = scene(
            f"slide_mu{mu}",
            [_ground(friction=mu), _box("box", (0, 0, 0.1), vel=(v0, 0, 0), friction=mu)],
            v0 / (mu * G) + 0.5,
        )
        sim, wall = run(adapter, ir)
        dist = float(sim.poses["box"][-1, 0] - sim.poses["box"][0, 0])
        out.append(
            CaseResult("slide", f"stopping distance (mu={mu})", "m", v0 * v0 / (2 * mu * G), dist, {"mu": mu, "v0": v0}, wall)
        )
    return out


def stack(adapter: PhysicsAdapter, n: int = 5) -> list[CaseResult]:
    """n boxes stacked at rest must stay put: drift and penetration should be 0."""
    edge = 0.2
    bodies = [_ground()] + [_box(f"b{i}", (0, 0, edge / 2 + i * edge), edge=edge) for i in range(n)]
    ir = scene(f"stack{n}", bodies, 3.0)
    sim, wall = run(adapter, ir)
    pos = np.stack([sim.poses[f"b{i}"][:, :3] for i in range(n)])  # (n, T, 3)
    drift = float(np.max(np.linalg.norm(pos[-1] - pos[-1, 0], axis=1)))
    z = pos[:, :, 2]
    overlap_ground = edge / 2 - z[0]
    overlap_pairs = edge - (z[1:] - z[:-1])
    penetration = float(max(overlap_ground.max(), overlap_pairs.max(), 0.0))
    p = {"n": n, "edge": edge}
    return [
        CaseResult("stack", f"top box drift over 3 s ({n} boxes)", "m", 0.0, drift, p, wall),
        CaseResult("stack", f"max penetration ({n} boxes)", "m", 0.0, penetration, p, wall),
    ]


def collision(adapter: PhysicsAdapter, restitutions=(1.0, 0.5)) -> list[CaseResult]:
    """Head-on collision of equal spheres in zero gravity, B at rest.

    Momentum is conserved; v_B' = (1 + e) / 2 * v.
    """
    v = 1.0
    out = []
    for e in restitutions:
        bodies = [
            _sphere("a", (-0.5, 0, 0), vel=(v, 0, 0), friction=0.0, restitution=e),
            _sphere("b", (0, 0, 0), friction=0.0, restitution=e),
        ]
        ir = scene(f"collision_e{e}", bodies, 1.0, gravity=(0.0, 0.0, 0.0))
        sim, wall = run(adapter, ir)
        va, vb = sim.velocities["a"][-1, 0], sim.velocities["b"][-1, 0]
        p = {"e": e, "v": v}
        out += [
            CaseResult("collision", f"momentum after (e={e})", "kg*m/s", v, float(va + vb), p, wall),
            CaseResult("collision", f"v_B after (e={e})", "m/s", (1 + e) / 2 * v, float(vb), p, wall),
        ]
    return out


def roll(adapter: PhysicsAdapter, v0: float = 2.0) -> list[CaseResult]:
    """Sphere rolling without slipping (v = omega r) on the ground keeps its speed.

    Rolling friction is not part of IR v0.1, so the expected speed after 1 s is v0. This case
    catches solvers that drain energy from rolling contact (see the 4DCodeBench Newton report).
    """
    r = 0.1
    ball = _sphere("ball", (0, 0, r), radius=r, vel=(v0, 0, 0))
    ball["initial_angular_velocity"] = [0.0, v0 / r, 0.0]
    ir = scene("roll", [_ground(), ball], 1.0)
    sim, wall = run(adapter, ir)
    speed = float(np.linalg.norm(sim.velocities["ball"][-1, :2]))
    return [CaseResult("roll", "rolling speed after 1 s", "m/s", v0, speed, {"v0": v0}, wall)]


CASES: dict[str, Callable[[PhysicsAdapter], list[CaseResult]]] = {
    "free_fall": free_fall,
    "bounce": bounce,
    "slide": slide,
    "stack": stack,
    "collision": collision,
    "roll": roll,
}


def run_suite(adapter: PhysicsAdapter, cases: list[str] | None = None) -> list[CaseResult]:
    out: list[CaseResult] = []
    for name in cases or list(CASES):
        out += CASES[name](adapter)
    return out
