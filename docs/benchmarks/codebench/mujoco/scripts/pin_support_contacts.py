"""Number of pin-lane contact points per pin after 0.1 s of settling (B_03, ball removed).

A standing cylinder needs >= 3 support points to stay up without rocking.
Usage: python pin_support_contacts.py examples/codebench/B_03.json
"""
import collections
import json
import sys

import mujoco

from vw.interventions import remove
from vw.ir import SceneIR
from vw.physics.mujoco import MuJoCoAdapter

ir = SceneIR.model_validate(json.load(open(sys.argv[1])))
cf = remove(ir, ["ball"])
m = mujoco.MjModel.from_xml_string(MuJoCoAdapter("cpu").compile(cf).xml)
d = mujoco.MjData(m)
for _ in range(int(0.1 / m.opt.timestep)):
    mujoco.mj_step(m, d)
name = lambda g: mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, g)
cnt = collections.Counter()
for i in range(d.ncon):
    a, b = sorted((name(d.contact[i].geom1), name(d.contact[i].geom2)))
    cnt[(a, b)] += 1
for k, v in sorted(cnt.items()):
    print(k, v)
