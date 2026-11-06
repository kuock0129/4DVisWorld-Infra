"""Capability registry: name -> adapter factory, plus device resolution and selection."""

from __future__ import annotations

import os
import platform
import shutil
from typing import Callable, TypeVar

from vw.ir import SceneIR
from vw.physics.base import Device, PhysicsAdapter
from vw.render.base import RenderAdapter

PhysicsFactory = Callable[..., PhysicsAdapter]
RenderFactory = Callable[..., RenderAdapter]

_PHYSICS: dict[str, PhysicsFactory] = {}
_RENDER: dict[str, RenderFactory] = {}

F = TypeVar("F", bound=Callable)


def register_physics(name: str) -> Callable[[F], F]:
    def deco(factory: F) -> F:
        if name in _PHYSICS:
            raise ValueError(f"physics adapter '{name}' already registered")
        _PHYSICS[name] = factory
        return factory

    return deco


def register_render(name: str) -> Callable[[F], F]:
    def deco(factory: F) -> F:
        if name in _RENDER:
            raise ValueError(f"render adapter '{name}' already registered")
        _RENDER[name] = factory
        return factory

    return deco


def physics_backends() -> list[str]:
    _ensure_builtin()
    return sorted(_PHYSICS)


def render_backends() -> list[str]:
    _ensure_builtin()
    return sorted(_RENDER)


def available_devices() -> list[Device]:
    """Devices present on this machine. Override with VW_DEVICES=cpu,cuda for testing / CI."""
    env = os.environ.get("VW_DEVICES")
    if env:
        return [Device(d.strip()) for d in env.split(",") if d.strip()]
    devs = [Device.CPU]
    if shutil.which("nvidia-smi"):
        devs.insert(0, Device.CUDA)
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        devs.insert(0, Device.METAL)
    return devs


def resolve_device(requested: str, supported: frozenset[Device]) -> Device:
    """Map ``--device auto|cpu|gpu|cuda|metal`` to a concrete device the adapter supports."""
    present = available_devices()
    if requested == "auto":
        candidates = present
    elif requested == "gpu":
        candidates = [d for d in present if d is not Device.CPU]
    else:
        candidates = [Device(requested)] if Device(requested) in present else []
    for d in candidates:
        if d in supported:
            return d
    raise RuntimeError(
        f"no usable device for --device {requested}: present={[d.value for d in present]}, "
        f"adapter supports={sorted(d.value for d in supported)}"
    )


def get_physics(name: str, device: str = "auto", **config) -> PhysicsAdapter:
    _ensure_builtin()
    if name not in _PHYSICS:
        raise KeyError(f"unknown physics backend '{name}'; known: {physics_backends()}")
    return _PHYSICS[name](device=device, **config)


def get_render(name: str, device: str = "auto", **config) -> RenderAdapter:
    _ensure_builtin()
    if name not in _RENDER:
        raise KeyError(f"unknown render backend '{name}'; known: {render_backends()}")
    return _RENDER[name](device=device, **config)


def compatible_physics(ir: SceneIR, device: str = "auto") -> dict[str, list[str]]:
    """Backend name -> problems ([] means it can handle ``ir`` on ``device``)."""
    out: dict[str, list[str]] = {}
    for name in physics_backends():
        try:
            out[name] = get_physics(name, device=device).check(ir)
        except RuntimeError as e:  # no usable device
            out[name] = [str(e)]
    return out


_LOADED = False


def _ensure_builtin() -> None:
    global _LOADED
    if not _LOADED:
        _LOADED = True
        import vw.physics.stubs  # noqa: F401  (registers on import)
        import vw.render.stubs  # noqa: F401
