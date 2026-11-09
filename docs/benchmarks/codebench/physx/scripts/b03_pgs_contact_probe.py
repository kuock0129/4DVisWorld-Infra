"""Step the B_03 PGS baseline by hand and print every ball-pin_A3 contact (points, separation,
impulse) from frame 45 to 54, to see whether PhysX generates the pair while the shapes overlap."""
import numpy as np
from vw.ir import SceneIR
from vw.physics.physx import PhysXAdapter, _import_sapien

sapien = _import_sapien()
ir = SceneIR.load("examples/codebench/B_03.json")
ad = PhysXAdapter(solver="pgs")
nat = ad.compile(ir)
n = nat.config["steps_per_frame"]
scene, ents, bodies = ad._build(sapien, nat.config, ir, set())
for k in range(1, 55):
    for s in range(n):
        scene.step()
        if k >= 46 and s % 7 == 0:
            for c in scene.get_contacts():
                names = {c.bodies[0].entity.name, c.bodies[1].entity.name}
                if names == {"ball", "pin_A3"}:
                    print(k, s, len(c.points), [round(p.separation, 4) for p in c.points],
                          round(sum(float(np.linalg.norm(p.impulse)) for p in c.points), 4))
    if k >= 46:
        print(k, "ball", np.round(ents["ball"].pose.p, 3), "pinA3", np.round(ents["pin_A3"].pose.p, 3),
              "ball v", np.round(bodies["ball"].linear_velocity, 2))
