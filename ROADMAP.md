# visualworld-infra — Roadmap & Milestones

Simulator-agnostic infra for generating physically consistent counterfactual video tuples:
**source video → coding agent (4DCodeBench-style) → Scene IR → intervention → physics adapter → render adapter → verify → export.**

Target: dataset v0.1 + arXiv draft by **end of January 2027**.

| # | Milestone | Window | Due (PST) | Owner |
|---|---|---|---|---|
| M0 | Foundations: IR + adapter interfaces | Nov 6 – Nov 15 | 2026-11-15 | Kevin |
| M1 | First end-to-end removal tuple | Nov 16 – Nov 29 | 2026-11-29 | Kevin |
| M2 | Physics backend benchmark | Nov 16 – Dec 6 | 2026-12-06 | Kevin |
| M3 | Video front-end (Stage 1 reconstruction) | Dec 1 – Dec 20 | 2026-12-20 | Kevin |
| M4 | Scale-out & contributor workflow | Dec 14 – Jan 10 | 2027-01-10 | Kevin |
| M5 | Dataset v0.1 + paper | Jan 4 – Jan 31 | 2027-01-31 | All |

M1 and M2 run in parallel. Holidays (Thanksgiving Nov 26, Dec 24 – Jan 1) are inside M1 and M4, so those windows are longer.

---

## M0 — Foundations: IR + adapter interfaces
**Goal:** freeze the contracts every other component depends on.

- [ ] Repo skeleton: `vw/{sdk,ir,interventions,physics,render,importers,exporters,verify,cli}`, `tests/`, `docker/`
- [ ] Scene IR schema v0 (pydantic): bodies (dynamic / static / kinematic), geometry, physics params (SI units), materials, cameras, lights, gravity, fps/frames, `level: physical | trace`
- [ ] `SimResult` schema: per-object poses & velocities per frame, contact events, backend info
- [ ] `PhysicsAdapter` / `RenderAdapter` / `Importer` / `Exporter` protocols
- [ ] Capability registry (features + device: cpu / cuda / metal) and `check(ir)` that fails loudly
- [ ] Manifest schema: seeds, backend + version, solver config, device, hardware, token usage
- [ ] CI (lint, type-check, unit tests on CPU) + CPU Docker image
- [ ] Aggregate contributor 4DCodeBench reports (framework, model, tokens/cost, runtime, hardware)

**Done when:** schemas are versioned (`ir_version: 0.1`), a hand-written IR JSON validates, and the adapter protocols have stub implementations passing CI.

## M1 — First end-to-end removal tuple
**Goal:** one hand-written scene produces a verified baseline / causal / non-causal tuple with masks.

- [ ] Kubric-style Python SDK (`Scene`, `add_box`, `add_mesh`, `camera`, `light`) → emits Scene IR
- [ ] MuJoCo adapter: IR → MJCF, simulate, normalize to `SimResult`; kinematic replay support
- [ ] Blender render adapter (Cycles + EEVEE): rgb, depth, instance segmentation; fixed render seed
- [ ] `Remove` intervention: `mode=causal` (re-simulate) and `mode=non_causal` (replay baseline poses)
- [ ] Mask derivation: removed-object mask, affected region (trajectory divergence), shadow/reflection (off-mask pixel diff)
- [ ] Code checks v0: rest-at-t0, causal must diverge / non-causal must not, penetration, energy
- [ ] Sample folder writer + manifest
- [ ] Demo scene: object resting on a support → remove support

**Done when:** `vw generate examples/remove_support.py` outputs a tuple folder that passes all checks, on CPU only.

## M2 — Physics backend benchmark
**Goal:** a data-backed answer to "which backend gives the best accuracy vs. cost".

- [ ] Analytic test suite: free-fall time, bounce height vs restitution, sliding distance vs friction, stack stability, pendulum period, momentum-conserving collision
- [ ] BlenderBullet adapter (parity with 4DCodeBench Blender runs)
- [ ] Newton / MuJoCo Warp adapter (GPU, batched)
- [ ] PhysX adapter (stretch)
- [ ] Cross-backend consistency: same IR on ≥2 adapters, trajectory error report
- [ ] Benchmark report: error vs wall-clock, CPU vs GPU, setup effort → backend decision

**Done when:** report is published in `docs/benchmarks/` and the default backends are chosen.

## M3 — Video front-end (Stage 1 reconstruction)
**Goal:** turn 4DCodeBench-style agent output into accepted Physical IR.

- [ ] `bpy_script` importer: run headless Blender, read rigid body / kinematic / camera / light / material state → IR
- [ ] Unsupported-feature detection (cloth, fluid, particles, fracture) → trace-level IR or reject
- [ ] Prompt addendum for 4DCodeBench runs (dynamic objects must use rigid body) + optional `vw` bpy helper for initial velocity etc.
- [ ] Import-yield study on existing B_01 / B_03 contributor runs (with vs. without simulator)
- [ ] Fidelity metrics vs source video: DINOv3 similarity, dynamic IoU, tracks, depth
- [ ] Parameter tuning after backend switch (CMA-ES / grid on mass ratio, friction, restitution)
- [ ] Calibrate fidelity thresholds on 4DCodeBench synthetic scenes (4D ground truth)
- [ ] Code-as-World `scene.json` importer (stretch)

**Done when:** ≥3 source videos go video → agent → importer → MuJoCo → fidelity pass → removal tuple.

## M4 — Scale-out & contributor workflow
**Goal:** many contributors can generate data without coordination overhead.

- [ ] CLI: `vw reconstruct`, `vw generate`, `vw validate`, `vw upload`; `--device auto|cpu|gpu`
- [ ] Taxonomy cell scheduler (replaces the FCFS sheet) + balance dashboard
- [ ] Perturbation sampler (params, camera, lighting) → ×N tuples per reconstructed scene
- [ ] Device consistency rule: every tuple generated on one device + backend (enforced via manifest)
- [ ] Newton batch path for Stage 2 + GPU render path
- [ ] Shared storage (HF dataset or WebDataset shards) + upload validation
- [ ] Contribution log: tokens, cost, accepted samples per contributor (authorship credit)
- [ ] Exporters: `4dcodebench_task`, `caw_scene_json`, `usd`

**Done when:** an external contributor generates and uploads accepted tuples by following `CONTRIBUTING.md` alone.

## M5 — Dataset v0.1 + paper
**Goal:** release a first dataset and an arXiv draft.

- [ ] Generate dataset v0.1 (target to be set from M3/M4 cost & yield numbers)
- [ ] QC report: acceptance rates, failure reasons, taxonomy distribution
- [ ] Infra capability comparison table vs Kubric, BlenderProc, Infinigen, Omniverse Replicator
- [ ] Baseline experiment (e.g., train/eval a removal model on v0.1)
- [ ] Dataset card, license audit of source videos and assets
- [ ] arXiv draft

**Done when:** dataset v0.1 is public and the draft is circulated to advisors.
