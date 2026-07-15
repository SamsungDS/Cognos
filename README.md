# AMOprof

AMOprof is a profiling and report-generation package for AI inference workloads. It correlates SGLang/HiCache metrics, GPU/HBM telemetry, host DRAM bandwidth, OS memory pressure, and local storage activity into Executive, Interactive, and End Report views.

It is designed for long-context and KV-cache tiering experiments where HBM, DRAM, and local SSD/NVMe behavior must be interpreted together without mixing logical cache counters with physical block-device telemetry.

---

## What AMOprof reports

AMOprof can generate a single combined HTML report with three tabs:

| Tab | Purpose |
|---|---|
| Executive | High-level KPIs, findings, source health, and cross-layer interpretation. |
| Interactive | Plotly-based exploratory timelines and drill-down charts. |
| End Report | Static deep-dive report with formulas, sectioned analysis, PNG charts, and per-chart takeaways. |

Core analysis areas include:

- SGLang request, latency, throughput, and cache-hit metrics.
- GPU utilization, GPU power, HBM usage, HBM bandwidth, and NVLink/PCIe signals when available.
- HiCache/KV tier analysis across L1/HBM, L2/DRAM, and L3/local storage.
- L3 local storage analysis from blktrace/iostat/sysfs, including bandwidth, IOPS, queue-depth evidence, request sizes, hot/cold LBA, TRIM/discard, and per-stream attribution when collected.
- DRAM bandwidth from AMD uProf, Intel PCM, or perf IMC fallback.
- OS page activity from vmstat, swap, NUMA, and page-fault counters.
- Formula/source documentation so report KPIs can be traced back to counters.

---

## Tier terminology

| Tier | Meaning | Typical source |
|---|---|---|
| L1 | GPU HBM and hot KV cache | DCGM / nvidia-smi / SGLang |
| L2 | Host DRAM / HiCache memory tier | SGLang host-cache counters, setup details, DRAM PMU |
| L3 | Node-local SSD/NVMe or local file-backed HiCache storage | blktrace, iostat, sysfs, SMART, filesystem capacity, plus SGLang movement counters |
| L3.5 | AI Memory Node, Mooncake, remote/shared/disaggregated memory, object store, or unresolved logical backing tier with no local SSD mapping | Logical SGLang movement counters; physical charts only when an explicit device mapping exists |

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
    │   ├── common_kpis.py            # Shared KPI definitions
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

## Report consistency expectations

AMOprof is designed to keep report sections stable across runs:

- L3-active reports show populated L3 storage and KV-cache tier sections.
- L2-only reports keep L3 sections collapsed instead of removing the section layout.
- Static End Report GPU/HBM timelines use the full report-window display scale.
- KV$B Event Traces appear immediately after KV Cache Footprint & HBM Capacity Analysis.
- Logical SGLang L3 movement and physical SSD/LBA telemetry are shown separately unless a concrete local mapping exists.

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

## Development checks

```bash
python -m compileall -q amoprof
pytest -q tests/ amoprof/tests/       # top-level + inner package tests
```

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
