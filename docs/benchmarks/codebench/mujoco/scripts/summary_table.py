"""Markdown table of the saved codebench JSONs for the given labels.

Usage: python summary_table.py docs/benchmarks/codebench mujoco mujoco_rk4 mujoco_dt0005
"""
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
print("| case | config | moved (base) | down (base) | causal max path | causal moved | causal static | NC replays | "
      "final err mean / median (m) | ball path err mean / final (m) | moved agree | sim s (b/c/nc) |")
print("|" + "---|" * 12)
for case in ("B_01", "B_03"):
    for label in sys.argv[2:]:
        f = root / label / f"{case}.json"
        if not f.exists():
            continue
        r = json.loads(f.read_text())
        b, c, ch, o, t = r["baseline"], r["causal"], r["checks"], r["vs_original_bullet"], r["timing"]
        down = len(b["down"]) if case == "B_03" else "n/a"
        print(f"| {case} | {label} | {b['moved']}/{b['of']} | {down} | {c['max_path_displacement']*1000:.1f} mm | "
              f"{c['moved']} | {ch['causal_is_static']} | {ch['noncausal_replays_baseline']} | "
              f"{o['final_pos_err_mean']:.3f} / {o['final_pos_err_median']:.3f} | "
              f"{o['ball_path_err_mean']:.3f} / {o['ball_final_err']:.3f} | {o['moved_agreement']}/{o['bodies']} | "
              f"{t['baseline']['sim_s']:.1f} / {t['causal']['sim_s']:.1f} / {t['noncausal']['sim_s']:.1f} |")
        if case == "B_03":
            print(f"|  |  down: {', '.join(x[4:] for x in b['down'])} | | | | | | | | | | |")
