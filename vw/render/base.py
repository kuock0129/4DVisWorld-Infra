"""Render adapter contract. Renderers read IR + SimResult only, never engine state."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from vw.ir import SceneIR
from vw.physics.base import Device, SimResult


class RenderPass(str, Enum):
    RGB = "rgb"
    DEPTH = "depth"
    INSTANCE_SEG = "instance_seg"  # required for removal masks
    FLOW = "flow"
    NORMALS = "normals"


@dataclass(frozen=True)
class RenderCapabilities:
    passes: frozenset[RenderPass]
    devices: frozenset[Device]


@dataclass(frozen=True)
class RenderBackendInfo:
    name: str
    version: str
    device: Device
    seed: int  # must be identical for both members of a pair
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class RenderResult:
    outputs: dict[RenderPass, Path]  # pass -> directory / file of frames
    backend: RenderBackendInfo


@runtime_checkable
class RenderAdapter(Protocol):
    name: str
    capabilities: RenderCapabilities

    def render(self, ir: SceneIR, sim: SimResult, passes: list[str], out: Path) -> RenderResult: ...
