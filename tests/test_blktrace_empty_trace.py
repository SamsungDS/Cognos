"""An empty blktrace is reported as such, not as a blkparse format change.

A trace with no events makes blkparse print only its per-file "added" lines
and a summary ending "Events (trace): 0 entries".  That once read as
"regex matched 0 events; format may have changed" plus the sudo/debugfs
fixes.  On an NVMe multipath namespace head it is always empty: the I/O runs
on a hidden controller path that blktrace cannot attach to.
"""
import os
import stat
import sys

from amoprof import blockdev, preflight
from amoprof.cli import _blkparse_to_csv
from amoprof.collectors import blktrace as bt


def _sysfs(tmp_path):
    """/sys/block with a multipath head nvme6n1 (+ path nvme6c6n1) and plain nvme0n1."""
    root = tmp_path / "sys"
    (root / "devices" / "virtual" / "nvme-subsystem" / "nvme-subsys6").mkdir(parents=True)
    (root / "devices" / "pci" / "nvme0").mkdir(parents=True)
    block = root / "block"
    for name, dev in (("nvme6n1", "../../devices/virtual/nvme-subsystem/nvme-subsys6"),
                      ("nvme6c6n1", "../../devices/pci/nvme0"),
                      ("nvme0n1", "../../devices/pci/nvme0")):
        (block / name).mkdir(parents=True)
        os.symlink(dev, block / name / "device")
    return str(root)


def test_multipath_head_detection(tmp_path):
    sys_root = _sysfs(tmp_path)
    assert blockdev.nvme_multipath_paths("/dev/nvme6n1", sys_root) == ["nvme6c6n1"]
    assert blockdev.nvme_multipath_paths("/dev/nvme6n1p1", sys_root) == ["nvme6c6n1"]
    assert blockdev.nvme_multipath_paths("/dev/nvme0n1", sys_root) is None
    assert blockdev.nvme_multipath_paths("/dev/sda", sys_root) is None
    assert blockdev.nvme_multipath_paths("", sys_root) is None


def test_sparse_trace_files_count_allocated_bytes(tmp_path):
    p = tmp_path / "trace.blktrace.0"
    with open(p, "wb") as f:
        f.truncate(256 * 1024 * 1024)       # what blktrace leaves per CPU
    assert p.stat().st_size == 256 * 1024 * 1024
    assert blockdev.allocated_bytes([p]) < 1024 * 1024


def _fake_blkparse(tmp_path, entries_line=True):
    lines = [f"Input file {tmp_path}/raw/blktrace_data/trace.blktrace.{i} added" for i in range(256)]
    lines += ["Throughput (R/W): 0KiB/s / 0KiB/s"]
    lines += ["Events (trace): 0 entries"] if entries_line else ["some new trailer"]
    lines += ["Skips: 0 forward (0 -   0.0%)"]
    out = tmp_path / "blkparse_out.txt"
    out.write_text("\n".join(lines) + "\n")
    p = tmp_path / "blkparse"
    p.write_text(f"#!{sys.executable}\nimport sys\nsys.stdout.write(open({str(out)!r}).read())\n")
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return str(p)


def _collector(tmp_path, device, blkparse):
    c = bt.BlktraceCollector(device, work_dir=tmp_path / "raw", blkparse_bin=blkparse,
                             use_sudo=False)
    c._trace_dir.mkdir(parents=True, exist_ok=True)
    for i in range(4):
        (c._trace_dir / f"trace.blktrace.{i}").write_bytes(b"")
    return c


def test_idle_device_is_not_a_format_error(tmp_path, monkeypatch):
    monkeypatch.setattr(blockdev, "nvme_multipath_paths", lambda d, sys_root="/sys": None)
    c = _collector(tmp_path, "/dev/nvme5n1", _fake_blkparse(tmp_path))
    assert c._run_blkparse_to_csv() == 0
    assert c._empty_kind == "no_io"
    assert "device was idle" in c._reason and "format" not in c._reason


def test_multipath_head_names_the_cause(tmp_path, monkeypatch):
    monkeypatch.setattr(blockdev, "nvme_multipath_paths", lambda d, sys_root="/sys": ["nvme6c6n1"])
    c = _collector(tmp_path, "/dev/nvme6n1", _fake_blkparse(tmp_path))
    assert c._run_blkparse_to_csv() == 0
    assert c._empty_kind == "multipath_head"
    assert "nvme6c6n1" in c._reason and "--enable-biosnoop" in c._reason


def test_unknown_output_is_still_a_format_error(tmp_path):
    c = _collector(tmp_path, "/dev/nvme5n1", _fake_blkparse(tmp_path, entries_line=False))
    assert c._run_blkparse_to_csv() == -1
    assert "format may have changed" in c._reason
    # blkparse's own lines are not offered as the unmatched sample.
    assert "added" not in c._reason and "Skips" not in c._reason
    assert "some new trailer" in c._reason


def test_report_reparse_of_empty_trace_is_a_warning(tmp_path, caplog):
    d = tmp_path / "raw" / "blktrace_data"
    d.mkdir(parents=True)
    (d / "trace.blktrace.0").write_bytes(b"")
    status = {}
    assert _blkparse_to_csv(d, tmp_path / "out.csv", blkparse_bin=_fake_blkparse(tmp_path),
                            status=status) is None
    assert status == {"empty": True}
    assert not [r for r in caplog.records if r.levelname == "ERROR"]


def test_preflight_warns_on_multipath_head_without_capturing(tmp_path, monkeypatch):
    monkeypatch.setattr(preflight, "nvme_multipath_paths", lambda d: ["nvme6c6n1"])
    monkeypatch.setattr(preflight, "_blktrace_smoke_capture",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("captured")))
    r = preflight.check_blktrace("/dev/nvme6n1", blktrace_bin=sys.executable,
                                 blkparse_bin=sys.executable, use_sudo=False)
    assert r.status == "warn"
    assert "multipath" in r.detail and "nvme6c6n1" in r.detail


def test_collector_does_not_trace_a_multipath_head(tmp_path, monkeypatch):
    # Tracing it captures nothing, holds the device against other tracers and
    # floods stderr with debugfs read errors.
    monkeypatch.setattr(blockdev, "nvme_multipath_paths", lambda d, sys_root="/sys": ["nvme6c6n1"])
    dev = tmp_path / "nvme6n1"
    dev.write_bytes(b"")
    c = bt.BlktraceCollector(str(dev), duration_s=1, work_dir=tmp_path / "raw",
                             blktrace_bin=sys.executable, use_sudo=False)
    monkeypatch.setattr(c, "_launch_blktrace_process",
                        lambda cmd: (_ for _ in ()).throw(AssertionError("launched")))
    c.start()
    out = c.stop()
    assert out["blktrace_empty_reason"] == "multipath_head"
    assert "nvme6c6n1" in out["blktrace_reason"]


def test_blktrace_runs_in_its_own_session(tmp_path, monkeypatch):
    import subprocess
    seen = {}
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: seen.update(k) or None)
    bt.BlktraceCollector("/dev/null", work_dir=tmp_path)._launch_blktrace_process(["true"])
    assert seen.get("start_new_session") is True


def test_stderr_drain_does_not_block_on_a_held_pipe():
    import subprocess
    import time
    # The child keeps stderr open, as an orphaned root blktrace did.
    p = subprocess.Popen([sys.executable, "-c",
                          "import sys,time; sys.stderr.write('Total: 5 events (dropped 0)\n'); "
                          "sys.stderr.flush(); time.sleep(30)"],
                         stderr=subprocess.PIPE, text=True)
    try:
        time.sleep(1.0)
        t = time.monotonic()
        txt = bt._read_available(p.stderr)
        assert time.monotonic() - t < 2
        assert "Total: 5 events" in txt
    finally:
        p.kill()
        p.wait()


def test_event_and_drop_totals_come_from_stdout(tmp_path, monkeypatch):
    # blktrace prints its per-CPU and Total summary on stdout, which used to
    # go to /dev/null, so dropped events were never detected.
    monkeypatch.setattr(blockdev, "nvme_multipath_paths", lambda d, sys_root="/sys": None)
    fake = tmp_path / "blktrace"
    fake.write_text(
        f"#!{sys.executable}\n"
        "import sys, pathlib, time\n"
        "d = pathlib.Path(sys.argv[sys.argv.index('-D') + 1]); d.mkdir(parents=True, exist_ok=True)\n"
        "(d / 'trace.blktrace.0').write_bytes(b'x' * 64)\n"
        "print('=== nvme1n1 ===')\n"
        "print('  CPU  0:                 4875 events,      229 KiB data')\n"
        "print('  Total:                  4875 events (dropped 125),      229 KiB data')\n"
        "sys.stdout.flush(); time.sleep(1)\n")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    dev = tmp_path / "nvme1n1"
    dev.write_bytes(b"")
    c = bt.BlktraceCollector(str(dev), duration_s=1, work_dir=tmp_path / "raw",
                             blktrace_bin=str(fake), blkparse_bin=str(tmp_path / "no-blkparse"),
                             use_sudo=False)
    c.start()
    out = c.stop()
    assert out["blktrace_events_reported_by_blktrace"] == 4875
    assert out["blktrace_dropped_events"] == 125
    assert "dropped 125" in out["blktrace_coverage_warning"]
