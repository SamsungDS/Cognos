"""A2 — I/O drivers (GPU / CPU / NVMe).

Per the AI-workload architecture (aiOpsArch.pptx), A2 is the true
driver-level row: CUDA streams, CPU/NUMA scheduler, io_uring / NVMe
driver, GPUDirect Storage (GDS), NVMe-oF fabric. AMOprof today ships
only the NVMe-side signals (iostat, biosnoop, /sys/block queue depth).

Owns collectors:
  iostat, biosnoop, nvme_driver, queue_depth_sysfs
Owns charts:
  storage, ssd_queue_depth, nvme_io, kvssd_io

biolatency / blktrace live above the driver at A3 (block layer) per
the arch — see A3DramLayer.
"""
from __future__ import annotations

from typing import Any

from ..base import AIStackLayer
from .base import LayerAnalysis, LayerModule, register_layer


@register_layer
class A2NvmeDriverLayer(LayerModule):
    LAYER = AIStackLayer.A2_NVME_DRIVER
    NAME  = "a2_io_drivers"
    TITLE = "A2 — I/O drivers (NVMe)"

    def analyze(self, raw_dir: Any, metrics: Any,
                scenarios: dict[str, Any] | None = None,
                bottlenecks: list | None = None) -> LayerAnalysis:
        from ..report import amoprof as R
        a = LayerAnalysis(layer=self.LAYER, name=self.NAME, title=self.TITLE)
        self._render_chart(a, "storage",         R.chart_storage,         metrics)
        self._render_chart(a, "ssd_queue_depth", R.chart_ssd_queue_depth, metrics)
        self._render_chart(a, "nvme_io",         R.chart_nvme_io,         metrics)
        self._render_chart(a, "kvssd_io",        R.chart_kvssd_io,        metrics)
        return a
