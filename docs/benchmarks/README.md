# M2 physics benchmark: findings so far

Raw numbers: [results.md](results.md) and [results.json](results.json); plot: [error_vs_walltime.png](error_vs_walltime.png).
Regenerate with `pip install -e ".[bench]"` then `vw bench`. A full run takes about 15 s on a laptop CPU.

**Scope of this run.** Only one backend, MuJoCo 3.17 on CPU, is implemented so far. Its configs
(integrator, timestep, friction cone, contact recording) are compared against closed-form physics and
against a high-accuracy reference (RK4, 0.25 ms). The cross-backend part of M2 (BlenderBullet, Newton,
PhysX) plugs into the same runner as extra `BenchConfig` entries, so **the backend decision is still
open**. This report covers MuJoCo's accuracy vs. cost and the effect of the IR → MuJoCo mapping.

## Analytic suite

| Case | Closed form | What MuJoCo does |
|---|---|---|
| Free fall | z = z0 − g t²/2 | Semi-implicit Euler is first order: error = g·dt·t/2 (9.8 mm after 1 s at 2 ms, halves with dt). RK4 is exact to 1e-14. Time to drop 1 m is within 0.2% for every config. |
| Sliding | d = v0²/(2 μ g) | Within 0.5% at the default config, within 0.1% at 1 ms or with RK4. Friction is mapped correctly. |
| Stack of 5 boxes | no motion | Stable in every config. Top-box drift is 0.65 mm over 3 s at the default config (2.9 mm at 4 ms); penetration is about 0.2 mm (soft contacts). |
| Head-on collision | momentum conserved; v_B = (1+e)/2·v | Momentum is conserved to about 2e-6. v_B is within 0.2% for e = 1 and about 2% high for e = 0.5. |
| Bounce | rebound = e² h | Accurate for e ≥ 0.9 (0.1%) and e = 0 (no bounce). **Biased for low e:** e = 0.6 rebounds about 6% high, e = 0.3 about 45% high (effective e ≈ 0.36). The bias does not shrink with smaller dt, so it comes from the restitution → `solref` mapping, not from the integrator. |

Pendulum period is not tested: IR v0.1 has no joints.

## Findings

1. **The restitution mapping needed a stiffness fix, and still has a low-e bias.** The naive mapping
   (fixed timeconst, dampratio from e) makes contact stiffness grow as 1/dampratio² and explodes for
   e ≥ 0.9 (a 21 m rebound from 1 m; 4155 m/s after an elastic collision). The adapter now uses
   timeconst / dampratio, which keeps stiffness constant (see `restitution_solref`). The remaining low-e bias
   matches neither the textbook damped-oscillator relation nor the unilateral Kelvin-Voigt model. Fixing it
   needs an empirical calibration table per (dt, contact timeconst). **Proposed follow-up issue.**
2. **RK4 at 2 ms is the best accuracy for the cost** among the configs tried. It beats Euler at 0.5 ms on
   free fall, sliding, stack drift and the remove-support scene at about 45% of the wall-clock (0.33 s vs 0.74 s
   for the analytic suite). Caveat: the consistency reference is also RK4, which flatters RK4 in that table;
   the analytic table has no such bias. **Proposal: make RK4 / 2 ms the MuJoCo default once a second backend confirms.**
3. **Multi-body collisions are chaotic, so pair consistency is mandatory, not optional.** In the "tumble"
   scene (a ball hits a 4-box tower), nudging one start position by 1 µm moves the reference trajectory
   by 4.6 cm. Different configs disagree by 7–80 cm. Simple scenes (stack, remove-support) do not amplify
   perturbations at all. Reruns of the same IR and config are bit-identical. This is direct evidence for the
   M0 rule that every member of a tuple must use one backend, config and device, and that rule is now
   enforced by the manifest.
4. **Contact recording is the main cost.** Extracting per-frame contact events in Python makes simulation
   3.5× slower (stack5: 0.17 s vs 0.05 s). Vectorizing it with `mj_contactForce` over `d.contact`, or
   recording only at frame boundaries, is the cheapest speed-up available. **Proposed follow-up issue.**
5. **The elliptic friction cone is not better here.** It roughly triples stack drift (2.1 mm vs 0.65 mm) at the same cost.
   Keep the pyramidal cone.
6. **The IR must define how pair materials combine.** Each analytic case gives both contacting bodies the same
   friction and restitution, because backends combine pairs differently: MuJoCo takes the max of the two
   frictions and the mean of the two solrefs, Bullet multiplies, and PhysX averages by default. With different
   materials, the same IR would give different physics on different backends. **Open IR v0.2 question:**
   either add a combination rule, which each adapter then implements, or store per-pair materials.

## Not done yet (rest of M2)

- BlenderBullet adapter (Blender 4.0 is available on the dev machine), Newton / MuJoCo Warp adapter (GPU), PhysX (stretch)
- Cross-backend columns in the report and the actual backend decision
- CPU vs GPU comparison (needs the Newton adapter)
- Pendulum (needs joints in the IR)
