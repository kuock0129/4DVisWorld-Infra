"""Render adapter stubs (Blender Cycles / EEVEE). Implemented in a later milestone."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from vw.ir import SceneIR
from vw.physics.base import Device, SimResult
from vw.registry import register_render, resolve_device
from vw.render.base import RenderBackendInfo, RenderCapabilities, RenderPass, RenderResult

_ALL_PASSES = frozenset(RenderPass)


class _BlenderStub:
    name = ""
    capabilities: RenderCapabilities

    def __init__(self, device: str = "auto", seed: int = 0, **config: Any):
        self.device = resolve_device(device, self.capabilities.devices)
        self.seed = seed
        self.config = config

    def backend_info(self) -> RenderBackendInfo:
        return RenderBackendInfo(self.name, "unimplemented", self.device, self.seed, dict(self.config))

    def check_passes(self, passes: list[str]) -> list[str]:
        bad = []
        for p in passes:
            try:
                rp = RenderPass(p)
            except ValueError:
                bad.append(f"unknown pass: {p}")
                continue
            if rp not in self.capabilities.passes:
                bad.append(f"unsupported pass: {p}")
        return bad

    def render(self, ir: SceneIR, sim: SimResult, passes: list[str], out: Path) -> RenderResult:
        problems = self.check_passes(passes)
        if problems:
            raise ValueError(f"{self.name}: " + "; ".join(problems))
        raise NotImplementedError(f"{self.name}.render is a stub")


@register_render("blender_cycles")
class BlenderCyclesAdapter(_BlenderStub):
    name = "blender_cycles"
    capabilities = RenderCapabilities(_ALL_PASSES, frozenset({Device.CPU, Device.CUDA, Device.METAL}))


@register_render("blender_eevee")
class BlenderEeveeAdapter(_BlenderStub):
    """Fast dev renderer. No flow pass."""

    name = "blender_eevee"
    capabilities = RenderCapabilities(
        _ALL_PASSES - {RenderPass.FLOW}, frozenset({Device.CPU, Device.CUDA, Device.METAL})
    )
