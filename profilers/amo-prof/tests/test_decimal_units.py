"""Sizes are decimal SI throughout the report (1 GB = 1e9 bytes)."""
import pytest

import validate_report as vr
from amoprof.report.metric_kernels import (
    GIB_TO_GB, collector_gb, gb_from_bytes, gb_from_gib, gb_from_kib, gb_from_mib,
    kb_from_bytes, mb_from_bytes)


def test_conversions_are_decimal():
    assert gb_from_bytes(9_367_000_000) == pytest.approx(9.367)
    assert gb_from_mib(40_960) == pytest.approx(42.949673, rel=1e-6)     # A100 "40 GB" = 40 GiB
    assert gb_from_kib(1_048_576) == pytest.approx(1.073741824)
    assert gb_from_gib(1) == pytest.approx(GIB_TO_GB) == pytest.approx(1.073741824)
    assert mb_from_bytes(3_000_000) == 3.0
    assert kb_from_bytes(560 * 1024) == pytest.approx(573.44)          # "560 KB/token" was KiB


def test_collector_fields_converted_from_their_true_unit():
    assert collector_gb("total_gb", 1.0) == pytest.approx(1.073741824)  # /proc/meminfo KiB/1024/1024
    assert collector_gb("bpf_mmap_bytes_gb", 1.0) == 1.0                # already decimal
    # SMART data units are 512,000 bytes; the collector used 512*1024 then /1024**3.
    units = 1_000_000
    written = units * 512 * 1024 / 1024 ** 3
    assert collector_gb("host_written_gb", written) == pytest.approx(units * 512_000 / 1e9)


def test_kv_generated_tokens_to_gb_matches_ticket():
    # 16,334,977 tokens x 560 KiB/token is 9,367 GB; the KPI printed 8,688.1 "GB" (GiB).
    assert gb_from_bytes(16_334_977 * 560 * 1024) == pytest.approx(9_367.1, abs=0.1)


def _tiles(*pairs):
    return "".join(f'<div class="kpi-label">{l}</div><div class="kpi-value">{v}</div>'
                   f'<div class="kpi-note">n</div>' for l, v in pairs)


def _fails(html, name):
    return any(name in f for f in vr.validate_html(html, "t").failures)


def test_validator_flags_binary_unit_tiles():
    html = _tiles(("HBM", "40.0 GiB"), ("A", "1"), ("B", "2"), ("C", "3"))
    assert _fails(html, "decimal units")
    assert not _fails(_tiles(("HBM", "42.9 GB"), ("A", "1"), ("B", "2"), ("C", "3")), "decimal units")


def test_validator_flags_kv_generated_mismatch():
    finding = "<p>KV generated in the run = 1 computed prompt + 2 output tokens = 3 tokens (≈ 9,367.3 GB at 573 KB/token).</p>"
    bad = _tiles(("KV cache generated this run", "8,688.1 GB"), ("A", "1"), ("B", "2"), ("C", "3")) + finding
    good = _tiles(("KV cache generated this run", "9,367.3 GB"), ("A", "1"), ("B", "2"), ("C", "3")) + finding
    assert _fails(bad, "KV generated agrees")
    assert not _fails(good, "KV generated agrees")
