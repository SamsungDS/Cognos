"""A3 — OS / Memory manager + Block layer.

Per the AI-workload architecture (aiOpsArch.pptx), A3 spans three columns:
  • CUDA / kernel-layer signals (KV$ resident on HBM)
  • OS / memory-manager signals (page faults, swap, TLB, NUMA)
  • OS / block-layer signals    (biolatency, blktrace, TRIM/discard,
                                 KV$ cold eviction, page cache)

Owns collectors:
  dram, pcm, amduprof_pcm      — DRAM bandwidth / channel utilisation
  vmstat, swap_storm           — page faults, swap in/out
  discard                      — TRIM / discard from /proc/diskstats
  power                        — RAPL / DCGM / IPMI power
  biolatency                   — biolatency-bpfcc read-latency histogram
  blktrace                     — blktrace per-request block I/O events

Owns charts:
  DRAM / memory-manager:  memory, dram_bandwidth, swap_storm
  Block layer:            blkio_deep, blktrace_streams, blktrace_hotcold

pcm and amduprof_pcm share `enable_flag="enable_dram"`; exactly one is
active per run. The choice is driven by `ctx["dram_tool"]` (resolved by
cli._resolve_dram_tool based on CPU vendor + --dram-tool).
"""
from __future__ import annotations

from typing import Any

from ..base import AIStackLayer, CollectorSpec
from .base import LayerAnalysis, LayerModule, register_layer


@register_layer
class A3DramLayer(LayerModule):
    LAYER = AIStackLayer.A3_DRAM
    NAME  = "a3_os_memory_block"
    TITLE = "A3 — OS / Memory manager + Block layer"

    def _policy_gate(self, spec: CollectorSpec, ctx: dict[str, Any]) -> bool:
        """Pick between `pcm` and `amduprof_pcm` based on --dram-tool.

        Both share enable_flag='enable_dram'; only one should build.
        `dram` (perf-imc/generic) is always allowed when enabled.
        """
        if spec.name not in ("pcm", "amduprof_pcm"):
            return True
        tool = ctx.get("dram_tool", "")
        if spec.name == "amduprof_pcm":
            return tool == "amduprof"
        # `pcm` covers intel-pcm and perf-imc.
        return tool in {"intel-pcm", "perf-imc"}

    def analyze(self, raw_dir: Any, metrics: Any,
                scenarios: dict[str, Any] | None = None,
                bottlenecks: list | None = None) -> LayerAnalysis:
        from ..report import amoprof as R
        a = LayerAnalysis(layer=self.LAYER, name=self.NAME, title=self.TITLE)
        # DRAM / OS memory-manager signals.
        self._render_chart(a, "memory",           R.chart_memory,           metrics)
        self._render_chart(a, "dram_bandwidth",   R.chart_dram_bandwidth,   metrics)
        self._render_chart(a, "swap_storm",       R.chart_swap_storm,       metrics)
        # Block-layer signals (page cache, biolatency, blktrace).
        self._render_chart(a, "blkio_deep",       R.chart_blkio_deep,       metrics)
        self._render_chart(a, "blktrace_streams", R.chart_blktrace_streams, metrics)
        self._render_chart(a, "blktrace_hotcold", R.chart_blktrace_hotcold, metrics)
        return a
