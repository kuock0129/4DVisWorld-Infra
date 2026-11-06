"""Object removal on the IR.

The removed bodies are deleted from the IR, not hidden: a hidden body would keep
its collider and still produce contacts. The causal / non-causal tuple assembly
(re-simulate vs. replay baseline poses as kinematic) is built on top of this in M1.
"""

from __future__ import annotations

from vw.ir import SceneIR


def remove(ir: SceneIR, targets: list[str]) -> SceneIR:
    """Return a new IR with ``targets`` deleted. The input IR is not modified."""
    if not targets:
        raise ValueError("remove: no targets given")
    known = {b.id for b in ir.bodies}
    missing = sorted(set(targets) - known)
    if missing:
        raise KeyError(f"remove: unknown body ids {missing}")

    data = ir.model_dump(mode="python")
    data["bodies"] = [b for b in data["bodies"] if b["id"] not in set(targets)]
    history = list(data["metadata"].get("interventions", []))
    history.append({"type": "remove", "targets": sorted(targets)})
    data["metadata"] = {**data["metadata"], "interventions": history}
    return SceneIR.model_validate(data)
