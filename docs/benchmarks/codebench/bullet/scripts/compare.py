"""Baseline vs the original 4DCodeBench Bullet run, for every saved bullet* result.

Prints moved / down counts (ours and original), the ball-path error over time (first frame it exceeds
1 / 5 / 20 cm), and the per-body final-position error. Original positions are vertex centroids
(world/dynamics/<id>.npz); for B_03 pins the centroid sits 6.1 mm above the cylinder centre at rest.
"""
import json
import sys
from pathlib import Path

import numpy as np

from vw.benchmark.codebench import _orig_tilted, _tilt_deg

ROOT = Path("C:/Users/kuock/source/repos/4DVisWorld-Infra/docs/benchmarks/codebench")
ORIG = Path("C:/Users/kuock/source/repos/4DCodeBench/outputs/2026-11-05/opus-5.5")


def first(err, thr):
    i = np.argmax(err > thr)
    return int(i) if err[i] > thr else None


def analyse(label, case):
    f = ROOT / label / f"{case}_poses.npz"
    if not f.exists():
        return None
    d = np.load(f)
    res = json.loads((ROOT / label / f"{case}.json").read_text())
    ids = sorted(k.split("/", 1)[1] for k in d.files if k.startswith("baseline/"))
    dyn = [i for i in ids if (ORIG / case / "sim/baseline/world/dynamics" / f"{i}.npz").exists()]
    orig = {i: np.load(ORIG / case / "sim/baseline/world/dynamics" / f"{i}.npz")["pos"].astype(float).mean(1) for i in dyn}
    ours = {i: d[f"baseline/{i}"].astype(float) for i in dyn}
    others = [i for i in dyn if i != "ball"]
    mv = lambda p: np.linalg.norm(p[-1, :3] - p[0, :3]) > 0.01
    pins = [i for i in others if i.startswith("pin_")]
    out = {
        "label": label, "case": case,
        "moved": sum(mv(ours[i]) for i in others), "moved_orig": sum(mv(orig[i]) for i in others), "of": len(others),
        "moved_both": sum(mv(ours[i]) and mv(orig[i]) for i in others),
        "down": [i for i in pins if _tilt_deg(ours[i][-1, 3:]) > 45],
        "down_orig": [i for i in pins if _orig_tilted(ORIG / case, i)],
        "causal_static": res["checks"]["causal_is_static"], "causal_max": res["causal"]["max_path_displacement"],
        "noncausal_diff": res["checks"]["noncausal_max_diff"],
        "sim_s": res["timing"]["baseline"]["sim_s"], "call_s": res["timing"]["baseline"]["call_s"],
    }
    e = np.linalg.norm(ours["ball"][:, :3] - orig["ball"], axis=1)
    out.update(ball_mean=float(e.mean()), ball_final=float(e[-1]), ball_max=float(e.max()),
               ball_1cm=first(e, 0.01), ball_5cm=first(e, 0.05), ball_20cm=first(e, 0.2))
    fin = np.array([np.linalg.norm(ours[i][-1, :3] - orig[i][-1]) for i in others])
    out.update(body_final_median=float(np.median(fin)), body_final_mean=float(fin.mean()), body_final_max=float(fin.max()))
    # earliest frame any non-ball body deviates > 2 cm from the original
    dev = np.array([np.linalg.norm(ours[i][:, :3] - orig[i], axis=1) for i in others])
    if case == "B_03":
        dev = np.abs(dev - 0.0061)  # centroid offset at rest
    out["first_body_2cm"] = first(dev.max(0), 0.02)
    return out


def main():
    labels = sys.argv[1:] or sorted(p.name for p in ROOT.iterdir() if p.is_dir() and p.name.startswith("bullet"))
    rows = [r for l in labels for c in ("B_01", "B_03") if (r := analyse(l, c))]
    for r in rows:
        print(json.dumps(r, default=int))
    (ROOT / "bullet" / "compare.json").write_text(json.dumps(rows, indent=1, default=int))


if __name__ == "__main__":
    main()
