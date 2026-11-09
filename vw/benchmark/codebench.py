"""Run a 4DCodeBench case (Scene IR from examples/codebench) as a full counterfactual tuple.

For one physics adapter: baseline, causal (target removed, re-simulated) and non-causal
(target removed, every other body replays the baseline). Reports the checks a tuple must
pass and compares the baseline with the original Blender/Bullet run of the same case.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import numpy as np

from vw.interventions import remove
from vw.ir import BodyKind, SceneIR
from vw.physics.base import PhysicsAdapter, SimResult
from vw.physics.util import quat_to_mat

MOVED = 0.01  # m: a body "moved" if it ends this far from its start
DOWN_DEG = 45.0  # deg: a pin is "down" if its axis tilts more than this


def _dynamic_ids(ir: SceneIR, exclude: str | None = None) -> list[str]:
    return [b.id for b in ir.bodies if b.kind is BodyKind.DYNAMIC and b.id != exclude]


def _tilt_deg(q: np.ndarray) -> float:
    return float(np.degrees(np.arccos(np.clip(quat_to_mat(q)[2, 2], -1.0, 1.0))))


def summarize(sim: SimResult, ids: list[str], upright: list[str] = ()) -> dict[str, Any]:
    """``upright``: bodies (pins) for which "down" = axis tilted more than DOWN_DEG is meaningful."""
    disp = {i: float(np.linalg.norm(sim.poses[i][-1, :3] - sim.poses[i][0, :3])) for i in ids}
    path = {i: float(np.linalg.norm(sim.poses[i][:, :3] - sim.poses[i][0, :3], axis=1).max()) for i in ids}
    return {
        "moved": sum(d > MOVED for d in disp.values()),
        "of": len(ids),
        "max_final_displacement": max(disp.values(), default=0.0),
        "max_path_displacement": max(path.values(), default=0.0),
        "down": sorted(i for i in upright if _tilt_deg(sim.poses[i][-1, 3:]) > DOWN_DEG),
        "contacts": len(sim.contacts),
    }


def load_original(case_dir: Path, ids: list[str]) -> dict[str, np.ndarray]:
    """Per-frame vertex centroids of the original run's moving bodies (world/dynamics/*.npz)."""
    out = {}
    for i in ids:
        f = case_dir / "world" / "dynamics" / f"{i}.npz"
        if f.exists():
            out[i] = np.load(f)["pos"].astype(float).mean(axis=1)
    return out


def compare_original(sim: SimResult, orig: dict[str, np.ndarray], ids: list[str]) -> dict[str, Any]:
    common = [i for i in ids if i in orig and orig[i].shape[0] == sim.num_frames]
    if not common:
        return {"available": False}
    final = {i: float(np.linalg.norm(sim.poses[i][-1, :3] - orig[i][-1])) for i in common}
    moved_here = {i: np.linalg.norm(sim.poses[i][-1, :3] - sim.poses[i][0, :3]) > MOVED for i in common}
    moved_orig = {i: np.linalg.norm(orig[i][-1] - orig[i][0]) > MOVED for i in common}
    out = {
        "available": True,
        "bodies": len(common),
        "final_pos_err_mean": float(np.mean(list(final.values()))),
        "final_pos_err_median": float(np.median(list(final.values()))),
        "final_pos_err_max": max(final.values()),
        "moved_agreement": int(sum(moved_here[i] == moved_orig[i] for i in common)),
        "original_moved": int(sum(moved_orig.values())),
    }
    if "ball" in orig and "ball" in sim.poses and orig["ball"].shape[0] == sim.num_frames:
        err = np.linalg.norm(sim.poses["ball"][:, :3] - orig["ball"], axis=1)
        out["ball_path_err_mean"] = float(err.mean())
        out["ball_path_err_first_12_frames_max"] = float(err[:12].max())
        out["ball_final_err"] = float(err[-1])
    return out


def run_tuple(adapter: PhysicsAdapter, ir: SceneIR, original_case_dir: Path | None = None,
              target: str | None = None) -> tuple[dict[str, Any], dict[str, SimResult]]:
    target = target or ir.metadata.get("target", "ball")
    others = _dynamic_ids(ir, exclude=target)
    upright = [b.id for b in ir.bodies if b.id in others and b.geometry.type in ("cylinder", "capsule")]
    cf = remove(ir, [target])
    sims: dict[str, SimResult] = {}
    walls: dict[str, dict[str, float]] = {}

    def timed(name, native, **kw):
        t0 = time.perf_counter()
        sims[name] = adapter.simulate(native, **kw)
        wall = time.perf_counter() - t0
        walls[name] = {"call_s": wall, "sim_s": float(sims[name].backend.solver_config.get("sim_wall_s", wall))}

    timed("baseline", adapter.compile(ir))
    timed("causal", adapter.compile(cf))
    timed("noncausal", adapter.compile(cf), kinematic={i: sims["baseline"].poses[i] for i in others})

    base, causal, non = sims["baseline"], sims["causal"], sims["noncausal"]
    non_diff = max(float(np.abs(non.poses[i] - base.poses[i]).max()) for i in others)
    causal_vs_base = {i: float(np.linalg.norm(causal.poses[i][-1, :3] - base.poses[i][-1, :3])) for i in others}
    result: dict[str, Any] = {
        "case": ir.metadata.get("name"),
        "backend": base.backend.name,
        "version": base.backend.version,
        "device": base.backend.device.value,
        "solver_config": {k: v for k, v in base.backend.solver_config.items() if k not in ("sim_wall_s", "process_wall_s")},
        "frames": ir.timing.frames,
        "fps": ir.timing.fps,
        "target": target,
        "timing": walls,
        "baseline": summarize(base, others, upright),
        "causal": summarize(causal, others, upright),
        "noncausal": summarize(non, others, upright),
        "checks": {
            "causal_is_static": summarize(causal, others)["max_path_displacement"] < MOVED,
            "noncausal_replays_baseline": non_diff < 1e-9,
            "noncausal_max_diff": non_diff,
            "causal_diverges_from_baseline": sum(d > 0.05 for d in causal_vs_base.values()),
        },
    }
    if original_case_dir is not None:
        orig = load_original(Path(original_case_dir) / "sim" / "baseline", others + [target])
        result["vs_original_bullet"] = compare_original(base, orig, others + [target])
        if result["vs_original_bullet"].get("available"):
            orig_down = sorted(i for i in upright if i in orig and _orig_tilted(Path(original_case_dir), i))
            result["vs_original_bullet"]["original_down"] = orig_down
    return result, sims


def _orig_tilted(case_dir: Path, oid: str) -> bool:
    """Pin tilt in the original run from its vertex cloud's principal axis at the last frame."""
    pos = np.load(case_dir / "sim" / "baseline" / "world" / "dynamics" / f"{oid}.npz")["pos"].astype(float)
    v = pos[-1] - pos[-1].mean(0)
    axis = np.linalg.svd(v, full_matrices=False)[2][0]
    return float(np.degrees(np.arccos(min(1.0, abs(axis[2]))))) > DOWN_DEG


def _jsonable(o):
    if isinstance(o, np.generic):
        return o.item()
    raise TypeError(f"not JSON serializable: {type(o).__name__}")


def save(result: dict[str, Any], sims: dict[str, SimResult], out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    case = result["case"]
    j = out_dir / f"{case}.json"
    j.write_text(json.dumps(result, indent=2, default=_jsonable), encoding="utf-8")
    npz = out_dir / f"{case}_poses.npz"
    np.savez_compressed(npz, **{f"{v}/{b}": s.poses[b].astype(np.float32) for v, s in sims.items() for b in s.poses})
    return [j, npz]
