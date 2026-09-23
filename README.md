# AMOprof

AMOprof is a profiling and report-generation package for AI inference workloads. It correlates SGLang/HiCache metrics, GPU/HBM telemetry, host DRAM bandwidth, OS memory pressure, and local storage activity into Executive, Interactive, and End Report views.

It is designed for long-context and KV-cache tiering experiments where HBM, DRAM, and local SSD/NVMe behavior must be interpreted together without mixing logical cache counters with physical block-device telemetry.

---

## What AMOprof reports

AMOprof can generate a single combined HTML report with three tabs:

| Tab | Purpose |
|---|---|
| Executive | High-level KPIs, findings, source health, and cross-layer correlation (Bottleneck Analysis). |
| Interactive | Plotly-based exploratory timelines and drill-down charts. |
| End Report | Static deep-dive report with formulas, sectioned analysis, PNG charts, and per-chart takeaways. |

Core analysis areas include:

- SGLang request, latency, throughput, and cache-hit metrics.
- GPU utilization, GPU power, HBM usage, HBM bandwidth, and NVLink/PCIe signals when available.
- HiCache/KV tier analysis across L1/HBM, L2/DRAM, and L3/local storage.
- L3 local storage analysis from blktrace/iostat/sysfs, including bandwidth, IOPS, queue-depth evidence, request sizes, hot/cold LBA, TRIM/discard, and per-stream attribution when collected.
- DRAM bandwidth from AMD uProf, Intel PCM, or perf IMC fallback.
- OS page activity from vmstat, swap, NUMA, and page-fault counters.
- Network fabric analysis from `/proc/net/dev`, InfiniBand/RoCE port counters, link speed, and TCP retransmits — used to separate a fabric bottleneck from a storage one.
- Per-interval p50/p90/p99 distributions for TTFT, TPOT/ITL, and input/output token size, computed from Prometheus histogram buckets.
- Formula/source documentation so report KPIs can be traced back to counters. Every summary tile in every report shows the formula and exact metric names that produced its number.

---

## Tier terminology

| Tier | Meaning | Typical source |
|---|---|---|
| L1 | GPU HBM and hot KV cache | DCGM / nvidia-smi / SGLang |
| L2 | Host DRAM / HiCache memory tier | SGLang host-cache counters, setup details, DRAM PMU |
| L3 | Node-local SSD/NVMe or local file-backed HiCache storage | blktrace, iostat, sysfs, SMART, filesystem capacity, plus SGLang movement counters |
| L3.5 | AI Memory Node, Mooncake, remote/shared/disaggregated memory, object store, or unresolved logical backing tier with no local SSD mapping | Logical SGLang movement counters; physical charts only when an explicit device mapping exists |
| NET | Host network fabric — NIC and InfiniBand/RoCE. Not a cache tier, but carries KV transfer for disaggregated serving and remote L3 backends | `/proc/net/dev`, `/sys/class/infiniband/*/ports/*/counters`, `/sys/class/net/*/speed`, `/proc/net/snmp` |

Important counter rules:

- `sglang_backuped_tokens_total` is logical offload/write movement.
- `sglang_prefetched_tokens_total` is logical prefetch/onboard movement.
- `sglang_load_back_tokens_total` is an L2→L1 restore diagnostic and is not counted as local SSD read bytes.
- Physical SSD/LBA charts are populated only from local block telemetry.
- If no L3 is configured and no L3 activity exists, L3-relevant sections stay present but collapsed with a “not configured / no activity” note.


### L3 vs L3.5 naming

AMOprof uses the following convention across Executive, Interactive, and End Report tabs:

- **L3** means local SSD/NVMe/file-backed cache storage.
- **L3.5** means AI Memory Node, Mooncake, remote/shared/disaggregated memory, or a logical backing tier where no local SSD mapping is present.

You can set this explicitly in `setup_details.json`:

```json
{
  "KV cache tier": "L3.5",
  "L3 storage type": "AI Memory Node / remote storage"
}
```

For local SSD/NVMe:

```json
{
  "KV cache tier": "L3",
  "L3 storage type": "NVMe SSD",
  "L3 Device": "/dev/nvme0n1",
  "L3 storage path": "/mnt/nvme/hicache"
}
```

For multiple local SSDs, pass a comma-separated `--ssd-device` list at
collect time (see example 11a). The first device drives the L3 tile;
additional devices are captured as sidecar summaries and CSVs.

If `KV cache tier` is omitted, AMOprof derives the label from setup and launch evidence: NVMe/SSD/local file path resolves to **L3**; AI Memory Node, Mooncake, remote/object/RDMA/disaggregated evidence resolves to **L3.5**. If only SGLang logical backing-tier movement is present and no local SSD mapping is available, AMOprof labels the tier **L3.5** and keeps physical SSD/LBA charts separate.

---

## Package structure

```text
amoprof_1_0_0/
├── README.md                         # Overview, features, CLI reference, examples
├── INSTALL.md                        # Installation and dependency guide
├── install.sh                        # Main installer for Python + common system dependencies
├── pyproject.toml                    # Python package metadata and amoprof console entry point
├── setup.py                          # Editable-install compatibility
├── setup_details_sample.json         # Example setup metadata for reports
├── scripts/
│   └── install_dram_deps.sh          # Architecture/vendor-aware DRAM PMU dependency installer
├── systemd/
│   ├── amoprof.service               # systemd unit for `amoprof service`
│   └── amoprof.env.example           # Example EnvironmentFile for the unit
├── tests/
│   └── test_executive_symbol_regression.py
└── amoprof/
    ├── base.py                       # BaseCollector ABC, AIStackLayer enum, CollectorRegistry
    ├── cli.py                        # CLI parser and command dispatch
    ├── service.py                    # Long-lived collection service with a Prometheus /metrics endpoint
    ├── blktrace_service.py           # Incremental blkparse poller feeding service blktrace metrics
    ├── collectors/                   # One collector class per module (iostat.py, gpu.py, ...)
    │   ├── __init__.py               # Imports every submodule → triggers @register_collector
    │   ├── _sudo.py                  # Shared sudo helpers (_sudo_check_output, ...)
    │   ├── iostat.py                 # IostatMonitor       (SSD-scoped, A2)
    │   ├── nvme_smart.py             # NvmeSmartMonitor    (SSD-scoped, A1)
    │   ├── ssd_hardware.py           # SsdHardwareMonitor  (SSD-scoped, A1)
    │   ├── biolatency.py             # BiolatencyCollector (SSD-scoped, A2)
    │   ├── nvme_driver.py            # NvmeDriverMonitor   (SSD-scoped, A2)
    │   ├── queue_depth.py            # BlockQueueDepthCollector (SSD-scoped, A2)
    │   ├── blktrace.py               # BlktraceCollector   (SSD-scoped, A2)
    │   ├── biosnoop.py               # BiosnoopCollector   (SSD-scoped, A2)
    │   ├── discard.py                # DiscardStatsMonitor (SSD-scoped, HOST_OS)
    │   ├── gpu.py                    # GpuMonitor          (host-wide, A4)
    │   ├── nvlink_pcie.py            # NvlinkPcieMonitor   (host-wide, A4)
    │   ├── dram.py                   # DramMonitor         (host-wide, A3)
    │   ├── network.py                # NetworkMonitor      (host-wide, A3) — NIC/IB bandwidth, packets, errors, TCP retransmits
    │   ├── pcm_memory.py             # PcmMemoryCollector  (host-wide, A3, opt-in)
    │   ├── amduprof_pcm.py           # AMDuProfPcmMemoryCollector (host-wide, A3, opt-in)
    │   ├── power.py                  # PowerMonitor        (host-wide, HOST_OS)
    │   ├── vmstat.py                 # VmstatMonitor       (host-wide, HOST_OS)
    │   ├── swap_storm.py             # SwapStormMonitor    (host-wide, HOST_OS)
    │   ├── sglang.py                 # SGLangMetricsSampler (host-wide, A5)
    │   ├── perf_stat.py              # PerfStatCollector   (PID-scoped, A5)
    │   ├── bpftrace.py               # BpftraceCollector   (PID-scoped, A5)
    │   └── nsys.py                   # NsysGpuTraceCollector (PID-scoped, A4)
    ├── layers/                       # LayerRegistry + one LayerModule per AI-stack layer
    │   ├── __init__.py               # Imports every submodule → triggers @register_layer
    │   ├── base.py                   # LayerModule ABC, LayerRegistry, ORDERED_LAYERS
    │   ├── a1_l3_ssd.py              # A1L3SsdLayer     (owns smart, ssd_hw)
    │   ├── a2_nvme_driver.py         # A2NvmeDriverLayer (owns iostat, nvme_driver, blktrace, biosnoop, biolatency, queue_depth_sysfs)
    │   ├── a3_dram.py                # A3DramLayer      (owns dram, pcm, amduprof_pcm; picks between pcm/amduprof_pcm)
    │   ├── a4_gpu_hbm.py             # A4GpuHbmLayer    (owns gpu, nvlink_pcie, nsys; honors --nsys-pid)
    │   ├── a5_app.py                 # A5AppLayer       (owns sglang, perf, bpf)
    │   ├── host_os.py                # HostOsLayer      (owns vmstat, power, swap_storm, discard)
    │   └── cross.py                  # CrossLayer       (synthetic, no collectors; hosts multi-layer overlays)
    ├── analysis.py                   # ScenarioAnalyzer — S1..S8 scenario-based KPIs
    ├── prometheus_source.py          # Prometheus/SGLang/DCGM/node-exporter source handling
    ├── blktrace_analyzer.py          # Block-level L3/NVMe trace analysis
    ├── comparator.py                 # Multi-run comparison support
    ├── aggregator.py                 # Multi-run aggregation support
    ├── retime.py                     # Legacy timeseries alignment helper
    ├── preflight.py                  # Pre-collect sanity checks (device present, binaries in PATH, ...)
    ├── writer.py                     # Emits canonical raw/*.csv/jsonl per collector + summary.json
    ├── models.py                     # Shared dataclasses used across analysis/report
    ├── percentiles.py                # Percentile helpers
    ├── plan.py                       # Workload/plan enum used by benchmarks
    ├── benchmark.py                  # Benchmark orchestration entry point
    ├── runner.py                     # Legacy runner support
    ├── bench_summary.py              # Parses bench_serving-style summary JSON for reports
    ├── bench_lc_results.py           # Long-context benchmark summary renderer
    ├── report/
    │   ├── amoprof.py                # Static End Report generation
    │   ├── interactive.py            # Interactive report generation
    │   ├── combined.py               # Combined tabbed report generation
    │   ├── enhancer.py               # Post-process pass that themes + polishes the End Report
    │   ├── common_kpis.py            # Shared KPI definitions + canonical-KPI note override
    │   ├── metric_formulas.py        # Single source of truth for KPI-tile and chart-axis formulas
    │   ├── metric_kernels.py         # Single source of truth for metric *arithmetic* (deltas, rates, alignment)
    │   ├── ai_metrics_dict.py        # Canonical AI benchmark metrics dictionary
    │   ├── loadback_patterns.py      # KV$ load-back / prefetch pattern detection
    │   ├── l3_backend.py             # L3 backend detection/resolution
    │   └── tier_terms.py             # Tier naming/terminology helpers
    ├── tests/                        # Package unit tests (test_common_kpis.py)
    └── dashboard/                    # Optional dashboard assets
```

---

## Architecture

AMOprof separates *what to collect* from *how to compose a report*.
Two complementary registries drive this:

1. **CollectorRegistry** (`amoprof/base.py`) — every collector class
   inherits `BaseCollector`, declares a `SPEC: CollectorSpec`, and
   self-registers via `@register_collector` at import time.
2. **LayerRegistry** (`amoprof/layers/base.py`) — one `LayerModule`
   per AI-stack layer (A1..A5, HOST_OS, CROSS). Each layer owns the
   collectors registered against its `AIStackLayer` and, in later
   stages, the analyze-time work that produces that layer's section
   of the report.

cli.py and service.py iterate `LayerRegistry.ordered()` to build the
collector set for a run — they don't know or care which concrete
collector classes exist. Each layer resolves the gating rules for its
collectors (pcm-vs-amduprof arbitration lives in `A3DramLayer`,
`--nsys-pid` preference lives in `A4GpuHbmLayer`, etc.).

### Building blocks (`amoprof/base.py`)

| Type                    | Role |
|-------------------------|------|
| `AIStackLayer`          | Enum of the layer taxonomy AMOprof reports on: `A1_L3_SSD`, `A2_NVME_DRIVER`, `A3_DRAM`, `A4_GPU_HBM`, `A5_APP`, `HOST_OS`, `CROSS` (synthetic — for multi-layer overlays). |
| `CollectorSpec`         | Frozen dataclass carrying a collector's `name`, `layer`, `is_ssd_scoped`, `is_pid_scoped`, `optional`, `enable_flag`, and one-line `description`. |
| `BaseCollector` (ABC)   | Abstract base every collector class inherits from. Declares `start()` / `stop()` (required) plus `sanity_check()` and `series()` (optional overrides). |
| `CollectorRegistry`     | Process-wide registry keyed by `(layer, name)`. Populated at import time. Queried via `.ssd_scoped()`, `.host_wide()`, `.pid_scoped()`, `.by_layer(layer)`, `.all()`. |
| `@register_collector`   | Class decorator that adds the class to `CollectorRegistry`. Reads the class's `SPEC` attribute. |

Each SSD-scoped collector also declares a `for_device(device, args, ctx)`
classmethod that owns its own constructor signature. That is how
`cli.py` / `service.py` stay collector-agnostic when instantiating
per-device instances — they never know that `IostatMonitor` takes
`(device, interval_s)` while `BlktraceCollector` takes ten arguments.

### What is registered today

Every AMOprof collector — SSD-scoped, host-wide, and PID-scoped — is now
in `CollectorRegistry`. cli/service iterate the registry instead of
hard-coding constructors.

**SSD-scoped** — instantiated once per device passed to `--ssd-device`:

| Layer            | Collector          | Optional (`--enable-*`)   |
|------------------|--------------------|---------------------------|
| `A1_L3_SSD`      | `smart`            | –                         |
| `A1_L3_SSD`      | `ssd_hw`           | –                         |
| `A2_NVME_DRIVER` | `iostat`           | –                         |
| `A2_NVME_DRIVER` | `nvme_driver`      | –                         |
| `A2_NVME_DRIVER` | `queue_depth_sysfs`| –                         |
| `A2_NVME_DRIVER` | `biolatency`       | –                         |
| `A2_NVME_DRIVER` | `blktrace`         | `--enable-blktrace`       |
| `A2_NVME_DRIVER` | `biosnoop`         | `--enable-biosnoop`       |
| `HOST_OS`        | `discard`          | –                         |

**Host-wide** — one instance per collect run (or per service cycle):

| Layer            | Collector      | Optional trigger                       |
|------------------|----------------|----------------------------------------|
| `A3_DRAM`        | `dram`         | –                                      |
| `A3_DRAM`        | `pcm`          | `--enable-dram --dram-tool intel-pcm` or `perf-imc` |
| `A3_DRAM`        | `amduprof_pcm` | `--enable-dram --dram-tool amduprof`   |
| `A3_DRAM`        | `network`      | –                                      |

`network` is in the default-on set, so `--collectors` may be omitted entirely; name it explicitly only when restricting the set.
| `A4_GPU_HBM`     | `gpu`          | –                                      |
| `A4_GPU_HBM`     | `nvlink_pcie`  | –                                      |
| `A5_APP`         | `sglang`       | `--sglang-port <PORT>`                 |
| `HOST_OS`        | `power`        | –                                      |
| `HOST_OS`        | `vmstat`       | –                                      |
| `HOST_OS`        | `swap_storm`   | –                                      |

**PID-scoped** — attach to a target PID via `--pid` or `--enable-nsys`:

| Layer            | Collector | Optional trigger        |
|------------------|-----------|-------------------------|
| `A4_GPU_HBM`     | `nsys`    | `--enable-nsys`         |
| `A5_APP`         | `perf`    | `--pid <PID>` (implicit)|
| `A5_APP`         | `bpf`     | `--pid <PID>` (implicit)|

PID-scoped collectors are automatically skipped when the SGLang server is
remote (they can only attach to a local process). Only the primary SSD
device drives the L3 HiCache capacity tile in reports; extra SSDs
produce sidecar summaries (see the multi-SSD section above).

**Layer classes** — the corresponding `LayerModule` for each
`AIStackLayer`. Each layer owns the collectors registered against its
`AIStackLayer` and provides layer-specific gating.

| AIStackLayer      | LayerModule class    | NAME slug     | Owns collectors                                              |
|-------------------|----------------------|---------------|--------------------------------------------------------------|
| `A1_L3_SSD`       | `A1L3SsdLayer`       | `a1_l3_ssd`   | smart, ssd_hw                                                |
| `A2_NVME_DRIVER`  | `A2NvmeDriverLayer`  | `a2_nvme_driver` | iostat, nvme_driver, queue_depth_sysfs, biolatency, blktrace, biosnoop |
| `A3_DRAM`         | `A3DramLayer`        | `a3_dram`     | dram, pcm, amduprof_pcm (arbitrates via `dram_tool`)         |
| `A4_GPU_HBM`      | `A4GpuHbmLayer`      | `a4_gpu_hbm`  | gpu, nvlink_pcie, nsys (honors `--nsys-pid`)                 |
| `A5_APP`          | `A5AppLayer`         | `a5_app`      | sglang, perf, bpf                                            |
| `HOST_OS`         | `HostOsLayer`        | `host_os`     | vmstat, power, swap_storm, discard                           |
| `CROSS`           | `CrossLayer`         | `cross_layer` | *(no collectors)* — synthetic layer for multi-layer overlay charts |

`LayerRegistry.ordered()` returns these in canonical presentation order:
A5 → A4 → A3 → A2 → A1 → HOST_OS → CROSS (top-of-stack to bottom).

### Anatomy of a registered collector

```python
from amoprof.base import BaseCollector, CollectorSpec, AIStackLayer, register_collector

@register_collector
class IostatMonitor(BaseCollector):
    SPEC = CollectorSpec(
        name='iostat',
        layer=AIStackLayer.A2_NVME_DRIVER,
        is_ssd_scoped=True,
        optional=False,
        enable_flag='',
        description='iostat -x per-device bandwidth/IOPS/await/util',
    )

    @classmethod
    def for_device(cls, device, args, ctx):
        # Called once per SSD device by cli/service.
        return cls(device, ctx.get('interval_s', 1.0))

    def start(self): ...        # spawn thread / subprocess
    def stop(self) -> dict: ... # join thread, return per-collector summary
```

`ctx` is a small dict that carries run-scoped data every SSD-scoped
collector might need:

| `ctx` key         | Meaning                                                       |
|-------------------|---------------------------------------------------------------|
| `raw_dir`         | `<run_dir>/raw` — where per-collector CSV/JSON sidecars land. |
| `filename_suffix` | `''` for the primary SSD, `<devslug>` (e.g. `nvme1n1`) otherwise. Used to disambiguate output filenames. |
| `duration_s`      | Effective run duration in seconds (needed by fixed-length subprocesses like `blktrace -w N`). |
| `use_sudo`        | Whether privileged commands may use `sudo -n`. Set from `--no-sudo`. |
| `interval_s`      | Polling interval for time-series collectors (`--interval-s`). |

### Lifecycle: register → init → start (three separate moments)

Registration, `__init__`, and `start()` are three distinct events. This
matters when extending AMOprof: import-time side effects, per-run
construction, and worker-thread launch are decoupled, so a bug in one
phase never contaminates the others.

```text
  ┌─────────────────────────────┐  ┌─────────────────────────────┐  ┌─────────────────────────────┐
  │  ①  REGISTER                │  │  ②  INITIALIZE              │  │  ③  START                   │
  │  Python import time         │  │  once per collect run       │  │  after every instance built │
  │  (before argv is parsed)    │  │  (after args parsed)        │  │                             │
  ├─────────────────────────────┤  ├─────────────────────────────┤  ├─────────────────────────────┤
  │  from .collectors import …  │  │  for dev in ssd_devices:    │  │  for name, c in collectors: │
  │   ↳ @register_collector     │  │    for spec in registry     │  │    c.start()                │
  │     puts class in           │  │     .ssd_scoped():          │  │                             │
  │     CollectorRegistry       │  │      cls.for_device(dev,    │  │  Spawns threads &           │
  │                             │  │        args, ctx)           │  │  subprocesses.              │
  │  Stored: class object +     │  │                             │  │                             │
  │  SPEC metadata only.        │  │  Constructor stashes config │  │  NOW: iostat runs,          │
  │                             │  │  on self. Does NOT touch    │  │  nvme smart-log fires,      │
  │  NO instances yet.          │  │  hardware.                  │  │  blktrace binary starts,    │
  │  NO threads.                │  │                             │  │  polling threads tick.      │
  │  NO /dev/* access.          │  │  NO threads yet.            │  │                             │
  │  NO sudo prompts.           │  │  NO subprocesses yet.       │  │  All start ~concurrently.   │
  └─────────────────────────────┘  └─────────────────────────────┘  └─────────────────────────────┘
        ↑                              ↑                                ↑
        │                              │                                │
        │                              │                                │
  happens once when                happens each time              happens each time
  the amoprof module is            you invoke `amoprof            you invoke `amoprof
  first loaded — module-level      collect`; also once per        collect`; also once per
  `@register_collector`            `amoprof service` cycle.       `amoprof service` cycle.
  runs.
```

**Consequences of this split**

- `import amoprof.collectors` in a notebook is safe — nothing runs, no
  privileges required.
- A broken `__init__` for one collector is caught by the registry loop
  (`try/except` around `cls.for_device(...)`) and does not stop the
  other collectors from being constructed.
- A broken `start()` on one collector is caught similarly and does not
  stop the others from starting.
- `amoprof service` calls ② + ③ every `--scrape-duration-s` seconds
  (fresh instances per cycle), but ① runs only once at process start.
- Host-wide collectors (`gpu`, `dram`, `vmstat`, `power`, `swap_storm`,
  `nvlink_pcie`, and any opted-in `pcm`/`amduprof_pcm`/`nsys`/`sglang`/
  `perf`/`bpf`) are still constructed by direct calls in `cli.py` /
  `service.py` — they will move into the registry in a follow-up but
  their ②/③ timing is identical to the SSD-scoped path.

### End-to-end flow: `amoprof collect`

```text
         ┌──────────────────────────────────────────────────────────────────┐
         │  ① Import time — REGISTER                                        │
         │     `import amoprof.collectors` and `amoprof.layers` runs        │
         │     each `@register_collector` decorator, populating             │
         │     `CollectorRegistry` with class objects + SPEC metadata.      │
         │     No instances, no threads, no I/O.                            │
         └──────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
         ┌──────────────────────────────────────────────────────────────────┐
         │  2. `cli._do_collect` argument resolution                        │
         │     • `_resolve_ssd_devices(args.ssd_device)` splits the         │
         │       `--ssd-device` value on `,`/`;` and de-dupes.              │
         │     • `args.ssd_devices = [primary, extra1, extra2, ...]`.       │
         │     • Builds a shared `_layer_ctx` dict with raw_dir, duration,  │
         │       use_sudo, interval_s, ssd_devices, pid, nsys_pid,          │
         │       dram_tool, sglang_is_remote.                               │
         └──────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
         ┌──────────────────────────────────────────────────────────────────┐
         │  ② LayerRegistry-driven build — INITIALIZE                       │
         │     for cls in LayerRegistry.ordered():   # A5→A4→A3→A2→A1→OS→CROSS
         │         layer = cls()                                            │
         │         built = layer.build(args, _layer_ctx)                    │
         │         collectors.update(built)                                 │
         │                                                                  │
         │     Inside `layer.build()` (LayerModule.build), for each spec    │
         │     the layer owns (from `CollectorRegistry.by_layer`):          │
         │       • gate on spec.enable_flag / _flag_enabled()               │
         │       • gate on layer-specific _policy_gate()                    │
         │         (A3 picks between pcm and amduprof_pcm)                  │
         │       • ssd_scoped  → cls.for_device(dev, args, ctx) per SSD;    │
         │                       primary keeps canonical key, extras get    │
         │                       __<slug> suffix + filename_suffix in ctx.  │
         │       • pid_scoped  → cls.for_pid(pid, args, ctx) via layer's    │
         │                       _resolve_pid_for_spec() (A4 uses --nsys-pid│
         │                       for nsys); skipped when sglang is remote. │
         │       • host-wide   → cls.for_host(args, ctx).                   │
         │                                                                  │
         │     Instances now exist. No threads / hardware I/O yet.          │
         └──────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
         ┌──────────────────────────────────────────────────────────────────┐
         │  ③ Start every collector — START                                 │
         │     for name, c in collectors.items():                           │
         │         try: c.start()                                           │
         │         except Exception as e: log.warning(...)                  │
         │     Each `start()` spawns its own worker thread / subprocess.    │
         │     iostat, nvme smart-log, blktrace, biolatency-bpfcc all       │
         │     launch here. Run concurrently until step 5 signals stop.     │
         └──────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
         ┌──────────────────────────────────────────────────────────────────┐
         │  5. Wait for stop condition                                      │
         │     `_wait_for_stop(args, collectors)` blocks until one of:      │
         │       --duration-s elapsed, SIGINT, --until-idle, --stop-file,   │
         │       --stop-url returned HTTP 200, or --max-duration-s ceiling. │
         └──────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
         ┌──────────────────────────────────────────────────────────────────┐
         │  6. Stop, write summaries, group multi-SSD sidecars              │
         │     for name, c in collectors.items():                           │
         │         result = c.stop()   # returns per-collector summary dict │
         │         summary[name] = result                                   │
         │         write raw/<name>_summary.json and _timeseries.csv/jsonl  │
         │     `raw/summary.json` records the full collector list plus      │
         │     `meta.ssd_devices`.  The report loader groups per-device     │
         │     sidecars into `data['l3_ssds']` for chart use.               │
         └──────────────────────────────────────────────────────────────────┘
```

### End-to-end flow: `amoprof service`

`amoprof service` uses the same registry loop but runs it inside a cycle
loop — every `--scrape-duration-s` seconds it builds fresh collector
instances, runs them, stops them, publishes their summaries to the
`/metrics` endpoint's `MetricsStore`, and repeats. The registry is
iterated once per cycle so device-scoped Prometheus series (e.g.
`amoprof_iostat__nvme1n1_read_bw_mb_mean`) refresh with each cycle.

```text
  ① REGISTER (once, at process start)
  ┌──────────────────────────────────────────────────────────────────────┐
  │  import amoprof.collectors     → @register_collector fills           │
  │  import amoprof.layers         → @register_layer     fills           │
  │  CollectorRegistry + LayerRegistry with class objects.               │
  └──────────────────────────────────────────────────────────────────────┘
        │
        ▼
  ┌──────────────────────────────────────────────────────────────────────┐
  │  argparse; parse --scrape-duration-s / --ssd-device / --collectors;  │
  │  start Prometheus HTTP server thread on --metrics-port.              │
  └──────────────────────────────────────────────────────────────────────┘
        │
        ▼
  ┌──────────────────────────────────────────────────────────────────────┐
  │  MAIN CYCLE LOOP  (until SIGINT/SIGTERM)                             │
  │                                                                      │
  │   ② INITIALIZE     _build_collectors(args, raw_dir, enabled, …)      │
  │                    ├─ host-wide collectors: direct construction      │
  │                    └─ per SSD-scoped spec in registry.ssd_scoped():  │
  │                          cls.for_device(dev, args, ctx)              │
  │                                                                      │
  │   ③ START          for name, c in collectors: c.start()              │
  │                                                                      │
  │      SLEEP         stop_event.wait(timeout=scrape_duration_s)        │
  │                                                                      │
  │      STOP          for name, c in collectors: result = c.stop()      │
  │                    store.update(name, result)  # push to MetricsStore│
  │                                                                      │
  │      PERSIST       write raw/ CSVs & summary.json for this cycle     │
  │                                                                      │
  │      (loop back to ②; fresh instances every cycle)                   │
  └──────────────────────────────────────────────────────────────────────┘
        │
        ▼ concurrent read path
  ┌──────────────────────────────────────────────────────────────────────┐
  │  HTTP /metrics                                                       │
  │  Prometheus scrapes MetricsStore → text exposition                   │
  │  (thread runs throughout; independent of the cycle loop)             │
  └──────────────────────────────────────────────────────────────────────┘
```

### Adding a new collector

1. Create `amoprof/collectors/<your_name>.py` and put the class in it,
   inheriting `BaseCollector`, decorated with `@register_collector`,
   with its `SPEC` declared. `SPEC.layer` decides which `LayerModule`
   picks up the class at build time (via `CollectorRegistry.by_layer`).
   Add a `from .<your_name> import <YourClass>` line to
   `amoprof/collectors/__init__.py` so the decorator fires and the
   class is re-exported for backward compatibility.
2. Implement `start()` and `stop()`. `stop()` must return the summary
   dict that will land in `raw/<name>_summary.json`.
3. Add the factory classmethod that matches the collector's scope:
     • SSD-scoped  → `for_device(cls, device, args, ctx)`
     • PID-scoped  → `for_pid(cls, pid, args, ctx)`
     • host-wide   → `for_host(cls, args, ctx)`
   The factory reads what it needs from `ctx` and `args`.
4. If the collector writes files, take `work_dir` and `filename_suffix`
   kwargs and honor them so multi-SSD runs don't overwrite each other.
5. If the collector needs a layer-specific gate beyond `spec.enable_flag`
   (e.g. "only build me when `dram_tool == 'amduprof'`"), override
   `LayerModule._policy_gate` on that layer. See `A3DramLayer` for the
   pcm-vs-amduprof arbitration example.

That is it — no changes needed in `cli.py` or `service.py`. The
collector shows up automatically on the next collect/service run
because `LayerRegistry.ordered()` calls each layer's `build()`, which
in turn iterates the specs registered against that layer.

---

## Quick installation

```bash
mkdir -p amoprof_1_0_0
unzip amoprof_1_0_0.zip -d amoprof_1_0_0
cd amoprof_1_0_0
chmod +x install.sh scripts/install_dram_deps.sh
./install.sh
source ~/amoprof_venv/bin/activate
amoprof --version
```
> **Install path note:** run `pip install -e .` only from the package root — the directory containing `pyproject.toml`, `setup.py`, `README.md`, and the inner `amoprof/` Python package. Do **not** run it from inside the inner `amoprof/` directory. If pip says neither `setup.py` nor `pyproject.toml` was found, run `cd ..` until `ls` shows one of those files.


For full tracing and DRAM PMU support on the target server:

```bash
sudo ./install.sh --with-dram-deps --dram-tool auto
```

`install.sh` detects the OS package manager, CPU architecture, CPU vendor, and available GPU tools. It installs common packages using the relevant package names for `apt`, `dnf`, `yum`, `zypper`, or `pacman` where available. `scripts/install_dram_deps.sh` selects AMD uProf, Intel PCM, or perf IMC support based on CPU vendor and architecture.

See [INSTALL.md](INSTALL.md) for detailed setup instructions.

---

## CLI commands

AMOprof exposes one console entry point, `amoprof`, with these subcommands:

| Command | Purpose | Typical output |
|---|---|---|
| `amoprof collect` | Collect local/remote runtime telemetry while a workload runs. | `metrics_run_*` directory with `raw/*.csv`, summaries, and optional reports. |
| `amoprof analyze` | Generate reports from an existing run directory, Prometheus, or both. | Static, Interactive, and/or Combined HTML report. |
| `amoprof retime` | Re-align legacy SGLang timeseries to the run start time. | Updated `raw/sglang_timeseries.csv` or dry-run offset report. |
| `amoprof aggregate` | Merge multiple run directories into one synthetic run and optionally enrich from Prometheus. | `merged_run_*` directory and optional reports. |
| `amoprof compare` | Compare multiple runs side by side. | Single comparison HTML with delta tables/charts. |
| `amoprof bench-lc` | Render a long-context benchmark JSON into an HTML benchmark summary. | Benchmark summary HTML. |
| `amoprof service` | Run a long-lived collection service that scrapes collectors in repeating cycles and exposes them on a Prometheus `/metrics` endpoint. | Live `/metrics` and `/healthz` HTTP endpoints plus per-cycle `raw/` output. |
| `amoprof --version` | Print installed package version. | Version string. |

Backward-compatible shortcut: if no subcommand is provided, AMOprof treats the invocation as `collect`. For example, `amoprof --duration-s 60 ...` is equivalent to `amoprof collect --duration-s 60 ...`.

---

## Command examples

### 1. Collect metrics from a local SGLang run

```bash
sudo amoprof collect \
  --output-dir ./amoprof_results \
  --label dgx_lc_l3_nvme \
  --duration-s 900 \
  --interval-s 1 \
  --sglang-host 127.0.0.1 \
  --sglang-port 30000 \
  --model openai/gpt-oss-120b \
  --ssd-device /dev/nvme2n1 \
  --hicache-path /mnt/sglang_hicache \
  --enable-dram \
  --dram-tool auto \
  --enable-blktrace \
  --enable-biosnoop \
  --setup-details setup_details_sample.json \
  --combined-report \
  --strict-sanity
```

Use `sudo` for blktrace, biosnoop, perf, and DRAM PMU collectors. Use `--no-sudo` only when AMOprof itself already runs as root.

### 2. Collect until SGLang becomes idle

Useful when the benchmark duration is not known in advance:

```bash
sudo amoprof collect \
  --output-dir ./amoprof_results \
  --label lc_until_idle \
  --sglang-host 127.0.0.1 \
  --sglang-port 30000 \
  --until-idle \
  --idle-grace-s 20 \
  --max-duration-s 7200 \
  --enable-dram \
  --enable-blktrace \
  --combined-report
```

### 3. Analyze a collected run

```bash
amoprof analyze \
  --run-dir ./amoprof_results/metrics_run_YYYYMMDD_HHMMSS \
  --combined-report \
  --interactive-report \
  --amoprof-report \
  --prom-rate-window 5m
```

### 4. Analyze a collected run and fill missing data from Prometheus

```bash
amoprof analyze \
  --run-dir ./amoprof_results/metrics_run_YYYYMMDD_HHMMSS \
  --prometheus http://PROM_HOST:9090 \
  --start 2026-06-17T23:15:54Z \
  --end   2026-06-17T23:25:54Z \
  --prom-step 15 \
  --prom-instance msl-ssg-dgx1.msl.lab:30000 \
  --prefer local \
  --setup-details setup_details_sample.json \
  --combined-report
```

### 5. Generate a Prometheus-only report

```bash
amoprof analyze \
  --prometheus http://PROM_HOST:9090 \
  --start 2026-06-17T23:15:54Z \
  --end   2026-06-17T23:25:54Z \
  --prom-step 15 \
  --prom-instance msl-ssg-dgx1.msl.lab:30000 \
  --nvme-device nvme2n1 \
  --output-dir ./prom_reports \
  --setup-details setup_details_sample.json \
  --prefer prometheus \
  --combined-report
```

### 6. Discover Prometheus target labels

```bash
amoprof analyze \
  --prometheus http://PROM_HOST:9090 \
  --list-targets
```

Use the listed `{job, instance}` pairs with `--prom-instance`, `--prom-job`, and `--prom-labels`.

### 7. Analyze with a benchmark summary file

```bash
amoprof analyze \
  --run-dir ./metrics_run_YYYYMMDD_HHMMSS \
  --bench-summary ./perf_metrics_summary.json \
  --combined-report \
  --interactive-report
```

### 8. Re-align a legacy SGLang timeseries

Use `retime` only for old run directories where SGLang time starts at zero or is shifted relative to GPU/host telemetry:

```bash
amoprof retime \
  --run-dir ./metrics_run_YYYYMMDD_HHMMSS \
  --sglang-offset-s 75 \
  --dry-run
```

Apply the offset after confirming the dry run:

```bash
amoprof retime \
  --run-dir ./metrics_run_YYYYMMDD_HHMMSS \
  --sglang-offset-s 75
```

### 9. Aggregate multiple runs into one report

```bash
amoprof aggregate \
  --run-dirs ./run_c1 ./run_c4 ./run_c8 \
  --start 1778871540 \
  --end 1778877078 \
  --prometheus http://PROM_HOST:9090 \
  --output-dir ./aggregated \
  --run-label concurrency_sweep \
  --setup-details setup_details_sample.json \
  --combined-report
```

### 10. Compare multiple runs side by side

Each `--run` uses `LABEL:DIR[:START[:END]]`. The first run is the baseline.

```bash
amoprof compare \
  --run "Baseline:./run_c1:1778871540:1778877078" \
  --run "4-way concurrency:./run_c4:1778881540:1778887078" \
  --run "FP8 KV:./run_fp8:1778891540:1778897078" \
  --output-dir ./comparison \
  --title "SGLang KV Cache Tuning Comparison"
```

### 11. Render a long-context benchmark summary

```bash
amoprof bench-lc \
  --input ./lc_bm_results.json \
  --output ./lc_benchmark_report.html \
  --title "Long-Context Benchmark" \
  --run-label qwen3_235b_awq
```

### 11a. Collect metrics from multiple SSDs in one run

Pass a comma-separated list of block devices to `--ssd-device`. Every SSD
collector (`iostat`, `smart`, `ssd_hw`, `nvme_driver`, `queue_depth_sysfs`,
`discard`, `biolatency`, and optionally `blktrace` and `biosnoop`) is
instantiated once per device.

```bash
sudo amoprof collect \
  --output-dir ./amoprof_results \
  --label dgx_lc_multi_ssd \
  --duration-s 900 \
  --interval-s 1 \
  --sglang-host 127.0.0.1 \
  --sglang-port 30000 \
  --ssd-device /dev/nvme0n1,/dev/nvme1n1,/dev/nvme2n1 \
  --hicache-path /mnt/sglang_hicache \
  --enable-blktrace \
  --enable-biosnoop \
  --combined-report
```

The first device (`/dev/nvme0n1`) is the **primary** L3 device. Its
collector outputs use the canonical filenames (`discard_timeseries.csv`,
`queue_depth_sources_timeseries.csv`, `blkparse_events.generated.csv`,
`blktrace_data/`, `biosnoop_events.csv`, …) and its `ssd_hw` capacity/df
stats are merged into `raw/smart_summary.json` for the HiCache capacity
tile.  Additional devices produce sidecar variants with a `_<devname>`
suffix on filenames and `__<devname>` on collector summary keys, e.g.:

```text
raw/discard_timeseries.csv              # primary /dev/nvme0n1
raw/discard_timeseries_nvme1n1.csv      # extra /dev/nvme1n1
raw/discard_timeseries_nvme2n1.csv      # extra /dev/nvme2n1
raw/queue_depth_sources_timeseries.csv          # primary
raw/queue_depth_sources_timeseries_nvme1n1.csv  # extra
raw/blktrace_data/trace.blktrace.*              # primary
raw/blktrace_data_nvme1n1/trace.blktrace.*      # extra
raw/blkparse_events.generated.csv               # primary
raw/blkparse_events.generated_nvme1n1.csv       # extra
raw/biosnoop_events.csv, biosnoop_events_nvme1n1.csv, ...
raw/smart_summary.json                          # primary HiCache tile
raw/smart_summary__nvme1n1.json                 # extra sidecar
```

`summary.json :: meta` records both fields:

```json
{
  "ssd_device": "/dev/nvme0n1",
  "ssd_devices": ["/dev/nvme0n1", "/dev/nvme1n1", "/dev/nvme2n1"]
}
```

`amoprof service` accepts the same comma-separated `--ssd-device` and
exposes each per-device collector as its own Prometheus series
(e.g. `amoprof_iostat__nvme1n1_read_bw_mb_mean`).

### 12. Run AMOprof as a long-lived collection service

Instead of a single bounded `collect` run, run AMOprof as a service that scrapes
the enabled collectors in repeating cycles and exposes the latest cycle on a
Prometheus `/metrics` endpoint. A Prometheus server can then scrape AMOprof
directly, and `/healthz` can be used for liveness checks.

```bash
sudo amoprof service \
  --metrics-port 9101 \
  --metrics-host 0.0.0.0 \
  --collectors gpu,dram,vmstat,iostat,smart \
  --scrape-duration-s 30 \
  --interval-s 1 \
  --ssd-device /dev/nvme0n1 \
  --hicache-path /mnt/sglang_hicache \
  --output-dir ./amoprof_results
```

Each cycle runs for `--scrape-duration-s` seconds, then refreshes the metrics
served at `http://<host>:<metrics-port>/metrics`. Use `--collectors all` for all
always-on collectors, or pass a comma-separated subset. `--ssd-device` also
accepts a comma-separated list of devices; every SSD-scoped collector runs
once per device and its Prometheus metric name gets the per-device suffix
(the primary keeps canonical names, extras become `amoprof_<collector>__<dev>_<key>`).
Add `--enable-blktrace`
(with `--blkparse-interval-s` to control how often the live trace is parsed),
`--enable-biosnoop`, `--enable-amduprof-pcm`, `--enable-nsys`, or `--enable-all`
for the optional privileged collectors. Pass `--sglang-port` to also scrape a
running SGLang server, or `--pid` to attach the perf/bpf collectors. Use
`--no-sudo` only when AMOprof itself already runs as root. The service runs until
it receives `SIGINT`/`SIGTERM`, and each cycle's raw output is written under
`--output-dir`. Defaults can also be supplied via the `AMOPROF_METRICS_PORT`,
`AMOPROF_SCRAPE_DURATION_S`, `AMOPROF_BLKPARSE_INTERVAL_S`, and related
environment variables.

Quick check while the service is running:

```bash
curl -s http://127.0.0.1:9101/healthz      # -> ok
curl -s http://127.0.0.1:9101/metrics      # Prometheus exposition text
```

#### Run the service under systemd

A unit file and an example environment file are provided under `systemd/`. The
unit is fully configured through the environment file, so it does not need to be
edited for normal use.

```bash
# 1. Install AMOprof to a system-wide venv so root can reach the console script.
sudo ./install.sh --venv /opt/amoprof_venv

# 2. Install the environment file and edit it for your host.
sudo install -d /etc/amoprof
sudo install -m 0644 systemd/amoprof.env.example /etc/amoprof/amoprof.env
sudo $EDITOR /etc/amoprof/amoprof.env

# 3. Install and start the service.
sudo install -m 0644 systemd/amoprof.service /etc/systemd/system/amoprof.service
sudo systemctl daemon-reload
sudo systemctl enable --now amoprof.service

# 4. Inspect it.
systemctl status amoprof.service
journalctl -u amoprof.service -f
curl -s http://127.0.0.1:9101/healthz
```

Every `AMOPROF_*` variable in `/etc/amoprof/amoprof.env` maps to the matching
`amoprof service` flag. Flags without a dedicated variable (for example
`--collectors`, `--enable-blktrace`, `--no-sudo`, `--sglang-port`) are passed
through `AMOPROF_EXTRA_ARGS`. If you install the venv somewhere other than
`/opt/amoprof_venv`, update the `ExecStart` path in `systemd/amoprof.service`.

#### Run the service with a subset of collectors (e.g. DRAM only)

`--collectors` has no dedicated environment variable, so select the collector
subset through `AMOPROF_EXTRA_ARGS`. To run the service with only the DRAM
collector, edit `/etc/amoprof/amoprof.env` so that line reads:

```ini
# /etc/amoprof/amoprof.env
AMOPROF_EXTRA_ARGS="--metrics-host 0.0.0.0 --collectors dram"
```

`AMOPROF_EXTRA_ARGS` is a single string, so keep any other non-env flags you
need on the same line. Pass a comma-separated list for more than one collector,
for example `--collectors dram,gpu,vmstat`. `dram` is an always-on collector, so
no `--enable-*` flag is required. Apply the change with:

```bash
sudo $EDITOR /etc/amoprof/amoprof.env
sudo systemctl restart amoprof.service
journalctl -u amoprof.service -n 20      # confirm "Collectors : dram"
```

Only the metrics for the selected collector(s) then appear at
`http://<host>:<metrics-port>/metrics` (for DRAM, the `amoprof_dram_*` series).

---

## Common collector options

| Option | Use |
|---|---|
| `--sglang-host`, `--sglang-port` | Scrape SGLang `/metrics` and server info. |
| `--ssd-device /dev/nvmeXnY[,/dev/nvmeAnB,...]` | Local L3 device(s) for physical storage analysis. Accepts a single device or a comma-separated list to monitor multiple SSDs in the same run. The first device is the primary L3 device (drives the HiCache capacity tile); extra devices produce per-device sidecar summaries and CSVs. |
| `--hicache-path PATH` | Resolve local file-backed HiCache/L3 location and filesystem capacity. |
| `--enable-blktrace` | Capture block I/O completions for request-size, LBA, latency, and physical R/W charts. |
| `--enable-biosnoop` | Add per-PID/per-stream block I/O attribution. |
| `--enable-dram --dram-tool auto` | Collect host DRAM bandwidth from AMD uProf, Intel PCM, or perf fallback. |
| `--enable-nsys` | Capture Nsight Systems GPU traces when the tool is installed and supported. |
| `--setup-details FILE` | Add model, TP, HBM, DRAM, L3 capacity, and launch configuration context. |
| `--bench-summary FILE` | Attach benchmark-level summary/percentile validation to reports. |
| `--strict-sanity` | Fail early on missing/invalid critical run metadata. |

---

## Common analyze/report options

| Option | Use |
|---|---|
| `--combined-report` | Generate the tabbed Executive / Interactive / End Report HTML. |
| `--interactive-report` | Generate only the interactive Plotly report. |
| `--amoprof-report` | Generate only the static End Report. |
| `--report-theme dark|light|off` | Select report styling and explanatory tooltip behavior. |
| `--prefer local|prometheus` | Pick which source wins when local CSVs and Prometheus both provide the same metric. |
| `--prom-rate-window 5m` | Set Prometheus `rate()` window for percentile timeseries. |
| `--sglang-page-size N` | Override SGLang page size/KV block size when it cannot be auto-detected. |
| `--server-info-url URL` | Fetch SGLang server metadata from an explicit endpoint. |
| `--setup-details-override` | Allow manual setup details to replace server-info-derived metadata. |

---

## Dependency overview

| Area | Tools |
|---|---|
| Python package | Python 3.10+, pip, venv, pandas, numpy, matplotlib, scipy, requests |
| GPU/HBM | nvidia-smi and optionally DCGM/dcgmi |
| SGLang metrics | SGLang Prometheus `/metrics` endpoint |
| L3 local storage | nvme-cli, sysstat/iostat, blktrace/blkparse, sysfs |
| Per-stream attribution | bpfcc-tools / biosnoop-bpfcc |
| DRAM bandwidth | AMD uProf on AMD x86_64, Intel PCM on Intel x86_64, perf IMC fallback |
| Optional tracing | bpftrace, Nsight Systems |

---

## Executive Bottleneck Analysis

Cards are ordered by driver, each scattering that driver against every signal
of every **configured** tier, ranked by `|Pearson r|` descending.

| Card group | Drivers |
|---|---|
| Concurrency → latency & resource pressure | One chart per latency metric (TTFT · TPOT · E2E), each carrying five parameters: running requests on X, with latency, storage queue depth, GPU util and HBM used as normalised curves. Reveals the *order of the knees* — the resource that bends before latency does is the constraint |
| HBM composition | Per-GPU split of measured HBM into model weights, reserved KV pool, occupied KV, and residual (activations / CUDA context / fragmentation). Reports a consistency check when weights + pool exceed measured usage |
| Queue depth across layers | Each layer's queue vs its own saturation reference: A5_APP `num_queue_reqs` / `num_running_reqs`, A1/A2 storage QD, NET TCP retransmits and link util, A3_DRAM BW pressure (proxy — no controller queue exposed). Includes p50/p90/p99 bars and a cross-correlation lead/lag "backpressure origin" list |
| Driver → layer response | One chart per driver (input/output tokens, evict, load-back, prefetch, backup) showing binned median response of every configured layer signal, normalised to each signal's own observed max so units share one axis |
### Poisoned DRAM samples

`metric_kernels.sanitize_bandwidth_samples()` and `DRAM_SANE_MAX_GBS` are the
**single rule**, applied on every surface. They were not, initially: the
Executive filtered and the End Report did not, so one file produced 0.86 GB/s
on one tab and 251,246,841 GB/s on another — the exact class of divergence the
kernel layer exists to prevent.

A handful of bad samples destroys an arithmetic mean. Observed on a real run:
956 rows of ~0.42 GB/s with five rows at 4.8e10 (44.7 GiB — a memory
*quantity* in a bandwidth column), giving `mean = 226,122,157 GB/s` while
`min`, `first` and `last` were all correct.

Samples outside `0 … 100,000 GB/s` are therefore excluded **per sample**
before averaging, and the count of exclusions is stated in the tile note.
Dropping the samples rather than the column matters: the measurement is real,
a few points are not, and rejecting the whole series would lose a working PMU
feed.

The upstream defect is collector-side — those samples should never be
published — so the exclusion count is worth watching rather than ignoring.

A **plausibility guard** drops any bandwidth series peaking above 100 TB/s.
No host moves that much; such a series is a computation artefact — a counter
reset spiking a delta, or a cumulative value read as a rate — and charting it
destroys the log axis for every other tier while asserting something false.
Dropped series are named in "Tiers not shown" with their peak, so the artefact
is visible rather than silently removed.

| Bandwidth per cache tier | Absolute **GB/s on a log axis**. A percentage needs a ceiling, and for a remote store the ceiling is often unknown or elastic — a percentage against an invented one says less than the real number. A log axis keeps HBM (TB/s) and NVMe (GB/s) legible together, which is what the percentage was solving for |
| KV bytes resident per tier | Absolute **GB on a log axis**, no tier capacity needed. Bytes are the native unit for L2/L3/L3.5 — tokens there are derived — and a remote store's capacity can change under you, making a percentage against it unstable in a way the byte count is not |
| ~~Tier bandwidth utilisation~~ | Each tier as a percentage of **its own** bandwidth ceiling — L1 HBM vs device peak, L2 DRAM vs controller peak, L3/L3.5 vs device spec or observed peak, NET vs link speed. Absolute bandwidth is not comparable across tiers: HBM peaks in thousands of GB/s while NVMe peaks in the low GB/s, so an absolute axis is dominated by L1 |
| KV tier fill % | Companion chart: each tier as a percentage of **its own** capacity on one 0–100 axis. The absolute view cannot answer "how full is this tier" — a remote store holding millions of tokens dwarfs an HBM pool holding tens of thousands, so a tier at 95% full is invisible next to a larger tier at 5%. Only tiers with a known ceiling appear |
| KV tokens per tier | Occupancy of every configured tier on **one axis, in tokens** — L1 HBM pool, L2 HiCache, L3 local storage, L3.5 remote store, each independent of the others — with each tier's configured capacity as a dashed ceiling. Tokens are comparable across tiers in a way GB is not: a token costs the same KV bytes wherever it sits |

Chart timelines use the **same window the report header states** (`duration_s`),
so the axis and the "Window: N min" line cannot disagree. Falling back to the
data extent silently shrank the axis to wherever samples happened to land — a
tier reporting for half the window then filled the whole chart. If samples run
past the stated duration the axis widens rather than clipping: metadata never
hides data. Tick precision follows the span, so labels do not repeat on short
windows.

Every time-axis chart in the section — queue occupancy, KV tokens per tier,
tier fill %, bandwidth utilisation — draws vertical gridlines and tick labels
across the window. The queue chart previously labelled its axis "elapsed (s)"
while drawing no ticks at all, which promised a timeline it did not provide.

The X axis spans the **full window selected by `--start`/`--end`**, not merely
the extent of the data: a tier reporting for only part of the run occupies
only its own portion of the axis rather than stretching to fill it. Ticks show
UTC wall-clock when the run's start epoch is known, elapsed time otherwise, and
the axis caption states the window span.

The L3 legend entry reads **L3-local storage** (hyphenated) deliberately: when
the backend is remote, a post-processing pass rewrites the phrase `L3 local
storage` to the L3.5 wording across the whole document, which made two legend
rows both read "L3.5". The hyphenated form is not in that rewrite table.

L3 occupancy is **gated on the backend being local**. `backup`/`prefetch`
counters describe movement to whatever backend HiCache uses; when that backend
is remote (mooncake / ai-memory-node / 3fs) the traffic belongs to L3.5, and
attributing it to local disk invents a tier that is not configured. The
symptom was the occupancy chart showing an L3 line while the fill chart —
which excludes tiers with no capacity — correctly did not.

L3 occupancy prefers a filesystem measurement (`df` on the HiCache path, from
the `ssd_hw` collector) and falls back to `backup − prefetch` token counters,
labelled **DERIVED** so it is not read as a measurement. SGLang exports no
resident-token gauge for the disk tier.

The timelines are their own **card and section**, `Latency & throughput over
the run`, placed directly after the distribution section. Interleaving
full-width timelines with half-width percentile bars in one flex container
rendered badly regardless of row breaks; a separate card avoids the layout
problem entirely and reads better.

Prometheus can return one histogram as **several series** when the label set
differs — a restarted server, more than one `model_name`, a stale target — and
the CSV then carries duplicate columns for a single metric. Exact-name lookup
sees only one of them, which may be the sparse or empty one: TTFT and E2E each
had two columns and silently produced no timeline, while ITL had one and
worked. Histogram components are now summed element-wise across every matching
column, which is the correct aggregation across label sets and keeps
`sum ÷ count` a properly weighted mean.

| TTFT / E2E / queue-wait percentiles over the run | p50, p90 and p99 **as time series**, from per-interval histogram bucket deltas. The mean-over-time chart hides the tail; the percentile card shows the tail but not when it happened. A p99 that spikes once and one that degrades steadily look identical in every other view |
| Latency over the run | TTFT, TPOT/ITL and E2E as per-interval means on a log axis. A latency that degrades steadily and one that spikes once can share a p90; only the timeline separates them |
| Token throughput over the run | Input and output tokens/s per interval, log axis |
| Memory hierarchy capacity used (% of each tier) | The same bytes as a percentage of each tier's own capacity. Absolute GB cannot answer *"how full is this tier"* — a store holding terabytes dwarfs an HBM pool holding hundreds of GB, so a tier at 95% is invisible beside a larger tier at 5%. Only tiers with a **known** ceiling appear; a percentage of an unknown capacity is not a number |
| Memory hierarchy capacity used | Absolute **GB resident** on a log axis, not % of capacity — same reasoning as the tier charts: the percentage needs a ceiling that may be unknown or elastic |
| KV cache hit ratio (time series) | Every definition on one 0–100 axis over the run. The percentile bars say how the ratio was *distributed*; this says *when it moved* — a hit rate that collapses partway through and a steady one can share a p50, and only the timeline separates them |
| KV cache hit ratio | p50/p90/p99 for **each definition** side by side: prefill token-weighted, whole-prompt token-weighted, and SGLang's own gauge. They can differ by tens of points on the same run, so a single headline number is easy to over-read |
| Percentile distribution *(rendered above Bottleneck Analysis, directly under the KPI grid)* | TTFT, TPOT, ITL, E2E latency, input tokens/request, output tokens/request — p50/p90/p99 **for the whole window**, as labelled bar charts |
| Network fabric | Token rates vs NIC/IB bandwidth, packets/s, link utilisation, TCP retransmits, drops |
| Per-tier throughput | Input/output tok/s vs L1 GPU util & HBM used, L1 HBM bandwidth, L2 DRAM BW, L3 read/write BW |
| Request latency | Input/output tok/s vs per-interval mean E2E latency |
| Token movement | Evict, load-back, prefetch, backup rates vs all configured tier signals |
| Phase activity | Prefill-compute, prefill-cache-hit, decode rate, running requests, queued requests vs all configured tier signals |

Tier signals available as correlation axes:

- **NET** — total/rx/tx MB/s, packets/s, link util %, TCP retrans/s, drops/s
- **L1** — GPU util %, HBM used GB, HBM bandwidth (GB/s where the GPU model
  resolves to a known peak, otherwise HBM BW util %)
- **L2** — DRAM total/read/write GB/s
- **L3** — read/write MB/s, read/write IOPS, read/write/combined latency ms,
  queue depth

Queue primitives are **not equivalent** and the card says so: storage QD and
NIC drops indicate a saturated *device*, while `num_queue_reqs` is SGLang's
scheduler `waiting_queue` — a software queue in host memory indicating a
saturated *allocation* (usually the KV pool). It costs no hardware resource,
so it normally *lags* the real constraint rather than causing it.

The Executive header shows model, runtime, GPU, window and cache tier only.
Telemetry-source availability badges were removed from it: they described
collector coverage rather than a result, and read as warnings about the tooling
rather than findings about the run. Coverage is still reported by `analyze` at
collection time via its "Data sources MISSING" log block, and any panel whose
source is absent renders an explicit placeholder rather than a misleading zero.

Every chart point, bar and line carries an SVG `<title>`, so hovering shows
coordinates in the signal's **own unit** — not the normalised percentage that
is plotted where axes are shared.

L2 capacity falls back to `--hicache-ratio x max_total_num_tokens x KV
bytes/token` when `--hicache-size` is 0 (SGLang's default). Without that the
configured capacity reads 0 GB and every derived L2 figure is clamped to zero
by the "bounded by configured capacity" rule — the DRAM used tile showed 0
even though occupancy had been measured.

All charts in the section share one visual format: title at 10px, subtitle at
8.5px, axis ticks at 7.5px, `rx="8"` dark panel, and an X/Y formula caption
beneath. Wide charts (layer response, queue views) use a 760px viewBox and span
the full card via `.corr-chart-wide`; scatters use 460px and sit side by side in
the strip. Both are `.corr-chart`, so padding, background and shrink behaviour
match.

Every card is a collapsible `<details>` labelled with the AI stack layers it
covers (`A5_APP ↔ A4_GPU_HBM · A3_DRAM · A1_L3_SSD · A2_NVME_DRIVER`). Only
**Latency & token-size distribution** is expanded by default — the rest open
on demand, so the tab opens as a summary rather than a wall of scatters.

Because each card's `<summary>` carries `data-amoprof-section`, the cards also
appear in the tab's section dropdown for direct navigation; that selector
already collected `details > summary`.

Each token-movement card **pins its physically expected pairing** so it is
always drawn, whatever its rank: evict vs L2 DRAM *write* BW and L3/L3.5 write,
load-back vs L2 DRAM *read* BW, prefetch vs L3/L3.5 read, backup vs L3/L3.5
write. Ranking by |r| alone buries these — a noisier signal with a higher
coefficient outranks the mechanism the tier exists for — and a weak r on a
pinned pair is itself the finding: the movement is not reaching that tier.

Signals *derived from* a driver (L1→L2 evict BW is the evict rate times KV
bytes/token) are excluded from that driver's own ranking, since r = 1.00 by
construction and they would otherwise crowd out the measured correlations.

Each section scrolls **vertically within itself**, capped at `--corr-h`
(default `74vh`), so an expanded card shows roughly one screenful of charts at
a time. A section with fifteen charts otherwise expands to thousands of pixels
and pushes everything after it far off-page, leaving no sense of position in
the report. `overscroll-behavior: contain` stops the page scrolling once the
section reaches its end.

Charts sit in a **wrapping grid**, not a horizontal strip: as many per row as
the viewport fits at ~430px each, wrapping onto further rows, so the page
scrolls vertically. The previous non-wrapping strip hid everything past the
second chart behind a sideways scrollbar most readers never touched — the
charts existed but were effectively invisible. Full-width charts (timelines,
layer response) span every column; below 900px the grid collapses to one
column.

Two size guards keep the tab loadable. Both are lossless for the reported
statistics — `r` is always computed on the full time-aligned series,
decimation only thins plotted points, and every pair below the cap still
appears with its `r` in the card footer:

```python
_CORR_MAX_SCATTERS_PER_CARD = 6    # scatters drawn per card
_CORR_MAX_PLOT_POINTS       = 400  # circles plotted per scatter
```

HBM bandwidth resolves from `DCGM_FI_PROF_DRAM_ACTIVE` (a 0–1 duty cycle),
else `DCGM_FI_DEV_MEM_COPY_UTIL`, else nvidia-smi `utilization.memory`.
Normalisation is by observed magnitude, not by metric name, so an exporter
that already reports percent is not scaled twice. The GB/s axis needs the GPU
model in the peak table (A100, H100, H200, H800, A800, B100, B200, GB200,
H20, L40/L40S, MI300X, V100); an unrecognised model keeps the percent axis
rather than deriving GB/s from a guessed peak.

TPOT and ITL are separate charts, each gated on its own histogram
(`sglang_time_per_output_token_seconds` and
`sglang_inter_token_latency_seconds`). SGLang builds that publish only ITL
omit the TPOT chart rather than relabelling ITL data as TPOT.

Percentiles prefer the values **Prometheus itself computed**
(`server_ttft_p50_ms` and friends, merged into `sglang_summary.json` by the
fetch, via `histogram_quantile` over the range) — the same source the summary
tiles use, so the chart and the tiles cannot disagree.

Local bucket accumulation is the fallback when those fields are absent. It is
bucket-limited: on a short window the quantile snaps to a bucket edge
(`2,000.0 ms` exactly) while the tiles showed the interpolated `1,541 ms`.
Same data, two methods, two numbers.

When the fallback is used, percentiles are **whole-window**: every sampling interval's bucket deltas are
summed into one histogram covering the selected period, then quantiled once —
the figure `histogram_quantile` over the full range would give. Deltas are
clamped non-negative before accumulating, so counter resets do not corrupt the
total. The quantile is linearly interpolated inside its containing bucket; a
value landing in the open-ended `+Inf` bucket is reported as that bucket's
floor, i.e. a lower bound rather than an invented number. Each bar is labelled
with its value and the card footer repeats all five metrics as text.

---

## Verifying the installation

`amoprof --version` prints the version *and* a build fingerprint:

```
amoprof 1.19.8
  package: /opt/amoprof/lib/python3.12/site-packages/amoprof
  modules:
    [x] network collector
    [x] metric formulas
    [x] metric kernels
  report features:
    [x] percentile p50/p90/p99 charts
    [x] network correlation card
    [x] HBM bandwidth card (DCGM)
    [x] E2E latency card
    [x] report naming convention
    [x] gpu_config capture
```

The version number alone cannot distinguish a correct install from a stale
tree an editable install still points at — both print the same string. The
fingerprint probes the deployed files, so an unchecked box means that tree
predates the feature and needs reinstalling, not re-running `analyze`.

`package:` shows which directory is actually imported, which is the fastest
way to spot a venv or editable install resolving somewhere unexpected.

Note that **network charts additionally require a fresh collection** —
`network_timeseries.csv` only exists for runs collected after the collector
was installed. Percentile charts, by contrast, appear on a re-`analyze` of
existing raw data, since the histogram buckets are already present.

---

## Report file naming

`analyze` writes reports using a fixed, sortable convention:

```
amoprof_<version>_<date>_<time>_<gpunode>_<model>_<report_type>.html

# Prometheus/local run with an explicit --start/--end window (named after the
# window it describes, in UTC):
amoprof_v1.19.8_20260813T0000Z-20260813T0145Z_ssi-gpubnode03_gemma-4-31b-it_combined.html
amoprof_v1.19.8_20260813T0000Z-20260813T0145Z_ssi-gpubnode03_gemma-4-31b-it_interactive.html
amoprof_v1.19.8_20260813T0000Z-20260813T0145Z_ssi-gpubnode03_gemma-4-31b-it_end.html

# Local collect with no window selected (falls back to generation time):
amoprof_v1.19.8_20260806_1556_msl-ssg-dgx1_gpt-oss-120b_combined.html
```

| Field | Source |
|---|---|
| `version` | `amoprof.__version__`, dots preserved |
| `date` / `time` | The **analysed window** — `YYYYMMDDTHHMMZ-YYYYMMDDTHHMMZ` in UTC — whenever `--start`/`--end` select one. Falls back to a single per-invocation generation timestamp (`YYYYMMDD_HHMM`) when no window is given, as on a plain local collect |
| `gpunode` | `hostname` from `gpu_config.json`, recorded at *collection* time |
| `model` | `setup_details.json` `Model`, else `server_info.json` `model_path`; path trimmed to its leaf |
| `report_type` | `combined`, `interactive`, `end`, `executive` |

Every field except `version` is lowercased and dash-separated, so
`split('_')` always yields exactly six fields. Missing metadata degrades to
`unknown-node` / `unknown-model` rather than dropping a field, keeping the
name parseable.

The node comes from `gpu_config.json` rather than the OS hostname because
`analyze` regenerates `setup_details.json` from `server_info` (dropping any
`Host` key), and analysis may run on a different machine than collection did.

The window is seeded by whichever path selects one: the Prometheus branch
parses `--start`/`--end` itself, and the local `--run-dir` branch takes the
values its time filter computed. Both must seed it — an earlier build seeded
only the local branch, so Prometheus-mode reports silently fell back to the
render timestamp.

### Timezone handling

Prometheus stores everything in UTC, but an operator asking for "17:00 to
18:45" means their own wall clock. `--start`/`--end` therefore interpret a
**naive** datetime in the local timezone of the machine running `analyze`, and
convert to UTC for the query:

```
--start 2026-08-12T17:00:00 --end 2026-08-12T18:45:00
Query window: 2026-08-13 00:00 → 01:45 UTC  (= 2026-08-12 17:00 → 18:45 PDT)
```

An explicit offset (`-07:00`) or a trailing `Z` always wins; only naive input
is localised. Relative forms (`2h`) and Unix timestamps are unaffected. Set
`AMOPROF_NAIVE_TZ=utc` to restore the previous behaviour.

This previously treated naive input as UTC, which silently profiled a window
seven hours off in US/Pacific — and the mistake is invisible in the output,
because the query succeeds and returns real data for the wrong hours.

Window stamps in filenames are **UTC and suffixed `Z`**. The analysing host's local
timezone is not a property of the data, and naming by it would label the same
window differently on two machines. Note that `--start`/`--end` treat a naive
datetime as UTC — pass an explicit offset (`2026-08-07T14:42:00-07:00`) or a
Unix timestamp for a local wall-clock window.

Naming by window rather than render time means two renders of the same period
produce the same filename, and re-analysing an old window sorts by when the
data happened rather than when the report was made.

`cli.report_filename(raw_dir, report_type, when=, version=, window_start=, window_end=)` is public — use
it when publishing reports to a shared location so stashed filenames match.

---

## Prometheus metrics endpoint

`amoprof service` exposes `/metrics`. Every enabled collector's summary is
published automatically as `amoprof_<collector>_<key>`; only scalar values
are emitted.

Recently added families:

| Family | Contents |
|---|---|
| `amoprof_network_*` | Aggregate rx/tx/total MB/s, packets/s, errors, drops, TCP retransmits, peak link utilisation |
| `amoprof_network_iface_<if>_*` | Per-interface rx/tx mean, link speed, peak link utilisation. Interface names are sanitised, so IB port `mlx5_0:1` becomes `iface_mlx5_0_1_*` |
| `amoprof_gpu_config_*` | Per-GPU HBM capacity, device count, TP/DP, and `hbm_capacity_gb` (per-GPU x TP x DP) |

`gpu_config` is a pseudo-collector: `cli._write_gpu_config()` writes the file
directly, and `service.py` folds it into the metrics store so it reaches
`/metrics` alongside real collector output.

Note the exporter builds metric names by concatenation and has no label
support, so per-interface and per-GPU series are distinct metric *names*
rather than one metric with an `iface=` / `gpu=` label. This matches the
existing `amoprof_blktrace_qd_*` convention but means `sum by (iface)` is not
available.

---

## KV page size

`page_size` (tokens per KV block) is taken from what the **server reports** —
`setup_details.json` / `server_info.json` — in preference to
`--sglang-page-size`. Every KV-block figure in the report scales by it, so a
stale flag silently multiplies block counts by the ratio between the two: a
`--sglang-page-size 1` against a server running 64 made every block figure 64x
wrong. When the two disagree the server wins and the mismatch is logged with
the skew it would have caused. The flag is used only when the server reports
nothing.

---

## Model configuration capture

`--model-path` (on `collect`, `analyze` and `service`; env
`AMOPROF_MODEL_PATH`) points at the served model directory or its
`config.json`. `cli._read_model_config()` extracts `num_hidden_layers`,
`num_key_value_heads`, `head_dim`, `hidden_size`, `num_attention_heads`,
`torch_dtype` and related fields into `raw/model_config.json`.

`--model-path` accepts any of:

| Form | Example |
|---|---|
| Bare repo id (searched in the HF cache) | `google/gemma-4-31B-it` |
| HF cache entry (resolves `refs/main`) | `~/.cache/huggingface/hub/models--google--gemma-4-31B-it` |
| Snapshot directory | `.../snapshots/3548789.../` |
| `config.json` directly | `.../snapshots/3548789.../config.json` |

Prefer the repo id or the cache entry: snapshot directories are named by
commit hash, so a hardcoded path breaks the next time the model is re-pulled.
Cache roots are taken from `HUGGINGFACE_HUB_CACHE`, `HF_HUB_CACHE`, `HF_HOME`,
then `~/.cache/huggingface/hub` and `/root/.cache/huggingface/hub`.

This matters because **KV bytes per token scales every derived bandwidth
figure in the report**. Without a config it is inferred from the model *name*,
which is a guess — and a guess that was wrong by 3.6× on a model no table
recognised.

* Multimodal configs that nest attention parameters under `text_config` /
  `language_model` are handled; the text-decoder block wins, since the KV
  cache is a property of the decoder.
* `head_dim` is derived from `hidden_size / num_attention_heads` when absent,
  and the derivation is recorded.

In service mode the config is written each cycle and published as
`amoprof_model_config_*` gauges, so `analyze --prometheus` can recover the
architecture for a historical window without the raw files being retained. If
those metrics are absent, `analyze` warns that KV bytes/token will be estimated
and names the flag that fixes it.

---

## GPU configuration capture

`cli._write_gpu_config()` runs during `collect` and once per `service`
cycle, after server-info resolution so TP/DP are known. It queries
`nvidia-smi --query-gpu=index,name,uuid,memory.total,compute_mode,pcie...`
and writes `raw/gpu_config.json`:

- per-GPU `name`, `uuid`, `memory_total_gb`
- `gpu_count`, `hbm_per_gpu_gb`, `hbm_total_gb`, `driver_version`, `hostname`
- `tp_size`, `dp_size`, `gpus_in_use` (TP x DP, clamped to the physical count)
- `hbm_capacity_gb` = `hbm_per_gpu_gb` x `gpus_in_use`

Reports prefer this file over values inferred from `setup_details.json`, so
GPU model, device count and the "HBM used" denominator come from the
hardware. Absent `nvidia-smi` it writes nothing and the previous inference
path still applies.

If Server Info or GPU panels are empty, see Troubleshooting below.

---

## Validation suites

Two runnable suites ship in the package root:

| Suite | Answers |
|---|---|
| `validate_math.py` | Is the arithmetic right? Kernels vs scipy/numpy references |
| `validate_report.py` | Does the generated HTML report hold up? Parses the artefact itself |

```bash
python3 validate_math.py
python3 validate_report.py <report>.html
```

Both exit non-zero on failure. See **Testing** near the end of this document
for what each group checks, which suite to run after which kind of change,
and the one check that is left failing deliberately.

---

## Inferred setup fields

`Application / Benchmark` and `Inference Cache Tier` are rarely declared
explicitly — SGLang does not always echo `--enable-hierarchical-cache` into
`server_info`, and a Prometheus-only run has no launch command at all. Rather
than printing "unknown", both are inferred from evidence the run already
carries, and the inference is labelled so it is distinguishable from a
declaration.

**Application / Benchmark**, most specific first:

1. A harness summary file in the run directory (`benchmark_summary.json`,
   `sweagent_summary.json`, `swebench_summary.json`).
2. Traffic shape: steady high concurrency reads as synthetic load, variable
   concurrency as interactive serving. The source line states the numbers —
   e.g. `inferred from concurrency: mean 8.7 / peak 12 requests`.
3. Prompt length: long-context vs short-prompt workload.

**Inference Cache Tier** now keys on evidence rather than requiring the flag: a
sized L2/L3 allocation, a declared storage backend, a non-zero
`--hicache-ratio`, or measured host-cache residency. It lists **only the tiers
this run actually has** — naming a tier that is not configured is worse than
saying nothing, because it sends the reader looking for charts that
legitimately do not exist.

Numeric summary lookups fall back to aggregating the timeseries column when
`sglang_summary.json` lacks the field, which is the normal case on the
Prometheus path.

---

## DRAM bandwidth without a PMU

When no PMU collector ran, the Executive `DRAM BW` tile read **0.0 GB/s** while
the End Report showed a populated "System DRAM (CPU-side) Bandwidth" section.
Both were correct about their own source and neither said so clearly: the End
Report was showing the **SGLang KV-movement fallback** (evict + load-back +
prefetch tokens x KV bytes/token / window), the Executive was showing the PMU
channel measurement, which was genuinely absent.

The Executive now falls back to the same estimate, relabelled so the two can
never be confused:

* tile becomes **`DRAM BW (KV movement est.)`**
* the tier bandwidth chart gains **`L2 host DRAM (KV movement est., not PMU)`**

The token totals feeding it are **window deltas**, differenced from the
timeseries endpoints — not the cumulative counter the summary carries. The
estimate divides by the window length, so a cumulative value is wrong by the
ratio of server uptime to window length: on a server up for days, analysed
over four hours, that was the difference between ~0.4 GB/s and 451,771,749
GB/s. When no series exists the function returns 0 rather than a summary value
that cannot be interpreted as window traffic.

Both surfaces call `metric_kernels.kv_movement_bandwidth`. They previously had
separate implementations that disagreed on the unit — one divided by `1024**2`
(GiB), the other by `1e9` (GB), a **7.4% difference on identical inputs**. GB
is now canonical, matching how DRAM peak bandwidth is quoted.

This is *logical* host-tier movement, not memory-controller bandwidth. Use it
for correlation and shape; it cannot prove channel saturation. For that, run
with `--enable-dram`.

---

## Interactive chart legends

Legend geometry is **derived**, not assumed. Previously the bottom margin was a
fixed 120px against a legend anchored at `y=-0.14`: fine for one row, and
overlapping as soon as the legend wrapped. It is now computed from the legend
offset, the number of rows the trace count implies, and the tick labels; the
figure height grows with it.

Right margins for vertical legends scale with the **longest trace name**
(`150 + len × 7`, capped at 460px) rather than a flat 320px, so long series
names no longer run under the plot.

---

## Chart legend placement

The GPU Utilisation / Power / HBM timeline (End Report) is a Plotly figure
with a horizontal legend below the plot. Its bottom margin must reserve room
for that legend: at `y=-0.24` on a 520px figure the legend needs ~125px, and
the margin was 74px, so it rode back over the axis and the traces. Now
`height=600`, `margin.b=150`, `y=-0.16`, `yanchor="top"` — anchored to the top
of its own box so it grows *downward* into the reserved margin rather than
upward across the chart when it wraps to multiple rows.

---

## Monitoring an L3.5 tier — worked example

A GPU node serving SGLang with Mooncake as the remote KV store, where the
store runs on a different host:

```bash
# 1. On the GPU node — collector service
amoprof service \
  --collectors gpu,dram,vmstat,network,iostat,cpu \
  --enable-dram --dram-tool intel-pcm \
  --ssd-device /dev/nvme0n1 \
  --metrics-port 9101 --metrics-host 0.0.0.0 \
  --sglang-host 127.0.0.1 --sglang-port 30001 \
  --model-path google/gemma-4-31B-it

# 2. On the L3.5 memory node — device visibility for the store's own SSD
amoprof service \
  --collectors iostat,nvme_driver \
  --ssd-device /dev/nvme0n1 \
  --metrics-port 9101 --metrics-host 0.0.0.0

# 3. Scrape all of them into ONE Prometheus: the GPU node's amoprof and
#    sglang jobs, DCGM, the Mooncake exporter, and the memory node's amoprof.
#    Shared timestamps are what make cross-host correlation valid.

# 4. Analyze
amoprof analyze \
  --prometheus http://prometheus:9090 \
  --start 2h --end now --prom-step 15 \
  --prom-instance ssi-gpubnode03.dsa.gpu:30001 \
  --l35-instance 105.140.238.242:9003 --l35-job mooncake \
  --l35-storage-instance ssi-store01:9101 \
  --model-path google/gemma-4-31B-it \
  --output-dir ./results --combined-report
```

`--start`/`--end` accept naive local times, explicit offsets, `Z`, relative
forms (`2h`), or Unix timestamps. Naive input is interpreted in the local
timezone and converted to UTC; both are echoed in the log.

Expect in the output:

```
L3.5 selector (explicit): {job="mooncake", instance="105.140.238.242:9003"}
L3.5 exporter publishes N metric(s) under that selector
Tier chart data — L2 (DRAM BW): yes | L3 (NVMe): yes
```

### L3.5 bandwidth from the master exporter

The Mooncake master publishes no transfer-engine byte counters, but it does
publish cumulative byte totals that give the same quantities:

| Canonical | Master metric | Meaning |
|---|---|---|
| read bytes | `file_cache_hit_bytes_total` + `mem_cache_hit_bytes_total` | bytes served on a hit, by tier |
| write bytes | `master_value_size_bytes_sum` | cumulative size of values PUT |
| promoted | `master_promotion_completed_bytes_total` | disk to memory |
| occupancy | `segment_allocated_bytes` / `segment_total_capacity_bytes` | |

The two read counters are summed **before** differencing. Differencing each and
adding gives the same number, but a gap in either would silently halve the
result.

These measure **logical** bytes in and out of the store, not wire bytes: RDMA
framing and any replication overhead are excluded, so they read slightly below
what a NIC counter would show.

Note the Mooncake **master** exporter is otherwise a metadata service: it reports
capacity, keys and request rates, never byte throughput. L3.5 bandwidth needs
the store or transfer-engine exporter, or the memory node's own device
metrics via `--l35-storage-instance`.

---

## Polling the inference server

Two knobs, because the two endpoints cost different things:

| Flag | Endpoint | Default |
|---|---|---|
| `--sglang-metrics-interval-s` | `/metrics` | `0` = follow `--interval-s` (1s) |
| `--server-info-interval-s` | `/get_server_info` | 300s |

`--interval-s` governs the host collectors — `/proc/stat`, iostat, DCGM —
where a 1s poll is free. The SGLang endpoints are different: those are requests
against a serving engine, so they get their own controls.

```bash
amoprof service --interval-s 1 \
                --sglang-metrics-interval-s 5 \
                --server-info-interval-s 600
```

Raising `--sglang-metrics-interval-s` coarsens the per-interval rates the
correlation charts are built from — it trades chart resolution for load on the
inference server. `--server-info-interval-s` has no such cost: configuration
changes on restart, so a long interval loses nothing but detection latency.

---

## Concurrency pressure is queueing, not utilisation

The concurrency card charts four signals that actually respond to load:

| Signal | Why |
|---|---|
| `num_queue_reqs` | requests waiting — the direct measure of pressure |
| `queue_time_seconds` | how long they wait, per-interval mean |
| `utilization` | SGLang's own engine utilisation, not DCGM's device-level `gpu_util` |
| `fwd_occupancy` | forward-pass occupancy |

GPU util and HBM used are still plotted, but neither answers the question.
**GPU util saturates before concurrency does** — once the device is busy,
another concurrent request adds waiting rather than utilisation. **HBM is
preallocated** for the KV pool at startup, so it does not move with load at
all; a rising HBM line here would indicate a leak, not concurrency.

Series are coloured individually rather than by layer. Colouring by layer gave
GPU util and HBM used — both `A4_GPU_HBM` — the *identical* colour, so the
legend could not distinguish them.

---

## NaN-safe axes

**NaN is truthy, and every comparison with it is False.** So `x or default`
passes NaN through, and `x <= 0` does not catch it. Both idioms were used as
guards throughout the chart code, and each occurrence produced a silently
broken chart rather than an error — an invisible line that still claimed a
legend entry, an axis labelled `nan`, or a stated `max 0.0`.

Sites found and fixed by the sweep:

| Site | Symptom |
|---|---|
| `sr["ymax"] or 1.0` | every coordinate `nan`; 3 of 6 series invisible |
| axis extrema via `max()` | one leading NaN made the whole axis `nan` |
| legend printing the supplied ceiling | `max 0.0 ms` beside a plotted line |
| circle/tooltip loop over raw bins | `nan` centres and `nan%` tooltips |
| `x.get("cap")` truthiness | NaN ceiling yielded a `nan` percentage |
| legend peak via `max()` | `peak nan ms` beside a correctly plotted line |
| `active_gpu_count <= 0` | a NaN GPU count propagated to every per-GPU figure |

`validate_math.py` group `0c` asserts the renderers survive NaN input, so a
reintroduction fails a test rather than producing a blank chart.

---

## Axis scale

Latency is charted as **two** series groups, not one:

* **Request latency** — TTFT and E2E, in ms per request
* **Per-token latency** — TPOT/ITL, in ms per token

They were one chart spanning ~450x (TPOT ~10ms beside E2E ~4,460ms), which
forced a log axis on all three. They are different quantities that happen to
share a unit name; separated, each sits within its own range and gets a linear
axis automatically.

The `(log)` suffix on axis labels was also hardcoded, so it claimed log even
when the auto-scale chose linear. Removed — the axis label now states the unit
and the scale follows the data.

Absolute-unit tier charts pick their y-axis scale from the data:

| Setting | Behaviour |
|---|---|
| `auto` (default) | log only when the series span more than 50x, linear otherwise |
| `log` | always log |
| `linear` | always linear |

```bash
AMOPROF_AXIS_SCALE=linear amoprof analyze ...
AMOPROF_LOG_AXIS_MIN_RATIO=200 amoprof analyze ...   # raise the threshold
```

A log axis exists to keep HBM (TB/s) legible beside NVMe (GB/s) on one chart.
When every series sits within a factor of ~50 it buys nothing and costs
readability: log spacing visually flattens real variation, so a tier that
doubles looks almost flat. Charts where the tiers happen to be close now get a
linear axis automatically.

```
narrow 2.3x range -> 79  60  40  20  0.00     (linear)
wide 2700x range  -> 6,624  884  118  16  2.1 (log)
```

---

## Top findings must be traceable

Findings quote numbers the reader can locate elsewhere in the report, and name
the statistic they used.

`ttft_ms` comes from the End Report's parsed KPI while the percentile card is
computed independently in the Executive. When they diverged, a finding
announced *"First-token wait is 74.8 seconds"* against a card showing
p50 2.2 s / mean 9.8 s, and nothing on the page explained the gap. A bare
number with no statistic named is how that stayed invisible.

```
First-token wait (End Report KPI) is 74.8 seconds (p50 is 2.2 s, p99 208.5 s)
  — long, but caused by the GPU being busy with the prompt itself ...
```

**The divergence itself is not yet fixed** — the two paths still compute TTFT
independently. Naming the statistic and quoting the distribution makes a
disagreement visible; making them agree, and asserting it in
`validate_math.py` group 0b alongside the DRAM and cache-hit checks, is
outstanding.

---

## p50 means the same thing in every report

TTFT, TPOT and E2E p50 are the **whole-window quantile** — the median request
over the analysed window — in the Executive report, the End report and the
tiles. That matches the formula the tiles display,
`histogram_quantile(0.50, rate(..._bucket))`.

Both reports previously preferred a different quantity: the per-interval p50
series averaged over active intervals. That weights a quiet interval with three
requests the same as a busy one with three hundred, so under a duty cycle it
differs severalfold from the median request. Each report read that series from
a different place, so the same label carried different numbers in the two tabs.

The interval series is still used as a fallback when no whole-window quantile is
available. When that happens the End report records
`per_interval_p50_active_mean_FALLBACK` as the method, so the source of the
number is visible rather than assumed.

Note that the percentile **charts** plot the per-interval series by design —
that is what a time series of p50 is. Their legend peak is the worst interval's
p50, which is a different quantity from the tile and will usually be larger.

---

## Percentile charts read at bucket resolution

TTFT, TPOT, E2E and queue-wait percentiles come from histogram bucket deltas,
so their resolution is the histogram's, not the timer's. Two consequences the
chart now states rather than hides:

**Round values are bucket edges.** When the quantile target coincides with a
bucket's cumulative count, the interpolation returns that bucket's upper
boundary exactly — which is why peaks land on 40,000 or 80,000 ms. The value is
not measured to that precision; the underlying value lies within the preceding
bucket. The subtitle names the boundary and the width of the bucket it belongs
to.

**An unbounded quantile is not plotted.** A quantile sitting in the open-ended
+Inf bucket interpolates to infinity. It is emitted as NaN so the line breaks,
rather than as a number: the reading is unbounded above, not large. Previously
this could reach the chart as inf.

`percentiles_from_bucket_deltas` also returns `_last_finite`, the last finite
boundary, so a caller can tell how far the histogram reaches.

---

## L3.5 store internals — eviction, get outcome, promotion

Three charts in *Compute and capacity utilisation over the run*, all from the
store exporter via `l35_store_capacity.csv`. Every counter below was confirmed
present on the 2026-09 deployment before being wired in.

**Eviction over the run** — `master_evicted_size_bytes` and
`master_evicted_size_bytes_mem`, both as rates. They are plotted as reported
rather than subtracted into a "dropped vs demoted" split, because whether the
`_mem` counter is a subset of the total is not established.

**Get outcome** — `total_get_nums_` and `valid_get_nums_`. The subtitle states
the fraction of gets that found their key. These are the lookup counts; the
names carry a trailing underscore on this build.

**Rendered whenever L3.5 is configured.** The section no longer depends on
the compute or capacity charts being present. When L3.5 is configured but a
chart has no data, a note names which charts are missing and why — the store
file absent (re-run `analyze` with `--l35-instance`), or specific counters
absent or idle. A configured tier never produces silent absence, since that
leaves the reader unable to tell an idle tier from an unmeasured one. When L3.5
is not configured, nothing is rendered and no note appears.

**Promotion pipeline** — window counts for each stage, recorded → admitted →
completed, with every rejection path:

```
rej: freq    master_promotion_rejected_frequency_total
rej: wmark   master_promotion_rejected_watermark_total
rej: cap     master_promotion_rejected_cap_total
rej: admit   master_promotion_candidate_admission_rejected_total
dropped      master_promotion_candidate_dropped_limit_total
expired      master_promotion_expired_total
failed       master_promotion_failed_total
```

The subtitle names the largest loss in full. This answers *why* KV does not
move back up from the file tier, where the completed-bytes counter alone could
only say *that* it does not.

---

## L3.5 read activity — bytes served, not replica lookups

The prefetch correlation card compares prefetch against **L3.5 read
bandwidth**, computed from bytes the store actually served:

```
L3.5 read BW = Δ(mem_cache_hit_bytes_total + file_cache_hit_bytes_total) ÷ Δt
```

It previously compared against "L3.5 get ops/s", fed by
`master_get_replica_list_requests_total`. A replica-list request is a
**metadata lookup** on the master — *where is this key?* — not a data read, and
it can fire without a byte moving. That series was also read from the engine's
timeseries while store metrics are fetched under the store's own selector, so it
was usually empty. The lookup counter now keeps its own name,
`mooncake_replica_lookups_total`, so it is not mistaken for data movement.

## L3 vs L3.5 wording in findings

When the tier is remote, bare prose phrases — `L3 reads`, `L3 tier`,
`L3 traffic`, `L3 backing` — are rewritten to `L3.5`, matching the KPI tiles.
The earlier relabel matched only parenthesised forms such as
`L3 (local storage)`, so Top findings said L3 while the tiles said L3.5 for the
same tier. Local-SSD deployments keep L3.

---

## KV movement counters — prefetch, backup, load-back, evict

All four go through one reader, `_kv_token_delta`, and report **tokens**.

**Summed across ranks.** SGLang publishes each counter once per tp_rank. The
previous reader took the first matching column and under-reported by the
parallelism factor — 1,000 against a true 8,000 at TP=8. It now sums every
matching column per row before differencing. Histogram `_bucket`, `_sum` and
`_count` side-series are excluded.

**Across ranks, never across aliases.** A run directory can carry the same
quantity under two names — `sglang_prefetched_tokens_total` and
`hicache_prefetched_tokens_total`. Matching columns are grouped by metric name
(the part before any `[label=...]` suffix) and only one group is summed,
preferring the canonical `sglang_` name. Summing every substring match, as
v1.39.0 briefly did, reported 2,000 tokens for 1,000.

**Absent vs idle.** A counter with no matching column returns `None` and prints
`absent`; one that exists and never moved returns `0.0`. The old reader
returned `0.0` for both, so a missing counter looked like an idle one.

**Tokens, not bytes.** Narrative text no longer converts these to GB. The
conversion `tokens × KV_bytes_per_token` was never validated against measured
storage bytes, and on real runs prefetch came out 30× above what the store
actually served — 55 TB against 1.7 TB — because `prefetched_tokens_total`
counts transfers into L2 rather than bytes read from the backing tier. Measured
bytes come from the store's own counters and from block telemetry.

**Run directories analysed before v1.36.0** carry per-rank columns rather than a
summed one. The new reader sums them correctly, so re-rendering an old run
directory with this version corrects the figures without re-running analyze.

---

## Capacity, split by tier

The capacity chart plots the store's memory and file tiers separately rather
than as one "remote store" line, because a single series conflates a DRAM tier
that is full with a file tier that is empty — opposite conditions with opposite
remedies.

```
L3.5 memory capacity     peak 1,500.00 GB
L3.5 storage capacity    peak   950.00 GB
```

The storage line appears only when a file tier is configured. A DRAM-only
deployment shows one line, not an empty second one implying a tier that does
not exist.

Both come from `l35_store_capacity.csv`, which is fetched under the store's own
selector. Older run directories fall back to the combined single-series source
and are labelled as combined so the difference is visible.

---

## Cross-checking against node_exporter

`amoprof/crosscheck.py` pairs AMOprof's own measurements against node_exporter's
for quantities both instruments observe by different routes — iostat parses a
text stream, node_exporter reads /sys and /proc directly.

```
disk bytes written    amoprof 1,833.00  node 1,840.00 GB   1.00x  agree
disk bytes read       amoprof     0.00  node     0.20 GB      —   DISAGREE
host DRAM used        amoprof   466.00  node   468.00 GB   1.00x  agree
network rx            amoprof   120.00  node    11.00 GB   0.09x  expected-gap
```

This answers *are the numbers right*, not *which layer is the bottleneck*. A
disagreement means one instrument is wrong, and a silent measurement error
propagates into every chart downstream — which is the failure this guards
against.

**Expected gaps are not faults.** AMOprof reads NIC PHY counters while
node_exporter reads `/proc/net/dev`, and RDMA traffic bypasses the kernel stack
entirely. Flagging that as an error would train the reader to ignore the check,
so those pairs report `expected-gap` with the reason. Agreement tolerance is
10%, since two instruments sampling the same counter at different phases will
not match exactly.

---

## KV movement metrics — the chain inputs

`analyze` now fetches the counters the tiering chain is built from. Store-side,
under the memory-node exporter's selector:

```
l35_evicted_b    <- mooncake_evicted_bytes | master_evicted_size_bytes
l35_promoted_b   <- mooncake_promoted_bytes | master_promotion_completed_bytes_total
l35_mem_hit_b    <- mooncake_read_bytes_mem | mem_cache_hit_bytes_total
l35_file_hit_b   <- mooncake_read_bytes_file | file_cache_hit_bytes_total
```

Engine-side, `sglang_{evicted,backuped,load_back,prefetched,cached}_tokens_total`
were already fetched but **unaggregated**. These carry one series per tp_rank,
so taking a single series under-reports by the parallelism factor — a prefetch
total read 8x low on a TP=8 deployment. They are now summed across ranks.
Gauges are deliberately left unaggregated, since summing an occupancy gauge
across ranks is meaningless.

Counter names differ by store build, so each entry has a fallback list rather
than one hardcoded name.

---

## compare: the tiering chain

`amoprof compare` now emits a causal chain before its delta tables, because a
tier-sizing change propagates through the store and the engine before it
reaches latency, and only the ordered view makes that visible.

```
Link           Measurement          A       B        Ratio        Measured by
Tier capacity  L3.5 DRAM (GB)   1,557     483    3.22x lower      configuration
Fit            evict : read       0.19    5.07       26.6x        memory node
Eviction       evicted (GB)      320.6  5,651.3      17.6x        memory node
Promotion      promoted (GB)       0.0      0.0        —          memory node
Prefetch       tokens prefetch  56.4M     5.1M   11.1x lower      inference engine
Recompute      tokens recomp    12.1M    17.3M       1.43x        inference engine
Latency        TPOT (ms)         373.5    602.1       1.61x       inference engine
```

Rows follow the stack rather than the size of the change, and each names the
layer that measured it. Links within 15% are omitted so only what moved
appears.

**`evict : read` is the headline.** Below 1.0 the tier is caching; above it,
thrashing. A promotion row of 0 to 0 is kept even though its ratio is
undefined — a tier that never promotes is the finding, not a missing value.

### Absent vs measured-zero

A counter that does not exist yields `None` and prints `absent`; one that
exists and never moved yields `0.0`. These are different findings and the
report must not conflate them.

### Variance guard

With fewer than three runs per label the report carries a banner stating that
differences are indicative and not attributable. This is not optional: on the
reference data, two identically configured runs differed by 38.5 pp on cache
hit and 48% on TPOT, and a two-run comparison produced a confident conclusion
that a third run reversed.

---

## setup_details.json — recipes

`--setup-details` declares what the run actually used. Keys are matched
**exactly**, including case, so a near-miss is silently ignored rather than
reported. `L3 Storage type` (capital S) does **not** match `L3 storage type`.

Always pass `--setup-details-override` — see the section below.

### Accepted keys

| Purpose | Accepted spellings (any one) |
|---|---|
| Tier | `KV cache tier`, `kv_cache_tier`, `KV backing tier`, `kv_backing_tier`, `L3 cache tier`, `l3_cache_tier`, `L3/L3.5 tier`, `l3_l35_tier`, `AMOprof cache tier`, `amoprof_cache_tier`, `Memory tier`, `memory_tier` |
| Storage type | `L3 storage type`, `l3_storage_type`, `L3 type`, `l3_type` |
| Backend | `Cache L3 (local storage) backend`, `cache_l3_backend`, `HiCache storage backend`, `hicache_storage_backend`, `L3 backend`, `l3_backend`, `storage_backend`, `hicache_backend` |
| Device | `L3 Device`, `L3 device`, `L3 block device`, `l3_device`, `NVMe device`, `ssd_device` |
| Mount path | `L3 Mount Path`, `L3 mount path`, `L3 mount`, `l3_mount_path`, `HiCache storage path`, `hicache_storage_path` |
| Benchmark | `Application / Benchmark`, `application_benchmark`, `Benchmark`, `Workload`, `Test` |

`L3 Tier` and `L3 storage backend` are **not** in these lists. They are not
entirely ignored — a later fallback scans the whole setup blob for `mooncake`
and similar, so a value can still land by accident — but they do not
participate in the explicit tier/type/backend resolution, and relying on the
fallback is fragile. Use the spellings above.

### Which class is resolved

The tier, storage-type and backend values are lowercased and joined, then
matched against these substrings:

* **remote (L3.5)** — `l3.5`, `l35`, `l3_5`, `l3-5`, `ai memory`, `ai-memory`,
  `aimemory`, `remote`, `shared`, `disaggregated`, `mooncake`, `moon cake`
* **local (L3)** — `local ssd`, `local_ssd`, `nvme`, `ssd`, `local storage`,
  `local-storage`

Remote is tested first, so a value containing both resolves to L3.5.

### Recipe: Mooncake / AI Memory Node (L3.5)

```json
{
  "KV cache tier": "L3.5",
  "L3 storage type": "remote",
  "hicache_storage_backend": "mooncake",
  "Application / Benchmark": "AgentBench"
}
```

Gives `remote_mooncake`, the `L3.5 (AI Memory Node / remote storage)` label,
and the L3.5 tiles. (`remote_storage` is the equivalent class for a
non-Mooncake remote store.)

### Recipe: local NVMe (L3)

```json
{
  "KV cache tier": "L3",
  "L3 storage type": "local ssd",
  "hicache_storage_backend": "file",
  "L3 device": "/dev/nvme0n1",
  "L3 mount path": "/mnt/kvcache",
  "Application / Benchmark": "AgentBench"
}
```

Gives `local_ssd` plus block-device mapping, so physical read/write totals are
attributed to the tier.

### Recipe: both tiers

A local SSD cache in front of a remote store resolves to **L3.5** — remote is
tested first. The local device metrics are still collected and charted; only
the tier label follows the remote declaration. Use `--l35-storage-instance` to
measure the memory node's own devices separately.

### Verify what landed

```bash
python3 -c "import json,glob;p=sorted(glob.glob('results/prom_run_*/raw/setup_details.json'))[-1];d=json.load(open(p));print({k:v for k,v in d.items() if 'L3' in k or 'tier' in k.lower() or 'ackend' in k or 'Bench' in k})"
```

If your values are absent, either the key spelling missed or
`--setup-details-override` was not passed.

---

## --setup-details is overridden by default

`--setup-details` is **replaced** by server_info-derived values unless
`--setup-details-override` is passed. That default is backwards — a flag you
supplied should outrank something discovered at runtime — and it silently
discarded the model name, the benchmark name, and the L3 tier declaration on
real runs.

Until the default is inverted, pass it on every invocation that supplies a
setup file:

```bash
amoprof analyze ... --setup-details my_setup.json --setup-details-override
```

Symptoms of forgetting it: the report shows the **currently running** model
rather than the one in the analysed window, `Application / Benchmark` falls
back to the instance name, and a Mooncake deployment is classified
`local_ssd` so no L3.5 tiles appear.

---

## Skipping the local SGLang scrape

When Prometheus already scrapes the inference server directly, amoprof's own
`/metrics` scrape is a second request for the same data. Exclude it by naming
`--collectors` without `sglang`:

```bash
amoprof service --collectors gpu,dram,vmstat,network,iostat,cpu \
                --sglang-port 30001
```

```
[info] service: sglang collector not in --collectors; skipping the local
       /metrics scrape (Prometheus may already be scraping it)
```

Only an **explicit** `--collectors` list excludes it. `enabled` falls back to
`DEFAULT_COLLECTORS`, which does not contain `sglang`, so keying off that set
alone would have disabled the collector for everyone who never named it — a
silent regression rather than the opt-out intended.

| Invocation | sglang collector |
|---|---|
| no `--collectors` | on |
| `--collectors all` | on |
| `--collectors gpu,dram,sglang` | on |
| `--collectors gpu,dram,iostat` | **off** |

`--sglang-port` is still needed for the configuration capture, which reads
`/get_server_info` regardless — that is a different endpoint on a different
schedule and is not affected by this.

---

## The collector does not call /get_server_info

SGLang exports both gauges we wanted from it — `sglang:cache_hit_rate` and
`sglang:token_usage` — on `/metrics`, which the collector already scrapes and
parses generically. Calling a heavy JSON endpoint that serialises the whole
server configuration, to extract two floats already present in a response we
were fetching anyway, was pure overhead.

The collector now polls `/metrics` only. `/get_server_info` is called solely by
the configuration capture, on `--server-info-interval-s` (default 300s).

```
over 1.6s @0.2s metrics poll: 9 /metrics, 0 /get_server_info
  cache_hit_rate from /metrics: 0.372
  token_usage    from /metrics: 0.41
```

This supersedes the throttle and the separate poll thread: neither is needed
once the request itself is unnecessary. Worth remembering as a general check —
before optimising the frequency of a call, confirm the call is needed at all.

---


## --model-path is authoritative

**It overrides the model fields in `setup_details.json`.** Those are normally
derived from a live `/get_server_info`, which describes the **running** server
— a different deployment entirely when the analysed window predates a restart.
A gemma window was reported as `Qwen/Qwen3.8-27B` for exactly that reason, and
`--setup-details-override` was required to get the reverse, which is backwards:
a flag you passed should outrank something discovered implicitly.

Only `Model` and `Model path` are replaced. TP size, page size and cache
settings are left as discovered, because `--model-path` says nothing about
them. A disagreement warns rather than resolving silently.

**It constrains the Prometheus fetch, not just the labelling.** A host that has
served several models keeps every model's series under the same
`{job,instance}`, so a selector without `model_name` pulls them all and
averages two deployments into one report. When `--model-path` is given, the
selector gains `model_name="..."`:

```
[warn] 2 models present under this selector in the window
       (google/gemma-4-31B-it, qwen3-8-27b). Constraining to
       model_name="google/gemma-4-31B-it" so the report describes one
       deployment.
Inference selector: {job="sglang", instance="...", model_name="google/gemma-4-31B-it"}
```

Which models are present is resolved with `/api/v1/series` **bounded to the
window**, so the answer reflects what was running then rather than now.
Matching is loose enough to survive case differences between the Prometheus
label (`gemma-4-31B-it`) and the path-derived name (`gemma-4-31b-it`).

If the requested model has no series in the window, that is reported and the
fetch proceeds unconstrained rather than returning nothing.

When `--model-path` is given, the model it names wins over anything discovered
at runtime. A live `/get_server_info` describes the server **as it is now**,
which is the wrong answer for a historical window if the model has changed
since — analysing a gemma window against a host now serving qwen reported
qwen throughout.

The name is taken from `_name_or_path` in the config, or derived from a
HuggingFace cache path (`models--google--gemma-4-31b-it` to
`google/gemma-4-31b-it`).

A disagreement is reported rather than silently resolved:

```
[warn] runtime reports model=qwen3-8-27b, but --model-path specifies
       google/gemma-4-31b-it. Using google/gemma-4-31b-it. If this window
       predates a server restart, the runtime value describes a different
       deployment.
```

The report **filename** honours it too. That path reads `setup_details.json`
and `server_info.json` and never consulted `model_config.json`, so the file was
named for the runtime model even when the report body was corrected.

Note this fixes the model **identity** only. TP size, page size and cache
configuration still come from runtime discovery, so for a historical window
those may describe the current deployment rather than the one that produced
the data. `--setup-details` pins them explicitly.

---

## Server configuration is captured per cycle

| Mode | Flag | Fetches |
|---|---|---|
| Production default | `--server-info-once` | once at service start |
| Periodic (default) | `--server-info-interval-s 300` | every 5 min |
| Every cycle | `--server-info-interval-s 0` | every collection cycle |

The two flags are **mutually exclusive** — `--server-info-once` is an interval
of infinity, so accepting both and silently letting one win would leave the
operator with no signal that their explicit interval was ignored. argparse
rejects the combination. The env-var form can still collide with an explicit
interval, and the service logs which one is in effect when it does.

`--server-info-once` (env `AMOPROF_SERVER_INFO_ONCE`) suits deployments where
amoprof is restarted alongside the inference server, so its configuration
cannot change while the service runs.

**It disables mid-window reconfiguration detection.** If the inference server
restarts with a different model or TP size while amoprof keeps running, the
reported setup will be stale and no warning is raised — the very case the
per-cycle capture exists to catch. Use it when the restart coupling is
guaranteed by your deployment, not merely expected.

Polling frequency is otherwise controlled by `--server-info-interval-s` (default **300**,
env `AMOPROF_SERVER_INFO_INTERVAL_S`; `0` re-fetches every collection cycle):

```bash
amoprof service --sglang-port 30001 --server-info-interval-s 60
```

Configuration changes on restart, not continuously, so polling
`/get_server_info` every cycle adds request load to the inference server for
no new information. Between polls the last good fetch is **reused rather than
skipped**, so the published metric stays continuous — a gap in it means the
server was unreachable, not that amoprof chose not to look.

The trade-off is detection latency: a longer interval means a mid-window
restart is noticed later. 300s is a reasonable default for a 12-hour window;
drop it if you are chasing a specific restart.

The service records inference-server configuration on **every collection
cycle**, not once at analyze time, and publishes a stable `config_hash`
alongside the numeric fields.

This matters when a server is restarted mid-window with a different model, TP
size, or cache setup. Previously the whole window was attributed to whichever
configuration happened to be live when the report ran — silently mixing two
different systems into one set of numbers. `analyze` now watches that single
series and warns:

```
[warn] inference-server configuration CHANGED during this window (2 distinct
       configs seen). Metrics before and after the change describe different
       systems; the setup shown in this report is only one of them. Narrow
       --start/--end to a single configuration before drawing conclusions.
       change at t=18450s into the window
```

No amount of careful arithmetic downstream can undo an average taken across
two different systems, so the honest response is to say so and let you
re-scope the window.

---

## Network on the tier bandwidth chart

The GPU-node ↔ L3.5-node link carries every KV transfer on a disaggregated
setup, so it is a tier boundary like any other and can be the binding
constraint. It is charted in **GB/s beside the cache tiers**:

```
L1 HBM bandwidth                       peak 5,760.00 GB/s
L3-local storage BW                    peak     2.13 GB/s
L3.5 node storage BW                       peak     0.59 GB/s
L3.5 remote store BW                   peak     0.30 GB/s
Network rx (L3.5 → GPU node)           peak     1.66 GB/s
Network tx (GPU node → L3.5)           peak     3.22 GB/s
```

### PHY counters, not the kernel's view

Byte counters come from `ethtool -S` (`rx_bytes_phy` / `tx_bytes_phy`) when the
NIC exposes them, falling back to `/proc/net/dev` otherwise.

`/proc/net/dev` reports what the **kernel** saw. On a Mellanox NIC carrying
RoCE/RDMA — which is how KV blocks reach a remote memory node — those transfers
bypass the kernel network stack entirely, so `/proc/net/dev` shows almost
nothing while the link is saturated. It also excludes Ethernet framing,
preamble and CRC, so even plain TCP is under-reported by a few percent.

The PHY counters are the NIC's own hardware registers: the same source
`mlnx_perf -i <if>` and `ethtool -S <if>` read, so amoprof's figures now match
what an operator sees from those tools.

The summary records which layer was used — `net_counter_source` is
`phy_ethtool` or `kernel_proc_net_dev`, with `net_phy_interfaces` listing the
interfaces read at PHY level — so a discrepancy against external tooling is
explainable rather than mysterious.

### Naming the interface

Available on **`collect`, `service` and `analyze`** (env `AMOPROF_NET_IFACE`).

For a systemd deployment, set it in `/etc/amoprof/amoprof.env` — the unit's
`EnvironmentFile` — rather than in `AMOPROF_EXTRA_ARGS`:

```
AMOPROF_NET_IFACE=enp97s0f1np1
```

An explicit `--net-iface` on the command line overrides the env var. Verify
the name with `ip -br link` first: matching is exact, so a typo yields zeros
rather than falling back to every interface.


```bash
# at collection time — only these interfaces are sampled
amoprof service --collectors ...,network --net-iface ib0,ib1

# at analysis time — narrow an already-collected run, no re-collection needed
amoprof analyze ... --net-iface ib0
```

`network_timeseries.csv` keeps one row per interface plus an `_total`
aggregate, so `analyze` can select interfaces after the fact. Named
interfaces are summed; without the flag the pre-aggregated `_total` row is
used, which sums every NIC on the box.

```
default (_total)     rx 1.67 GB/s   tx 3.23 GB/s
--net-iface ib0      rx 1.66 GB/s   tx 3.22 GB/s
--net-iface eno1     rx 0.01 GB/s   tx 0.01 GB/s
```

The run log states the restriction:
`Network: restricted to ib0 (200 interval(s))`

**Link utilisation (%) is not reported.** It divided rx+tx by a link speed
read from `/sys/class/net/<if>/speed`, which is unreliable on bonded
interfaces, absent on many IB devices, and wrong whenever it is stale. rx and
tx in absolute GB/s answer the same question without depending on a ceiling
that may not exist. The saturation signal is rx or tx flattening while token
activity keeps rising.

**rx and tx are charted separately.** KV traffic is strongly directional —
offload to the store is tx, restore is rx — so a combined line hides which
direction saturates the link. A run that is 90% tx is doing far more writing
than reading, the same asymmetry the write-only L3 finding surfaces.

A link peak below the L3.5 store's own read bandwidth means the fabric, not
the store, is the limit. It was previously excluded because the series carried
was a link *percentage*; the `total_mbs` series converts cleanly to GB/s. The
percentage stays on the correlation cards, where a ratio is the right unit.

Requires the `network` collector on the GPU node (in `DEFAULT_COLLECTORS`).

---

## L3.5 memory vs storage

Mooncake accounts the two tiers separately — `mem_cache_hit_bytes_total`
beside `file_cache_hit_bytes_total` shows the store knows which tier served
each hit — so one conflated "L3.5 used" figure is a percentage of the wrong
total.

```
L3.5 memory (raw)        470.0 / 512 GB      master_allocated_bytes / total
L3.5 storage (raw)     3,500.0 / 4,000 GB    master_allocated_file_size_bytes / total
L3.5 memory (tokens)   1,403,620 / 1,529,052 tok
L3.5 storage (tokens) 10,452,488 / 11,945,719 tok
```

**Raw first, tokens second.** Raw bytes are what the store reports and need no
model assumption; token figures divide by KV bytes/token and inherit that
derivation's error, so they are marked DERIVED with the sliding-window caveat.

When the store reports only a combined total, the token tile collapses to a
single **L3.5 used (tokens)** and says so. An aggregate is honest; a split that
cannot be substantiated is not.

If the memory tier further separates DRAM from CXL, that split is not in the
store's metrics — CXL appears only as AMDuProfPcm *bandwidth* on the node, not
as capacity, so a DRAM/CXL capacity split would need the memory node to report
it.

---

## Write amplification and endurance

**True WAF needs the OCP log.** Standard SMART has no NAND-writes field, so
`nvme smart-log` alone cannot give write amplification — the collector used to
fall back to the host figure, producing exactly 1.0, which reads as "no
amplification" when it means "not known".

`nvme ocp smart-add-log` exposes the real counters, and the collector now reads
them:

```
Physical media units written  ->  nand_bytes_written
Physical media units read     ->  nand_bytes_read
Percent free blocks           ->  pct_free_blocks
Max/Min user data erase counts->  max_erase_count / min_erase_count
Endurance estimate            ->  endurance_estimate
Bad user nand blocks          ->  bad_user_nand_blocks
Soft ecc error count          ->  soft_ecc_errors
```

The 128-bit counters print as two words (high low); the low word is taken.

When the drive does not support the OCP log, `nand_written_gb` and `waf` are
**omitted** rather than fabricated, and `nand_reported_by_drive 0` says so.



Two amplification ratios, because they answer different questions:

```
L3.5 storage host writes        476.8 GB    SMART host_written delta
L3.5 storage WAF (host→NAND)      2.31x     the drive's own amplification
L3.5 KV→host amplification        0.96x     host bytes ÷ logical KV bytes
L3.5 KV→NAND total                2.21x     both stages combined
L3.5 storage DWPD (extrapolated)  4.61      scaled to 24h, upper bound
```

**KV→host moves with your choices** — page size, eviction policy, memory
composition. If the store writes 4 KB blocks for 960 KB of KV, or rewrites
metadata per operation, it shows here.

**host→NAND is the drive's garbage collection**, driven by write size and LBA
concentration — so read it beside the LBA decile chart. Concentrated small
writes to a narrow span force more GC.

Their product is what actually burns endurance, which is why **KV→NAND total**
is shown rather than one conflated "WAF".

DWPD is extrapolated from the window to 24h and marked as such: a bursty
workload will not sustain the rate, so it is an upper bound.

SMART counters are since drive life, so every figure is the delta across the
analysed window.

---

## LBA distribution

A bar per GB band across the device:

```
share of write bytes per GB band across the 2,000 GB span
3 of 10 bands active · busiest 1,200-1,400G carries 63% · 1,400 GB never written

0-200G  200-400G  400-600G ... 1,800-2,000G
```

Red above 30%, amber above 10%, dark slate for untouched bands, so the cold
regions stay visible — a drive with 70% never written wears nothing like its
rated DWPD. The subtitle names the busiest band in GB and the untouched total,
which is the sentence that goes on a slide.

Earlier versions also tried a cumulative concentration curve and a heat strip.
The curve needed three inferential steps to read; the strip carried the same
ten deciles as the bars. One chart, with the conclusion stated in the
subtitle, does the job.

## Superseded: LBA heat strip

One chart: ten cells across the device, shaded by share of bytes.

```
Where writes land on the L3.5 storage device
3 of 10 regions take the writes · 1,400 GB of 2,000 GB never written

[  ][17%][  ][  ][  ][19%][63%][  ][  ][  ]
 0G  200  400  600  800  1000 1200 1400 1600 1800
```

Red is the dominant band, amber secondary, grey untouched. The share is
printed in each active cell and the GB offset underneath, so the finding reads
without interpreting an axis — and the grey cells carry half the endurance
story, since a drive with 70% never written wears very differently from its
rated DWPD.

Earlier versions also showed a cumulative "hottest N% of the span carries X%"
curve and a by-offset bar chart. Both plotted the same ten deciles: the curve
needed three inferential steps to read (sort, accumulate, compare to an even
split), and the bars were the strip with a y-axis. Two views of identical data
make the reader hunt for a difference that is not there.

## LBA distribution chart

**The analyzer has two summary dicts.** The in-memory path and the streaming
path each build their own, and the deployed service uses the streaming one.
A decile export added only to the in-memory dict therefore published nothing
on a real node while testing clean in isolation — the metric was simply never
computed on the path that runs.

Both now export `lba_{read,write}_decile{0..9}_pct`, `_deciles_touched`,
`_span_gb` and `_start_gb`.

If these are ABSENT in Prometheus, check `streaming_analyzer` in the same
summary: it tells you which path produced the data.



`_amoprof_exec_svg_percentile_bars` hardcoded its label order to
`("p50", "p90", "p99")` and returned `""` for any other key set — so the
ten-decile LBA chart silently produced nothing, with no error logged anywhere.
It now keeps the canonical ordering when those keys are present and accepts any
label set otherwise.

```
L3.5 storage write I/O across LBA space
  0-10%  10-20%  20-30% ... 90-100%   ·  N/10 deciles touched
```

One tall bar means access is concentrated in a tenth of the device span; ten
even bars means it is spread. Fed by the decile gauges the analyzer publishes,
so it works for a remote node over Prometheus — unlike the CSV-backed versions
in the Interactive and End reports.

---

## L3.5 node storage

Tiles, each naming the node:

```
L3.5 node DRAM used     peak GB, from the memory node's /proc/meminfo
L3.5 node storage BW        rd / wr MB/s peak, with the write:read ratio
L3.5 node storage queue     peak avgqu-sz, plus %util with its caveat
L3.5 used (physical)    segment_allocated / segment_total from the store
L3.5 used (KV tokens)   the same bytes ÷ KV bytes/token (DERIVED)
```

Charts over the run: **reads vs writes**, **IOPS**, and **queue depth with
%util**. Read and write are always plotted separately — a large write:read
ratio means the tier is absorbing cost without delivering read benefit, which
is invisible in a combined line.

`%util` is shown beside queue depth rather than alone: on NVMe it measures
time-with-a-request-outstanding and saturates near 100% long before the device
does, so queue depth is the real pressure signal.

**Two views are not yet possible:**

* **Storage capacity used over time** — iostat reports rate, not residency. Needs a
  filesystem sampler (`df` on the store's mount) in the `dram` or a new
  collector.
* **LBA distribution is now exported.** The full hot-region table goes to
`hot_regions_overall.csv`, which a Prometheus-fetched run never sees — so a
remote node had locality scalars and no distribution. The analyzer now also
publishes bounded gauges:

```
amoprof_blktrace_analysis_lba_write_decile0_pct .. decile9_pct
amoprof_blktrace_analysis_lba_write_deciles_touched
amoprof_blktrace_analysis_lba_write_span_gb / _start_gb
  (and the read_ equivalents)
```

Ten deciles across the observed LBA span, so cardinality is fixed. Concentrated
access shows as one decile near 100% with `deciles_touched` = 1; spread access
shows ~10% each with `deciles_touched` = 10.

Still to do: synthesise these into the analysis CSV on the Prometheus path,
and render the Executive chart from them.

~~**Storage I/O distribution across LBA space**~~ — needs `blktrace` running on the L3.5
  node and its request-level path wired through `--l35-storage-instance`, which
  currently assumes a single host.

---

## CXL memory on the L3.5 node

AMDuProfPcm reports CXL-attached memory bandwidth separately from DRAM.
Those counters are now parsed (`cxl_read_gb_s`, `cxl_write_gb_s`,
`cxl_total_gb_s`, `cxl_available`) and **never folded into the DRAM totals** —
they are different memory with different latency, and summing them produces a
"DRAM bandwidth" figure that no longer describes DRAM.

A dedicated chart splits the memory node's traffic four ways:

```
L3.5 DRAM read   peak 60.00 GB/s      L3.5 CXL read   peak 18.00 GB/s
L3.5 DRAM write  peak 29.00 GB/s      L3.5 CXL write  peak  8.00 GB/s
```

CXL sits between local DRAM and NVMe in both latency and bandwidth, so how the
store splits traffic across the two is a placement question the aggregate
cannot answer: a store serving mostly from CXL behaves very differently from
one serving mostly from DRAM at identical total bandwidth.

Both are also correlation targets (`L3.5 node · CXL read BW`, `... CXL write
BW`), so token activity can be plotted against CXL traffic directly.

Requires `--enable-dram --dram-tool amduprof` on the memory node, with
`--l35-storage-instance` pointing at it.

---

## Correlating token activity against the L3.5 node

Run the full collector set on the memory node, not just storage:

```bash
# on the L3.5 memory node
amoprof service --collectors iostat,nvme_driver,dram,cpu \
  --enable-dram --dram-tool intel-pcm --ssd-device /dev/nvme0n1 \
  --metrics-port 9101 --metrics-host 0.0.0.0

# analyze
amoprof analyze ... --l35-storage-instance ssi-store01:9101
```

Its SSD, DRAM and CPU then appear as correlation targets beside the GPU
node's, so token activity can be plotted against all of them on one card:

```
L3.5 node · SSD read BW (MB/s)    L3.5 node · DRAM BW (GB/s)
L3.5 node · SSD write BW (MB/s)   L3.5 node · DRAM used (GB)
L3.5 node · SSD util (%)          L3.5 node · CPU util (%)
L3.5 node · SSD queue depth       L3.5 node · CPU iowait (%)
```

A remote tier can be slow because its disks are busy, its DRAM cache is
thrashing, or its CPU is saturated. Only the first was measurable before.

Every label names the **node**, and the CSV columns are `l35_`-prefixed, so
neither a reader nor the code can confuse them with the GPU host's
identically-named metrics. Unprefixed columns from older run directories are
still read.

Both hosts must scrape into the same Prometheus — series are aligned by
timestamp, so a shared clock is what makes the correlation valid.

---

## Tracing the SSD inside an L3.5 memory node

The L3.5 store exporter is a **metadata service**: capacity, key counts,
request rates. It publishes no device I/O, so it cannot tell you whether the
disk behind it kept up. That requires a collector running **on the memory
node**, and an explicit selector — the GPU-node `--prom-instance` filter would
otherwise exclude it, exactly as it excluded the store metrics before
`--l35-instance` existed.

On the memory node, either:

```bash
amoprof service --collectors iostat,nvme_driver --ssd-device /dev/nvme0n1 \
                --metrics-port 9101 --metrics-host 0.0.0.0
# or, lighter:
node_exporter --collector.diskstats
```

Scrape it into the **same Prometheus** as the GPU node — two hosts mean two
clocks, and shared Prometheus timestamps are what make the correlation valid.

Then:

```
--l35-storage-instance ssi-store01:9101 [--l35-storage-job amoprof]
```

Both exporter shapes are handled: `amoprof_iostat_*` per-device aggregates
directly, or raw `node_disk_*_total` counters wrapped in `rate()`. The result
lands in `l35_storage_timeseries.csv` and charts as **L3.5 node storage BW**
beside the local tiers.

This is what lets you ask the question the store exporter cannot answer:
Mooncake accepted 500 puts/s — was the SSD underneath saturated, or were
those puts absorbed by page cache?

---

## Compute and capacity over time

Two time-series charts on the shared windowed timeline:

* **Compute utilisation** — GPU SM, HBM bandwidth, and CPU as % of their own
  ceiling. Answers *what was busy and when*; the correlation cards answer
  *what moves with what*, which a scatter cannot show over time.
* **Memory hierarchy capacity utilisation** — bytes resident / tier capacity
  for L1 HBM, L2 host DRAM, L3 filesystem. Distinct from the KV-tier-fill
  chart: this counts **everything** in a tier (weights, activations, page
  cache), so a tier can read nearly full here while its KV share is small.
  That difference is the point — it separates KV pressure from everything else.

CPU comes from the **`cpu` collector** (`collectors/cpu.py`), enabled by
default, reading `/proc/stat`. Three series are charted:

| Series | Why |
|---|---|
| CPU utilisation (all cores) | aggregate busy time, excluding idle and iowait |
| CPU busiest core | a single-threaded bottleneck pins one core while the aggregate reads comfortable |
| CPU iowait | shown only when non-trivial — the signal that storage, not compute, is the constraint |

`cpu_steal_pct` is also collected: non-zero means the host is oversubscribed
and the measurement is not yours alone. Percentages come from **jiffy deltas
between snapshots**, never from a raw counter read — an absolute counter says
nothing about the window. Guest time is excluded from the denominator because
Linux already counts it inside user/nice; including it pushes totals past
100%.

---

## Mean alongside p50

Latency rows report **mean beside p50 with the ratio between them**, because
the two answer different questions and neither alone describes the tail:

| mean / p50 | Reading |
|---|---|
| < 1.3x | tight — mean tracks the median |
| 1.3-3x | right-skewed — normal for latency |
| 3-10x | heavy tail — outliers well beyond p50 |
| > 10x | extreme — check for stalls or a metrics artefact |

p99 says where the boundary sits; only the mean is sensitive to how far beyond
it the worst cases run. The mean is also what Little's Law needs (`L = lambda*W`) —
a median substituted there gives the wrong queue depth.

`metric_kernels.tail_ratio()` is the single implementation.

### Single-sample counters

`_delta_sum_metric` previously fell back to the **raw value** when a window
held only one sample of a monotonic counter. That value is the server's
lifetime total, so the resulting "window mean" was a since-boot average — an
E2E mean of 108 s against a p50 of 1.5 s, reading as a catastrophic tail
rather than the artefact it was. A window with fewer than two samples has no
measurable delta and now returns 0.

---

## Executive card order

Cards are presented in the order an operator reads them, not the order the
code computes them:

1. **Latency distributions** — TTFT, TPOT, ITL, E2E (rendered above the
   Bottleneck Analysis section)
2. **Throughput & cache** — input/output tokens per second percentiles, KV
   cache hit ratio by definition
3. **Compute and capacity over time** — GPU/CPU utilisation, memory hierarchy
   capacity. Placed before the per-tier correlation scatters: "what was busy
   and when" frames the run, and the scatters ("what moves with what") are
   read against that frame rather than the other way round
4. **Compute correlations** — concurrency vs latency, HBM composition
5. **Memory hierarchy** — KV tokens per tier, tier fill %, bandwidth
   utilisation
6. **Token activity → effect across layers** — input, output, evict,
   load-back, prefetch, backup. Placed directly after the tier charts: those
   show what each tier was doing, these show what token activity did *to* each
   tier, so the two are read together rather than separated by every scatter
7. **Queue depth across layers**
8. Everything else keeps its relative position after the ranked set

Ranking matches the card **title** only. Scanning the whole card body ranked
correlation cards as "throughput" because their axis labels mention it. Adding
a new card never requires touching the list — unranked cards simply follow.

---

## Collapsible formulas

Every tile note and chart axis caption renders as a collapsed disclosure
(`<details class="fx">`) labelled **formula** or **axis formulas**. One click
expands it; the text stays in the DOM either way, so Ctrl-F and the report
validators still find it.

Formulas are what make a number auditable, but printed in full under every
tile and chart they crowd out the value itself. `metric_formulas.py` exposes
`formula_details()` plus `FORMULA_CSS` / `FORMULA_CSS_LIGHT` — the dark theme
for Executive and Interactive, the light variant for the End Report — so all
three surfaces share one implementation and one appearance.

---

## Shared metric computation

`report/metric_formulas.py` owns each metric's **documentation**;
`report/metric_kernels.py` owns its **arithmetic**. Both live in the shared
layer so a formula string and the code evaluating it cannot disagree.

| Kernel | Meaning |
|---|---|
| `counter_delta(values)` | `last - first`, clamped at 0 for counter resets — the window's work |
| `window_seconds(times)` | `last - first` of a timestamp column |
| `window_rate(values, times)` | Δcounter ÷ Δtime — **run average, includes idle time** |
| `rate_series_with_time(values, times)` | Per-interval **instantaneous** rate, with timestamps |
| `aligned_rate_series(values, times, clamp_negative)` | Per-interval rate that stays index-aligned with `times` (prepends 0.0, emits 0.0 for Δt ≤ 0) — for charts plotted against the original time axis |
| `ratio_delta(sum, count, scale)` | Δsum ÷ Δcount — histogram mean (TTFT/TPOT/E2E) |
| `align_on_time(...)` | Nearest-neighbour pairing on `time_sec` within half the coarser step |
| `pearson(xs, ys)` | Correlation coefficient |
| `resolve_gpu_hbm(gpu_summary, setup, gpu_config)` | Canonical GPU count and HBM used/total, with the source of each |
| `resolve_kv_bytes_per_token(model, kv_dtype, config)` | KV bytes/token with the architecture and provenance that produced it |
| `resolve_hbm_breakdown(hbm, kv, ...)` | Weights / KV pool / occupied KV / residual split of measured HBM, per GPU |
| `kv_movement_bandwidth(...)` | Logical host-tier KV movement GB/s when no DRAM PMU was collected |

`resolve_gpu_hbm` exists because Executive and Interactive each resolved GPU
count and HBM capacity from their own key lists and disagreed: Interactive
read only `hbm_used_mb_mean` and fell back to a hardcoded **40 GB** per-GPU
capacity, understating a 179 GB B200 by 4.5x. Per-GPU capacity now comes from
`gpu_config.json` (nvidia-smi `memory.total`) first, and there is **no
hardcoded default** — an unresolvable capacity yields 0 so the tile can show
"unknown" rather than a wrong denominator. Both tiles print the resolved
source.

All three report surfaces call `resolve_kv_bytes_per_token`; none keeps its
own architecture table. `resolve_kv_bytes_per_token` exists for the same
reason as `resolve_gpu_hbm`.
Executive and the End Report each carried an architecture table with a "keep in
sync" comment; they drifted. On a `gemma-4-31B-it` run the Executive reported
**320 KB/token** (falling through to a 70B-class default) while the End Report
reported **88 KB/token** — its size-hint matcher used bare substring matching,
and `"1b"` is a substring of `"31b"`, so a 31B model resolved to the 1B entry.
Size hints are now matched on a token boundary, and resolution prefers the
engine's own model config over any name-based table.

KV bytes/token scales every derived bandwidth figure in the report, so its
provenance is now stated wherever it appears — `exact — model config`,
`size hint '31b' (ESTIMATE — assumed layout)`, or `UNRESOLVED`. An estimate
and an exact value are not distinguishable from the number alone.

`counter_delta` is the most misused primitive: `values[-1]` is the total
since the *server* started, unrelated to the collection window. Dividing it
by the window is what produced ~3.9 M tok/s where the true rate was
thousands.

**New code must call these rather than adding a private variant.** Reports
had accumulated eight independent delta/rate helpers and they diverged in
production. Converged so far:

| Helper | Status |
|---|---|
| `combined._rate_with_time`, `_pearson`, `_align_xy` | delegates to kernel |
| `common_kpis._delta`, `_delta_col`, `_ratio_delta_ms` | delegates to kernel |
| `interactive._rate` (both definitions) | delegates to `aligned_rate_series` |
| `amoprof.py` throughput delta | delegates to `counter_delta` |
| `combined._ts_delta`, `amoprof._delta`/`_counter_delta` | **not yet converged** |

`_delta` and `_delta_col` in `common_kpis` were byte-identical copies of the
same loop; `interactive._rate` was defined twice in one file with different
clamping. Each conversion was validated by differential test against the
previous implementation (including counter resets, Δt ≤ 0, single-sample and
empty input) and by byte-comparing the rendered reports.

---

## Report consistency expectations

AMOprof is designed to keep report sections stable across runs:

- End Report sections whose raw source was never collected carry an explicit **"not collected in this run"** banner naming the flag that enables it. Detection is by the presence of the raw source, not by the values: sections such as NVMe IO Workload render *derived projections from token movement*, which are non-zero precisely when the measurement is missing and would otherwise be indistinguishable from a measurement.
- L3-active reports show populated L3 storage and KV-cache tier sections.
- L2-only reports keep L3 sections collapsed instead of removing the section layout.
- Static End Report GPU/HBM timelines use the full report-window display scale.
- KV$B Event Traces appear immediately after KV Cache Footprint & HBM Capacity Analysis.
- Logical SGLang L3 movement and physical SSD/LBA telemetry are shown separately unless a concrete local mapping exists.
- Correlation charts in Executive → Bottleneck Analysis render only for **configured** tiers. An unconfigured tier contributes no axis and is omitted from the card title, so an L1-only run shows `... vs L1 signals` rather than an empty L2/L3 axis.
- Every summary tile in Executive, Interactive, and the End Report shows the formula and exact metric names behind its number. Those strings live only in `report/metric_formulas.py`; the four tile renderers and the End Report §Metrics & Formulas table all read from it, so a metric's definition cannot drift between reports. Explanatory prose is replaced by the formula; measured values in a note (`P90=1.4s`, `312 M txns/s`) are preserved and appended.
- **Throughput numbers are not interchangeable.** KPI tiles report a *run average* over the whole selected window (idle time included); Bottleneck Analysis charts report the *instantaneous* per-sampling-interval rate. A mostly-idle window legitimately shows ~95 tok/s in a tile while the charts peak in the thousands. Each formula caption states which it is.
- Prompt/generation token counters are **cumulative since server start**. Any throughput must use a window delta — dividing a lifetime counter by the collection window overstates by orders of magnitude (a 6-day-old server profiled for 120 s reads ~3.9 M tok/s).
- **GPU series are restricted to the GPUs the server occupies, then collapsed to one sample per timestamp.** A node may hold more GPUs than the run uses: at TP=2 on an 8-GPU host, six are idle. Serving devices are chosen by *activity rank* (the TP × DP busiest by mean utilisation, then memory) rather than by index, because `CUDA_VISIBLE_DEVICES` can remap ordinals so "GPUs 0..TP-1" is not reliable. Without this, averaging across all eight understates the serving GPUs' load by ~4×.
- **Per-GPU rows are then collapsed to one sample per timestamp before correlation.** `gpu_timeseries.csv` carries one row *per GPU per timestamp*; correlating against it unreduced pairs each token sample with an arbitrary GPU's row rather than with the node. On an 8-GPU node this turned r=+0.93 into r=+0.04 for the same underlying relationship. Utilisation-style signals are averaged across GPUs; `mem_used` is summed, matching the "HBM used (all GPUs)" semantics.
- Correlated series are paired on `time_sec`, not on list position — collectors run at different cadences (local collectors default to `--interval-s 1.0` while Prometheus-sourced CSVs use a 15 s step, and AMDuProf PCM is local-only even in Prometheus mode).

---

## Troubleshooting

### `blktrace` or `biosnoop` fails

Run collection with sudo or configure passwordless sudo for the tracing binaries. These tools need root privileges on most systems.

### DRAM bandwidth is missing

Run:

```bash
sudo scripts/install_dram_deps.sh --dram-tool auto
```

Then collect with:

```bash
amoprof collect --enable-dram --dram-tool auto ...
```

### Server Info shows fewer fields than raw/server_info.json

Two filters used to drop fields between the endpoint and the report:

1. `cli._server_info_to_setup_details()` mapped ~18 named fields; SGLang's
   `/server_info` returns the full ServerArgs (100+ entries) and the rest were
   discarded. It now passes through every remaining **scalar** field with a
   humanised label, curated names taking precedence. Nested dicts and long
   lists stay in `SGLang server_info raw`.
2. The Executive Server Configuration table rendered a fixed 11-row list.
   It now appends every remaining scalar `setup_details` entry after the
   curated summary rows.

If a field is still missing, check whether it is a nested object or a list
longer than 12 entries — those are intentionally left in the raw block rather
than flattened into the table.

### Server Info / GPU panels are empty

`_fetch_sglang_server_info()` needs a reachable SGLang endpoint. It tries, in
order: `--server-info-url`, `--sglang-port`, any port recoverable from a
metrics/Prometheus URL already passed, then the SGLang defaults 30000 and
8000. If none respond it logs a warning naming the endpoints tried.

Without server info, `setup_details.json` is not written, the Server Info
panel is empty, and TP/DP are unknown — which also makes the HBM capacity
denominator fall back to the physical device count. Pass `--sglang-port`
pointing at the running server.

### A `--collectors` name is ignored

If the service banner lists fewer collectors than you passed, the missing
name was rejected by the `--collectors` filter. The service now logs this at
ERROR level with the full list of known collectors.

`AVAILABLE_COLLECTORS` is derived from `CollectorRegistry`, so registering a
collector is all that is needed for it to become selectable. The *default-on*
set (`DEFAULT_COLLECTORS`, used when `--collectors` is omitted) stays
explicit, because some registered collectors need BPF/sudo and should not
start unasked.

### TP size disagrees between sources

Two independent sources report tensor-parallel size:

* **Live `/server_info`** (via `--sglang-port`) — authoritative, used for
  `gpu_config.json` and the HBM-capacity denominator.
* **Prometheus `tp_rank` labels** — computed as `max(tp_rank)+1` over the
  label sets *visible to the query*. With `--prom-instance` pinning one
  instance, or an exporter that only publishes rank 0, only one rank is
  visible and this reports **TP=1 for a multi-way TP server**.

The Prometheus value is therefore a **lower bound**, and is now labelled as
such in the console output. `_write_gpu_config()` prefers the live value and
logs a WARNING when the two disagree, because TP multiplies per-GPU HBM into
the "HBM used" denominator — an undercount makes the GPU look far more
utilised than it is.

If you see the warning, the live value is the one being used and no action is
needed. If `/server_info` is unreachable, TP falls back to the Prometheus
lower bound and HBM capacity will be understated.

### A collector is enabled but its metrics have no samples

`amoprof_<collector>_*` gauges existing in Prometheus does **not** mean the
collector produced data. Every collector publishes an `*_available` flag and a
`*_reason` alongside its metrics; when a synthesis finds the gauges but no
samples, analyze now queries that flag and says which case it is:

* **reports NOT AVAILABLE** — the collector ran and produced nothing. The
  binary is missing, unreachable, or the service lacks the privileges it needs
  (MSR access for PMU tools). A host problem, not a windowing one.
* **reports available, but no samples in this window** — the window is
  shorter than the collector's cycle.

A telltale is the summary size: `pcm_summary.json(5)` or
`iostat_summary.json(4)` means only the collection-metadata fields
(`*_collection_duration_s`, `*_available`) came through and no measurement
fields at all.

### `--enable-dram` is set but no DRAM bandwidth is collected

DRAM *bandwidth* requires an external PMU tool; the flag alone does not
provide it. The service resolves the backend from the CPU vendor
(`amduprof` on AMD, `intel-pcm` on Intel) and now checks whether the binary is
on PATH, warning by name when it is not — previously an enabled-but-silent
collector looked identical to the flag never being set.

| Backend | Needs on PATH | Notes |
|---|---|---|
| `amduprof` | `AMDuProfPcm` | AMD EPYC |
| `intel-pcm` | `pcm-memory` / `pcm` | Intel Xeon |
| `perf-imc` | `perf` | uncore IMC counters; needs `perf_event_paranoid <= 0` |

The **configured path is checked first** (`--amduprof-pcm-bin`, env
`AMOPROF_AMDUPROF_PCM_BIN`, default `/opt/AMDuProf_5.2-606/bin/AMDuProfPcm`),
then PATH — these tools normally live outside PATH, so a PATH-only check
false-warns on a correctly configured host. The service logs the resolved
binary on success.

**Vendor mismatch is warned explicitly.** AMDuProf cannot read Intel
memory-controller counters and vice versa; without the warning the collector
runs and silently returns nothing. On an Intel Xeon use `--dram-tool
intel-pcm` or `perf-imc` even if AMDuProf is installed.

`--dram-tool perf-imc` is usually the quickest route on Intel if PCM is not
installed. Note L2 *occupancy* and L1↔L2 movement are measured from SGLang's
hicache counters regardless and need no PMU.

### Only L1 charts appear although L2/L3 are configured

Tier charts need **telemetry**, not configuration. A tier declared in the
SGLang launch command still renders no charts if nothing measured it:

| Tier | Required timeseries | Produced by |
|---|---|---|
| L2 *(occupancy + movement)* | `sglang_hicache_host_used_tokens` / `_total_tokens` in `sglang_timeseries.csv` | SGLang itself — **no PMU needed**. Gives L2 fill, used GB, and L1↔L2 movement bandwidth derived from evict/load-back token rates x KV bytes/token |
| L2 (DRAM bandwidth) | `amduprof_pcm_timeseries.csv` | a **PMU** collector — `--enable-dram` (AMDuProfPcm, Intel PCM, or `--dram-tool perf-imc`). The `dram` collector reports **capacity only** (`/proc/meminfo`) and cannot supply bandwidth |
| L3 (storage) | `nvme_driver_timeseries.csv` | the `nvme_driver` or `iostat` collector, or node_exporter disk metrics in Prometheus |

`analyze` rebuilds both from `amoprof_*` gauges when the service collected
them. **The two PMU collectors and the two storage collectors publish under
different namespaces**, and all four are checked:

| Collector | Metric namespace |
|---|---|
| AMDuProf | `amoprof_amduprof_pcm_dram_*` |
| Intel PCM / perf-IMC | `amoprof_pcm_dram_*` |
| nvme_driver | `amoprof_nvme_driver_nvme_*` |
| iostat | `amoprof_iostat_read_bw_mb_*` etc. |

Checking only the AMD and nvme_driver names reported "L2/L3: NO" on hosts
running Intel PCM and iostat successfully.

Synthesised DRAM rows are written to the file matching the collector that
**produced** them — `pcm_timeseries.csv` for Intel PCM / perf-IMC,
`amduprof_pcm_timeseries.csv` for AMDuProf. The data-source list is keyed on
filename, so writing Intel data into the AMD file made the report claim AMD
uProf was present and Intel PCM missing, both describing the same rows. A per-tier line is printed:

```
Tier chart data — L2 (DRAM BW): NO | L3 (NVMe): yes
[warn] L2 (DRAM BW) has no timeseries — Executive will show no L2 charts even
       if the tier is configured. needs a PMU collector: --enable-dram ...
```

A service started with `--collectors gpu,dram,vmstat,network` has **no L3
collector at all** and only capacity-level DRAM, so it can only ever produce
L1 and NET charts.

### Charts missing on the `--prometheus` path only

The Prometheus fetch pulls a curated list of series, so a chart can be
present on a local `--run-dir` run and absent on a Prometheus-only run of the
same node. Three inputs were previously never requested:

| Chart | Required series | Fetched as |
|---|---|---|
| p50/p90/p99 distribution | `sglang_*_bucket` | histogram loop now includes `_bucket` (was `_sum`/`_count` only) |
| HBM bandwidth | `DCGM_FI_PROF_DRAM_ACTIVE` | written to `gpu_timeseries.csv` as `hbm_bw_pct`, already scaled to percent |
| Network fabric | `amoprof_network_*` | `network_timeseries.csv` synthesised by range-querying the service exporter |

Note the Prometheus path renames DCGM columns: `DRAM_ACTIVE` becomes
`hbm_bw_pct` and `MEM_COPY_UTIL` becomes `mem_copy_util_pct`, both already in
percent. The HBM bandwidth resolver accepts all spellings.

### Network charts are missing

First confirm the collector ran: `raw/network_timeseries.csv` must exist in
the cycle directory and contain rows with `iface=_total`. If it does not, the
collector never started — check the service banner for `network` in the
collector list.

If the CSV exists but the Executive card is absent, one of:

* **No traffic.** The card requires at least one non-zero `total_mbs` sample;
  an idle NIC renders nothing.
* **Timebases do not overlap.** Network and SGLang series are paired on
  `time_sec`, so a network CSV covering a different window than the SGLang
  timeseries yields no aligned pairs. Both should be cycle-relative from the
  same `start_epoch`.


The `network` collector reads `/proc/net/dev` and, for IB/RoCE,
`/sys/class/infiniband/*/ports/*/counters`. Kernel-bypass verbs traffic does
**not** appear in `/proc/net/dev`, so on an RDMA fabric check that
`network_timeseries.csv` contains rows with an `mlx5_*:1`-style `iface`
value. `port_rcv_data` / `port_xmit_data` are counted in 32-bit words and
multiplied by 4 for bytes.

### SGLang counters are missing

Confirm the metrics endpoint is reachable:

```bash
curl http://127.0.0.1:30000/metrics | grep sglang_
```

### SMART data is missing

Install `nvme-cli` and run collection with permission to query the NVMe device:

```bash
sudo nvme smart-log /dev/nvme2n1
```

---

## Collector readiness

`install.sh` runs `check_collectors.py` at the end of installation, and you
can re-run it any time:

```bash
python3 check_collectors.py --ssd-device /dev/nvme0n1
python3 check_collectors.py --only pcm,iostat --seconds 5
```

It **runs each collector**, rather than checking that a binary exists.
Presence is not readiness: Intel PCM installs fine and returns nothing without
MSR access; iostat sits on PATH and reports zeros for the wrong device. Both
failures look identical from Prometheus hours later — the
`amoprof_<collector>_*` gauges appear carrying only collection metadata, the
charts are empty, and nothing says why.

Checks: `cpu`, `vmstat`, `iostat`, `dram`, `gpu`, `smart`, `nvme_driver`,
`queue_depth`, `blktrace`, `biosnoop`.

The trace collectors get privilege checks as well as binary checks: `blktrace`
needs debugfs mounted and root, `biosnoop` needs bcc and root, and both produce
nothing silently without them — which is the failure this script exists to
catch.

```
  [OK]    cpu — util 12.4% mean over 96 core(s), 8 samples
  [OK]    vmstat — readable (1,204 major faults in window)
  [FAIL]  iostat — binary not on PATH
          fix: install sysstat. iostat has no --*-bin flag; it must be on PATH.
  [FAIL]  dram PMU — intel-pcm ran but produced no data: no Intel PCM samples
          fix: this is exactly the failure that shows up later as
               'L2 (DRAM BW): NO' with the gauges present but empty.
```

### Building Intel PCM from source

```bash
./install.sh --with-pcm                    # default branch
./install.sh --with-pcm --pcm-ref 202409   # Xeon 6 / Granite Rapids needs 202409+
./install.sh --with-pcm --pcm-prefix /opt/intel-pcm
```

Opt-in, because it pulls a toolchain and takes a few minutes. It is skipped
automatically on AMD hosts, and when the installed PCM already supports the
CPU. The clone uses `--recursive`: PCM vendors simdjson as a submodule and the
build fails without it.

After building it verifies the new binary actually accepts the CPU — a build
from too old a tag would otherwise install cleanly and still refuse — and
records the path in `.amoprof-pcm.env` with the exact
`--intel-pcm-memory-bin` line to add to your service arguments.

Without `--with-pcm`, install.sh still *detects* an unsupported PCM and tells
you to re-run with it or use `--dram-tool perf-imc`.

**Intel PCM on a newer Xeon.** PCM only supports the microarchitectures its
build was compiled for. On a CPU outside that table — a Granite Rapids Xeon
against a Sapphire-Rapids-era build, say — every `pcm-*` binary is installed
and every one exits with *"unsupported processor"*. "Install the tool" is then
exactly the wrong advice. The check probes for this and points at
`--dram-tool perf-imc`, which reads the same uncore IMC counters through the
kernel and has no CPU-support table. `--dram-tool auto` also avoids PCM in
that case rather than selecting a collector that runs and silently produces
nothing.

Checks performed, beyond running the collector: CPU-vendor vs `--dram-tool`
mismatch (AMDuProf cannot read Intel counters and vice versa), `/dev/cpu/0/msr`
presence for PMU tools, and `perf_event_paranoid` for `perf-imc`. An idle disk
reporting zeros is a **warning**, not a failure — the collector worked, there
was simply nothing happening.

Exit status is non-zero if any checked collector produced no data, so it can
gate an install. A failure does not abort installation; amoprof still works,
the affected charts are just empty.

---

## Testing

Three suites, each answering a different question. Run all three before
packaging or deploying — they take under a minute together.

```bash
python3 validate_math.py                 # is the arithmetic right?
python3 validate_report.py report.html   # does the generated report hold up?
pytest -q tests/ amoprof/tests/          # unit tests (needs `pip install pytest`)
```

`validate_math.py` requires `numpy` and `scipy`; both are already runtime
dependencies. Compiling every module is covered by its group 0, so a separate
`compileall` pass is unnecessary.

Both `validate_*.py` scripts exit non-zero on failure, so they can gate a
release in CI.

### Throughput percentiles: active intervals only

Token-throughput p50/p90/p99 are computed over intervals in which something
was actually served. Including idle intervals put the zeros in charge: at a
2.5% duty cycle, 97.5% of the population is zero, so p50 and p90 both land
inside the idle block and report **0.0** for a server sustaining thousands of
tok/s while working.

```
all intervals : p50=0    p90=0    p99=9000   <- before
active only   : p50=9000 p90=9000 p99=9000   <- now
```

The chart subtitle and the takeaway both state the population and the duty
cycle — `n=7 active of 299 intervals (2.3% duty cycle, 292 idle excluded)` —
so the exclusion is visible and the duty cycle itself becomes a reported
finding rather than something to infer.

Latency percentiles are unaffected: they come from histogram buckets, which
only record actual requests.

### Cache hit rate: token-weighted, not time-weighted

The tile caption previously claimed `Δsglang_cached_tokens_total` was in the
numerator. The code never added it. A caption describing a different
expression than the one evaluated is worse than no caption — it sends the
reader chasing a discrepancy that does not exist. `validate_math.py` group 0b
now asserts the caption matches the computed method.

The headline cache-hit tile is `Δprefill_cache ÷ (Δprefill_cache +
Δprefill_compute)` over the window — **token-weighted**, from
`metric_kernels.prefill_cache_hit_ratio()`.

It previously reported the mean of `sglang_cache_hit_rate` across **all**
samples, idle ones included. At a 2.5% duty cycle that is ~97% zeros, and a
cache serving a third of prefill tokens reported as 0.5%. That number
described the wall clock, not the cache.

Two averaging traps this avoids:

* **Mean over all samples** — idle intervals drag it toward zero.
* **Mean over active samples** — every interval gets an equal vote, so one
  that prefilled 5 tokens counts as much as one that prefilled 100,000.

Weighting by tokens answers what a tiering study asks: of all prefill work,
how much was avoided? It also equals

```promql
sum(increase(sglang:realtime_tokens_total{mode="prefill_cache"}[12h]))
/ ( sum(increase(...{mode="prefill_cache"}[12h]))
  + sum(increase(...{mode="prefill_compute"}[12h])) )
```

so the tile and a Grafana panel agree by construction.

`common_kpis.py` delegates to the same kernel and lists it **first** among
candidate methods. It was last, so three weaker sources — including gauge
means over idle samples — won ahead of it, and different surfaces picked
different methods for the same quantity. All four now report identically
(60.8% on the test fixture), and `validate_math.py` group 0b asserts it.

### Flat series are absence, not zero

A rate series that is entirely zero means the counter was never read, not that
throughput was zero. Charting it produced a scatter with a fabricated
`0.0-1.0` axis that looked like a measurement of a nearly idle system.

Flat driver series are therefore reduced to `[]` **at source**, so every
downstream emitter skips them through checks it already has. Guarding
individual call sites was not enough — six scatters were still drawing
fabricated axes after the first two were fixed, because each emitter had its
own truthiness test and a list of zeros is truthy.

### Run average vs per-interval rate

The End Report throughput tiles and the Executive correlation axes measure
**different things**, and both are correct:

| | Statistic | Typical value |
|---|---|---|
| End Report tile | Δtokens ÷ Δt over the **whole window** | 14.7 tok/s |
| Executive axis | Δtokens ÷ Δt **per sampling interval** | 300–900 tok/s |

They differ by the duty cycle: idle intervals are averaged into the run
average but not into the per-interval rate. A 20x gap means the server was
serving roughly 2.5% of the window — not an error.

Correlation *needs* the per-interval rate: a run average is a single number
and cannot be plotted against anything. Axes are therefore labelled
`(tok/s, per-interval)` and carry the matching formula.

`axis_formula()` now tries the **full** label before stripping the
parenthesised suffix. Stripping first reduced
`Input throughput (tok/s, per-interval)` to `input throughput`, which matched
the run-average entry — so the caption described the opposite statistic to the
one plotted. A qualifier inside the parentheses is meaning, not decoration.

### Counter columns: zeros are not absence

`_sg_raw` is an exact-name lookup and returns a list of **zeros** on a miss,
not an empty list. `if values:` is therefore true for a miss, so a
substring fallback guarded that way never runs — the rate series stayed flat
and the Input/Output tok/s scatter axes collapsed to `0.0-1.0` while the End
Report reported the real rates.

Counter lookups now require an actually-rising series before accepting a hit,
and consider **every** matching column rather than the first: SGLang may export
a plain column of zeros alongside a label-suffixed sibling that carries the
data.

### Raw capacity vs KV-derived occupancy

The capacity charts plot **bytes actually resident**, not tokens × bytes/token:

| Tier | Source | Kind |
|---|---|---|
| L1 | DCGM `mem_used` | measured — all GPU memory, not just KV |
| L2 | `/proc/meminfo` | measured — whole host, not just HiCache |
| L3 | filesystem used/size | measured, when a mount is declared |
| L3.5 | `segment_allocated_bytes` / `segment_total_capacity_bytes` | measured, as the store reports it |

L3.5 here avoids the KV-bytes/token derivation entirely, which is where the
sliding-window-attention error lives — so this occupancy is firmer than the
token-derived figure in the KV tier charts.

Reading them together is the point: **where raw and KV-derived diverge, the
difference is non-KV consumption.** L1 is the clearest case — HBM stays near
constant because the KV pool is preallocated, so a rising raw line would mean
a leak, not caching.

### Percentiles over time

`metric_kernels.percentiles_from_bucket_deltas()` reconstructs quantiles per
interval: cumulative bucket counts are differenced, and the quantile is read
off that interval's distribution with linear interpolation inside the
containing bucket. Prometheus computes `histogram_quantile` over a whole range
rather than as a series, so this is the only way to get a percentile timeline.

Two inherent limits, stated on the chart:

Cumulative bucket counts are made **monotonically non-decreasing** with a
running maximum before any quantile is read. Clamping each bucket delta at 0
independently (for counter resets) can leave a bucket below its predecessor;
the quantile target is then never reached and every percentile falls through
to the last bucket boundary, so p50, p90 and p99 all report the identical
value.

* **Bucket-limited resolution.** A quantile landing in the `+Inf` bucket can
  only be reported as ">= the last finite `le`".
* **Bins widen until each holds >=10 completions.** With one request
  p50 == p90 == p99 by definition, and a single such interval anywhere in the
  run makes all three legend peaks identical — three lines that are really
  one. Discarding those intervals instead left the chart empty on a low-duty
  workload, which is worse. Widening trades **time** resolution, visible in the
  uneven point spacing, for quantiles that are real. Each point carries the
  timestamp of the interval it ends at. Threshold:
  `metric_kernels.MIN_COMPLETIONS_FOR_QUANTILE`.
* ~~Intervals with fewer than 10 completions are omitted.~~ With one request
  p50 == p90 == p99 by definition, and a single such interval anywhere in the
  run makes all three legend peaks identical — three lines that are really
  one. At a low duty cycle most intervals look like this. The threshold is
  `metric_kernels.MIN_COMPLETIONS_FOR_QUANTILE`.
* **Sparse intervals are noisy.** An interval with no completions yields NaN
  rather than a fabricated zero, so the line breaks instead of dropping to the
  axis.

### Cross-surface agreement

Group `0b` of `validate_math.py` renders **all three surfaces from one
directory** and asserts they agree. The kernel layer only prevents divergence
if every surface actually calls it, and repeatedly one did not — the Executive
filtered impossible DRAM samples while the End Report did not, so one file
produced 0.86 GB/s on one tab and 251,246,841 GB/s on another.

The probe directory deliberately contains poisoned samples. Checks: no surface
may render an impossible bandwidth in visible text, and the DRAM total must
agree between Executive and End Report within 5%.

This is the durable fix. Chasing each divergence as it is reported does not
scale; a test that fails when two surfaces disagree does.

### 1. `validate_math.py` — the arithmetic

45 checks in 10 groups. Every kernel is validated against an **independent
reference** (`scipy.stats.pearsonr`, `numpy.diff`, `numpy.quantile`) or a
closed-form answer, never against itself.

| Group | What it pins down |
|---|---|
| 0 | Every module parses; the CLI and all subparsers import — the same thing `install.sh` verifies |
| 1 | Pearson vs scipy across four distributions, plus degenerate cases (constant series, n<3, perfect ±1) and scale/offset invariance |
| 2 | `counter_delta` / `window_rate` vs closed form, including counter resets |
| 3 | `rate_series` vs `numpy.diff`; duplicate-timestamp handling; length-preserving variant |
| 4 | `ratio_delta` histogram mean |
| 5 | `align_on_time` vs brute-force nearest neighbour; non-overlapping windows |
| 6 | End-to-end known relationship recovered through the full pipeline |
| 6b | Sampling-rate dilution (below) |
| 7–8 | Histogram percentiles vs `numpy.quantile`; binned-response monotonicity |

Run it after **any** change to `report/metric_kernels.py`.

Two properties it documents, both inherent rather than defects:

* **Sampling-rate dilution.** A driver varying faster than the resource is
  sampled cannot correlate fully. A 19 s signal against a 15 s scrape yields
  r=+0.24; the same relationship at 754 s yields r=+0.999. A weak r on a
  coarse `--prom-step` may be an artefact of the step, not an absent
  relationship.
* **First-sample loss.** Per-interval deltas start at index 1, so the first
  sample's observations are never counted — 5,980 rather than 6,000 over 300
  intervals of 20.

### 2. `validate_report.py` — the generated HTML

Operates on **the report file itself**, not on the raw directory. It parses
what was actually rendered, so it works on reports produced by a different
version, on another host, or months ago — and it validates the artefact you
ship rather than re-deriving it.

35–66 checks depending on how much the report contains (a combined report with
three tabs exercises far more than a standalone Executive).

```bash
python3 validate_report.py report.html
python3 validate_report.py results/*/amoprof_*_combined.html
python3 validate_report.py --render <raw_dir>     # render first, then check
```

| Group | Checks |
|---|---|
| `LAYOUT` | Document not truncated; no unsubstituted `{template}` placeholders; no leaked Python traceback; Bottleneck Analysis present; tiles rendered |
| `TIER` | A tier the config declares must either be **charted** or **explicitly reported as not collected** — silent omission fails. L1 must always be charted |
| `TILES` | No NaN/Inf; percentages within 0–100; no negative bandwidth/token/power; used ≤ capacity; HBM capacity = per-GPU × the GPU count the tile itself states; KV bytes/token within 1–4096 KB |
| `CHARTS` | Every Pearson r within [-1, 1]; every scatter n ≥ 3; every chart carries hover coordinates; no chart drawn with no data |
| `CROSSTAB` | A quantity shown on more than one tab of a combined report must agree within 2% |

Because it reads the artefact, `TIER` compares the report's **own** claims
against its **own** evidence: if the config table says HiCache is enabled but
no L2 axis appears anywhere and nothing says why, that is a failure regardless
of what the raw directory contained.

Warnings (not failures) flag things worth a look rather than defects: a tier
configured in setup but never measured, KV bytes/token resolved by estimate
rather than model config, scatters drawn from very few aligned samples.

**Known failing check.** `CROSSTAB 'DRAM used' agrees across tabs` fails on
combined reports where the hicache token counts appear only in
`sglang_timeseries.csv` and not in `sglang_summary.json`. The Executive tile
then falls back to OS host memory (`/proc/meminfo`) as the numerator while
keeping the HiCache allocation as the denominator, so the two surfaces report
different quantities under one label. It is left failing deliberately: a green
suite that hides a real defect is worse than a red one that names it.

### 3. `pytest` — unit tests

Five test modules across two directories:

```bash
pip install pytest            # not a runtime dependency
pytest -q tests/ amoprof/tests/
```

| Path | Covers |
|---|---|
| `amoprof/tests/test_common_kpis.py` | shared KPI computation |
| `amoprof/tests/test_server_metrics.py` | metric alias tables |
| `amoprof/tests/test_vllm_collect.py`, `test_vllm_percentiles.py` | vLLM collection and percentiles |
| `tests/test_executive_symbol_regression.py` | Executive symbol regressions |

Unlike the two `validate_*.py` suites, pytest is an optional developer
dependency and is not installed by `install.sh`.

### What to run when

| Change | Run |
|---|---|
| `report/metric_kernels.py` | `validate_math.py` — mandatory |
| Any report surface | `validate_report.py <generated>.html` |
| Collector or CLI flags | `validate_math.py` (group 0 catches syntax/import breakage) |
| Before packaging or release | all three |

A syntax error in any module ships as a broken install and only surfaces at
`from amoprof.cli import main` on the target host, which is why group 0 of
`validate_math.py` parses every module rather than relying on import alone.

### Output directory behavior

`amoprof collect --output-dir <DIR>` now writes the collection directly into `<DIR>`:

- `<DIR>/raw/` contains the canonical raw CSV/JSON files.
- `<DIR>/summary.json` and `<DIR>/summary.csv` describe the run.
- Reports are written directly into `<DIR>` when requested.

This means scripts can run:

```bash
amoprof collect --output-dir results/my_run --enable-dram --dram-tool auto
amoprof analyze --run-dir results/my_run --combined-report
```

For compatibility with older workflows that expect `<DIR>/metrics_run_<timestamp>/raw`, pass `--nested-output` to `collect`.
