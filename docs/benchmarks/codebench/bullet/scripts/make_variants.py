"""Diagnostic IR variants (written next to this script; the shared examples/ files are untouched).

* B_03_fixgutter.json: the gutters rebuilt from the original mesh profile. convert.py chunks the
  40-vertex gutter meshes into groups of 8 and fits an OBB to each, which turns the half-pipe into
  solid blocks that rise above the lane and overlap the corner pins. Here each profile edge of the
  extruded gutter becomes a 1 cm slab lying inside the solid, so its outer face is the true surface. The two arc segments that
  meet the lane edge are skipped (the solid is thinner than 1 cm there); this leaves a < 1 cm notch.
* B_03_fixgutter_damp.json: as above plus the original pin damping (linear 0.05, angular 0.15).
* B_03_damp.json: the shipped (regenerated) B_03.json plus the original pin damping.
* B_01_damp.json: the original plank damping (0.05 / 0.1) and ball damping (0.02 / 0.05).
"""
import copy
import importlib.util
import json
from pathlib import Path

import numpy as np

from vw.ir import SceneIR

REPO = Path("C:/Users/kuock/source/repos/4DVisWorld-Infra")
ORIG = Path("C:/Users/kuock/source/repos/4DCodeBench/outputs/2026-11-05/opus-5.5")
OUT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("convert", REPO / "examples/codebench/convert.py")
convert = importlib.util.module_from_spec(spec)
spec.loader.exec_module(convert)

T = 0.01  # slab thickness


def gutter_slabs(name, v, mat):
    x0, x1 = v[:, 0].min(), v[:, 0].max()
    prof = v[np.isclose(v[:, 0], x0)][:, 1:]  # (y, z) profile, polygon order as stored
    area = 0.5 * np.sum(prof[:, 0] * np.roll(prof[:, 1], -1) - np.roll(prof[:, 0], -1) * prof[:, 1])
    out = []
    for i in range(len(prof)):
        a, b = prof[i], prof[(i + 1) % len(prof)]
        e = b - a
        L = float(np.linalg.norm(e))
        if L < 1e-6:
            continue
        t = e / L
        n_in = np.array([-t[1], t[0]]) * (1 if area > 0 else -1)  # inward normal in (y, z)
        c_yz = (a + b) / 2 + n_in * T / 2
        corners = [c_yz + su * t * L / 2 + sv * n_in * T / 2 for su in (-1, 1) for sv in (-1, 1)]
        if min(abs(c[0]) for c in corners) < 0.527 - 1e-4:
            continue  # arc segment next to the lane edge: a 1 cm slab would poke into the lane, so skip it
        ax = np.array([1.0, 0, 0]); ay = np.array([0, t[0], t[1]]); az = np.cross(ax, ay)
        R = np.column_stack([ax, ay, az])
        out.append({"id": f"{name}_s{i:02d}", "kind": "static",
                    "geometry": {"type": "box", "extents": [round(float(x1 - x0), 6), round(L, 6), T]},
                    "initial_pose": {"position": [round(float((x0 + x1) / 2), 6), round(float(c_yz[0]), 6),
                                                  round(float(c_yz[1]), 6)], "orientation": convert.mat_to_quat(R)},
                    "material": mat})
    return out


def main():
    b03 = json.loads((REPO / "examples/codebench/B_03.json").read_text())
    ids = json.loads((ORIG / "B_03/sim/baseline/build_log.json").read_text())["ids"]
    world = ORIG / "B_03/sim/baseline/world"
    mat = next(b["material"] for b in b03["bodies"] if b["id"] == "lane")
    bodies = [b for b in b03["bodies"] if not b["id"].startswith("gutter")]
    for g in ("gutter_L", "gutter_R"):
        bodies += gutter_slabs(g, convert.mesh0(world, ids[g]), mat)
    fix = {**b03, "bodies": bodies}
    fix["metadata"] = {**b03["metadata"], "variant": "gutters rebuilt as profile slabs (bullet/scripts/make_variants.py)"}
    damp = copy.deepcopy(fix)
    for b in damp["bodies"]:
        if b["id"].startswith("pin_"):
            b["linear_damping"], b["angular_damping"] = 0.05, 0.15
    damp["metadata"]["variant"] += " + original pin damping 0.05/0.15"

    b01 = json.loads((REPO / "examples/codebench/B_01.json").read_text())
    for b in b01["bodies"]:
        if b["kind"] == "dynamic":
            b["linear_damping"], b["angular_damping"] = (0.02, 0.05) if b["id"] == "ball" else (0.05, 0.1)
    b01["metadata"] = {**b01["metadata"], "variant": "original damping restored (bullet/scripts/make_variants.py)"}

    b03d = copy.deepcopy(b03)  # the regenerated shipped file (gutters fixed upstream) + pin damping
    for b in b03d["bodies"]:
        if b["id"].startswith("pin_"):
            b["linear_damping"], b["angular_damping"] = 0.05, 0.15
    b03d["metadata"] = {**b03["metadata"], "variant": "original pin damping 0.05/0.15 (bullet/scripts/make_variants.py)"}

    for fname, d in (("B_03_damp.json", b03d), ("B_03_fixgutter.json", fix), ("B_03_fixgutter_damp.json", damp), ("B_01_damp.json", b01)):
        p = OUT / fname
        p.write_text(json.dumps(d, indent=1))
        SceneIR.load(p)  # validates
        print("wrote", p)


if __name__ == "__main__":
    main()
