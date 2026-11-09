"""B_01 tower: for each box whose AABB is exact (orientations are multiples of 90 deg), the vertical gap (+) or
overlap (-) to the highest body below it that overlaps it in x-y, and any 3D AABB interpenetration between boxes."""
import json
import numpy as np

def R(q):
    w, x, y, z = q
    return np.array([[1-2*(y*y+z*z), 2*(x*y-w*z), 2*(x*z+w*y)], [2*(x*y+w*z), 1-2*(x*x+z*z), 2*(y*z-w*x)], [2*(x*z-w*y), 2*(y*z+w*x), 1-2*(x*x+y*y)]])
d = json.load(open("examples/codebench/B_01.json"))
bx = {}
for b in d["bodies"]:
    if b["geometry"]["type"] != "box" or b["kind"] != "dynamic" or not b["id"].startswith(("up", "cap")):
        continue
    Rm = R(b["initial_pose"]["orientation"])
    if not np.allclose(np.abs(Rm), np.round(np.abs(Rm)), atol=1e-6):
        continue
    e = np.abs(Rm) @ (np.array(b["geometry"]["extents"]) / 2); p = np.array(b["initial_pose"]["position"])
    bx[b["id"]] = (p - e, p + e)
pens, gaps = [], []
for a, (lo, hi) in bx.items():
    below = []
    for c, (lo2, hi2) in bx.items():
        if c == a: continue
        ov = np.minimum(hi, hi2) - np.maximum(lo, lo2)
        if (ov > 1e-5).all():
            pens.append((ov.min(), a, c))
        if ov[0] > 1e-5 and ov[1] > 1e-5 and hi2[2] <= hi[2] and lo2[2] < lo[2]:
            below.append((hi2[2], c))
    if lo[2] < 1e-4:
        gaps.append((lo[2], a, "floor"))
    elif below:
        z, c = max(below); gaps.append((lo[2] - z, a, c))
print("bodies:", len(bx))
print("support gaps (m), sorted:")
for g, a, c in sorted(gaps):
    print(f"  {a:6s} on {c:6s}: {g*1000:+.2f} mm")
print("3D interpenetrations (min overlap axis, mm):", [(a, c, round(o*1000, 2)) for o, a, c in sorted(pens, reverse=True)][::2])
