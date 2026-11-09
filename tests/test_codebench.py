from pathlib import Path

import numpy as np
import pytest

from vw.ir import SceneIR

CB = Path(__file__).resolve().parents[1] / "examples" / "codebench"


@pytest.mark.parametrize("case,n_dynamic,frames", [("B_01", 48, 105), ("B_03", 11, 130)])
def test_codebench_ir_is_valid(case, n_dynamic, frames):
    ir = SceneIR.load(CB / f"{case}.json")
    assert sum(b.kind.value == "dynamic" for b in ir.bodies) == n_dynamic and ir.timing.frames == frames
    ball = ir.body("ball")
    v, w, r = np.array(ball.initial_linear_velocity), np.array(ball.initial_angular_velocity), ball.geometry.radius
    np.testing.assert_allclose(np.cross(w, [0, 0, -r]) + v, 0, atol=1e-4)  # rolling without slipping


def test_run_tuple_on_mujoco(tmp_path):
    pytest.importorskip("mujoco")
    from vw import registry
    from vw.benchmark.codebench import run_tuple, save

    ir = SceneIR.load(CB / "B_03.json")
    res, sims = run_tuple(registry.get_physics("mujoco", device="cpu"), ir)
    assert res["checks"]["noncausal_replays_baseline"] and res["checks"]["noncausal_max_diff"] == 0.0
    assert res["baseline"]["moved"] >= 5 and res["checks"]["causal_diverges_from_baseline"] >= 5
    assert set(sims) == {"baseline", "causal", "noncausal"} and "ball" not in sims["causal"].poses
    paths = save(res, sims, tmp_path)
    assert paths[0].exists() and "baseline/pin_A1" in np.load(paths[1]).files
