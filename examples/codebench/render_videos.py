"""Render the 4DCodeBench tuple results of every physics adapter into videos/.

Usage:  python examples/codebench/render_videos.py [--engine EEVEE|WORKBENCH] [--res 640 360]

Reads docs/benchmarks/codebench/<label>/<case>_poses.npz (written by ``vw codebench``) and
renders, with Blender, one mp4 per (case, adapter, member) into videos/<case>/, plus a grid
video per case (rows = adapters, columns = baseline / causal / non-causal). The motion comes
from each physics engine; the rendering is the same Blender preview for all of them.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from vw.ir import SceneIR  # noqa: E402
from vw.physics.bullet_blender import find_blender  # noqa: E402

ADAPTERS = [("mujoco", "MuJoCo 3.15"), ("bullet", "Bullet (Blender 4.0.2)"), ("physx", "PhysX 5.3.1"),
            ("newton", "Newton 1.7 XPBD (CUDA)")]
MEMBERS = [("baseline", "baseline"), ("causal", "causal: ball removed, re-simulated"),
           ("noncausal", "non-causal: ball removed, replayed")]
CASES = ["B_01", "B_03"]
WORKER = ROOT / "vw" / "render" / "blender_preview_worker.py"


def find_ffmpeg() -> str | None:
    for c in (shutil.which("ffmpeg"), r"C:\Users\kuock\anaconda3\envs\ffmpeg_tools\Library\bin\ffmpeg.exe"):
        if c and Path(c).exists():
            return c
    return None


def members_from_npz(npz: Path) -> dict[str, dict[str, list]]:
    data = np.load(npz)
    out: dict[str, dict[str, list]] = {}
    for key in data.files:
        member, body = key.split("/", 1)
        out.setdefault(member, {})[body] = data[key].astype(float).tolist()
    return out


def render_case(case: str, engine: str, res: tuple[int, int], blender: str) -> list[list[Path]]:
    ir = SceneIR.load(ROOT / "examples" / "codebench" / f"{case}.json")
    out_dir = ROOT / "videos" / case
    out_dir.mkdir(parents=True, exist_ok=True)
    grid: list[list[Path]] = []
    for label, pretty in ADAPTERS:
        npz = ROOT / "docs" / "benchmarks" / "codebench" / label / f"{case}_poses.npz"
        if not npz.exists():
            print(f"skip {case}/{label}: no {npz}")
            continue
        poses = members_from_npz(npz)
        row, members = [], []
        for m, desc in MEMBERS:
            out = out_dir / f"{case}_{label}_{m}.mp4"
            members.append({"label": f"{case} | {pretty} | {desc}", "out": str(out), "poses": poses[m]})
            row.append(out)
        job = {"ir": ir.model_dump(mode="json"), "fps": ir.timing.fps, "resolution": list(res),
               "engine": engine, "members": members}
        with tempfile.TemporaryDirectory() as tmp:
            jp = Path(tmp) / "job.json"
            jp.write_text(json.dumps(job), encoding="utf-8")
            cmd = [blender, "--background", "--factory-startup", "--python-exit-code", "1",
                   "--python", str(WORKER), "--", str(jp)]
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if proc.returncode != 0:
            raise RuntimeError(f"render failed for {case}/{label}:\n" + "\n".join(proc.stdout.splitlines()[-20:]))
        print(f"rendered {case}/{label}: " + ", ".join(p.name for p in row))
        grid.append(row)
    return grid


def compose(case: str, grid: list[list[Path]], ffmpeg: str) -> Path:
    out = ROOT / "videos" / case / f"{case}_compare.mp4"
    inputs = [str(p) for row in grid for p in row]
    rows, cols = len(grid), len(grid[0])
    cells = []  # xstack layout: "0_0|w0_0|w0+w0_0|0_h0|..."
    for r in range(rows):
        for c in range(cols):
            x = "+".join(["w0"] * c) or "0"
            y = "+".join(["h0"] * r) or "0"
            cells.append(f"{x}_{y}")
    cmd = [ffmpeg, "-y", "-loglevel", "error"]
    for p in inputs:
        cmd += ["-i", p]
    cmd += ["-filter_complex", f"xstack=inputs={len(inputs)}:layout={'|'.join(cells)}[v]", "-map", "[v]",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23", str(out)]
    subprocess.run(cmd, check=True)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", default="EEVEE", choices=["EEVEE", "WORKBENCH"])
    ap.add_argument("--res", type=int, nargs=2, default=[640, 360])
    ap.add_argument("--cases", nargs="+", default=CASES)
    args = ap.parse_args()
    blender, ffmpeg = find_blender(), find_ffmpeg()
    if blender is None:
        raise SystemExit("Blender not found (set VW_BLENDER)")
    for case in args.cases:
        grid = render_case(case, args.engine, tuple(args.res), blender)
        if ffmpeg and grid:
            print("composed", compose(case, grid, ffmpeg))
        elif not ffmpeg:
            print("ffmpeg not found: skipped the comparison grid")


if __name__ == "__main__":
    main()
