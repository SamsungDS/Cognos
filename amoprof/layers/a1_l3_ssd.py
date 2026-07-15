"""A1 — Hardware (L1 HBM + L2 DRAM + L3 SSD).

Per the AI-workload architecture (aiOpsArch.pptx), A1 is the physical
hardware row: HBM (~3.35 TB/s per H100), DRAM (~300 GB/s DDR5 ECC),
and SSD NAND (seq BW, random IOPS, WAF, TBW, endurance).

AMOprof today only ships collectors for the L3 SSD column
(nvme-smart-log, sysfs, df). HBM samples live implicitly in A4's GPU
collectors; DRAM hardware samples in A3's pcm/amduprof_pcm. When
dedicated HBM / DRAM hardware collectors land, they will register
against A1_L3_SSD (the enum member name is legacy — A1 spans all three
columns).

Owns collectors: ssd_hw, smart.
Owns charts:     ssd_per_device_overlay, ssd_read_workload,
                 ssd_write_workload, trim_seasonal.
"""
from __future__ import annotations

from typing import Any

from ..base import AIStackLayer
from .base import LayerAnalysis, LayerModule, register_layer


@register_layer
class A1L3SsdLayer(LayerModule):
    LAYER = AIStackLayer.A1_L3_SSD
    NAME  = "a1_hardware"
    TITLE = "A1 — Hardware (HBM · DRAM · SSD)"

    def analyze(self, raw_dir: Any, metrics: Any,
                scenarios: dict[str, Any] | None = None,
                bottlenecks: list | None = None) -> LayerAnalysis:
        from ..report import amoprof as R
        a = LayerAnalysis(layer=self.LAYER, name=self.NAME, title=self.TITLE)
        self._render_chart(a, "ssd_per_device_overlay", R.chart_ssd_per_device_overlay, metrics)
        self._render_chart(a, "ssd_read_workload",     R.chart_ssd_read_workload,     metrics)
        self._render_chart(a, "ssd_write_workload",    R.chart_ssd_write_workload,    metrics)
        self._render_chart(a, "trim_seasonal",         R.chart_trim_seasonal,         metrics)
        return a
