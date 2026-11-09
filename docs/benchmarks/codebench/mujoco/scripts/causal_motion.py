"""Per-body motion in the causal member (ball removed) of a saved *_poses.npz.

Usage: python causal_motion.py <poses.npz> [variant]
Prints, per dynamic body that moves: max path displacement, final displacement,
final z change, final tilt (deg), and the first frame at which it exceeds 1 mm / 1 cm.
"""
import sys

import numpy as np


def tilt(q):
    w, x, y, z = q
    return np.degrees(np.arccos(np.clip(1 - 2 * (x * x + y * y), -1, 1)))


path = sys.argv[1]
variant = sys.argv[2] if len(sys.argv) > 2 else "causal"
d = np.load(path)
rows = []
for k in d.files:
    v, b = k.split("/", 1)
    if v != variant:
        continue
    p = d[k].astype(float)
    disp = np.linalg.norm(p[:, :3] - p[0, :3], axis=1)
    if disp.max() < 1e-4:
        continue
    f1 = int(np.argmax(disp > 1e-3)) if (disp > 1e-3).any() else -1
    f10 = int(np.argmax(disp > 1e-2)) if (disp > 1e-2).any() else -1
    rows.append((disp.max(), b, disp[-1], p[-1, 2] - p[0, 2], tilt(p[-1, 3:]),
                 max(tilt(q) for q in p[:, 3:]), f1, f10, p[-1, :3] - p[0, :3]))
rows.sort(reverse=True)
print(f"{'body':10s} {'maxpath':>8s} {'final':>8s} {'dz':>8s} {'tilt':>6s} {'maxtilt':>7s} {'f>1mm':>5s} {'f>1cm':>5s}  final dxyz")
for r in rows:
    print(f"{r[1]:10s} {r[0]:8.4f} {r[2]:8.4f} {r[3]:8.4f} {r[4]:6.1f} {r[5]:7.1f} {r[6]:5d} {r[7]:5d}  {np.round(r[8], 4)}")
print(f"{len(rows)} bodies move > 0.1 mm")
