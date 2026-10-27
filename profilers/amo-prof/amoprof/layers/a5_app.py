"""A5 — Application (benchmark harness).

Per the AI-workload architecture (aiOpsArch.pptx), A5 is the top of the
stack: the benchmark harness that drives the workload and measures
end-user KPIs (Tokens/s, TTFT, TPOT, P99 request latency).

No collectors register against A5 today. When a benchmark-harness
collector lands (e.g. bench_serving output → CSV → collector), it will
declare `layer=AIStackLayer.A5_APP` and this class will render its
charts. Until then, the section renders as an empty placeholder so the
layered report keeps its full stack view.
"""
from __future__ import annotations

from typing import Any

from ..base import AIStackLayer
from .base import LayerAnalysis, LayerModule, register_layer


@register_layer
class A5AppLayer(LayerModule):
    LAYER = AIStackLayer.A5_APP
    NAME  = "a5_app"
    TITLE = "A5 — Application (benchmark harness)"

    def analyze(self, raw_dir: Any, metrics: Any,
                scenarios: dict[str, Any] | None = None,
                bottlenecks: list | None = None) -> LayerAnalysis:
        # Placeholder: no collectors emit A5-layer data today. See the
        # class docstring for the plug-in contract.
        return LayerAnalysis(layer=self.LAYER, name=self.NAME, title=self.TITLE)
