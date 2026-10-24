"""biosnoop's slow startup is not reported as a crash.

BCC compiles the eBPF program and scans /proc/kallsyms before biosnoop prints
its header.  Stopping it during that scan leaves a KeyboardInterrupt traceback
ending in `if fn.startswith(b'_kbl_addr_'):`, which the preflight once
reported as a failed collector.
"""
import stat
import sys
import time

from amoprof import preflight
from amoprof.collectors.biosnoop import BiosnoopCollector

HEADER = "TIME(s) COMM PID DISK T SECTOR BYTES LAT(ms)"


def _fake(tmp_path, name, body):
    p = tmp_path / name
    p.write_text(
        f"#!{sys.executable}\n"
        "import sys, time\n"
        "if '-h' in sys.argv:\n"
        "    print('usage: biosnoop [-h] [-Q]'); sys.exit(0)\n"
        + body)
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return str(p)


def _scan_forever():
    # Stands in for BPF.get_kprobe_functions iterating /proc/kallsyms.
    return ("while True:\n"
            "    fn = b'x'\n"
            "    if fn.startswith(b'_kbl_addr_'):\n"
            "        pass\n")


def _check(binary, tmp_path, monkeypatch, timeout_s):
    monkeypatch.setenv("AMOPROF_PREFLIGHT_DIAG_DIR", str(tmp_path / "diag"))
    monkeypatch.setattr(preflight, "BIOSNOOP_STARTUP_TIMEOUT_S", timeout_s)
    return preflight.check_biosnoop(binary, use_sudo=False)


def test_header_after_eight_seconds_passes(tmp_path, monkeypatch):
    # The old 8 s deadline failed this; the wait now ends at the header.
    b = _fake(tmp_path, "slow", f"time.sleep(9)\nprint({HEADER!r}, flush=True)\ntime.sleep(60)\n")
    r = _check(b, tmp_path, monkeypatch, 20.0)
    assert r.status == "pass", r.detail
    assert "within 9." in r.detail


def test_still_starting_is_a_warning_not_a_crash(tmp_path, monkeypatch):
    r = _check(_fake(tmp_path, "scan", _scan_forever()), tmp_path, monkeypatch, 1.0)
    assert r.status == "warn", r.detail
    assert "still starting" in r.detail and "KeyboardInterrupt" in r.detail
    assert "_kbl_addr_" not in r.detail


def test_real_failure_reports_its_own_error(tmp_path, monkeypatch):
    b = _fake(tmp_path, "crash",
              "sys.stderr.write('Traceback (most recent call last):\\n'\n"
              "                 '    open(blacklist)\\n    ^^^^\\n'\n"
              "                 'PermissionError: [Errno 13] Permission denied\\n')\n"
              "sys.exit(1)\n")
    r = _check(b, tmp_path, monkeypatch, 5.0)
    assert r.status == "fail"
    assert "exited with code 1" in r.detail
    assert "PermissionError" in r.detail and "^^^^" not in r.detail


def test_collector_stopped_during_startup_says_so(tmp_path):
    c = BiosnoopCollector(work_dir=tmp_path / "raw", binary=_fake(tmp_path, "scan", _scan_forever()),
                          use_sudo=False)
    c.start()
    time.sleep(1.0)
    out = c.stop()
    assert out["biosnoop_events"] == 0
    assert "still starting" in out["biosnoop_reason"]
    assert "--duration-s" in out["biosnoop_reason"]


def test_collector_records_startup_time(tmp_path):
    b = _fake(tmp_path, "ok", f"time.sleep(1)\nprint({HEADER!r}, flush=True)\n"
              "print('0.1 kworker 12 nvme0n1 W 100 4096 0.05', flush=True)\ntime.sleep(60)\n")
    c = BiosnoopCollector(work_dir=tmp_path / "raw", binary=b, use_sudo=False)
    c.start()
    time.sleep(2.5)
    out = c.stop()
    assert out["biosnoop_events"] == 1
    import json
    s = json.loads((tmp_path / "raw" / "biosnoop_summary.json").read_text())
    assert 0.8 <= s["biosnoop_startup_s"] < 2.5


def test_teardown_does_not_hang_on_a_surviving_child(tmp_path, monkeypatch):
    # sudo with use_pty did not relay the SIGINT, so biosnoop outlived the
    # check holding stderr open, and the blocking stderr read never returned.
    pidfile = tmp_path / "child.pid"
    b = _fake(tmp_path, "orphan",
              "import os, signal\n"
              "if os.fork() == 0:\n"
              "    signal.signal(signal.SIGINT, signal.SIG_IGN)\n"
              "    signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
              f"    open({str(pidfile)!r}, 'w').write(str(os.getpid()))\n"
              "    time.sleep(120)\n"
              "    sys.exit(0)\n"
              f"print({HEADER!r}, flush=True)\n"
              "time.sleep(120)\n")
    t = time.monotonic()
    try:
        r = _check(b, tmp_path, monkeypatch, 10.0)
        assert r.status == "pass", r.detail
        assert time.monotonic() - t < 30
    finally:
        if pidfile.exists():
            import os
            import signal
            try:
                os.kill(int(pidfile.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_biosnoop_runs_in_its_own_session(tmp_path, monkeypatch):
    # sudo ignores signals sent from its own process group.
    import subprocess
    seen = []
    real = subprocess.Popen

    def spy(*a, **k):
        if "biosnoop" in " ".join(map(str, a[0] if a else k.get("args", []))) and "-h" not in a[0]:
            seen.append(k.get("start_new_session"))
        return real(*a, **k)

    monkeypatch.setattr(subprocess, "Popen", spy)
    b = _fake(tmp_path, "biosnoop-ok", f"print({HEADER!r}, flush=True)\ntime.sleep(60)\n")
    assert _check(b, tmp_path, monkeypatch, 5.0).status == "pass"
    c = BiosnoopCollector(work_dir=tmp_path / "raw", binary=b, use_sudo=False)
    c.start()
    c.stop()
    assert seen == [True, True]


def test_multipath_controller_path_matches_its_namespace():
    # /dev/nvme6n1 is the multipath head; biosnoop reports I/O on nvme6c6n1.
    from amoprof.collectors.biosnoop import disk_matches
    for d in ("nvme6n1", "nvme6n1p2", "nvme6c6n1", "nvme6c12n1p1"):
        assert disk_matches("nvme6n1", d), d
    for d in ("nvme6n2", "nvme16n1", "nvme6c6n12", "nvme1n1", "R", ""):
        assert not disk_matches("nvme6n1", d), d
    assert disk_matches("nvme6n1p1", "nvme6c6n1p1")
    assert not disk_matches("nvme6n1p1", "nvme6c6n1p2")
    assert disk_matches("sda", "sda1") and not disk_matches("sda", "sdb")
    assert preflight._biosnoop_disk_matches(
        "1.2 dd 4242 nvme6c6n1 R 0 4096 0.05", "/dev/nvme6n1")
