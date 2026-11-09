import math

import numpy as np
import pytest

from vw import registry
from vw.interventions import remove

pytest.importorskip("sapien")


@pytest.fixture
def px():
    return registry.get_physics("physx", device="cpu")


def test_remove_support_tuple(px, example_ir):
    base = px.simulate(px.compile(example_ir))
    cf = remove(example_ir, ["support"])
    causal = px.simulate(px.compile(cf))
    noncausal = px.simulate(px.compile(cf), kinematic={"box": base.poses["box"]})

    assert base.num_frames == example_ir.timing.frames and set(base.poses) == {"ground", "support", "box"}
    assert np.abs(base.poses["box"][:, :3] - base.poses["box"][0, :3]).max() < 1e-3
    assert causal.poses["box"][-1, 2] == pytest.approx(0.1, abs=2e-3)
    np.testing.assert_allclose(noncausal.poses["box"], base.poses["box"])
    assert {frozenset((c.obj_a, c.obj_b)) for c in base.contacts} == {
        frozenset(("box", "support")), frozenset(("ground", "support"))}
    assert {frozenset((c.obj_a, c.obj_b)) for c in causal.contacts} == {frozenset(("box", "ground"))}
    assert noncausal.contacts == []
    t_hit = min(c.t for c in causal.contacts)
    assert t_hit == pytest.approx(math.sqrt(2 * 0.4 / 9.81), abs=1.0 / example_ir.timing.fps)
    assert base.backend.solver_config["steps_per_frame"] == 21 and "physx-5" in base.backend.version


def test_analytic_cases(px):
    from vw.benchmark.analytic import bounce, collision, slide

    rs = {r.metric: r for r in bounce(px, (0.6, 0.9)) + slide(px, (0.5,)) + collision(px)}
    assert rs["rebound height (e=0.9)"].rel_err < 0.01
    assert rs["rebound height (e=0.6)"].rel_err < 0.02
    assert rs["stopping distance (mu=0.5)"].rel_err < 0.01
    for e in (1.0, 0.5):
        assert rs[f"v_B after (e={e})"].rel_err < 0.01
        assert rs[f"momentum after (e={e})"].abs_err < 1e-4


def test_kinematic_ir_body_and_overrides(px, example_ir):
    from vw.benchmark.analytic import _box, _ground, scene

    T = 101
    paddle = _box("paddle", (-0.5, 0, 0.1))
    paddle.pop("mass")
    paddle["kind"] = "kinematic"
    xs = np.linspace(-0.5, 0.3, T)
    paddle["trajectory"] = {"positions": [[x, 0, 0.1] for x in xs], "orientations": [[1, 0, 0, 0]] * T}
    sim = px.simulate(px.compile(scene("push", [_ground(), paddle, _box("box", (0.0, 0, 0.1))], (T - 1) / 250)))
    np.testing.assert_allclose(sim.poses["paddle"][:, 0], xs)
    assert sim.poses["box"][-1, 0] > 0.45
    native = px.compile(example_ir)
    with pytest.raises(Exception, match="static"):
        px.simulate(native, kinematic={"ground": np.zeros((72, 7))})
    with pytest.raises(ValueError, match="must be"):
        px.simulate(native, kinematic={"box": np.zeros((10, 7))})


def test_runs_are_deterministic(px):
    from vw.benchmark.runner import consistency_scenes

    ir = consistency_scenes()["tumble"]
    a, b = px.simulate(px.compile(ir)), px.simulate(px.compile(ir))
    for bid in a.poses:
        np.testing.assert_array_equal(a.poses[bid], b.poses[bid])
