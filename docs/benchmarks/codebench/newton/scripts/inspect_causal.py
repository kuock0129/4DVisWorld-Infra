"""Print per-body motion in a variant of a saved *_poses.npz: when each body first moves > 1 mm / 1 cm, final displacement, tilt."""
import sys
import numpy as np

path, variant = sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "causal"
d = np.load(path)
def tilt(q):
    w, x, y, z = q
    r22 = 1 - 2 * (x * x + y * y)
    return np.degrees(np.arccos(np.clip(r22, -1, 1)))
rows = []
for k in d.files:
    v, b = k.split("/", 1)
    if v != variant:
        continue
    p = d[k].astype(float)
    disp = np.linalg.norm(p[:, :3] - p[0, :3], axis=1)
    f1 = int(np.argmax(disp > 1e-3)) if (disp > 1e-3).any() else -1
    f10 = int(np.argmax(disp > 1e-2)) if (disp > 1e-2).any() else -1
    rows.append((disp[-1], b, f1, f10, p[0, :3], p[-1, :3], tilt(p[-1, 3:]), p[:, 2].min() - p[0, 2]))
for r in sorted(rows, reverse=True):
    if r[0] > 1e-3:
        print(f"{r[1]:10s} final_disp={r[0]:.4f} first>1mm=f{r[2]} first>1cm=f{r[3]} start={np.round(r[4],3)} end={np.round(r[5],3)} tilt={r[6]:.1f} min_dz={r[7]:.4f}")
print("bodies moving >1mm:", sum(r[0] > 1e-3 for r in rows), "of", len(rows))
