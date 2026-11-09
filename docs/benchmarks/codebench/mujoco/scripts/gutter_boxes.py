"""World AABB of each B_03 gutter box in the Scene IR vs the original gutter mesh extent.

The original gutter meshes (4DCodeBench world/meshes/3.npz, 4.npz) are a 20-vertex trough
profile extruded from x=-9 to x=0.87, entirely at |y| >= 0.527 (the lane edge).
Usage: python gutter_boxes.py examples/codebench/B_03.json
"""
import itertools
import json
import sys

import numpy as np

from vw.physics.util import quat_to_mat

d = json.load(open(sys.argv[1]))
for b in d["bodies"]:
    if not b["id"].startswith("gutter"):
        continue
    e = np.array(b["geometry"]["extents"]) / 2
    R = quat_to_mat(np.array(b["initial_pose"]["orientation"]))
    c = np.array(b["initial_pose"]["position"])
    pts = np.array([c + R @ (e * s) for s in itertools.product([-1, 1], repeat=3)])
    lo, hi = pts.min(0), pts.max(0)
    inner = hi[1] if c[1] < 0 else lo[1]
    print(f"{b['id']:11s} x[{lo[0]:7.3f},{hi[0]:7.3f}] y[{lo[1]:7.3f},{hi[1]:7.3f}] z[{lo[2]:7.3f},{hi[2]:7.3f}]"
          f"  inner |y| edge = {abs(inner):.3f} (lane edge 0.527)")
