import copy
import math

import numpy as np
import pytest

from vw import registry
from vw.interventions import remove
from vw.ir import SceneIR
from vw.physics.base import UnsupportedSceneError
from vw.physics.mujoco import effective_timestep
from vw.physics.mujoco_mjcf import restitution_solref, restitution_to_dampratio

# --- pure-python helpers (no mujoco needed) -------------------------------------------


def test_effective_timestep_divides_frame_period():
    dt, n = effective_timestep(0.002, 24)
    assert n == 21 and dt * n * 24 == pytest.approx(1.0) and dt <= 0.002
    assert effective_timestep(0.002, 250) == (pytest.approx(0.002), 2)
    assert effective_timestep(0.01, 250) == (pytest.approx(0.004), 1)


def test_restitution_mapping_keeps_stiffness_constant():
    assert restitution_to_dampratio(0.0) == 1.0
    assert restitution_to_dampratio(1.0) > 0
    for e in (0.1, 0.5, 0.9):
        z = restitution_to_dampratio(e)
        assert math.exp(-z * math.pi / math.sqrt(1 - z * z)) == pytest.approx(e)
        tc, zeta = restitution_solref(e, 0.02)
        # MuJoCo stiffness k ~ 1 / (tc * zeta)^2 must not depend on e.
        assert tc * zeta == pytest.approx(0.02)


# --- simulation (needs mujoco) ---------------------------------------------------------

mujoco = pytest.importorskip("mujoco")


@pytest.fixture
def mj():
    return registry.get_physics("mujoco", device="cpu")


def test_remove_support_tuple(mj, example_ir):
    base = mj.simulate(mj.compile(example_ir))
    cf = remove(example_ir, ["support"])
    causal = mj.simulate(mj.compile(cf))
    noncausal = mj.simulate(mj.compile(cf), kinematic={"box": base.poses["box"]})

    assert base.num_frames == example_ir.timing.frames
    assert set(base.poses) == {"ground", "support", "box"}
    # Baseline at rest, causal falls onto the ground, non-causal replays the baseline.
    assert np.abs(base.poses["box"][:, :3] - base.poses["box"][0, :3]).max() < 1e-3
    assert causal.poses["box"][-1, 2] == pytest.approx(0.1, abs=2e-3)
    np.testing.assert_allclose(noncausal.poses["box"], base.poses["box"])
    assert {frozenset((c.obj_a, c.obj_b)) for c in base.contacts} == {
        frozenset(("box", "support")), frozenset(("ground", "support"))}
    assert {frozenset((c.obj_a, c.obj_b)) for c in causal.contacts} == {frozenset(("box", "ground"))}
    assert noncausal.contacts == []
    # First box-ground contact within one frame of the analytic fall time.
    t_hit = min(c.t for c in causal.contacts)
    assert t_hit == pytest.approx(math.sqrt(2 * 0.4 / 9.81), abs=1.0 / example_ir.timing.fps)
    assert base.backend.name == "mujoco" and base.backend.solver_config["steps_per_frame"] == 21


def test_static_frames_and_quaternions(mj, example_ir):
    sim = mj.simulate(mj.compile(example_ir))
    np.testing.assert_allclose(sim.poses["ground"], np.tile([0, 0, 0, 1, 0, 0, 0], (72, 1)))
    np.testing.assert_allclose(np.linalg.norm(sim.poses["box"][:, 3:], axis=1), 1.0, atol=1e-9)


def test_initial_angular_velocity_is_world_frame(mj):
    from vw.benchmark.analytic import _sphere, scene

    ball = _sphere("ball", (0, 0, 0))
    ball["initial_pose"]["orientation"] = [0.7071068, 0.7071068, 0, 0]  # 90 deg about x
    ball["initial_angular_velocity"] = [0, 0, 2.0]  # world z
    ir = scene("spin", [ball], 0.2, gravity=(0, 0, 0))
    sim = mj.simulate(mj.compile(ir))
    np.testing.assert_allclose(sim.velocities["ball"][:, 3:], np.tile([0, 0, 2.0], (sim.num_frames, 1)), atol=1e-6)


def test_kinematic_ir_body_follows_trajectory(mj, example_dict):
    d = copy.deepcopy(example_dict)
    T = d["timing"]["frames"]
    xs = np.linspace(0, 1, T)
    d["bodies"][2]["kind"] = "kinematic"
    d["bodies"][2]["trajectory"] = {"positions": [[x, 0, 0.8] for x in xs], "orientations": [[1, 0, 0, 0]] * T}
    d["bodies"][2]["initial_pose"]["position"] = [0, 0, 0.8]
    sim = mj.simulate(mj.compile(SceneIR.model_validate(d)))
    np.testing.assert_allclose(sim.poses["box"][:, 0], xs)
    np.testing.assert_allclose(sim.velocities["box"][1:-1, 0], 1.0 * d["timing"]["fps"] / (T - 1), rtol=1e-6)


def test_override_errors(mj, example_ir):
    native = mj.compile(example_ir)
    with pytest.raises(UnsupportedSceneError, match="static"):
        mj.simulate(native, kinematic={"ground": np.zeros((72, 7))})
    with pytest.raises(ValueError, match="must be"):
        mj.simulate(native, kinematic={"box": np.zeros((10, 7))})
    with pytest.raises(KeyError):
        mj.simulate(native, kinematic={"nope": np.zeros((72, 7))})


def test_elastic_collision_is_stable(mj):
    from vw.benchmark.analytic import collision

    rs = {r.metric: r for r in collision(mj, restitutions=(1.0,))}
    assert rs["v_B after (e=1.0)"].rel_err < 0.01
    assert rs["momentum after (e=1.0)"].abs_err < 1e-4
