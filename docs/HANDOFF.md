# 4DVisWorld-Infra — Design Handoff

## Project in one paragraph
Build an open-source, physically consistent dataset (target 50K–100K) of **counterfactual video tuples**. A coding agent reconstructs a scene from a source video as executable code (4DCodeBench-style). The scene is converted to a canonical **Scene IR**. Interventions (first task: **object removal**) are applied to the IR. An accurate physics backend re-simulates it, a renderer renders it, and code-level checks verify the result. Each sample is a tuple: baseline, causal counterfactual (re-simulated), and non-causal counterfactual (baseline poses replayed without the removed object), plus masks. The API design follows Kubric (Scene / Asset / View / worker), but the code is new: Kubric is tied to PyBullet + Blender 2.93 and has no interventions.

## Core principle: simulator-agnostic, adapter-based
Layers exchange only two data structures: **Scene IR** (JSON) and **SimResult**. Blender is optional in every layer.

```
Source video → coding agent (4DCodeBench harness)
  → Front-end adapters (authoring → IR): bpy_script (headless Blender) | our SDK | Code-as-World scene.json
  → Scene IR (canonical JSON, level = physical | trace)
  → Intervention engine (baseline + CF variants, parameter/camera perturbations)
  → Physics adapters (check → compile → simulate): MuJoCo (CPU) | Newton/MuJoCo Warp (GPU) | PhysX | Bullet via Blender
  → SimResult (keyframes + contact events)
  → Render adapters (read IR + SimResult only): Blender Cycles | Blender EEVEE | others later
  → Verify (Stage 1: fidelity vs source video; Stage 2: code checks) — on failure, return to the agent for repair
  → Export: tuple folder | 4dcodebench_task | caw_scene_json | usd
```

## Two stages
- **Stage 1: reconstruction.** One agent run per video. The agent writes a bpy script in the 4DCodeBench harness, with an extra prompt rule: dynamic objects must use a Blender rigid body, not keyframes. The `bpy_script` importer runs it headless and reads the scene state into IR. Then:
  - re-simulate in MuJoCo;
  - tune a few parameters (mass ratio, friction, restitution) with CMA-ES or grid search;
  - run a fidelity check against the source video (DINOv3 similarity, dynamic IoU, tracks, depth).
- **Stage 2: counterfactual generation.** No LLM. Interventions × perturbations give ×N tuples per scene. Pair consistency comes from simulating both members of a pair from the same IR on the same backend and device, so it does not depend on how accurate the reconstruction is.

## Key contracts (M0)
```python
class PhysicsAdapter(Protocol):
    name: str
    capabilities: Capabilities              # rigid/articulated/deformable, devices: cpu/cuda/metal
    def check(self, ir: SceneIR) -> list[str]: ...   # unsupported features; non-empty => refuse
    def compile(self, ir: SceneIR) -> NativeScene: ...  # IR -> MJCF / USD / URDF / bpy scene
    def simulate(self, native, kinematic: dict[str, Trajectory] | None = None) -> SimResult: ...
    def param_map(self) -> dict: ...         # IR param -> engine param mapping + approximations, written to manifest

class RenderAdapter(Protocol):
    def render(self, ir: SceneIR, sim: SimResult, passes: list[str], out: Path) -> RenderResult: ...
    # passes: rgb, depth, instance_seg (required for masks), flow, normals

@dataclass
class SimResult:
    fps: int
    poses: dict[str, np.ndarray]       # obj_id -> (T, 7) pos + quat
    velocities: dict[str, np.ndarray]
    contacts: list[ContactEvent]       # t, obj_a, obj_b, point, impulse
    backend: BackendInfo               # name, version, solver config, device
```

## Scene IR rules
1. The IR stores physical semantics only: SI units, mass, friction, restitution, geometry (primitive, or mesh plus collision mesh), body kind (`dynamic` / `static` / `kinematic` with trajectory), initial state, cameras, lights, gravity, fps/frames, and `ir_version`.
2. Solver parameters (substeps, iterations, margins) belong in adapter config, never in the IR.
3. `level: physical` can be re-simulated and supports causal interventions. `level: trace` has geometry and per-frame poses only, so it supports rendering and non-causal interventions.
4. Interventions operate on the IR only, which is what lets them work with any backend.
5. Capability checks fail loudly. Never silently ignore an unsupported feature.

## bpy_script importer mapping (M3)
| Blender | IR |
|---|---|
| `rigid_body.type == 'ACTIVE'` | dynamic body: mass, friction, restitution, collision_shape, damping |
| `rigid_body.type == 'PASSIVE'` | static collider |
| keyframed object, no rigid body | kinematic body with baked trajectory |
| `rigid_body.kinematic` released at frame k | initial velocity from the keyframes before release, then dynamic |
| cloth / fluid / particles / fracture | flag as unsupported; trace-level IR or reject |

## Removal tuple + masks (M1)
- Causal: delete the object, then re-simulate.
- Non-causal: delete the object, then replay the baseline poses of all other objects as kinematic.
- Masks:
  - removed-object mask from instance segmentation;
  - affected region from objects whose trajectories diverge between baseline and causal;
  - shadows and reflections from pixel differences between baseline and non-causal that fall outside the object mask.
- Code checks:
  - the scene is at rest at t=0 when nothing is changed;
  - causal tuples must diverge and non-causal tuples must not;
  - penetration stays below a threshold;
  - energy never increases;
  - non-causal pixel changes stay inside the masks.

## CPU / GPU
- Device is chosen by config (`--device auto|cpu|gpu`), never hard-coded.
- All members of one tuple must be generated on the same device and backend; the manifest records both.
- Work splits naturally: CPU-only contributors run Stage 1 (API-bound), and GPU machines run the Stage 2 render plus Newton batch.
- Rendering is the main bottleneck. Use EEVEE or low-sample Cycles for development, Cycles GPU plus denoise for production, and a fixed render seed for both members of a pair.

## Repo layout
```
vw/
  sdk/  ir/  interventions/  physics/  render/  importers/  exporters/  verify/  cli.py
tests/  docker/  docs/  examples/
```
