"""Top-down x-y paths: PhysX default baseline (solid) vs original Blender/Bullet run (dashed)."""
from pathlib import Path
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from vw.benchmark.codebench import load_original

HERE = Path(__file__).resolve().parents[1]
ORIG = Path("C:/Users/kuock/source/repos/4DCodeBench/outputs/2026-11-05/opus-5.5")
COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
fig, axes = plt.subplots(1, 2, figsize=(12, 5.2), facecolor="#fcfcfb")
for ax, case in zip(axes, ["B_01", "B_03"]):
    z = np.load(HERE / f"{case}_poses.npz")
    if case == "B_01":
        planks = [k.split("/", 1)[1] for k in z.files if k.startswith("baseline/") and k != "baseline/ball"]
        disp = {p: np.linalg.norm(z[f"baseline/{p}"][-1, :3] - z[f"baseline/{p}"][0, :3]) for p in planks}
        ids = ["ball"] + sorted(disp, key=disp.get, reverse=True)[:3]
    else:
        ids = ["ball", "pin_A1", "pin_A4", "pin_D1"]
    orig = load_original(ORIG / case / "sim" / "baseline", ids)
    for c, i in zip(COLORS, ids):
        p = z[f"baseline/{i}"][:, :3]
        ax.plot(p[:, 0], p[:, 1], color=c, lw=2, solid_capstyle="round")
        if i in orig:
            ax.plot(orig[i][:, 0], orig[i][:, 1], color=c, lw=2, ls=(0, (3, 2)))
        ax.plot(p[0, 0], p[0, 1], "o", ms=8, color=c, mec="#fcfcfb", mew=2)
        ax.annotate(i, p[-1, :2], xytext=(5, 5), textcoords="offset points", fontsize=9, color="#0b0b0b")
    ax.set_title(f"{case}: physx default (solid) vs original Bullet (dashed)", fontsize=10, color="#0b0b0b", loc="left")
    ax.set_aspect("equal", adjustable="datalim"); ax.set_xlabel("x (m)", color="#52514e"); ax.set_ylabel("y (m)", color="#52514e")
    ax.grid(color="#e5e4df", lw=0.6); ax.set_facecolor("#fcfcfb")
    for s in ax.spines.values(): s.set_color("#c8c7c0")
    ax.tick_params(colors="#52514e", labelsize=8)
from matplotlib.lines import Line2D
fig.legend([Line2D([], [], color="#52514e", lw=2), Line2D([], [], color="#52514e", lw=2, ls=(0, (3, 2))),
            Line2D([], [], color="#52514e", marker="o", ls="", ms=7)],
           ["PhysX 5.3.1 (default config)", "original Blender/Bullet", "start"], loc="lower center", ncol=3, frameon=False, fontsize=9)
axes[1].set_xlim(-1.0, 2.0)
fig.tight_layout(rect=(0, 0.06, 1, 1))
fig.savefig(HERE / "paths_xy.png", dpi=130, facecolor=fig.get_facecolor())
print(HERE / "paths_xy.png")
