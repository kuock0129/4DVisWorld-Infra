"""Write benchmark results: results.json (raw), results.md (tables), error_vs_walltime.png."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Metrics plotted against wall-clock (metric string as produced by vw.benchmark.analytic).
PLOT_METRICS = [
    ("free_fall", "max position error over 1 s", "abs"),
    ("slide", "stopping distance (mu=0.5)", "rel"),
    ("bounce", "rebound height (e=0.6)", "rel"),
    ("collision", "v_B after (e=0.5)", "rel"),
    ("stack", "top box drift over 3 s (5 boxes)", "abs"),
]


def _fmt(x: float | None, unit: str = "") -> str:
    if x is None:
        return "n/a"
    if x == 0:
        return "0"
    if abs(x) >= 1000 or abs(x) < 1e-3:
        return f"{x:.2e}"
    return f"{x:.4f}".rstrip("0").rstrip(".")


def _cell(c: dict[str, Any]) -> str:
    if c["rel_err"] is not None:
        return f"{_fmt(c['measured'])} ({c['rel_err'] * 100:.1f}%)"
    return f"{_fmt(c['measured'])}"


def to_markdown(res: dict[str, Any]) -> str:
    cfgs = res["configs"]
    labels = [c["label"] for c in cfgs]
    h = res["host"]
    lines = [
        "# Physics backend benchmark: results",
        "",
        f"Generated {res['created_at']} on {h['os']}, {h['cpu']}, Python {h['python']}. "
        f"Regenerate with `vw bench`. Interpretation: [README.md](README.md).",
        "",
        "## Configs",
        "",
        "| Label | Backend | Version | Device | Config | Analytic suite sim time |",
        "|---|---|---|---|---|---|",
    ]
    for c in cfgs:
        cfg = ", ".join(f"{k}={v}" for k, v in c["config"].items()) or "defaults"
        lines.append(
            f"| {c['label']} | {c['backend']} | {c['version']} | {c['device']} | {cfg} | {c['suite_sim_wall_s']:.2f} s |"
        )

    for s in res.get("skipped", []):
        lines.append(f"
Skipped **{s['label']}**: {'; '.join(s['reason'])}")

    lines += ["", "## Analytic suite", "",
              "Cells: measured value (relative error where the expected value is non-zero).", "",
              "| Case | Metric | Expected | " + " | ".join(labels) + " |",
              "|---|---|---|" + "---|" * len(labels)]
    for i, base in enumerate(cfgs[0]["analytic"]):
        row = [base["case"], f"{base['metric']} [{base['unit']}]", _fmt(base["expected"])]
        row += [_cell(c["analytic"][i]) for c in cfgs]
        lines.append("| " + " | ".join(row) + " |")

    scenes = list(cfgs[0]["consistency"])
    lines += ["", f"## Consistency vs reference ({res['reference']})", "",
              "Max position deviation over all bodies and frames, in meters (worst body in brackets).", "",
              "| Scene | " + " | ".join(labels) + " |", "|---|" + "---|" * len(labels)]
    for s in scenes:
        row = [s] + [f"{_fmt(c['consistency'][s]['max_pos'])} [{c['consistency'][s]['worst_body']}]" for c in cfgs]
        lines.append("| " + " | ".join(row) + " |")
    lines += ["", "Simulation wall-clock per scene (s):", "",
              "| Scene | " + " | ".join(labels) + " |", "|---|" + "---|" * len(labels)]
    for s in scenes:
        lines.append("| " + " | ".join([s] + [f"{c['consistency'][s]['sim_wall_s']:.3f}" for c in cfgs]) + " |")
    lines += ["", "![Error vs wall-clock](error_vs_walltime.png)", ""]
    return "\n".join(lines)


def plot(res: dict[str, Any], out: Path) -> Path | None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None
    cfgs = res["configs"]
    fig, axes = plt.subplots(2, 3, figsize=(13, 7.5))
    for ax, (case, metric, kind) in zip(axes.flat, PLOT_METRICS):
        for c in cfgs:
            row = next((r for r in c["analytic"] if r["case"] == case and r["metric"] == metric), None)
            if row is None:
                continue
            err = row["rel_err"] * 100 if kind == "rel" else row["abs_err"]
            ax.scatter(row["sim_wall_s"], max(err, 1e-9), s=30)
            ax.annotate(c["label"].split(" ")[0].replace("mujoco/", ""), (row["sim_wall_s"], max(err, 1e-9)),
                        fontsize=7, xytext=(3, 3), textcoords="offset points")
        ax.set_title(f"{case}: {metric}", fontsize=9)
        ax.set_xlabel("sim wall-clock (s)", fontsize=8)
        ax.set_ylabel("relative error (%)" if kind == "rel" else "abs error (m)", fontsize=8)
        ax.set_yscale("log")
        ax.grid(alpha=0.3)
    ax = axes.flat[-1]
    scene = "remove_support/causal" if "remove_support/causal" in cfgs[0]["consistency"] else next(iter(cfgs[0]["consistency"]))
    for c in cfgs:
        d = c["consistency"][scene]
        ax.scatter(d["sim_wall_s"], max(d["max_pos"], 1e-9), s=30)
        ax.annotate(c["label"].split(" ")[0].replace("mujoco/", ""), (d["sim_wall_s"], max(d["max_pos"], 1e-9)),
                    fontsize=7, xytext=(3, 3), textcoords="offset points")
    ax.set_title(f"{scene}: max deviation vs reference", fontsize=9)
    ax.set_xlabel("sim wall-clock (s)", fontsize=8)
    ax.set_ylabel("max position deviation (m)", fontsize=8)
    ax.set_yscale("log")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    path = out / "error_vs_walltime.png"
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


def write_report(res: dict[str, Any], out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    paths = [out / "results.json", out / "results.md"]
    paths[0].write_text(json.dumps(res, indent=2), encoding="utf-8")
    paths[1].write_text(to_markdown(res), encoding="utf-8")
    png = plot(res, out)
    if png:
        paths.append(png)
    return paths
