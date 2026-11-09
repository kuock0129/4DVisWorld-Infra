"""Top-down x-y paths, Newton baseline (default XPBD and MuJoCo Warp) vs the original Blender/Bullet run."""
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parents[2]
ORIG = Path("C:/Users/kuock/source/repos/4DCodeBench/outputs/2026-11-05/opus-5.5")
CASES = {"B_01": ["ball", "up00", "capS", "capE1"], "B_03": ["ball", "pin_A1", "pin_A4", "pin_D1"]}
COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#6250d6"]
RUNS = [("newton", "-", "Newton XPBD (default)"), ("newton_mujoco", ":", "Newton MuJoCo Warp")]

fig, axs = plt.subplots(1, 3, figsize=(17, 5.4))
axes = axs[:2]
for ax, (case, ids) in zip(axes, CASES.items()):
    for col, oid in zip(COLORS, ids):
        o = np.load(ORIG / case / "sim/baseline/world/dynamics" / f"{oid}.npz")["pos"].astype(float).mean(1)
        ax.plot(o[:, 0], o[:, 1], "--", color=col, lw=2, alpha=0.6)
        for lab, ls, _ in RUNS:
            f = ROOT / lab / f"{case}_poses.npz"
            if f.exists():
                p = np.load(f)[f"baseline/{oid}"]
                ax.plot(p[:, 0], p[:, 1], ls, color=col, lw=2)
                ax.plot(p[-1, 0], p[-1, 1], "o", color=col, ms=5)
        ax.plot(o[-1, 0], o[-1, 1], "x", color=col, ms=8)
    ax.legend(handles=[Line2D([], [], color=c, lw=3, label=i) for c, i in zip(COLORS, ids)], fontsize=8, loc="upper left", frameon=False)
    if case == "B_03": ax.set_xlim(-1.0, 2.0); ax.set_ylim(-1.2, 1.6)
    ax.set_title(f"{case}: top-down x-y paths (baseline)", fontsize=11)
    ax.set_xlabel("x (m)"); ax.set_ylabel("y (m)"); ax.set_aspect("equal", adjustable="box")
    ax.grid(color="#e5e4e0", lw=0.6); [s.set_color("#c3c2b7") for s in ax.spines.values()]
ax = axs[2]
for case, col in (("B_01", "#2a78d6"), ("B_03", "#eb6834")):
    o = np.load(ORIG / case / "sim/baseline/world/dynamics/ball.npz")["pos"].astype(float).mean(1)
    ax.plot(np.linalg.norm(np.diff(o, axis=0), axis=1) * 24, "--", color=col, lw=2, alpha=0.6)
    for lab, ls, _ in RUNS + [("newton_dt05", "-.", "")]:
        f = ROOT / lab / f"{case}_poses.npz"
        if f.exists():
            p = np.load(f)["baseline/ball"].astype(float)
            ax.plot(np.linalg.norm(np.diff(p[:, :3], axis=0), axis=1) * 24, ls, color=col, lw=2 if ls != "-." else 1.2)
ax.legend(handles=[Line2D([], [], color="#2a78d6", lw=3, label="B_01 ball"), Line2D([], [], color="#eb6834", lw=3, label="B_03 ball"),
                   Line2D([], [], color="#52514e", ls="-.", lw=1.2, label="XPBD dt = 0.5 ms")], fontsize=8, frameon=False)
ax.set_xlim(0, 40); ax.set_xlabel("frame (24 fps)"); ax.set_ylabel("ball speed (m/s)"); ax.set_title("Ball speed, first 40 frames", fontsize=11)
ax.grid(color="#e5e4e0", lw=0.6); [s_.set_color("#c3c2b7") for s_ in ax.spines.values()]
h = [Line2D([], [], color="#52514e", ls="--", lw=2, alpha=0.6, label="original Blender/Bullet (x = end)")]
h += [Line2D([], [], color="#52514e", ls=ls, lw=2, label=f"{n} (o = end)") for _, ls, n in RUNS]
fig.legend(handles=h, loc="lower center", ncol=3, fontsize=9, frameon=False)
fig.tight_layout(rect=(0, 0.07, 1, 1))
out = ROOT / "newton" / "paths_xy.png"
fig.savefig(out, dpi=130)
print(out)
