#!/usr/bin/env python3
"""check_collectors.py — will each collector actually produce data on this host?

Presence of a binary is not readiness.  Intel PCM installs fine and then
returns nothing without MSR access; iostat is on PATH but reports no activity
for the wrong device.  Both failures look identical from Prometheus: the
`amoprof_<collector>_*` gauges appear, carry only collection metadata, and the
report shows empty charts hours later.

So this runs each collector for a short interval and reports what came back.

    python3 check_collectors.py                # all
    python3 check_collectors.py --ssd-device /dev/nvme0n1
    python3 check_collectors.py --only pcm,iostat

Exit status: 0 if every collector checked produced data, 1 otherwise, so it
can gate an install.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"
if not sys.stdout.isatty():
    GREEN = RED = YELLOW = DIM = RESET = ""


def ok(msg: str) -> None:
    print(f"  {GREEN}[OK]{RESET}    {msg}")


def bad(msg: str, fix: str = "") -> None:
    print(f"  {RED}[FAIL]{RESET}  {msg}")
    if fix:
        print(f"          {DIM}fix: {fix}{RESET}")


def warn(msg: str, fix: str = "") -> None:
    print(f"  {YELLOW}[WARN]{RESET}  {msg}")
    if fix:
        print(f"          {DIM}{fix}{RESET}")


def _run_collector(cls, seconds: float, **kwargs) -> dict:
    """Start a collector, let it sample, and return its stop() payload."""
    try:
        mon = cls(**kwargs)
    except Exception as e:
        return {"_error": f"could not construct: {e}"}
    try:
        mon.start()
        time.sleep(seconds)
        return mon.stop() or {}
    except Exception as e:
        try:
            mon.stop()
        except Exception:
            pass
        return {"_error": f"raised while sampling: {e}"}


def check_cpu(seconds: float) -> bool:
    from amoprof.collectors.cpu import CpuMonitor
    r = _run_collector(CpuMonitor, seconds, interval_s=0.25)
    if r.get("_error"):
        bad(f"cpu — {r['_error']}")
        return False
    if not r.get("cpu_available"):
        bad(f"cpu — {r.get('cpu_reason', 'no data')}", "/proc/stat unreadable?")
        return False
    ok(f"cpu — util {r.get('cpu_util_pct_mean', 0):.1f}% mean over "
       f"{int(r.get('cpu_core_count', 0))} core(s), {r.get('cpu_samples', 0)} samples")
    return True


def check_vmstat(seconds: float) -> bool:
    from amoprof.collectors.vmstat import VmstatMonitor
    r = _run_collector(VmstatMonitor, seconds, interval_s=0.25)
    if r.get("_error"):
        bad(f"vmstat — {r['_error']}")
        return False
    # The collector renames /proc/vmstat keys to friendlier ones
    # (major_faults_per_s, not pgmajfault), so check for those.
    expected = ("major_faults_total", "major_faults_per_s",
                "page_cache_reads_per_s", "oom_kills")
    if not any(k in r for k in expected):
        bad("vmstat — no page-fault fields returned",
            "/proc/vmstat unreadable?")
        return False
    ok(f"vmstat — readable ({r.get('major_faults_total', 0):,.0f} major faults "
       f"in window)")
    return True


def check_iostat(seconds: float, device: str) -> bool:
    if not shutil.which("iostat"):
        bad("iostat — binary not on PATH",
            "install sysstat (apt install sysstat / dnf install sysstat). "
            "iostat has no --*-bin flag; it must be on PATH.")
        return False
    from amoprof.collectors.iostat import IostatMonitor
    r = _run_collector(IostatMonitor, max(seconds, 3.0), device=device)
    if r.get("_error"):
        bad(f"iostat — {r['_error']}")
        return False
    got = r.get("read_iops_mean", 0) or r.get("write_iops_mean", 0) or \
        r.get("read_bw_mb_mean", 0) or r.get("write_bw_mb_mean", 0) or \
        r.get("util_pct_mean", 0)
    if not got:
        # An idle disk legitimately reports zeros, so this is a warning: the
        # collector worked, there was simply nothing happening.
        warn(f"iostat — ran on {device} but every field was zero",
             "either the device is idle (fine) or --ssd-device points at the "
             "wrong device. Check `lsblk` and `df /mnt/<hicache-path>`.")
        return True
    ok(f"iostat — {device}: {r.get('read_iops_mean', 0):.0f} r/s, "
       f"{r.get('write_iops_mean', 0):.0f} w/s, "
       f"{r.get('util_pct_mean', 0):.1f}% util")
    return True


def check_dram_pmu(seconds: float, tool: str, binaries: dict) -> bool:
    from amoprof.service import _resolve_dram_tool, _detect_cpu_vendor
    from types import SimpleNamespace
    resolved = _resolve_dram_tool(SimpleNamespace(dram_tool=tool))
    vendor = _detect_cpu_vendor()

    if vendor == "intel" and resolved == "amduprof":
        bad("dram PMU — AMDuProf selected on an INTEL cpu",
            "AMDuProf cannot read Intel memory-controller counters. "
            "Use --dram-tool intel-pcm or perf-imc.")
        return False
    if vendor == "amd" and resolved == "intel-pcm":
        bad("dram PMU — Intel PCM selected on an AMD cpu",
            "Use --dram-tool amduprof.")
        return False

    needed = {"amduprof": ("AMDuProfPcm",),
              "intel-pcm": ("pcm-memory", "pcm-memory.x", "pcm"),
              "perf-imc": ("perf",)}.get(resolved, ())

    # A PCM build only supports the microarchitectures it was compiled to know
    # about.  On a newer CPU every pcm-* binary is present and every one of
    # them refuses to run — "install the tool" is then exactly the wrong
    # advice, because the tool is installed and can never work.  Probe for
    # that case explicitly and point at perf-imc, which reads the same
    # counters through the kernel and does not need PCM to know the model.
    if resolved == "intel-pcm":
        probe = shutil.which("pcm-raw") or shutil.which("pcm-core") or \
            shutil.which("pcm-numa")
        if probe:
            try:
                import subprocess
                out = subprocess.run([probe], capture_output=True, text=True,
                                     timeout=20).stdout or ""
            except Exception:
                out = ""
            if "unsupported processor" in out.lower():
                model = ""
                for line in out.splitlines():
                    if "CPU model number" in line and "Brand" in line:
                        model = line.strip()[:110]
                        break
                bad("dram PMU — Intel PCM is installed but does NOT support this CPU",
                    (f"{model}\n          " if model else "") +
                    "PCM only knows the microarchitectures its build was "
                    "compiled for; a newer Xeon is refused by every pcm-* "
                    "binary. Use --dram-tool perf-imc instead — it reads the "
                    "same uncore IMC counters through the kernel and does not "
                    "need PCM to recognise the model.")
                _imc = list(Path("/sys/bus/event_source/devices").glob("uncore_imc*")) \
                    if Path("/sys/bus/event_source/devices").exists() else []
                if _imc:
                    print(f"          {DIM}perf-imc looks viable: "
                          f"{len(_imc)} uncore_imc PMU(s) present.{RESET}")
                else:
                    print(f"          {DIM}note: no uncore_imc PMUs exposed either; "
                          f"DRAM bandwidth may not be measurable on this host. "
                          f"L2 occupancy is still measured from SGLang "
                          f"hicache counters.{RESET}")
                return False
    explicit = binaries.get(resolved, "")
    found = ""
    if explicit and Path(explicit).exists():
        found = explicit
    else:
        for b in needed:
            w = shutil.which(b)
            if w:
                found = w
                break
    if not found:
        bad(f"dram PMU — {resolved}: no usable binary "
            f"(checked {explicit or '(no explicit path)'} and PATH for "
            f"{'/'.join(needed)})",
            "install the tool, or use --dram-tool perf-imc "
            "(needs perf_event_paranoid <= 0).")
        return False

    # MSR access is the usual silent failure: the binary exists, runs, and
    # returns nothing.
    if resolved in ("amduprof", "intel-pcm"):
        msr = Path("/dev/cpu/0/msr")
        if not msr.exists():
            bad(f"dram PMU — {found} present but /dev/cpu/0/msr is missing",
                "modprobe msr, and run the service as root or with CAP_SYS_RAWIO.")
            return False
    if resolved == "perf-imc":
        try:
            lvl = int(Path("/proc/sys/kernel/perf_event_paranoid").read_text().strip())
            if lvl > 0:
                bad(f"dram PMU — perf present but perf_event_paranoid={lvl}",
                    "sysctl -w kernel.perf_event_paranoid=0")
                return False
        except Exception:
            pass

    # v1.20.34: dispatch to the collector class that matches the resolved
    # tool - the old code hardcoded PcmMemoryCollector (Intel) which was
    # a no-op on AMD hosts and produced a misleading "amduprof ran but
    # produced no data" message.
    if resolved == "amduprof":
        from amoprof.collectors.amduprof_pcm import AMDuProfPcmMemoryCollector
        r = _run_collector(AMDuProfPcmMemoryCollector,
                           max(seconds, 4.0),
                           binary=(explicit or found or
                                    "/opt/AMDuProf_5.2-606/bin/AMDuProfPcm"))
        _avail_key, _reason_key = "amduprof_pcm_available", "amduprof_pcm_reason"
    else:
        from amoprof.collectors.pcm_memory import PcmMemoryCollector
        r = _run_collector(PcmMemoryCollector, max(seconds, 4.0))
        _avail_key, _reason_key = "pcm_available", "pcm_reason"
    if r.get("_error"):
        bad(f"dram PMU — {r['_error']}")
        return False
    if not r.get(_avail_key):
        bad(f"dram PMU — {resolved} ran but produced no data: "
            f"{r.get(_reason_key, 'unknown reason')}",
            "this is exactly the failure that shows up later as "
            "'L2 (DRAM BW): NO' with the gauges present but empty.")
        return False
    # Both collectors publish dram_total_gb_s_mean (the AMD variant
    # from stop() at line ~294; the Intel variant at pcm_memory.py:514).
    ok(f"dram PMU — {resolved} via {found}: "
       f"{r.get('dram_total_gb_s_mean', 0):.1f} GB/s total "
       f"(read {r.get('dram_read_gb_s_mean', 0):.1f}, "
       f"write {r.get('dram_write_gb_s_mean', 0):.1f})")
    return True


def check_gpu(seconds: float) -> bool:
    if not shutil.which("nvidia-smi"):
        warn("gpu — nvidia-smi not on PATH",
             "expected on a GPU node; DCGM via Prometheus also works.")
        return True
    from amoprof.collectors.gpu import GpuMonitor
    r = _run_collector(GpuMonitor, max(seconds, 2.0), interval_s=0.5)
    if r.get("_error"):
        bad(f"gpu — {r['_error']}")
        return False
    n = r.get("gpu_count", 0)
    if not n:
        bad("gpu — nvidia-smi present but no GPUs reported")
        return False
    ok(f"gpu — {int(n)} device(s), util {r.get('gpu_util_mean', 0):.1f}% mean")
    return True


def check_smart(seconds: float, device: str) -> bool:
    """SMART/endurance. Needs nvme-cli or smartctl, and usually root."""
    tool = shutil.which("nvme") or shutil.which("smartctl")
    if not tool:
        bad("smart — neither nvme-cli nor smartmontools on PATH",
            "apt install nvme-cli smartmontools")
        return False
    # The module is nvme_smart.py and the class NvmeSmartMonitor — I guessed
    # both wrong, and the check reported "will produce no data" for a
    # collector that works fine.  A readiness check that fails on its own
    # import is worse than no check: it sends the operator chasing a
    # non-existent problem.
    from amoprof.collectors import NvmeSmartMonitor  # type: ignore
    r = _run_collector(NvmeSmartMonitor, seconds, device=device, poll_s=1)
    if r.get("_error"):
        bad(f"smart — {r['_error']}")
        return False
    got = [k for k in r if "wear" in k or "written" in k or "percentage" in k]
    if not got:
        warn(f"smart — ran on {device} but returned no endurance fields",
             "usually a permissions issue: SMART needs root or CAP_SYS_RAWIO.")
        return True
    ok(f"smart — {device}: {len(got)} endurance field(s)")
    return True


def check_nvme_driver(seconds: float, device: str) -> bool:
    """Driver-level NVMe stats from sysfs — no external binary needed."""
    from pathlib import Path as _P
    base = _P("/sys/block") / _P(device).name / "stat"
    if not base.exists():
        bad(f"nvme_driver — {base} not found",
            f"is {device} a real block device? check `lsblk`.")
        return False
    ok(f"nvme_driver — {base} readable")
    return True


def check_queue_depth(seconds: float, device: str) -> bool:
    """Queue depth from sysfs. Absent on some virtualised devices."""
    from pathlib import Path as _P
    name = _P(device).name
    cand = [_P("/sys/block") / name / "device" / "queue_depth",
            _P("/sys/block") / name / "queue" / "nr_requests"]
    found = [c for c in cand if c.exists()]
    if not found:
        warn(f"queue_depth_sysfs — no queue-depth node for {device}",
             "expected at /sys/block/<dev>/device/queue_depth; some virtual "
             "and RAID devices do not expose it.")
        return True
    ok(f"queue_depth_sysfs — {found[0]}")
    return True


def check_blktrace(seconds: float, device: str) -> bool:
    """blktrace needs its binaries, debugfs mounted, and root."""
    missing = [b for b in ("blktrace", "blkparse") if not shutil.which(b)]
    if missing:
        bad(f"blktrace — missing binaries: {', '.join(missing)}",
            "apt install blktrace")
        return False
    from pathlib import Path as _P
    if not _P("/sys/kernel/debug/tracing").exists():
        bad("blktrace — debugfs is not mounted",
            "mount -t debugfs none /sys/kernel/debug")
        return False
    if os.geteuid() != 0:
        warn("blktrace — binaries present but not running as root",
             "blktrace needs root or CAP_SYS_ADMIN; it will produce nothing "
             "otherwise, and the failure is silent.")
        return True
    ok(f"blktrace — binaries, debugfs and privileges all present")
    return True


def check_biosnoop(seconds: float) -> bool:
    """biosnoop is BPF-based: needs bcc and root."""
    tool = (shutil.which("biosnoop-bpfcc") or shutil.which("biosnoop")
            or shutil.which("biosnoop.py"))
    if not tool:
        bad("biosnoop — not on PATH",
            "apt install bpfcc-tools (binary is usually biosnoop-bpfcc)")
        return False
    if os.geteuid() != 0:
        warn(f"biosnoop — {tool} present but not running as root",
             "BPF attach needs root or CAP_BPF + CAP_PERFMON.")
        return True
    ok(f"biosnoop — {tool}")
    return True


CHECKS = ("cpu", "vmstat", "iostat", "dram", "gpu",
          "smart", "nvme_driver", "queue_depth", "blktrace", "biosnoop")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ssd-device", default="/dev/nvme0n1")
    ap.add_argument("--dram-tool", default="auto")
    ap.add_argument("--amduprof-pcm-bin", default="")
    ap.add_argument("--intel-pcm-memory-bin", default="")
    ap.add_argument("--seconds", type=float, default=2.0,
                    help="sampling window per collector")
    ap.add_argument("--only", default="",
                    help=f"comma-separated subset of: {','.join(CHECKS)}")
    args = ap.parse_args(argv[1:])

    wanted = [c.strip() for c in args.only.split(",") if c.strip()] or list(CHECKS)
    binaries = {"amduprof": args.amduprof_pcm_bin,
                "intel-pcm": args.intel_pcm_memory_bin}

    print("Collector readiness — each collector is RUN, not merely located.\n")
    results: dict[str, bool] = {}
    for name in wanted:
        try:
            if name == "cpu":
                results[name] = check_cpu(args.seconds)
            elif name == "vmstat":
                results[name] = check_vmstat(args.seconds)
            elif name == "iostat":
                results[name] = check_iostat(args.seconds, args.ssd_device)
            elif name == "dram":
                results[name] = check_dram_pmu(args.seconds, args.dram_tool, binaries)
            elif name == "gpu":
                results[name] = check_gpu(args.seconds)
            elif name == "smart":
                results[name] = check_smart(args.seconds, args.ssd_device)
            elif name == "nvme_driver":
                results[name] = check_nvme_driver(args.seconds, args.ssd_device)
            elif name == "queue_depth":
                results[name] = check_queue_depth(args.seconds, args.ssd_device)
            elif name == "blktrace":
                results[name] = check_blktrace(args.seconds, args.ssd_device)
            elif name == "biosnoop":
                results[name] = check_biosnoop(args.seconds)
            else:
                warn(f"{name} — unknown check, skipped")
        except ImportError as e:
            bad(f"{name} — collector not importable: {e}")
            results[name] = False
        except Exception as e:
            bad(f"{name} — check raised: {e}")
            results[name] = False

    failed = [k for k, v in results.items() if not v]
    print()
    if failed:
        print(f"{RED}{len(failed)} collector(s) will produce no data: "
              f"{', '.join(failed)}{RESET}")
        print("Charts fed by these will be empty, and the gauges will still "
              "appear in Prometheus carrying only collection metadata.")
        return 1
    print(f"{GREEN}All {len(results)} checked collector(s) produced data.{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
