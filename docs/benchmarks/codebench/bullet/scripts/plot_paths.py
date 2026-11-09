"""Top-down x-y paths: this adapter (solid) vs the original 4DCodeBench Bullet run (dashed)."""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path("C:/Users/kuock/source/repos/4DVisWorld-Infra/docs/benchmarks/codebench")
ORIG = Path("C:/Users/kuock/source/repos/4DCodeBench/outputs/2026-11-05/opus-5.5")
COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#6250d6"]
PANELS = [
    ("B_01", "bullet_orig", ["ball", "capE1", "up20", "capA3"], "B_01, IR, original solver settings"),
    ("B_03", "bullet_orig", ["ball", "pin_A1", "pin_C1", "pin_D1"], "B_03, IR, original solver settings"),
    ("B_03", "bullet_damp_orig", ["ball", "pin_A1", "pin_C1", "pin_D1"],
     "B_03, IR + original pin damping, original solver settings"),
]

fig, axes = plt.subplots(1, 3, figsize=(16, 5.6))
for ax, (case, label, ids, title) in zip(axes, PANELS):
    d = np.load(ROOT / label / f"{case}_poses.npz")
    for c, i in zip(COLORS, ids):
        o = np.load(ORIG / case / "sim/baseline/world/dynamics" / f"{i}.npz")["pos"].astype(float).mean(1)
        p = d[f"baseline/{i}"]
        ax.plot(p[:, 0], p[:, 1], color=c, lw=2, label=f"{i} (this run)")
        ax.plot(o[:, 0], o[:, 1], color=c, lw=2, ls=(0, (3, 2)), alpha=0.8, label=f"{i} (original)")
        ax.plot(p[-1, 0], p[-1, 1], "o", color=c, ms=8, mec="white", mew=2)
        ax.plot(o[-1, 0], o[-1, 1], "s", color=c, ms=8, mec="white", mew=2)
    ax.set_title(title, fontsize=11, color="#0b0b0b")
    ax.set_xlabel("x (m)", color="#52514e"); ax.set_ylabel("y (m)", color="#52514e")
    if case == "B_03":  # zoom on the pin deck and pit; the ball's straight approach from x = -6.3 is off to the left
        ax.set_xlim(-0.6, 1.9); ax.set_ylim(-0.9, 0.9)
        ax.set_aspect("equal")
    else:
        ax.set_aspect("equal", adjustable="datalim")
    ax.grid(color="#e4e3df", lw=0.6)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.legend(fontsize=7.5, frameon=False, loc="best")
fig.suptitle("bullet_blender vs original 4DCodeBench run: top-down paths (solid/circle = this run, dashed/square = original; markers = final frame)",
             fontsize=11)
fig.tight_layout()
out = ROOT / "bullet" / "paths.png"
fig.savefig(out, dpi=130, facecolor="#fcfcfb")
print(out)
