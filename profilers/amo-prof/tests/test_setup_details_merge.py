import json
from types import SimpleNamespace

from amoprof.cli import _copy_setup_details


def _args(src, override=False):
    return SimpleNamespace(setup_details=str(src), setup_details_override=override)


def test_manual_setup_fills_model_only_stub(tmp_path):
    # prom-only analyze: --model-path writes a {Model, Model path} stub before
    # --setup-details is copied; the manual TP/GPU fields must still land.
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "setup_details.json").write_text(json.dumps(
        {"Model": "google/gemma-4-31b-it", "Model path": "google/gemma-4-31b-it"}))
    src = tmp_path / "manual.json"
    src.write_text(json.dumps({"Model": "gemma4", "TP size": 8, "DP size": 1,
                               "GPU Count": 8, "Engine": "unknown"}))

    _copy_setup_details(_args(src), raw)

    sd = json.loads((raw / "setup_details.json").read_text())
    assert sd["Model"] == "google/gemma-4-31b-it"   # existing value wins
    assert sd["TP size"] == 8 and sd["DP size"] == 1 and sd["GPU Count"] == 8
    assert "Engine" not in sd                       # placeholder not copied


def test_existing_unknown_is_filled_and_override_replaces(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    dst = raw / "setup_details.json"
    dst.write_text(json.dumps({"TP size": "unknown", "Host": "a"}))
    src = tmp_path / "manual.json"
    src.write_text(json.dumps({"TP size": 4, "Host": "b"}))

    _copy_setup_details(_args(src), raw)
    assert json.loads(dst.read_text()) == {"TP size": 4, "Host": "a"}

    _copy_setup_details(_args(src, override=True), raw)
    assert json.loads(dst.read_text()) == {"TP size": 4, "Host": "b"}


def test_report_filename_ignores_bind_address_host(tmp_path):
    from datetime import datetime
    from amoprof.cli import report_filename
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "setup_details.json").write_text(json.dumps(
        {"Host": "0.0.0.0", "Model": "gemma"}))
    (raw / "gpu_config.json").write_text(json.dumps({"hostname": "msl-ssg-dgx1.msl.lab"}))
    name = report_filename(raw, "combined", when=datetime(2026, 1, 1))
    assert "_msl-ssg-dgx1_" in name and "_0_" not in name
