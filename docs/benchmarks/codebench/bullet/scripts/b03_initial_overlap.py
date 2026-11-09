"""B_03: which static boxes does each pin cylinder overlap at t=0? Samples the cylinder volume and
reports the deepest point inside each static box (pure geometry, independent of any engine)."""
import json
import numpy as np

import sys
ir = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "C:/Users/kuock/source/repos/4DVisWorld-Infra/examples/codebench/B_03.json"))


def R(q):
    w, x, y, z = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
                     [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
                     [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]])


boxes = [b for b in ir["bodies"] if b["kind"] == "static" and b["geometry"]["type"] == "box"]
rng = np.random.default_rng(0)
for pin in [b for b in ir["bodies"] if b["id"].startswith("pin")]:
    r, h = pin["geometry"]["radius"], pin["geometry"]["height"]
    n = 40000
    rr = r * np.sqrt(rng.random(n)); th = 2 * np.pi * rng.random(n); zz = (rng.random(n) - 0.5) * h
    pts = np.stack([rr * np.cos(th), rr * np.sin(th), zz], 1) @ R(pin["initial_pose"]["orientation"]).T
    pts += pin["initial_pose"]["position"]
    hits = []
    for b in boxes:
        loc = (pts - b["initial_pose"]["position"]) @ R(b["initial_pose"]["orientation"])
        half = np.array(b["geometry"]["extents"]) / 2
        inside = np.all(np.abs(loc) < half, axis=1)
        if inside.any():
            depth = (half - np.abs(loc[inside])).min(axis=1).max()
            hits.append(f"{b['id']} ({inside.mean()*100:.2f}% of volume, depth {depth*1000:.1f} mm)")
    print(f"{pin['id']:7s} pos={np.round(pin['initial_pose']['position'],3)}  overlaps: {', '.join(hits) or '-'}")
