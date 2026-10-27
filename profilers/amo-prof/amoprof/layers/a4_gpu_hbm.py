"""A4 — Inference Runtime (server + GPU).

Per the AI-workload architecture (aiOpsArch.pptx), A4 owns everything
the inference runtime does — batch efficiency, KV$ operations, prefill/
decode scheduling, KV swap utilisation — and the GPU/HBM signals it
drives (utilisation, HBM occupancy, NVLink/PCIe traffic, kernel traces).

Owns collectors:
  sglang        — SGLang Prometheus scrape (KV$ tiers, TTFT, throughput)
  perf          — perf stat -p PID (cycles, IPC, cache misses, faults)
  bpf           — bpftrace uprobes (mmap, page faults, malloc)
  gpu           — nvidia-smi / DCGM samples
  nsys          — Nsight Systems GPU trace
  nvlink_pcie   — NVLink + PCIe TX/RX bandwidth

Owns charts:
  Runtime (sglang):  inference_metrics, percentile_summary,
                     latency_breakdown, kv_analysis, kv_tiers,
                     session_analysis, kvb_events
  GPU / HBM:         gpu_timeline (PNG), gpu_timeline_plotly (HTML),
                     hbm_bandwidth, pcie_nvlink

nsys is pid-scoped and honors `--nsys-pid` when set; otherwise it falls
back to the sglang PID.
"""
from __future__ import annotations

from typing import Any

from ..base import AIStackLayer, CollectorSpec
from .base import LayerAnalysis, LayerModule, register_layer


@register_layer
class A4GpuHbmLayer(LayerModule):
    LAYER = AIStackLayer.A4_GPU_HBM
    NAME  = "a4_inference_runtime"
    TITLE = "A4 — Inference Runtime"

    def _resolve_pid_for_spec(self, spec: CollectorSpec,
                              ctx: dict[str, Any]) -> "int | None":
        # nsys prefers --nsys-pid; falls back to the default pid.
        if spec.name == "nsys":
            return ctx.get("nsys_pid") or ctx.get("pid")
        return super()._resolve_pid_for_spec(spec, ctx)

    def analyze(self, raw_dir: Any, metrics: Any,
                scenarios: dict[str, Any] | None = None,
                bottlenecks: list | None = None) -> LayerAnalysis:
        from ..report import amoprof as R
        a = LayerAnalysis(layer=self.LAYER, name=self.NAME, title=self.TITLE)
        # Runtime signals (sglang, perf, bpf) — batch efficiency, KV$ ops,
        # request-level percentiles.
        self._render_chart(a, "inference_metrics",   R.chart_inference_metrics,   metrics)
        self._render_chart(a, "percentile_summary",  R.chart_percentile_summary,  metrics)
        self._render_chart(a, "latency_breakdown",   R.chart_latency_breakdown,   metrics)
        self._render_chart(a, "kv_analysis",         R.chart_kv_analysis,         metrics)
        self._render_chart(a, "kv_tiers",            R.chart_kv_tiers,            metrics)
        self._render_chart(a, "session_analysis",    R.chart_session_analysis,    metrics)
        self._render_chart(a, "kvb_events",          R.chart_kvb_events,          metrics)
        # GPU / HBM signals driven by the runtime.
        self._render_chart(a, "gpu_timeline",        R.chart_gpu_timeline,        metrics)
        self._render_chart(a, "gpu_timeline_plotly", R.chart_gpu_timeline_plotly, metrics, kind="html")
        self._render_chart(a, "hbm_bandwidth",       R.chart_hbm_bandwidth,       metrics)
        self._render_chart(a, "pcie_nvlink",         R.chart_pcie_nvlink,         metrics)
        return a
