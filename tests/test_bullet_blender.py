import math

import numpy as np
import pytest

from vw import registry
from vw.interventions import remove
from vw.physics.bullet_blender import find_blender
from vw.physics.util import finite_diff_velocities, quat_from_rotvec, quat_mul


def test_finite_diff_velocities_recovers_constant_motion():
    fps, T = 50, 20
    t = np.arange(T) / fps
    w = np.array([0.0, 0.0, 3.0])
    poses = np.zeros((T, 7))
    poses[:, :3] = np.outer(t, [1.0, -2.0, 0.5])
    poses[:, 3:] = [quat_mul(quat_from_rotvec(w * ti), [0.7071068, 0.7071068, 0, 0]) for ti in t]
    v = finite_diff_velocities(poses, fps)
    np.testing.assert_allclose(v[:, :3], np.tile([1.0, -2.0, 0.5], (T, 1)), atol=1e-9)
    np.testing.assert_allclose(v[:, 3:], np.tile(w, (T, 1)), atol=1e-6)


def test_check_reports_missing_blender(monkeypatch, example_ir):
    monkeypatch.setattr("vw.physics.bullet_blender.find_blender", lambda explicit=None: None)
    a = registry.get_physics("bullet_blender", device="cpu")
    assert any("blender executable not found" in p for p in a.check(example_ir))
    assert a.version == "not-installed"


# --- simulation (needs a Blender install) ----------------------------------------------

pytestmark_blender = pytest.mark.skipif(find_blender() is None, reason="Blender not installed")


@pytest.fixture
def bt():
    return registry.get_physics("bullet_blender", device="cpu")


@pytestmark_blender
def test_remove_support_tuple(bt, example_ir):
    base = bt.simulate(bt.compile(example_ir))
    cf = remove(example_ir, ["support"])
    causal = bt.simulate(bt.compile(cf))
    noncausal = bt.simulate(bt.compile(cf), kinematic={"box": base.poses["box"]})

    assert base.num_frames == example_ir.timing.frames and set(base.poses) == {"ground", "support", "box"}
    assert np.abs(base.poses["box"][:, :3] - base.poses["box"][0, :3]).max() < 1e-3
    assert causal.poses["box"][-1, 2] == pytest.approx(0.1, abs=2e-3)
    np.testing.assert_allclose(noncausal.poses["box"], base.poses["box"])
    z = causal.poses["box"][:, 2]
    t_hit = int(np.argmax(z < 0.1 + 2e-3)) / example_ir.timing.fps
    assert t_hit == pytest.approx(math.sqrt(2 * 0.4 / 9.81), abs=1.5 / example_ir.timing.fps)
    cfg = base.backend.solver_config
    assert base.backend.name == "bullet_blender" and cfg["substeps"] == 21 and cfg["sim_wall_s"] > 0
    assert base.contacts == []


@pytestmark_blender
def test_initial_velocity_and_friction(bt):
    from vw.benchmark.analytic import collision, slide

    rs = {r.metric: r for r in slide(bt, frictions=(0.5,)) + collision(bt, restitutions=(1.0,))}
    assert rs["stopping distance (mu=0.5)"].rel_err < 0.02  # pre-roll imparts v0, sqrt(mu) mapping
    assert rs["momentum after (e=1.0)"].abs_err < 1e-3


@pytestmark_blender
def test_kinematic_body_pushes_dynamic_box(bt):
    from vw.benchmark.analytic import _box, _ground, scene

    T = 101
    paddle = _box("paddle", (-0.5, 0, 0.1))
    paddle.pop("mass")
    paddle["kind"] = "kinematic"
    xs = np.linspace(-0.5, 0.3, T)
    paddle["trajectory"] = {"positions": [[x, 0, 0.1] for x in xs], "orientations": [[1, 0, 0, 0]] * T}
    ir = scene("push", [_ground(), paddle, _box("box", (0.0, 0, 0.1))], (T - 1) / 250)
    sim = bt.simulate(bt.compile(ir))
    np.testing.assert_allclose(sim.poses["paddle"][:, 0], xs, atol=1e-5)
    assert sim.poses["box"][-1, 0] > 0.45  # pushed ahead of the paddle (0.3 + one box width)
