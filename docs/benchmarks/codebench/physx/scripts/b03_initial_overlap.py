"""B_03: which static shapes touch the corner pins at t=0? Prints the first-step contacts
(separation < 0 = penetration) for every pin, using the adapter's own scene builder."""
import sys
import numpy as np
from vw.ir import SceneIR
from vw.interventions import remove
from vw.physics.physx import PhysXAdapter, _import_sapien

ir = remove(SceneIR.load("examples/codebench/B_03.json"), ["ball"])
ad = PhysXAdapter()
native = ad.compile(ir)
sapien = _import_sapien()
scene, ents, bodies = ad._build(sapien, native.config, ir, set())
scene.step()
for c in scene.get_contacts():
    a, b = c.bodies[0].entity.name, c.bodies[1].entity.name
    if "pin" not in a + b:
        continue
    seps = [pt.separation for pt in c.points]
    imp = sum(float(np.linalg.norm(pt.impulse)) for pt in c.points)
    if a.startswith("pin") and b == "lane" or b.startswith("pin") and a == "lane":
        continue
    print(f"{a:10s} {b:10s} n={len(seps)} min_sep={min(seps):+.4f} m impulse={imp:.4f}")

# analytic: AABB of each gutter / curb slab vs. pin cylinder footprint
from vw.physics.util import quat_to_mat
for b in ir.bodies:
    if not (b.id.startswith("gutter") or b.id.startswith("curb")):
        continue
    R = quat_to_mat(np.array(b.initial_pose.orientation)); h = np.array(b.geometry.extents) / 2
    half = np.abs(R) @ h; p = np.array(b.initial_pose.position)
    print(f"{b.id:11s} AABB x[{p[0]-half[0]:+.3f},{p[0]+half[0]:+.3f}] y[{p[1]-half[1]:+.3f},{p[1]+half[1]:+.3f}] z[{p[2]-half[2]:+.3f},{p[2]+half[2]:+.3f}]")
