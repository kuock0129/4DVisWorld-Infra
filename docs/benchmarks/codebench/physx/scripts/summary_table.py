"""Collect the physx*/ result JSONs into one markdown table."""
import json
from pathlib import Path
root = Path(__file__).resolve().parents[2]
print("| label | case | moved | down | causal moved / max path (m) | non-causal diff | ball path err mean / final (m) | final pos err mean (m) | contacts base/causal | sim s base/causal/non |")
print("|---|---|---|---|---|---|---|---|---|---|")
for d in sorted(root.glob("physx*")):
    for c in ("B_01", "B_03"):
        f = d / f"{c}.json"
        if not f.exists():
            continue
        r = json.loads(f.read_text()); b, k, ch, o, t = r["baseline"], r["causal"], r["checks"], r["vs_original_bullet"], r["timing"]
        print(f"| {d.name} | {c} | {b['moved']}/{b['of']} | {len(b['down'])} | {k['moved']} / {k['max_path_displacement']:.2g} | {ch['noncausal_max_diff']:.0g} | "
              f"{o['ball_path_err_mean']:.3f} / {o['ball_final_err']:.3f} | {o['final_pos_err_mean']:.3f} | {b['contacts']}/{k['contacts']} | "
              f"{t['baseline']['sim_s']:.1f}/{t['causal']['sim_s']:.1f}/{t['noncausal']['sim_s']:.1f} |")
        if b["down"] or k["down"]:
            print(f"|  |  | down base: {','.join(x[4:] for x in b['down'])}; causal: {','.join(x[4:] for x in k['down'])} |||||||||")
