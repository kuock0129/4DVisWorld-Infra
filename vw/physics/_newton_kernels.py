"""Warp kernels for the Newton adapter. Imported lazily (needs warp).

No ``from __future__ import annotations`` here: Warp reads the annotations as types.
"""

import warp as wp


@wp.kernel
def set_kinematic(
    track_q: wp.array2d(dtype=wp.float32),  # (substeps_total, K * 7) free-joint q: pos + quat xyzw
    track_qd: wp.array2d(dtype=wp.float32),  # (substeps_total, K * 6) free-joint qd: lin + ang, world
    q_start: wp.array(dtype=wp.int32),
    qd_start: wp.array(dtype=wp.int32),
    step: wp.array(dtype=wp.int32),
    joint_q: wp.array(dtype=wp.float32),
    joint_qd: wp.array(dtype=wp.float32),
):
    k = wp.tid()
    s = step[0]
    for i in range(7):
        joint_q[q_start[k] + i] = track_q[s, k * 7 + i]
    for i in range(6):
        joint_qd[qd_start[k] + i] = track_qd[s, k * 6 + i]


@wp.kernel
def advance(step: wp.array(dtype=wp.int32)):
    step[0] = step[0] + 1


@wp.kernel
def record(
    body_q: wp.array(dtype=wp.transform),
    body_qd: wp.array(dtype=wp.spatial_vector),
    frame: wp.array(dtype=wp.int32),
    hist_q: wp.array2d(dtype=wp.transform),
    hist_qd: wp.array2d(dtype=wp.spatial_vector),
):
    b = wp.tid()
    f = frame[0]
    hist_q[f, b] = body_q[b]
    hist_qd[f, b] = body_qd[b]
