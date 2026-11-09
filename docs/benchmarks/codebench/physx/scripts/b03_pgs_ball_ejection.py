"""B_03 with solver=pgs: the ball, resting in the pit against the back wall, is launched upward at
about frame 55 and leaves the scene. Print the ball's speed per frame and the largest contact
impulses around the event."""
import numpy as np
from vw.ir import SceneIR
from vw.physics.physx import PhysXAdapter

ir = SceneIR.load("examples/codebench/B_03.json")
ad = PhysXAdapter(solver="pgs")
sim = ad.simulate(ad.compile(ir))
v = np.linalg.norm(sim.velocities["ball"][:, :3], axis=1)
p = sim.poses["ball"][:, :3]
for k in range(40, 70):
    ev = sorted((c for c in sim.contacts if abs(c.t * 24 - k) < 0.5 and "ball" in (c.obj_a, c.obj_b)),
                key=lambda c: -c.impulse)[:3]
    print(k, p[k].round(3), f"|v|={v[k]:.2f}", [(c.obj_a, c.obj_b, round(c.impulse, 2)) for c in ev])
