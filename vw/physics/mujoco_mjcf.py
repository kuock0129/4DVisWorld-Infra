"""Scene IR -> MJCF. Pure XML generation; does not import mujoco.

Conventions handled here (and only here):
* IR box / plane ``extents`` are full lengths; MJCF ``size`` is half-sizes -> divide by 2.
* IR cylinder / capsule ``height`` is full length; MJCF second size is half-length -> divide by 2.
* Quaternions are (w, x, y, z) in both IR and MJCF; no reordering.
* Static bodies become world geoms, dynamic bodies get a free joint, kinematic bodies
  become ``mocap`` bodies whose pose simulate() sets every step.
* Restitution e -> per-geom ``solref = (timeconst, dampratio)`` with the damped-oscillator
  relation  zeta = -ln(e) / sqrt(pi^2 + ln(e)^2)  (e=0 -> critically damped, zeta=1).
  This is an approximation of MuJoCo's soft-contact model; M2 benchmarks measure its error.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any

from vw.ir import Body, BodyKind, Box, Capsule, Cylinder, Mesh, Plane, SceneIR, Sphere

# MuJoCo's plane third size is the grid spacing for rendering only.
_PLANE_GRID = 0.1
_MIN_DAMPRATIO = 1e-3  # e -> 1 would give zeta -> 0 (undamped); keep strictly positive


def _f(vals) -> str:
    return " ".join(f"{float(v):.9g}" for v in vals)


def restitution_to_dampratio(e: float) -> float:
    if e <= 0.0:
        return 1.0
    if e >= 1.0:
        return _MIN_DAMPRATIO
    ln = math.log(e)
    return max(-ln / math.sqrt(math.pi**2 + ln**2), _MIN_DAMPRATIO)


def restitution_solref(e: float, timeconst: float) -> tuple[float, float]:
    """(timeconst', dampratio) for restitution ``e`` at constant contact stiffness.

    MuJoCo: b = 2 / (dmax tc), k = d / (dmax^2 tc^2 zeta^2). Holding tc fixed while
    lowering zeta makes k (stiffness) blow up and explicit integration diverge. Using
    tc' = tc / zeta keeps k = d / (dmax tc)^2 fixed and scales only the damping.
    """
    zeta = restitution_to_dampratio(e)
    return timeconst / zeta, zeta


@dataclass
class MJCFScene:
    xml: str
    ir: SceneIR
    timestep: float
    options: dict[str, Any] = field(default_factory=dict)
    mocap_bodies: list[str] = field(default_factory=list)  # kinematic body ids, in MJCF order
    free_bodies: list[str] = field(default_factory=list)  # dynamic body ids, in MJCF order


def _geom_attrs(body: Body, mesh_name: str | None, timeconst: float) -> dict[str, str]:
    g = body.geometry
    a: dict[str, str] = {"name": body.id}
    if isinstance(g, Box):
        a.update(type="box", size=_f(e / 2 for e in g.extents))
    elif isinstance(g, Plane):
        a.update(type="plane", size=_f([g.extents[0] / 2, g.extents[1] / 2, _PLANE_GRID]))
    elif isinstance(g, Sphere):
        a.update(type="sphere", size=_f([g.radius]))
    elif isinstance(g, Cylinder):
        a.update(type="cylinder", size=_f([g.radius, g.height / 2]))
    elif isinstance(g, Capsule):
        a.update(type="capsule", size=_f([g.radius, g.height / 2]))
    elif isinstance(g, Mesh):
        a.update(type="mesh", mesh=mesh_name or body.id)
    else:  # pragma: no cover - guarded by the IR's discriminated union
        raise TypeError(f"unhandled geometry {type(g).__name__}")
    # Sliding friction only; torsional / rolling keep MuJoCo defaults (see param_map).
    a["friction"] = _f([body.material.friction, 0.005, 0.0001])
    a["solref"] = _f(restitution_solref(body.material.restitution, timeconst))
    if body.kind is BodyKind.DYNAMIC and body.mass is not None:
        a["mass"] = _f([body.mass])
    if body.appearance.color is not None:
        a["rgba"] = _f([*body.appearance.color, 1.0])
    return a


def ir_to_mjcf(
    ir: SceneIR,
    timestep: float = 0.002,
    options: dict[str, Any] | None = None,
    contact_timeconst: float | None = None,
) -> MJCFScene:
    """``options`` are extra ``<option>`` attributes (integrator, solver, iterations, cone, ...).

    ``contact_timeconst`` defaults to max(0.02, 2 * timestep): MuJoCo needs timeconst >= 2 dt.
    """
    options = dict(options or {})
    timeconst = contact_timeconst if contact_timeconst is not None else max(0.02, 2.0 * timestep)

    root = ET.Element("mujoco", model=str(ir.metadata.get("name", "vw_scene")))
    ET.SubElement(root, "compiler", angle="radian")
    ET.SubElement(
        root, "option", timestep=_f([timestep]), gravity=_f(ir.gravity), **{k: str(v) for k, v in options.items()}
    )

    meshes = [b for b in ir.bodies if isinstance(b.geometry, Mesh)]
    if meshes:
        asset = ET.SubElement(root, "asset")
        for b in meshes:
            g = b.geometry
            ET.SubElement(asset, "mesh", name=b.id, file=g.collision_path or g.path, scale=_f(g.scale))

    world = ET.SubElement(root, "worldbody")
    scene = MJCFScene(xml="", ir=ir, timestep=timestep, options={**options, "contact_timeconst": timeconst})
    for b in ir.bodies:
        pos, quat = _f(b.initial_pose.position), _f(b.initial_pose.orientation)
        if b.kind is BodyKind.STATIC:
            ET.SubElement(world, "geom", pos=pos, quat=quat, **_geom_attrs(b, b.id, timeconst))
            continue
        attrs = {"name": b.id, "pos": pos, "quat": quat}
        if b.kind is BodyKind.KINEMATIC:
            attrs["mocap"] = "true"
            scene.mocap_bodies.append(b.id)
        body_el = ET.SubElement(world, "body", **attrs)
        if b.kind is BodyKind.DYNAMIC:
            joint = {"type": "free", "name": f"{b.id}__free"}
            if b.linear_damping or b.angular_damping:
                # MuJoCo has one damping value per joint; use the larger (approximation, see param_map).
                joint["damping"] = _f([max(b.linear_damping, b.angular_damping)])
            ET.SubElement(body_el, "joint", **joint)
            scene.free_bodies.append(b.id)
        ET.SubElement(body_el, "geom", **_geom_attrs(b, b.id, timeconst))

    for c in ir.cameras:
        ET.SubElement(
            world, "camera", name=c.id, pos=_f(c.pose.position), quat=_f(c.pose.orientation), fovy=_f([c.fov_deg])
        )

    ET.indent(root)
    scene.xml = ET.tostring(root, encoding="unicode")
    return scene
