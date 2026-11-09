"""Ball path (every N frames) of saved runs vs the original vertex-centroid track.

Usage: python ball_path.py <case> <original_case_dir> <label> [<label> ...]
"""
import sys
from pathlib import Path

import numpy as np

case, odir, labels = sys.argv[1], Path(sys.argv[2]), sys.argv[3:]
root = Path(__file__).resolve().parents[2]
orig = np.load(odir / "sim" / "baseline" / "world" / "dynamics" / "ball.npz")["pos"].astype(float).mean(1)
runs = {l: np.load(root / l / f"{case}_poses.npz")["baseline/ball"].astype(float) for l in labels}
step = max(1, len(orig) // 14)
print("frame | original xyz | " + " | ".join(f"{l} xyz (err)" for l in labels))
for k in list(range(0, len(orig), step)) + [len(orig) - 1]:
    cells = [f"{np.round(orig[k], 3)}"]
    for l, p in runs.items():
        cells.append(f"{np.round(p[k, :3], 3)} ({np.linalg.norm(p[k, :3] - orig[k]):.3f})")
    print(f"{k:4d} | " + " | ".join(cells))
