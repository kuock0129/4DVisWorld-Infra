"""Bullet via Blender's rigid-body world, run headless (CPU).

Each simulate() call writes a job file and runs ``blender --background --python
blender_worker.py``. The worker builds the scene from the IR dict, steps it and returns
per-frame poses. This matches how 4DCodeBench drives Blender, so results are directly
comparable with those runs.

Limits (all recorded in param_map):
* Blender exposes no velocities or contacts. Velocities are finite differences of the
  poses; ``SimResult.contacts`` is empty.
* Initial velocities are imparted by a 2-frame animated pre-roll that Bullet keeps on
  release (the same trick 4DCodeBench uses).
* Each call pays Blender's start-up cost (about 1-2 s); the worker's own stepping time
  is reported as ``solver_config["sim_wall_s"]``.

Blender is found via the ``blender`` config key, the ``VW_BLENDER`` environment
variable, ``PATH``, or the default install locations.
"""

from __future__ import annotations

import glob
import json
import os
import platform
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

from vw.ir import BodyKind, Mesh, SceneIR
from vw.physics.base import Capabilities, Device, Feature, NativeScene, SimResult, Trajectory, UnsupportedSceneError
from vw.physics.stubs import _AdapterBase
from vw.physics.util import effective_timestep, finite_diff_velocities
from vw.registry import register_physics

WORKER = Path(__file__).with_name("blender_worker.py")


def find_blender(explicit: str | None = None) -> str | None:
    for cand in (explicit, os.environ.get("VW_BLENDER"), shutil.which("blender")):
        if cand and Path(cand).exists():
            return str(cand)
    if platform.system() == "Windows":
        hits = sorted(glob.glob(r"C:\Program Files\Blender Foundation\Blender*\blender.exe"))
    elif platform.system() == "Darwin":
        hits = glob.glob("/Applications/Blender*.app/Contents/MacOS/Blender")
    else:
        hits = sorted(glob.glob("/opt/blender*/blender")) + sorted(glob.glob("/usr/local/blender*/blender"))
    return hits[-1] if hits else None


@lru_cache(maxsize=8)
def blender_version(exe: str) -> str:
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    for line in out.splitlines():
        if line.startswith("Blender "):
            return line.split()[1]
    return "unknown"


@dataclass
class BlenderJob:
    ir: SceneIR
    config: dict[str, Any]  # resolved: substeps, solver_iterations, timestep, ...


@register_physics("bullet_blender")
class BulletBlenderAdapter(_AdapterBase):
    """Config: timestep (s, default 0.002; sets substeps per frame), solver_iterations
    (default 10, Blender's default), split_impulse (bool), collision_margin (m, default 0.001;
    Blender's own 0.04 m default breaks contacts between cylinders and thin boxes), blender (path to the executable), timeout (s)."""

    name = "bullet_blender"
    capabilities = Capabilities(frozenset({Feature.RIGID, Feature.KINEMATIC}), frozenset({Device.CPU}))
    single_shot_timing = True  # process start-up dominates: the benchmark times one run, not min-of-N

    @property
    def exe(self) -> str | None:
        return find_blender(self.config.get("blender"))

    @property
    def version(self) -> str:  # type: ignore[override]
        exe = self.exe
        return f"blender-{blender_version(exe)}" if exe else "not-installed"

    def check(self, ir: SceneIR) -> list[str]:
        problems = super().check(ir)
        if any(isinstance(b.geometry, Mesh) for b in ir.bodies):
            problems.append("unsupported feature: mesh_collision (not implemented in the Blender worker yet)")
        if self.exe is None:
            problems.append("blender executable not found (set VW_BLENDER or the 'blender' config key)")
        return sorted(set(problems))

    def compile(self, ir: SceneIR) -> NativeScene:
        self._require(ir)
        dt, n = effective_timestep(float(self.config.get("timestep", 0.002)), ir.timing.fps)
        cfg = {
            "timestep": dt,
            "timestep_requested": float(self.config.get("timestep", 0.002)),
            "substeps": n,
            "solver_iterations": int(self.config.get("solver_iterations", 10)),
            "split_impulse": bool(self.config.get("split_impulse", False)),
            # Blender's own default margin (0.04 m) makes thin boxes push cylinders away: use 1 mm.
            "collision_margin": float(self.config.get("collision_margin", 0.001)),
        }
        return BlenderJob(ir, cfg)

    def simulate(self, native: NativeScene, kinematic: dict[str, Trajectory] | None = None) -> SimResult:
        job: BlenderJob = native
        ir, T, fps = job.ir, job.ir.timing.frames, job.ir.timing.fps
        overrides: dict[str, list] = {}
        for bid, traj in (kinematic or {}).items():
            body = ir.body(bid)  # KeyError for unknown ids
            if body.kind is BodyKind.STATIC:
                raise UnsupportedSceneError(self.name, [f"cannot override static body '{bid}'"])
            arr = np.asarray(traj, dtype=float)
            if arr.shape != (T, 7):
                raise ValueError(f"kinematic['{bid}'] must be ({T}, 7), got {arr.shape}")
            overrides[bid] = arr.tolist()

        exe = self.exe
        if exe is None:
            raise RuntimeError("blender executable not found (set VW_BLENDER or the 'blender' config key)")
        with tempfile.TemporaryDirectory(prefix="vw_blender_") as tmp:
            job_path, out_path = Path(tmp) / "job.json", Path(tmp) / "out.json"
            payload = {"ir": ir.model_dump(mode="json"), "config": job.config, "overrides": overrides,
                       "out": str(out_path)}
            job_path.write_text(json.dumps(payload), encoding="utf-8")
            cmd = [exe, "--background", "--factory-startup", "--python-exit-code", "1",
                   "--python", str(WORKER), "--", str(job_path)]
            t0 = time.perf_counter()
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                  timeout=float(self.config.get("timeout", 600)))
            process_wall = time.perf_counter() - t0
            if proc.returncode != 0 or not out_path.exists():
                tail = "\n".join((proc.stdout + proc.stderr).splitlines()[-25:])
                raise RuntimeError(f"Blender worker failed (exit {proc.returncode}):\n{tail}")
            out = json.loads(out_path.read_text(encoding="utf-8"))

        poses = {bid: np.asarray(p, dtype=float) for bid, p in out["poses"].items()}
        for b in ir.bodies:  # exact static poses (avoid float32 round-trip through Blender)
            if b.kind is BodyKind.STATIC:
                poses[b.id] = np.tile([*b.initial_pose.position, *b.initial_pose.orientation], (T, 1))
            elif b.id in overrides:
                poses[b.id] = np.asarray(overrides[b.id])
        for p in poses.values():
            p[:, 3:] /= np.linalg.norm(p[:, 3:], axis=1, keepdims=True)
        vels = {bid: finite_diff_velocities(p, fps) for bid, p in poses.items()}
        solver = {**job.config, "sim_wall_s": out["sim_wall_s"], "process_wall_s": process_wall,
                  "scene_fps": out["scene_fps"], "time_scale": out["time_scale"], "contacts": "unavailable"}
        return SimResult(fps, poses, vels, [], type(self.backend_info())(self.name, self.version, self.device, solver))

    def param_map(self) -> dict[str, Any]:
        return {
            "geometry.box.extents": {"to": "cube object scale", "note": "exact; collision_shape=BOX"},
            "geometry.sphere|cylinder": {"to": "SPHERE / CYLINDER shape", "note": "exact"},
            "geometry.capsule": {"to": "CAPSULE shape", "note": "exact: mesh height = height + 2 * radius"},
            "geometry.plane": {"to": "BOX 200 x 200 x 1 m under the plane", "note": "approximation of an infinite plane"},
            "material.friction": {"to": "rigid_body.friction", "note": "sqrt(mu): Bullet multiplies the pair, so an equal pair gives mu"},
            "material.restitution": {"to": "rigid_body.restitution", "note": "sqrt(e), same reason"},
            "mass": {"to": "rigid_body.mass", "note": "inertia from the collision shape"},
            "linear_damping|angular_damping": {"to": "rigid_body.*_damping", "note": "approximation: Bullet damping is a per-second velocity fraction"},
            "initial_linear_velocity|initial_angular_velocity": {
                "to": "2-frame animated pre-roll, released at frame 0",
                "note": "Bullet keeps the kinematic velocity on release",
            },
            "kind=kinematic": {"to": "animated passive body", "note": "keyframe per IR frame, linear interpolation across substeps"},
            "timing": {"to": "substeps_per_frame, time_scale", "note": "one Blender frame = one IR frame; dt divides 1/fps"},
            "velocities": {"to": "finite differences of poses", "note": "Blender does not expose body velocities"},
            "contacts": {"to": "none", "note": "Blender does not expose contacts; SimResult.contacts is empty"},
            "deactivation": {"to": "use_deactivation=False", "note": "bodies never sleep"},
        }
