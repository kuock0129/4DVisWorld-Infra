"""Engine-independent helpers shared by the physics adapters (numpy only)."""

from __future__ import annotations

import math

import numpy as np


def effective_timestep(requested: float, fps: int) -> tuple[float, int]:
    """Largest dt <= requested that divides the frame period exactly, and steps per frame."""
    period = 1.0 / fps
    n = max(1, math.ceil(period / requested - 1e-9))
    return period / n, n


def quat_to_mat(q: np.ndarray) -> np.ndarray:
    """Rotation matrix of a unit quaternion (w, x, y, z)."""
    w, x, y, z = q
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
            [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
            [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
        ]
    )


def quat_mul(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Hamilton product a * b of (..., 4) wxyz quaternions."""
    aw, ax, ay, az = np.moveaxis(np.asarray(a, dtype=float), -1, 0)
    bw, bx, by, bz = np.moveaxis(np.asarray(b, dtype=float), -1, 0)
    return np.stack(
        [
            aw * bw - ax * bx - ay * by - az * bz,
            aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
        ],
        axis=-1,
    )


def quat_conj(q: np.ndarray) -> np.ndarray:
    q = np.array(q, dtype=float)
    q[..., 1:] *= -1
    return q


def quat_from_rotvec(v: np.ndarray) -> np.ndarray:
    """Unit quaternion for a rotation vector (axis * angle, radians)."""
    v = np.asarray(v, dtype=float)
    angle = float(np.linalg.norm(v))
    if angle < 1e-12:
        return np.array([1.0, 0.0, 0.0, 0.0])
    return np.array([math.cos(angle / 2), *(math.sin(angle / 2) * v / angle)])


def quat_to_rotvec(q: np.ndarray) -> np.ndarray:
    """Rotation vectors (..., 3) of (..., 4) unit quaternions, shortest arc."""
    q = np.asarray(q, dtype=float)
    q = np.where(q[..., :1] < 0, -q, q)
    s = np.linalg.norm(q[..., 1:], axis=-1, keepdims=True)
    angle = 2 * np.arctan2(s, q[..., :1])
    scale = np.where(s > 1e-12, angle / np.maximum(s, 1e-12), 2.0)
    return q[..., 1:] * scale


def interp_pose(traj: np.ndarray, f: float) -> tuple[np.ndarray, np.ndarray]:
    """Pose at fractional frame ``f``: linear position, normalized-lerp quaternion."""
    T = traj.shape[0]
    f = min(max(f, 0.0), T - 1)
    i = min(int(f), T - 2) if T > 1 else 0
    a = f - i if T > 1 else 0.0
    p0, p1 = traj[i], traj[min(i + 1, T - 1)]
    pos = (1 - a) * p0[:3] + a * p1[:3]
    q0, q1 = p0[3:], p1[3:]
    if np.dot(q0, q1) < 0:
        q1 = -q1
    q = (1 - a) * q0 + a * q1
    return pos, q / np.linalg.norm(q)


def finite_diff_velocities(poses: np.ndarray, fps: int) -> np.ndarray:
    """(T, 6) world-frame linear + angular velocity of a (T, 7) pose track.

    Central differences inside, one-sided at the ends. Used by backends that do not
    expose body velocities (Blender) and for kinematic bodies.
    """
    T = poses.shape[0]
    v = np.zeros((T, 6))
    if T < 2:
        return v
    dt = 1.0 / fps
    v[:, :3] = np.gradient(poses[:, :3], dt, axis=0)
    q = poses[:, 3:]
    lo = np.r_[0, np.arange(T - 2), T - 2]
    hi = np.r_[1, np.arange(2, T), T - 1]
    # World-frame angular velocity: q_hi = exp(w * dt_span) * q_lo.
    rel = quat_mul(q[hi], quat_conj(q[lo]))
    v[:, 3:] = quat_to_rotvec(rel) / ((hi - lo) * dt)[:, None]
    return v


def contact_key(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a <= b else (b, a)
