"""Does Blender itself follow the kinematic replay? BulletBlenderAdapter.simulate() overwrites the poses
of overridden bodies with the input track, so the runner's noncausal check (diff < 1e-9) holds by
construction. This script runs the same Blender job but reads the worker's raw output instead.

usage: python raw_noncausal.py <case IR json> <saved *_poses.npz from vw codebench> [config json]
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

from vw.interventions import remove
from vw.ir import BodyKind, SceneIR
from vw.physics.bullet_blender import WORKER, BulletBlenderAdapter

ir = SceneIR.load(sys.argv[1])
saved = np.load(sys.argv[2])
cfg = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
cf = remove(ir, ["ball"])
ad = BulletBlenderAdapter(device="cpu", **cfg)
job = ad.compile(cf)
others = [b.id for b in cf.bodies if b.kind is BodyKind.DYNAMIC]
overrides = {i: saved[f"baseline/{i}"].astype(float).tolist() for i in others}
with tempfile.TemporaryDirectory(prefix="vw_raw_") as tmp:
    jp, op = Path(tmp) / "job.json", Path(tmp) / "out.json"
    jp.write_text(json.dumps({"ir": cf.model_dump(mode="json"), "config": job.config, "overrides": overrides, "out": str(op)}))
    subprocess.run([ad.exe, "--background", "--factory-startup", "--python-exit-code", "1", "--python", str(WORKER), "--", str(jp)],
                   capture_output=True, check=True)
    raw = json.loads(op.read_text())["poses"]
pos = max(float(np.abs(np.asarray(raw[i])[:, :3] - np.asarray(overrides[i])[:, :3]).max()) for i in others)
q = []
for i in others:
    a, b = np.asarray(raw[i])[:, 3:], np.asarray(overrides[i])[:, 3:]
    q.append(float((1 - np.abs((a * b).sum(1) / np.linalg.norm(a, axis=1) / np.linalg.norm(b, axis=1))).max()))
print(f"raw Blender noncausal vs baseline: max |dpos| = {pos:.2e} m, max (1-|q.q'|) = {max(q):.2e}")
