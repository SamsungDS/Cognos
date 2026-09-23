"""
amoprof/layers/base.py — layer abstractions and a shared registry.

Introduces:
  • LayerModule       — abstract base every layer class inherits from.
  • LayerAnalysis     — dataclass returned by LayerModule.analyze().
  • LayerRegistry     — process-wide registry keyed by AIStackLayer.
  • register_layer    — class decorator that populates LayerRegistry.
  • ORDERED_LAYERS    — canonical presentation order for reports.

Design contract (Stage 1)
─────────────────────────
Each concrete layer owns:
  • the collectors registered against its AIStackLayer
    (queried via `CollectorRegistry.by_layer(self.LAYER)`), and
  • the analyze-time work that produces its section of the report.

Stage 1 wires only the abstractions and skeleton classes. cli._collect
and cli._analyze continue to drive collectors and chart generation via
the existing paths; behavior is unchanged. Later stages will migrate
those call sites to iterate `ORDERED_LAYERS` and delegate to each
layer's `collect()` / `stop()` / `analyze()`.
"""

from __future__ import annotations

import abc
import logging
import threading
from dataclasses import dataclass, field
from typing import Any

from ..base import AIStackLayer, BaseCollector, CollectorRegistry, CollectorSpec

log = logging.getLogger("amoprof.layers")


# ─── LayerAnalysis result ─────────────────────────────────────────────────────

@dataclass
class LayerAnalysis:
    """Per-layer analyze() output.

    Fields
    ──────
    layer            The AIStackLayer this analysis belongs to.
    name             Stable short id used as the report section slug
                     (e.g. "a1_l3_ssd"). Matches LayerModule.NAME.
    title            Human-facing section title (e.g. "A1 — L3 (SSD)").
    charts           list of {name, kind, payload} dicts, one per chart
                     the layer contributes. `kind` is "html" for a fully
                     rendered `<img>`/`<div>` snippet, or "b64" for a raw
                     base64 PNG string. Renderers key off `kind` to know
                     how to embed the payload.
    scenarios        Subset of ScenarioAnalyzer results that apply to
                     this layer.
    kpis             Flat scalar summary the enhancer / combined report
                     surfaces above the charts.
    warnings         Human-readable threshold breaches / anomalies.
    """

    layer:     AIStackLayer
    name:      str
    title:     str
    charts:    list[dict[str, Any]] = field(default_factory=list)
    scenarios: list[Any]            = field(default_factory=list)
    kpis:      dict[str, Any]       = field(default_factory=dict)
    warnings:  list[str]            = field(default_factory=list)


# ─── LayerModule abstract base ────────────────────────────────────────────────

class LayerModule(abc.ABC):
    """Abstract base every layer class inherits from.

    Contract
    ────────
      • Subclasses declare class attributes:
          LAYER: AIStackLayer      — enum member
          NAME:  str               — short slug used for the section id
          TITLE: str               — human-facing section title
      • Lifecycle is split into three explicit phases so callers control
        the wall-clock boundary of a run:
            build(args, ctx)   →  instantiate collectors, return dict
            start()            →  call collector.start() on each
            stop()             →  call collector.stop(); return summaries
        `collect(args, ctx)` is a convenience that runs build + start.
      • `analyze(raw_dir, metrics, scenarios)` produces this layer's
        section of the report. Subclasses must override; Stage 1 stubs
        return an empty `LayerAnalysis`.

    Cross-cutting concerns handled in the base
    ──────────────────────────────────────────
      • `optional` collectors gated by `args.<enable_flag>` truthiness.
        `enable_flag="pid"` (bpf/perf) means "enabled when args.pid".
        `enable_flag="sglang_port"` means "enabled when the port is set".
      • SSD-scoped collectors iterate once per `ctx["ssd_devices"]`;
        the first device keeps the unsuffixed name; subsequent devices
        get `<name>__<slug>` keys and `filename_suffix` in a per-device
        ctx clone so raw filenames stay unique.
      • PID-scoped collectors get skipped when `ctx["sglang_is_remote"]`
        is True (perf/bpf/nsys need local process attachment).
      • Layer-specific extras route through `_policy_gate(spec, ctx)`
        which subclasses override (e.g. A3 picks pcm vs amduprof_pcm
        based on `ctx["dram_tool"]`).
    """

    LAYER: AIStackLayer  # type: ignore[assignment]
    NAME:  str           = ""
    TITLE: str           = ""

    def __init__(self) -> None:
        # Collectors this layer owns for the current run. Populated by
        # build() and drained by stop(). Keyed the same way cli._collect
        # keys them today, so downstream code that references collectors
        # by name keeps working.
        self._collectors: dict[str, BaseCollector] = {}

    # ── Lifecycle ─────────────────────────────────────────────────────────
    def specs(self) -> list[CollectorSpec]:
        """CollectorSpecs registered against this layer, in registry order."""
        return CollectorRegistry.by_layer(self.LAYER)

    def build(self, args: Any, ctx: dict[str, Any]) -> dict[str, BaseCollector]:
        """Instantiate every collector belonging to this layer.

        Returns the {name → collector} mapping the layer now owns. Does
        NOT call `.start()`; callers invoke `start()` explicitly so the
        wall-clock boundary of the run stays in caller control.

        Subclasses rarely need to override this — instead override
        `_policy_gate(spec, ctx)` or `_resolve_pid_for_spec(spec, ctx)`.
        """
        built: dict[str, BaseCollector] = {}
        ssd_devices: list[str] = list(ctx.get("ssd_devices", []) or [])
        sglang_is_remote: bool = bool(ctx.get("sglang_is_remote", False))

        for spec in self.specs():
            if not self._flag_enabled(spec, args):
                continue
            if not self._policy_gate(spec, ctx):
                continue

            cls = CollectorRegistry.get(spec.layer, spec.name)
            if cls is None:
                log.debug("layer %s: no class for spec %s", self.NAME, spec.name)
                continue

            if spec.is_ssd_scoped:
                self._build_ssd_scoped(built, spec, cls, args, ctx, ssd_devices)
            elif spec.is_pid_scoped:
                if sglang_is_remote:
                    log.info("layer %s: skipping %s — SGLang server is remote",
                             self.NAME, spec.name)
                    continue
                self._build_pid_scoped(built, spec, cls, args, ctx)
            else:
                self._build_host_wide(built, spec, cls, args, ctx)

        self._collectors.update(built)
        return built

    def start(self) -> None:
        """Call `.start()` on every collector this layer built."""
        for name, collector in self._collectors.items():
            try:
                collector.start()
            except Exception as e:
                log.warning("layer %s: start(%s) failed: %s",
                            self.NAME, name, e)

    def collect(self, args: Any, ctx: dict[str, Any]) -> dict[str, BaseCollector]:
        """Convenience: build() + start(). Preserved for the LayerModule
        contract; cli.py uses build() + explicit start() to keep the
        collection start banner sequenced with wall-clock `t0`.
        """
        built = self.build(args, ctx)
        self.start()
        return built

    def stop(self) -> dict[str, dict[str, Any]]:
        """Stop every collector owned by this layer and return summaries."""
        summaries: dict[str, dict[str, Any]] = {}
        for name, collector in list(self._collectors.items()):
            try:
                s = collector.stop()
                summaries[name] = s if isinstance(s, dict) else {}
            except Exception as e:
                log.warning("layer %s: stop(%s) failed: %s", self.NAME, name, e)
                summaries[name] = {}
        return summaries

    # ── Build helpers (extension points) ──────────────────────────────────
    def _build_ssd_scoped(self,
                          built: dict[str, BaseCollector],
                          spec: CollectorSpec,
                          cls: type,
                          args: Any,
                          ctx: dict[str, Any],
                          ssd_devices: list[str]) -> None:
        """Iterate once per SSD device. First device keeps unsuffixed
        name; the rest get `__<slug>` keys and `filename_suffix` in ctx.
        """
        if not hasattr(cls, "for_device") or not ssd_devices:
            return
        for idx, dev in enumerate(ssd_devices):
            slug = _slug(dev)
            key      = spec.name if idx == 0 else f"{spec.name}__{slug}"
            file_sfx = ""        if idx == 0 else slug
            dev_ctx = dict(ctx)
            dev_ctx["filename_suffix"] = file_sfx
            try:
                built[key] = cls.for_device(dev, args, dev_ctx)
            except Exception as e:
                log.warning("layer %s: for_device(%s, %s) failed: %s",
                            self.NAME, spec.name, dev, e)

    def _build_pid_scoped(self,
                          built: dict[str, BaseCollector],
                          spec: CollectorSpec,
                          cls: type,
                          args: Any,
                          ctx: dict[str, Any]) -> None:
        pid = self._resolve_pid_for_spec(spec, ctx)
        if pid is None or not hasattr(cls, "for_pid"):
            return
        try:
            built[spec.name] = cls.for_pid(pid, args, ctx)
        except Exception as e:
            log.warning("layer %s: for_pid(%s, pid=%s) failed: %s",
                        self.NAME, spec.name, pid, e)

    def _build_host_wide(self,
                         built: dict[str, BaseCollector],
                         spec: CollectorSpec,
                         cls: type,
                         args: Any,
                         ctx: dict[str, Any]) -> None:
        if not hasattr(cls, "for_host"):
            return
        try:
            built[spec.name] = cls.for_host(args, ctx)
        except Exception as e:
            log.warning("layer %s: for_host(%s) failed: %s",
                        self.NAME, spec.name, e)

    # ── Extension hooks (override in subclasses) ──────────────────────────
    def _flag_enabled(self, spec: CollectorSpec, args: Any) -> bool:
        """Return True when `spec.enable_flag` is truthy on args (or the
        spec is not optional). Handles the two non-boolean flags in the
        current spec set — `pid` (int) and `sglang_port` (int).
        """
        if not spec.optional:
            return True
        if not spec.enable_flag:
            return False
        return bool(getattr(args, spec.enable_flag, None))

    def _policy_gate(self, spec: CollectorSpec, ctx: dict[str, Any]) -> bool:
        """Layer-specific admission gate beyond enable_flag. Default: allow.
        Subclasses (A3DramLayer) override to pick between mutually
        exclusive collectors that share an enable_flag.
        """
        return True

    def _resolve_pid_for_spec(self, spec: CollectorSpec,
                              ctx: dict[str, Any]) -> "int | None":
        """Return the PID to attach for a pid-scoped collector. Default
        uses `ctx["pid"]`. A4 overrides so nsys can honor `--nsys-pid`
        independently of the sglang PID used by perf/bpf.
        """
        return ctx.get("pid")

    # ── Analyze helpers (chart rendering) ─────────────────────────────────
    def _render_chart(self,
                      analysis: LayerAnalysis,
                      name: str,
                      fn: Any,
                      *fn_args: Any,
                      kind: str = "b64") -> None:
        """Call a chart_* function and append its output to `analysis`.

        Silently drops empty results (empty string = "no data") and
        catches exceptions so one broken chart doesn't kill the run.
        `kind` is "b64" for base64 PNGs and "html" for HTML div fragments;
        renderers key off it to know how to embed the payload.
        """
        try:
            payload = fn(*fn_args)
        except Exception as e:
            log.warning("layer %s: chart %s failed: %s", self.NAME, name, e)
            analysis.warnings.append(f"chart {name} failed: {e}")
            return
        if not payload:
            return
        analysis.charts.append({"name": name, "kind": kind, "payload": payload})

    # ── Analyze ───────────────────────────────────────────────────────────
    @abc.abstractmethod
    def analyze(self,
                raw_dir: Any,
                metrics: Any,
                scenarios: dict[str, Any] | None = None,
                bottlenecks: list | None = None) -> LayerAnalysis:
        """Produce this layer's section of the analyze-time report.

        Parameters
        ──────────
        raw_dir      Path to the run's raw/ directory (where collectors
                     wrote their sidecar files).
        metrics      `amoprof.report.amoprof.Metrics` object built from
                     `extract_metrics(load_raw_dir(raw_dir))`. Passed
                     through so each layer can reach into the shared
                     frames without re-parsing.
        scenarios    Optional {scenario_id → ScenarioResult} filtered to
                     this layer's slice; None until Stage 5 lands.
        bottlenecks  Output of `score_bottlenecks(metrics)`, computed
                     once by the orchestrator. Only CrossLayer needs it
                     today (feeds chart_bottleneck_radar). Other layers
                     ignore it.

        Return
        ──────
        A `LayerAnalysis` populated with charts, kpis, warnings, and
        the scenario subset relevant to this layer.
        """


# ─── LayerRegistry ────────────────────────────────────────────────────────────

@dataclass
class _LayerEntry:
    cls: type[LayerModule]


class LayerRegistry:
    """Process-wide registry keyed by AIStackLayer.

    Populated at import time via `@register_layer` on the class body.
    cli._collect / cli._analyze query it to enumerate layers in canonical
    presentation order.
    """

    _entries: dict[AIStackLayer, _LayerEntry] = {}
    _lock = threading.Lock()

    @classmethod
    def register(cls, entry_cls: type[LayerModule]) -> type[LayerModule]:
        layer = getattr(entry_cls, "LAYER", None)
        if not isinstance(layer, AIStackLayer):
            raise TypeError(
                f"{entry_cls.__name__} must declare LAYER: AIStackLayer"
                " before it can be registered."
            )
        with cls._lock:
            if layer in cls._entries:
                log.debug("re-registering layer %s (was %s, now %s)",
                          layer.value,
                          cls._entries[layer].cls.__name__,
                          entry_cls.__name__)
            cls._entries[layer] = _LayerEntry(cls=entry_cls)
        return entry_cls

    @classmethod
    def get(cls, layer: AIStackLayer) -> type[LayerModule] | None:
        entry = cls._entries.get(layer)
        return entry.cls if entry else None

    @classmethod
    def all(cls) -> list[type[LayerModule]]:
        """All registered layer classes, in the order they were registered."""
        return [e.cls for e in cls._entries.values()]

    @classmethod
    def ordered(cls) -> list[type[LayerModule]]:
        """Layer classes in canonical presentation order (ORDERED_LAYERS).

        Any registered layers not present in ORDERED_LAYERS are appended
        in registration order so a stray addition never silently drops.
        """
        seen: set[AIStackLayer] = set()
        result: list[type[LayerModule]] = []
        for layer in ORDERED_LAYERS:
            entry = cls._entries.get(layer)
            if entry is None:
                continue
            result.append(entry.cls)
            seen.add(layer)
        for layer, entry in cls._entries.items():
            if layer not in seen:
                result.append(entry.cls)
        return result


def register_layer(cls: type[LayerModule]) -> type[LayerModule]:
    """Class decorator: register the layer in LayerRegistry.

    Usage
    ─────
        @register_layer
        class A1L3SsdLayer(LayerModule):
            LAYER = AIStackLayer.A1_L3_SSD
            NAME  = "a1_l3_ssd"
            TITLE = "A1 — L3 (SSD)"
            def analyze(self, raw_dir, metrics, scenarios=None):
                ...
    """
    return LayerRegistry.register(cls)


# ─── Presentation order ───────────────────────────────────────────────────────
#
# CROSS is a synthetic layer for charts that overlay two or more real layers
# (cross_layer_kpi, kvssd_cross_layer, kv_lba_dram_correlation). It is not an
# AIStackLayer member; concrete CrossLayer overrides `LAYER` with a stable
# sentinel to keep the LayerRegistry contract intact.

ORDERED_LAYERS: list[AIStackLayer] = [
    AIStackLayer.A5_APP,
    AIStackLayer.A4_GPU_HBM,
    AIStackLayer.A3_DRAM,
    AIStackLayer.A2_NVME_DRIVER,
    AIStackLayer.A1_L3_SSD,
    AIStackLayer.CROSS,
]
# NOTE: AIStackLayer.HOST_OS is retained on the enum for backward compat
# but is intentionally absent from ORDERED_LAYERS — every collector that
# previously mapped to HOST_OS now maps to A3_DRAM (see aiOpsArch.pptx).


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _slug(device: str) -> str:
    """Mirror cli._ssd_device_slug without importing cli (avoids cycles).

    Only used by the default collect() implementation for multi-SSD keying.
    Any hyphens/slashes in the device path become underscores.
    """
    return (
        device.strip()
              .lstrip("/")
              .replace("/", "_")
              .replace("-", "_")
    )


__all__ = [
    "LayerAnalysis",
    "LayerModule",
    "LayerRegistry",
    "ORDERED_LAYERS",
    "register_layer",
]
