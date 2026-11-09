"""Minimal repro: the B_03 / B_01 ball alone on its support, rolling with v = w r. Prints ball speed and spin per frame.

Usage: python rolling_ball.py B_03|B_01 [device] [json-config]
With no pins/planks, the ball should keep v (no damping, rolling friction 1e-4).
"""
import json, sys
import numpy as np
from vw.ir import SceneIR
from vw.registry import get_physics

case = sys.argv[1] if len(sys.argv) > 1 else "B_03"
dev = sys.argv[2] if len(sys.argv) > 2 else "cuda"
cfg = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
ir = SceneIR.load(f"examples/codebench/{case}.json")
ir = ir.model_copy(update={"bodies": [b for b in ir.bodies if b.kind.value == "static" or b.id == "ball"]})
ad = get_physics("newton", device=dev, **cfg)
sim = ad.simulate(ad.compile(ir))
p, v = sim.poses["ball"], sim.velocities["ball"]
r = ir.body("ball").geometry.radius
for f in [0, 1, 2, 3, 4, 6, 8, 12, 20, 30, 40]:
    if f < len(p):
        print(f"f{f:3d} x={p[f,0]:7.3f} z={p[f,2]:.4f} |v|={np.linalg.norm(v[f,:3]):.3f} w={np.round(v[f,3:],2)} w*r={np.linalg.norm(v[f,3:])*r:.3f}")
