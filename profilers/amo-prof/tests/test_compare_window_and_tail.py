#!/usr/bin/env python3
"""A window mean is only a property of the system if the window is the workload's.

Run: python3.12 tests/test_compare_window_and_tail.py

Two runs of the same workload on the reference hardware, one on a local-SSD
L3 tier and one on a remote AI-memory-node L3.5 tier, were compared and the
L3.5 run looked better on every headline:

    output throughput   50.1 vs 45.6 tok/s
    GPU utilisation     84.2% vs 49.1%
    HBM bandwidth        341 vs 226 GB/s
    TTFT mean         79,341 vs 84,703 ms

All of the first three reverse, and the fourth is noise, because:

* The L3 window was 2,925 s and its workload finished inside it. Its HBM
  bandwidth fell monotonically by quartile -- 392, 221, 156, 136 GB/s -- and
  its last samples read 0, 13, 4. The L3.5 window was 1,800 s and flat
  throughout: 332, 321, 379, 332. So 35% of one window was dead and 2% of
  the other, and every time-average on the L3 side is diluted by that.
  Corrected to the active span, L3's output throughput is 70.2 tok/s --
  above L3.5's 50.1.
* Both TTFT means sit ~100x above their own p50 (79,341/598 = 133x;
  84,703/800 = 106x), so they are queue wait, not service time. A 6%
  difference between two such means is not a tier effect.
* The L3 p50 of exactly 800.00 ms is the le=0.8 s boundary of the
  0.08/0.8/8/400 s ladder -- a bucket edge, not a measurement.
* Neither tier was serving reads: 747 GB written and 3.8 GB read back,
  0.51%. So no property of the media -- the DRAM on the memory node
  included -- can explain a read-latency difference.
* The SSD was at 1.3 MB/s read against a 7,000 MB/s target: 0.019%, at a
  mean queue depth of 5.4. It was not the constraint.

`compare` reported none of that. The variance banner fired, correctly, to
say a single run per configuration is not attributable -- but that is a
general disclaimer, not a finding, and the duration guard fires above 2x
while these windows differ by 1.63x.

This file builds both runs' shapes from the measured figures and requires
each of the six to be stated.

Needs no Prometheus and no pandas.
"""
import csv
import json
import logging
import pathlib
import re
import shutil
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
logging.basicConfig(level=logging.CRITICAL)

from amoprof.comparator import (  # noqa: E402
    RunSpec, build_comparison_html, build_ruled_out_banner,
    build_suspect_banner, extract_metrics,
)
from amoprof.report.metric_kernels import (  # noqa: E402
    active_window_fraction, bucket_edge_check,
)

_RESULTS = []
_P = "sglang:"


def _check(name, got, want):
    ok = got == want
    _RESULTS.append((ok, name))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        print(f"        got  {got!r}\n        want {want!r}")


def _close(name, got, want, tol=1e-6):
    ok = got is not None and abs(float(got) - float(want)) <= tol
    _RESULTS.append((ok, name))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        print(f"        got  {got!r}\n        want {want!r} (+/-{tol})")


def _w(path, header, rows):
    with pathlib.Path(path).open("w", encoding="utf-8", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(header)
        for r in rows:
            wr.writerow(["" if x is None else x for x in r])


def _make_run(root, *, label, win_s, n, hbm_profile, p50_ms, mean_ms,
              rd_bw, wr_bw, rd_total, wr_total, qd, l1_tok, decode_tok):
    """One run directory shaped like the reference telemetry."""
    raw = root / label
    raw.mkdir()
    step = win_s / (n - 1)
    # GPU: the activity series the active-fraction test reads.
    _w(raw / "gpu_timeseries.csv", ["time_sec", "gpu_util", "hbm_bw_gbs"],
       [[round(i * step), min(100.0, hbm_profile[i] / 4.77),
         hbm_profile[i]] for i in range(n)])
    # SGLang: the counters, the KV-pool gauge and the TTFT histogram.
    hdr = ["time_sec",
           f'{_P}realtime_tokens_total{{mode="prefill_cache"}}',
           f'{_P}realtime_tokens_total{{mode="prefill_compute"}}',
           f'{_P}realtime_tokens_total{{mode="decode"}}',
           f'{_P}time_to_first_token_seconds_sum',
           f'{_P}time_to_first_token_seconds_count',
           f'{_P}time_to_first_token_seconds_bucket{{le="0.08"}}',
           f'{_P}time_to_first_token_seconds_bucket{{le="0.8"}}',
           f'{_P}time_to_first_token_seconds_bucket{{le="8"}}',
           f'{_P}time_to_first_token_seconds_bucket{{le="400"}}',
           f'{_P}time_to_first_token_seconds_bucket{{le="+Inf"}}',
           f'{_P}num_used_tokens', f'{_P}max_total_num_tokens']
    rows = []
    # Δsum ÷ Δcount over the window must come out at mean_ms.
    obs = 2000.0
    d_sum_s = mean_ms / 1000.0 * obs
    for i in range(n):
        live = hbm_profile[i] > 20.0
        rows.append([round(i * step),
                     1_000_000 + i * 40_000,
                     10_000 + i * 1_000,
                     40_000 + i * (decode_tok / (n - 1)),
                     100.0 + d_sum_s * i / (n - 1),
                     200.0 + obs * i / (n - 1),
                     5 + i, 10 + i * 2, 12 + i * 3, 13 + i * 3, 14 + i * 3,
                     (l1_tok if live else 0), 196_153])
    _w(raw / "sglang_timeseries.csv", hdr, rows)
    (raw / "sglang_summary.json").write_text(json.dumps({
        "server_ttft_p50_ms": p50_ms,
        "server_ttft_p90_ms": 6419.47,
        "server_ttft_p99_ms": 57273.91}), encoding="utf-8")
    (raw / "summary.json").write_text(json.dumps({
        "duration_s": win_s,
        "nvme_rd_bw_mbs_mean": rd_bw, "nvme_wr_bw_mbs_mean": wr_bw,
        "nvme_read_total_gb": rd_total, "nvme_write_total_gb": wr_total}),
        encoding="utf-8")
    _w(raw / "nvme_driver_timeseries.csv",
       ["time_sec", "rd_bw_mbs", "wr_bw_mbs", "avgqu_sz", "qd_peak"],
       [[round(i * step), rd_bw, wr_bw, qd, qd * 1.5] for i in range(n)])
    return RunSpec(label=label, raw_dir=raw)


def main() -> int:
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="amoprof-win-"))
    try:
        # L3.5: flat for the whole window, as measured by quartile.
        prof_l35 = ([332.0] * 10 + [321.0] * 10 + [379.0] * 10
                    + [332.0] * 9 + [90.0])
        # L3: the measured monotonic wind-down, dead for the last stretch.
        prof_l3 = ([392.0] * 10 + [221.0] * 10 + [156.0] * 7
                   + [136.0] * 3 + [1.0, 0.0, 0.0, 13.0, 4.0]
                   + [0.0] * 5)
        s35 = _make_run(tmp, label="L3.5 mooncake", win_s=1800,
                        n=len(prof_l35), hbm_profile=prof_l35,
                        p50_ms=598.07, mean_ms=79341.0, rd_bw=0.02,
                        wr_bw=644.2, rd_total=0.03, wr_total=1082.0,
                        qd=2.7, l1_tok=94_143, decode_tok=88_380)
        s3 = _make_run(tmp, label="L3 local SSD", win_s=2925,
                       n=len(prof_l3), hbm_profile=prof_l3,
                       p50_ms=800.00, mean_ms=84703.0, rd_bw=1.3,
                       wr_bw=255.3, rd_total=3.8, wr_total=747.0,
                       qd=5.4, l1_tok=59_782, decode_tok=133_380)
        m35 = extract_metrics(s35)
        m3 = extract_metrics(s3)

        print("\n1 · the dead tail is measured, not assumed")
        _check("L3.5 was alive for essentially its whole window",
               round((m35.active_frac or 0) * 100) >= 95, True)
        _check("L3 was not", round((m3.active_frac or 0) * 100) <= 80, True)
        _check("the trailing idle time is named for L3",
               (m3.trail_idle_s or 0) > 600.0, True)
        _check("and is ~zero for L3.5", (m35.trail_idle_s or 0) < 120.0, True)
        _check("each says which series measured it",
               ("gpu_timeseries.csv" in (m3.active_src or "")
                and "gpu_timeseries.csv" in (m35.active_src or "")), True)
        _check("with the threshold it used, so the fraction is checkable",
               "above" in (m3.active_method or ""), True)

        print("\n2 · the active-span rate reverses the window-mean verdict")
        _check("L3.5's window mean and active mean barely differ",
               abs((m35.active_output_tok_s or 0)
                   - (m35.throughput_tok_s or 0))
               < 0.1 * (m35.throughput_tok_s or 1), True)
        _check("L3's active mean is materially higher than its window mean",
               (m3.active_output_tok_s or 0) > 1.2 * (m3.throughput_tok_s or 1),
               True)
        _check("and it overtakes L3.5 once the dead time is out",
               (m3.active_output_tok_s or 0) > (m35.active_output_tok_s or 0),
               True)
        _check("while the window means say the opposite",
               (m3.throughput_tok_s or 0) < (m35.throughput_tok_s or 0), True)

        print("\n3 · a mean that is all tail says so")
        _close("the TTFT mean is the window Δsum ÷ Δcount", m3.ttft_ms,
               84703.0, tol=1.0)
        _close("the p50 comes from the whole-window quantile",
               (m3.lat_pct_ms or {}).get(("ttft", 0.5)), 800.00)
        _check("p90 and p99 are carried too",
               sorted(q for (k, q) in (m3.lat_pct_ms or {}) if k == "ttft"),
               [0.5, 0.9, 0.99])
        _close("L3's mean is 106x its own p50", m3.tail_ratio_for("ttft"),
               84703.0 / 800.0, tol=0.5)
        _close("L3.5's is 133x", m35.tail_ratio_for("ttft"),
               79341.0 / 598.07, tol=0.5)

        print("\n4 · a percentile on a bucket edge is not a measurement")
        _check("L3's p50 of exactly 800.00 ms is flagged",
               bool((m3.lat_bucket_note or {}).get(("ttft", 0.5))), True)
        _check("naming the boundary and how wide the bracket is",
               ("le=0.8s" in (m3.lat_bucket_note or {}).get(("ttft", 0.5), "")
                and "100x" in (m3.lat_bucket_note or {}).get(("ttft", 0.5), "")),
               True)
        _check("L3.5's 598.07 ms is not on an edge",
               (m35.lat_bucket_note or {}).get(("ttft", 0.5)), None)
        _check("the ladder was read from the run's own bucket columns",
               bucket_edge_check(800.0, [0.08, 0.8, 8, 400])["on_edge"], True)

        print("\n5 · the tier is a sink, so its media cannot be the reason")
        _close("L3 read back 0.51% of what it absorbed", m3.read_back_pct,
               3.8 / 747.0 * 100.0)
        _check("L3.5 is the same shape", (m35.read_back_pct or 99) < 5.0, True)

        print("\n6 · the device was never asked for what it can do")
        _close("read BW is 0.019% of the read target", m3.rd_headroom_pct,
               1.3 / 7000.0 * 100.0)
        _close("write BW is 5.1% of the write target", m3.wr_headroom_pct,
               255.3 / 5000.0 * 100.0)
        _check("and the target is labelled a DEFAULT, not this drive's spec",
               "DEFAULT" in (m3.dev_target_src or ""), True)

        print("\n7 · HBM used would have hidden the KV-pool difference")
        _close("L3.5 held 94,143 tokens resident while active",
               m35.l1_kv_tok_peak, 94_143.0)
        _close("L3 held 59,782", m3.l1_kv_tok_peak, 59_782.0)
        _check("the pool capacity is reported beside them",
               (m35.l1_kv_cap_tok, m3.l1_kv_cap_tok), (196_153.0, 196_153.0))
        _check("and the source names the gauge",
               "num_used_tokens" in (m35.l1_kv_src or ""), True)

        print("\n8 · and every one of them reaches the report")
        _runs = [m35, m3]
        _sus = build_suspect_banner(_runs)
        _out = build_ruled_out_banner(_runs)
        _check("the window outlived its workload is stated",
               "outlived its workload" in _sus, True)
        _check("naming the run and the dead minutes",
               ("L3 local SSD" in _sus and "min of its" in _sus), True)
        _check("with both the window and the active-span throughput",
               "over the active span" in _sus, True)
        _check("the differing active fractions are stated",
               "not alive for the same share" in _sus, True)
        _check("the bucket-limited percentile is stated",
               "bucket-limited" in _sus, True)
        _check("the all-tail mean is stated",
               "almost all tail" in _sus, True)
        _check("the write-sink finding is stated",
               "write sink, not a read cache" in _out, True)
        _check("ruling the media out explicitly",
               "can explain a read-latency difference" in _out, True)
        _check("the idle device is stated",
               "is not the constraint" in _out, True)
        _check("with the percentage of target, not just the MB/s",
               "% of its" in _out, True)
        _check("the 2x duration guard alone would NOT have fired "
               "(2,925/1,800 = 1.63x)",
               "Window lengths differ" in _sus, False)

        print("\n  the whole report still builds, with the rows behind them")
        _html = build_comparison_html(_runs, title="L3 vs L3.5")
        for _frag in ("over the ACTIVE span only",
                      "window the workload was alive for",
                      "idle at the end of the window",
                      "TTFT p50", "mean ÷ its own p50",
                      "bucket-limited?",
                      "Bytes read back ÷ bytes written",
                      "% of the device&#x27;s read target",
                      "L1 HBM KV pool · mean resident"):
            _check(f"row present: {_frag[:42]}",
                   _frag in _html or _frag.replace("&#x27;", "'") in _html,
                   True)
        _check("and the ruled-out banner is in the document",
               "What the telemetry rules out" in _html, True)

        print("\n9 · a well-bounded pair raises none of it")
        _good_a = _make_run(tmp, label="A", win_s=1800, n=40,
                            hbm_profile=[330.0] * 40, p50_ms=598.07,
                            mean_ms=700.0, rd_bw=3200.0, wr_bw=2600.0,
                            rd_total=600.0, wr_total=700.0, qd=24.0,
                            l1_tok=90_000, decode_tok=88_000)
        _good_b = _make_run(tmp, label="B", win_s=1800, n=40,
                            hbm_profile=[325.0] * 40, p50_ms=612.00,
                            mean_ms=690.0, rd_bw=3100.0, wr_bw=2550.0,
                            rd_total=590.0, wr_total=690.0, qd=23.0,
                            l1_tok=89_000, decode_tok=87_000)
        _ga, _gb = extract_metrics(_good_a), extract_metrics(_good_b)
        _sus2 = build_suspect_banner([_ga, _gb])
        _out2 = build_ruled_out_banner([_ga, _gb])
        _check("no dead-tail warning", "outlived its workload" in _sus2, False)
        _check("no active-fraction warning",
               "not alive for the same share" in _sus2, False)
        _check("no all-tail warning", "almost all tail" in _sus2, False)
        _check("no write-sink finding when the tier serves reads",
               "write sink" in _out2, False)
        _check("no idle-device finding when the device is loaded",
               "is not the constraint" in _out2, False)
        _check("a loaded device reads as a real share of its target",
               round(_ga.rd_headroom_pct or 0) == 46, True)

        print("\n10 · the kernel's own guards")
        _check("two samples cannot establish a duty cycle",
               active_window_fraction([1.0, 2.0])["present"], False)
        _check("an absolute threshold is reported as such",
               "absolute threshold" in
               active_window_fraction([0.0, 5.0, 9.0], threshold=1.0)["method"],
               True)
        _close("a flat series is fully active",
               active_window_fraction([10.0] * 6)["fraction"], 1.0)
        _close("a series that is dead half the time is half active",
               active_window_fraction([10.0] * 3 + [0.0] * 3)["fraction"], 0.5)
        _check("no bucket ladder means no edge claim",
               bucket_edge_check(800.0, [])["on_edge"], False)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    bad = [n for ok, n in _RESULTS if not ok]
    print(f"\n{len(_RESULTS) - len(bad)}/{len(_RESULTS)} passed"
          + (f" — FAILED: {', '.join(bad)}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
