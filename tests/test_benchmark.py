import numpy as np
import pytest

from vw.benchmark.consistency import trajectory_divergence
from vw.physics.base import BackendInfo, Device, SimResult


def _sim(poses):
    return SimResult(10, poses, {}, [], BackendInfo("x", "0", Device.CPU))


def test_divergence_identical_and_shifted():
    p = np.tile([0, 0, 0, 1, 0, 0, 0.0], (5, 1))
    q = p.copy()
    q[:, 0] += np.arange(5) * 0.1
    a, b = _sim({"o": p}), _sim({"o": q})
    assert trajectory_divergence(a, a).max_pos == 0
    d = trajectory_divergence(a, b)
    assert d.max_pos == pytest.approx(0.4) and d.final_pos == pytest.approx(0.4) and d.worst_body == "o"
    assert d.max_rot_deg == pytest.approx(0, abs=1e-5)


def test_divergence_rejects_mismatch():
    p = np.tile([0, 0, 0, 1, 0, 0, 0.0], (5, 1))
    with pytest.raises(ValueError, match="timing"):
        trajectory_divergence(_sim({"o": p}), _sim({"o": p[:4]}))
    with pytest.raises(ValueError, match="body sets differ"):
        trajectory_divergence(_sim({"o": p}), _sim({"o": p, "x": p}))


mujoco = pytest.importorskip("mujoco")


def test_analytic_suite_default_config():
    from vw import registry
    from vw.benchmark.analytic import run_suite

    res = {(r.case, r.metric): r for r in run_suite(registry.get_physics("mujoco", device="cpu"))}
    assert res[("free_fall", "max position error over 1 s")].abs_err < 0.011  # Euler: g*dt*t/2
    assert res[("free_fall", "time to drop 1 m")].rel_err < 0.01
    assert res[("slide", "stopping distance (mu=0.2)")].rel_err < 0.01
    assert res[("slide", "stopping distance (mu=0.5)")].rel_err < 0.01
    assert res[("stack", "top box drift over 3 s (5 boxes)")].abs_err < 2e-3
    assert res[("bounce", "rebound height (e=0.0)")].abs_err < 1e-3
    assert res[("bounce", "rebound height (e=0.9)")].rel_err < 0.02
    for e in (1.0, 0.5):
        assert res[("collision", f"momentum after (e={e})")].abs_err < 1e-4


def test_runner_and_report(tmp_path, example_path):
    from vw.benchmark.report import write_report
    from vw.benchmark.runner import QUICK_CONFIGS, BenchConfig, run_benchmark

    ref = BenchConfig("ref", "mujoco", {"timestep": 0.001, "integrator": "RK4"})
    res = run_benchmark(QUICK_CONFIGS[:1], reference=ref, example=example_path, repeats=1, log=lambda *_: None)
    assert res["configs"][0]["consistency"]["remove_support/causal"]["max_pos"] < 0.05
    paths = write_report(res, tmp_path)
    md = (tmp_path / "results.md").read_text(encoding="utf-8")
    assert "## Analytic suite" in md and "remove_support/causal" in md
    assert (tmp_path / "results.json").exists() and len(paths) >= 2
