"""
amoprof/base.py — collector abstractions and a shared registry.

Introduces:
  • AIStackLayer         — AMOprof's canonical layer taxonomy (A1..A5, HOST_OS).
  • CollectorSpec        — metadata describing one collector (layer, name flags).
  • BaseCollector        — abstract base with the shared collector protocol.
  • CollectorRegistry    — process-wide registry keyed by (layer, name).

Every collector class inherits from BaseCollector and declares its `SPEC`; the
class-body `@register_collector` decorator adds it to the registry so that
cli/service can iterate collectors by layer instead of hard-coding a dict
literal.

Backwards-compatibility contract:
  • Existing collectors keep every public method and attribute they had before
    the refactor (start / stop / .samples / .raw_samples / etc.).
  • BaseCollector.start()/stop() and .summarise()/.series() are thin defaults
    that call the subclass's own implementations if present. Subclasses only
    need to override the abstract methods they don't already provide.
"""

from __future__ import annotations

import abc
import logging
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

log = logging.getLogger("amoprof.base")


# ─── AI-stack layer taxonomy ─────────────────────────────────────────────────

class AIStackLayer(Enum):
    """AMOprof's AI-stack layer identifiers.

    Names match the report section prefixes (A1..A5) so the layer is
    self-documenting.  HOST_OS covers OS-level collectors that don't map to
    a specific A-layer (vmstat, swap, discard, power).
    """

    A1_L3_SSD       = "A1_L3_SSD"          # Local NVMe/SSD hardware + SMART
    A2_NVME_DRIVER  = "A2_NVME_DRIVER"     # Kernel block/NVMe driver (sysfs, blktrace, biosnoop)
    A3_DRAM         = "A3_DRAM"            # Host DRAM bandwidth (AMDuProf / Intel PCM / perf IMC)
    A4_GPU_HBM      = "A4_GPU_HBM"         # GPU utilisation, HBM, NVLink, PCIe
    A5_APP          = "A5_APP"             # Application-layer telemetry (SGLang, request latency)
    HOST_OS         = "HOST_OS"            # Host OS counters (vmstat, swap, power)
    CROSS           = "CROSS"              # Synthetic layer for charts that overlay 2+ real layers;
                                           # no collector registers against it — used by amoprof.layers.CrossLayer.


# ─── CollectorSpec metadata ──────────────────────────────────────────────────

@dataclass(frozen=True)
class CollectorSpec:
    """Static metadata for a collector class.

    Fields
    ──────
    name            Short lowercase identifier used as the summary key
                    (e.g. "iostat", "smart", "blktrace"). Must be unique
                    within a layer.
    layer           Which AIStackLayer this collector belongs to.
    is_ssd_scoped   True when the collector must be run once per SSD device
                    (iostat/smart/ssd_hw/…). False for host-wide collectors
                    (gpu/dram/vmstat/power/…).
    is_pid_scoped   True when the collector attaches to a target PID
                    (perf/bpf/nsys). Instantiated via `for_pid(pid, args, ctx)`.
    optional        True when the collector must be explicitly enabled via
                    an --enable-* flag or sglang_port/pid. Always-on
                    collectors have optional=False.
    enable_flag     argparse-style attribute name that toggles the collector
                    (e.g. "enable_blktrace"). Empty for always-on collectors.
    description     Short human-facing sentence used in --help style output.
    """

    name: str
    layer: AIStackLayer
    is_ssd_scoped: bool = False
    is_pid_scoped: bool = False   # collector attaches to a PID (perf/bpf/nsys)
    optional: bool = False
    enable_flag: str = ""
    description: str = ""


# ─── BaseCollector abstract base class ───────────────────────────────────────

class BaseCollector(abc.ABC):
    """Abstract base every AMOprof collector inherits from.

    Contract
    ────────
      • Subclasses declare a class attribute `SPEC: CollectorSpec`.
      • Subclasses implement `start()` and `stop()`. `stop()` returns a
        summary dict (empty dict = "no data").
      • Subclasses may optionally implement `sanity_check()` (returns
        (ok: bool, reason: str)); the default returns (True, "").
      • Subclasses may optionally override `series()` to return a list of
        per-sample rows; the default inspects common attributes (samples,
        raw_samples, _samples) to preserve backward compatibility.

    Threading
    ─────────
    BaseCollector does not itself spawn a thread. Subclasses that need to
    poll in the background continue to manage their own threads (as they do
    today). This keeps the abstraction thin and avoids re-plumbing every
    collector's lifecycle.
    """

    # Subclasses must set this. Access via cls.SPEC or self.SPEC.
    SPEC: CollectorSpec  # type: ignore[assignment]

    # ── Lifecycle ─────────────────────────────────────────────────────────
    @abc.abstractmethod
    def start(self) -> None:
        """Begin collecting. Must be safe to call from any thread."""

    @abc.abstractmethod
    def stop(self) -> dict[str, Any]:
        """Stop collecting; return the per-collector summary dict.

        Callers write this dict to `<name>_summary.json` and merge it into
        `summary.json :: summary[<key>]`.  An empty dict is treated as
        "collector had nothing to report" — never as an error.
        """

    # ── Diagnostics ───────────────────────────────────────────────────────
    def sanity_check(self) -> tuple[bool, str]:
        """Return (ok, reason). Default: no-op pass.

        Subclasses can override to check for required binaries, kernel
        modules, sysfs paths, or capabilities. The reason is shown to the
        user when ok=False.
        """
        return True, ""

    # ── Time-series export ────────────────────────────────────────────────
    def series(self) -> list[dict[str, Any]]:
        """Return per-sample rows suitable for CSV/JSONL export.

        Default implementation looks for common attribute names used across
        the existing collector zoo — this preserves the exact behavior of
        cli._series_from_obj so that migrating a collector to BaseCollector
        is a pure additive change with no data-shape churn.
        """
        for attr in ("samples", "raw_samples"):
            v = getattr(self, attr, None)
            if isinstance(v, list):
                return [dict(r) for r in v if isinstance(r, dict)]
        v = getattr(self, "_samples", None)
        if isinstance(v, list):
            rows: list[dict[str, Any]] = []
            for item in v:
                if isinstance(item, dict):
                    rows.append(dict(item))
                elif isinstance(item, tuple) and len(item) == 3:
                    tag, ts, payload = item
                    if isinstance(payload, dict):
                        d: dict[str, Any] = {"tag": tag, "ts": ts}
                        d.update(payload)
                        rows.append(d)
            return rows
        return []

    # ── Convenience ───────────────────────────────────────────────────────
    @classmethod
    def collector_name(cls) -> str:
        return getattr(cls, "SPEC").name

    @classmethod
    def layer(cls) -> AIStackLayer:
        return getattr(cls, "SPEC").layer

    @classmethod
    def is_ssd_scoped(cls) -> bool:
        return bool(getattr(cls, "SPEC").is_ssd_scoped)

    @classmethod
    def is_pid_scoped(cls) -> bool:
        return bool(getattr(cls, "SPEC").is_pid_scoped)


# ─── CollectorRegistry ───────────────────────────────────────────────────────

@dataclass
class _RegistryEntry:
    cls: type
    spec: CollectorSpec


class CollectorRegistry:
    """Process-wide registry keyed by (layer, name).

    Populated at import time via `@register_collector` on the class body.
    cli/service query it to enumerate collectors, filter by SSD-scoped vs
    host-wide, and instantiate them.
    """

    _entries: dict[tuple[AIStackLayer, str], _RegistryEntry] = {}
    _lock = threading.Lock()

    @classmethod
    def register(cls, entry_cls: type) -> type:
        spec = getattr(entry_cls, "SPEC", None)
        if not isinstance(spec, CollectorSpec):
            raise TypeError(
                f"{entry_cls.__name__} must declare SPEC: CollectorSpec"
                " before it can be registered."
            )
        key = (spec.layer, spec.name)
        with cls._lock:
            if key in cls._entries:
                # Re-registration is OK (module reloads in tests, notebooks).
                # We overwrite so the newest definition wins.
                log.debug("re-registering collector %s in layer %s", spec.name, spec.layer.value)
            cls._entries[key] = _RegistryEntry(cls=entry_cls, spec=spec)
        return entry_cls

    @classmethod
    def get(cls, layer: AIStackLayer, name: str) -> type | None:
        entry = cls._entries.get((layer, name))
        return entry.cls if entry else None

    @classmethod
    def find(cls, name: str) -> type | None:
        """Return the collector class for a bare name (first match across layers)."""
        for (_layer, _name), entry in cls._entries.items():
            if _name == name:
                return entry.cls
        return None

    @classmethod
    def all(cls) -> list[CollectorSpec]:
        return [e.spec for e in cls._entries.values()]

    @classmethod
    def by_layer(cls, layer: AIStackLayer) -> list[CollectorSpec]:
        return [e.spec for e in cls._entries.values() if e.spec.layer == layer]

    @classmethod
    def ssd_scoped(cls) -> list[CollectorSpec]:
        return [e.spec for e in cls._entries.values() if e.spec.is_ssd_scoped]

    @classmethod
    def pid_scoped(cls) -> list[CollectorSpec]:
        return [e.spec for e in cls._entries.values() if e.spec.is_pid_scoped]

    @classmethod
    def host_wide(cls) -> list[CollectorSpec]:
        """Collectors that are neither SSD- nor PID-scoped.

        These are per-host singletons: gpu, dram, vmstat, power, …
        Instantiated via `for_host(args, ctx)` per collector class.
        """
        return [e.spec for e in cls._entries.values()
                if not e.spec.is_ssd_scoped and not e.spec.is_pid_scoped]


def register_collector(cls: type) -> type:
    """Class decorator: register the collector class in CollectorRegistry.

    Usage
    ─────
        @register_collector
        class IostatMonitor(BaseCollector):
            SPEC = CollectorSpec(
                name="iostat",
                layer=AIStackLayer.A2_NVME_DRIVER,
                is_ssd_scoped=True,
                description="iostat -x per-device bandwidth/IOPS/latency",
            )
            def start(self): ...
            def stop(self) -> dict: ...
    """
    return CollectorRegistry.register(cls)


__all__ = [
    "AIStackLayer",
    "CollectorSpec",
    "BaseCollector",
    "CollectorRegistry",
    "register_collector",
]
