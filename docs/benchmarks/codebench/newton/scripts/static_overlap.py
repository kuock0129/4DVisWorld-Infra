"""World AABBs of B_03 static boxes and their overlap with each pin's initial AABB (cylinder treated as its AABB)."""
import json, sys
import numpy as np

def R(q):
    w, x, y, z = q
    return np.array([[1-2*(y*y+z*z), 2*(x*y-w*z), 2*(x*z+w*y)],
                     [2*(x*y+w*z), 1-2*(x*x+z*z), 2*(y*z-w*x)],
                     [2*(x*z-w*y), 2*(y*z+w*x), 1-2*(x*x+y*y)]])
d = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "examples/codebench/B_03.json"))
boxes = {}
for b in d["bodies"]:
    g = b["geometry"]
    if g["type"] != "box":
        continue
    h = np.array(g["extents"]) / 2
    Rm = R(b["initial_pose"]["orientation"]); p = np.array(b["initial_pose"]["position"])
    ext = np.abs(Rm) @ h
    boxes[b["id"]] = (b["kind"], p - ext, p + ext, Rm, p, h)
    if b["kind"] == "static":
        print(f"{b['id']:12s} aabb min={np.round(p-ext,3)} max={np.round(p+ext,3)}")
print()
for b in d["bodies"]:
    if b["geometry"]["type"] != "cylinder":
        continue
    g = b["geometry"]; p = np.array(b["initial_pose"]["position"])
    lo = p - [g["radius"], g["radius"], g["height"] / 2]; hi = p + [g["radius"], g["radius"], g["height"] / 2]
    for k, (kind, blo, bhi, Rm, bp, h) in boxes.items():
        ov = np.minimum(hi, bhi) - np.maximum(lo, blo)
        if (ov > 1e-6).all():
            # exact-ish test: sample cylinder points, express in box frame
            th = np.linspace(0, 2*np.pi, 64); zz = np.linspace(-g["height"]/2, g["height"]/2, 21); rr = np.linspace(0, g["radius"], 6)
            pts = np.array([[r*np.cos(t), r*np.sin(t), z] for r in rr for t in th for z in zz]) + p
            loc = (pts - bp) @ Rm
            inside = (np.abs(loc) <= h).all(axis=1)
            depth = (h - np.abs(loc[inside])).min(axis=1).max() if inside.any() else 0
            print(f"{b['id']} AABB-overlaps {k}: overlap={np.round(ov,4)}; sampled points inside box: {inside.sum()}, max depth {depth:.4f} m")
