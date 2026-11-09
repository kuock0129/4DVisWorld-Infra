"""Convert 4DCodeBench B_01 / B_03 (Opus 5.5 run of 2026-11-05) into Scene IR.

Usage:  python examples/codebench/convert.py <4DCodeBench>/outputs/2026-11-05/opus-5.5

Reads each case's ``sim/baseline/world`` export (frame-0 world-space meshes, camera.json)
and the Bullet settings recorded by that run, and writes ``examples/codebench/<case>.json``.
Every adapter then runs the SAME IR, so differences come from the engines alone.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parent

APPROXIMATIONS = [
    "Box meshes (8 vertices, or several disjoint 8-vertex boxes) become IR boxes. The non-box static "
    "meshes Bullet used are kept part by part: the B_01 storage box is 5 boxes; each B_03 gutter (a "
    "half-pipe profile extruded along the lane) becomes one 2 cm slab per profile segment, top face on the surface.",
    "B_01 floor becomes an infinite plane at its top face.",
    "B_03 pins (lathe meshes, convex hulls in Bullet) become cylinders r = 0.0605 m, h = 0.381 m, "
    "so their centre of mass sits higher (0.19 m vs about 0.14 m) and their base is wider.",
    "Materials: 4DCodeBench set Blender values, which Bullet multiplies per pair. The IR stores "
    "value**2, so bullet_blender (IR -> sqrt) reproduces the original pairs exactly; other engines "
    "combine pairs by their own rule (MuJoCo max, PhysX average, Newton XPBD average).",
    "Damping is 0 (the original used small plank / pin damping; Newton has no per-body damping).",
    "The ball is dynamic from frame 0 with the velocity of its scripted release track and rolling "
    "spin, instead of being animated for the first frames.",
    "Window, window pane and baseboards were excluded from the original Bullet world; same here.",
]


def mat_to_quat(R: np.ndarray) -> list[float]:
    w = math.sqrt(max(0.0, 1 + R[0, 0] + R[1, 1] + R[2, 2])) / 2
    x = math.copysign(math.sqrt(max(0.0, 1 + R[0, 0] - R[1, 1] - R[2, 2])) / 2, R[2, 1] - R[1, 2])
    y = math.copysign(math.sqrt(max(0.0, 1 - R[0, 0] + R[1, 1] - R[2, 2])) / 2, R[0, 2] - R[2, 0])
    z = math.copysign(math.sqrt(max(0.0, 1 - R[0, 0] - R[1, 1] + R[2, 2])) / 2, R[1, 0] - R[0, 1])
    q = np.array([w, x, y, z])
    return (q / np.linalg.norm(q)).round(9).tolist()


def obb(v: np.ndarray) -> tuple[list[float], list[float], list[float]]:
    """Centre, quaternion (wxyz) and full extents of the 8 vertices of a box."""
    c = v.mean(0)
    d = v - v[0]
    order = np.argsort(np.linalg.norm(d, axis=1))[1:4]  # the three edges from vertex 0
    axes = np.array([d[i] / np.linalg.norm(d[i]) for i in order])
    a0 = axes[0]
    a1 = axes[1] - a0 * (a0 @ axes[1])
    a1 /= np.linalg.norm(a1)
    R = np.column_stack([a0, a1, np.cross(a0, a1)])  # right-handed
    ext = np.array([np.ptp(v @ R[:, i]) for i in range(3)])
    return c.round(6).tolist(), mat_to_quat(R), ext.round(6).tolist()


def boxes(v: np.ndarray) -> list[tuple]:
    if len(v) % 8:
        raise ValueError(f"not a set of boxes: {len(v)} vertices")
    return [obb(v[i : i + 8]) for i in range(0, len(v), 8)]


def trough(v: np.ndarray, thickness: float = 0.02) -> list[tuple]:
    """B_03 gutter: a 20-point cross-section profile extruded along x (vertices = both end caps).

    Each profile segment that faces the air (rail top + the half-pipe) becomes a thin slab whose
    top face lies on the surface. Air side = towards a point above the channel's lowest point.
    """
    n = len(v) // 2
    prof = v[:n, 1:]  # (y, z) at the first end cap
    x0, x1 = float(v[:, 0].min()), float(v[:, 0].max())
    low = prof[np.argmin(prof[:, 1])]
    air = np.array([low[0], prof[:, 1].max() + 0.2])
    out = []
    zmax = prof[:, 1].max()
    for a, b in zip(prof[:-1], prof[1:]):
        seg = b - a
        L = float(np.linalg.norm(seg))
        mid = (a + b) / 2
        # Skip the block's outer side, bottom and inner (lane-side) wall: only surfaces at the top.
        if L < 1e-6 or (abs(seg[0]) < 1e-6 and mid[1] < zmax - 1e-6) or mid[1] < low[1] - 1e-6:
            continue
        t = seg / L
        nrm = np.array([-t[1], t[0]])
        if nrm @ (air - mid) < 0:
            nrm = -nrm
        c = mid - nrm * thickness / 2
        # Local axes: x along the gutter, y along the segment, z = air-side normal.
        R = np.array([[1.0, 0.0, 0.0], [0.0, t[0], nrm[0]], [0.0, t[1], nrm[1]]])
        if np.linalg.det(R) < 0:
            R[:, 1] *= -1
        out.append(([round((x0 + x1) / 2, 6), round(float(c[0]), 6), round(float(c[1]), 6)], mat_to_quat(R),
                    [round(x1 - x0, 6), round(L, 6), thickness]))
    return out


def camera(world: Path) -> dict:
    cam = json.loads((world / "camera.json").read_text())
    K, E = np.array(cam["intrinsics"]), np.array(cam["extrinsic"])  # E: camera-to-world, OpenCV axes
    R = E[:3, :3] @ np.diag([1.0, -1.0, -1.0])  # OpenCV (+z forward, +y down) -> IR (-z forward, +y up)
    W, H = int(round(2 * K[0, 2])), int(round(2 * K[1, 2]))
    return {"id": "cam", "pose": {"position": E[:3, 3].round(6).tolist(), "orientation": mat_to_quat(R)},
            "fov_deg": round(math.degrees(2 * math.atan(H / 2 / K[1, 1])), 4), "resolution": [W, H]}


def mesh0(world: Path, oid) -> np.ndarray:
    return np.load(world / "meshes" / f"{oid}.npz")["vertices_0000"].astype(float)


def mat(friction: float, restitution: float) -> dict:
    return {"friction": round(friction**2, 6), "restitution": round(restitution**2, 6)}


def static_box(bid, c, q, e, m) -> dict:
    return {"id": bid, "kind": "static", "geometry": {"type": "box", "extents": e},
            "initial_pose": {"position": c, "orientation": q}, "material": m}


def rolling_ball(world: Path, frames: slice, fps: int, mass: float, m: dict) -> dict:
    pos = np.load(world / "dynamics" / "ball.npz")["pos"].astype(float)  # (T, V, 3)
    ctr = pos.mean(axis=1)
    r = float(np.linalg.norm(pos[0] - ctr[0], axis=1).max())
    seg = ctr[frames]
    vel = (seg[-1] - seg[0]) / ((len(seg) - 1) / fps)
    vel[2] = 0.0
    omega = np.cross([0.0, 0.0, 1.0], vel) / r  # rolling without slipping on a z-up floor
    return {"id": "ball", "kind": "dynamic", "mass": mass, "geometry": {"type": "sphere", "radius": round(r, 6)},
            "initial_pose": {"position": ctr[0].round(6).tolist()}, "material": m,
            "initial_linear_velocity": vel.round(6).tolist(), "initial_angular_velocity": omega.round(6).tolist()}


def b01(root: Path) -> dict:
    case = root / "B_01" / "sim" / "baseline"
    world = case / "world"
    meta = json.loads((case / "build_meta.json").read_text())
    sim, objs = meta["sim"], meta["objects"]
    plank_m, floor_m = mat(sim["plank_friction"], sim["plank_restitution"]), mat(sim["floor_friction"], 0.1)
    bodies = []
    for oid, o in objs.items():
        name, kind = o["name"], o["kind"]
        if name in ("window_pane", "window_frame", "baseboards"):
            continue
        if kind == "ball":
            bodies.append(rolling_ball(world, slice(0, 3), 24, sim["ball_mass"],
                                       mat(sim["ball_friction"], sim["ball_restitution"])))
            continue
        v = mesh0(world, oid)
        if kind == "static":
            if name == "floor":
                c = v.mean(0)
                bodies.append({"id": "floor", "kind": "static", "geometry": {"type": "plane", "extents": [8.0, 7.0]},
                               "initial_pose": {"position": [round(c[0], 6), round(c[1], 6), float(v[:, 2].max())]},
                               "material": floor_m})
                continue
            for i, (c, q, e) in enumerate(boxes(v)):
                bodies.append(static_box(name if len(v) == 8 else f"{name}_{i}", c, q, e, floor_m))
        else:  # plank
            c, q, e = obb(v)
            bodies.append({"id": name, "kind": "dynamic", "mass": round(sim["wood_density"] * float(np.prod(e)), 6),
                           "geometry": {"type": "box", "extents": e}, "initial_pose": {"position": c, "orientation": q},
                           "material": plank_m})
    return finish("B_01", bodies, 105, world, "ball topples a 42-plank tower (+5 loose planks)", sim)


def b03(root: Path) -> dict:
    case = root / "B_03" / "sim" / "baseline"
    world = case / "world"
    ids = json.loads((case / "build_log.json").read_text())["ids"]
    S = dict(pin_friction=0.45, pin_restitution=0.55, ball_friction=0.35, ball_restitution=0.4, lane_friction=0.5,
             lane_restitution=0.5, floor_friction=0.7, floor_restitution=0.3, wall_restitution=0.3)  # scene.py SIM
    bodies = []
    for name, oid in ids.items():
        if name == "ball":
            bodies.append(rolling_ball(world, slice(8, 13), 24, 6.5, mat(S["ball_friction"], S["ball_restitution"])))
            continue
        v = mesh0(world, oid)
        if name.startswith("pin_"):
            base = v.mean(0)
            z0 = float(v[:, 2].min())
            bodies.append({"id": name, "kind": "dynamic", "mass": 1.5,
                           "geometry": {"type": "cylinder", "radius": 0.0605, "height": 0.381},
                           "initial_pose": {"position": [round(base[0], 6), round(base[1], 6), round(z0 + 0.1905, 6)]},
                           "material": mat(S["pin_friction"], S["pin_restitution"])})
            continue
        if name == "floor":
            m = mat(S["floor_friction"], S["floor_restitution"])
        elif name in ("wall", "curb_L", "curb_R"):
            m = mat(S["floor_friction"], S["wall_restitution"])
        else:
            m = mat(S["lane_friction"], S["lane_restitution"])
        parts = trough(v) if name.startswith("gutter") else boxes(v)
        for i, (c, q, e) in enumerate(parts):
            bodies.append(static_box(name if len(parts) == 1 else f"{name}_{i}", c, q, e, m))
    return finish("B_03", bodies, 130, world, "bowling ball strikes a 10-pin rack", S)


def finish(case, bodies, frames, world, desc, sim) -> dict:
    return {
        "ir_version": "0.1", "level": "physical", "gravity": [0.0, 0.0, -9.81],
        "timing": {"fps": 24, "frames": frames},
        "metadata": {"name": case, "description": desc, "target": "ball",
                     "source": "4DCodeBench outputs/2026-11-05/opus-5.5, sim/baseline",
                     "original_bullet_settings": sim, "approximations": APPROXIMATIONS},
        "bodies": bodies, "cameras": [camera(world)],
    }


def main() -> None:
    root = Path(sys.argv[1])
    sys.path.insert(0, str(OUT.parents[1]))
    from vw.ir import SceneIR

    for case, fn in (("B_01", b01), ("B_03", b03)):
        ir = SceneIR.model_validate(fn(root))
        ir.save(OUT / f"{case}.json")
        n_dyn = sum(b.kind.value == "dynamic" for b in ir.bodies)
        print(f"{case}: {len(ir.bodies)} bodies ({n_dyn} dynamic), {ir.timing.frames} frames @ {ir.timing.fps} fps")


if __name__ == "__main__":
    main()
