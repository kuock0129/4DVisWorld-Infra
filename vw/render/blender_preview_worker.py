"""Runs INSIDE Blender: renders simulated poses to an mp4 preview.

``blender --background --python blender_preview_worker.py -- job.json``

job = {"ir": <SceneIR dict>, "fps": int, "resolution": [w, h], "engine": "EEVEE" | "WORKBENCH",
       "members": [{"label": str, "out": path.mp4, "poses": {body_id: [[x,y,z,qw,qx,qy,qz], ...]}}]}

Bodies missing from a member's poses (e.g. the removed target) are not created. The camera
is the IR's first camera (looks along local -Z, +Y up, same convention as Blender).
Preview only: simple materials, one sun, no motion blur.
"""

import hashlib
import json
import math
import sys

import bpy
from mathutils import Quaternion, Vector


def _clear():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for m in list(bpy.data.materials):
        bpy.data.materials.remove(m)


def _color(body):
    app = body.get("appearance") or {}
    if app.get("color"):
        return tuple(app["color"]) + (1.0,)
    bid = body["id"]
    if body["kind"] == "static":
        return (0.55, 0.55, 0.55, 1.0)
    if bid == "ball":
        return (0.10, 0.25, 0.85, 1.0)
    if bid.startswith("pin"):
        return (0.92, 0.92, 0.90, 1.0)
    h = int(hashlib.md5(bid.encode()).hexdigest()[:6], 16)
    return (0.75 + 0.2 * ((h >> 16) & 255) / 255, 0.55 + 0.2 * ((h >> 8) & 255) / 255, 0.25 + 0.15 * (h & 255) / 255, 1.0)


def _material(body):
    mat = bpy.data.materials.new(body["id"])
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    c = _color(body)
    bsdf.inputs["Base Color"].default_value = c
    bsdf.inputs["Roughness"].default_value = 0.6
    mat.diffuse_color = c  # used by Workbench
    return mat


def _add(body):
    g = body["geometry"]
    t = g["type"]
    if t == "box":
        bpy.ops.mesh.primitive_cube_add(size=1.0)
        ob = bpy.context.object
        ob.scale = tuple(g["extents"])
    elif t == "sphere":
        bpy.ops.mesh.primitive_uv_sphere_add(radius=g["radius"], segments=32, ring_count=16)
        ob = bpy.context.object
        bpy.ops.object.shade_smooth()
    elif t == "cylinder":
        bpy.ops.mesh.primitive_cylinder_add(radius=g["radius"], depth=g["height"], vertices=32)
        ob = bpy.context.object
    elif t == "capsule":
        bpy.ops.mesh.primitive_cylinder_add(radius=g["radius"], depth=g["height"] + 2 * g["radius"], vertices=32)
        ob = bpy.context.object
    elif t == "plane":
        bpy.ops.mesh.primitive_plane_add(size=1.0)
        ob = bpy.context.object
        ob.scale = (max(g["extents"][0], 20.0), max(g["extents"][1], 20.0), 1.0)
    else:
        return None
    ob.name = body["id"]
    ob.rotation_mode = "QUATERNION"
    ob.data.materials.append(_material(body))
    return ob


def _camera(ir, res):
    cam = ir["cameras"][0]
    bpy.ops.object.camera_add()
    ob = bpy.context.object
    ob.location = Vector(cam["pose"]["position"])
    ob.rotation_mode = "QUATERNION"
    ob.rotation_quaternion = Quaternion(cam["pose"]["orientation"])
    ob.data.sensor_fit = "VERTICAL"
    ob.data.angle_y = math.radians(cam.get("fov_deg", 50.0))
    ob.data.clip_end = 200.0
    bpy.context.scene.camera = ob


def _render_member(ir, member, fps, res, engine):
    _clear()
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE" if engine == "EEVEE" else "BLENDER_WORKBENCH"
    if engine != "EEVEE":
        sc.display.shading.light = "STUDIO"
        sc.display.shading.color_type = "MATERIAL"
        sc.display.shading.show_shadows = True
    else:
        sc.eevee.use_soft_shadows = True
        sc.eevee.taa_render_samples = 16
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.fps, sc.render.fps_base = fps, 1.0
    world = sc.world or bpy.data.worlds.new("World")
    sc.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.32, 0.34, 0.38, 1.0)
    world.node_tree.nodes["Background"].inputs[1].default_value = 0.6
    bpy.ops.object.light_add(type="SUN", rotation=(math.radians(40), math.radians(10), math.radians(-30)))
    bpy.context.object.data.energy = 3.0

    poses = member["poses"]
    T = len(next(iter(poses.values())))
    for body in ir["bodies"]:
        if body["id"] not in poses:
            continue
        ob = _add(body)
        if ob is None:
            continue
        track = poses[body["id"]]
        moving = any(abs(track[k][i] - track[0][i]) > 1e-9 for k in range(T) for i in range(7))
        for k, row in enumerate(track if moving else track[:1]):
            ob.location = Vector(row[:3])
            ob.rotation_quaternion = Quaternion(row[3:])
            ob.keyframe_insert("location", frame=k + 1)
            ob.keyframe_insert("rotation_quaternion", frame=k + 1)
    _camera(ir, res)

    sc.frame_start, sc.frame_end = 1, T
    sc.render.use_stamp = True
    for flag in ("date", "time", "render_time", "frame", "frame_range", "memory", "hostname", "camera",
                 "lens", "scene", "marker", "filename", "sequencer_strip"):
        setattr(sc.render, f"use_stamp_{flag}", False)
    sc.render.use_stamp_note = True
    sc.render.stamp_note_text = member["label"]
    sc.render.stamp_font_size = max(14, res[1] // 22)
    sc.render.image_settings.file_format = "FFMPEG"
    sc.render.ffmpeg.format = "MPEG4"
    sc.render.ffmpeg.codec = "H264"
    sc.render.ffmpeg.constant_rate_factor = "MEDIUM"
    sc.render.filepath = member["out"]
    bpy.ops.render.render(animation=True)


def main():
    job = json.load(open(sys.argv[sys.argv.index("--") + 1], encoding="utf-8"))
    for member in job["members"]:
        _render_member(job["ir"], member, job["fps"], job["resolution"], job.get("engine", "EEVEE"))
        print("RENDERED", member["out"])


if __name__ == "__main__":
    main()
