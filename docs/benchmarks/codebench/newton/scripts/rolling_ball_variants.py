"""Which ingredient slows the free rolling ball? Ball alone on (a) the B_03 lane box or (b) an infinite plane,
with Newton's default torsional/rolling friction or with both patched to 0. Prints |v| at frames 0, 1, 12, 40."""
import json, sys
import numpy as np
import newton
from vw.ir import SceneIR
from vw.ir.schema import Plane
from vw.registry import get_physics

dev = sys.argv[1] if len(sys.argv) > 1 else "cuda"
cfg = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
base = SceneIR.load("examples/codebench/B_03.json")
ball = base.body("ball")
lane = base.body("lane")
orig_init = newton.ModelBuilder.ShapeConfig.__init__

def run(support, zero_extra):
    if support == "plane":
        sup = lane.model_copy(update={"geometry": Plane(type="plane", extents=[20.0, 20.0]),
                                      "initial_pose": lane.initial_pose.model_copy(update={"position": [0, 0, 0], "orientation": [1, 0, 0, 0]})})
    else:
        sup = lane
    ir = base.model_copy(update={"bodies": [sup, ball]})
    if zero_extra:
        def init(self, *a, **k):
            orig_init(self, *a, **k); self.mu_torsional = 0.0; self.mu_rolling = 0.0
        newton.ModelBuilder.ShapeConfig.__init__ = init
    else:
        newton.ModelBuilder.ShapeConfig.__init__ = orig_init
    ad = get_physics("newton", device=dev, **cfg)
    s = ad.simulate(ad.compile(ir))
    v = np.linalg.norm(s.velocities["ball"][:, :3], axis=1)
    print(f"{support:5s} torsional/rolling={'0' if zero_extra else 'default'}: |v| f0={v[0]:.3f} f1={v[1]:.3f} f12={v[12]:.3f} f40={v[40]:.3f}  z_f40={s.poses['ball'][40,2]:.4f}")

for sup in ("lane", "plane"):
    for z in (False, True):
        run(sup, z)
