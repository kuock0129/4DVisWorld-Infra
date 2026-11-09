"""B_03 causal scene (ball removed): which config setting makes pin_D1 jump at frame 1? Prints D1's frame-1
displacement for one-at-a-time changes from the default config. Optionally drop static bodies by prefix."""
import sys

import numpy as np

from vw.interventions import remove
from vw.ir import SceneIR
from vw.physics.bullet_blender import BulletBlenderAdapter

ir = remove(SceneIR.load("C:/Users/kuock/source/repos/4DVisWorld-Infra/examples/codebench/B_03.json"), ["ball"])
ir = ir.model_copy(update={"timing": ir.timing.model_copy(update={"frames": 3})})
CFGS = [{}, {"collision_margin": 0.002}] if len(sys.argv) > 1 else [{}, {"collision_margin": 0.002}, {"collision_margin": 0.0}, {"collision_margin": 0.04},
        {"split_impulse": True}, {"solver_iterations": 80}, {"timestep": 0.000695}]
drop = sys.argv[1:]  # e.g. gutter_R
if drop:
    ir = remove(ir, [b.id for b in ir.bodies if any(b.id.startswith(p) for p in drop)])
for cfg in CFGS:
    ad = BulletBlenderAdapter(device="cpu", **cfg)
    r = ad.simulate(ad.compile(ir))
    moved = {i: float(np.linalg.norm(r.poses[i][1, :3] - r.poses[i][0, :3])) for i in r.poses if i.startswith("pin")}
    worst = max(moved, key=moved.get)
    print(f"{str(cfg):40s} D1 d(f1) = {moved['pin_D1']*1000:7.2f} mm   worst pin {worst} {moved[worst]*1000:.2f} mm")
