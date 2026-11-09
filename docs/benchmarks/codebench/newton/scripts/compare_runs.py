"""Summaries across runs (labels = dirs under docs/benchmarks/codebench/), pose diffs between runs.

python compare_runs.py table                      -> results table for every newton* label
python compare_runs.py diff LABEL_A LABEL_B       -> per-variant max |pose diff| and per-body final-position divergence
"""
import json, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]

def table():
    for lab in sorted(p.name for p in ROOT.glob("newton*") if p.is_dir()):
        for c in ("B_01", "B_03"):
            f = ROOT / lab / f"{c}.json"
            if not f.exists():
                continue
            d = json.loads(f.read_text()); v = d["vs_original_bullet"]; ch = d["checks"]
            print(f"{lab:14s} {c} dev={d['device']:4s} moved={d['baseline']['moved']}/{d['baseline']['of']} "
                  f"down={len(d['baseline']['down'])} {d['baseline']['down'] if c=='B_03' else ''} | causal moved={d['causal']['moved']} "
                  f"maxpath={d['causal']['max_path_displacement']:.3f} down={d['causal']['down']} | static={ch['causal_is_static']} "
                  f"replay={ch['noncausal_replays_baseline']} diverge={ch['causal_diverges_from_baseline']} | "
                  f"agree={v['moved_agreement']}/{v['bodies']} final_err_mean={v['final_pos_err_mean']:.3f} "
                  f"ball_err_mean={v['ball_path_err_mean']:.3f} ball_err_12={v['ball_path_err_first_12_frames_max']:.3f} "
                  f"ball_final={v['ball_final_err']:.3f} | sim_s={d['timing']['baseline']['sim_s']:.2f} call_s={d['timing']['baseline']['call_s']:.2f}")

def diff(a, b):
    for c in ("B_01", "B_03"):
        A, B = np.load(ROOT / a / f"{c}_poses.npz"), np.load(ROOT / b / f"{c}_poses.npz")
        for var in ("baseline", "causal", "noncausal"):
            keys = [k for k in A.files if k.startswith(var + "/")]
            mx = max(float(np.abs(A[k].astype(float) - B[k].astype(float)).max()) for k in keys)
            ident = all(np.array_equal(A[k], B[k]) for k in keys)
            fin = {k.split("/")[1]: float(np.linalg.norm(A[k][-1, :3].astype(float) - B[k][-1, :3])) for k in keys}
            # first frame where any body differs by > 1 mm
            dd = np.max([np.linalg.norm(A[k][:, :3].astype(float) - B[k][:, :3], axis=1) for k in keys], axis=0)
            f1 = int(np.argmax(dd > 1e-3)) if (dd > 1e-3).any() else -1
            top = sorted(fin.items(), key=lambda kv: -kv[1])[:3]
            print(f"{c} {var:9s} bit-identical={ident} max|diff|={mx:.3g} first frame >1mm={f1} "
                  f"final-pos diff mean={np.mean(list(fin.values())):.3f} max={max(fin.values()):.3f} "
                  f"bodies>5cm={sum(x > 0.05 for x in fin.values())} top={[(k, round(x, 3)) for k, x in top]}")

if __name__ == "__main__":
    table() if sys.argv[1] == "table" else diff(sys.argv[2], sys.argv[3])
