"""Block-device facts shared by the storage collectors and the preflight.

Under NVMe native multipath (nvme_core.multipath=Y, the Ubuntu default),
/dev/nvmeXnY is a namespace head: bios are re-issued on a hidden controller
path nvmeXcZnY, which carries the I/O counters and the block-layer trace
events.  The head's /sys/block/<dev>/stat stays at zero and blktrace attached
to it records nothing, while the path has no device node to attach to.
"""
from __future__ import annotations

import os
import re
from pathlib import Path


def nvme_multipath_paths(device: str | None, sys_root: str = "/sys") -> list[str] | None:
    """Controller paths behind an NVMe multipath namespace head.

    Returns None when `device` is not a multipath head (plain NVMe, SATA, a
    path device itself, or no device), else the sorted path names, which can
    be empty if sysfs lists none.  A partition is resolved to its disk.
    """
    base = os.path.basename(str(device or "").strip())
    m = re.fullmatch(r"nvme(\d+)n(\d+)(?:p\d+)?", base)
    if not m:
        return None
    disk = f"nvme{m.group(1)}n{m.group(2)}"
    block = Path(sys_root) / "block"
    try:
        target = os.path.realpath(block / disk / "device")
    except OSError:
        return None
    if not os.path.basename(target).startswith("nvme-subsys"):
        return None
    pat = re.compile(rf"nvme{m.group(1)}c\d+n{m.group(2)}")
    try:
        return sorted(p.name for p in block.iterdir() if pat.fullmatch(p.name))
    except OSError:
        return []


def allocated_bytes(paths) -> int:
    """Bytes actually allocated on disk.

    blktrace creates sparse per-CPU files, so st_size reads as tens of GB for
    a trace holding a few hundred bytes (256 files once summed to "65536 MB").
    """
    total = 0
    for p in paths:
        try:
            total += Path(p).stat().st_blocks * 512
        except OSError:
            pass
    return total
