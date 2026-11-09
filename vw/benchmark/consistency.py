"""Trajectory comparison between two SimResults of the same IR (cross-backend or cross-config)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from vw.physics.base import SimResult


@dataclass(frozen=True)
class Divergence:
    max_pos: float  # m, max over bodies and frames
    rms_pos: float  # m, RMS over bodies and frames
    final_pos: float  # m, max over bodies at the last frame
    max_rot_deg: float  # deg, max orientation difference over bodies and frames
    worst_body: str


def _quat_angle_deg(qa: np.ndarray, qb: np.ndarray) -> np.ndarray:
    dot = np.abs(np.sum(qa * qb, axis=-1)) / (np.linalg.norm(qa, axis=-1) * np.linalg.norm(qb, axis=-1))
    return np.degrees(2.0 * np.arccos(np.clip(dot, -1.0, 1.0)))


def trajectory_divergence(a: SimResult, b: SimResult, bodies: list[str] | None = None) -> Divergence:
    if a.fps != b.fps or a.num_frames != b.num_frames:
        raise ValueError(f"timing mismatch: {a.fps}fps x {a.num_frames} vs {b.fps}fps x {b.num_frames}")
    if bodies is None:
        if set(a.poses) != set(b.poses):
            raise ValueError(f"body sets differ: {sorted(set(a.poses) ^ set(b.poses))}")
        ids = sorted(a.poses)
    else:
        ids = list(bodies)
        missing = [i for i in ids if i not in a.poses or i not in b.poses]
        if missing:
            raise ValueError(f"bodies missing from a result: {missing}")
    if not ids:
        raise ValueError("no bodies to compare")
    d = {i: np.linalg.norm(a.poses[i][:, :3] - b.poses[i][:, :3], axis=1) for i in ids}
    rot = {i: _quat_angle_deg(a.poses[i][:, 3:], b.poses[i][:, 3:]) for i in ids}
    worst = max(ids, key=lambda i: d[i].max())
    allp = np.concatenate(list(d.values()))
    return Divergence(
        max_pos=float(allp.max()),
        rms_pos=float(np.sqrt(np.mean(allp**2))),
        final_pos=float(max(v[-1] for v in d.values())),
        max_rot_deg=float(max(v.max() for v in rot.values())),
        worst_body=worst,
    )
