# 4DVisWorld-Infra

Simulator-agnostic infrastructure for generating physically consistent counterfactual video tuples. A coding agent reconstructs a source video as executable scene code. That code is converted to a canonical **Scene IR**, interventions such as object removal are applied to the IR, and a real physics backend re-simulates the result. Each sample is a baseline, a causal counterfactual, a non-causal counterfactual, and masks, all checked at the code level. Every layer talks through adapters that exchange only the Scene IR and a `SimResult`, so backends (MuJoCo, Newton, PhysX, Bullet via Blender) and renderers can be swapped freely. See [ROADMAP.md](ROADMAP.md) for milestones and [docs/HANDOFF.md](docs/HANDOFF.md) for the full design.

## Status: M0 (contracts)

| Module | What's there |
|---|---|
| `vw/ir` | pydantic Scene IR v0.1: SI units, Z-up, quaternions in wxyz order, `physical` / `trace` levels, strict validation, content hash. Dimensions are named per shape: box/plane `extents` are **full** edge lengths in m |
| `vw/physics` | `PhysicsAdapter` protocol, `SimResult`, `Capabilities`, fail-loud `check()` |
| `vw/render` | `RenderAdapter` protocol, render passes, `RenderResult` |
| `vw/importers`, `vw/exporters` | `Importer` / `Exporter` protocols |
| `vw/interventions` | `remove()`: deletes bodies from the IR (no hidden colliders left behind) |
| `vw/registry.py` | adapter registry, `--device auto\|cpu\|gpu` resolution, capability routing |
| `vw/manifest.py` | per-tuple manifest (seeds, backends, device, hardware, token usage); enforces the same physics and render backend, device and seed across all members of a tuple |
| adapters | `mujoco` compile is real (IR → MJCF, kinematic bodies → mocap), simulate in M1; `newton`, `physx`, `bullet_blender`, `blender_cycles`, `blender_eevee` are stubs; `replay` is fully implemented |

## Quickstart

```bash
pip install -e ".[dev]"
vw validate examples/remove_support.json
vw check examples/remove_support.json      # which backends can simulate it
vw backends
pytest
```
