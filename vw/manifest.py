"""Per-tuple manifest schema (manifest.json inside each exported tuple folder).

Enforces the pair-consistency rule: every member of a tuple is simulated on the
same physics backend/version/device/solver config and rendered with the same
renderer/version/device/seed. The non-causal member uses the same physics backend
with the remaining bodies passed as ``kinematic`` overrides.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

MANIFEST_VERSION = "0.1"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Role(str, Enum):
    BASELINE = "baseline"
    CAUSAL = "causal"
    NONCAUSAL = "noncausal"


class PhysicsRecord(_Model):
    name: str
    version: str
    device: str
    solver_config: dict[str, Any] = {}


class RenderRecord(_Model):
    name: str
    version: str
    device: str
    seed: int
    config: dict[str, Any] = {}


class Member(_Model):
    role: Role
    ir_path: str
    ir_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    physics: PhysicsRecord
    render: RenderRecord | None = None
    outputs: dict[str, str] = Field(default_factory=dict, description="pass name -> relative path")


class Intervention(_Model):
    type: str = Field(description="e.g. 'remove'")
    targets: list[str] = Field(min_length=1)
    params: dict[str, Any] = {}


class Hardware(_Model):
    os: str = ""
    cpu: str = ""
    gpu: str | None = None
    ram_gb: float | None = None


class Usage(_Model):
    """Cost of producing the sample (Stage 1 agent run + Stage 2 compute)."""

    agent_framework: str | None = None
    model: str | None = None
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cost_usd: float | None = Field(default=None, ge=0.0)
    runtime_s: float | None = Field(default=None, ge=0.0)


class CheckResult(_Model):
    name: str
    passed: bool
    value: float | None = None
    threshold: float | None = None
    detail: str = ""


class Manifest(_Model):
    manifest_version: str = MANIFEST_VERSION
    sample_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ir_version: str
    source: dict[str, Any] = Field(default_factory=dict, description="source video, agent run id, ...")
    intervention: Intervention
    members: list[Member]
    masks: dict[str, str] = Field(
        default_factory=dict, description="removed_object | affected_region | shadow_reflection -> path"
    )
    param_map: dict[str, Any] = Field(default_factory=dict, description="from PhysicsAdapter.param_map()")
    seeds: dict[str, int] = Field(default_factory=dict, description="perturbation / sampler seeds")
    hardware: Hardware | None = None
    usage: Usage | None = None
    contributor: str | None = None
    checks: list[CheckResult] = []

    @model_validator(mode="after")
    def _consistency(self) -> Manifest:
        roles = [m.role for m in self.members]
        if len(set(roles)) != len(roles):
            raise ValueError(f"duplicate member roles: {[r.value for r in roles]}")
        if Role.BASELINE not in roles:
            raise ValueError("tuple must include a baseline member")
        if len(self.members) < 2:
            raise ValueError("tuple needs a baseline and at least one counterfactual")

        phys = {m.physics.model_dump_json() for m in self.members}
        if len(phys) > 1:
            raise ValueError("all members must share physics backend, version, device and solver config")
        rendered = [m.render for m in self.members if m.render is not None]
        if rendered and len(rendered) != len(self.members):
            raise ValueError("either all members are rendered or none are")
        if len({r.model_dump_json() for r in rendered}) > 1:
            raise ValueError("all members must share renderer, version, device and seed")
        return self

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @classmethod
    def load(cls, path: str | Path) -> Manifest:
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))

    def save(self, path: str | Path) -> None:
        Path(path).write_text(self.model_dump_json(indent=2), encoding="utf-8")
