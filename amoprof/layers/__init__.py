"""amoprof.layers — layer-oriented analog of amoprof.collectors.

Each AI-stack layer (A1..A5, HOST_OS, plus the synthetic CROSS layer) is
represented by a concrete `LayerModule` subclass. Importing this package
imports every submodule, which triggers the class-body `@register_layer`
decorator and populates `LayerRegistry`.

Stage 1 (this commit) introduces the abstractions and skeleton classes
only. cli._collect / cli._analyze continue to drive collectors and charts
through the existing paths; behavior is unchanged.
"""
from __future__ import annotations

from .base import (
    LayerAnalysis,
    LayerModule,
    LayerRegistry,
    ORDERED_LAYERS,
    register_layer,
)
from .a1_l3_ssd import A1L3SsdLayer  # noqa: F401
from .a2_nvme_driver import A2NvmeDriverLayer  # noqa: F401
from .a3_dram import A3DramLayer  # noqa: F401
from .a4_gpu_hbm import A4GpuHbmLayer  # noqa: F401
from .a5_app import A5AppLayer  # noqa: F401
from .cross import CrossLayer  # noqa: F401

# ─── Layered-analyze entry point ──────────────────────────────────────────────
def run_layered_analyze(raw_dir):
    """Run analyze across every registered layer against `raw_dir`.

    Loads raw data + Metrics once, then hands the shared Metrics to each
    layer's `analyze()`. Returns `{LayerModule.NAME: LayerAnalysis}` in
    ORDERED_LAYERS order. Callers combine the LayerAnalysis fields into
    whatever section layout the report renderer wants.

    Programmatic entry point only — cli._analyze is NOT rewired here.
    Stage 4 introduces a renderer + swaps generate_adaptive_report for
    this loop once the section-based HTML template exists.
    """
    from pathlib import Path
    from ..report.amoprof import (
        load_raw_dir_with_extras, extract_metrics, score_bottlenecks,
        _amoprof_resolve_raw_dir_path,
    )
    raw_dir = Path(raw_dir)
    # Resolve wrapper-vs-raw dir once so downstream sibling lookups
    # (blktrace_analysis/, biosnoop_events.csv, etc.) hit the right level.
    resolved = _amoprof_resolve_raw_dir_path(raw_dir)
    # Auto-discover the blktrace_analysis/ subdir the static path receives
    # via `--blktrace-analysis-dir` from cli._run_amoprof. Without this, the
    # SSD Queue Depth chart + blktrace stream/hotcold charts render empty
    # even when analysis CSVs are already present next to raw/.
    bt_analysis_dir = resolved / "blktrace_analysis"
    bt_analysis_arg = (str(bt_analysis_dir)
                      if bt_analysis_dir.is_dir()
                      and (bt_analysis_dir / "queue_depth_summary.json").exists()
                      else "")
    data = load_raw_dir_with_extras(
        raw_path=resolved,
        blktrace_analysis_dir=bt_analysis_arg,
    )
    metrics = extract_metrics(data)
    # score_bottlenecks feeds chart_bottleneck_radar; compute once.
    bottlenecks = score_bottlenecks(metrics)

    results = {}
    for cls in LayerRegistry.ordered():
        inst = cls()
        analysis = inst.analyze(raw_dir, metrics,
                                scenarios=None,
                                bottlenecks=bottlenecks)
        results[inst.NAME] = analysis
    return results


__all__ = [
    "LayerAnalysis",
    "LayerModule",
    "LayerRegistry",
    "ORDERED_LAYERS",
    "register_layer",
    "run_layered_analyze",
    "A1L3SsdLayer",
    "A2NvmeDriverLayer",
    "A3DramLayer",
    "A4GpuHbmLayer",
    "A5AppLayer",
    "CrossLayer",
]
