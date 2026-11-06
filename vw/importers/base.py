"""Front-end contract: authoring format -> Scene IR."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from vw.ir import SceneIR


@runtime_checkable
class Importer(Protocol):
    name: str  # e.g. "bpy_script", "sdk", "caw_scene_json"

    def can_import(self, source: Path) -> bool:
        """Cheap sniff (extension / header). Must not execute the source."""
        ...

    def load(self, source: Path, **options: Any) -> SceneIR:
        """Produce a validated IR. Unsupported features (cloth, fluid, ...) must raise or
        downgrade to level=trace explicitly; never drop them silently."""
        ...
