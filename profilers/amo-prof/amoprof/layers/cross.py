"""Cross-layer synthetic layer.

Owns no collectors. Owns charts that overlay two or more real layers:
cross_layer_kpi, bottleneck_radar, kvssd_cross_layer, kv_lba_dram_correlation.

Uses the `AIStackLayer.CROSS` sentinel so LayerRegistry keeps its
"one class per AIStackLayer" invariant. `collect()` is a no-op — cross
signals are derived from other layers' summaries at analyze time.
"""
from __future__ import annotations

from typing import Any

from ..base import AIStackLayer, BaseCollector
from .base import LayerAnalysis, LayerModule, register_layer


@register_layer
class CrossLayer(LayerModule):
    LAYER = AIStackLayer.CROSS
    NAME  = "cross_layer"
    TITLE = "Cross-layer"

    def build(self, args: Any, ctx: dict[str, Any]) -> dict[str, BaseCollector]:
        return {}

    def collect(self, args: Any, ctx: dict[str, Any]) -> dict[str, BaseCollector]:
        return {}

    def stop(self) -> dict[str, dict[str, Any]]:
        return {}

    def analyze(self, raw_dir: Any, metrics: Any,
                scenarios: dict[str, Any] | None = None,
                bottlenecks: list | None = None) -> LayerAnalysis:
        from ..report import amoprof as R
        a = LayerAnalysis(layer=self.LAYER, name=self.NAME, title=self.TITLE)
        self._render_chart(a, "cross_layer_kpi",         R.chart_cross_layer_kpi,         metrics)
        self._render_chart(a, "kvssd_cross_layer",       R.chart_kvssd_cross_layer,       metrics)
        self._render_chart(a, "kv_lba_dram_correlation", R.chart_kv_lba_dram_correlation, metrics)
        if bottlenecks:
            self._render_chart(a, "bottleneck_radar", R.chart_bottleneck_radar, bottlenecks)
        return a
