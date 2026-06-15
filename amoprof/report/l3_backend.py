"""Shared L3 / HiCache backend resolver for AMOprof reports.

The SGLang HiCache movement counters (backuped/prefetched/load_back) are
logical tier-movement counters.  They do not by themselves say whether the
backing tier is local SSD, Mooncake, CXL, or another remote backend.  This
module centralises that decision so Executive, Interactive, and End Report use
one interpretation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

_MISSING = {"", "unknown", "none", "n/a", "na", "null", "default", "disabled", "false", "0", "-", "—"}

@dataclass(frozen=True)
class L3BackendResolution:
    backend_class: str          # local_ssd | remote_mooncake | remote_storage | host_dram_only | unknown
    display_name: str           # Local SSD, Mooncake, Remote storage, ...
    logical_write_label: str    # what backuped_tokens_total means
    logical_read_label: str     # what prefetched means; load_back is diagnostic-only
    has_local_block_mapping: bool
    local_device: str = ""
    local_mount_path: str = ""
    local_storage_path: str = ""
    evidence: str = ""


def _norm(v: Any) -> str:
    return str(v if v is not None else "").strip()


def _is_set(v: Any) -> bool:
    s = _norm(v)
    return bool(s) and s.lower() not in _MISSING


def _get(setup: Mapping[str, Any], *keys: str) -> str:
    # exact first, then case-insensitive
    for k in keys:
        if k in setup and _is_set(setup.get(k)):
            return _norm(setup.get(k))
    lower = {str(k).lower(): v for k, v in setup.items()}
    for k in keys:
        v = lower.get(k.lower())
        if _is_set(v):
            return _norm(v)
    return ""


def _defaulted_fields(setup: Mapping[str, Any]) -> set[str]:
    s = _norm(setup.get("Defaulted fields", setup.get("defaulted_fields", "")))
    return {x.strip().lower() for x in s.split(",") if x.strip()}


def _get_explicit(setup: Mapping[str, Any], *keys: str) -> str:
    defaulted = _defaulted_fields(setup)
    for k in keys:
        if k.lower() in defaulted:
            continue
        if k in setup and _is_set(setup.get(k)):
            return _norm(setup.get(k))
    lower = {str(k).lower(): v for k, v in setup.items()}
    for k in keys:
        if k.lower() in defaulted:
            continue
        v = lower.get(k.lower())
        if _is_set(v):
            return _norm(v)
    return ""


def resolve_l3_backend(setup: Mapping[str, Any] | None, launch_command: str | None = None) -> L3BackendResolution:
    setup = setup or {}
    launch = _norm(launch_command or _get(setup, "Launch command", "launch_command", "SGLang launch command", "sglang_launch_command"))

    storage_type = _get(setup, "L3 storage type", "l3_storage_type", "L3 type", "l3_type", "Cache L3 storage backend", "cache_l3_backend")
    backend = _get(setup, "HiCache storage backend", "hicache_storage_backend", "L3 backend", "l3_backend", "storage_backend", "hicache_backend")
    device = _get_explicit(setup, "L3 Device", "L3 device", "L3 block device", "l3_device", "L3 storage device", "l3_storage_device", "NVMe device", "ssd_device")
    mount = _get_explicit(setup, "L3 Mount Path", "L3 mount path", "L3 mount", "l3_mount_path", "L3 storage mount path", "l3_storage_mount_path")
    path = _get_explicit(setup, "HiCache storage path", "hicache_storage_path", "L3 filesystem path", "L3 storage path", "l3_storage_path", "storage_path")

    blob = " ".join([storage_type, backend, device, mount, path, launch]).lower()
    has_mapping = bool(device or mount or path)

    if any(x in blob for x in ("mooncake", "moon cake")):
        return L3BackendResolution(
            "remote_mooncake", "Mooncake / remote L3",
            "logical remote L3 write from sglang_backuped_tokens_total",
            "logical remote L3 read/onboard from sglang_prefetched_tokens_total; sglang_load_back_tokens_total is diagnostic-only",
            False, evidence="mooncake in setup/launch")

    if any(x in blob for x in ("s3", "object", "remote", "rdma", "tcp", "nfs", "lustre", "weka", "ceph", "disaggregated")):
        return L3BackendResolution(
            "remote_storage", "Remote L3 storage",
            "logical remote L3 write from sglang_backuped_tokens_total",
            "logical remote L3 read/onboard from sglang_prefetched_tokens_total; sglang_load_back_tokens_total is diagnostic-only",
            False, evidence="remote/object/disaggregated backend in setup/launch")

    # Local file/SSD backend.  A concrete device/mount/path is best evidence,
    # but setup may only say NVMe SSD / file backend; treat that as local SSD for
    # logical counter meaning, while has_local_block_mapping records whether raw
    # block telemetry can be safely called physical L3 SSD telemetry.
    if (has_mapping or any(x in blob for x in ("nvme", "ssd", "file", "filesystem", "fs", "block", "disk", "/dev/"))):
        return L3BackendResolution(
            "local_ssd", "Local SSD / file-backed L3",
            "logical local-SSD L3 write from sglang_backuped_tokens_total",
            "logical local-SSD L3 read/onboard from sglang_prefetched_tokens_total; sglang_load_back_tokens_total is diagnostic-only",
            has_mapping, local_device=device, local_mount_path=mount, local_storage_path=path,
            evidence="local SSD/file/backend/path/device in setup/launch")

    hicache = _get(setup, "HiCache", "Hierarchical cache", "enable_hierarchical_cache", "hicache", "HiCache enabled")
    if hicache and hicache.lower() in {"l2", "host", "host_dram", "dram", "enabled-no-storage", "memory"}:
        return L3BackendResolution(
            "host_dram_only", "Host DRAM only",
            "not an L3 write; no backing L3 backend resolved",
            "not an L3 read; no backing L3 backend resolved",
            False, evidence="hicache enabled without resolved storage backend")

    return L3BackendResolution(
        "unknown", "Unknown L3 backend",
        "generic logical HiCache backup from sglang_backuped_tokens_total",
        "generic logical HiCache read/onboard from sglang_prefetched_tokens_total; sglang_load_back_tokens_total is diagnostic-only",
        False, evidence="no explicit backend evidence")

@dataclass(frozen=True)
class L3IoReconciliation:
    status: str                 # match | partial | mismatch | no_block | not_comparable | no_l3
    display_status: str
    note: str
    sglang_write_gb: float
    sglang_read_gb: float
    block_write_gb: float
    block_read_gb: float
    write_ratio: float
    read_ratio: float


def reconcile_l3_io(backend: L3BackendResolution, *,
                     sglang_write_gb: float = 0.0, sglang_read_gb: float = 0.0,
                     block_write_gb: float = 0.0, block_read_gb: float = 0.0,
                     blktrace_available: bool = False, tolerance: float = 0.35) -> L3IoReconciliation:
    """Compare SGLang logical L3 movement with local block telemetry.

    SGLang reports logical KV movement (tokens × KV bytes/token).  blktrace/
    blkparse/iostat report physical local block-device bytes.  They are directly
    comparable only when the resolved backend is local_ssd and setup maps L3 to
    a concrete local block device/mount/path.  The report should never merge
    the two silently; this helper returns an explicit status and note used by
    Executive, Interactive, and End Report sections.
    """
    sw, sr = max(float(sglang_write_gb or 0.0), 0.0), max(float(sglang_read_gb or 0.0), 0.0)
    bw, br = max(float(block_write_gb or 0.0), 0.0), max(float(block_read_gb or 0.0), 0.0)
    logical = sw + sr
    physical = bw + br
    wr = (bw / sw) if sw > 0 else (1.0 if bw == 0 else float('inf'))
    rr = (br / sr) if sr > 0 else (1.0 if br == 0 else float('inf'))
    if logical <= 0 and physical <= 0:
        return L3IoReconciliation('no_l3','No L3 activity','Neither SGLang nor local block telemetry shows L3 I/O in the selected window.',sw,sr,bw,br,wr,rr)
    if backend.backend_class != 'local_ssd' or not backend.has_local_block_mapping:
        return L3IoReconciliation('not_comparable','Not directly comparable',f'SGLang counters are logical {backend.display_name} movement; local block-device bytes are not treated as L3 because no resolved local SSD block mapping is available.',sw,sr,bw,br,wr,rr)
    if not blktrace_available and physical <= 0:
        return L3IoReconciliation('no_block','No physical block trace','SGLang shows logical local-SSD L3 movement, but blktrace/blkparse physical bytes are missing or zero for the window.',sw,sr,bw,br,wr,rr)
    # Directional tolerance with a tiny absolute floor to avoid noise-only mismatches.
    def ok(logical_gb, physical_gb):
        if logical_gb <= 0:
            return physical_gb <= 0.01
        return abs(physical_gb - logical_gb) <= max(0.05, tolerance * logical_gb)
    w_ok, r_ok = ok(sw,bw), ok(sr,br)
    if w_ok and r_ok:
        return L3IoReconciliation('match','Consistent','SGLang logical L3 bytes and local SSD physical bytes agree within tolerance for read/write directions.',sw,sr,bw,br,wr,rr)
    if (sw > 0 and bw <= 0.01) or (sr > 0 and br <= 0.01):
        return L3IoReconciliation('partial','Partial capture','SGLang shows logical local-SSD L3 movement, but one or more physical blktrace directions are missing/zero; report shows provenance separately and does not treat missing physical bytes as zero logical activity.',sw,sr,bw,br,wr,rr)
    return L3IoReconciliation('mismatch','Mismatch','SGLang logical local-SSD L3 bytes and physical blktrace bytes differ beyond tolerance; check traced device, time-window alignment, dropped events, filesystem buffering, and blkparse completion-only filtering.',sw,sr,bw,br,wr,rr)

