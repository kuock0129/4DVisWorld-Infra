import copy

import numpy as np
import pytest

from vw import registry
from vw.ir import SceneIR
from vw.physics import (
    BackendInfo,
    Device,
    Feature,
    PhysicsAdapter,
    SimResult,
    UnsupportedSceneError,
    required_features,
)


def _trace_ir(example_dict) -> SceneIR:
    """Trace-level version of the example: box and support follow straight-line trajectories."""
    d = copy.deepcopy(example_dict)
    d["level"] = "trace"
    T = d["timing"]["frames"]
    for b in d["bodies"][1:]:
        z0 = b["initial_pose"]["position"][2]
        b["trajectory"] = {
            "positions": [[0.0, 0.01 * t, z0] for t in range(T)],
            "orientations": [[1.0, 0.0, 0.0, 0.0]] * T,
        }
    return SceneIR.model_validate(d)


def test_registry_lists_builtin_backends():
    assert {"mujoco", "newton", "physx", "bullet_blender", "replay"} <= set(registry.physics_backends())
    assert {"blender_cycles", "blender_eevee"} <= set(registry.render_backends())


def test_adapters_satisfy_protocol():
    for name in ["mujoco", "physx", "bullet_blender", "replay"]:
        assert isinstance(registry.get_physics(name, device="cpu"), PhysicsAdapter)


def test_required_features(example_ir):
    assert required_features(example_ir) == {Feature.RIGID}


def test_compatible_physics_routes_example(example_ir):
    res = registry.compatible_physics(example_ir, device="auto")
    assert res["mujoco"] == []
    assert res["physx"] == []
    assert res["replay"] == ["unsupported feature: rigid"]
    assert "no usable device" in res["newton"][0]  # CUDA-only, CPU-only machine (VW_DEVICES=cpu)


def test_device_resolution(monkeypatch):
    monkeypatch.setenv("VW_DEVICES", "cuda,cpu")
    assert registry.get_physics("physx", device="auto").device is Device.CUDA
    assert registry.get_physics("physx", device="cpu").device is Device.CPU
    assert registry.get_physics("newton", device="gpu").device is Device.CUDA
    with pytest.raises(RuntimeError, match="no usable device"):
        registry.get_physics("mujoco", device="gpu")


def test_unknown_backend():
    with pytest.raises(KeyError, match="unknown physics backend"):
        registry.get_physics("havok")


def test_stub_simulate_is_explicit(example_ir):
    mj = registry.get_physics("mujoco")
    with pytest.raises(NotImplementedError, match="stub"):
        mj.simulate(mj.compile(example_ir))
    with pytest.raises(NotImplementedError, match="stub"):
        registry.get_physics("physx").compile(example_ir)


def test_compile_refuses_unsupported_loudly(example_ir):
    replay = registry.get_physics("replay")
    with pytest.raises(UnsupportedSceneError, match="rigid"):
        replay.compile(example_ir)


def test_param_map_documents_approximations():
    pm = registry.get_physics("mujoco").param_map()
    assert "material.restitution" in pm and "note" in pm["material.restitution"]


def test_replay_trace_scene(example_dict):
    ir = _trace_ir(example_dict)
    replay = registry.get_physics("replay")
    assert replay.check(ir) == []
    sim = replay.simulate(replay.compile(ir))
    assert sim.num_frames == ir.timing.frames
    assert sim.poses["ground"].shape == (72, 7)
    np.testing.assert_allclose(sim.poses["ground"][:, :3], 0.0)  # static stays put
    np.testing.assert_allclose(sim.velocities["box"][:, 1], 0.01 * ir.timing.fps)  # dy/dt
    assert sim.backend.name == "replay"


def test_replay_kinematic_override(example_dict):
    ir = _trace_ir(example_dict)
    replay = registry.get_physics("replay")
    held = np.tile([0, 0, 1.0, 1, 0, 0, 0], (72, 1))
    sim = replay.simulate(replay.compile(ir), kinematic={"box": held})
    np.testing.assert_allclose(sim.poses["box"], held)
    with pytest.raises(ValueError, match="must be"):
        replay.simulate(replay.compile(ir), kinematic={"box": held[:10]})


def _info():
    return BackendInfo("x", "0", Device.CPU)


def test_simresult_validates_shapes():
    ok = SimResult(24, {"a": np.zeros((5, 7))}, {"a": np.zeros((5, 6))}, [], _info())
    assert ok.num_frames == 5
    with pytest.raises(ValueError, match=r"\(T, 7\)"):
        SimResult(24, {"a": np.zeros((5, 6))}, {}, [], _info())
    with pytest.raises(ValueError, match=r"\(T, 6\)"):
        SimResult(24, {"a": np.zeros((5, 7))}, {"a": np.zeros((4, 6))}, [], _info())
    with pytest.raises(ValueError, match="share T"):
        SimResult(24, {"a": np.zeros((5, 7)), "b": np.zeros((6, 7))}, {}, [], _info())
    with pytest.raises(ValueError, match="no matching poses"):
        SimResult(24, {"a": np.zeros((5, 7))}, {"b": np.zeros((5, 6))}, [], _info())


def test_render_stub_checks_passes(example_ir):
    eevee = registry.get_render("blender_eevee", seed=7)
    sim = SimResult(24, {"box": np.zeros((72, 7))}, {}, [], _info())
    with pytest.raises(ValueError, match="unsupported pass: flow"):
        eevee.render(example_ir, sim, ["rgb", "flow"], out=None)
    with pytest.raises(NotImplementedError):
        eevee.render(example_ir, sim, ["rgb", "instance_seg"], out=None)
    assert eevee.backend_info().seed == 7
