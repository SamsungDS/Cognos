"""The declared configuration is checked before amoprof collects or analyses.

A report on an AgentX + MLPerf run carried "HiCache storage path /dev/nvm6n1"
(the device is nvme6n1) and was headed "interactive serving": nothing had
declared the workload, so the report guessed it.  Both reached the report
unchecked, and correcting them meant rerunning the benchmark.
"""
import json
import pathlib
import sys

from amoprof import cli
from amoprof.config_checks import (check_config, declared_benchmark,
                                   local_block_devices)

SEEN = {"nvme0n1", "nvme1n1", "nvme6n1"}
TICKET_SETUP = {"HiCache storage backend": "file", "HiCache storage path": "/dev/nvm6n1",
                "Model": "google/gemma-4-31b-it"}


def _fields(issues):
    return {i.field for i in issues}


def test_ticket_setup_is_rejected_with_a_suggestion():
    issues = check_config(TICKET_SETUP, observed_devices=SEEN)
    assert _fields(issues) == {"Application / Benchmark", "HiCache storage path"}
    path = next(i for i in issues if i.field == "HiCache storage path")
    assert "no block device 'nvm6n1'" in path.problem
    assert "did you mean /dev/nvme6n1?" in path.fix


def test_correct_device_as_file_backend_path_is_still_wrong():
    issues = check_config(dict(TICKET_SETUP, **{"HiCache storage path": "/dev/nvme6n1"}),
                          benchmark="AgentX + MLPerf", observed_devices=SEEN)
    assert len(issues) == 1 and "file backend stores KV as files" in issues[0].problem


def test_valid_setup_passes():
    good = dict(TICKET_SETUP, **{"HiCache storage path": "/mnt/nvme6/hicache",
                                 "L3 device": "/dev/nvme6c6n1"})      # multipath path of nvme6n1
    assert check_config(good, benchmark="AgentX + MLPerf", observed_devices=SEEN) == []


def test_device_names_are_not_checked_when_devices_are_unknown():
    issues = check_config({"L3 device": "/dev/nvm6n1"}, benchmark="x", observed_devices=None)
    assert issues == []


def test_benchmark_declaration_rules():
    assert declared_benchmark({}, "AgentX + MLPerf") == "AgentX + MLPerf"
    assert declared_benchmark({"Application / Benchmark": "MLPerf"}, "AgentX") == "AgentX"
    assert declared_benchmark({"Application / Benchmark": "MLPerf"}) == "MLPerf"
    assert declared_benchmark({"Application / Benchmark": "unknown"}) == ""
    # A reference-profile default is not a declaration.
    assert declared_benchmark({"Benchmark": "bench_serving",
                               "Defaulted fields": "Host, Benchmark"}) == ""


def test_local_devices_fold_multipath_paths(tmp_path):
    for n in ("nvme6n1", "nvme6c6n1", "nvme0n1p1", "loop0", "sda", "dm-0"):
        (tmp_path / "block" / n).mkdir(parents=True)
    assert local_block_devices(str(tmp_path)) == {"nvme6n1", "sda"}


def test_collect_stops_before_touching_the_host(tmp_path, monkeypatch):
    setup = tmp_path / "setup.json"
    setup.write_text(json.dumps(TICKET_SETUP))
    monkeypatch.setattr("amoprof.config_checks.local_block_devices", lambda *a, **k: SEEN)
    out = tmp_path / "out"
    rc = cli.main(["collect", "--setup-details", str(setup), "--output-dir", str(out),
                   "--duration-s", "1"])
    assert rc == 2
    assert not out.exists()                      # nothing created, nothing collected


def test_analyze_stops_before_any_work(tmp_path, caplog):
    # No Prometheus here, so devices cannot be listed; the device-as-directory
    # check is static and still stops the run.
    raw = tmp_path / "run" / "raw"
    raw.mkdir(parents=True)
    (raw / "setup_details.json").write_text(json.dumps(
        {"HiCache storage backend": "file", "HiCache storage path": "/dev/nvme6n1"}))
    rc = cli.main(["analyze", "--run-dir", str(tmp_path / "run"),
                   "--output-dir", str(tmp_path / "reports")])
    assert rc == 2
    assert not (tmp_path / "reports").exists()
    assert "file backend stores KV as files" in caplog.text


def test_missing_benchmark_is_a_warning_not_a_stop():
    issues = check_config({"Model": "m"}, observed_devices=SEEN)
    assert [(i.field, i.blocking) for i in issues] == [("Application / Benchmark", False)]
    # A wrong device still blocks alongside it.
    issues = check_config(TICKET_SETUP, observed_devices=SEEN)
    assert {i.field: i.blocking for i in issues} == {
        "Application / Benchmark": False, "HiCache storage path": True}


def test_cli_warns_but_proceeds_without_a_benchmark(caplog):
    class A:
        benchmark = ""
    assert cli._check_config_or_stop(A, {"Model": "m"}, SEEN, "on this host") == 0
    assert "not declared" in caplog.text and "--benchmark" in caplog.text


def test_benchmark_flag_is_recorded_in_the_setup(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "setup_details.json").write_text(json.dumps(
        {"Application / Benchmark": "bench_serving",
         "Defaulted fields": "Host, Application / Benchmark"}))

    class A:
        setup_details = ""
        benchmark = "AgentX + MLPerf"
    cli._copy_setup_details(A, raw)
    sd = json.loads((raw / "setup_details.json").read_text())
    assert sd["Application / Benchmark"] == "AgentX + MLPerf"
    assert "Application / Benchmark" not in sd["Defaulted fields"]


def test_report_says_not_declared_instead_of_guessing(tmp_path):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    from test_l35_report_consistency import _mk
    from amoprof.report.combined import build_executive_summary_html
    import re
    raw = _mk(tmp_path / "r")
    txt = re.sub(r"<[^>]+>", " ", build_executive_summary_html(raw.parent, run_label="t"))
    m = re.search(r"Application / Benchmark\s*:\s*([^·&]+)", txt)
    assert m and m.group(1).strip().startswith("not declared"), m and m.group(1)


def test_prometheus_device_query_is_valid_promql(monkeypatch):
    # re.escape put "\." in the PromQL string, which does not parse; the
    # device list then always came back unknown.
    import io
    import urllib.parse
    from amoprof import config_checks as cc
    seen = {}

    def fake_urlopen(url, timeout=0):
        seen["q"] = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["query"][0]
        body = {"data": {"result": [{"metric": {"device": d}} for d in
                                    ("nvme6c6n1", "nvme6n1", "nvme1n1", "md0", "dm-0")]}}
        return io.BytesIO(json.dumps(body).encode())

    monkeypatch.setattr(cc.urllib.request, "urlopen", fake_urlopen)
    devs = cc.prometheus_block_devices("http://prom:9090", "host-dgx1.example.com", 0, 600)
    assert devs == {"nvme6n1", "nvme1n1", "md0"}
    assert "\\" not in seen["q"] and 'instance=~"host-dgx1.example.com(:[0-9]+)?"' in seen["q"]
    assert cc.prometheus_block_devices("http://prom:9090", 'bad"host', 0, 600) is None
