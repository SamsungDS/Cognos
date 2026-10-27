"""amoprof.collectors — one collector class per module.


Importing this package imports every submodule, which triggers each
class's @register_collector decorator and populates CollectorRegistry.

For backward compatibility we also re-export every class name so that
`from amoprof.collectors import IostatMonitor` continues to work.
"""
from __future__ import annotations

from .amduprof_pcm import AMDuProfPcmMemoryCollector  # noqa: F401
from .biolatency import BiolatencyCollector  # noqa: F401
from .biosnoop import BiosnoopCollector  # noqa: F401
from .blktrace import BlktraceCollector  # noqa: F401
from .bpftrace import BpftraceCollector  # noqa: F401
from .discard import DiscardStatsMonitor  # noqa: F401
from .dram import DramMonitor  # noqa: F401
from .gpu import GpuMonitor  # noqa: F401
from .iostat import IostatMonitor  # noqa: F401
from .nsys import NsysGpuTraceCollector  # noqa: F401
from .network import NetworkMonitor  # noqa: F401
from .nvlink_pcie import NvlinkPcieMonitor  # noqa: F401
from .nvme_driver import NvmeDriverMonitor  # noqa: F401
from .nvme_smart import NvmeSmartMonitor  # noqa: F401
from .pcm_memory import PcmMemoryCollector  # noqa: F401
from .perf_stat import PerfStatCollector  # noqa: F401
from .power import PowerMonitor  # noqa: F401
from .queue_depth import BlockQueueDepthCollector  # noqa: F401
from .sglang import SGLangMetricsSampler  # noqa: F401
from .ssd_hardware import SsdHardwareMonitor  # noqa: F401
from .swap_storm import SwapStormMonitor  # noqa: F401
from .cpu import CpuMonitor  # noqa: F401
from .vmstat import VmstatMonitor  # noqa: F401

__all__ = [
    "AMDuProfPcmMemoryCollector",
    "BiolatencyCollector",
    "BiosnoopCollector",
    "BlktraceCollector",
    "BlockQueueDepthCollector",
    "BpftraceCollector",
    "DiscardStatsMonitor",
    "DramMonitor",
    "GpuMonitor",
    "IostatMonitor",
    "NsysGpuTraceCollector",
    "NvlinkPcieMonitor",
    "NvmeDriverMonitor",
    "NvmeSmartMonitor",
    "PcmMemoryCollector",
    "PerfStatCollector",
    "PowerMonitor",
    "SGLangMetricsSampler",
    "SsdHardwareMonitor",
    "SwapStormMonitor",
    "CpuMonitor",
    "VmstatMonitor",
]
