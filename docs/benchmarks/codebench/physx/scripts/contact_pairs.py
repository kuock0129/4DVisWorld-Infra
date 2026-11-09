"""Tally contact events by pair class for the default-config baseline and causal runs.
Also print the first ball contact and, for B_03, the first-frame contacts of the corner pins."""
import collections, re, sys
from vw.ir import SceneIR
from vw.interventions import remove
from vw.physics.physx import PhysXAdapter

def cls(n):
    return re.sub(r"_?\d+$", "", re.sub(r"^(pin|plank|gutter|storage_box)_.*", r"\1", n))

for case in sys.argv[1:] or ["B_01", "B_03"]:
    ir = SceneIR.load(f"examples/codebench/{case}.json")
    for name, scene in (("baseline", ir), ("causal", remove(ir, ["ball"]))):
        ad = PhysXAdapter(); sim = ad.simulate(ad.compile(scene))
        tally = collections.Counter(tuple(sorted((cls(c.obj_a), cls(c.obj_b)))) for c in sim.contacts)
        pairs = {tuple(sorted((c.obj_a, c.obj_b))) for c in sim.contacts}
        print(case, name, "events", len(sim.contacts), "distinct pairs", len(pairs), dict(tally.most_common(8)))
        if name == "baseline":
            ball = sorted((c for c in sim.contacts if "ball" in (c.obj_a, c.obj_b) and "floor" not in (c.obj_a, c.obj_b)
                           and "lane" not in (c.obj_a, c.obj_b)), key=lambda c: c.t)[:3]
            print("  first ball contacts:", [(round(c.t * 24), c.obj_a, c.obj_b, round(c.impulse, 3)) for c in ball])
        print("  frame-1 non-support pairs:", sorted({(c.obj_a, c.obj_b) for c in sim.contacts if round(c.t * 24) == 1}
              - {p for p in pairs if "floor" in p or "lane" in p})[:12])
