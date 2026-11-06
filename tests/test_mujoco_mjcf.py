import copy
import xml.etree.ElementTree as ET

import pytest

from vw import registry
from vw.interventions import remove
from vw.ir import SceneIR


def _compile(ir: SceneIR):
    scene = registry.get_physics("mujoco").compile(ir)
    return scene, ET.fromstring(scene.xml)


def _geom(root, name):
    g = root.find(f".//geom[@name='{name}']")
    assert g is not None, f"no geom '{name}' in MJCF"
    return g


def _size(el):
    return [float(v) for v in el.get("size").split()]


def test_box_half_size_is_half_extents(example_ir):
    _, root = _compile(example_ir)
    for bid in ("support", "box"):
        extents = example_ir.body(bid).geometry.extents
        assert _size(_geom(root, bid)) == pytest.approx([e / 2 for e in extents])


def test_non_cubic_box_axes_not_swapped(example_dict):
    d = copy.deepcopy(example_dict)
    d["bodies"][2]["geometry"]["extents"] = [0.1, 0.3, 0.5]
    _, root = _compile(SceneIR.model_validate(d))
    assert _size(_geom(root, "box")) == pytest.approx([0.05, 0.15, 0.25])


def test_plane_and_round_shapes(example_dict):
    d = copy.deepcopy(example_dict)
    d["bodies"][1]["geometry"] = {"type": "cylinder", "radius": 0.1, "height": 0.4}
    d["bodies"][2]["geometry"] = {"type": "capsule", "radius": 0.05, "height": 0.2}
    _, root = _compile(SceneIR.model_validate(d))
    assert _size(_geom(root, "ground"))[:2] == pytest.approx([2.0, 2.0])
    assert _size(_geom(root, "support")) == pytest.approx([0.1, 0.2])
    assert _size(_geom(root, "box")) == pytest.approx([0.05, 0.1])


def test_body_structure_and_params(example_ir):
    scene, root = _compile(example_ir)
    world = root.find("worldbody")
    assert world.find("geom[@name='ground']") is not None  # static -> world geom
    box_body = world.find("body[@name='box']")
    assert box_body.find("joint").get("type") == "free"
    assert float(_geom(root, "box").get("mass")) == pytest.approx(1.0)
    assert float(_geom(root, "box").get("friction").split()[0]) == pytest.approx(0.6)
    assert [float(v) for v in root.find("option").get("gravity").split()] == pytest.approx([0, 0, -9.81])
    assert scene.free_bodies == ["support", "box"] and scene.mocap_bodies == []


def test_kinematic_body_is_mocap(example_dict):
    d = copy.deepcopy(example_dict)
    T = d["timing"]["frames"]
    d["bodies"][2]["kind"] = "kinematic"
    d["bodies"][2]["trajectory"] = {"positions": [[0, 0, 0.5]] * T, "orientations": [[1, 0, 0, 0]] * T}
    scene, root = _compile(SceneIR.model_validate(d))
    body = root.find(".//body[@name='box']")
    assert body.get("mocap") == "true" and body.find("joint") is None
    assert scene.mocap_bodies == ["box"]


def test_remove_deletes_body_and_collider(example_ir):
    after = remove(example_ir, ["support"])
    assert [b.id for b in after.bodies] == ["ground", "box"]
    assert [b.id for b in example_ir.bodies] == ["ground", "support", "box"]  # input untouched
    assert after.metadata["interventions"] == [{"type": "remove", "targets": ["support"]}]
    assert after.content_hash() != example_ir.content_hash()
    _, root = _compile(after)
    assert root.find(".//*[@name='support']") is None  # no body, no geom, no collider


def test_remove_unknown_target(example_ir):
    with pytest.raises(KeyError, match="unknown body"):
        remove(example_ir, ["nope"])
