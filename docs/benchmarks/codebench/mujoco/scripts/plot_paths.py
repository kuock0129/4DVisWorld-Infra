"""Top-down x-y paths of the ball and a few bodies: MuJoCo baseline vs the original Bullet run.

Also prints the bodies whose moved/not-moved status (1 cm) differs from the original.
Usage: python plot_paths.py <original_root> (writes paths.png next to REPORT.md)
"""
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

oroot = Path(sys.argv[1])
here = Path(__file__).resolve().parents[1]
bench = here.parent
cases = {"B_01": ("mujoco", None), "B_03": ("mujoco", None)}
fig, axes = plt.subplots(1, 2, figsize=(14, 7.5))
for ax, (case, (lab, lab2)) in zip(axes, cases.items()):
    run = np.load(bench / lab / f"{case}_poses.npz")
    run2 = np.load(bench / lab2 / f"{case}_poses.npz") if lab2 else None
    dyn = sorted({k.split("/", 1)[1] for k in run.files if k.startswith("baseline/")})
    odir = oroot / case / "sim" / "baseline" / "world" / "dynamics"
    orig = {b: np.load(odir / f"{b}.npz")["pos"].astype(float).mean(1) for b in dyn if (odir / f"{b}.npz").exists()}
    mov = lambda p: np.linalg.norm(p[-1, :3] - p[0, :3]) > 0.01
    diff = [b for b in orig if mov(run[f"baseline/{b}"][:, :3]) != mov(orig[b])]
    print(case, "moved-status differs:", diff)
    # ball + the 5 bodies that travel furthest in the original
    far = sorted((b for b in orig if b != "ball"), key=lambda b: -np.linalg.norm(orig[b][-1] - orig[b][0]))[:5]
    colors = plt.cm.tab10(np.arange(6))
    for c, b in zip(colors, ["ball", *far]):
        o, s = orig[b], run[f"baseline/{b}"][:, :3]
        ax.plot(o[:, 0], o[:, 1], "-", color=c, lw=2, alpha=0.5, label=f"{b} original")
        ax.plot(s[:, 0], s[:, 1], "--", color=c, lw=1.5, label=f"{b} MuJoCo")
        if run2 is not None:
            s2 = run2[f"baseline/{b}"][:, :3]
            ax.plot(s2[:, 0], s2[:, 1], ":", color=c, lw=1.5, label=f"{b} MuJoCo, no gutter_*_2")
        ax.plot(*o[-1, :2], "o", color=c, ms=5, alpha=0.5)
        ax.plot(*s[-1, :2], "x", color=c, ms=6)
    if case == "B_03":
        ax.set_xlim(-0.5, 2.0)
        ax.axhline(0.527, color="0.6", lw=0.8); ax.axhline(-0.527, color="0.6", lw=0.8)
        ax.axvline(0.87, color="0.6", lw=0.8)
    ax.set_title(f"{case}: solid = original Bullet, dashed = MuJoCo default"
                 + (", dotted = MuJoCo without gutter_*_2" if lab2 else ""), fontsize=9)
    ax.set_xlabel("x (m)"); ax.set_ylabel("y (m)"); ax.set_aspect("equal", adjustable="box")
    ax.legend(fontsize=6, ncol=3 if lab2 else 2, loc="upper center", bbox_to_anchor=(0.5, -0.12))
    ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(here / "paths.png", dpi=130)
print("wrote", here / "paths.png")
