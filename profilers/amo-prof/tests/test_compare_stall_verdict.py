#!/usr/bin/env python3
"""The same workload, finished 1.66x later, must be reported as exactly that.

Run: python3 tests/test_compare_stall_verdict.py

Two runs of one ~5,900-request workload on the reference hardware -- a
local-SSD L3 tier (SGLang `file` backend, page_size 1) and an L3.5 Mooncake
memory node -- were compared. The comparison said L3 was faster per active
minute and told the reader to compare the active-span rows. What actually
happened:

* Both runs served the same requests and prompt tokens (within 2%), and
  needed about the same GPU-busy time.
* L3 took 50 min and L3.5 30: the same work, 1.66x later.
* The difference was two STALLS in the L3 run -- GPUs at 0% with requests
  waiting to enter prefill and the L1 KV pool under 12% full -- not compute
  and not a dead tail.
* L3's prefetch counter stopped moving at t~1,350 s; L3.5 prefetched ~36x
  more per second, 97% of it from its store's DRAM tier.
* L3.5's TPOT is worse because it decoded twice as many requests at once.
* The L3 run's recorded launch command says mooncake while the engine ran
  the file backend.

This file builds both runs' shapes from those figures and requires each to
be stated, and requires a stall-free pair to state none of it.

Needs no Prometheus and no pandas.
"""
import csv
import json
import logging
import pathlib
import shutil
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
logging.basicConfig(level=logging.CRITICAL)

from amoprof.comparator import (  # noqa: E402
    RunSpec, build_comparison_html, build_suspect_banner, build_verdict_html,
    extract_metrics,
)
from amoprof.report.metric_kernels import admission_stalls  # noqa: E402

_RESULTS = []
_P = "sglang:"
_STEP = 15


def _check(name, got, want):
    ok = got == want
    _RESULTS.append((ok, name))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        print(f"        got  {got!r}\n        want {want!r}")


def _near(name, got, want, tol):
    ok = got is not None and abs(float(got) - float(want)) <= tol
    _RESULTS.append((ok, name))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        print(f"        got  {got!r}\n        want {want!r} (+/-{tol})")


def _w(path, header, rows):
    with pathlib.Path(path).open("w", encoding="utf-8", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(header)
        wr.writerows(rows)


def _make_run(root, *, label, win_s, phase, busy_util, requests, prompt_tok,
              hit, decode_tok, tpot_ms, e2e_ms, queue_ms, running,
              prefetched, prefetch_until, backuped, backend, launch_backend,
              page_size, store=None, nvme=None, ttft_ms=600.0):
    """phase(t) -> "busy" | "stall" | "nowork" for each sample time."""
    raw = root / label.replace(" ", "_")
    raw.mkdir()
    ts = list(range(0, win_s + 1, _STEP))
    n = len(ts)
    kinds = [phase(t) for t in ts]

    _w(raw / "gpu_timeseries.csv",
       ["time_sec", "gpu_idx", "gpu_util", "mem_used", "mem_total",
        "hbm_bw_pct"],
       [[t, g, (busy_util if k == "busy" else 0.0), 33_900, 40_960,
         (busy_util / 4 if k == "busy" else 0.0)]
        for t, k in zip(ts, kinds) for g in range(8)])
    if nvme:
        _w(raw / "nvme_driver_timeseries.csv",
           ["time_sec", "rd_bw_mbs", "wr_bw_mbs", "rd_iops", "avgqu_sz",
            "qd_peak"],
           [[t, nvme[0], nvme[1], nvme[2], nvme[3], nvme[3] * 3]
            for t in ts])

    hdr = ["time_sec",
           f"{_P}num_queue_reqs", f"{_P}num_running_reqs",
           f"{_P}num_used_tokens", f"{_P}max_total_num_tokens",
           f"{_P}prefetched_tokens_total", f"{_P}backuped_tokens_total",
           f'{_P}realtime_tokens_total{{mode="prefill_cache"}}',
           f'{_P}realtime_tokens_total{{mode="prefill_compute"}}',
           f'{_P}realtime_tokens_total{{mode="decode"}}',
           f"{_P}e2e_request_latency_seconds_sum",
           f"{_P}e2e_request_latency_seconds_count",
           f"{_P}time_to_first_token_seconds_sum",
           f"{_P}time_to_first_token_seconds_count",
           f"{_P}inter_token_latency_seconds_sum",
           f"{_P}inter_token_latency_seconds_count",
           f"{_P}queue_time_seconds_sum", f"{_P}queue_time_seconds_count"]
    rows = []
    busy_n = max(1, kinds[1:].count("busy"))
    pf_n = max(1, sum(1 for t in ts if t <= prefetch_until) - 1)
    done = 0.0
    pf = 0.0
    for i, (t, k) in enumerate(zip(ts, kinds)):
        if i and kinds[i] == "busy":
            done += 1.0 / busy_n
        if i and t <= prefetch_until:
            pf += prefetched / pf_n
        frac = i / (n - 1)
        reqs = requests * done
        rows.append([
            t,
            0 if k == "nowork" else (30 if k == "stall" else 4),
            0 if k != "busy" else running,
            14_000 if k != "busy" else 120_000, 196_153,
            pf, backuped * frac,
            prompt_tok * hit * done, prompt_tok * (1 - hit) * done,
            decode_tok * done,
            reqs * e2e_ms / 1000.0, reqs,
            reqs * ttft_ms / 1000.0, reqs,
            decode_tok * done * tpot_ms / 1000.0, decode_tok * done,
            reqs * queue_ms / 1000.0, reqs])
    _w(raw / "sglang_timeseries.csv", hdr, rows)

    if store:
        _w(raw / "l35_store_capacity.csv",
           ["time_sec", "l35_get_total_n", "l35_mem_hit_n", "l35_file_hit_n"],
           [[t, store[0] * i / (n - 1), store[1] * i / (n - 1),
             (store[0] - store[1]) * i / (n - 1)] for i, t in enumerate(ts)])

    setup = {
        "Model": "google/gemma-4-31b-it", "TP size": "8",
        "SGLang server_info raw": {"hicache_storage_backend": backend,
                                   "page_size": page_size},
        "Launch command": ("python3 -m sglang.launch_server "
                           "--enable-hierarchical-cache "
                           f"--hicache-storage-backend {launch_backend}"),
    }
    (raw / "setup_details.json").write_text(json.dumps(setup), encoding="utf-8")
    (raw / "summary.json").write_text(json.dumps({"duration_s": win_s}),
                                      encoding="utf-8")
    return RunSpec(label=label, raw_dir=raw)


def _l3_phase(t):
    if 1350 <= t < 1500 or 1950 <= t < 2300:
        return "stall"
    if 2625 <= t < 2775:
        return "nowork"
    return "busy"


def main() -> int:
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="amoprof-stall-"))
    try:
        s3 = _make_run(tmp, label="L3 local SSD", win_s=3000,
                       phase=_l3_phase, busy_util=64.0, requests=5_931,
                       prompt_tok=79_792_388, hit=0.871, decode_tok=114_722,
                       tpot_ms=255.5, e2e_ms=14_818, queue_ms=9_000,
                       running=11, prefetched=197_064, prefetch_until=1335,
                       backuped=10_147_448, backend="file",
                       launch_backend="mooncake", page_size=1,
                       nvme=(1.3, 223.4, 251.0, 5.36), ttft_ms=10_080)
        s35 = _make_run(tmp, label="L3.5 DRAM500+SSD", win_s=1800,
                        phase=lambda t: "busy", busy_util=88.0,
                        requests=5_863, prompt_tok=78_444_310, hit=0.866,
                        decode_tok=113_706, tpot_ms=307.4, e2e_ms=9_571,
                        queue_ms=2_000, running=20, prefetched=4_268_360,
                        prefetch_until=1800, backuped=31_334_545,
                        backend="mooncake", launch_backend="mooncake",
                        page_size=1, store=(44_622_192, 43_482_666),
                        nvme=(16.2, 0.0, 7164.0, 0.01), ttft_ms=3_915)
        m3, m35 = extract_metrics(s3), extract_metrics(s35)

        print("\n1 · the workload and how long it took")
        _check("requests are counted from the e2e histogram",
               round(m3.requests_n or 0), 5_931)
        _near("L3 took ~50 min, first to last busy sample",
              (m3.completion_s or 0) / 60, 50.0, 0.6)
        _near("L3.5 took 30", (m35.completion_s or 0) / 60, 30.0, 0.3)
        _near("the same work took 1.66x longer on L3",
              m3.completion_s / m35.completion_s, 1.66, 0.03)
        _check("request throughput favours L3.5",
               (m35.req_per_s or 0) > 1.5 * (m3.req_per_s or 1), True)
        _check("and both needed about the same GPU-busy time",
               abs(m3.gpu_busy_equiv_s - m35.gpu_busy_equiv_s)
               / max(m3.gpu_busy_equiv_s, m35.gpu_busy_equiv_s) < 0.15, True)

        print("\n2 · idle time is split into stalls and genuine idle")
        _check("L3's idle time could be classified", m3.stall_present, True)
        _near("L3 stalled for ~500 s", m3.stall_s, 500.0, 30.0)
        _check("in two episodes", len(m3.stall_episodes), 2)
        _near("the longest ~350 s", max(e["dur_s"] for e in m3.stall_episodes),
              350.0, 30.0)
        _check("with the L1 KV pool under 12% full",
               all(e["kv_fill_mean"] < 12 for e in m3.stall_episodes), True)
        _check("and the tier prefetching nothing while it waited",
               all(e["prefetch_tok"] == 0 for e in m3.stall_episodes), True)
        _near("the no-work idle is kept apart", m3.no_work_s, 150.0, 30.0)
        _check("L3.5 never stalled", m35.stall_s, 0.0)

        print("\n3 · the backing tier's delivery")
        _check("L3's prefetch went silent for the last ~27 min",
               (m3.prefetch_quiet_tail_s or 0) > 1500, True)
        _check("L3.5 prefetched over 20x faster",
               m35.prefetch_rate_tok_s > 20 * m3.prefetch_rate_tok_s, True)
        _near("L3 returned ~1.9% of what it absorbed",
              m3.engine_read_back_pct, 197_064 / 10_147_448 * 100, 0.05)

        print("\n4 · the A5 scheduler queue is no longer lost to column names")
        _check("waiting-queue mean is read from sglang:num_queue_reqs",
               m3.sg_queue_reqs_mean is not None, True)
        _check("decode-batch mean likewise",
               (m35.sg_running_reqs_mean or 0) > (m3.sg_running_reqs_mean or 0),
               True)
        _near("queue wait is the window Δsum ÷ Δcount", m3.queue_wait_ms,
              9_000.0, 1.0)

        print("\n5 · configuration that matters")
        _check("page size from server_info", m3.page_size, 1.0)
        _check("the engine ran the file backend", m3.storage_backend, "file")
        _check("the launch command claims mooncake", m3.launch_backend,
               "mooncake")

        print("\n6 · the verdict is numbers: tiles, evidence table, flags")
        v = build_verdict_html(m3, m35)
        for frag, why in (
                ("L3.5 DRAM500+SSD served the same workload 1.6", "headline"),
                ('class="tile"', "KPI tiles"),
                ("Requests completed", "workload row"),
                (">same<", "workload match reading"),
                ("same GPU work", "GPU-time reading"),
                ("Stalled (GPU idle, reqs waiting)", "stall row"),
                ("HBM had room", "KV capacity reading"),
                ("silent for the last", "tier went silent"),
                ("store lookups from DRAM", "store DRAM share"),
                ("cost of the larger batch", "TPOT trade-off"),
                ("page_size 1", "page-size flag"),
                ("launch command is stale", "launch mismatch"),
                ("inferred, not measured", "mechanism is labelled"),
                ("To confirm:", "with its checks")):
            _check(f"verdict carries the {why}", frag in v, True)
        _check("and prose is gone: no bullet list", "<ul>" in v, False)

        print("\n6b · how the signals co-moved")
        _c = m3.corr or {}
        _check("a correlation matrix is computed",
               "waiting reqs" in (_c.get("names") or []), True)
        _gi = _c["names"].index("GPU util")
        _wi = _c["names"].index("waiting reqs")
        _check("GPU util falls as the waiting queue grows (r < -0.5)",
               (_c["r"][_gi][_wi] or 0) < -0.5, True)
        _check("the matrix is symmetric",
               _c["r"][_gi][_wi] == _c["r"][_wi][_gi], True)

        print("\n7 · the active-span advice is withdrawn when idle was a stall")
        sus = build_suspect_banner([m3, m35])
        _check("the differing active fractions are still stated",
               "not alive for the same share" in sus, True)
        _check("but the idle minutes are named as stalls",
               "idle minutes were stalls" in sus, True)
        _check("and the reader is not told to use the active-span rows",
               "compare the active-span rows below, not the window means" in sus,
               False)

        print("\n8 · the full report carries the new sections")
        html = build_comparison_html([m3, m35], title="L3 vs L3.5")
        for frag in ("Verdict —", "Diagnosis charts", "diag-ratio",
                     "diag-time", "diag-tier", "diag-scatter", "diag-corr-0",
                     "Workload and time to complete",
                     "Timeline — where the time went", "timeline-0",
                     "Stalled (GPU idle, reqs waiting)",
                     "Idle · between batches",
                     "Time to complete (min)", "Fastest to finish"):
            _check(f"section present: {frag}", frag in html, True)

        print("\n8b · A4 and the device charts are fed without summary JSONs")
        _near("GPU util falls back to gpu_timeseries.csv (window mean)",
              m3.gpu_util_pct, 64.0 * (201 - 43) / 201, 0.5)
        _near("HBM fill from mem_used ÷ mem_total", m3.hbm_pct,
              33_900 / 40_960 * 100, 0.01)
        _check("DCGM activity from hbm_bw_pct", m3.dcgm_active_pct > 0, True)
        _near("NVMe read BW from the driver timeseries", m3.nvme_rd_bw_mbs,
              1.3, 1e-6)
        _check("and the bytes it moved are integrated",
               (m3.read_total_gb > 0, m3.write_total_gb > 0), (True, True))
        for _cid, _name in (("ch-gpu", "GPU utilisation & HBM"),
                            ("ch-nvme", "Local NVMe: bandwidth and IOPS"),
                            ("ch-ssd-total", "SSD I/O volume")):
            _check(f"chart renders: {_name}", f'id="{_cid}"' in html, True)
        _check("no chart says its data was not collected",
               "not collected for any of these runs" in html, False)
        _check("no headline figure is printed twice",
               html.count("Request throughput · over time to complete"), 0)

        print("\n9 · a stall-free pair raises none of it")
        ga = extract_metrics(_make_run(
            tmp, label="A", win_s=1800, phase=lambda t: "busy", busy_util=88.0,
            requests=5_900, prompt_tok=79e6, hit=0.87, decode_tok=114_000,
            tpot_ms=300, e2e_ms=9_000, queue_ms=2_000, running=20,
            prefetched=4e6, prefetch_until=1800, backuped=3e7,
            backend="mooncake", launch_backend="mooncake", page_size=64))
        gb = extract_metrics(_make_run(
            tmp, label="B", win_s=1800, phase=lambda t: "busy", busy_util=87.0,
            requests=5_890, prompt_tok=78.9e6, hit=0.87, decode_tok=113_900,
            tpot_ms=301, e2e_ms=9_050, queue_ms=2_010, running=20,
            prefetched=4e6, prefetch_until=1800, backuped=3e7,
            backend="mooncake", launch_backend="mooncake", page_size=64))
        v2 = build_verdict_html(ga, gb)
        _check("no difference is claimed", "No material difference" in v2, True)
        _check("no flag is raised", 'class="chip"' in v2, False)
        _check("no mechanism is inferred", "inferred" in v2, False)

        print("\n10 · the kernel's own rules")
        _r = admission_stalls([0, 15, 30, 45, 60], [90, 0, 90, 90, 90],
                              [5, 5, 5, 5, 5])
        _check("one idle sample beside a queue is not a stall",
               (_r["stall_s"], len(_r["episodes"])), (0.0, 0))
        _r = admission_stalls([0, 15, 30, 45, 60, 75], [90, 0, 0, 0, 0, 90],
                              [0, 3, 3, 0, 0, 0], [5, 0, 0, 0, 0, 5])
        _check("idle with a queue is a stall, idle without is not",
               (_r["stall_s"], _r["no_work_s"]), (30.0, 30.0))
        _check("misaligned series are refused",
               admission_stalls([0, 1, 2], [1, 2], [0, 0, 0])["present"], False)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    bad = [n for ok, n in _RESULTS if not ok]
    print(f"\n{len(_RESULTS) - len(bad)}/{len(_RESULTS)} passed"
          + (f" — FAILED: {', '.join(bad)}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
