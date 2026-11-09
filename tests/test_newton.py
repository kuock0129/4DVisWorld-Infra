import math
import shutil

import numpy as np
import pytest

from vw import registry
from vw.interventions import remove

pytest.importorskip("newton")


@pytest.fixture(scope="module")
def nt():
    return registry.get_physics("newton", device="cpu")


def _diff(a, b):
    return max(np.abs(a.poses[k][:, :3] - b.poses[k][:, :3]).max() for k in a.poses)


def test_remove_support_tuple(nt, example_ir):
    base = nt.simulate(nt.compile(example_ir))
    cf = remove(example_ir, ["support"])
    causal = nt.simulate(nt.compile(cf))
    noncausal = nt.simulate(nt.compile(cf), kinematic={"box": base.poses["box"]})

    assert base.num_frames == example_ir.timing.frames and set(base.poses) == {"ground", "support", "box"}
    assert np.abs(base.poses["box"][:, :3] - base.poses["box"][0, :3]).max() < 1e-3
    assert causal.poses["box"][-1, 2] == pytest.approx(0.1, abs=2e-3)
    np.testing.assert_allclose(noncausal.poses["box"], base.poses["box"])
    z = causal.poses["box"][:, 2]
    t_hit = int(np.argmax(z < 0.1 + 2e-3)) / example_ir.timing.fps
    assert t_hit == pytest.approx(math.sqrt(2 * 0.4 / 9.81), abs=1.5 / example_ir.timing.fps)
    cfg = base.backend.solver_config
    assert cfg["solver"] == "xpbd" and cfg["steps_per_frame"] == 21 and cfg["deterministic"]


def test_analytic_cases(nt):
    from vw.benchmark.analytic import bounce, collision, slide

    rs = {r.metric: r for r in bounce(nt, (0.6, 0.9)) + slide(nt, (0.5,)) + collision(nt)}
    assert rs["rebound height (e=0.9)"].rel_err < 0.02
    assert rs["rebound height (e=0.6)"].rel_err < 0.02
    assert rs["stopping distance (mu=0.5)"].rel_err < 0.01
    for e in (1.0, 0.5):
        assert rs[f"v_B after (e={e})"].rel_err < 0.01
        assert rs[f"momentum after (e={e})"].abs_err < 1e-4


def test_kinematic_ir_body(nt):
    from vw.benchmark.analytic import _box, _ground, scene

    T = 101
    paddle = _box("paddle", (-0.5, 0, 0.1))
    paddle.pop("mass")
    paddle["kind"] = "kinematic"
    xs = np.linspace(-0.5, 0.3, T)
    paddle["trajectory"] = {"positions": [[x, 0, 0.1] for x in xs], "orientations": [[1, 0, 0, 0]] * T}
    sim = nt.simulate(nt.compile(scene("push", [_ground(), paddle, _box("box", (0.0, 0, 0.1))], (T - 1) / 250)))
    np.testing.assert_allclose(sim.poses["paddle"][:, 0], xs)
    assert sim.poses["box"][-1, 0] > 0.45


def test_deterministic_and_worlds_match_single_run(nt):
    from vw.benchmark.runner import consistency_scenes

    ir = consistency_scenes()["tumble"]
    a, b = nt.simulate(nt.compile(ir)), nt.simulate(nt.compile(ir))
    assert _diff(a, b) == 0.0
    batch = registry.get_physics("newton", device="cpu", worlds=3)
    c = batch.simulate(batch.compile(ir))
    assert _diff(a, c) == 0.0 and c.backend.solver_config["worlds"] == 3


def test_refuses_damping(nt, example_dict):
    from vw.ir import SceneIR

    example_dict["bodies"][2]["linear_damping"] = 0.1
    assert any("damping" in p for p in nt.check(SceneIR.model_validate(example_dict)))


@pytest.mark.skipif(shutil.which("nvidia-smi") is None, reason="no CUDA device")
def test_cuda_matches_contract(monkeypatch, example_ir):
    monkeypatch.setenv("VW_DEVICES", "cuda,cpu")
    gpu = registry.get_physics("newton", device="cuda")
    sim = gpu.simulate(gpu.compile(remove(example_ir, ["support"])))
    assert sim.backend.device.value == "cuda" and sim.backend.solver_config["cuda_graph"]
    assert sim.poses["box"][-1, 2] == pytest.approx(0.1, abs=2e-3)
