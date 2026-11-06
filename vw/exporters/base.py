"""Export contract: a finished tuple folder -> another format."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from vw.manifest import Manifest


@runtime_checkable
class Exporter(Protocol):
    name: str  # e.g. "tuple_folder", "4dcodebench_task", "caw_scene_json", "usd"

    def export(self, manifest: Manifest, sample_dir: Path, out: Path) -> Path:
        """Write the export under ``out`` and return its path. Must not modify ``sample_dir``."""
        ...
