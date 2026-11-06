import copy

import pytest
from pydantic import ValidationError

from vw.ir import BodyKind, Level, SceneIR


def test_example_validates(example_ir):
    assert example_ir.level is Level.PHYSICAL
    assert {b.id for b in example_ir.bodies} == {"ground", "support", "box"}
    assert example_ir.body("box").kind is BodyKind.DYNAMIC


def test_example_starts_in_contact(example_ir):
    """Box bottom sits exactly on support top; support bottom on the ground (rest at t=0)."""
    sup, box = example_ir.body("support"), example_ir.body("box")
    sup_top = sup.initial_pose.position[2] + sup.geometry.extents[2] / 2
    box_bottom = box.initial_pose.position[2] - box.geometry.extents[2] / 2
    assert sup.initial_pose.position[2] - sup.geometry.extents[2] / 2 == pytest.approx(0.0)
    assert box_bottom == pytest.approx(sup_top)


def test_hash_is_stable_and_roundtrips(example_ir, tmp_path):
    p = tmp_path / "s.json"
    example_ir.save(p)
    again = SceneIR.load(p)
    assert again.content_hash() == example_ir.content_hash()
    assert example_ir.content_hash().startswith("sha256:")


def test_hash_changes_with_content(example_dict):
    a = SceneIR.model_validate(example_dict)
    d = copy.deepcopy(example_dict)
    d["bodies"][2]["mass"] = 2.0
    assert SceneIR.model_validate(d).content_hash() != a.content_hash()


def _mutate(example_dict, fn):
    d = copy.deepcopy(example_dict)
    fn(d)
    return d


@pytest.mark.parametrize(
    "mutation, msg",
    [
        (lambda d: d["bodies"][1].pop("mass"), "need mass"),
        (lambda d: d["bodies"].append(copy.deepcopy(d["bodies"][1])), "duplicate ids"),
        (lambda d: d["bodies"][1].update(kind="kinematic"), "need a trajectory"),
        (lambda d: d["bodies"][1]["material"].update(restitution=1.5), "less than or equal to 1"),
        (lambda d: d["bodies"][1]["material"].update(friction=-0.1), "greater than or equal to 0"),
        (lambda d: d["bodies"][1]["geometry"].update(extents=[0.4, 0.4]), "extents"),
        (lambda d: d["bodies"][1]["geometry"].update(extents=[0.4, 0.0, 0.4]), "greater than 0"),
        (lambda d: d["bodies"][1]["geometry"].update(size=[0.4, 0.4, 0.4]), "Extra inputs are not permitted"),
        (lambda d: d["bodies"][1]["initial_pose"].update(orientation=[1, 1, 0, 0]), "unit length"),
        (lambda d: d["bodies"][1].update(substeps=10), "Extra inputs are not permitted"),
        (lambda d: d.update(ir_version="0.2"), "ir_version"),
        (lambda d: d.update(cameras=[]), "at least 1"),
        (lambda d: d.update(level="trace"), "need a trajectory at level=trace"),
    ],
    ids=[
        "dynamic-no-mass",
        "duplicate-id",
        "kinematic-no-trajectory",
        "restitution-range",
        "negative-friction",
        "box-extents-arity",
        "box-extents-positive",
        "legacy-size-field-rejected",
        "non-unit-quat",
        "solver-param-in-ir",
        "wrong-version",
        "no-camera",
        "trace-without-trajectories",
    ],
)
def test_invalid_scenes_rejected(example_dict, mutation, msg):
    with pytest.raises(ValidationError, match=msg):
        SceneIR.model_validate(_mutate(example_dict, mutation))


def test_trajectory_length_must_match_frames(example_dict):
    traj = {"positions": [[0, 0, 0.5]] * 10, "orientations": [[1, 0, 0, 0]] * 10}
    d = _mutate(example_dict, lambda d: d["bodies"][2].update(kind="kinematic", trajectory=traj))
    with pytest.raises(ValidationError, match="timing.frames"):
        SceneIR.model_validate(d)


def test_static_body_rejects_trajectory(example_dict):
    traj = {"positions": [[0, 0, 0]] * 72, "orientations": [[1, 0, 0, 0]] * 72}
    d = _mutate(example_dict, lambda d: d["bodies"][0].update(trajectory=traj))
    with pytest.raises(ValidationError, match="static bodies must not"):
        SceneIR.model_validate(d)
