"""Minimal reproduction: a sphere (r 0.1085, 6.5 kg) rolls at 0.42 m/s along +y past the end cap of a
cylinder (r 0.0605, h 0.381, 1.5 kg) lying on the floor, the B_03 PGS geometry. Prints, per frame,
the sphere-cylinder gap computed from the poses and whether PhysX reported a ball-pin contact.
Usage: python min_repro_sphere_cylinder_cap.py [pgs|tgs] [offset_y]"""
import json, math, sys
import numpy as np
from vw.ir import SceneIR
from vw.physics.physx import PhysXAdapter
from vw.physics.util import quat_to_mat

solver = sys.argv[1] if len(sys.argv) > 1 else "pgs"
yaw = math.atan2(0.31, -0.95)  # pin axis direction in the B_03 event

# rotation: first about y by 90 deg (z -> x), then yaw about z
def qmul(a, b):
    w1, x1, y1, z1 = a; w2, x2, y2, z2 = b
    return [w1*w2-x1*x2-y1*y2-z1*z2, w1*x2+x1*w2+y1*z2-z1*y2, w1*y2-x1*z2+y1*w2+z1*x2, w1*z2+x1*y2-y1*x2+z1*w2]
qpin = qmul([math.cos(yaw/2), 0, 0, math.sin(yaw/2)], [math.cos(math.pi/4), 0, math.sin(math.pi/4), 0])
mat = {"friction": 0.2, "restitution": 0.3}
scene = {"ir_version": "0.1", "level": "physical", "gravity": [0, 0, -9.81], "timing": {"fps": 24, "frames": 30},
         "cameras": [{"id": "cam", "pose": {"position": [0, -3, 1], "orientation": [1, 0, 0, 0]}, "fov_deg": 40, "resolution": [64, 64]}], "lights": [], "metadata": {"name": "min_repro"},
         "bodies": [
    {"id": "floor", "kind": "static", "geometry": {"type": "plane", "extents": [10, 10]}, "material": mat,
     "initial_pose": {"position": [0, 0, 0], "orientation": [1, 0, 0, 0]}},
    {"id": "pin", "kind": "dynamic", "mass": 1.5, "geometry": {"type": "cylinder", "radius": 0.0605, "height": 0.381},
     "material": mat, "initial_pose": {"position": [1.426, 0.663, 0.0605], "orientation": qpin}},
    {"id": "ball", "kind": "dynamic", "mass": 6.5, "geometry": {"type": "sphere", "radius": 0.1085}, "material": mat,
     "initial_pose": {"position": [1.592, 0.30, 0.1085], "orientation": [1, 0, 0, 0]},
     "initial_linear_velocity": [0, 0.42, 0], "initial_angular_velocity": [-0.42 / 0.1085, 0, 0]}]}
ir = SceneIR.model_validate(scene)
ad = PhysXAdapter(solver=solver)
sim = ad.simulate(ad.compile(ir))
b, a = sim.poses["ball"], sim.poses["pin"]
hit = {round(c.t * 24) for c in sim.contacts if {c.obj_a, c.obj_b} == {"ball", "pin"}}
for k in range(sim.num_frames):
    R = quat_to_mat(a[k, 3:]); ax = R[:, 2]; v = b[k, :3] - a[k, :3]; s = v @ ax; r = np.linalg.norm(v - s * ax)
    gap = math.hypot(max(r - 0.0605, 0), max(abs(s) - 0.1905, 0)) - 0.1085
    print(f"{k:2d} gap={gap:+.4f} m  contact={'yes' if k in hit else 'no '}  |v_ball|={np.linalg.norm(sim.velocities['ball'][k,:3]):.2f}")
