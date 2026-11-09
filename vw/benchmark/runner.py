"""Benchmark runner: analytic suite + consistency vs a reference, over backend configs.

A config is (label, backend name, adapter config). Adding a new backend to the
report is one more entry in the config list; nothing else changes.
"""

from __future__ import annotations

import platform
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vw import registry
from vw.benchmark import analytic
from vw.benchmark.consistency import trajectory_divergence
from vw.interventions import remove
from vw.ir import SceneIR


@dataclass(frozen=True)
class BenchConfig:
    label: str
    backend: str
    config: dict[str, Any] = field(default_factory=dict)
    device: str = "auto"


DEFAULT_CONFIGS = [
    BenchConfig("mujoco/euler/4ms", "mujoco", {"timestep": 0.004}),
    BenchConfig("mujoco/euler/2ms (default)", "mujoco", {"timestep": 0.002}),
    BenchConfig("mujoco/euler/1ms", "mujoco", {"timestep": 0.001}),
    BenchConfig("mujoco/euler/0.5ms", "mujoco", {"timestep": 0.0005}),
    BenchConfig("mujoco/implicitfast/2ms", "mujoco", {"timestep": 0.002, "integrator": "implicitfast"}),
    BenchConfig("mujoco/rk4/2ms", "mujoco", {"timestep": 0.002, "integrator": "RK4"}),
    BenchConfig("mujoco/euler/2ms/elliptic", "mujoco", {"timestep": 0.002, "cone": "elliptic"}),
    BenchConfig("mujoco/euler/2ms/no-contacts", "mujoco", {"timestep": 0.002, "record_contacts": False}),
    BenchConfig("bullet/2ms", "bullet_blender", {"timestep": 0.002}),
    BenchConfig("bullet/0.5ms", "bullet_blender", {"timestep": 0.0005}),
    BenchConfig("bullet/2ms/50it", "bullet_blender", {"timestep": 0.002, "solver_iterations": 50}),
]
QUICK_CONFIGS = [DEFAULT_CONFIGS[1], DEFAULT_CONFIGS[3]]
REFERENCE = BenchConfig("mujoco/rk4/0.25ms (reference)", "mujoco", {"timestep": 0.00025, "integrator": "RK4"})


def consistency_scenes(example: Path | None = None) -> dict[str, SceneIR]:
    """Scenes compared trajectory-by-trajectory against the reference config."""
    a = analytic
    scenes = {
        "stack5": a.scene("stack5", [a._ground()] + [a._box(f"b{i}", (0, 0, 0.1 + 0.2 * i)) for i in range(5)], 3.0),
        "bounce_e0.6": a.scene("bounce", [a._ground(restitution=0.6), a._sphere("ball", (0, 0, 1.1), restitution=0.6)], 1.4),
        "slide_mu0.5": a.scene("slide", [a._ground(friction=0.5), a._box("box", (0, 0, 0.1), vel=(2, 0, 0), friction=0.5)], 1.0),
        "tumble": a.scene(
            "tumble",
            [a._ground(friction=0.6)]
            + [a._box(f"b{i}", (0.03 * i, 0, 0.1 + 0.2 * i), friction=0.6) for i in range(4)]
            + [a._sphere("ball", (-1.0, 0, 0.5), radius=0.1, mass=2.0, vel=(4, 0, 0), friction=0.6)],
            2.0,
        ),
    }
    if example and example.exists():
        ir = SceneIR.load(example)
        scenes["remove_support/baseline"] = ir
        scenes["remove_support/causal"] = remove(ir, ["support"])
    return scenes


def _host() -> dict[str, str]:
    return {"os": f"{platform.system()} {platform.release()}", "cpu": platform.processor() or platform.machine(),
            "python": platform.python_version()}


def run_benchmark(
    configs: list[BenchConfig] | None = None,
    reference: BenchConfig = REFERENCE,
    example: Path | None = Path("examples/remove_support.json"),
    repeats: int = 3,
    log=print,
) -> dict[str, Any]:
    configs = configs or DEFAULT_CONFIGS
    analytic.REPEATS = repeats
    scenes = consistency_scenes(example)

    log(f"reference: {reference.label}")
    ref_adapter = registry.get_physics(reference.backend, device=reference.device, **reference.config)
    ref_sims = {name: ref_adapter.simulate(ref_adapter.compile(ir)) for name, ir in scenes.items()}

    results: dict[str, Any] = {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "host": _host(),
        "reference": reference.label,
        "configs": [],
    }
    probe = next(iter(scenes.values()))
    for cfg in configs:
        t0 = time.perf_counter()
        try:
            adapter = registry.get_physics(cfg.backend, device=cfg.device, **cfg.config)
            problems = adapter.check(probe)
        except (RuntimeError, ImportError) as e:
            problems = [str(e)]
        if problems:
            log(f"  {cfg.label:34s} skipped: {'; '.join(problems)}")
            results.setdefault("skipped", []).append({"label": cfg.label, "reason": problems})
            continue
        cases = analytic.run_suite(adapter)
        cons = {}
        for name, ir in scenes.items():
            native = adapter.compile(ir)
            ts = time.perf_counter()
            sim = adapter.simulate(native)
            wall = analytic.sim_wall(sim, time.perf_counter() - ts)
            div = trajectory_divergence(sim, ref_sims[name])
            cons[name] = {**div.__dict__, "sim_wall_s": wall}
        suite_wall = sum({(c.case, tuple(sorted(c.params.items()))): c.sim_wall_s for c in cases}.values())
        results["configs"].append(
            {
                "label": cfg.label,
                "backend": cfg.backend,
                "version": adapter.version,
                "device": adapter.device.value,
                "config": cfg.config,
                "suite_sim_wall_s": suite_wall,
                "analytic": [c.to_dict() for c in cases],
                "consistency": cons,
            }
        )
        log(f"  {cfg.label:34s} suite sim {suite_wall:6.2f}s  (total {time.perf_counter() - t0:5.1f}s)")
    return results
