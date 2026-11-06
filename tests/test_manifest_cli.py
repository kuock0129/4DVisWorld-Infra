import pytest
from pydantic import ValidationError

from vw.cli import main
from vw.manifest import Manifest

H = "sha256:" + "0" * 64
PHYS = {"name": "mujoco", "version": "3.2.0", "device": "cpu", "solver_config": {"timestep": 0.002}}
REND = {"name": "blender_cycles", "version": "4.2", "device": "cuda", "seed": 0}


def _manifest(**over):
    m = {
        "sample_id": "remove_support-000",
        "ir_version": "0.1",
        "intervention": {"type": "remove", "targets": ["support"]},
        "members": [
            {"role": r, "ir_path": f"{r}.json", "ir_hash": H, "physics": PHYS, "render": REND}
            for r in ("baseline", "causal", "noncausal")
        ],
    }
    m.update(over)
    return m


def test_manifest_valid_and_roundtrip(tmp_path):
    m = Manifest.model_validate(_manifest())
    p = tmp_path / "manifest.json"
    m.save(p)
    assert Manifest.load(p) == m
    assert m.passed  # no checks yet


def test_manifest_rejects_mixed_backends():
    m = _manifest()
    m["members"][1]["physics"] = {**PHYS, "device": "cuda"}
    with pytest.raises(ValidationError, match="share physics"):
        Manifest.model_validate(m)


def test_manifest_rejects_mixed_render_seed():
    m = _manifest()
    m["members"][2]["render"] = {**REND, "seed": 1}
    with pytest.raises(ValidationError, match="seed"):
        Manifest.model_validate(m)


def test_manifest_requires_baseline_and_unique_roles():
    m = _manifest()
    m["members"][0]["role"] = "causal"
    with pytest.raises(ValidationError, match="duplicate member roles"):
        Manifest.model_validate(m)
    m = _manifest()
    m["members"] = m["members"][1:]
    with pytest.raises(ValidationError, match="baseline"):
        Manifest.model_validate(m)


def test_manifest_checks_drive_passed():
    m = Manifest.model_validate(
        _manifest(checks=[{"name": "noncausal_no_divergence", "passed": False, "value": 0.3, "threshold": 0.0}])
    )
    assert not m.passed


def test_cli_validate(example_path, capsys):
    assert main(["validate", str(example_path)]) == 0
    assert "OK" in capsys.readouterr().out


def test_cli_validate_bad(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text('{"level": "physical", "bodies": []}')
    assert main(["validate", str(bad)]) == 1
    assert "INVALID" in capsys.readouterr().err


def test_cli_check(example_path, capsys):
    assert main(["check", str(example_path)]) == 0
    out = capsys.readouterr().out
    assert "OK     mujoco" in out and "REFUSE replay" in out


def test_cli_backends(capsys):
    assert main(["backends"]) == 0
    assert "mujoco" in capsys.readouterr().out


def test_manifest_hardware_and_usage():
    m = Manifest.model_validate(
        _manifest(
            hardware={"os": "Windows 11", "cpu": "x86_64", "gpu": "RTX 4090", "ram_gb": 64},
            usage={"agent_framework": "claude-code", "model": "claude-opus-5-5", "input_tokens": 120000,
                   "output_tokens": 8000, "cost_usd": 1.2, "runtime_s": 340},
            seeds={"perturbation": 3},
            contributor="kuock0129",
        )
    )
    assert m.usage.input_tokens == 120000 and m.hardware.gpu == "RTX 4090"
    with pytest.raises(ValidationError):
        Manifest.model_validate(_manifest(usage={"input_tokens": -1}))


def test_import_export_protocols_importable():
    from vw.exporters import Exporter
    from vw.importers import Importer

    class _Imp:
        name = "dummy"

        def can_import(self, source):
            return False

        def load(self, source, **options):
            raise NotImplementedError

    assert isinstance(_Imp(), Importer) and not isinstance(_Imp(), Exporter)
