"""Minimal reproduction of the B_03 default-config pin pop: collision_margin unset -> Blender's 0.04 m default.

Three bodies taken verbatim from examples/codebench/B_03.json: the lane top as a plane (z = 0), the
gutter slab gutter_R_0 (2.3 x 2 cm cross-section, entirely below z = 0 and not touching the pin), and
pin_D1 (cylinder r 0.0605, h 0.381) standing on the lane. A correct run leaves the pin at rest.
Swapping the pin for a box of the same footprint tells whether the cylinder shape is involved.
"""
import json

import numpy as np

from vw.ir import SceneIR
from vw.physics.bullet_blender import BulletBlenderAdapter

src = {b["id"]: b for b in json.load(open("C:/Users/kuock/source/repos/4DVisWorld-Infra/examples/codebench/B_03.json"))["bodies"]}
pin = src["pin_D1"]
box = {**pin, "id": "box_D1", "geometry": {"type": "box", "extents": [0.121, 0.121, 0.381]}}
for dyn in (pin, box):
    ir = SceneIR.model_validate({
        "level": "physical", "timing": {"fps": 24, "frames": 4}, "gravity": [0, 0, -9.81],
        "cameras": [{"id": "cam", "pose": {"position": [0, -3, 1]}, "fov_deg": 40, "resolution": [64, 64]}],
        "bodies": [{"id": "lane", "kind": "static", "geometry": {"type": "plane", "extents": [4, 4]},
                    "initial_pose": {"position": [0, 0, 0]}}, src["gutter_R_0"], dyn]})
    for cfg in ({}, {"collision_margin": 0.002}):
        ad = BulletBlenderAdapter(device="cpu", **cfg)
        p = ad.simulate(ad.compile(ir)).poses[dyn["id"]]
        print(f"{dyn['id']:7s} config={str(cfg):28s} displacement per frame (mm):",
              np.round(np.linalg.norm(p[:, :3] - p[0, :3], axis=1) * 1000, 2))
