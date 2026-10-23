"""A run without an L3 tier says so instead of reporting an idle L3.

SGLang's server_info carries hicache_storage_backend=None on an L1 + L2 run.
The setup file can still list "HiCache storage backend: file" as a defaulted
field and "L3 device" as the disk amoprof monitors; neither is a tier.
"""
import json
import pathlib
import re
import sys

from amoprof.report.combined import build_executive_summary_html
from amoprof.report.l3_backend import resolve_l3_backend

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from test_l35_report_consistency import _mk  # noqa: E402

N = 12
EVICTED = 12_887_944

SI_RAW = {"model_path": "qwen/qwen2.5-72b-instruct", "tp_size": 8,
          "enable_hierarchical_cache": True, "hicache_ratio": 2.0,
          "hicache_storage_backend": None, "hicache_write_policy": "write_through"}


def _setup(**extra):
    d = {"Model": "qwen/qwen2.5-72b-instruct", "TP size": 8,
         "SGLang server_info raw": dict(SI_RAW),
         "L3 device": "/dev/nvme0n1", "SSD device": "/dev/nvme0n1",
         "HiCache path": "sglang_storage", "Hierarchical cache": "enabled",
         "HiCache storage backend": "file",
         "Defaulted fields": "Host, Port, Hierarchical cache, HiCache storage backend"}
    d.update(extra)
    return d


def _mk_l1l2(base):
    raw = base / "raw"
    raw.mkdir(parents=True)
    cols = ["time_sec",
            "sglang_realtime_tokens_total[mode=prefill_cache]",
            "sglang_realtime_tokens_total[mode=prefill_compute]",
            "sglang_realtime_tokens_total[mode=decode]",
            "sglang_hicache_host_used_tokens", "sglang_hicache_host_total_tokens",
            "sglang_max_total_num_tokens",
            "sglang_backuped_tokens_total", "sglang_prefetched_tokens_total",
            "sglang_load_back_tokens_total", "sglang_evicted_tokens_total"]
    rows = []
    for i in range(N):
        f = i / (N - 1)
        rows.append([i * 90.0, int(1_000_000 * f), int(3_000_000 * f), int(400_000 * f),
                     int(300_000 * f), 392_307, 196_153, 0, 0,
                     int(2_000_000 * f), int(EVICTED * f)])
    raw.joinpath("sglang_timeseries.csv").write_text(
        ",".join(cols) + "\n" + "\n".join(",".join(str(v) for v in r) for r in rows) + "\n")
    raw.joinpath("setup_details.json").write_text(json.dumps(_setup()))
    raw.joinpath("model_config.json").write_text(json.dumps(
        {"num_hidden_layers": 80, "num_key_value_heads": 8,
         "head_dim": 128, "torch_dtype": "bfloat16"}))
    raw.joinpath("gpu_summary.json").write_text(json.dumps(
        {"gpu_count": 8, "hbm_used_gb_mean": 33.1, "hbm_total_gb": 40.0,
         "gpu_util_mean": 95.5}))
    # A filesystem df snapshot from the node, not a HiCache tier.
    raw.joinpath("ssd_hw_summary.json").write_text(json.dumps(
        {"hicache_fs_total_gb": 3575.0, "hicache_fs_used_gb": 25.0,
         "hicache_fs_avail_gb": 3550.0, "nvme_device_capacity_gb": 3577.0}))
    return raw


def _finding(html, title):
    i = html.find(title)
    return re.sub(r"<[^>]+>", "", html[i:i + 3000]) if i >= 0 else ""


def test_server_info_none_backend_is_no_storage_tier():
    assert resolve_l3_backend(_setup()).backend_class == "host_dram_only"


def test_explicit_backend_or_launch_flag_still_wins():
    # The same backend value, no longer defaulted, is a statement about the deployment.
    assert resolve_l3_backend(_setup(**{"Defaulted fields": "Host, Port"})).backend_class == "local_ssd"
    assert resolve_l3_backend(
        _setup(), "python3 -m sglang.launch_server --hicache-storage-backend file"
    ).backend_class == "local_ssd"
    si = dict(SI_RAW, hicache_storage_backend="file")
    assert resolve_l3_backend(_setup(**{"SGLang server_info raw": si})).backend_class == "local_ssd"


def test_l1l2_run_reports_no_l3_tier(tmp_path):
    raw = _mk_l1l2(tmp_path / "l1l2")
    html = build_executive_summary_html(raw.parent, run_label="t")
    txt = _finding(html, "L3 TIER · NOT CONFIGURED")
    assert txt, "missing the no-L3 finding"
    assert "L1 HBM + L2 DRAM only" in txt
    assert "is expected" in txt
    assert f"{EVICTED:,}" in txt and "nowhere to offload" in txt
    assert "consider adding an L3 tier" in txt
    assert "L3 ACTIVITY · NONE OBSERVED" not in html
    assert "re-run with a larger context" not in html
    tier = re.search(r"Inference Cache Tier</b>: ([^<]+)", html)
    assert tier and "L3" not in tier.group(1)


def test_l3_run_keeps_activity_findings(tmp_path):
    html = build_executive_summary_html(_mk(tmp_path / "file", backend="file").parent,
                                        run_label="t")
    assert "L3 TIER · NOT CONFIGURED" not in html
