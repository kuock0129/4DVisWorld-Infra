"""CPU vs GPU throughput: world-steps per second for N independent copies of a scene.

Newton runs N worlds in one model (``worlds=N``) on CUDA or CPU. The CPU engines
(MuJoCo, PhysX) are timed on one world; N worlds on them cost N times as much on one
core (or N / cores with process-level parallelism, which this does not measure).
"""

from __future__ import annotations

import time
from typing import Any

from vw import registry
from vw.ir import SceneIR

NEWTON_WORLDS = (1, 16, 128, 1024, 4096)


def _rate(sim, frames: int, worlds: int, measured: float) -> dict[str, float]:
    cfg = sim.backend.solver_config
    wall = float(cfg.get("sim_wall_s", measured))
    steps = (frames - 1) * int(cfg.get("steps_per_frame", 1))
    return {"worlds": worlds, "sim_wall_s": wall, "world_steps_per_s": worlds * steps / wall,
            "world_frames_per_s": worlds * (frames - 1) / wall}


def run_throughput(ir: SceneIR, newton_worlds=NEWTON_WORLDS, log=print) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []

    def add(label, backend, device, worlds=1, **config):
        try:
            a = registry.get_physics(backend, device=device, **config, **({"worlds": worlds} if worlds > 1 else {}))
            if a.check(ir):
                return
            native = a.compile(ir)
            t0 = time.perf_counter()
            sim = a.simulate(native)
            r = _rate(sim, ir.timing.frames, worlds, time.perf_counter() - t0)
        except (RuntimeError, ImportError) as e:
            log(f"  throughput {label}: skipped ({e})")
            return
        rows.append({"label": label, "backend": backend, "device": device, **r})
        log(f"  throughput {label:34s} worlds {worlds:5d}  {r['world_steps_per_s']:12.0f} world-steps/s")

    add("mujoco/cpu", "mujoco", "cpu", timestep=0.002, record_contacts=False)
    add("physx/cpu", "physx", "cpu", timestep=0.002, record_contacts=False)
    for det in (False, True):
        tag = "det" if det else "nondet"
        for w in newton_worlds:
            add(f"newton/xpbd/cuda/{tag}", "newton", "cuda", worlds=w, timestep=0.002, deterministic=det)
    for w in newton_worlds[:3]:
        add("newton/xpbd/cpu/nondet", "newton", "cpu", worlds=w, timestep=0.002, deterministic=False)
    return {"scene": ir.metadata.get("name"), "frames": ir.timing.frames, "rows": rows}
