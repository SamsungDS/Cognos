"""Validate the run's declared configuration before collecting or analysing.

A report repeats whatever the setup file says, and a wrong value there --
"/dev/nvm6n1" for nvme6n1, or no benchmark name at all so the report guessed
"interactive serving" -- is only noticed after the run, when fixing it means
re-running the benchmark.  These checks compare the declaration with what
the run can observe and stop the command when they disagree.
"""
from __future__ import annotations

import difflib
import json
import os
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

# Setup fields naming the block device behind L3.
DEVICE_KEYS = ("L3 Device", "L3 device", "L3 block device", "l3_device",
               "L3 (local storage) device", "l3_storage_device",
               "SSD device", "NVMe device", "ssd_device")
# Setup fields naming where the file backend keeps its KV files.
STORAGE_PATH_KEYS = ("HiCache storage path", "hicache_storage_path",
                     "File storage path", "file_storage_path",
                     "HiCache path", "hicache_path", "L3 storage path")
# Setup fields naming the workload, in the order the report reads them.
BENCHMARK_KEYS = ("Application / Benchmark", "application_benchmark", "Benchmark",
                  "benchmark", "Application", "application", "Workload", "workload",
                  "Benchmark name", "benchmark_name")
_UNSET = {"", "unknown", "none", "n/a", "na", "null", "-", "default", "tbd"}
# Real disks; partitions, loop, ram and device-mapper nodes are not L3 devices.
_DISK_RE = re.compile(r"(?:nvme\d+(?:c\d+)?n\d+|sd[a-z]+|vd[a-z]+|xvd[a-z]+|md\d+)")


@dataclass(frozen=True)
class ConfigIssue:
    field: str
    value: str
    problem: str
    fix: str
    # False: reported as a warning, the run goes ahead.
    blocking: bool = True

    def render(self) -> str:
        return f"{self.field} = {self.value!r}: {self.problem}  Fix: {self.fix}"


def _defaulted(setup: dict) -> set:
    s = str(setup.get("Defaulted fields", setup.get("defaulted_fields", "")) or "")
    return {x.strip().lower() for x in s.split(",") if x.strip()}


def _declared(setup: dict, key: str) -> str:
    """The value of `key` if the setup states it (present, set, not defaulted)."""
    v = str(setup.get(key, "") or "").strip()
    if v.lower() in _UNSET or key.lower() in _defaulted(setup):
        return ""
    return v


def declared_benchmark(setup: dict, cli_value: str = "") -> str:
    """The benchmark this run declares: --benchmark first, then the setup file."""
    v = str(cli_value or "").strip()
    if v and v.lower() not in _UNSET:
        return v
    for k in BENCHMARK_KEYS:
        v = _declared(setup, k)
        if v:
            return v
    return ""


def _disk_head(name: str) -> str:
    """nvme6n1p2 / nvme6c6n1 / /dev/sda3 -> the whole-disk name (nvme6n1, sda)."""
    base = os.path.basename(str(name).strip())
    m = re.fullmatch(r"nvme(\d+)(?:c\d+)?n(\d+)(?:p\d+)?", base)
    if m:
        return f"nvme{m.group(1)}n{m.group(2)}"
    m = re.fullmatch(r"((?:sd|vd|xvd)[a-z]+)\d*", base)
    return m.group(1) if m else base


def local_block_devices(sys_root: str = "/sys") -> set:
    """Whole-disk names this host has (multipath paths folded into their head)."""
    try:
        names = os.listdir(os.path.join(sys_root, "block"))
    except OSError:
        return set()
    return {_disk_head(n) for n in names if _DISK_RE.fullmatch(n)}


def prometheus_block_devices(base_url: str, host: str, start: float, end: float,
                             timeout: float = 10.0) -> "set | None":
    """Whole-disk names node_exporter reported for `host` in the window.

    None when that cannot be determined (no URL, no host, query failure, no
    node_exporter series), so the caller skips the device check instead of
    failing a run on missing telemetry.
    """
    if not base_url or not host or end <= start:
        return None
    if not re.fullmatch(r"[A-Za-z0-9.-]+", host):
        return None
    rng = max(60, int(end - start))
    # Unescaped: re.escape's "\." is not a valid escape inside a PromQL
    # string literal, so the query failed to parse.  A "." then matches any
    # character, which is looser than needed but cannot pick up another real
    # host's name.
    q = (f'count by (device) (count_over_time(node_disk_reads_completed_total'
         f'{{instance=~"{host}(:[0-9]+)?"}}[{rng}s]))')
    url = (base_url.rstrip("/") + "/api/v1/query?"
           + urllib.parse.urlencode({"query": q, "time": f"{end:.0f}"}))
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            data = json.load(r)
        res = data.get("data", {}).get("result", [])
    except Exception:
        return None
    devs = {_disk_head(x.get("metric", {}).get("device", "")) for x in res}
    devs = {d for d in devs if _DISK_RE.fullmatch(d)}
    return devs or None


def _device_issue(field: str, value: str, observed: set, where: str) -> "ConfigIssue | None":
    head = _disk_head(value)
    if head in observed:
        return None
    near = difflib.get_close_matches(head, sorted(observed), n=1, cutoff=0.6)
    return ConfigIssue(
        field, value,
        f"no block device '{head}' {where} (seen: {', '.join(sorted(observed)) or 'none'}).",
        (f"did you mean /dev/{near[0]}? " if near else "")
        + "Correct it in the setup details file and rerun.")


def check_config(setup: dict, *, benchmark: str = "",
                 observed_devices: "set | None" = None,
                 device_source: str = "on this host") -> list:
    """Every disagreement between the declared configuration and the run.

    `observed_devices` None means the devices could not be listed; device
    names are then not checked (the caller reports that they were skipped).
    """
    setup = setup if isinstance(setup, dict) else {}
    issues = []

    if not declared_benchmark(setup, benchmark):
        issues.append(ConfigIssue(
            "Application / Benchmark", "",
            "not declared, so the report could only guess the workload from its "
            "request pattern.",
            "pass --benchmark \"<name>\" (e.g. --benchmark \"AgentX + MLPerf\") or set "
            "\"Application / Benchmark\" in the setup details file; the report will "
            "say \"not declared\" until then.", blocking=False))

    for k in DEVICE_KEYS:
        v = _declared(setup, k)
        if v and observed_devices is not None:
            i = _device_issue(k, v, observed_devices, device_source)
            if i:
                issues.append(i)

    backend = _declared(setup, "HiCache storage backend").lower()
    for k in STORAGE_PATH_KEYS:
        v = _declared(setup, k)
        if not v.startswith("/dev/"):
            continue
        if observed_devices is not None:
            i = _device_issue(k, v, observed_devices, device_source)
            if i:
                issues.append(i)
                continue
        if backend == "file":
            issues.append(ConfigIssue(
                k, v,
                "is a block device, but the file backend stores KV as files in a "
                "directory.",
                "give the directory on the SSD here (e.g. the mount point) and the "
                "device under \"L3 device\"."))
    return issues


def load_setup(path: str) -> dict:
    """The setup details JSON, or {} when absent/unreadable (copying reports that)."""
    if not path:
        return {}
    try:
        d = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}
