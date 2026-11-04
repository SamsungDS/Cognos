"""The Inference Cache Tier line names every KV layer, its memory type and capacity."""
import json
import pathlib
import re
import sys

import validate_report as vr
from amoprof.report.combined import build_executive_summary_html

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from test_l35_report_consistency import _mk  # noqa: E402

GB = lambda b: f"{b / 1e9:,.0f} GB"                     # noqa: E731
KV_BYTES = 60 * 16 * 256 * 2 * 2                        # fixture model: 983,040 B/token


def _tier_line(raw_dir, run="t"):
    html = build_executive_summary_html(raw_dir.parent, run_label=run)
    m = re.search(r"Inference Cache Tier</b>: ([^<]+)", html)
    return m.group(1).replace("&amp;", "&") if m else ""


def _with_setup(raw, **extra):
    p = raw / "setup_details.json"
    d = json.loads(p.read_text())
    d.update(extra)
    p.write_text(json.dumps(d))
    return raw


def test_l35_run_lists_every_layer_with_type_and_capacity(tmp_path):
    line = _tier_line(_mk(tmp_path / "l35"))
    assert line.startswith("Enabled · L1 (HBM: ")
    assert f"L1 (HBM: {GB(196_153 * KV_BYTES)})" in line           # KV pool
    # HiCache allocation (host-total gauge x KV bytes), not the host's 1,082 GB of DRAM.
    assert f"+ L2 (DRAM: {GB(392_307 * KV_BYTES)})" in line
    # The store reports memory and file capacity but not DRAM vs CXL.
    assert "L3.5 (memory: 537 GB [DRAM/CXL split not reported] + NVMe SSD: 2,000 GB)" in line
    assert "L3 (NVMe SSD" not in line                              # no local L3 on a remote run


def test_setup_split_distinguishes_dram_from_dram_plus_cxl(tmp_path):
    dram = _tier_line(_with_setup(_mk(tmp_path / "d"), **{"L3.5 DRAM GB": 537}))
    cxl = _tier_line(_with_setup(_mk(tmp_path / "c"), **{"L3.5 DRAM GB": 400, "L3.5 CXL GB": 137}))
    assert "L3.5 (DRAM: 537 GB + NVMe SSD: 2,000 GB)" in dram
    assert "L3.5 (DRAM: 400 GB + CXL: 137 GB + NVMe SSD: 2,000 GB)" in cxl
    assert "≠ measured" not in cxl                                # 400 + 137 matches 537


def test_setup_split_that_disagrees_with_the_store_is_flagged(tmp_path):
    line = _tier_line(_with_setup(_mk(tmp_path / "x"), **{"L3.5 DRAM GB": 300, "L3.5 CXL GB": 100}))
    assert "[setup DRAM + CXL 400 GB ≠ measured memory 537 GB]" in line


def test_local_run_shows_l3_nvme_and_no_l35(tmp_path):
    line = _tier_line(_mk(tmp_path / "file", backend="file"))
    assert "L1 (HBM: " in line and "L3 (NVMe SSD: " in line
    assert "L3.5" not in line


def test_validator_requires_typed_layers():
    ok = "<b>Inference Cache Tier</b>: Enabled · L1 (HBM: 193 GB) + L2 (DRAM: 386 GB)"
    bad = "<b>Inference Cache Tier</b>: Enabled · L2 DRAM (209 GB) + L3.5 (537 GB DRAM)"
    def failed(h):
        return any("Inference Cache Tier" in f for f in vr.validate_html(h * 3, "t").failures)
    assert not failed(ok)
    assert failed(bad)
