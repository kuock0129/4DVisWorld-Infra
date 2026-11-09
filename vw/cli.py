"""vw command line.

    vw validate scene.json            validate a Scene IR file
    vw check scene.json [--device D]  which physics backends can handle it
    vw backends                       list registered adapters
    vw bench [--quick] [--out DIR]    M2 physics benchmark -> DIR/results.{json,md}, plot
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from vw import registry
from vw.ir import SceneIR
from vw.physics.base import required_features


def _load(path: str) -> SceneIR | None:
    try:
        return SceneIR.load(path)
    except ValidationError as e:
        print(f"INVALID {path}\n{e}", file=sys.stderr)
    except (OSError, ValueError) as e:
        print(f"ERROR {path}: {e}", file=sys.stderr)
    return None


def cmd_validate(args: argparse.Namespace) -> int:
    ok = True
    for p in args.paths:
        ir = _load(p)
        if ir is None:
            ok = False
            continue
        print(f"OK {p}  level={ir.level.value} bodies={len(ir.bodies)} frames={ir.timing.frames} {ir.content_hash()}")
    return 0 if ok else 1


def cmd_check(args: argparse.Namespace) -> int:
    ir = _load(args.path)
    if ir is None:
        return 1
    req = sorted(f.value for f in required_features(ir))
    print(f"{Path(args.path).name}: requires {req}")
    any_ok = False
    for name, problems in registry.compatible_physics(ir, device=args.device).items():
        if problems:
            print(f"  REFUSE {name}: {'; '.join(problems)}")
        else:
            any_ok = True
            print(f"  OK     {name}")
    return 0 if any_ok else 2


def cmd_backends(args: argparse.Namespace) -> int:
    print("devices present:", ", ".join(d.value for d in registry.available_devices()))
    print("physics:", ", ".join(registry.physics_backends()))
    print("render: ", ", ".join(registry.render_backends()))
    return 0


def cmd_bench(args: argparse.Namespace) -> int:
    from vw.benchmark.report import write_report
    from vw.benchmark.runner import DEFAULT_CONFIGS, QUICK_CONFIGS, run_benchmark

    res = run_benchmark(QUICK_CONFIGS if args.quick else DEFAULT_CONFIGS, repeats=args.repeats,
                        example=Path(args.example))
    for p in write_report(res, Path(args.out)):
        print("wrote", p)
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="vw", description="4DVisWorld-Infra")
    sub = ap.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("validate", help="validate Scene IR JSON files")
    v.add_argument("paths", nargs="+")
    v.set_defaults(fn=cmd_validate)

    c = sub.add_parser("check", help="capability check against all physics backends")
    c.add_argument("path")
    c.add_argument("--device", default="auto", choices=["auto", "cpu", "gpu", "cuda", "metal"])
    c.set_defaults(fn=cmd_check)

    b = sub.add_parser("backends", help="list registered adapters")
    b.set_defaults(fn=cmd_backends)

    bn = sub.add_parser("bench", help="run the M2 physics benchmark")
    bn.add_argument("--quick", action="store_true", help="two configs only")
    bn.add_argument("--repeats", type=int, default=3, help="wall-clock = min over N runs")
    bn.add_argument("--out", default="docs/benchmarks")
    bn.add_argument("--example", default="examples/remove_support.json")
    bn.set_defaults(fn=cmd_bench)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
