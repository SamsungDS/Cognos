"""The bandwidth-per-tier chart charts L3 from cumulative byte counters.

A Prometheus-sourced nvme_driver_timeseries.csv carries rd_bytes / wr_bytes
counters and no rd_bw_mbs gauge.  The Executive chart differenced only
read_bytes / write_bytes, so it said "no NVMe/iostat bandwidth series" while
the Interactive tab charted L3 bandwidth from the same file.
"""
import pathlib
import re
import sys

from amoprof.report.combined import build_executive_summary_html

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from test_l35_report_consistency import _mk, N  # noqa: E402

STEP_S = 90.0
RD_MBS, WR_MBS = 1_200.0, 400.0          # decimal MB/s


def _byte_counters_only(raw):
    """Replace the gauge-style NVMe file with cumulative byte counters."""
    rows = ["time_sec,rd_ios,wr_ios,rd_bytes,wr_bytes,rd_iops,wr_iops,avgqu_sz"]
    for i in range(N):
        t = i * STEP_S
        rows.append(f"{t},{i * 1000},{i * 500},{int(i * STEP_S * RD_MBS * 1e6)},"
                    f"{int(i * STEP_S * WR_MBS * 1e6)},40,20,0.5")
    (raw / "nvme_driver_timeseries.csv").write_text("\n".join(rows) + "\n")
    return raw


def _bw_section(raw):
    html = build_executive_summary_html(raw.parent, run_label="t")
    t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    i = t.find("Bandwidth utilisation per cache tier")
    return t[i:i + 6000]


def test_l3_line_from_byte_counters(tmp_path):
    seg = _bw_section(_byte_counters_only(_mk(tmp_path / "bytes", backend="file")))
    assert "L3-local storage BW" in seg
    assert "no NVMe/iostat bandwidth series" not in seg
    # Each interval moved (1,200 + 400) MB/s = 1.6 GB/s; the observed peak is it.
    assert re.search(r"peak 1\.60 GB/s", seg), seg[:800]


def test_gauge_csv_still_charts_l3(tmp_path):
    seg = _bw_section(_mk(tmp_path / "gauge", backend="file"))
    assert "L3-local storage BW" in seg
