"""List MuJoCo contacts (and penetration depth) at t=0 for a case with the ball removed.

Usage: python initial_contacts.py <scene.json> [target]
"""
import json
import sys

import mujoco
import numpy as np

from vw.interventions import remove
from vw.ir import SceneIR
from vw.physics.mujoco import MuJoCoAdapter

ir = SceneIR.model_validate(json.load(open(sys.argv[1])))
target = sys.argv[2] if len(sys.argv) > 2 else "ball"
cf = remove(ir, [target])
scene = MuJoCoAdapter().compile(cf)
m = mujoco.MjModel.from_xml_string(scene.xml)
d = mujoco.MjData(m)
mujoco.mj_forward(m, d)
f6 = np.zeros(6)
name = lambda g: mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, g)
print(f"{d.ncon} contacts at t=0")
for i in range(d.ncon):
    c = d.contact[i]
    mujoco.mj_contactForce(m, d, i, f6)
    a, b = name(c.geom1), name(c.geom2)
    if "pin" in a or "pin" in b or "gutter" in a or "gutter" in b:
        print(f"{a:12s} {b:12s} dist={c.dist*1000:8.3f} mm  pos={np.round(c.pos, 4)}  "
              f"normal={np.round(c.frame[:3], 3)}  fn={f6[0]:8.2f} N")
