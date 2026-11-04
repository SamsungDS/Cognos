"""HBM composition bands must partition the device."""
import pytest

from amoprof.report.metric_kernels import resolve_hbm_breakdown

KV_KB = 960.0                         # KiB per token, as the resolver returns it
GB_PER_TOKEN = KV_KB * 1024 / 1e9     # decimal GB, the report's unit


def _bands(b):
    return (b["weights_gb"] + b["kv_active_gb"] + b["kv_free_gb"]
            + b["residual_gb"] + b["free_gb"])


def test_ticket_numbers_kv_in_use_counted_once_without_pool_size():
    # B200 179 GB, TP 2, 81.6 GB used, 31 GB weights, 35 GB KV in use, and
    # max_total_num_tokens not exported (pool = 0) — the reported case.
    b = resolve_hbm_breakdown(
        hbm={"per_gpu_total_gb": 179.1, "per_gpu_used_gb": 81.6},
        kv={"kb": KV_KB}, used_tokens=35.0 / GB_PER_TOKEN * 2,
        params_b=31.0, weight_dtype_bytes=2, tp_size=2)
    assert b["kv_pool_gb"] == 0.0
    assert b["kv_active_gb"] == pytest.approx(35.0)
    assert b["residual_gb"] == pytest.approx(15.6)          # was 50.6
    assert b["free_gb"] == pytest.approx(97.5)
    assert _bands(b) == pytest.approx(179.1)                # was 214.1
    assert b["consistent"]


def test_known_pool_contains_kv_in_use():
    # Pool 60 GB of which 35 GB occupied: residual excludes the whole pool,
    # and KV in use + reserved-free = pool, so nothing is counted twice.
    b = resolve_hbm_breakdown(
        hbm={"per_gpu_total_gb": 179.1, "per_gpu_used_gb": 120.0},
        kv={"kb": KV_KB}, max_total_tokens=60.0 / GB_PER_TOKEN * 2,
        used_tokens=35.0 / GB_PER_TOKEN * 2, params_b=31.0, tp_size=2)
    assert b["kv_pool_gb"] == pytest.approx(60.0)
    assert b["kv_active_gb"] + b["kv_free_gb"] == pytest.approx(60.0)
    assert b["residual_gb"] == pytest.approx(120.0 - 31.0 - 60.0)
    assert _bands(b) == pytest.approx(179.1)


def test_kv_exceeding_used_is_flagged_not_hidden():
    b = resolve_hbm_breakdown(
        hbm={"per_gpu_total_gb": 40.0, "per_gpu_used_gb": 20.0},
        kv={"kb": KV_KB}, used_tokens=30.0 / GB_PER_TOKEN, params_b=0.0)
    assert b["residual_gb"] == 0.0
    assert not b["consistent"] and "exceed" in b["note"]
