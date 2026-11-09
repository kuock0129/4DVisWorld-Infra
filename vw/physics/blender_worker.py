"""Runs INSIDE Blender (``blender --background --python blender_worker.py -- job.json``).

Builds a Bullet rigid-body world from a Scene IR dict, steps it frame by frame and
writes per-frame world poses to the output JSON named in the job. Uses only bpy,
mathutils and the standard library (Blender's Python has no pydantic, no vw).

Time mapping. IR frame k is Blender frame F0 + k. Bullet's step per Blender frame is
time_scale / scene_fps, so scene_fps = min(ir_fps, 120) and time_scale = scene_fps / ir_fps
make one Blender frame exactly one IR frame; substeps_per_frame sets the solver dt.

Initial velocities. Blender has no initial-velocity property. Every dynamic body is
driven as an animated (kinematic) body along its initial velocity for PRE frames
before F0 and released at F0; Bullet keeps the kinematic body's linear and angular
velocity on release. Bodies at rest are simply held in place during the pre-roll.
"""

import json
import math
import sys
import time

import bpy
from mathutils import Quaternion, Vector

PRE = 2  # pre-roll frames (release needs at least two kinematic steps)
PLANE_SIZE = 200.0  # collision planes become a thick box this wide (IR planes are infinite)
PLANE_THICKNESS = 1.0


def _clear_scene():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)


def _add_object(body):
    g = body["geometry"]
    t = g["type"]
    if t == "box":
        bpy.ops.mesh.primitive_cube_add(size=1.0)
        ob = bpy.context.object
        ob.scale = tuple(g["extents"])
        shape = "BOX"
    elif t == "sphere":
        bpy.ops.mesh.primitive_uv_sphere_add(radius=g["radius"], segments=24, ring_count=12)
        ob, shape = bpy.context.object, "SPHERE"
    elif t == "cylinder":
        bpy.ops.mesh.primitive_cylinder_add(radius=g["radius"], depth=g["height"], vertices=32)
        ob, shape = bpy.context.object, "CYLINDER"
    elif t == "capsule":
        # Blender's capsule: radius = max(dim_x, dim_y) / 2, cylinder part = dim_z - 2 * radius.
        bpy.ops.mesh.primitive_cylinder_add(radius=g["radius"], depth=g["height"] + 2 * g["radius"], vertices=32)
        ob, shape = bpy.context.object, "CAPSULE"
    elif t == "plane":
        bpy.ops.mesh.primitive_cube_add(size=1.0)
        ob = bpy.context.object
        ob.scale = (PLANE_SIZE, PLANE_SIZE, PLANE_THICKNESS)
        shape = "BOX"
    else:
        raise ValueError("unsupported geometry type in blender worker: " + t)
    ob.name = body["id"]
    ob.rotation_mode = "QUATERNION"
    return ob, shape


def _set_pose(ob, body, pos, quat):
    q = Quaternion(quat)
    p = Vector(pos)
    if body["geometry"]["type"] == "plane":
        # The box's top face is the plane: shift the centre down along the plane normal.
        p = p + q @ Vector((0.0, 0.0, -PLANE_THICKNESS / 2))
    ob.location = p
    ob.rotation_quaternion = q


def _key(ob, frame):
    ob.keyframe_insert("location", frame=frame)
    ob.keyframe_insert("rotation_quaternion", frame=frame)


def _linear_keys(ob):
    ad = ob.animation_data
    if ad and ad.action:
        for fc in ad.action.fcurves:
            for k in fc.keyframe_points:
                k.interpolation = "LINEAR"


def main():
    job_path = sys.argv[sys.argv.index("--") + 1]
    with open(job_path, encoding="utf-8") as f:
        job = json.load(f)
    ir, cfg, overrides = job["ir"], job["config"], job.get("overrides", {})
    fps, T = ir["timing"]["fps"], ir["timing"]["frames"]
    F0 = 1 + PRE

    _clear_scene()
    sc = bpy.context.scene
    sc.use_gravity = True
    sc.gravity = tuple(ir["gravity"])
    bpy.ops.rigidbody.world_add()
    rbw = sc.rigidbody_world
    scene_fps = min(fps, 120)
    sc.render.fps, sc.render.fps_base = scene_fps, 1.0
    rbw.time_scale = scene_fps / fps
    rbw.substeps_per_frame = int(cfg["substeps"])
    rbw.solver_iterations = int(cfg["solver_iterations"])
    rbw.use_split_impulse = bool(cfg.get("split_impulse", False))
    sc.frame_start, sc.frame_end = 1, F0 + T
    rbw.point_cache.frame_start, rbw.point_cache.frame_end = 1, F0 + T

    dt = 1.0 / fps
    objects = {}
    for body in ir["bodies"]:
        ob, shape = _add_object(body)
        objects[body["id"]] = ob
        kind = body["kind"]
        pose = body.get("initial_pose") or {}
        p0 = pose.get("position", [0.0, 0.0, 0.0])
        q0 = pose.get("orientation", [1.0, 0.0, 0.0, 0.0])
        _set_pose(ob, body, p0, q0)

        bpy.context.view_layer.objects.active = ob
        bpy.ops.rigidbody.object_add()
        rb = ob.rigid_body
        rb.type = "PASSIVE" if kind != "dynamic" else "ACTIVE"
        rb.collision_shape = shape
        mat = body.get("material") or {}
        # Bullet multiplies the two bodies' values; the square root makes an equal pair give the IR value.
        rb.friction = math.sqrt(mat.get("friction", 0.5))
        rb.restitution = math.sqrt(mat.get("restitution", 0.0))
        rb.use_deactivation = False
        if cfg.get("collision_margin") is not None:
            rb.use_margin = True
            rb.collision_margin = float(cfg["collision_margin"])
        if kind == "dynamic":
            rb.mass = body["mass"]
            rb.linear_damping = body.get("linear_damping", 0.0)
            rb.angular_damping = body.get("angular_damping", 0.0)

        track = overrides.get(body["id"])
        if track is None and kind == "kinematic":
            tr = body["trajectory"]
            track = [list(p) + list(q) for p, q in zip(tr["positions"], tr["orientations"])]
        if track is not None:
            # Animated passive body for the whole run (pre-roll holds the first pose).
            rb.type = "ACTIVE" if kind == "dynamic" else rb.type
            rb.kinematic = True
            for fr in range(1, F0):
                _set_pose(ob, body, track[0][:3], track[0][3:])
                _key(ob, fr)
            for k, row in enumerate(track):
                _set_pose(ob, body, row[:3], row[3:])
                _key(ob, F0 + k)
            rb.keyframe_insert("kinematic", frame=1)
            _linear_keys(ob)
        elif kind == "dynamic":
            v = Vector(body.get("initial_linear_velocity", [0.0, 0.0, 0.0]))
            w = Vector(body.get("initial_angular_velocity", [0.0, 0.0, 0.0]))
            for fr in range(1, F0 + 1):
                s = (fr - F0) * dt  # <= 0: time before release
                q = Quaternion(w.normalized(), w.length * s) @ Quaternion(q0) if w.length > 0 else Quaternion(q0)
                _set_pose(ob, body, list(Vector(p0) + v * s), list(q))
                _key(ob, fr)
                rb.kinematic = True
                rb.keyframe_insert("kinematic", frame=fr)
            rb.kinematic = False
            rb.keyframe_insert("kinematic", frame=F0 + 1)
            _linear_keys(ob)

    poses = {bid: [] for bid in objects}
    t0 = time.perf_counter()
    for fr in range(1, F0 + T):
        sc.frame_set(fr)
        if fr < F0:
            continue
        for body in ir["bodies"]:
            ob = objects[body["id"]]
            loc, rot, _ = ob.matrix_world.decompose()
            if body["geometry"]["type"] == "plane":
                loc = loc + rot @ Vector((0.0, 0.0, PLANE_THICKNESS / 2))
            poses[body["id"]].append([loc.x, loc.y, loc.z, rot.w, rot.x, rot.y, rot.z])
    sim_wall = time.perf_counter() - t0

    with open(job["out"], "w", encoding="utf-8") as f:
        json.dump(
            {"poses": poses, "sim_wall_s": sim_wall, "blender_version": bpy.app.version_string,
             "scene_fps": scene_fps, "time_scale": rbw.time_scale},
            f,
        )


if __name__ == "__main__":
    main()
