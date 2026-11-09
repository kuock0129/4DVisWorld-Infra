# M2 physics benchmark: cross-backend findings

Raw numbers: [results.md](results.md) and [results.json](results.json); plot: [error_vs_walltime.png](error_vs_walltime.png).
4DCodeBench scenes: [codebench/](codebench/) (one report per engine) and the rendered videos in [`/videos`](../../videos).
Regenerate with `vw bench` (about 6 min, most of it Blender start-up and Newton JIT) and
`vw codebench examples/codebench/B_0x.json --backend <name>`; videos with `python examples/codebench/render_videos.py`.

**Engines.** All four run on one laptop (Windows 11, Ryzen CPU, RTX 4060 Laptop GPU):

| adapter | engine | device | contacts | notes |
|---|---|---|---|---|
| `mujoco` | MuJoCo 3.15 | CPU | yes | soft contacts; restitution mapped onto `solref` |
| `bullet_blender` | Bullet in Blender 4.0.2 (headless) | CPU | no | same engine as the 4DCodeBench runs; about 2-4 s Blender start-up per call |
| `physx` | PhysX 5.3.1 via SAPIEN 3.0.3 | CPU | yes | GPU PhysX not wired up |
| `newton` | Newton 1.7 on Warp 1.19 (XPBD, MuJoCo Warp) | CUDA or CPU | no | multi-world batches |

Every engine gets the same Scene IR through its adapter. All four pass the remove-support tuple, and both 4DCodeBench tuples with the settings listed below.

## Analytic suite (2 ms, default settings)

Rows show the error against the closed-form answer. Full table: [results.md](results.md).

| case | MuJoCo (Euler) | Bullet (Blender) | PhysX (TGS) | Newton XPBD | Newton MuJoCo Warp |
|---|---|---|---|---|---|
| free fall after 1 s (semi-implicit Euler: g·dt·t/2) | 9.8 mm | 9.8 mm | 9.8 mm | 9.8 mm | 9.8 mm |
| sliding distance, μ = 0.2 / 0.5 | 0.2% / 0.4% | 0.6% / 0.6% | 0.2% / 0.5% | 0.2% / 0.5% | 0.2% / 0.4% |
| bounce e = 0.3 / 0.6 / 0.9 | **+45%** / +6% / 0.1% | **−99% / −69% / −51%** | 1.3% / 0.5% / 0.3% | 1.3% / 0.5% / 0.3% | **no bounce** (restitution ignored) |
| head-on collision v_B, e = 1 / 0.5 | 0.1% / 1.9% | **+10% / +13%** | exact | exact | **−48% / −31%** |
| stack of 5: drift / penetration | 0.65 / 0.20 mm | 0.19 / 0.06 mm | 0.11 / 0.03 mm | 1.7 / 0.58 mm | 1.1 / 0.27 mm |
| rolling ball, speed after 1 s | 0.0% | 0.0% | 0.0% | **−30%** | 0.0% |

## 4DCodeBench B_01 / B_03 tuples

Both scenes are converted once (`examples/codebench/convert.py`) and every engine runs the same IR. Each tuple is baseline / causal (ball removed, re-simulated) / non-causal (ball removed, others replay the baseline). The original Blender/Bullet run is a reference, not ground truth.

| engine (setting) | B_01 planks moved (orig 43) | B_03 pins down (orig 9, D1 standing) | causal still | ball error before impact | report |
|---|---|---|---|---|---|
| MuJoCo (default) | 44 | 9 (D1 down, A4 up) | ≤ 1.8 mm | ≤ 3.6 mm | [mujoco](codebench/mujoco/REPORT.md) |
| Bullet (1 mm margin) | 43 | 8 (C1, D1 up) | ≤ 1.6 mm | ≤ 5 mm | [bullet](codebench/bullet/REPORT.md) |
| PhysX (default) | 43, the same set as the original | 8 (A4, D1 up) | ≤ 0.5 mm | ≤ 3.6 mm | [physx](codebench/physx/REPORT.md) |
| Newton XPBD (default) | **21** (the ball stalls in the tower base) | **5** | B_01 creeps 2.2 cm (passes with 32 iterations) | 0.2-1.3 m (the rolling ball slows down) | [newton](codebench/newton/REPORT.md) |
| Newton MuJoCo Warp | 46 | 10 | ≤ 1 cm, run-dependent | ≤ 4 mm | [newton](codebench/newton/REPORT.md) |

After the first impact every engine diverges from the original. The ball typically ends 0.1-0.9 m away. That is the same spread one engine shows across its own timestep and solver settings, so it is chaos, not a bias that a closer setting would remove.

## CPU vs GPU throughput

Scene `tumble` (a ball hits a 4-box tower, 501 frames), N independent copies. Figures are world-steps per second, simulation only, with no contact recording.

| config | N = 1 | 16 | 128 | 1024 | 4096 |
|---|---|---|---|---|---|
| MuJoCo, CPU (1 thread) | 30,261 | | | | |
| PhysX, CPU (1 thread) | 40,797 | | | | |
| Newton XPBD, CUDA, non-deterministic | 2,571 | 40,828 | 362,575 | 1,659,171 | **2,329,862** |
| Newton XPBD, CUDA, deterministic | 399 | 3,241 | 28,000 | 66,569 | **79,811** |
| Newton XPBD, CPU (Warp) | 470 | 6,300 | 21,540 | | |

## Findings

1. **PhysX is the most accurate engine across the board.** It is the only one within about 1% on every analytic case, including the full restitution range and elastic collisions. It is bit-identical across reruns, records contacts, and runs as fast as MuJoCo. On 4DCodeBench it reproduces the original B_01 outcome body for body. One caveat: `max_depenetration_velocity` is unbounded by default, so deep initial overlaps launch bodies. It is now available as an opt-in config key.
2. **Bullet, as Blender exposes it, cannot reproduce restitution.** Bounces lose 50-100% of their height, and an elastic collision gains 10% energy. This applies to every 4DCodeBench Blender scene with bouncing. Blender's default collision margin (0.04 m) also makes thin boxes push cylinders away, so the adapter now uses 1 mm. No contacts or velocities are exposed. Keep it for parity checks against 4DCodeBench, not as the dataset backend.
3. **MuJoCo is fast and stable but biased at low restitution** (e = 0.3 rebounds 45% too high; #45). Its soft contacts let resting bodies settle by up to about 2 mm. It is a solid second backend.
4. **Newton XPBD drains rolling energy.** A ball rolling without slipping loses 30% of its speed in 1 s. This is an engine limitation, not a mapping issue: it is unaffected by iterations or rolling friction and shrinks only with a smaller timestep. As a result B_01's tower does not fall. Newton's MuJoCo Warp solver rolls correctly but ignores restitution, needs μ ≥ 1e-3, and cannot run in Warp's deterministic mode (`WarpDeterminismError`).
5. **Determinism has to be a hard requirement, and it erases most of the GPU advantage today.** The scenes are chaotic: a 1 µm nudge changes the tumble outcome by 4.6 cm, CPU vs GPU Newton runs end up 0.5 m apart, and non-deterministic GPU reruns differ by 5 mm (or 3.8 m with MuJoCo Warp). With determinism on, 4096 Newton worlds give 80 k world-steps/s. That is only 2× one CPU core of PhysX, which scales almost linearly across cores. Non-deterministic Newton reaches 2.3 M/s (57× one PhysX core).
6. **The IR must define how pair materials combine (#47).** The 4DCodeBench scenes mix materials. MuJoCo takes the max of the two friction values, Bullet multiplies them, and PhysX and Newton XPBD average them, so the same IR gives different contact parameters per engine.
7. **Non-causal members record no contacts** on any engine, because only kinematic and static bodies remain. Downstream code that labels contacts must read them from the baseline.
8. **Contact recording makes stepping about 4× slower in MuJoCo and 6× slower in PhysX** (stack of 5 boxes; #46).

## Recommendation (backend decision, #22)

- **Default dataset backend: PhysX (CPU), TGS solver, 2 ms.** Scale out with one process per core. It is the most accurate engine, deterministic, records contacts, and passes both 4DCodeBench tuples.
- **Second backend for cross-checks: MuJoCo.**
- **Bullet (Blender):** keep only to compare against existing 4DCodeBench Blender runs.
- **Newton:** keep for GPU batch experiments, but do not use it for tuples until XPBD's rolling loss or MuJoCo Warp's determinism is fixed upstream. Re-evaluate with each Newton release; the adapter, determinism switch and multi-world benchmark are already in place.

This is a proposal from the benchmark. The decision is the project's to make.

## Not covered

- Meshes: the PhysX, Bullet and Newton adapters refuse them in `check()`.
- Pendulum: needs joints in the IR.
- GPU PhysX.
- Rendering beyond the Blender preview used for the videos.
