"""
amoprof/prometheus_source.py — Fetch timeseries data from a Prometheus
server via /api/v1/query_range and emit the canonical amoprof CSV/JSON
files into a raw/ directory.

This is the analyze-side counterpart to the live SGLangMetricsSampler
collector. It lets users build a report from historical Prometheus
data instead of (or in addition to) a local AMOprof collect run.

Three modes are supported:

  1. Prometheus-only — fetch everything from a Prom server.
     amoprof analyze --prometheus http://host:9090 --start -1h --end now

  2. Local-only — re-analyze a previous collect run (existing behaviour).
     amoprof analyze --run-dir results/metrics_run_20260514

  3. Merge — combine both. Conflict handling is controlled by
     --prefer. With --prefer prometheus, every canonical metric file that
     Prometheus can produce is refreshed from the requested Prometheus
     window, and the local run directory is used only for metric families
     Prometheus did not return (for example blktrace/SMART/vendor PMU data).
     With --prefer local, existing local files are kept and Prometheus fills
     only missing canonical files.
     amoprof analyze --run-dir results/foo --prometheus http://host:9090 --prefer prometheus

The actual Prometheus fetch happens via the bundled amoprof report's
collect_from_prometheus_api(), which we import dynamically because
that module also pulls matplotlib at module-import time and we don't
want that cost for callers who never use Prometheus.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("amoprof.prom_source")


# ─── Time parsing ────────────────────────────────────────────────────────────
def parse_time_arg(s: str, now: float | None = None) -> float:
    """Parse a time argument into a Unix timestamp.

    Accepts:
      - Empty string         → 0 (caller decides default)
      - Literal 'now'        → current time
      - Unix timestamp       → '1715623200' or '1715623200.5'
      - ISO datetime         → '2026-04-25T10:00:00' / '2026-04-25 10:00:00'
                               / '2026-04-25' (treated as UTC)
      - Relative offset      → '-1h', '-30m', '-2d' OR '1h', '30m', '2d'
                               (both forms treated as "N units ago";
                               leading dash is optional).

    Returns 0 for unparseable / empty strings so the caller can supply
    a fallback. Raises ValueError only for clearly malformed offsets.
    """
    if not s:
        return 0.0
    s = s.strip()
    if s.lower() in ("now", ""):
        return now if now is not None else time.time()
    if now is None:
        now = time.time()
    # Unix timestamp (10+ digits, optional decimal).  Match BEFORE the
    # relative-offset regex so a bare integer like '1715623200' isn't
    # mis-parsed as "1715623200 seconds ago".
    if re.match(r"^\d{10,}(\.\d+)?$", s):
        return float(s)
    # Relative offset: -<n>{h,m,d,s} OR <n>{h,m,d,s} (dash optional).
    # Both `-168h` and `168h` mean "168 hours ago" so operators don't have
    # to remember the leading dash — mirrors Grafana / Prometheus URL params.
    m = re.match(r"^-?(\d+)([hmds])$", s)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        return now - n * {"h": 3600, "m": 60, "d": 86400, "s": 1}[unit]
    # ISO datetime.  A naive datetime is interpreted in the LOCAL timezone of
    # the machine running analyze, then converted to UTC for the query.
    #
    # Prometheus stores everything in UTC, but an operator asking for
    # "17:00 to 18:45" means their own wall clock, not UTC.  Treating naive
    # input as UTC silently profiled the wrong window — seven hours off in
    # US/Pacific — and the mistake is invisible in the output because the
    # query succeeds and returns real data for the wrong hours.
    #
    # An explicit offset or a trailing Z always wins; only naive input is
    # localised.  Set AMOPROF_NAIVE_TZ=utc to restore the old behaviour.
    iso = s.strip()
    if iso.endswith("Z"):
        iso = iso[:-1] + "+00:00"
    _naive_utc = str(os.environ.get("AMOPROF_NAIVE_TZ", "")).strip().lower() in (
        "utc", "z", "gmt")
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=(timezone.utc if _naive_utc else None))
            if not _naive_utc:
                dt = dt.astimezone()          # attach the local zone
        return dt.timestamp()
    except ValueError:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            _d = datetime.strptime(s, fmt)
            _d = (_d.replace(tzinfo=timezone.utc) if _naive_utc else _d.astimezone())
            return _d.timestamp()
        except ValueError:
            pass
    return 0.0


def parse_labels_arg(label_args: list[str] | None) -> dict[str, str]:
    """Parse ['key1=val1', 'key2=val2'] into a dict."""
    out: dict[str, str] = {}
    for item in (label_args or []):
        item = item.strip().strip('"').strip("'")
        if "=" in item:
            k, _, v = item.partition("=")
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def parse_duration_arg_s(value: str | int | float | None) -> int | None:
    """Parse a Prometheus rate/window duration into seconds.

    Accepts:
      - None / empty / 0 -> None, meaning caller default
      - integer/float seconds, e.g. 300 or "300"
      - Prometheus-style single durations: "60s", "5m", "1h", "2d"

    This intentionally supports one unit at a time to avoid surprising
    interpretations. Use 90m instead of 1h30m.
    """
    if value in (None, "", 0, "0"):
        return None
    if isinstance(value, (int, float)):
        out = int(value)
        if out <= 0:
            raise ValueError(f"duration must be > 0 seconds, got {value!r}")
        return out
    text = str(value).strip().lower()
    if not text:
        return None
    if re.match(r"^\d+(\.\d+)?$", text):
        out = int(float(text))
        if out <= 0:
            raise ValueError(f"duration must be > 0 seconds, got {value!r}")
        return out
    m = re.match(r"^(\d+(?:\.\d+)?)(ms|s|m|h|d)$", text)
    if not m:
        raise ValueError(
            f"invalid duration {value!r}; use seconds or one unit like 300s, 5m, 1h")
    n = float(m.group(1))
    unit = m.group(2)
    mult = {"ms": 0.001, "s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
    out = int(round(n * mult))
    if out <= 0:
        raise ValueError(f"duration must be > 0 seconds, got {value!r}")
    return out


# ─── Bundled-amoprof loader ─────────────────────────────────────────────────
# The bundled report at amoprof/report/amoprof.py defines the actual
# Prometheus query helpers. Loading it as a sibling module would shadow our
# own `amoprof` package, so we load it under a distinct name via importlib.
_REPORT_MODULE = None


def _load_bundled_report():
    global _REPORT_MODULE
    if _REPORT_MODULE is not None:
        return _REPORT_MODULE
    import importlib.util as _ilu
    report_py = Path(__file__).resolve().parent / "report" / "amoprof.py"
    if not report_py.exists():
        raise RuntimeError(f"bundled amoprof report not found at {report_py}")
    # Use a name that can't collide with our package
    spec = _ilu.spec_from_file_location("amoprof_bundled_report", report_py)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to build importlib spec for {report_py}")
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _REPORT_MODULE = mod
    return mod


# ─── Target discovery ───────────────────────────────────────────────────────
def discover_targets(prom_base_url: str, hostname: str = "") -> dict[str, list[str]]:
    """Return {job: [instance, ...]} from /api/v1/targets.

    Used by `amoprof analyze --prometheus URL --list-targets`.
    """
    mod = _load_bundled_report()
    return mod._prom_discover_targets(prom_base_url, hostname)


# ─── Main fetch ──────────────────────────────────────────────────────────────
# Files the bundled collect_from_prometheus_api can produce.
CANONICAL_FILES = (
    "sglang_timeseries.csv",
    "sglang_summary.json",
    "sglang_percentiles_timeseries.json",
    "gpu_timeseries.csv",
    "gpu_summary.json",
    "nvme_driver_timeseries.csv",
    "vmstat_timeseries.csv",
    "power_timeseries.csv",
)

# Metric families that Prometheus can own.  In merge mode with
# --prefer prometheus these files must come from the requested Prometheus
# window whenever Prometheus returns data.  The local run directory is used
# only as a fallback for files Prometheus does not produce.  Non-Prometheus
# local-only artifacts (blktrace raw events, SMART, AMDuProf PCM, biosnoop,
# setup_details, benchmark summaries, etc.) are intentionally left in place.
PROMETHEUS_OWNED_FILES = set(CANONICAL_FILES)

SOURCE_POLICY_FILE = "amoprof_source_policy.json"


def fetch_from_prometheus(
    prom_url: str,
    output_dir: Path,
    start: str = "",
    end: str = "",
    step_s: int = 15,
    percentile_rate_window: str | int | float | None = None,
    instance: str = "",
    job: str = "",
    extra_labels: dict[str, str] | None = None,
    label: str = "prom",
    nvme_device: str = "",
    server_type: str = "auto",
    l35_instance: str = "",
    l35_job: str = "",
    l35_storage_instance: str = "",
    l35_storage_job: str = "",
    l35_nvme_device: str = "",
    model_config: "dict | None" = None,
) -> dict[str, Any]:
    """Pull timeseries from a Prometheus server and write canonical CSVs.

    Args:
      prom_url     : Prometheus base URL (e.g. http://host:9090)
      output_dir   : Destination raw/ directory. Will be created.
      start, end   : Time range strings (see parse_time_arg).
                     Empty → default to last 1 hour.
      step_s       : query_range resolution (seconds).
      percentile_rate_window:
                     Optional histogram_quantile rate() window for percentile
                     timeseries, e.g. "5m" or 300. Default: max(60s, 4*step_s).
      l35_instance : Instance of the L3.5 store exporter (Mooncake / AI Memory
                     Node / 3FS) when it runs on a DIFFERENT host than the GPU
                     node.  Target discovery is scoped to the GPU hostname, so
                     a remote store is otherwise never found and its metrics
                     are filtered out by `instance`.
      l35_job      : Prometheus job name of that exporter, if it is not one of
                     mooncake / mooncake_store / mooncake_master.
      instance     : Filter to {instance="..."} on every PromQL query.
      job          : Filter to {job="..."} on every PromQL query.
      extra_labels : Additional {key:value} label filters (ANDed).
      label        : Run label for output filenames.
      nvme_device  : NVMe device name (e.g. "nvme0n1", or "nvme6c6n1") to
                     scope the GPU host's node_disk_* metrics to one device.
      l35_nvme_device:
                     The same, for the L3.5 memory node's own block device.
                     Without it every node_disk_* query on that node is
                     averaged across its NVMe namespaces, which dilutes
                     bandwidth, IOPS and queue depth by the number of idle
                     devices.  On a multipath namespace prefer the
                     per-controller path name (nvmeXcYnZ): the kernel accounts
                     the queue-depth integral there, not on the head.

    Returns a dict describing what was written, suitable for logging.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load the bundled amoprof report module — it owns the actual
    # collect_from_prometheus_api implementation.
    try:
        mod = _load_bundled_report()
        collect_from_prometheus_api = mod.collect_from_prometheus_api
    except Exception as e:
        raise RuntimeError(
            "Unable to load the bundled amoprof report module: "
            f"{e!r}. Ensure amoprof/report/amoprof.py is present."
        ) from e

    now_ts = time.time()
    # Fail loud when a non-empty --start / --end failed to parse — silently
    # falling back to the 1-hour default caused a report bug where
    # --start 168h (missing leading dash, doesn't match the -168h regex)
    # was interpreted as 1-hour-ago instead of 7-days-ago.  A non-empty
    # arg that returns 0 from parse_time_arg is definitionally unparseable.
    _end_parsed = parse_time_arg(end, now_ts)
    if end and _end_parsed == 0.0:
        raise ValueError(
            f"Could not parse --end={end!r}.  Accepted forms: 'now', a Unix "
            f"timestamp, an ISO datetime (2026-04-25T10:00:00), or a "
            f"relative offset like '30m' / '6h' / '2d' (leading dash optional).")
    t_end = _end_parsed or now_ts
    _start_parsed = parse_time_arg(start, now_ts)
    if start and _start_parsed == 0.0:
        raise ValueError(
            f"Could not parse --start={start!r}.  Accepted forms: a Unix "
            f"timestamp, an ISO datetime (2026-04-25T10:00:00), or a "
            f"relative offset like '30m' / '6h' / '168h' / '2d' "
            f"(leading dash optional).")
    t_start = _start_parsed or (t_end - 3600)

    if t_start >= t_end:
        raise ValueError(
            f"Empty time range: start={t_start} >= end={t_end}. "
            "Check --start / --end arguments."
        )

    window_s = t_end - t_start

    # Prometheus /api/v1/query_range caps at --query.max-samples (default
    # 11,000 points per series). Passing (window/step) above that limit
    # makes the server return HTTP 422 and every series comes back empty,
    # which shows up in the report as "charts missing data for the full
    # window". Auto-bump step to keep points/series ≤ 10,000 (buffer for
    # rate() window alignment). We announce the auto-bump loudly so it's
    # obvious why the resolution is coarser than requested.
    _requested_step_s = int(step_s)
    _MAX_POINTS_PER_SERIES = 10_000
    _min_step = int((window_s // _MAX_POINTS_PER_SERIES) + 1)
    if _min_step > _requested_step_s:
        # Round up to a "nice" step boundary so downstream rate-window math
        # produces round numbers (30, 60, 120, 300, 600, 900, 1800, 3600).
        _NICE_STEPS = (30, 60, 120, 300, 600, 900, 1800, 3600, 7200)
        _bumped_step = next((s for s in _NICE_STEPS if s >= _min_step), _min_step)
        log.warning(
            "Prometheus fetch: --prom-step %ds would exceed the server's "
            "per-series sample cap for a %.0fh window "
            "(%.0f points/series > ~%d limit). "
            "Auto-bumping to --prom-step %ds. "
            "Pass --prom-step %d or higher explicitly to silence this warning.",
            _requested_step_s, window_s / 3600.0,
            window_s / max(_requested_step_s, 1), _MAX_POINTS_PER_SERIES,
            _bumped_step, _bumped_step)
        step_s = _bumped_step

    resolved_rate_window_s = parse_duration_arg_s(percentile_rate_window)
    if resolved_rate_window_s is None:
        resolved_rate_window_s = max(60, int(step_s) * 4)
    log.info("Prometheus fetch: %s  window=%.0fs  step=%ds  percentile_rate_window=%ds  instance=%r  job=%r",
             prom_url, window_s, step_s, resolved_rate_window_s, instance or "(any)", job or "(any)")

    labels = dict(extra_labels or {})
    if nvme_device:
        labels.setdefault("nvme_device", nvme_device)

    # Snapshot existing files so we can tell what got produced.
    before = {f.name for f in output_dir.iterdir() if f.is_file()}

    data = collect_from_prometheus_api(
        prom_base_url=prom_url,
        start_time=t_start,
        end_time=t_end,
        step_s=step_s,
        label=label,
        output_dir=output_dir,
        instance=instance,
        job=job,
        extra_labels=labels,
        server_type=server_type,
        l35_instance=l35_instance,
        l35_job=l35_job,
        l35_storage_instance=l35_storage_instance,
        l35_storage_job=l35_storage_job,
        l35_nvme_device=l35_nvme_device,
        # The caller's already-read --model-path config, so the fetch can
        # write raw/model_config.json itself rather than depending on which
        # step wrote it first.
        model_config=model_config,
    )

    # The collector may auto-detect the backend when server_type="auto"; reuse
    # its decision (persisted in sglang_summary.json) for the percentile fetch
    # so both halves agree on which metric names to query.
    resolved_server_type = server_type
    if (server_type or "auto").lower() == "auto":
        try:
            _sg0 = output_dir / "sglang_summary.json"
            if _sg0.exists():
                resolved_server_type = (
                    json.loads(_sg0.read_text()).get("server_type")
                    or server_type)
        except Exception:
            resolved_server_type = server_type

    after = {f.name for f in output_dir.iterdir() if f.is_file()}
    new_files = sorted(after - before)
    overwritten = sorted(after & before)

    # Fetch percentile summary + per-tick percentile timeseries from
    # histogram buckets. These give true per-request P50/P90/P99 (matching
    # what bench_serving prints) — distinct from the per-tick gauge means
    # already in sglang_summary.json.
    pct_summary: dict = {}
    pct_ts: dict = {}
    try:
        from .percentiles import (
            fetch_percentile_summary, fetch_percentile_timeseries,
        )
        pct_summary = fetch_percentile_summary(
            prom_url, t_start, t_end,
            instance=instance, job=job, extra_labels=labels,
            server_type=resolved_server_type)
        if pct_summary:
            # Merge percentile fields into sglang_summary.json if present
            sg_path = output_dir / "sglang_summary.json"
            if sg_path.exists():
                try:
                    sg = json.loads(sg_path.read_text())
                except Exception:
                    sg = {}
            else:
                sg = {}
            sg.update(pct_summary)
            sg["percentile_rate_window_s"] = resolved_rate_window_s
            sg["percentile_rate_window_source"] = (
                f"--prom-rate-window {percentile_rate_window}"
                if percentile_rate_window not in (None, "", 0, "0")
                else "default max(60s, 4 * --prom-step)"
            )
            sg["cache_hit_calc_method"] = sg.get(
                "cache_hit_calc_method", "histogram_quantile_window")
            sg_path.write_text(json.dumps(sg, indent=2, default=str))
            log.info("Merged %d percentile fields into sglang_summary.json",
                     len(pct_summary))

        pct_ts = fetch_percentile_timeseries(
            prom_url, t_start, t_end, step_s=step_s,
            rate_window_s=resolved_rate_window_s,
            instance=instance, job=job, extra_labels=labels,
            server_type=resolved_server_type)
        if pct_ts:
            pts_path = output_dir / "sglang_percentiles_timeseries.json"
            # Filter out None values for cleaner JSON
            def _clean(d):
                if isinstance(d, dict):
                    return {k: _clean(v) for k, v in d.items()}
                if isinstance(d, list):
                    return [None if v is None else v for v in d]
                return d
            pts_path.write_text(json.dumps(_clean(pct_ts), indent=2, default=str))
            log.info("Wrote percentile timeseries (%d metrics) → %s",
                     len(pct_ts), pts_path.name)
    except Exception as e:
        log.warning("percentile fetch failed: %s", e)

    return {
        "prom_url":    prom_url,
        "start":       t_start,
        "end":         t_end,
        "step_s":      step_s,
        "percentile_rate_window_s": resolved_rate_window_s,
        "percentile_rate_window_source": (
            f"--prom-rate-window {percentile_rate_window}"
            if percentile_rate_window not in (None, "", 0, "0")
            else "default max(60s, 4 * --prom-step)"
        ),
        "instance":    instance,
        "job":         job,
        "labels":      labels,
        "new_files":   sorted(set(new_files) | {f.name for f in output_dir.iterdir() if f.is_file()} - before),
        "overwritten": overwritten,
        "percentile_fields": list(pct_summary.keys()),
        "percentile_timeseries_metrics": list(pct_ts.keys()),
        "data_keys":   sorted(data.keys()) if isinstance(data, dict) else [],
    }


# ─── Merge: fill gaps in local raw/ with Prometheus data ────────────────────
def merge_prometheus_into_local(
    prom_url: str,
    local_raw_dir: Path,
    prefer: str = "local",
    **fetch_kwargs: Any,
) -> dict[str, Any]:
    """Combine a local raw/ dir with a Prometheus fetch.

    Source precedence is intentionally strict:

      * prefer == "prometheus": every Prometheus-owned canonical file is copied
        from the requested Prometheus window when Prometheus returns a non-empty
        file.  Local raw/ is used only for files Prometheus did not return and
        for local-only metric families outside CANONICAL_FILES (blktrace, SMART,
        AMDuProf PCM, benchmark summaries, setup_details, etc.).

      * prefer == "local": existing local canonical files are preserved and
        Prometheus fills only missing canonical files.

    A raw/amoprof_source_policy.json manifest is written so report builders can
    avoid later "richest local file" searches that would accidentally override
    the explicit --prefer prometheus policy.
    """
    local_raw_dir = Path(local_raw_dir)
    local_raw_dir.mkdir(parents=True, exist_ok=True)

    prefer = (prefer or "local").strip().lower()
    if prefer not in {"local", "prometheus"}:
        raise ValueError(f"prefer must be 'local' or 'prometheus', got {prefer!r}")

    locally_present = {
        name for name in CANONICAL_FILES
        if (local_raw_dir / name).exists()
        and (local_raw_dir / name).stat().st_size > 0
    }

    prom_stage = local_raw_dir / ".prom_stage"
    if prom_stage.exists():
        shutil.rmtree(prom_stage)
    prom_stage.mkdir(parents=True, exist_ok=True)

    policy: dict[str, Any] = {
        "version": 1,
        "prefer": prefer,
        "prom_url": prom_url,
        "created_epoch": time.time(),
        "rule": (
            "prometheus_primary_local_only_for_missing_prometheus_metrics"
            if prefer == "prometheus"
            else "local_primary_prometheus_only_for_missing_local_metrics"
        ),
        "canonical_files": {},
        "local_only_files_preserved": [],
    }

    try:
        fetch_result = fetch_from_prometheus(
            prom_url=prom_url,
            output_dir=prom_stage,
            **fetch_kwargs,
        )

        copied: list[str] = []
        kept_local: list[str] = []
        skipped_empty_prom: list[str] = []

        for name in CANONICAL_FILES:
            src = prom_stage / name
            dst = local_raw_dir / name
            prom_has_data = src.exists() and src.stat().st_size > 0
            local_has_data = name in locally_present

            if prefer == "prometheus":
                if prom_has_data:
                    shutil.copyfile(src, dst)
                    copied.append(name)
                    policy["canonical_files"][name] = {
                        "selected_source": "prometheus",
                        "reason": "--prefer prometheus and Prometheus returned data",
                        "local_was_present": local_has_data,
                    }
                elif local_has_data:
                    kept_local.append(name)
                    policy["canonical_files"][name] = {
                        "selected_source": "local_fallback_missing_in_prometheus",
                        "reason": "--prefer prometheus but Prometheus did not return this metric family",
                        "local_was_present": True,
                    }
                else:
                    skipped_empty_prom.append(name)
                    policy["canonical_files"][name] = {
                        "selected_source": "missing",
                        "reason": "neither Prometheus nor local run directory provided this metric family",
                        "local_was_present": False,
                    }
                continue

            # prefer == "local"
            if local_has_data:
                kept_local.append(name)
                policy["canonical_files"][name] = {
                    "selected_source": "local",
                    "reason": "--prefer local and local file exists",
                    "prometheus_had_data": prom_has_data,
                }
            elif prom_has_data:
                shutil.copyfile(src, dst)
                copied.append(name)
                policy["canonical_files"][name] = {
                    "selected_source": "prometheus_fallback_missing_local",
                    "reason": "--prefer local but local file was missing",
                    "prometheus_had_data": True,
                }
            else:
                skipped_empty_prom.append(name)
                policy["canonical_files"][name] = {
                    "selected_source": "missing",
                    "reason": "neither local nor Prometheus provided this metric family",
                    "prometheus_had_data": False,
                }

        # Record non-canonical local files that remain available as local-only
        # fallbacks.  Do not list private temp dirs or the source policy itself.
        try:
            for f in sorted(local_raw_dir.iterdir()):
                if not f.is_file():
                    continue
                if f.name in CANONICAL_FILES or f.name == SOURCE_POLICY_FILE or f.name.startswith("."):
                    continue
                if f.stat().st_size > 0:
                    policy["local_only_files_preserved"].append(f.name)
        except Exception:
            pass

        policy["fetch"] = {
            "start": fetch_result.get("start"),
            "end": fetch_result.get("end"),
            "step_s": fetch_result.get("step_s"),
            "instance": fetch_result.get("instance"),
            "job": fetch_result.get("job"),
            "labels": fetch_result.get("labels"),
            "percentile_rate_window_s": fetch_result.get("percentile_rate_window_s"),
        }
        policy_path = local_raw_dir / SOURCE_POLICY_FILE
        policy_path.write_text(json.dumps(policy, indent=2, default=str), encoding="utf-8")

        return {
            "prefer":            prefer,
            "locally_present":   sorted(locally_present),
            "copied_from_prom":  copied,
            "kept_local":        kept_local,
            "skipped_empty_prom": skipped_empty_prom,
            "policy_file":       str(policy_path),
            "policy":            policy,
            "fetch":             fetch_result,
        }
    finally:
        if prom_stage.exists():
            shutil.rmtree(prom_stage)
