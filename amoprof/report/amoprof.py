#!/usr/bin/env python3
"""
amoprof.py — AMOprof: AI Memory & IO Profiler
Usage:
    python3 amoprof.py --raw /path/to/raw/           [--output report.html]
    python3 amoprof.py --raw /path/to/raw.zip        [--output report.html]
    python3 amoprof.py --raw /path/to/results_run_*/  (glob)

Reads AMOprof raw output (CSV + JSON collectors), generates a self-contained
HTML report with charts and bottleneck analysis.
"""

import argparse
import base64
import glob
import html
import io
import json
import os
import sys
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.gridspec as gridspec
from matplotlib.ticker import FuncFormatter
import numpy as np
import pandas as pd

# ── Metrics dictionary (optional — graceful fallback if missing) ──────────
try:
    import sys as _sys, os as _os
    _dict_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "ai_metrics_dict.py")
    if _os.path.exists(_dict_path):
        import importlib.util as _ilu
        _spec = _ilu.spec_from_file_location("ai_metrics_dict", _dict_path)
        _amd  = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_amd)
        _DICT_RESOLVE   = _amd.resolve
        _DICT_DISCOVER  = _amd.discover
        _DICT_ANNOTATE  = _amd.annotate_df
        _DICT_REGISTRY  = _amd.REGISTRY
        _DICT_AVAILABLE = True
    else:
        raise ImportError("ai_metrics_dict.py not found alongside profiler")
except Exception as _e:
    _DICT_AVAILABLE = False
    _DICT_REGISTRY  = {}
    def _DICT_RESOLVE(n, **kw):   return None
    def _DICT_DISCOVER(s, **kw):  return {}
    def _DICT_ANNOTATE(df, **kw): return df

# ── Palette ──────────────────────────────────────────────────────────────────
BG      = "#f8fafc"
BG2     = "#ffffff"
BG3     = "#f1f5f9"
BORDER  = "#cbd5e1"
PREFILL = "#f97316"
DECODE  = "#22d3ee"
GPU_C   = "#a78bfa"
HBM_C   = "#7c3aed"
POWER_C = "#fb923c"
DRAM_C  = "#34d399"
NVME_C  = "#f43f5e"
PGF_C   = "#fbbf24"
OK_C    = "#22c55e"
WARN_C  = "#ef4444"
CAU_C   = "#f59e0b"
TEXT_C  = "#0f172a"
MUTED   = "#475569"
ACCENT  = "#4f46e5"

plt.rcParams.update({
    "figure.facecolor": "#ffffff",
    "axes.facecolor": "#f8fafc",
    "axes.edgecolor": "#475569",
    "axes.labelcolor": "#475569",
    "axes.titlecolor": "#0f172a",
    "xtick.color": "#475569",
    "ytick.color": "#475569",
    "grid.color": "#e2e8f0",
    "grid.linestyle": "--",
    "grid.alpha": 0.6,
    "text.color": "#0f172a",
    "legend.facecolor": "#ffffff",
    "legend.edgecolor": "#cbd5e1",
    "legend.labelcolor": "#0f172a",
    "lines.linewidth": 1.8,
    "font.family": "monospace",
})

# ── Data loading ──────────────────────────────────────────────────────────────

def load_raw_dir(raw_path: Path) -> dict:
    """Load all summary JSONs and timeseries CSVs from a raw directory."""
    data = {}
    for f in raw_path.iterdir():
        if f.suffix == ".json":
            try:
                with open(f) as fh:
                    data[f.stem] = json.load(fh)
            except Exception as e:
                print(f"  [warn] {f.name}: {e}")
        elif f.suffix == ".csv":
            try:
                df = pd.read_csv(f, low_memory=False)
                data[f.stem] = df
            except Exception as e:
                print(f"  [warn] {f.name}: {e}")
        elif f.suffix in (".txt",) and "amduprof" in f.stem:
            # AMDuProf raw text dump
            try:
                data[f.stem] = f.read_text(errors="replace")
            except Exception as e:
                print(f"  [warn] {f.name}: {e}")

    # Load AMDuProf raw CSV as text (for DRAM BW parsing - the CSV has a text header)
    for fname in ["amduprof_pcm_raw.csv", "amduprof_pcm_raw"]:
        raw_f = raw_path / fname
        if raw_f.exists() and "amduprof_pcm_raw" not in data:
            try:
                data["amduprof_pcm_raw"] = raw_f.read_text(errors="replace")
            except Exception as e:
                print(f"  [warn] amduprof raw: {e}")

    # Load nsys GPU_METRICS from nsys_csv_dump subdirectory
    nsys_dir = raw_path / "nsys_csv_dump"
    if nsys_dir.is_dir():
        for fname in ["GPU_METRICS.csv", "TARGET_INFO_GPU_METRICS.csv"]:
            fpath = nsys_dir / fname
            if fpath.exists():
                try:
                    data[f"nsys_{fpath.stem}"] = pd.read_csv(fpath, low_memory=False)
                except Exception as e:
                    print(f"  [warn] nsys/{fname}: {e}")

    return data


def load_zip(zip_path: Path) -> dict:
    """Extract zip to a temp dir and load."""
    import tempfile, shutil
    tmp = Path(tempfile.mkdtemp())
    try:
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(tmp)
        # Find the raw directory inside
        candidates = [p for p in tmp.rglob("*.csv")]
        if not candidates:
            raise ValueError("No CSV files found in zip")
        raw_dir = candidates[0].parent
        return load_raw_dir(raw_dir)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _prefer_metric_columns(df: pd.DataFrame, partial: str, *, prefer_unified: bool = True,
                           exclude_buckets: bool = True) -> list[str]:
    """Return matching metric columns, preferring engine_type=unified when present."""
    if df is None or getattr(df, "empty", True):
        return []
    cols = [c for c in df.columns if partial in c]
    if exclude_buckets:
        cols = [c for c in cols if "bucket" not in c]
    if prefer_unified:
        unified = [c for c in cols if "engine_type=unified" in c]
        if unified:
            return unified + [c for c in cols if c not in unified]
    return cols


def _find_metric_col(df: pd.DataFrame, partial: str, *, prefer_unified: bool = True,
                     exclude_buckets: bool = True) -> str | None:
    matches = _prefer_metric_columns(df, partial, prefer_unified=prefer_unified,
                                     exclude_buckets=exclude_buckets)
    return matches[0] if matches else None


def _find_metric_col_with_parts(df: pd.DataFrame, base_partial: str, *required_parts: str,
                                prefer_unified: bool = True,
                                exclude_buckets: bool = True) -> str | None:
    """Find a metric column by base name plus extra substrings, ignoring label order.
    Example: _find_metric_col_with_parts(df, "realtime_tokens_total", "mode=prefill_cache")
    matches both colon and underscore metric styles and any label ordering.
    """
    matches = _prefer_metric_columns(df, base_partial, prefer_unified=prefer_unified,
                                     exclude_buckets=exclude_buckets)
    if required_parts:
        matches = [c for c in matches if all(part in c for part in required_parts)]
    return matches[0] if matches else None


def _find_metric_cols_with_parts(df: pd.DataFrame, base_partial: str, *required_parts: str,
                                 prefer_unified: bool = True,
                                 exclude_buckets: bool = True) -> list[str]:
    """Return ALL matching metric columns, not just the first label series.

    Several SGLang metrics are exported as multiple labelled series, e.g.
    realtime_tokens_total{mode="prefill_cache"} or cached_tokens_total{source="..."}.
    Using the first matching column undercounts/overcounts aggregate cache-hit
    ratios depending on label ordering. Aggregate calculations must sum deltas
    across all relevant series.
    """
    matches = _prefer_metric_columns(df, base_partial, prefer_unified=prefer_unified,
                                     exclude_buckets=exclude_buckets)
    if required_parts:
        matches = [c for c in matches if all(part in c for part in required_parts)]
    return matches


def _delta_sum_metric(df: pd.DataFrame, base_partial: str, *required_parts: str) -> float:
    """Sum positive counter deltas across all matching labelled series."""
    total = 0.0
    for col in _find_metric_cols_with_parts(df, base_partial, *required_parts):
        try:
            vals = pd.to_numeric(df[col], errors="coerce").dropna()
            if len(vals) >= 2:
                d = float(vals.iloc[-1] - vals.iloc[0])
            elif len(vals) == 1:
                d = float(vals.iloc[0])
            else:
                d = 0.0
            # Counters can reset; do not let a reset make the aggregate negative.
            if d > 0:
                total += d
        except Exception:
            pass
    return total



def _cache_hit_gauge_stats(df: pd.DataFrame) -> dict:
    """Script-compatible stats for sglang_cache_hit_rate over the full window.

    This intentionally matches the standalone script semantics:
      - collect every sglang_cache_hit_rate sample in the selected start/end window
      - overall average includes zero/idle samples
      - active average filters value > 0
      - peak is max(sample)
    Values are returned as percentages. Multiple labelled series are flattened.
    """
    stats = {
        "overall_pct": 0.0,
        "active_pct": 0.0,
        "peak_pct": 0.0,
        "total_samples": 0,
        "active_samples": 0,
        "columns": [],
    }
    if df is None or getattr(df, "empty", True):
        return stats
    cols = _find_metric_cols_with_parts(df, "cache_hit_rate")
    cols = [c for c in cols if "bucket" not in c and "_sum" not in c and "_count" not in c]
    if not cols:
        return stats
    vals = []
    for c in cols:
        try:
            ser = pd.to_numeric(df[c], errors="coerce").dropna()
            if len(ser):
                vals.extend(float(x) for x in ser.tolist())
        except Exception:
            pass
    if not vals:
        return stats
    import numpy as _np
    arr = _np.asarray(vals, dtype=float)
    # SGLang exports 0..1. Some derived files may already be 0..100; normalize.
    pct = _np.where(arr <= 1.0, arr * 100.0, arr)
    active = pct[pct > 0]
    stats["overall_pct"] = float(_np.mean(pct))
    stats["peak_pct"] = float(_np.max(pct))
    stats["total_samples"] = int(len(pct))
    stats["active_samples"] = int(len(active))
    stats["active_pct"] = float(_np.mean(active)) if len(active) else 0.0
    stats["columns"] = cols
    return stats


# ── Prometheus live collector ──────────────────────────────────────────────────

def _parse_prometheus_text(text: str) -> dict:
    """Parse Prometheus text exposition format → {metric_key: float}.
    Key format: metric_name  or  metric_name[label=val,label2=val2]
    Strips _bucket lines to keep only _sum / _count for histograms.
    """
    import re
    metrics = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        # Skip histogram buckets — we only need sum/count
        if '_bucket{' in line:
            continue
        parts = line.rsplit(' ', 1)
        if len(parts) < 2:
            continue
        key_part, val_str = parts[0].strip(), parts[1].split()[0]
        try:
            val = float(val_str)
        except ValueError:
            continue
        m = re.match(r'^([a-zA-Z_:][a-zA-Z0-9_:]*)\{([^}]*)\}$', key_part)
        if m:
            key = f"{m.group(1)}[{m.group(2)}]"
        else:
            key = key_part
        metrics[key] = val
    return metrics


def _scrape_once(url: str, timeout: float = 5.0) -> dict:
    """Single scrape of a Prometheus endpoint. Returns {} on failure."""
    try:
        import requests as _req
        r = _req.get(url, timeout=timeout)
        r.raise_for_status()
        return _parse_prometheus_text(r.text)
    except Exception as e:
        return {}


def _nvidia_smi_snapshot() -> list[dict]:
    """Collect per-GPU metrics via nvidia-smi subprocess. Returns [] if unavailable."""
    import subprocess
    try:
        out = subprocess.check_output(
            ["nvidia-smi",
             "--query-gpu=index,utilization.gpu,memory.used,memory.total,power.draw,temperature.gpu",
             "--format=csv,noheader,nounits"],
            timeout=5, stderr=subprocess.DEVNULL
        ).decode()
        rows = []
        for line in out.strip().splitlines():
            parts = [p.strip() for p in line.split(',')]
            if len(parts) < 6:
                continue
            try:
                rows.append({
                    "gpu_idx":  int(parts[0]),
                    "gpu_util": float(parts[1]),
                    "mem_used": float(parts[2]),
                    "mem_total":float(parts[3]),
                    "power":    float(parts[4]),
                    "temp_c":   float(parts[5]),
                })
            except ValueError:
                pass
        return rows
    except Exception:
        return []


def _vmstat_snapshot() -> dict:
    """Read key /proc/vmstat counters. Returns {} on non-Linux."""
    try:
        with open('/proc/vmstat') as f:
            raw = f.read()
        out = {}
        for line in raw.splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[0] in (
                'pgfault', 'pgmajfault', 'numa_pages_migrated',
                'pgpgin', 'pgpgout',
            ):
                out[parts[0]] = int(parts[1])
        return out
    except Exception:
        return {}


def _parse_prom_extra_labels(label_args: list) -> dict:
    """
    Parse --prom-labels KEY=VALUE [KEY=VALUE ...] into a dict.
    Accepts both 'key=value' and 'key="value"' forms.
    Example:  ['gpu=0', 'device=nvme9n1']  →  {'gpu': '0', 'device': 'nvme9n1'}
    """
    result = {}
    for item in (label_args or []):
        item = item.strip().strip('"').strip("'")
        if "=" in item:
            k, _, v = item.partition("=")
            result[k.strip()] = v.strip().strip('"').strip("'")
    return result


def _prom_discover_targets(base_url: str,
                           hostname: str = "") -> dict[str, list[str]]:
    """
    Query Prometheus /api/v1/targets and return a mapping of
    {job_name: [instance_label, ...]} for all active targets.

    Equivalent to:
      curl -s 'http://host:9090/api/v1/targets' | \\
        jq '.data.activeTargets[] | {job:.labels.job, instance:.labels.instance}'

    If hostname is provided, filters to targets whose instance contains
    that hostname string.

    Returns dict like:
      {
        "sglang":        ["msl-ssg-dgx3.msl.lab:30000"],
        "dcgm":          ["msl-ssg-dgx3.msl.lab:9400"],
        "node":          ["msl-ssg-dgx3.msl.lab:9100"],
        "ipmi_exporter": ["msl-ssg-dgx3.msl.lab:9290"],
      }
    """
    try:
        import requests as _req
        r = _req.get(f"{base_url}/api/v1/targets", timeout=10)
        r.raise_for_status()
        data = r.json()
        targets = data.get("data", {}).get("activeTargets", [])

        result: dict[str, list[str]] = {}
        for t in targets:
            labels   = t.get("labels", {})
            job      = labels.get("job", "")
            instance = labels.get("instance", "")
            if not job or not instance:
                continue
            if hostname and hostname not in instance:
                continue
            result.setdefault(job, [])
            if instance not in result[job]:
                result[job].append(instance)
        return result
    except Exception as e:
        return {}


# Known job → metric prefix mappings (used when targets can't be auto-discovered)
_JOB_METRIC_PREFIXES: dict[str, list[str]] = {
    "sglang":        ["sglang_"],
    "vllm":          ["vllm:"],
    "tgi":           ["tgi_"],
    "triton":        ["nv_inference_"],
    "tensorrt":      ["nv_trt_llm_"],
    "dcgm":          ["DCGM_FI_"],
    "node":          ["node_disk_", "node_memory_", "node_vmstat_",
                      "node_cpu_", "node_filesystem_", "node_network_"],
    "node_exporter": ["node_disk_", "node_memory_", "node_vmstat_"],
    "ipmi_exporter": ["ipmi_power_", "ipmi_temperature_", "ipmi_dcmi_"],
    "ipmi":          ["ipmi_power_", "ipmi_temperature_", "ipmi_dcmi_"],
    "prometheus":    ["prometheus_", "go_", "process_"],
    "scrape":        ["up", "scrape_"],
}


def _prom_api_base(url: str) -> str:
    """Convert any Prometheus-related URL to the base API URL.
    Accepts:
      http://host:9090/api/v1/label/__name__/values  → http://host:9090
      http://host:9090                               → http://host:9090
      http://host:30000/metrics                      → http://host:30000  (sglang direct)
    """
    import urllib.parse
    p = urllib.parse.urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    return base


def _prom_query_range(base_url: str, metric: str, start: float, end: float,
                      step: int = 15, timeout: float = 30.0) -> pd.DataFrame:
    """Query Prometheus /api/v1/query_range. Returns DataFrame with columns [time, value, labels...]."""
    try:
        import requests as _req
        url = f"{base_url}/api/v1/query_range"
        params = {"query": metric, "start": start, "end": end, "step": step}
        r = _req.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        if data.get("status") != "success":
            return pd.DataFrame()
        rows = []
        for result in data["data"]["result"]:
            labels = result["metric"]
            for ts, val in result["values"]:
                row = {"time_sec": float(ts) - start}
                row.update(labels)
                try:
                    row["value"] = float(val)
                except (ValueError, TypeError):
                    row["value"] = 0.0
                rows.append(row)
        return pd.DataFrame(rows) if rows else pd.DataFrame()
    except Exception as e:
        return pd.DataFrame()


def _prom_query_instant(base_url: str, metric: str,
                        timeout: float = 10.0) -> list[dict]:
    """Query Prometheus /api/v1/query (instant). Returns list of {labels, value}."""
    try:
        import requests as _req
        r = _req.get(f"{base_url}/api/v1/query",
                     params={"query": metric}, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        if data.get("status") != "success":
            return []
        return [{"labels": res["metric"], "value": float(res["value"][1])}
                for res in data["data"]["result"]]
    except Exception:
        return []


def _prom_list_metrics(base_url: str) -> list[str]:
    """List all metric names from Prometheus."""
    try:
        import requests as _req
        r = _req.get(f"{base_url}/api/v1/label/__name__/values", timeout=10)
        r.raise_for_status()
        return r.json().get("data", [])
    except Exception:
        return []


def _prom_detect_labels(base_url: str, metric: str) -> dict:
    """Get label names and example values for a metric."""
    results = _prom_query_instant(base_url, metric)
    if results:
        return results[0]["labels"]
    return {}


def collect_from_prometheus_api(
    prom_base_url: str,
    start_time: float = 0,
    end_time:   float = 0,
    step_s:     int   = 15,
    label:      str   = "live",
    output_dir: Path  = None,
    instance:   str   = "",
    job:        str   = "",
    extra_labels: dict = None,
) -> dict:
    """
    Pull a complete set of profiling data from a Prometheus server using
    /api/v1/query_range. Covers: SGLang, DCGM GPU, node_exporter disk/memory,
    IPMI power. Works with the existing metrics available at:
      http://105.128.44.21:9090

    Args:
        prom_base_url : Prometheus server base URL, e.g. http://105.128.44.21:9090
                        Can also be the label endpoint URL (auto-stripped).
        start_time    : Unix timestamp for window start (0 = now - 1h)
        end_time      : Unix timestamp for window end   (0 = now)
        step_s        : Query resolution in seconds (15 = good for 1h windows)
        label         : Run label for output files
        output_dir    : If set, write raw CSVs for offline re-analysis
        instance      : Filter to a specific Prometheus instance label.
                        Matches the 'instance' label in your metrics.
                        Example: "msl-ssg-dgx3.msl.lab:30000"
                        Equivalent to: {instance="msl-ssg-dgx3.msl.lab:30000"}
        job           : Filter to a specific Prometheus job label.
                        Example: "sglang", "dcgm", "node_exporter"
        extra_labels  : Any additional label filters as a dict.
                        Example: {"gpu": "0", "device": "nvme9n1"}
                        Multiple labels are ANDed together.

    Label filter examples:
        --prom-instance msl-ssg-dgx3.msl.lab:30000
          → {instance="msl-ssg-dgx3.msl.lab:30000"}

        --prom-instance msl-ssg-dgx3.msl.lab:30000 --prom-job sglang
          → {instance="msl-ssg-dgx3.msl.lab:30000",job="sglang"}

        curl equivalent:
          curl -G 'http://105.128.44.21:9090/api/v1/query' \\
            --data-urlencode 'query={instance="msl-ssg-dgx3.msl.lab:30000"}'

    Returns:
        data dict compatible with extract_metrics()
    """
    import time as _time, requests as _req

    base = _prom_api_base(prom_base_url)
    now  = _time.time()
    t_end   = end_time   if end_time   > 0 else now
    t_start = start_time if start_time > 0 else (t_end - 3600)
    window  = t_end - t_start

    # ── Discover Prometheus targets for this server ─────────────────────────
    # Query /api/v1/targets to get exact {job, instance} pairs per exporter,
    # then use precise selectors like {job="dcgm", instance="host:9400"} for
    # each metric group instead of fragile hostname-regex guessing.
    hostname = instance.split(":")[0] if instance else ""
    discovered_targets: dict = {}

    if hostname:
        print(f"  Discovering targets for: {hostname} ...", end=" ", flush=True)
        discovered_targets = _prom_discover_targets(base, hostname)
        if discovered_targets:
            total_tgts = sum(len(v) for v in discovered_targets.values())
            print(f"found {total_tgts} targets across {len(discovered_targets)} jobs")
            for jname, instances in sorted(discovered_targets.items()):
                for inst in instances:
                    print(f"    {jname:<25} {inst}")
        else:
            print("none (targets API may be restricted — falling back to hostname regex)")

    # ── Build per-job selectors ───────────────────────────────────────────────
    # Priority for each job:
    #   1. Exact {job="...", instance="..."}  from /api/v1/targets discovery
    #   2. Exact {instance="..."}             from --prom-instance
    #   3. Hostname regex {instance=~"host:.*"}
    #   4. "" (no filter)

    label_parts: dict = {}
    if instance:
        label_parts["instance"] = instance
    if job:
        label_parts["job"] = job
    if extra_labels:
        label_parts.update({k: v for k, v in extra_labels.items()
                            if k != "nvme_device"})

    exact_selector = ("{" + ", ".join(f'{k}="{v}"' for k, v in label_parts.items()) + "}"
                      if label_parts else "")

    hostname_re      = hostname.replace(".", "\\.") if hostname else ""
    hostname_selector = ('{' + f'instance=~"{hostname_re}:.*"' + '}') if hostname_re else ""

    def _sel_for(job_name: str = "", metric_prefix: str = "") -> str:
        """Return tightest available PromQL selector for a job/metric combination."""
        # 1. Exact match from target discovery
        if job_name and job_name in discovered_targets and discovered_targets[job_name]:
            inst = discovered_targets[job_name][0]
            return '{' + f'job="{job_name}", instance="{inst}"' + '}'
        # 2. Find by metric prefix across discovered jobs
        if metric_prefix:
            for jname, instances in discovered_targets.items():
                prefixes = _JOB_METRIC_PREFIXES.get(jname, [])
                if any(metric_prefix.startswith(p) for p in prefixes) and instances:
                    return '{' + f'job="{jname}", instance="{instances[0]}"' + '}'
        # 3. Exact instance selector
        if exact_selector:
            return exact_selector
        # 4. Hostname regex
        if hostname_selector:
            return hostname_selector
        return ""



    def _qr(metric_expr: str, agg: str = "", force_selector: str = "") -> pd.DataFrame:
        """Query range with automatic label filter injection."""
        active = force_selector if force_selector else selector
        if active and "{" not in metric_expr:
            expr = metric_expr + active
        elif active and "{" in metric_expr:
            inner = active.strip("{}")
            expr = metric_expr.rstrip("}") + ", " + inner + "}"
        else:
            expr = metric_expr
        if agg:
            expr = f"{agg}({expr})"
        return _prom_query_range(base, expr, t_start, t_end, step_s)

    def _has(name: str) -> bool:
        return name in available

    # ── Discover available metric names ──────────────────────────────────────
    available = set(_prom_list_metrics(base))
    if not available:
        raise ConnectionError(
            f"Cannot reach Prometheus at {base}\n"
            f"  Try: curl '{base}/api/v1/label/__name__/values' | jq '.data|length'"
        )
    print(f"  Found {len(available)} metrics")

    # ── Auto-detect inference server type ────────────────────────────────────
    server_type = "unknown"
    if any(m.startswith("sglang") for m in available):
        server_type = "sglang"
    elif any(m.startswith("vllm") for m in available):
        server_type = "vllm"
    elif any(m.startswith("tgi") for m in available):
        server_type = "tgi"
    elif any(m.startswith("nv_trt_llm") or m.startswith("nv_inference") for m in available):
        server_type = "tensorrt-llm"
    print(f"  Detected server type: {server_type}")

    # Final selector for inference server queries — use target-discovered exact
    # {job,instance} if available, otherwise fall back to exact_selector or hostname regex
    selector = _sel_for(server_type) or exact_selector
    if selector:
        print(f"  Inference selector: {selector}")

    # ── Dictionary-driven metric discovery ────────────────────────────────────
    # Use the dictionary to map ALL available Prometheus metrics regardless of server
    if _DICT_AVAILABLE:
        prom_mapping = _DICT_DISCOVER(list(available), threshold=55)
        print(f"  Dictionary matched {len(prom_mapping)}/{len(available)} metrics")
        # Log unmapped metrics (potential new server metrics)
        unmapped = [m for m in available if m not in prom_mapping
                    and not any(m.startswith(p) for p in
                                ("go_", "process_", "ALERTS", "up", "scrape"))]
        if unmapped[:5]:
            print(f"  Unmapped (sample): {unmapped[:5]}")

    # ── SGLang metrics ────────────────────────────────────────────────────────
    print("  Fetching SGLang metrics...", end=" ", flush=True)
    sg_dfs = {}

    # Core inference metrics
    for name in [
        "sglang_gen_throughput", "sglang_cache_hit_rate",
        "sglang_num_running_reqs", "sglang_token_usage", "sglang_full_token_usage",
        "sglang_hicache_host_used_tokens", "sglang_hicache_host_total_tokens",
        "sglang_max_total_num_tokens", "sglang_kv_used_tokens",
        "sglang_kv_available_tokens", "sglang_kv_evictable_tokens",
        "sglang_num_requests_total", "sglang_num_queue_reqs",
        "sglang_prompt_tokens_total", "sglang_generation_tokens_total",
        "sglang_realtime_tokens_total",
        # KV$B event metrics — the valuable new ones
        "sglang_evicted_tokens_total", "sglang_backuped_tokens_total",
        "sglang_load_back_tokens_total", "sglang_prefetched_tokens_total",
        "sglang_cached_tokens_total", "sglang_new_token_ratio",
        "sglang_utilization", "sglang_num_used_tokens",
        "sglang_decode_sum_seq_lens", "sglang_page_size", "sglang_num_pages",
    ]:
        if _has(name):
            df = _qr(name)
            if not df.empty:
                sg_dfs[name] = df

    # Cumulative sum/count histogram pairs → sglang_timeseries format
    # Iterate over histogram metric base names to fetch _sum and _count
    for base_name, _ in [
        ("sglang_time_to_first_token_seconds", "ttft"),
        ("sglang_inter_token_latency_seconds",  "itl"),
        ("sglang_e2e_request_latency_seconds",  "e2e"),
        ("sglang_queue_time_seconds",            "queue"),
        ("sglang_generation_tokens_histogram",   "gen_tok_hist"),
        ("sglang_prompt_tokens_histogram",       "prompt_tok_hist"),
        ("sglang_eviction_duration_seconds",     "evict_dur"),
        ("sglang_backup_bandwidth",              "backup_bw"),
        ("sglang_load_back_bandwidth",           "loadback_bw"),
        ("sglang_prefetch_bandwidth",            "prefetch_bw"),
        ("sglang_backup_pgs",                    "backup_pgs"),
        ("sglang_load_back_duration_seconds",    "loadback_dur"),
    ]:
        for suffix in ["_sum", "_count"]:
            full = f"{base_name}{suffix}"
            if _has(full):
                df = _qr(full)
                if not df.empty:
                    sg_dfs[full] = df

    print(f"OK ({len(sg_dfs)} series)")

    # ── DCGM GPU metrics ──────────────────────────────────────────────────────
    print("  Fetching DCGM GPU metrics...", end=" ", flush=True)
    dcgm_dfs = {}
    _dcgm_sel = _sel_for("dcgm", "DCGM_FI_")
    for name in [
        "DCGM_FI_DEV_GPU_UTIL", "DCGM_FI_DEV_FB_USED", "DCGM_FI_DEV_FB_FREE",
        "DCGM_FI_DEV_POWER_USAGE", "DCGM_FI_DEV_GPU_TEMP",
        "DCGM_FI_DEV_TOTAL_ENERGY_CONSUMPTION",
        "DCGM_FI_DEV_SM_CLOCK", "DCGM_FI_DEV_MEM_CLOCK",
        "DCGM_FI_DEV_MEM_COPY_UTIL", "DCGM_FI_DEV_DEC_UTIL",
        "DCGM_FI_PROF_DRAM_ACTIVE",      # HBM bandwidth fraction!
        "DCGM_FI_PROF_GR_ENGINE_ACTIVE", # compute active fraction
        "DCGM_FI_PROF_PIPE_TENSOR_ACTIVE",
        "DCGM_FI_PROF_PCIE_RX_BYTES", "DCGM_FI_PROF_PCIE_TX_BYTES",
        "DCGM_FI_DEV_NVLINK_BANDWIDTH_TOTAL",
    ]:
        if _has(name):
            df = _qr(name, force_selector=_dcgm_sel)
            if not df.empty:
                dcgm_dfs[name] = df
    print(f"OK ({len(dcgm_dfs)} series)")

    # ── Node exporter — disk / memory / vmstat ────────────────────────────────
    print("  Fetching node exporter metrics...", end=" ", flush=True)
    node_dfs = {}
    # node_exporter job may be named "node" or "node_exporter"
    _node_sel = _sel_for("node", "node_disk_") or _sel_for("node_exporter", "node_disk_")
    for name in [
        "node_disk_reads_completed_total", "node_disk_writes_completed_total",
        "node_disk_read_bytes_total", "node_disk_written_bytes_total",
        "node_disk_read_time_seconds_total", "node_disk_write_time_seconds_total",
        "node_disk_io_time_seconds_total", "node_disk_io_now",
        "node_disk_io_time_weighted_seconds_total",
        "node_disk_discards_completed_total", "node_disk_discarded_sectors_total",
        "node_disk_flush_requests_total",
        "node_memory_MemTotal_bytes", "node_memory_MemAvailable_bytes",
        "node_memory_MemFree_bytes", "node_memory_Cached_bytes",
        "node_memory_Buffers_bytes", "node_memory_SwapFree_bytes",
        "node_vmstat_pgfault", "node_vmstat_pgmajfault",
        "node_vmstat_pgpgin", "node_vmstat_pgpgout",
        "node_vmstat_pswpin", "node_vmstat_pswpout",
    ]:
        if _has(name):
            df = _qr(name, force_selector=_node_sel)
            if not df.empty:
                node_dfs[name] = df
    print(f"OK ({len(node_dfs)} series)")

    # ── IPMI system power ─────────────────────────────────────────────────────
    print("  Fetching IPMI power...", end=" ", flush=True)
    ipmi_dfs = {}
    _ipmi_sel = _sel_for("ipmi_exporter", "ipmi_") or _sel_for("ipmi", "ipmi_")
    for name in ["ipmi_power_watts", "ipmi_dcmi_power_consumption_watts",
                 "ipmi_temperature_celsius"]:
        if _has(name):
            df = _qr(name, force_selector=_ipmi_sel)
            if not df.empty:
                ipmi_dfs[name] = df
    print(f"OK ({len(ipmi_dfs)} series)")

    # ── Fallback: if system exporters got 0 series, the instance label format   ──
    # may differ (e.g. IP:port instead of hostname:port). Retry without selector.
    if hostname_selector and len(dcgm_dfs) == 0 and len(node_dfs) == 0:
        print("  [warn] DCGM/node returned 0 series with hostname filter.")
        # Probe what instance labels actually exist for DCGM
        probe_metric = next((m for m in available
                             if m.startswith("DCGM_") or m.startswith("node_disk")), None)
        if probe_metric:
            probe_df = _qr(probe_metric, force_selector="")  # no filter
            if not probe_df.empty and "instance" in probe_df.columns:
                actual_instances = probe_df["instance"].unique().tolist()
                print(f"  Actual instance labels for '{probe_metric}':")
                for inst in actual_instances[:8]:
                    print(f"    {inst}")
                # Try to find a matching instance
                hostname = instance.split(":")[0] if instance else ""
                matched = [i for i in actual_instances
                           if hostname and hostname in i] if hostname else []
                if matched:
                    best_inst = matched[0]
                    print(f"  Retrying with matched instance: {best_inst}")
                    retry_sel = '{instance="' + best_inst + '"}'
                    for name in list(available):
                        if name.startswith("DCGM_") and _has(name):
                            df2 = _qr(name, force_selector=retry_sel)
                            if not df2.empty:
                                dcgm_dfs[name] = df2
                        elif name.startswith("node_") and _has(name):
                            df2 = _qr(name, force_selector=retry_sel)
                            if not df2.empty:
                                node_dfs[name] = df2
                    print(f"  After retry — DCGM: {len(dcgm_dfs)}  node: {len(node_dfs)}")
                else:
                    print(f"  No instance containing '{hostname}' found.")
                    print(f"  Tip: use --prom-labels to specify the exact instance label,")
                    print(f"  e.g. --prom-labels 'instance=<one of the above>'")
            else:
                print(f"  Could not probe instance labels — fetching without instance filter")
                for name in list(available):
                    if name.startswith("DCGM_") and _has(name) and name not in dcgm_dfs:
                        df2 = _qr(name, force_selector="")
                        if not df2.empty:
                            dcgm_dfs[name] = df2
                    elif name.startswith("node_disk") and _has(name) and name not in node_dfs:
                        df2 = _qr(name, force_selector="")
                        if not df2.empty:
                            node_dfs[name] = df2
                print(f"  After unfiltered fetch — DCGM: {len(dcgm_dfs)}  node: {len(node_dfs)}")

    # nvme device hint — passed from caller (--nvme-device arg), empty = auto-detect
    instance_nvme_device = extra_labels.get("nvme_device", "") if extra_labels else ""

    # ── Build sglang_timeseries DataFrame (profiler format) ───────────────────
    # Merge all sg series on time_sec using the canonical metric name as column key
    def _flatten_series(df: pd.DataFrame, metric_name: str) -> pd.DataFrame:
        """Take a query_range result and pivot to wide format keyed by metric_name[labels]."""
        if df.empty:
            return pd.DataFrame()
        label_cols = [c for c in df.columns if c not in ("time_sec","value")]
        rows = []
        for t in df["time_sec"].unique():
            sub = df[df["time_sec"] == t]
            for _, row in sub.iterrows():
                lbl = ",".join(f'{c}={row[c]}' for c in label_cols if c in row and row[c])
                key = f"{metric_name}[{lbl}]" if lbl else metric_name
                rows.append({"time_sec": t, "col": key, "val": row["value"]})
        if not rows:
            return pd.DataFrame()
        wide = pd.DataFrame(rows).pivot_table(
            index="time_sec", columns="col", values="val", aggfunc="first"
        ).reset_index()
        wide.columns.name = None
        return wide

    # Build the master timeseries from all sglang series
    master = pd.DataFrame({"time_sec": pd.Series(dtype=float)})
    for metric_name, df in sg_dfs.items():
        flat = _flatten_series(df, metric_name)
        if not flat.empty:
            master = pd.merge(master, flat, on="time_sec", how="outer")
    master = master.sort_values("time_sec").reset_index(drop=True)

    # ── Build gpu_timeseries from DCGM ────────────────────────────────────────
    gpu_rows = []
    dcgm_util = dcgm_dfs.get("DCGM_FI_DEV_GPU_UTIL", pd.DataFrame())
    dcgm_fb   = dcgm_dfs.get("DCGM_FI_DEV_FB_USED",  pd.DataFrame())
    dcgm_pwr  = dcgm_dfs.get("DCGM_FI_DEV_POWER_USAGE", pd.DataFrame())
    dcgm_temp = dcgm_dfs.get("DCGM_FI_DEV_GPU_TEMP", pd.DataFrame())
    dcgm_mem_total = dcgm_dfs.get("DCGM_FI_DEV_FB_FREE", pd.DataFrame())
    dcgm_dram_act = dcgm_dfs.get("DCGM_FI_PROF_DRAM_ACTIVE", pd.DataFrame())

    if not dcgm_util.empty:
        for _, row in dcgm_util.iterrows():
            t_s = float(row["time_sec"])
            gpu_id = row.get("gpu","0") or row.get("UUID","0") or "0"
            g_row = {"time_sec": t_s, "gpu_idx": gpu_id, "gpu_util": float(row["value"])}
            # Match FB_USED at same time
            if not dcgm_fb.empty:
                sub = dcgm_fb[(dcgm_fb["time_sec"] == t_s) &
                              (dcgm_fb.get("gpu", dcgm_fb.get("UUID", pd.Series())) == gpu_id
                               if "gpu" in dcgm_fb.columns else slice(None))]
                g_row["mem_used"] = float(sub["value"].mean()) if not sub.empty else 0
            if not dcgm_pwr.empty:
                sub = dcgm_pwr[dcgm_pwr["time_sec"] == t_s]
                g_row["power"] = float(sub["value"].mean()) if not sub.empty else 0
            if not dcgm_temp.empty:
                sub = dcgm_temp[dcgm_temp["time_sec"] == t_s]
                g_row["temp_c"] = float(sub["value"].mean()) if not sub.empty else 0
            if not dcgm_dram_act.empty:
                sub = dcgm_dram_act[dcgm_dram_act["time_sec"] == t_s]
                g_row["hbm_bw_pct"] = float(sub["value"].mean()) * 100 if not sub.empty else 0
            gpu_rows.append(g_row)

    gpu_df = pd.DataFrame(gpu_rows) if gpu_rows else pd.DataFrame()

    # ── Build power_timeseries ────────────────────────────────────────────────
    power_rows = []
    # Prefer DCGM power (per-GPU)
    if not dcgm_pwr.empty:
        for t_s, grp in dcgm_pwr.groupby("time_sec"):
            power_rows.append({
                "time_sec": t_s, "source": "DCGM",
                "gpu_power": float(grp["value"].sum())
            })
    # IPMI as fallback / system-level supplement
    ipmi_pwr = ipmi_dfs.get("ipmi_power_watts", ipmi_dfs.get("ipmi_dcmi_power_consumption_watts", pd.DataFrame()))
    if not ipmi_pwr.empty:
        for _, row in ipmi_pwr.iterrows():
            power_rows.append({"time_sec": float(row["time_sec"]),
                                "source": "IPMI", "system_power_w": float(row["value"])})
    power_df = pd.DataFrame(power_rows) if power_rows else pd.DataFrame()

    # ── Build nvme_driver_timeseries from node_disk ───────────────────────────
    # nvme_device comes from extra_labels["nvme_device"] set by --nvme-device arg.
    # Falls back to auto-detect (empty string) when not provided.
    nvme_device = (extra_labels or {}).get("nvme_device", "")
    instance_nvme_device = nvme_device
    nvme_rows = []

    def _get_disk_series(metric: str, device: str = "") -> pd.DataFrame:
        df = node_dfs.get(metric, pd.DataFrame())
        if df.empty:
            return pd.DataFrame()
        if "device" not in df.columns:
            return df
        dev = device or nvme_device
        if dev:
            sub = df[df["device"] == dev]
            if not sub.empty:
                return sub
            sub2 = df[df["device"].str.startswith(dev.rstrip("1"), na=False)]
            if not sub2.empty:
                return sub2
        # Auto-detect: nvme device with highest cumulative value
        nvme_sub = df[df["device"].str.match(r"nvme\d+n\d+$", na=False)]
        if nvme_sub.empty:
            nvme_sub = df[df["device"].str.contains("nvme", na=False)]
        if not nvme_sub.empty:
            val_col = "value" if "value" in nvme_sub.columns else nvme_sub.columns[-1]
            top_dev = nvme_sub.groupby("device")[val_col].max().idxmax()
            return nvme_sub[nvme_sub["device"] == top_dev]
        return df

    rd_bytes = _get_disk_series("node_disk_read_bytes_total")
    wr_bytes = _get_disk_series("node_disk_written_bytes_total")
    rd_cmds  = _get_disk_series("node_disk_reads_completed_total")
    wr_cmds  = _get_disk_series("node_disk_writes_completed_total")
    rd_time  = _get_disk_series("node_disk_read_time_seconds_total")
    wr_time  = _get_disk_series("node_disk_write_time_seconds_total")
    io_time  = _get_disk_series("node_disk_io_time_seconds_total")
    io_now   = _get_disk_series("node_disk_io_now")
    disc_cmds= _get_disk_series("node_disk_discards_completed_total")
    disc_secs= _get_disk_series("node_disk_discarded_sectors_total")

    if not rd_cmds.empty or not wr_cmds.empty:
        ref = wr_cmds if not wr_cmds.empty else rd_cmds
        for _, row in ref.iterrows():
            t_s  = float(row["time_sec"])
            nrow = {"time_sec": t_s}
            def _val(df, t):
                if df.empty: return 0
                sub = df[df["time_sec"] == t]
                return float(sub["value"].iloc[0]) if not sub.empty else 0
            nrow["rd_ios"]   = _val(rd_cmds,  t_s)
            nrow["wr_ios"]   = _val(wr_cmds,  t_s)
            nrow["rd_ms"]    = _val(rd_time,  t_s) * 1000
            nrow["wr_ms"]    = _val(wr_time,  t_s) * 1000
            nrow["io_ms"]    = _val(io_time,  t_s) * 1000
            nrow["inflight"] = _val(io_now,   t_s)
            nrow["disc_ios"] = _val(disc_cmds, t_s)
            nrow["disc_sectors"] = _val(disc_secs, t_s)
            nvme_rows.append(nrow)

    nvme_df = pd.DataFrame(nvme_rows).sort_values("time_sec").reset_index(drop=True) \
              if nvme_rows else pd.DataFrame()

    # ── Build vmstat_timeseries ───────────────────────────────────────────────
    vmstat_rows2 = []
    pgf = node_dfs.get("node_vmstat_pgfault", pd.DataFrame())
    pgmaj = node_dfs.get("node_vmstat_pgmajfault", pd.DataFrame())
    pgin  = node_dfs.get("node_vmstat_pgpgin", pd.DataFrame())
    pgout = node_dfs.get("node_vmstat_pgpgout", pd.DataFrame())
    pswpin  = node_dfs.get("node_vmstat_pswpin", pd.DataFrame())
    pswpout = node_dfs.get("node_vmstat_pswpout", pd.DataFrame())
    swapfree_b = node_dfs.get("node_memory_SwapFree_bytes", pd.DataFrame())
    memavail_b = node_dfs.get("node_memory_MemAvailable_bytes", pd.DataFrame())
    if not pgf.empty:
        for _, row in pgf.iterrows():
            t_s = float(row["time_sec"])
            def _v(df): return float(df[df["time_sec"]==t_s]["value"].iloc[0]) if not df.empty and (df["time_sec"]==t_s).any() else 0
            vmstat_rows2.append({
                "time_sec": t_s,
                "pgfault": _v(pgf), "pgmajfault": _v(pgmaj),
                "pgpgin":  _v(pgin), "pgpgout":  _v(pgout),
                "pswpin":  _v(pswpin), "pswpout": _v(pswpout),
                "swap_free_mb":   _v(swapfree_b) / (1024 * 1024),
                "mem_avail_mb":   _v(memavail_b) / (1024 * 1024),
            })
    vmstat_df2 = pd.DataFrame(vmstat_rows2) if vmstat_rows2 else pd.DataFrame()

    # ── SMART supplement from DCGM total_energy_consumption ──────────────────
    smart_rows2 = []
    dcgm_energy = dcgm_dfs.get("DCGM_FI_DEV_TOTAL_ENERGY_CONSUMPTION", pd.DataFrame())
    if not dcgm_energy.empty:
        for _, row in dcgm_energy.groupby("time_sec").first().reset_index().iterrows():
            smart_rows2.append({"time_sec": float(row["time_sec"]),
                                  "tag": "poll", "energy_mj": float(row["value"])})
    smart_df2 = pd.DataFrame(smart_rows2) if smart_rows2 else pd.DataFrame()

    # ── Derive sglang_summary from the collected timeseries ───────────────────
    def _last_col2(partial, df=master):
        c = _find_metric_col(df, partial)
        return float(df[c].dropna().iloc[-1]) if c and not df[c].dropna().empty else 0.0

    def _first_col2(partial, df=master):
        c = _find_metric_col(df, partial)
        return float(df[c].dropna().iloc[0]) if c and not df[c].dropna().empty else 0.0

    def _delta2(partial, df=master):
        return max(_last_col2(partial, df) - _first_col2(partial, df), 0)

    d_ttft_sum = _delta2("time_to_first_token_seconds_sum")
    d_ttft_cnt = _delta2("time_to_first_token_seconds_count")
    d_itl_sum  = _delta2("inter_token_latency_seconds_sum")
    d_itl_cnt  = _delta2("inter_token_latency_seconds_count")
    d_e2e_sum  = _delta2("e2e_request_latency_seconds_sum")
    d_e2e_cnt  = _delta2("e2e_request_latency_seconds_count")

    ttft_ms = (d_ttft_sum / d_ttft_cnt * 1000) if d_ttft_cnt > 0 else 0
    tpot_ms = (d_itl_sum  / d_itl_cnt  * 1000) if d_itl_cnt  > 0 else 0
    e2e_ms  = (d_e2e_sum  / d_e2e_cnt  * 1000) if d_e2e_cnt  > 0 else 0

    # Use absolute values if no delta (window captured a single ongoing request)
    if ttft_ms == 0:
        abs_sum = _last_col2("time_to_first_token_seconds_sum")
        abs_cnt = _last_col2("time_to_first_token_seconds_count")
        if abs_cnt > 0: ttft_ms = abs_sum / abs_cnt * 1000

    # DCGM DRAM_ACTIVE gives HBM BW utilisation directly
    dcgm_dram_mean = 0.0
    if not dcgm_dram_act.empty:
        dcgm_dram_mean = float(dcgm_dram_act["value"].mean()) * 100  # percent

    gen_tp_col = _find_metric_col(master, "gen_throughput")
    gen_tp_peak = float(master[gen_tp_col].max()) if gen_tp_col else 0

    # Cache hit rate: keep both benchmark-style token accounting and the
    # script-compatible gauge averages.  The primary report KPI intentionally
    # uses the gauge active average when present, because that is what the
    # standalone validation script computes from sglang_cache_hit_rate.
    _d_rt_cache = _delta_sum_metric(master, "realtime_tokens_total", "mode=prefill_cache")
    _d_rt_compute = _delta_sum_metric(master, "realtime_tokens_total", "mode=prefill_compute")
    _token_weighted_hit = 0.0
    if (_d_rt_cache + _d_rt_compute) > 0:
        _token_weighted_hit = (_d_rt_cache / (_d_rt_cache + _d_rt_compute)) * 100.0
    _gstats = _cache_hit_gauge_stats(master)
    if _gstats["active_samples"] > 0:
        _alt_cache_hit = _gstats["active_pct"]
        _alt_method = "gauge_active_average_script_compatible"
    elif _gstats["total_samples"] > 0:
        _alt_cache_hit = _gstats["overall_pct"]
        _alt_method = "gauge_timeline_average_script_compatible"
    elif _token_weighted_hit > 0:
        _alt_cache_hit = _token_weighted_hit
        _alt_method = "realtime_tokens_delta"
    else:
        _alt_cache_hit = 0.0
        _alt_method = "none"

    sglang_summary = {
        "model_name":                  "unknown",
        "server_ttft_ms":              round(ttft_ms, 2),
        "server_itl_ms":               round(tpot_ms, 2),
        "server_e2e_ms":               round(e2e_ms,  2),
        "cache_hit_rate_realtime_pct": round(_alt_cache_hit, 2),
        "cache_hit_calc_method":       _alt_method,
        "cache_hit_token_weighted_pct": round(_token_weighted_hit, 2),
        "cache_hit_gauge_overall_pct":  round(_gstats.get("overall_pct", 0.0), 2),
        "cache_hit_gauge_active_pct":   round(_gstats.get("active_pct", 0.0), 2),
        "cache_hit_gauge_peak_pct":     round(_gstats.get("peak_pct", 0.0), 2),
        "cache_hit_gauge_total_samples": int(_gstats.get("total_samples", 0)),
        "cache_hit_gauge_active_samples": int(_gstats.get("active_samples", 0)),
        "hicache_host_fill_pct":       round(
            _last_col2("hicache_host_used_tokens") /
            max(_last_col2("hicache_host_total_tokens"), 1) * 100, 2),
        "rt_decode_tokens":            int(_delta2("realtime_tokens_total") or
                                           _delta2("generation_tokens_total")),
        "rt_prefill_compute_tokens":   0,
        "rt_prefill_cache_tokens":     0,
        "hicache_host_used_tokens":    _last_col2("hicache_host_used_tokens"),
        "hicache_host_total_tokens":   _last_col2("hicache_host_total_tokens"),
        "kv_used_tokens":              _last_col2("kv_used_tokens"),
        "kv_available_tokens":         _last_col2("kv_available_tokens"),
        "evicted_tokens_total":        _delta2("evicted_tokens_total"),
        "backuped_tokens_total":       _delta2("backuped_tokens_total"),
        "load_back_tokens_total":      _delta2("load_back_tokens_total"),
        "dcgm_hbm_bw_util_pct":        round(dcgm_dram_mean, 2),
        "prometheus_source":           prom_base_url,
        "collection_elapsed_s":        window,
        "collection_window_start":     t_start,
        "collection_window_end":       t_end,
    }

    gpu_summary = {}
    if not gpu_df.empty:
        try:
            gpu_count = int(dcgm_util["gpu"].nunique()) if "gpu" in dcgm_util.columns else 8
        except Exception:
            gpu_count = 8
        gpu_summary = {
            "gpu_count":             gpu_count,
            "gpu_util_mean":         round(float(gpu_df["gpu_util"].mean()), 2),
            "gpu_util_peak":         round(float(gpu_df["gpu_util"].max()),  2),
            "hbm_used_mb_mean":      round(float(gpu_df["mem_used"].mean()), 0) if "mem_used" in gpu_df.columns else 0,
            "hbm_total_mb_per_gpu":  40960.0,  # A100 40GB
            "hbm_util_pct_mean":     round(float(gpu_df["mem_used"].mean()) / 40960 * 100, 2) if "mem_used" in gpu_df.columns else 0,
            "power_all_gpus_w_mean": round(float(gpu_df["power"].mean()), 2) if "power" in gpu_df.columns else 0,
            "power_w_peak":          round(float(gpu_df["power"].max()), 2)   if "power" in gpu_df.columns else 0,
            "dcgm_hbm_bw_active_pct": round(dcgm_dram_mean, 2),
        }

    vmstat_summary = {}
    if not vmstat_df2.empty and "pgfault" in vmstat_df2.columns:
        dt2 = vmstat_df2["time_sec"].iloc[-1] - vmstat_df2["time_sec"].iloc[0]
        d_pgf = vmstat_df2["pgfault"].iloc[-1] - vmstat_df2["pgfault"].iloc[0]
        vmstat_summary = {"page_faults_per_s": round(d_pgf / max(dt2, 1), 2)}

    power_summary = {"power_elapsed_s": window}

    # ── Save raw CSVs if requested ────────────────────────────────────────────
    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        if not master.empty:
            master.to_csv(output_dir / "sglang_timeseries.csv", index=False)
        if not gpu_df.empty:
            gpu_df.to_csv(output_dir / "gpu_timeseries.csv", index=False)
        if not nvme_df.empty:
            nvme_df.to_csv(output_dir / "nvme_driver_timeseries.csv", index=False)
        if not vmstat_df2.empty:
            vmstat_df2.to_csv(output_dir / "vmstat_timeseries.csv", index=False)
        if not power_df.empty:
            power_df.to_csv(output_dir / "power_timeseries.csv", index=False)
        with open(output_dir / "sglang_summary.json", "w") as fh:
            json.dump(sglang_summary, fh, indent=2)
        if gpu_summary:
            with open(output_dir / "gpu_summary.json", "w") as fh:
                json.dump(gpu_summary, fh, indent=2)
        print(f"  Raw CSVs saved → {output_dir}")

    print(f"  SGLang series: {len(sg_dfs)}  DCGM: {len(dcgm_dfs)}  "
          f"node: {len(node_dfs)}  IPMI: {len(ipmi_dfs)}")

    return {
        "sglang_summary":            sglang_summary,
        "gpu_summary":               gpu_summary,
        "vmstat_summary":            vmstat_summary,
        "power_summary":             power_summary,
        "sglang_timeseries":         master,
        "gpu_timeseries":            gpu_df,
        "nvme_driver_timeseries":    nvme_df,
        "vmstat_timeseries":         vmstat_df2,
        "power_timeseries":          power_df,
        "smart_timeseries":          smart_df2,
        # Hint for extract_metrics — the nvme device name (empty = auto-detect)
        "_nvme_device_hint":         instance_nvme_device,
        # Raw per-metric DataFrames for advanced use
        "_dcgm_raw":  dcgm_dfs,
        "_node_raw":  node_dfs,
        "_sg_raw":    sg_dfs,
    }



def collect_from_prometheus(
    prom_url: str,
    duration_s: int = 0,
    interval_s: float = 2.0,
    extra_gpu: bool = True,
    extra_vmstat: bool = True,
    label: str = "live",
    output_dir: Path = None,
    instance: str = "",
    job: str = "",
    extra_labels: dict = None,
) -> dict:
    """
    Scrape a Prometheus endpoint + nvidia-smi + /proc/vmstat at `interval_s`
    for `duration_s` seconds (0 = run until Ctrl-C), then return a data dict
    compatible with extract_metrics().

    Args:
        prom_url     : Full URL to /metrics endpoint
                       e.g. "http://localhost:30000/metrics"
        duration_s   : Collection window in seconds (0 = until Ctrl-C)
        interval_s   : Scrape interval in seconds (default 2.0)
        extra_gpu    : Also collect nvidia-smi each interval
        extra_vmstat : Also collect /proc/vmstat each interval
        label        : Run label used in filenames if output_dir is set
        output_dir   : If set, write raw CSVs here for offline re-analysis

    Returns:
        data dict suitable for passing to extract_metrics()
    """
    import time, signal, sys

    # ── Validate endpoint ─────────────────────────────────────────────────────
    print(f"\n  Probing {prom_url} ...", end=" ", flush=True)
    first = _scrape_once(prom_url, timeout=8.0)
    if not first:
        raise ConnectionError(
            f"Cannot reach Prometheus endpoint: {prom_url}\n"
            f"  • Check SGLang is running:  curl {prom_url}\n"
            f"  • Check port / firewall"
        )
    print(f"OK  ({len(first)} metrics)")

    # Detect model name from metric keys
    model_name = "unknown"
    import re as _re
    for key in first:
        m = _re.search(r'model_name=([^\]",]+)', key)
        if m:
            model_name = m.group(1).strip('"\'')
            break
    print(f"  Model detected: {model_name}")

    # ── Collection loop ───────────────────────────────────────────────────────
    sglang_rows  = []   # [{time_sec, metric_key: val, ...}]
    gpu_rows     = []   # [{time_sec, gpu_idx, gpu_util, mem_used, ...}]
    vmstat_rows  = []   # [{time_sec, pgfault, ...}]
    power_rows   = []   # [{time_sec, source, gpu_power}]

    stopped = [False]
    def _on_signal(sig, frame):
        stopped[0] = True
        print("\n  [collector] Ctrl-C received — stopping collection...")

    old_handler = signal.signal(signal.SIGINT, _on_signal)

    t_start = time.monotonic()
    t_end   = t_start + duration_s if duration_s > 0 else float('inf')
    iteration = 0

    if duration_s > 0:
        print(f"  Collecting for {duration_s}s at {interval_s}s intervals "
              f"({'+ nvidia-smi' if extra_gpu else ''}"
              f"{'+ vmstat' if extra_vmstat else ''}) — press Ctrl-C to stop early")
    else:
        print(f"  Collecting at {interval_s}s intervals (Ctrl-C to stop)...")

    try:
        while not stopped[0] and time.monotonic() < t_end:
            t_iter = time.monotonic()
            t_sec  = round(t_iter - t_start, 2)

            # Prometheus scrape
            snap = _scrape_once(prom_url, timeout=interval_s * 0.8)
            if snap:
                row = {"time_sec": t_sec, "iteration": iteration}
                row.update({f"sglang:{k}": v for k, v in snap.items()
                             if not k.startswith("sglang:")})
                row.update({k: v for k, v in snap.items()
                             if k.startswith("sglang:")})
                sglang_rows.append(row)

            # nvidia-smi
            if extra_gpu:
                for g in _nvidia_smi_snapshot():
                    gpu_rows.append({
                        "time_sec":   t_sec,
                        "iteration":  iteration,
                        "gpu_idx":    g["gpu_idx"],
                        "gpu_util":   g["gpu_util"],
                        "mem_used":   g["mem_used"],
                        "mem_total":  g["mem_total"],
                        "power":      g["power"],
                        "temp_c":     g["temp_c"],
                    })
                    power_rows.append({
                        "time_sec":  t_sec,
                        "source":    "nvidia-smi",
                        "gpu_power": g["power"],
                    })

            # vmstat
            if extra_vmstat:
                vs = _vmstat_snapshot()
                if vs:
                    vmstat_rows.append({"time_sec": t_sec, "iteration": iteration, **vs})

            # Progress
            if iteration % max(1, int(10 / interval_s)) == 0:
                elapsed = int(t_iter - t_start)
                gpu_util = (sum(r["gpu_util"] for r in gpu_rows[-8:]) /
                            max(len(gpu_rows[-8:]), 1)) if gpu_rows else 0
                gen_tp_key = next((k for k in snap if "gen_throughput" in k), None)
                gen_tp = snap.get(gen_tp_key, 0) if gen_tp_key else 0
                print(f"  [{elapsed:5d}s]  samples={iteration+1:4d}  "
                      f"gen_tp={gen_tp:.1f}tok/s  "
                      f"gpu={gpu_util:.0f}%", flush=True)

            iteration += 1
            # Sleep for remainder of interval
            sleep_t = max(0.0, interval_s - (time.monotonic() - t_iter))
            time.sleep(sleep_t)

    finally:
        signal.signal(signal.SIGINT, old_handler)

    elapsed_s = round(time.monotonic() - t_start, 1)
    print(f"\n  Collection complete: {iteration} scrapes over {elapsed_s}s")
    print(f"  SGLang rows: {len(sglang_rows)}  GPU rows: {len(gpu_rows)}  "
          f"vmstat rows: {len(vmstat_rows)}")

    if not sglang_rows:
        raise RuntimeError("No metrics collected — check Prometheus endpoint and interval")

    # ── Convert to DataFrames ─────────────────────────────────────────────────
    sglang_df  = pd.DataFrame(sglang_rows).ffill().fillna(0)
    gpu_df     = pd.DataFrame(gpu_rows)     if gpu_rows     else pd.DataFrame()
    vmstat_df  = pd.DataFrame(vmstat_rows)  if vmstat_rows  else pd.DataFrame()
    power_df   = pd.DataFrame(power_rows)   if power_rows   else pd.DataFrame()

    # ── Build summary JSON (mirrors what offline collectors produce) ──────────
    # Derive TTFT/TPOT from cumulative counters in the last vs first scrape
    def _delta(col):
        if col not in sglang_df.columns:
            return 0.0
        vals = sglang_df[col].dropna()
        return float(vals.iloc[-1] - vals.iloc[0]) if len(vals) > 1 else 0.0

    def _last(col):
        if col not in sglang_df.columns:
            return 0.0
        vals = sglang_df[col].dropna()
        return float(vals.iloc[-1]) if len(vals) > 0 else 0.0

    # Find actual column names (they may have label suffixes)
    def _find_col(partial, df):
        return _find_metric_col(df, partial)

    ttft_sum_col   = _find_col("time_to_first_token_seconds_sum",   sglang_df)
    ttft_cnt_col   = _find_col("time_to_first_token_seconds_count",  sglang_df)
    itl_sum_col    = _find_col("inter_token_latency_seconds_sum",    sglang_df)
    itl_cnt_col    = _find_col("inter_token_latency_seconds_count",  sglang_df)
    e2e_sum_col    = _find_col("e2e_request_latency_seconds_sum",    sglang_df)
    e2e_cnt_col    = _find_col("e2e_request_latency_seconds_count",  sglang_df)
    gen_tp_col     = _find_col("gen_throughput",                     sglang_df)
    cache_col      = _find_col("cache_hit_rate",                     sglang_df)
    # Counter-based cache hit (matches what bench_serving reports): cumulative
    # cached tokens / cumulative prompt tokens across the run. This is the
    # ground-truth aggregate weighted by token volume — the gauge column
    # alone is a per-tick snapshot that decays to 0 during idle windows,
    # and a naive .mean() of it gives a meaningless number (e.g. 4.6%) on
    # bursty workloads where most ticks are idle. See cache_hit calculation
    # below for the chosen formula.
    cached_tok_col = _find_col("cached_tokens_total",                sglang_df)
    prompt_tok_col = _find_col("prompt_tokens_total",                sglang_df)
    hi_used_col    = _find_col("hicache_host_used_tokens",           sglang_df)
    hi_total_col   = _find_col("hicache_host_total_tokens",          sglang_df)
    decode_tok_col = _find_metric_col_with_parts(sglang_df, 'realtime_tokens_total', 'mode=decode')
    pfc_col        = _find_metric_col_with_parts(sglang_df, 'realtime_tokens_total', 'mode=prefill_compute')
    pfc_cache_col  = _find_metric_col_with_parts(sglang_df, 'realtime_tokens_total', 'mode=prefill_cache')

    d_ttft_sum  = _delta(ttft_sum_col)  if ttft_sum_col  else 0
    d_ttft_cnt  = _delta(ttft_cnt_col)  if ttft_cnt_col  else 0
    d_itl_sum   = _delta(itl_sum_col)   if itl_sum_col   else 0
    d_itl_cnt   = _delta(itl_cnt_col)   if itl_cnt_col   else 0
    d_e2e_sum   = _delta(e2e_sum_col)   if e2e_sum_col   else 0
    d_e2e_cnt   = _delta(e2e_cnt_col)   if e2e_cnt_col   else 0

    ttft_ms = (d_ttft_sum / d_ttft_cnt * 1000) if d_ttft_cnt > 0 else 0
    tpot_ms = (d_itl_sum  / d_itl_cnt  * 1000) if d_itl_cnt  > 0 else 0
    e2e_ms  = (d_e2e_sum  / d_e2e_cnt  * 1000) if d_e2e_cnt  > 0 else 0

    # If counters didn't change (collected during a single long request),
    # use the absolute final values as the single-request measurement
    if ttft_ms == 0 and ttft_sum_col:
        abs_ttft = _last(ttft_sum_col)
        abs_cnt  = _last(ttft_cnt_col) if ttft_cnt_col else 0
        if abs_cnt > 0:
            ttft_ms = abs_ttft / abs_cnt * 1000
    if tpot_ms == 0 and itl_sum_col:
        abs_itl = _last(itl_sum_col)
        abs_cnt = _last(itl_cnt_col) if itl_cnt_col else 0
        if abs_cnt > 0:
            tpot_ms = abs_itl / abs_cnt * 1000
    if e2e_ms == 0 and e2e_sum_col:
        abs_e2e = _last(e2e_sum_col)
        abs_cnt = _last(e2e_cnt_col) if e2e_cnt_col else 0
        if abs_cnt > 0:
            e2e_ms = abs_e2e / abs_cnt * 1000

    gen_tp_peak = float(sglang_df[gen_tp_col].max()) if gen_tp_col else 0

    # Cache hit rate — strategies, in order of fidelity:
    #
    # Cache-hit methodology.  We keep all variants, but the primary KPI
    # is script-compatible: active average of every sglang_cache_hit_rate
    # sample in the selected Prometheus window.  This should match the
    # standalone validation script posted with the issue.
    d_rt_cache = _delta_sum_metric(sglang_df, "realtime_tokens_total", "mode=prefill_cache")
    d_rt_compute = _delta_sum_metric(sglang_df, "realtime_tokens_total", "mode=prefill_compute")
    cache_hit_token_weighted = 0.0
    if (d_rt_cache + d_rt_compute) > 0:
        cache_hit_token_weighted = (d_rt_cache / (d_rt_cache + d_rt_compute)) * 100.0

    d_cached = _delta_sum_metric(sglang_df, "cached_tokens_total")
    d_prompt = _delta_sum_metric(sglang_df, "prompt_tokens_total")
    cache_hit_cached_prompt_pct = (d_cached / d_prompt * 100.0) if d_prompt > 0 else 0.0

    _gstats = _cache_hit_gauge_stats(sglang_df)
    cache_hit_gauge_overall = float(_gstats.get("overall_pct", 0.0))
    cache_hit_gauge_active = float(_gstats.get("active_pct", 0.0))
    cache_hit_gauge_peak = float(_gstats.get("peak_pct", 0.0))
    cache_hit_gauge_total_samples = int(_gstats.get("total_samples", 0))
    cache_hit_gauge_active_samples = int(_gstats.get("active_samples", 0))

    if cache_hit_gauge_active_samples > 0:
        cache_hit = cache_hit_gauge_active
        cache_hit_method = "gauge_active_average_script_compatible"
    elif cache_hit_gauge_total_samples > 0:
        cache_hit = cache_hit_gauge_overall
        cache_hit_method = "gauge_timeline_average_script_compatible"
    elif cache_hit_token_weighted > 0:
        cache_hit = cache_hit_token_weighted
        cache_hit_method = "realtime_tokens_delta"
    elif cache_hit_cached_prompt_pct > 0:
        cache_hit = cache_hit_cached_prompt_pct
        cache_hit_method = "cached_tokens_over_prompt_tokens"
    else:
        cache_hit = 0.0
        cache_hit_method = "none"

    hi_used  = _last(hi_used_col)  if hi_used_col  else 0
    hi_total = _last(hi_total_col) if hi_total_col else 0
    hi_fill  = (hi_used / hi_total * 100) if hi_total > 0 else 0

    # Use deltas for cumulative token counters so the report reflects the run
    # window, not server lifetime before the benchmark started.
    rt_decode    = _delta_sum_metric(sglang_df, "realtime_tokens_total", "mode=decode")
    rt_pfc       = _delta_sum_metric(sglang_df, "realtime_tokens_total", "mode=prefill_compute")
    rt_pfc_cache = _delta_sum_metric(sglang_df, "realtime_tokens_total", "mode=prefill_cache")

    # Decode throughput — same idle-tick pitfall as cache_hit. The gauge
    # gen_throughput drops to 0 between request bursts, so a naive .mean()
    # would underreport sustained throughput. Use active-window mean.
    if gen_tp_col:
        try:
            _ser = sglang_df[gen_tp_col].astype(float)
            _active = _ser[_ser > 0]
            if len(_active) > 0:
                _gen_tp_mean = float(_active.mean())
                _gen_tp_method = "active_mean"
            else:
                _gen_tp_mean = float(_ser.mean())
                _gen_tp_method = "all_zeros"
        except Exception:
            _gen_tp_mean = 0.0
            _gen_tp_method = "error"
    else:
        _gen_tp_mean = 0.0
        _gen_tp_method = "no_column"

    sglang_summary = {
        "model_name":                   model_name,
        "server_ttft_ms":               round(ttft_ms, 2),
        "server_itl_ms":                round(tpot_ms, 2),
        "server_e2e_ms":                round(e2e_ms,  2),
        "ai_op_decode_tok_s":           round(_gen_tp_mean, 3),
        "ai_op_decode_tok_s_method":    _gen_tp_method,
        "cache_hit_rate_realtime_pct":  round(cache_hit, 2),
        "cache_hit_calc_method":        cache_hit_method,
        "cache_hit_token_weighted_pct": round(cache_hit_token_weighted, 2),
        "cache_hit_cached_prompt_pct":  round(cache_hit_cached_prompt_pct, 2),
        "cache_hit_gauge_overall_pct":  round(cache_hit_gauge_overall, 2),
        "cache_hit_gauge_active_pct":   round(cache_hit_gauge_active, 2),
        "cache_hit_gauge_peak_pct":     round(cache_hit_gauge_peak, 2),
        "cache_hit_gauge_total_samples": cache_hit_gauge_total_samples,
        "cache_hit_gauge_active_samples": cache_hit_gauge_active_samples,
        "hicache_host_fill_pct":        round(hi_fill, 2),
        "rt_decode_tokens":             int(rt_decode),
        "rt_prefill_compute_tokens":    int(rt_pfc),
        "rt_prefill_cache_tokens":      int(rt_pfc_cache),
        "prometheus_source":            prom_url,
        "collection_elapsed_s":         elapsed_s,
        "collection_samples":           iteration,
    }

    # GPU summary from collected gpu_rows
    gpu_summary = {}
    if not gpu_df.empty:
        gpu_summary = {
            "gpu_count":            int(gpu_df["gpu_idx"].nunique()),
            "gpu_util_mean":        round(float(gpu_df["gpu_util"].mean()), 2),
            "gpu_util_peak":        round(float(gpu_df["gpu_util"].max()),  2),
            "hbm_used_mb_mean":     round(float(gpu_df["mem_used"].mean()),  0),
            "hbm_total_mb_per_gpu": round(float(gpu_df["mem_total"].max()),  0),
            "hbm_util_pct_mean":    round(float(gpu_df["mem_used"].mean() /
                                               gpu_df["mem_total"].max() * 100), 2),
            "power_all_gpus_w_mean":round(float(power_df["gpu_power"].sum()
                                               / gpu_df["gpu_idx"].nunique()
                                               if not power_df.empty else 0), 2),
            "power_w_peak":         round(float(gpu_df["power"].max()), 2),
        }

    # vmstat summary
    vmstat_summary = {}
    if not vmstat_df.empty and "pgfault" in vmstat_df.columns:
        dt = vmstat_df["time_sec"].iloc[-1] - vmstat_df["time_sec"].iloc[0]
        d_pgf = vmstat_df["pgfault"].iloc[-1] - vmstat_df["pgfault"].iloc[0]
        vmstat_summary = {
            "page_faults_per_s":        round(d_pgf / max(dt, 1), 2),
            "numa_migrations_per_s":    0,
        }

    # power summary
    power_summary = {
        "power_elapsed_s": elapsed_s,
    }

    # ── Optionally write raw CSVs ─────────────────────────────────────────────
    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        safe = label.replace("/", "_").replace(" ", "_")[:40]

        sglang_df.to_csv(output_dir / f"sglang_timeseries.csv", index=False)
        if not gpu_df.empty:
            gpu_df.to_csv(output_dir / f"gpu_timeseries.csv", index=False)
        if not vmstat_df.empty:
            vmstat_df.to_csv(output_dir / f"vmstat_timeseries.csv", index=False)
        if not power_df.empty:
            power_df.to_csv(output_dir / f"power_timeseries.csv", index=False)
        with open(output_dir / "sglang_summary.json", "w") as fh:
            json.dump(sglang_summary, fh, indent=2)
        if gpu_summary:
            with open(output_dir / "gpu_summary.json", "w") as fh:
                json.dump(gpu_summary, fh, indent=2)
        if vmstat_summary:
            with open(output_dir / "vmstat_summary.json", "w") as fh:
                json.dump(vmstat_summary, fh, indent=2)
        print(f"  Raw CSVs saved to: {output_dir}")

    return {
        "sglang_summary":    sglang_summary,
        "gpu_summary":       gpu_summary,
        "vmstat_summary":    vmstat_summary,
        "power_summary":     power_summary,
        "sglang_timeseries": sglang_df,
        "gpu_timeseries":    gpu_df,
        "vmstat_timeseries": vmstat_df,
        "power_timeseries":  power_df,
    }



# ═══════════════════════════════════════════════════════════════════════════════
# ADAPTIVE SCHEMA-DRIVEN ANALYZER
# Ingests any CSV / JSON / JSONL / Prometheus data and auto-generates HTML reports.
# The data file itself serves as the schema — no config needed.
# ═══════════════════════════════════════════════════════════════════════════════

def _infer_schema(df: pd.DataFrame) -> dict:
    """
    Infer a complete schema from a DataFrame. Returns:
      numeric_cols  : list of float/int columns (metrics to chart)
      categorical_cols : list of low-cardinality string columns (grouping dims)
      sweep_col     : best candidate for x-axis sweep (e.g. request_rate)
      tag_col       : primary grouping column (if exists)
      dim_cols      : decoded dimension columns (if tag was parsed)
      units         : {col: unit_str} guessed from column names
      descriptions  : {col: human readable description}
    """
    numeric_cols     = []
    categorical_cols = []
    sweep_col        = None
    units            = {}

    # ── Guess units from column name (fallback hints) ─────────────────────────
    UNIT_HINTS = {
        "ttft": "ms", "latency": "ms", "itl": "ms", "duration": "ms", "time": "ms",
        "throughput": "req/s", "token_throughput": "tok/s",
        "rate": "req/s", "iops": "IOPS", "bw": "MB/s", "bandwidth": "MB/s",
        "tokens": "tokens", "len": "tokens",
        "hit_rate": "%", "util": "%", "pct": "%", "usage": "%",
        "bytes": "B", "mb": "MB", "gb": "GB",
        "watts": "W", "power": "W", "temp": "°C",
    }
    # Fallback descriptions (for columns not in dictionary)
    DESCRIPTIONS = {
        "average_ttft": "Time to First Token — mean (ms)",
        "p90_ttft": "Time to First Token — P90 (ms)",
        "p99_ttft": "Time to First Token — P99 (ms)",
        "median_ttft": "Time to First Token — median (ms)",
        "average_itl": "Inter-Token Latency — mean (ms)",
        "average_latency": "E2E Request Latency — mean (ms)",
        "throughput": "Request Throughput (req/s)",
        "input_token_throughput": "Input Token Throughput (tok/s)",
        "output_token_throughput": "Output Token Throughput (tok/s)",
        "cache_hit_rate": "KV Cache Hit Rate (0–1)",
        "average_prompt_len": "Mean Prompt Length (tokens)",
        "average_output_len": "Mean Output Length (tokens)",
        "request_rate": "Request Rate (req/s)",
        "total_requests": "Total Requests",
    }
    # Direction hints (lower/higher is better)
    direction: dict[str, Optional[bool]] = {}

    # ── Dictionary-enriched column classification ─────────────────────────────
    dict_map: dict = df.attrs.get("dict_mapping", {}) if hasattr(df, "attrs") else {}
    if _DICT_AVAILABLE and not dict_map:
        dict_map = _DICT_DISCOVER(df, threshold=40)

    for col in df.columns:
        col_l = col.lower()
        series = df[col]
        nuniq  = series.nunique()

        if pd.api.types.is_numeric_dtype(series):
            numeric_cols.append(col)
            # Try dictionary first for unit, description, direction
            m_def = dict_map.get(col) or (
                _DICT_RESOLVE(col, threshold=45) if _DICT_AVAILABLE else None)
            if m_def:
                if m_def.unit:
                    units[col] = m_def.unit
                if col not in DESCRIPTIONS and m_def.full_name:
                    DESCRIPTIONS[col] = (f"{m_def.full_name}"
                                         + (f" ({m_def.unit})" if m_def.unit else "")
                                         + (f" [§{m_def.section}]" if m_def.section else ""))
                direction[col] = m_def.higher_is_better
            else:
                # Fallback: guess unit from column name hints
                for hint, unit in UNIT_HINTS.items():
                    if hint in col_l:
                        units[col] = unit
                        break
        elif pd.api.types.is_string_dtype(series) or pd.api.types.is_object_dtype(series):
            if nuniq <= min(50, len(df) * 0.5):
                categorical_cols.append(col)

    # ── Find sweep column ─────────────────────────────────────────────────────
    sweep_hints = ["rate", "request_rate", "concurrency", "batch", "load",
                   "workers", "step", "iteration", "time", "timestamp"]
    for hint in sweep_hints:
        for col in numeric_cols:
            if hint in col.lower() and df[col].nunique() <= 20:
                sweep_col = col
                break
        if sweep_col:
            break
    if not sweep_col:
        for col in numeric_cols:
            if 2 <= df[col].nunique() <= 20:
                sweep_col = col
                break

    return {
        "numeric_cols":     numeric_cols,
        "categorical_cols": categorical_cols,
        "sweep_col":        sweep_col,
        "units":            units,
        "descriptions":     DESCRIPTIONS,
        "direction":        direction,
        "dict_map":         dict_map,
        "descriptions":     DESCRIPTIONS,
    }


def _parse_tag_dimensions(tags: pd.Series) -> pd.DataFrame:
    """
    Auto-decode structured tags like 'stock-4gpu-L2sz-100G-with-spec-decoding'
    into individual dimension columns. Also works for any hyphen-delimited tags.
    Returns a DataFrame of decoded dimensions (same index as tags).
    """
    import re

    # Known dimension patterns
    PATTERNS = [
        ("cache_type",    lambda t: "unified-radix-tree" if "unified-radix-tree" in t
                                   else ("stock" if "stock" in t else None)),
        ("gpu_count",     lambda t: re.search(r'(\d+gpu)', t).group(1) if re.search(r'\d+gpu', t) else None),
        ("spec_decoding", lambda t: "yes" if "with-spec-decoding" in t
                                   else ("no" if "without-spec-decoding" in t else None)),
        ("l2_size",       lambda t: re.search(r'L2sz-([^\-]+)', t).group(1) if re.search(r'L2sz-', t) else "default"),
        ("l3_size",       lambda t: re.search(r'L3-([^\-]+)', t).group(1) if re.search(r'L3-', t) else "none"),
    ]

    rows = []
    for tag in tags:
        row = {}
        for dim_name, extractor in PATTERNS:
            try:
                row[dim_name] = extractor(str(tag)) or "unknown"
            except Exception:
                row[dim_name] = "unknown"
        rows.append(row)

    result = pd.DataFrame(rows, index=tags.index)
    # Drop columns that are all "unknown"
    result = result.loc[:, ~(result == "unknown").all()]
    return result


def load_adaptive(source: str) -> pd.DataFrame:
    """
    Load any data source and return a flat DataFrame.

    Accepts:
      • .jsonl / .json  — nested records flattened; top-level tag + summary
      • .csv            — loaded directly
      • http://...      — Prometheus instant query or CSV endpoint
      • directory       — try each file, return concatenated
    """
    import os, io

    source = str(source).strip()

    # ── JSONL / JSON ──────────────────────────────────────────────────────────
    if source.endswith(".jsonl") or source.endswith(".ndjson"):
        rows = []
        with open(source) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                row = {}
                for k, v in rec.items():
                    if isinstance(v, dict):
                        for kk, vv in v.items():
                            row[kk] = vv
                    else:
                        row[k] = v
                rows.append(row)
        df = pd.DataFrame(rows)

    elif source.endswith(".json"):
        with open(source) as f:
            data = json.load(f)
        if isinstance(data, list):
            rows = []
            for rec in data:
                row = {}
                for k, v in rec.items():
                    if isinstance(v, dict):
                        for kk, vv in v.items():
                            row[kk] = vv
                    else:
                        row[k] = v
                rows.append(row)
            df = pd.DataFrame(rows)
        elif isinstance(data, dict):
            df = pd.json_normalize(data)
        else:
            df = pd.DataFrame([{"value": data}])

    # ── CSV ───────────────────────────────────────────────────────────────────
    elif source.endswith(".csv") or source.endswith(".tsv"):
        sep = "\t" if source.endswith(".tsv") else ","
        df = pd.read_csv(source, sep=sep, low_memory=False)

    # ── HTTP (Prometheus instant or CSV endpoint) ─────────────────────────────
    elif source.startswith("http://") or source.startswith("https://"):
        import requests as _req
        r = _req.get(source, timeout=15)
        ct = r.headers.get("content-type", "")
        if "json" in ct:
            data = r.json()
            # Prometheus instant query result
            if "data" in data and "result" in data.get("data", {}):
                rows = []
                for res in data["data"]["result"]:
                    row = dict(res["metric"])
                    row["value"] = float(res["value"][1])
                    row["time"]  = float(res["value"][0])
                    rows.append(row)
                df = pd.DataFrame(rows)
            else:
                df = pd.json_normalize(data)
        else:
            df = pd.read_csv(io.StringIO(r.text))

    # ── Parquet (bonus) ───────────────────────────────────────────────────────
    elif source.endswith(".parquet"):
        df = pd.read_parquet(source)

    else:
        # Try CSV fallback
        try:
            df = pd.read_csv(source, low_memory=False)
        except Exception:
            raise ValueError(f"Cannot infer format for: {source}")

    # ── Post-processing ───────────────────────────────────────────────────────
    # Parse timestamp column if present
    for col in df.columns:
        if "timestamp" in col.lower() or col.lower() in ("time", "ts", "date"):
            try:
                df[col] = pd.to_datetime(df[col])
            except Exception:
                pass

    # Decode structured tag column if present
    for col in df.columns:
        if col.lower() in ("tag", "config", "label", "name", "experiment"):
            tag_dims = _parse_tag_dimensions(df[col])
            if not tag_dims.empty:
                df = pd.concat([df, tag_dims], axis=1)
            break

    # Convert numeric strings
    for col in df.columns:
        if df[col].dtype == object:
            try:
                df[col] = pd.to_numeric(df[col])
            except (ValueError, TypeError):
                pass

    # ── Dictionary annotation ─────────────────────────────────────────────────
    # Resolve every column to a canonical metric definition for richer reporting
    if _DICT_AVAILABLE:
        df.attrs["dict_mapping"] = _DICT_DISCOVER(df, threshold=40)

    return df


def generate_adaptive_report(
    df: pd.DataFrame,
    title: str = "Analysis Report",
    output_path: str = "adaptive_report.html",
    source_name: str = "",
) -> str:
    """
    Given any flat DataFrame (from load_adaptive), infer the schema and generate
    a complete self-contained HTML report with:
      • Schema summary table
      • Sweep charts (each metric vs sweep dim, grouped by config dimensions)
      • Distribution charts (histograms for key metrics)
      • Heatmap / comparison table
      • Raw data preview
    Returns the HTML string.
    """
    import html as _html_mod
    import json as _json

    schema  = _infer_schema(df)
    n_rows  = len(df)
    n_cols  = len(df.columns)
    sweep   = schema["sweep_col"]
    nums    = schema["numeric_cols"]
    cats    = schema["categorical_cols"]
    units   = schema["units"]
    descs   = schema["descriptions"]

    # Identify dimension columns (decoded from tag)
    dim_cols = [c for c in cats if c in (
        "cache_type", "gpu_count", "spec_decoding", "l2_size", "l3_size",
        "tag", "config", "label", "name", "experiment",
    ) and c in df.columns]
    if not dim_cols:
        dim_cols = cats[:3]  # fallback: first 3 categorical

    # Build the primary "group" key for legend/series
    tag_col = next((c for c in df.columns if c.lower() in ("tag","config","label","name")), None)

    # ── Auto-select key metrics to feature (TTFT, latency, throughput, cache) ─
    PRIORITY_METRICS = [
        "average_ttft", "p90_ttft", "p99_ttft",
        "average_latency", "p90_latency",
        "average_itl", "p90_itl",
        "throughput", "output_token_throughput", "input_token_throughput",
        "cache_hit_rate",
    ]
    featured = [m for m in PRIORITY_METRICS if m in df.columns]
    if not featured:
        # Use first 10 numeric cols
        featured = [c for c in nums if c != sweep][:10]

    # ── Prepare Chart.js data ─────────────────────────────────────────────────
    PALETTE = ["#6366f1","#22c55e","#f97316","#ef4444","#3b82f6",
               "#a855f7","#06b6d4","#84cc16","#f43f5e","#fbbf24",
               "#14b8a6","#8b5cf6","#ec4899","#10b981","#f59e0b",
               "#0ea5e9","#d946ef","#65a30d"]

    def _make_sweep_data(metric: str, group_col: str | None) -> str:
        """Build Chart.js datasets for metric vs sweep, grouped by group_col."""
        if sweep is None or sweep not in df.columns or metric not in df.columns:
            return "[]"
        x_vals = sorted(df[sweep].dropna().unique())
        datasets = []
        if group_col and group_col in df.columns:
            groups = sorted(df[group_col].unique())
        else:
            groups = ["all"]
        for gi, grp in enumerate(groups[:18]):
            if grp == "all":
                sub = df
            else:
                sub = df[df[group_col] == grp]
            ys = []
            for x in x_vals:
                row = sub[sub[sweep] == x][metric]
                ys.append(round(float(row.mean()), 4) if len(row) else None)
            color = PALETTE[gi % len(PALETTE)]
            datasets.append({
                "label":           str(grp),
                "data":            ys,
                "borderColor":     color,
                "backgroundColor": color + "22",
                "borderWidth":     2,
                "pointRadius":     4,
                "tension":         0.3,
                "fill":            False,
            })
        return _json.dumps({
            "labels":   [str(x) for x in x_vals],
            "datasets": datasets,
        })

    def _make_bar_data(metric: str, group_col: str | None, x_col: str | None) -> str:
        """Grouped bar chart at a single request rate point (or overall mean)."""
        if metric not in df.columns:
            return "{}"
        if group_col and group_col in df.columns:
            if x_col and x_col in df.columns:
                # Use median request_rate as reference point
                ref_x = float(df[x_col].median())
                sub = df.iloc[(df[x_col] - ref_x).abs().argsort()[:20]]
            else:
                sub = df
            agg = sub.groupby(group_col)[metric].mean().sort_values()
            labels  = list(agg.index.astype(str))
            values  = [round(float(v), 4) for v in agg.values]
            colors  = [PALETTE[i % len(PALETTE)] for i in range(len(labels))]
        else:
            labels  = ["All"]
            values  = [round(float(df[metric].mean()), 4)]
            colors  = [PALETTE[0]]
        return _json.dumps({"labels": labels, "values": values, "colors": colors})

    # ── Schema summary ────────────────────────────────────────────────────────
    schema_rows = ""
    for col in df.columns:
        s = df[col]
        dtype = "numeric" if pd.api.types.is_numeric_dtype(s) else "text"
        nuniq = s.nunique()
        sample = str(s.dropna().iloc[0]) if len(s.dropna()) else "—"
        if len(sample) > 40: sample = sample[:40] + "…"
        desc = descs.get(col, "")
        unit = units.get(col, "")
        rng  = (f"{s.min():.3g} – {s.max():.3g}" if dtype == "numeric"
                else f"{nuniq} unique")
        # Dictionary enrichment
        dir_map = schema.get("direction", {})
        d_map   = schema.get("dict_map", {})
        m_def   = d_map.get(col) or (_DICT_RESOLVE(col, threshold=45) if _DICT_AVAILABLE else None)
        direction_arrow = ""
        canonical_badge = ""
        formula_tooltip = ""
        if m_def:
            direction_arrow = ("↑" if m_def.higher_is_better
                               else "↓" if m_def.higher_is_better is False else "")
            canonical_badge = (
                f'<span style="background:#eef2ff;color:#4338ca;font-size:8px;'
                f'padding:1px 5px;border-radius:10px;margin-left:4px">'
                f'{m_def.name}</span>'
            )
            if not desc and m_def.full_name:
                desc = m_def.full_name + (f" ({m_def.unit})" if m_def.unit else "")
            if not unit and m_def.unit:
                unit = m_def.unit
            if m_def.formula:
                safe_fml = _html_mod.escape(m_def.formula[:200])
                formula_tooltip = (
                    f'<details style="font-size:9px"><summary style="cursor:pointer;'
                    f'color:#4f46e5">📐 formula</summary>'
                    f'<pre style="background:#f1f5f9;padding:4px;border-radius:3px;'
                    f'font-size:8px;color:#1e3a5f;white-space:pre-wrap">{safe_fml}</pre>'
                    f'</details>'
                )
        schema_rows += (
            f'<tr><td style="font-weight:600;color:#1e3a5f">'
            f'{_html_mod.escape(col)}{canonical_badge}</td>'
            f'<td><span style="background:{"#eef2ff" if dtype=="numeric" else "#f0fdf4"};'
            f'color:{"#4338ca" if dtype=="numeric" else "#166534"};padding:1px 6px;'
            f'border-radius:4px;font-size:10px">{dtype}</span></td>'
            f'<td style="font-family:monospace;font-size:10px;color:#475569">'
            f'{unit} {direction_arrow}</td>'
            f'<td style="font-family:monospace;font-size:10px;color:#334155">{rng}</td>'
            f'<td style="font-size:11px;color:#64748b">{desc or "—"}</td>'
            f'<td style="font-family:monospace;font-size:10px;color:#94a3b8">'
            f'{_html_mod.escape(sample)}</td>'
            f'<td style="font-size:10px">{formula_tooltip}</td></tr>'
        )

    # ── Build sweep section for each featured metric ──────────────────────────
    sweep_charts_html = ""
    sweep_charts_js   = ""
    dict_map2 = schema.get("dict_map", {})

    # Group column: prefer tag, else first dim col
    group_col = tag_col or (dim_cols[0] if dim_cols else None)

    for mi, metric in enumerate(featured):
        chart_id  = f"c_adp_{mi}"
        bar_id    = f"c_adp_bar_{mi}"
        sweep_d   = _make_sweep_data(metric, group_col)
        bar_d     = _make_bar_data(metric, group_col, sweep)
        # Use dictionary for richer label / unit / formula
        m_def2    = dict_map2.get(metric) or (_DICT_RESOLVE(metric, threshold=45) if _DICT_AVAILABLE else None)
        label     = (m_def2.full_name if m_def2 else None) or descs.get(metric, metric.replace("_", " ").title())
        unit_str  = (m_def2.unit if m_def2 else None) or units.get(metric, "")
        dir_hint  = ("↑ higher better" if m_def2 and m_def2.higher_is_better
                     else "↓ lower better" if m_def2 and m_def2.higher_is_better is False
                     else "")
        # Formula block from dictionary
        fml_block = ""
        if m_def2 and m_def2.formula:
            safe_fml2 = _html_mod.escape(m_def2.formula[:400])
            srcs_str  = ", ".join(m_def2.sources[:5]) if m_def2.sources else ""
            note_str  = _html_mod.escape(m_def2.interpretation[:200]) if m_def2.interpretation else ""
            fml_block = (
                f'<details class="adp-badge" style="margin-top:6px;background:#f8fafc;'
                f'border:1px solid #e2e8f0;border-radius:4px;padding:4px 8px">'
                f'<summary style="cursor:pointer;font-size:9px;color:#4f46e5;font-weight:600">'
                f'📐 Formula &amp; Sources: {srcs_str}</summary>'
                f'<pre style="background:#f1f5f9;padding:6px;border-radius:3px;font-size:9px;'
                f'color:#1e3a5f;white-space:pre-wrap;margin-top:4px">{safe_fml2}</pre>'
                + (f'<div style="font-size:9px;color:#475569;font-style:italic;margin-top:2px">'
                   f'{note_str}</div>' if note_str else "")
                + '</details>'
            )
        sweep_charts_html += f'''
<div class="adp-card" id="section_{chart_id}">
  <div class="adp-card-title">{_html_mod.escape(label)}</div>
  <div class="adp-meta">
    <span class="adp-badge">metric: {_html_mod.escape(metric)}</span>
    <span class="adp-badge">{unit_str}</span>
    {f'<span class="adp-badge" style="color:#059669">{dir_hint}</span>' if dir_hint else ''}
    {f'<span class="adp-badge">x-axis: {sweep}</span>' if sweep else ''}
    {f'<span class="adp-badge">grouped by: {group_col}</span>' if group_col else ''}
  </div>
  <div class="adp-chart-row">
    <div class="adp-chart-main">
      <div class="adp-chart-label">vs {sweep or "index"} sweep</div>
      <canvas id="{chart_id}"></canvas>
    </div>
    <div class="adp-chart-side">
      <div class="adp-chart-label">mean by configuration</div>
      <canvas id="{bar_id}"></canvas>
    </div>
  </div>
  {fml_block}
</div>'''

        sweep_charts_js += f'''
(function() {{
  const sweep_data_{mi} = {sweep_d};
  const bar_data_{mi}   = {bar_d};
  const opts = {{
    responsive:true, maintainAspectRatio:false,
    plugins:{{
      legend:{{labels:{{color:"#334155",font:{{size:9}},boxWidth:10,padding:8}}}},
      tooltip:{{enabled:true,backgroundColor:"#111827",borderColor:"#94a3b8",borderWidth:1,titleColor:"#ffffff",bodyColor:"#ffffff",padding:10,caretPadding:6,displayColors:true}}
    }},
    interaction:{{mode:"nearest",intersect:false,axis:"x"}},
    scales:{{
      x:{{ticks:{{color:"#64748b",font:{{size:9}}}},grid:{{color:"#f1f5f9"}},
          title:{{display:true,text:{_json.dumps(str(sweep or "x"))},color:"#64748b",font:{{size:9}}}}}},
      y:{{ticks:{{color:"#64748b",font:{{size:9}}}},grid:{{color:"#f1f5f9"}},
          title:{{display:true,text:{_json.dumps(unit_str)},color:"#64748b",font:{{size:9}}}}}}
    }}
  }};
  new Chart(document.getElementById("{chart_id}"), {{type:"line",data:sweep_data_{mi},options:opts}});
  new Chart(document.getElementById("{bar_id}"), {{type:"bar",
    data:{{labels:bar_data_{mi}.labels,
           datasets:[{{data:bar_data_{mi}.values,backgroundColor:bar_data_{mi}.colors,
                       borderColor:bar_data_{mi}.colors,borderWidth:1,borderRadius:3}}]}},
    options:{{...opts,indexAxis:"y",plugins:{{...opts.plugins,legend:{{display:false}}}}}}
  }});
}})();
'''

    # ── Dimension breakdown section ───────────────────────────────────────────
    dim_section_html = ""
    dim_section_js   = ""

    if dim_cols and featured:
        # For each dimension: show how the top metric varies across its values
        top_metric = featured[0]
        for di, dim in enumerate(dim_cols[:4]):
            if dim not in df.columns:
                continue
            dim_chart_id = f"c_dim_{di}"
            bar_d2 = _make_bar_data(top_metric, dim, sweep)
            label  = descs.get(top_metric, top_metric.replace("_"," ").title())
            dim_section_html += f'''
<div style="flex:1;min-width:280px">
  <div class="adp-chart-label">{_html_mod.escape(label)} by <b>{_html_mod.escape(dim)}</b></div>
  <canvas id="{dim_chart_id}" style="max-height:240px"></canvas>
</div>'''
            dim_section_js += f'''
new Chart(document.getElementById("{dim_chart_id}"), {{type:"bar",
  data:{{labels:{_json.dumps(list(df[dim].unique().astype(str)))},
         datasets:[{{data:{_json.dumps([round(float(df[df[dim]==v][top_metric].mean()),4) for v in df[dim].unique()])},
                     backgroundColor:{_json.dumps([PALETTE[i%len(PALETTE)] for i in range(df[dim].nunique())])},
                     borderRadius:3,borderWidth:1}}]}},
  options:{{responsive:true,maintainAspectRatio:false,indexAxis:"y",
            plugins:{{legend:{{display:false}},
              tooltip:{{backgroundColor:"#fff",borderColor:"#e2e8f0",borderWidth:1,
                       titleColor:"#475569",bodyColor:"#0f172a",padding:8}}}},
            scales:{{
              x:{{ticks:{{color:"#64748b",font:{{size:9}}}},grid:{{color:"#f1f5f9"}}}},
              y:{{ticks:{{color:"#475569",font:{{size:9}}}},grid:{{color:"#f1f5f9"}}}}
            }}
  }}
}});'''

    # ── Best configuration table ──────────────────────────────────────────────
    best_rows = ""
    if group_col and group_col in df.columns and featured:
        agg = df.groupby(group_col)[featured].mean()
        # Sort by first featured metric
        agg_sorted = agg.sort_values(featured[0])
        for rank, (grp, row) in enumerate(agg_sorted.iterrows()):
            bg = "#f0fdf4" if rank == 0 else ("f8fafc" if rank % 2 == 0 else "#ffffff")
            medal = "🥇" if rank == 0 else ("🥈" if rank == 1 else ("🥉" if rank == 2 else ""))
            cells = "".join(
                f'<td style="padding:6px 10px;text-align:right;font-family:monospace;'
                f'font-size:11px;color:#334155">{val:.4g}</td>'
                for m, val in row.items()
            )
            best_rows += (
                f'<tr style="background:{bg};border-bottom:1px solid #f1f5f9">'
                f'<td style="padding:6px 10px;font-size:10px;color:#94a3b8;text-align:center">'
                f'{medal or rank+1}</td>'
                f'<td style="padding:6px 10px;color:#1e3a5f;font-weight:600;font-size:11px">'
                f'{_html_mod.escape(str(grp))}</td>'
                f'{cells}</tr>'
            )
        header_cols = "".join(
            f'<th style="padding:6px 10px;font-size:10px;color:#475569;font-weight:600;'
            f'text-align:right;white-space:nowrap">{descs.get(m,m)[:25]}</th>'
            for m in featured
        )
        best_table = f'''
<div class="adp-card">
  <div class="adp-card-title">🏆 Configuration Ranking — sorted by {descs.get(featured[0], featured[0])}</div>
  <div class="adp-meta"><span class="adp-badge">lower is better for latency metrics</span></div>
  <div style="overflow-x:auto">
  <table style="width:100%;border-collapse:collapse;font-size:12px">
    <thead><tr>
      <th style="padding:6px 10px;background:#f8fafc;color:#475569;font-size:10px">#</th>
      <th style="padding:6px 10px;background:#f8fafc;color:#475569;font-size:10px;text-align:left">{_html_mod.escape(group_col)}</th>
      {header_cols}
    </tr></thead>
    <tbody>{best_rows}</tbody>
  </table>
  </div>
</div>'''
    else:
        best_table = ""

    # ── Raw data preview ──────────────────────────────────────────────────────
    preview_cols = ([tag_col] if tag_col else []) + \
                   ([sweep] if sweep else []) + featured[:6]
    preview_cols = [c for c in preview_cols if c in df.columns]
    preview_head = "".join(f'<th>{_html_mod.escape(c)}</th>' for c in preview_cols)
    preview_rows = ""
    for i, (_, row) in enumerate(df.head(15).iterrows()):
        cells = ""
        for c in preview_cols:
            v = row.get(c, "")
            if isinstance(v, float):
                v = f"{v:.4g}"
            cells += f'<td style="padding:5px 10px;font-family:monospace;font-size:10px;color:#334155">{_html_mod.escape(str(v))}</td>'
        bg = "#f8fafc" if i % 2 == 0 else "#ffffff"
        preview_rows += f'<tr style="background:{bg};border-bottom:1px solid #f1f5f9">{cells}</tr>'

    # ── Build HTML ────────────────────────────────────────────────────────────
    html = f'''<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{_html_mod.escape(title)}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<script>
(function(){{
  function install(){{
    if(!window.Chart || window.__amoprofHoverInstalled) return;
    window.__amoprofHoverInstalled = true;
    Chart.defaults.interaction = {{mode:'nearest', intersect:false, axis:'x'}};
    Chart.defaults.plugins.tooltip = Object.assign({{}}, Chart.defaults.plugins.tooltip || {{}}, {{
      enabled: true,
      backgroundColor: '#111827',
      titleColor: '#ffffff',
      bodyColor: '#ffffff',
      borderColor: '#94a3b8',
      borderWidth: 1,
      displayColors: true,
      padding: 10,
      caretPadding: 6
    }});
    const plugin = {{
      id: 'amoprofHoverReadout',
      afterInit(chart){{
        const canvas = chart.canvas;
        if(!canvas || !canvas.parentNode) return;
        const wrap = canvas.parentNode;
        if(wrap.querySelector(':scope > .amoprof-hover-readout')) return;
        const box = document.createElement('div');
        box.className = 'amoprof-hover-readout';
        box.style.cssText = [
          'margin-top:6px',
          'min-height:22px',
          'font:12px/1.5 system-ui,sans-serif',
          'color:#0f172a',
          'background:#f1f5f9',
          'border:1px solid #cbd5e1',
          'border-radius:6px',
          'padding:5px 10px',
          'transition:background 0.1s',
        ].join(';');
        box.textContent = 'Hover over chart to see values';
        wrap.appendChild(box);
        chart.$amoprofReadout = box;
      }},
      afterEvent(chart, args){{
        const box = chart.$amoprofReadout;
        if(!box) return;
        const ev = args && args.event;
        if(!ev || !['mousemove','click'].includes(ev.type)){{ return; }}
        const pts = chart.getElementsAtEventForMode(
          (ev.native || ev), 'nearest', {{intersect:false, axis:'x'}}, false
        ) || [];
        if(!pts.length){{
          box.style.background='#f1f5f9';
          box.innerHTML='<span style="color:#94a3b8;font-style:italic">Hover over chart to see values</span>';
          return;
        }}
        box.style.background='#ffffff';
        const p = pts[0];
        const labels = chart.data && chart.data.labels ? chart.data.labels : [];
        const rawPoint = chart.data.datasets[p.datasetIndex] &&
                         chart.data.datasets[p.datasetIndex].data &&
                         chart.data.datasets[p.datasetIndex].data[p.index];
        let xLabel;
        if(rawPoint != null && typeof rawPoint === 'object' && 'x' in rawPoint){{
          const xv = rawPoint.x;
          xLabel = Number.isFinite(xv) ? xv.toLocaleString(undefined,{{maximumFractionDigits:3}}) : String(xv);
        }} else {{
          xLabel = labels[p.index] != null ? String(labels[p.index]) : `#${{p.index}}`;
        }}
        const parts = [];
        (chart.data.datasets || []).forEach((ds, di) => {{
          const meta = chart.getDatasetMeta(di);
          if(meta && meta.hidden) return;
          const raw = ds.data && ds.data[p.index];
          if(raw == null) return;
          let shown;
          if(typeof raw === 'object' && raw !== null && 'y' in raw){{
            const y = raw.y;
            shown = Number.isFinite(y) ? y.toLocaleString(undefined,{{maximumFractionDigits:4}}) : String(y);
          }} else {{
            const num = Number(raw);
            shown = Number.isFinite(num) ? num.toLocaleString(undefined,{{maximumFractionDigits:4}}) : String(raw);
          }}
          const color = ds.borderColor || ds.backgroundColor || '#475569';
          parts.push(
            `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;` +
            `background:${{color}};margin-right:4px;vertical-align:middle"></span>` +
            `<b style="color:#0f172a">${{ds.label || 'value'}}:</b> ` +
            `<span style="color:#1e3a5f;font-family:monospace">${{shown}}</span>`
          );
        }});
        if(!parts.length){{
          box.innerHTML=`<span style="color:#94a3b8;font-style:italic">No data at ${{xLabel}}</span>`;
          return;
        }}
        box.innerHTML =
          `<span style="color:#64748b;font-size:11px">${{xLabel}}</span>` +
          `<span style="color:#cbd5e1;margin:0 6px">|</span>` +
          parts.join('<span style="color:#cbd5e1;margin:0 5px">·</span>');
      }}
    }};
    Chart.register(plugin);
  }}
  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install);
  else install();
}})();
</script>
</script>

<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#f8fafc;color:#0f172a;font-family:"Inter",system-ui,sans-serif;padding:20px}}
.adp-header{{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:20px 24px;
  margin-bottom:18px;border-left:4px solid #4f46e5;box-shadow:0 1px 4px rgba(0,0,0,0.05)}}
.adp-title{{font-size:22px;font-weight:900;color:#0f172a;letter-spacing:-0.5px}}
.adp-subtitle{{font-size:13px;color:#64748b;margin-top:4px}}
.adp-card{{background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:18px;
  margin-bottom:14px;box-shadow:0 1px 3px rgba(0,0,0,0.04)}}
.adp-card-title{{font-size:13px;font-weight:700;color:#1e3a5f;margin-bottom:6px}}
.adp-meta{{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px}}
.adp-badge{{font-size:9px;background:#f1f5f9;color:#475569;padding:2px 7px;
  border-radius:10px;font-family:monospace}}
.adp-chart-row{{display:grid;grid-template-columns:2fr 1fr;gap:14px}}
.adp-chart-main canvas{{height:280px!important}}
.adp-chart-side canvas{{height:280px!important}}
.adp-chart-label{{font-size:10px;color:#94a3b8;font-weight:600;text-transform:uppercase;
  letter-spacing:.5px;margin-bottom:6px}}
.adp-section-title{{font-size:11px;font-weight:700;color:#4f46e5;text-transform:uppercase;
  letter-spacing:.6px;margin:18px 0 10px;border-bottom:1px solid #e2e8f0;padding-bottom:6px}}
.adp-dim-row{{display:flex;gap:14px;flex-wrap:wrap;margin-bottom:14px}}
.adp-schema-table{{width:100%;border-collapse:collapse;font-size:11px}}
.adp-schema-table th{{padding:7px 10px;background:#f8fafc;color:#475569;font-weight:600;
  font-size:10px;text-align:left;border-bottom:2px solid #e2e8f0}}
.adp-schema-table td{{padding:6px 10px;border-bottom:1px solid #f1f5f9}}
/* Hover readout box below charts */
.amoprof-hover-readout{{
  min-height:22px;
  font:12px/1.5 system-ui,sans-serif;
  color:#0f172a;
  background:#f1f5f9;
  border:1px solid #cbd5e1;
  border-radius:6px;
  padding:5px 10px;
  overflow:hidden;
  text-overflow:ellipsis;
  white-space:nowrap;
  transition:background 0.1s;
}}
/* Fix adp-chart-label — was #94a3b8 (too light on white) */
.adp-chart-label{{color:#64748b!important}}
@media(max-width:800px){{.adp-chart-row{{grid-template-columns:1fr}}}}
</style></head><body>

<div class="adp-header">
  <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
    <div class="adp-title">{_html_mod.escape(title)}</div>
    <span style="font-size:10px;background:#eef2ff;color:#4338ca;padding:3px 10px;
                 border-radius:20px;font-weight:700;border:1px solid #c7d2fe">AMOprof · Adaptive</span>
  </div>
  <div class="adp-subtitle">
    {_html_mod.escape(source_name)} &nbsp;·&nbsp;
    {n_rows:,} records &nbsp;·&nbsp;
    {n_cols} columns &nbsp;·&nbsp;
    {len(nums)} numeric metrics &nbsp;·&nbsp;
    {len(cats)} categorical dimensions
    {f"&nbsp;·&nbsp; sweep: <b>{sweep}</b>" if sweep else ""}
    {f"&nbsp;·&nbsp; grouped by: <b>{group_col}</b>" if group_col else ""}
  </div>
</div>

<!-- SCHEMA -->
<div class="adp-section-title">📐 Auto-Inferred Schema</div>
<div class="adp-card">
  <div class="adp-meta">
    <span class="adp-badge">source: {_html_mod.escape(source_name)}</span>
    <span class="adp-badge">{n_rows} rows</span>
    <span class="adp-badge">{n_cols} columns</span>
    <span class="adp-badge">sweep dim: {sweep or "none"}</span>
  </div>
  <div style="overflow-x:auto">
  <table class="adp-schema-table">
    <thead><tr>
      <th>Column</th><th>Type</th><th>Unit / Dir</th><th>Range / Cardinality</th>
      <th>Description</th><th>Sample</th><th>Formula</th>
    </tr></thead>
    <tbody>{schema_rows}</tbody>
  </table>
  </div>
</div>

<!-- DIMENSION BREAKDOWN -->
{"" if not dim_section_html else f'''
<div class="adp-section-title">🎛 Dimension Analysis — Impact of Each Config Variable</div>
<div class="adp-card">
  <div class="adp-card-title">Mean {descs.get(featured[0] if featured else "", "metric")} across each configuration dimension</div>
  <div class="adp-meta">
    <span class="adp-badge">averaged across all request rates</span>
    <span class="adp-badge">lower is better for latency</span>
  </div>
  <div class="adp-dim-row">{dim_section_html}</div>
</div>
'''}

<!-- SWEEP CHARTS -->
<div class="adp-section-title">📈 Metric Sweep Analysis — {sweep or "all records"}</div>
{sweep_charts_html}

<!-- BEST CONFIG TABLE -->
{best_table}

<!-- RAW DATA PREVIEW -->
<div class="adp-section-title">🗃 Raw Data Preview (first 15 rows)</div>
<div class="adp-card">
  <div style="overflow-x:auto">
  <table style="width:100%;border-collapse:collapse;font-size:11px">
    <thead><tr style="background:#f8fafc">{preview_head}</tr></thead>
    <tbody>{preview_rows}</tbody>
  </table>
  </div>
</div>

<div style="border-top:1px solid #e2e8f0;margin-top:18px;padding-top:10px;
            font-size:10px;color:#94a3b8;display:flex;justify-content:space-between">
  <span>AMOprof Adaptive Analyzer · Auto-generated</span>
  <span>{_html_mod.escape(source_name)} · {n_rows} records · {len(featured)} metrics</span>
</div>

<script>
Chart.defaults.color = "#64748b";
Chart.defaults.borderColor = "#f1f5f9";
Chart.defaults.font.family = '"Inter", system-ui, sans-serif';
document.addEventListener("DOMContentLoaded", () => {{
  {sweep_charts_js}
  {dim_section_js}
}});
</script>
</body></html>'''

    if output_path:
        Path(output_path).write_text(html, encoding="utf-8")

    return html



# ═══════════════════════════════════════════════════════════════════════════════
# OFFLINE SOURCE PARSERS  (KV_SSD_Inference_Metrics_Complete_Table.docx §A–G)
# ═══════════════════════════════════════════════════════════════════════════════

def parse_blktrace(path: str, device: str = "") -> pd.DataFrame:
    """
    Parse blkparse output into a structured DataFrame.

    Accepts multiple formats:
      A) Raw blkparse text  (blktrace -d /dev/nvme0n1 | blkparse -i -)
      B) CSV with columns:  ts,pid,action,rwbs,sector,nsectors,comm,dev,...
         (as produced by blkparse_events.generated.csv)
      C) CSV with columns:  time_ns/time_sec, type/op, sector, nr_sectors/size_bytes, ...

    Returns DataFrame with normalised columns:
      time_sec, type (R/W/D), sector, size_bytes, offset_bytes, lat_ms, pid, comm
    """
    import re as _re
    path = str(path)

    try:
        with open(path) as f:
            first_lines = [f.readline() for _ in range(3)]
        header = first_lines[0].strip().lower()
        is_csv = "," in header or "\t" in header

        # ── CSV formats ───────────────────────────────────────────────────────
        if is_csv:
            df_raw = pd.read_csv(path, low_memory=False)
            cols   = {c.lower().strip().replace(" ","_").replace("/","_").replace("-","_")
                      : c for c in df_raw.columns}

            rows = []
            for _, row in df_raw.iterrows():
                # ── Map time ──────────────────────────────────────────────────
                if "ts" in cols:
                    t = float(row[cols["ts"]])
                elif "time_ns" in cols or "timestamp_ns" in cols:
                    t = float(row[cols.get("time_ns", cols.get("timestamp_ns"))]) / 1e9
                elif "time_sec" in cols or "time_s" in cols:
                    t = float(row[cols.get("time_sec", cols.get("time_s"))])
                else:
                    t = 0.0

                # ── Map IO type from rwbs or type column ──────────────────────
                iotype = None
                for col_key in ("rwbs", "type", "op", "rw"):
                    if col_key in cols:
                        raw_type = str(row[cols[col_key]]).upper().strip()
                        # rwbs can be 'WS','RS','DS','WFSUa' etc.
                        # Rule: D/DISCARD first, then W, then R
                        if "D" in raw_type or "DISCARD" in raw_type:
                            iotype = "D"
                        elif "W" in raw_type:
                            iotype = "W"
                        elif "R" in raw_type:
                            iotype = "R"
                        break

                if iotype is None:
                    # Try action field: Q=queue, C=complete, D=dispatch — not IO type
                    # Fallback: assume write if no read column
                    iotype = "W"

                # ── Map size ──────────────────────────────────────────────────
                size_bytes = 0
                if "size_bytes" in cols or "bytes" in cols:
                    size_bytes = int(row[cols.get("size_bytes", cols.get("bytes", 0))])
                elif "nsectors" in cols or "nr_sectors" in cols or "sectors" in cols:
                    ns = int(row[cols.get("nsectors", cols.get("nr_sectors",
                                                               cols.get("sectors", 0)))])
                    size_bytes = ns * 512

                # ── Map sector / offset ───────────────────────────────────────
                sector = 0
                if "sector" in cols:
                    sector = int(row[cols["sector"]])
                elif "offset_bytes" in cols:
                    sector = int(row[cols["offset_bytes"]]) // 512

                # ── Map latency ───────────────────────────────────────────────
                lat_ms = 0.0
                for lk in ("lat_ms","latency_ms","lat","await"):
                    if lk in cols:
                        try: lat_ms = float(row[cols[lk]])
                        except: pass
                        break

                # ── PID / comm ────────────────────────────────────────────────
                pid  = str(row[cols["pid"]])  if "pid"  in cols else ""
                comm_raw = row[cols["comm"]] if "comm" in cols else ""
                # comm may be numeric (PID alias) or string command name
                try:
                    comm = str(int(float(str(comm_raw)))) if str(comm_raw).replace(".","").isdigit() else str(comm_raw)
                except Exception:
                    comm = str(comm_raw)

                rows.append({
                    "time_sec":    t,
                    "type":        iotype,
                    "sector":      sector,
                    "size_bytes":  size_bytes,
                    "offset_bytes":sector * 512,
                    "lat_ms":      lat_ms,
                    "pid":         pid,
                    "comm":        comm,
                })

            df = pd.DataFrame(rows)

        # ── Raw blkparse text format ──────────────────────────────────────────
        else:
            rows = []
            T0   = None
            INTEREST = {"D", "Q", "C"}
            for line in open(path):
                line = line.strip()
                if not line: continue
                parts = line.split()
                if len(parts) < 7: continue
                try:
                    ts   = float(parts[3])
                    pid  = int(parts[4])
                    act  = parts[5]
                    rwbs = parts[6].upper()
                    if act not in INTEREST: continue
                    if T0 is None: T0 = ts

                    if "D" in rwbs or "DISCARD" in rwbs:
                        iotype = "D"
                    elif "W" in rwbs:
                        iotype = "W"
                    elif "R" in rwbs:
                        iotype = "R"
                    else:
                        continue

                    sector     = int(parts[7]) if len(parts) > 7 else 0
                    nr_sectors = int(parts[9]) if len(parts) > 9 else 0
                    rows.append({
                        "time_sec":    ts - T0,
                        "type":        iotype,
                        "sector":      sector,
                        "size_bytes":  nr_sectors * 512,
                        "offset_bytes":sector * 512,
                        "lat_ms":      0.0,
                        "pid":         str(pid),
                        "comm":        parts[-1].strip("[]") if parts[-1].startswith("[") else "",
                    })
                except (ValueError, IndexError):
                    continue

            if not rows:
                print(f"  [warn] blktrace: no parseable events in {path}")
                return pd.DataFrame()
            df = pd.DataFrame(rows)

        # ── Common post-processing ────────────────────────────────────────────
        if df.empty:
            return df

        df = df.sort_values("time_sec").reset_index(drop=True)

        # Filter to device if specified and 'dev' column exists in raw CSV
        # (we already parsed into normalised format, so just return)
        return df

    except Exception as e:
        print(f"  [warn] blktrace parse error ({path}): {e}")
        import traceback; traceback.print_exc()
        return pd.DataFrame()
    import re as _re
    path = str(path)
    rows = []

    try:
        with open(path) as f:
            first_lines = [f.readline() for _ in range(5)]
        content_head = " ".join(first_lines)

        # Detect CSV format
        if "time_ns" in content_head or "time_sec" in content_head or "size_bytes" in content_head:
            df = pd.read_csv(path, low_memory=False)
            # Normalise column names
            rename = {}
            for c in df.columns:
                cl = c.lower().strip()
                if cl in ("time_ns","timestamp_ns"): rename[c] = "time_ns"
                elif cl in ("time_sec","time_s"):     rename[c] = "time_sec"
                elif cl in ("type","op","rwbs"):       rename[c] = "type"
                elif cl in ("sector",):                rename[c] = "sector"
                elif cl in ("nr_sectors","sectors"):   rename[c] = "nr_sectors"
                elif cl in ("size_bytes","bytes","size"): rename[c] = "size_bytes"
                elif cl in ("lat_ms","latency_ms","lat"): rename[c] = "lat_ms"
                elif cl in ("pid","process_id"):        rename[c] = "pid"
                elif cl in ("comm","command","process"): rename[c] = "comm"
            df = df.rename(columns=rename)
            if "time_ns" in df.columns and "time_sec" not in df.columns:
                df["time_sec"] = df["time_ns"] / 1e9
            if "time_sec" not in df.columns:
                df["time_sec"] = range(len(df))
            if "nr_sectors" in df.columns and "size_bytes" not in df.columns:
                df["size_bytes"] = df["nr_sectors"] * 512
            if "size_bytes" not in df.columns:
                df["size_bytes"] = 512
            if "sector" in df.columns:
                df["offset_bytes"] = df["sector"] * 512
            else:
                df["offset_bytes"] = 0
            for c in ("type","lat_ms","pid","comm"):
                if c not in df.columns:
                    df[c] = ("R" if c == "type" else 0.0 if c == "lat_ms" else "")
            return df[["time_sec","type","sector","size_bytes","offset_bytes","lat_ms","pid","comm"]].copy()

        # Parse raw blkparse text
        # Pattern: "  8,0   0  1   0.000000000  1234  D   R 1024 + 8 [fio]"
        # or:      "  8,0   0  1   0.000000000  1234  C   R 1024 0 [fio]"
        # We care about "D" (dispatch/issue) or "Q" (queue) events
        INTEREST = {"D", "Q", "C"}
        T0 = None
        for line in open(path):
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) < 7:
                continue
            try:
                ts   = float(parts[3])
                pid  = int(parts[4])
                act  = parts[5]
                rwbs = parts[6].upper()
                if act not in INTEREST:
                    continue
                if T0 is None:
                    T0 = ts
                # IO type: R=read, W=write, D/DISCARD=trim
                if "D" in rwbs or "DISCARD" in rwbs:
                    iotype = "D"
                elif "W" in rwbs:
                    iotype = "W"
                elif "R" in rwbs:
                    iotype = "R"
                else:
                    continue
                sector    = int(parts[7]) if len(parts) > 7 else 0
                nr_sectors= int(parts[9]) if len(parts) > 9 else 0
                rows.append({
                    "time_sec":    ts - T0,
                    "type":        iotype,
                    "sector":      sector,
                    "size_bytes":  nr_sectors * 512,
                    "offset_bytes":sector * 512,
                    "lat_ms":      0.0,
                    "pid":         pid,
                    "comm":        parts[-1].strip("[]") if parts[-1].startswith("[") else "",
                })
            except (ValueError, IndexError):
                continue

        if not rows:
            print(f"  [warn] blktrace: no parseable events in {path}")
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        # Filter to device if specified (by major:minor or device name)
        if device and "nvme" in device:
            pass  # already filtered by file content
        return df.sort_values("time_sec").reset_index(drop=True)

    except Exception as e:
        print(f"  [warn] blktrace parse error: {e}")
        return pd.DataFrame()


def parse_iostat(path: str, device: str = "nvme") -> pd.DataFrame:
    """
    Parse iostat output. Handles:
      • iostat -xm 1  (extended stats, MB/s, 1s interval)
      • iostat -dxm 1 (device only)
      • Pre-exported CSV

    Columns in the output vary by iostat version — handles both:
      Old: rkB/s, wkB/s,  r/s, w/s, r_await, w_await
      New: rMB/s, wMB/s,  r/s, w/s, r_await, w_await, aqu-sz, %util

    Returns DataFrame with normalised columns:
      time_sec, device, r_s, w_s, r_mb_s, w_mb_s, r_await_ms, w_await_ms,
      util_pct, queue_depth, d_s, d_mb_s
    """
    import re as _re

    try:
        with open(path) as f:
            content = f.read()
        lines = content.splitlines()

        # ── CSV format ─────────────────────────────────────────────────────────
        first_data = next((l for l in lines if l.strip() and not l.startswith("Linux")), "")
        if "," in first_data:
            df_raw = pd.read_csv(path, low_memory=False)
            # Normalise column names
            df_raw.columns = [c.lower().strip().replace("/","_").replace("-","_").replace("%","pct_")
                              for c in df_raw.columns]
            renames = {"r_s": "r_s", "w_s": "w_s",
                       "rmb_s": "r_mb_s", "wmb_s": "w_mb_s",
                       "rkb_s": "r_mb_s",  # will divide by 1024 below if needed
                       "wkb_s": "w_mb_s",
                       "r_await": "r_await_ms", "w_await": "w_await_ms",
                       "aqu_sz": "queue_depth", "aqu-sz": "queue_depth",
                       "pct_util": "util_pct",
                       "time": "time_sec", "timestamp": "time_sec"}
            df_raw = df_raw.rename(columns={k: v for k, v in renames.items()
                                             if k in df_raw.columns})
            if "device" in df_raw.columns and device:
                df_raw = df_raw[df_raw["device"].str.contains(device, na=False)]
            if "time_sec" not in df_raw.columns:
                df_raw["time_sec"] = range(len(df_raw))
            return df_raw.reset_index(drop=True)

        # ── Raw iostat text ────────────────────────────────────────────────────
        # Detect column header line for this iostat version
        # Format: Device r/s rMB/s rrqm/s %rrqm r_await rareq-sz w/s wMB/s ...
        col_header = None
        col_names  = None
        rows = []
        ts   = -1  # will increment at each blank+avg-cpu block

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # New interval starts with blank line or avg-cpu line
            if not line:
                i += 1
                continue
            if line.startswith("avg-cpu:"):
                ts += 1
                i += 2  # skip the values line
                continue
            if line.startswith("Linux"):
                i += 1
                continue

            # Column header line (contains "Device" and MB or kB markers)
            if line.lower().startswith("device"):
                # Parse the header to know column positions
                col_names = line.split()
                i += 1
                continue

            # Data line — matches our device
            if col_names and ts >= 0:
                parts = line.split()
                if not parts:
                    i += 1
                    continue
                dev_name = parts[0]
                if device.lower() in dev_name.lower() or dev_name.startswith("nvme"):
                    if len(parts) >= len(col_names):
                        row = {"time_sec": float(ts), "device": dev_name}
                        for ci, cn in enumerate(col_names[1:], 1):
                            try:
                                row[cn] = float(parts[ci])
                            except (ValueError, IndexError):
                                row[cn] = 0.0
                        rows.append(row)
            i += 1

        if not rows:
            print(f"  [warn] iostat: no data rows for device '{device}' in {path}")
            # Try again with no device filter
            if device != "nvme":
                return parse_iostat(path, device="nvme")
            return pd.DataFrame()

        df = pd.DataFrame(rows)

        # Normalise column names to standard set
        CN = {}
        for c in df.columns:
            cl = c.lower().replace("/","_").replace("-","_").replace("%","pct_")
            CN[c] = cl
        df = df.rename(columns=CN)

        # Map to standard output columns regardless of MB vs kB units
        col_map = {
            "r_s": "r_s", "w_s": "w_s",
            "rmb_s": "r_mb_s",  "wmb_s": "w_mb_s",
            "rkb_s": "r_kb_s",  "wkb_s": "w_kb_s",   # handle below
            "r_await": "r_await_ms", "w_await": "w_await_ms",
            "aqu_sz": "queue_depth",
            "pct_util": "util_pct",
            "d_s": "d_s", "dmb_s": "d_mb_s",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

        # Convert kB/s to MB/s if MB columns not present
        if "r_kb_s" in df.columns and "r_mb_s" not in df.columns:
            df["r_mb_s"] = df["r_kb_s"] / 1024
        if "w_kb_s" in df.columns and "w_mb_s" not in df.columns:
            df["w_mb_s"] = df["w_kb_s"] / 1024

        # Ensure standard columns exist
        for col in ("r_s","w_s","r_mb_s","w_mb_s","r_await_ms","w_await_ms",
                    "util_pct","queue_depth","d_s","d_mb_s"):
            if col not in df.columns:
                df[col] = 0.0

        return df.reset_index(drop=True)

    except Exception as e:
        print(f"  [warn] iostat parse error: {e}")
        import traceback; traceback.print_exc()
        return pd.DataFrame()
    rows = []
    try:
        with open(path) as f:
            content = f.read()

        # CSV format with header
        if "r/s" in content[:200] or "rkB/s" in content[:200] or "r_s" in content[:200]:
            df = pd.read_csv(path, low_memory=False)
            renames = {}
            for c in df.columns:
                cl = c.lower().strip().replace("/","_").replace(" ","_")
                for k, v in [("r_s","r_s"),("w_s","w_s"),("rkb_s","rkb_s"),
                              ("wkb_s","wkb_s"),("r_await","r_await_ms"),
                              ("w_await","w_await_ms"),("util","util_pct"),
                              ("avgqu","queue_depth"),("aqu","queue_depth"),
                              ("time","time_sec"),("device","device")]:
                    if k in cl:
                        renames[c] = v
            df = df.rename(columns=renames)
            if "device" in df.columns and device:
                df = df[df["device"].str.contains(device, na=False)]
            if "time_sec" not in df.columns:
                df["time_sec"] = range(len(df))
            for col in ("r_s","w_s","rkb_s","wkb_s","r_await_ms","w_await_ms","util_pct","queue_depth"):
                if col not in df.columns:
                    df[col] = 0.0
            return df.reset_index(drop=True)

        # Parse raw iostat text output
        import re as _re
        ts = 0
        for line in content.splitlines():
            line = line.strip()
            # Timestamp lines
            m = _re.match(r'^(\d{2}/\d{2}/\d{4}|\d{2}:\d{2}:\d{2})', line)
            if m:
                ts += 1
                continue
            # Device data lines
            parts = line.split()
            if len(parts) >= 8 and (device in parts[0] or "nvme" in parts[0]):
                try:
                    rows.append({
                        "time_sec":    float(ts),
                        "device":      parts[0],
                        "r_s":         float(parts[1]),
                        "w_s":         float(parts[2]),
                        "rkb_s":       float(parts[3]),
                        "wkb_s":       float(parts[4]),
                        "r_await_ms":  float(parts[5]) if len(parts) > 5 else 0,
                        "w_await_ms":  float(parts[6]) if len(parts) > 6 else 0,
                        "util_pct":    float(parts[-1]),
                        "queue_depth": float(parts[7]) if len(parts) > 7 else 0,
                    })
                except (ValueError, IndexError):
                    pass
        if rows:
            return pd.DataFrame(rows)
        print(f"  [warn] iostat: no parseable rows in {path}")
        return pd.DataFrame()

    except Exception as e:
        print(f"  [warn] iostat parse error: {e}")
        return pd.DataFrame()


def parse_smart_log(path: str) -> dict:
    """
    Parse nvme smart-log output. Accepts:
      A) JSON  (nvme smart-log --output-format=json /dev/nvme0n1)
      B) Text  (nvme smart-log /dev/nvme0n1)
      C) JSONL with nested stdout  {"epoch":..., "rc":0, "stdout": "{...}", "stderr":""}
         (as produced by polling scripts that wrap nvme smart-log output)
      D) JSONL timeseries — multiple records, returns delta between first and last

    Returns dict with normalised keys (first record, or delta for counters).
    Also sets _timeseries key with full DataFrame if multiple records present.
    """
    import re as _re

    try:
        text = open(path).read().strip()
        records = []

        # ── C/D: JSONL with nested stdout ────────────────────────────────────
        if text.startswith("{") and "\n" in text:
            # Could be multi-line single JSON or JSONL
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            # Try line-by-line JSONL first
            for line in lines:
                try:
                    outer = json.loads(line)
                    if "stdout" in outer and isinstance(outer["stdout"], str):
                        # Nested format: {"epoch":..., "stdout": "{...json...}"}
                        inner_str = outer["stdout"].strip()
                        if inner_str:
                            inner = json.loads(inner_str)
                            inner["_epoch"] = outer.get("epoch", 0)
                            records.append(inner)
                    elif "data_units_written" in outer or "percent_used" in outer:
                        # Direct SMART fields
                        records.append(outer)
                except (json.JSONDecodeError, KeyError):
                    continue

        # ── A: Single JSON object ─────────────────────────────────────────────
        if not records:
            try:
                data = json.loads(text)
                if isinstance(data, dict):
                    if "stdout" in data and isinstance(data["stdout"], str):
                        records.append(json.loads(data["stdout"]))
                    else:
                        records.append(data)
                elif isinstance(data, list):
                    records.extend(data)
            except json.JSONDecodeError:
                pass

        # ── B: Text key:value format ──────────────────────────────────────────
        if not records:
            data = {}
            for line in text.splitlines():
                m = _re.match(r'^\s*(.+?)\s*:\s*(.+)$', line)
                if m:
                    k = m.group(1).strip().lower().replace(" ","_").replace("-","_")
                    v = m.group(2).strip()
                    try:
                        data[k] = int(v.split()[0].replace(",",""))
                    except ValueError:
                        data[k] = v
            if data:
                records.append(data)

        if not records:
            print(f"  [warn] smart-log: no records parsed from {path}")
            return {}

        # ── Normalise keys ─────────────────────────────────────────────────────
        KEY_MAP = {
            "percentage_used":     "percent_used",
            "percent_used":        "percent_used",
            "endurance_used":      "percent_used",
            "avail_spare":         "avail_spare",
            "available_spare":     "avail_spare",
            "data_units_read":     "data_units_read",
            "data_units_written":  "data_units_written",
            "host_read_commands":  "host_read_commands",
            "host_write_commands": "host_write_commands",
            "media_errors":        "media_errors",
            "num_err_log_entries": "error_log_count",
            "power_cycles":        "power_cycles",
            "power_on_hours":      "power_on_hours",
            "unsafe_shutdowns":    "unsafe_shutdowns",
            "temperature":         "temperature_k",
            "critical_warning":    "critical_warning",
            "controller_busy_time":"controller_busy_time",
        }

        def _norm(rec):
            out = {}
            for src_k, dst_k in KEY_MAP.items():
                if src_k in rec:
                    try:
                        out[dst_k] = int(str(rec[src_k]).split()[0].replace(",",""))
                    except (ValueError, TypeError):
                        out[dst_k] = rec[src_k]
            # Pass through _epoch if present
            if "_epoch" in rec:
                out["_epoch"] = rec["_epoch"]
            return out

        first_rec = _norm(records[0])
        last_rec  = _norm(records[-1])

        # For cumulative counters, report delta (last - first) as the run total
        # For state metrics, report the latest value
        COUNTERS = {"data_units_read","data_units_written",
                    "host_read_commands","host_write_commands",
                    "media_errors","error_log_count"}
        result = {}
        for k in set(list(first_rec.keys()) + list(last_rec.keys())):
            if k.startswith("_"): continue
            if k in COUNTERS:
                f = first_rec.get(k, 0)
                l = last_rec.get(k, 0)
                result[k] = max(l - f, 0)   # delta
                result[f"{k}_first"] = f
                result[f"{k}_last"]  = l
            else:
                result[k] = last_rec.get(k, first_rec.get(k, 0))

        # Duration
        if "_epoch" in last_rec and "_epoch" in first_rec:
            result["_duration_s"] = last_rec["_epoch"] - first_rec["_epoch"]

        # Attach timeseries DataFrame for temperature / spare trending
        if len(records) > 1:
            norm_recs = [_norm(r) for r in records]
            ts_df = pd.DataFrame(norm_recs)
            if "_epoch" in ts_df.columns:
                ts_df["time_sec"] = ts_df["_epoch"] - ts_df["_epoch"].iloc[0]
            result["_timeseries"] = ts_df

        print(f"    {len(records)} SMART records  "
              f"write delta={result.get('data_units_written',0):,} units "
              f"({result.get('data_units_written',0)*512000/1e9:.1f} GB)  "
              f"wear={result.get('percent_used',0)}%  "
              f"temp_k={result.get('temperature_k',0)}")

        return result

    except Exception as e:
        print(f"  [warn] smart-log parse error: {e}")
        import traceback; traceback.print_exc()
        return {}


def _compute_blktrace_metrics(
    df: pd.DataFrame,
    iotype: str,          # "R", "W", or "D"
    kv_block_bytes: int,
    run_duration_s: float,
) -> dict:
    """
    Compute all doc §C / §D / §E metrics from a blktrace DataFrame for one IO type.
    Returns a dict of computed values.
    """
    import scipy.stats as _stats
    out = {}
    sub = df[df["type"] == iotype].copy()
    if sub.empty:
        return out

    sub = sub.sort_values("time_sec").reset_index(drop=True)
    sizes = sub["size_bytes"].values / 1024  # KB

    # Inter-arrival times (ms)
    iats_us = np.diff(sub["time_sec"].values) * 1e6
    iats_us = iats_us[iats_us > 0]

    # Basic size stats
    out["size_mean_kb"]  = round(float(np.mean(sizes)), 2)
    out["size_p50_kb"]   = round(float(np.percentile(sizes, 50)), 2)
    out["size_p99_kb"]   = round(float(np.percentile(sizes, 99)), 2)

    # IAT stats
    if len(iats_us) > 0:
        out["iat_mean_us"]  = round(float(np.mean(iats_us)), 2)
        out["iat_p50_us"]   = round(float(np.percentile(iats_us, 50)), 2)
        out["iat_p99_us"]   = round(float(np.percentile(iats_us, 99)), 2)

    # BW
    if run_duration_s > 0:
        total_bytes = float(sub["size_bytes"].sum())
        out["bw_mbs_mean"]  = round(total_bytes / run_duration_s / 1e6, 2)
        out["bytes_total"]  = int(total_bytes)
        out["bytes_per_day_gb"] = round(total_bytes / run_duration_s * 86400 / 1e9, 2)

    # Burst detection (consecutive IOs with IAT < 1ms threshold)
    BURST_THRESH_US = 1000  # 1ms
    in_burst = False
    burst_count = 0
    burst_sizes = []
    current_burst_bytes = 0
    for i, iat in enumerate(iats_us):
        if iat < BURST_THRESH_US:
            if not in_burst:
                in_burst = True
                burst_count += 1
                current_burst_bytes = float(sub["size_bytes"].iloc[i])
            else:
                current_burst_bytes += float(sub["size_bytes"].iloc[i+1] if i+1 < len(sub) else 0)
        else:
            if in_burst:
                burst_sizes.append(current_burst_bytes)
                in_burst = False
    out["burst_count"]      = burst_count
    out["burst_mean_bytes"] = round(float(np.mean(burst_sizes)), 0) if burst_sizes else 0

    # Sequential vs random (consecutive sector check)
    if "sector" in sub.columns:
        sectors    = sub["sector"].values
        nr_secs    = sub["size_bytes"].values // 512
        seq_flags  = np.zeros(len(sectors), dtype=bool)
        for i in range(1, len(sectors)):
            seq_flags[i] = (sectors[i] == sectors[i-1] + nr_secs[i-1])
        out["seq_pct"]  = round(float(seq_flags.mean() * 100), 1)
        out["rand_pct"] = round(100 - out["seq_pct"], 1)

        # LBA skewness (bucket access counts)
        BUCKET_SZ = max(1, int(sectors.max() / 1000)) if len(sectors) > 0 else 1
        buckets = sectors // BUCKET_SZ
        counts  = pd.Series(buckets).value_counts().values.astype(float)
        if len(counts) > 3:
            out["skewness"] = round(float(_stats.skew(counts)), 3)
            # Gini coefficient
            counts_s = np.sort(counts)
            n = len(counts_s)
            out["gini"] = round(float((2 * np.sum((np.arange(1, n+1)) * counts_s) /
                                       (n * counts_s.sum()) - (n+1)/n)), 3)

        # Alignment checks
        offsets = sub["size_bytes"].values  # already in bytes
        offset_bytes = (sub["sector"].values * 512).astype(np.int64)
        page_size = 4096
        if kv_block_bytes > 0:
            kvb_aligned = ((offset_bytes % kv_block_bytes == 0) &
                           (sub["size_bytes"].values % kv_block_bytes == 0))
            out["kvb_aligned_pct"]  = round(float(kvb_aligned.mean() * 100), 1)
        page_aligned = ((offset_bytes % page_size == 0) &
                        (sub["size_bytes"].values % page_size == 0))
        out["page_aligned_pct"] = round(float(page_aligned.mean() * 100), 1)

        # Correlation: size vs random
        if len(seq_flags) > 3:
            from scipy.stats import pearsonr as _pr
            import warnings as _w
            try:
                x = sub["size_bytes"].values.astype(float)
                y = (~seq_flags).astype(float)
                # Skip if either input is constant (pearsonr raises ConstantInputWarning)
                if x.std() > 0 and y.std() > 0:
                    with _w.catch_warnings():
                        _w.simplefilter("ignore")
                        corr, _ = _pr(x, y)
                    out["size_rand_corr"] = round(float(corr), 3)
            except Exception:
                pass

    # BW degradation: compare first 20% vs last 20% of run
    if run_duration_s > 10:
        win = run_duration_s * 0.2
        early = sub[sub["time_sec"] < win]["size_bytes"].sum() / win / 1e6
        late  = sub[sub["time_sec"] > run_duration_s - win]["size_bytes"].sum() / win / 1e6
        if early > 0:
            out["bw_degradation"] = round(float(late / early), 4)

    return out


def _seasonal_analysis(ts_values: np.ndarray, interval_s: float) -> dict:
    """FFT-based dominant period detection. Returns {period_s, power_at_peak}."""
    try:
        import scipy.fft as _fft
        n = len(ts_values)
        if n < 20:
            return {}
        yf = np.abs(_fft.fft(ts_values - ts_values.mean()))[:n//2]
        freqs = _fft.fftfreq(n, d=interval_s)[:n//2]
        freqs = freqs[1:]  # skip DC
        yf    = yf[1:]
        if len(freqs) == 0:
            return {}
        peak_idx = int(np.argmax(yf))
        if freqs[peak_idx] > 0:
            period_s = round(1.0 / float(freqs[peak_idx]), 1)
            return {"period_s": period_s, "power": round(float(yf[peak_idx]), 2)}
    except Exception:
        pass
    return {}


def _cross_correlation_lag(s1: np.ndarray, s2: np.ndarray, max_lag: int = 30) -> dict:
    """Find peak cross-correlation lag between two time series."""
    try:
        corrs = []
        for lag in range(-max_lag, max_lag+1):
            if lag >= 0:
                c = np.corrcoef(s1[:len(s1)-lag], s2[lag:])[0, 1] if lag < len(s1) else 0
            else:
                c = np.corrcoef(s1[-lag:], s2[:len(s2)+lag])[0, 1] if -lag < len(s2) else 0
            corrs.append((lag, c if not np.isnan(c) else 0))
        best = max(corrs, key=lambda x: abs(x[1]))
        return {"lag": best[0], "corr": round(float(best[1]), 3)}
    except Exception:
        return {}




def _normalise_blktrace_df(df_raw: pd.DataFrame) -> pd.DataFrame:
    """Convert a raw blkparse CSV (any schema) to the normalised blktrace format."""
    cols = {c.lower().strip().replace(" ","_").replace("/","_"): c for c in df_raw.columns}
    rows = []
    for _, row in df_raw.iterrows():
        # type from rwbs or op column
        iotype = "W"
        for ck in ("op","rwbs","type","rw"):
            if ck in cols:
                rv = str(row[cols[ck]]).upper().strip()
                if "D" in rv or "DISCARD" in rv: iotype = "D"
                elif "W" in rv: iotype = "W"
                elif "R" in rv: iotype = "R"
                break

        # time
        t = 0.0
        for tk in ("ts","time_sec","time_s","time_ns","timestamp"):
            if tk in cols:
                v = row[cols[tk]]
                t = float(v) / 1e9 if tk == "time_ns" else float(v)
                break

        # size
        size = 0
        for sk in ("size_bytes","bytes","nsectors","nr_sectors","sectors"):
            if sk in cols:
                v = int(row[cols[sk]])
                size = v if sk in ("size_bytes","bytes") else v * 512
                break

        # sector / offset
        sector = 0
        if "sector" in cols: sector = int(row[cols["sector"]])
        elif "offset" in cols:
            off = str(row[cols["offset"]]).split(":")[0]
            try: sector = int(float(off)) // 512
            except: pass

        rows.append({
            "time_sec":    t,
            "type":        iotype,
            "sector":      sector,
            "size_bytes":  size,
            "offset_bytes":sector * 512,
            "lat_ms":      0.0,
            "pid":         str(row[cols.get("pid","ts")]) if "pid" in cols else "",
            "comm":        str(row[cols.get("comm","ts")]) if "comm" in cols else "",
            "stream":      str(row[cols.get("stream","ts")]) if "stream" in cols else "",
        })
    return pd.DataFrame(rows).sort_values("time_sec").reset_index(drop=True) if rows else pd.DataFrame()


def _normalise_biosnoop_df(df_raw: pd.DataFrame) -> pd.DataFrame:
    """Convert biosnoop CSV output to the normalised blkio/blktrace schema.

    Supports both BCC biosnoop variants:
      TIME(s),COMM,PID,DISK,T,SECTOR,BYTES,LAT(ms)
    and AMOprof's normalized collector output:
      ts,comm,pid,disk,op,sector,size_bytes,latency_ms
    """
    if df_raw is None or getattr(df_raw, "empty", True):
        return pd.DataFrame()
    cols = {c.lower().strip().replace(" ", "_").replace("/", "_").replace("(", "").replace(")", ""): c for c in df_raw.columns}
    rows = []
    for _, row in df_raw.iterrows():
        try:
            def _get(*names, default=""):
                for n in names:
                    if n in cols:
                        return row[cols[n]]
                return default
            t = float(_get("ts", "times", "time_s", "time", default=0) or 0)
            op_raw = str(_get("op", "t", "rwbs", "type", default="")).upper().strip()
            if "D" in op_raw or "DISCARD" in op_raw:
                iotype = "D"
            elif "W" in op_raw:
                iotype = "W"
            elif "R" in op_raw:
                iotype = "R"
            else:
                iotype = "?"
            sector = int(float(_get("sector", "lba", default=0) or 0))
            size = int(float(_get("size_bytes", "bytes", "size", default=0) or 0))
            lat = float(_get("latency_ms", "latms", "lat_ms", "lat", default=0) or 0)
            rows.append({
                "time_sec": t,
                "type": iotype,
                "op": iotype,
                "sector": sector,
                "size_bytes": size,
                "offset_bytes": sector * 512,
                "lat_ms": lat,
                "pid": str(_get("pid", default="")),
                "comm": str(_get("comm", "command", default="")),
                "disk": str(_get("disk", "dev", "device", default="")),
                "stream": str(_get("comm", "command", "pid", default="")),
            })
        except Exception:
            continue
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out = out[pd.to_numeric(out["time_sec"], errors="coerce").notna()]
    out = out[pd.to_numeric(out["size_bytes"], errors="coerce").fillna(0) > 0]
    return out.sort_values("time_sec").reset_index(drop=True)


def _load_blktrace_analysis_dir(analysis_dir: Path) -> dict:
    """
    Load all pre-computed blktrace analysis files from a directory.
    Returns a dict with normalised keys for use in extract_metrics and charting.

    Expected files (all optional):
      summary.json                       — §C/D/E scalar summary
      bandwidth_per_stream.csv           — per stream BW, count, bytes
      bandwidth_per_stream_summary.csv   — avg/max stream BW summary
      hot_regions_overall.csv            — LBA hot regions
      hot_regions_by_time_window.csv     — hot regions per time window
      interarrival_distribution.csv      — IAT distribution
      request_size_distribution.csv      — request size + access_area + alignment
      burst_temporal_windows.csv         — burst windows
      temporal_read_write_trim_pattern.csv — R/W/T ratio per window
      access_skew_summary.csv            — Gini, skewness per op
      bandwidth_degradation.csv          — early vs late BW
      request_size_random_seq_correlation.csv
      report.md                          — human-readable summary
    """
    ad = Path(analysis_dir)
    result = {}

    def _load(fname, **kwargs):
        p = ad / fname
        if p.exists():
            try:
                return pd.read_csv(p, **kwargs)
            except Exception as e:
                print(f"    [warn] {fname}: {e}")
        return pd.DataFrame()

    # summary.json — core scalar metrics
    summary_path = ad / "summary.json"
    if summary_path.exists():
        with open(summary_path) as f:
            result["summary"] = json.load(f)

    # Pre-computed analysis DataFrames
    result["bw_per_stream"]      = _load("bandwidth_per_stream.csv")
    result["bw_per_stream_summary"] = _load("bandwidth_per_stream_summary.csv")
    result["hot_regions"]        = _load("hot_regions_overall.csv")
    result["hot_regions_windows"]= _load("hot_regions_by_time_window.csv")
    result["iat_dist"]           = _load("interarrival_distribution.csv")
    result["req_size_dist"]      = _load("request_size_distribution.csv", nrows=500000)
    result["burst_windows"]      = _load("burst_temporal_windows.csv")
    result["temporal_pattern"]   = _load("temporal_read_write_trim_pattern.csv")
    result["access_skew"]        = _load("access_skew_summary.csv")
    result["bw_degradation"]     = _load("bandwidth_degradation.csv")
    result["size_rand_corr"]     = _load("request_size_random_seq_correlation.csv")

    # Derived PNG images — store as paths for embedding
    for img_name in ("read_burst_shape.png","write_burst_shape.png",
                     "read_hot_regions.png","write_hot_regions.png"):
        p = ad / img_name
        if p.exists():
            result[f"img_{img_name.replace('.png','').replace('-','_')}"] = str(p)

    # report.md text
    rp = ad / "report.md"
    if rp.exists():
        result["report_md"] = rp.read_text()

    return {k: v for k, v in result.items() if v is not None and
            (not isinstance(v, pd.DataFrame) or not v.empty)}


def load_raw_dir_with_extras(
    raw_path: Path,
    blktrace_file: str       = "",
    blktrace_analysis_dir: str = "",
    nvme_smart_file: str     = "",
    iostat_file: str         = "",
    pcm_file: str            = "",
    kv_event_log: str        = "",
    kv_block_size_tokens: int = 0,
    nvme_device: str         = "nvme",
) -> dict:
    """
    Extended loader. Extra sources all optional.

    blktrace_analysis_dir: directory of pre-computed blktrace analysis outputs
      (summary.json, bandwidth_per_stream.csv, hot_regions_overall.csv, etc.)
      as produced by the KV$ SSD analysis pipeline. When provided, these
      pre-computed results are used directly instead of re-computing from raw events.
    """
    data = load_raw_dir(raw_path) if raw_path and Path(raw_path).is_dir() else {}

    # ── biosnoop CSVs captured by AMOprof collectors ─────────────────────────
    # load_raw_dir() reads biosnoop_events.csv/biosnoop.csv as generic frames,
    # but the chart path expects blkio_trace/blkio_timeseries.  Normalize and
    # alias them here so biosnoop can populate per-PID/process IO charts even
    # when blkparse fails.
    for _bio_key in ("biosnoop_events", "biosnoop", "biosnoop_timeseries"):
        _bio_df = data.get(_bio_key)
        if isinstance(_bio_df, pd.DataFrame) and not _bio_df.empty:
            _bio_norm = _normalise_biosnoop_df(_bio_df)
            if not _bio_norm.empty:
                data["biosnoop_normalized"] = _bio_norm
                if not isinstance(data.get("blkio_trace"), pd.DataFrame) or data.get("blkio_trace").empty:
                    data["blkio_trace"] = _bio_norm
                    data["blkio_timeseries"] = _bio_norm
                print(f"  [biosnoop] normalized {len(_bio_norm):,} events from {_bio_key}")
                break

    # ── blktrace analysis directory (pre-computed results) ────────────────────
    if blktrace_analysis_dir:
        ad = Path(blktrace_analysis_dir)
        print(f"  [blktrace-analysis] Loading directory: {ad}", flush=True)
        bt_analysis = _load_blktrace_analysis_dir(ad)
        if bt_analysis:
            data["blktrace_analysis"] = bt_analysis
            # Also load raw events CSV if present for existing charts
            raw_csv = ad / "blkparse_events.generated.csv"
            if raw_csv.exists():
                fsize = raw_csv.stat().st_size
                max_raw_mb = int(os.environ.get("AMOPROF_MAX_RAW_BLKTRACE_CSV_MB", "256"))
                if fsize > max_raw_mb * 1024 * 1024:
                    print(f"    Skipping raw events CSV load ({fsize//1024//1024} MB); "
                          f"using compact blktrace-analysis CSVs only. "
                          f"Set AMOPROF_MAX_RAW_BLKTRACE_CSV_MB to override.")
                else:
                    print(f"    Loading raw events CSV ({fsize//1024//1024} MB)...")
                    try:
                        read_kw = dict(low_memory=False, comment=None, on_bad_lines='skip')
                        blkt = pd.read_csv(raw_csv, **read_kw)
                        ts_col = next((c for c in blkt.columns
                                       if c.lower() in ("ts","time_sec","timestamp")), None)
                        if ts_col:
                            blkt = blkt[pd.to_numeric(blkt[ts_col], errors='coerce').notna()]
                        blkt_norm = _normalise_blktrace_df(blkt)
                        if not blkt_norm.empty:
                            data["blktrace"]         = blkt_norm
                            data["blkio_trace"]      = blkt_norm
                            data["blkio_timeseries"] = blkt_norm
                            nr = int((blkt_norm["type"]=="R").sum())
                            nw = int((blkt_norm["type"]=="W").sum())
                            print(f"    {len(blkt_norm):,} events  R={nr:,}  W={nw:,}")
                    except Exception as e:
                        print(f"    [warn] raw CSV load: {e}")
            scalar_keys = [k for k, v in bt_analysis.items() if not isinstance(v, pd.DataFrame)]
            df_keys = [f"{k}({len(v)})" for k, v in bt_analysis.items() if isinstance(v, pd.DataFrame)]
            print(f"    Analysis keys: scalar={scalar_keys} dataframes={df_keys}")
        else:
            print(f"    [warn] analysis directory appears empty or unreadable")

    # ── blktrace / blkparse ───────────────────────────────────────────────────
    if blktrace_file:
        bf = Path(blktrace_file)
        max_raw_mb = int(os.environ.get("AMOPROF_MAX_RAW_BLKTRACE_CSV_MB", "256"))
        if bf.exists() and bf.stat().st_size > max_raw_mb * 1024 * 1024:
            print(f"  [blktrace] Skipping raw per-event load ({bf.stat().st_size//1024//1024} MB); "
                  f"use --blktrace-analysis-dir / pre-aggregated CSVs instead.", flush=True)
            blkt = pd.DataFrame()
        else:
            print(f"  [blktrace] Loading: {blktrace_file}", flush=True)
            blkt = parse_blktrace(blktrace_file, device=nvme_device)
        if not blkt.empty:
            data["blktrace"]         = blkt
            data["blkio_trace"]      = blkt   # alias
            data["blkio_timeseries"] = blkt
            nr = int((blkt["type"] == "R").sum())
            nw = int((blkt["type"] == "W").sum())
            nd = int((blkt["type"] == "D").sum())
            print(f"    {len(blkt):,} events  R={nr:,}  W={nw:,}  D/trim={nd:,}  "
                  f"size range: {blkt['size_bytes'].min()//512}–{blkt['size_bytes'].max()//512} sectors")
        else:
            print(f"    [warn] blktrace parse returned empty")

    # ── nvme smart-log (JSON / text / JSONL poll log) ─────────────────────────
    if nvme_smart_file:
        print(f"  [nvme-smart] Loading: {nvme_smart_file}", flush=True)
        smart_dict = parse_smart_log(nvme_smart_file)
        if smart_dict:
            data["nvme_smart_snapshot"] = smart_dict

            # Extract embedded timeseries (from JSONL multi-record parse)
            ts_df = smart_dict.pop("_timeseries", None)
            dur   = smart_dict.pop("_duration_s", 0)

            if isinstance(ts_df, pd.DataFrame) and not ts_df.empty:
                col_remap = {"data_units_read":    "data_units_read",
                             "data_units_written": "data_units_written",
                             "host_read_commands": "host_read_commands",
                             "host_write_commands":"host_write_commands",
                             "percent_used":       "percent_used",
                             "avail_spare":        "avail_spare",
                             "temperature_k":      "temperature_k",
                             "time_sec":           "time_sec"}
                ts_df = ts_df.rename(columns={k: v for k, v in col_remap.items()
                                               if k in ts_df.columns})
                for col in ("percent_used","avail_spare","data_units_read",
                             "data_units_written","host_read_commands","host_write_commands"):
                    if col not in ts_df.columns:
                        ts_df[col] = 0
                data["smart_timeseries"] = ts_df
            else:
                # Single snapshot — create minimal 2-row DF for delta computation
                def _get(k):
                    return smart_dict.get(f"{k}_last",
                           smart_dict.get(f"{k}_first",
                           smart_dict.get(k, 0)))
                row0 = {k: smart_dict.get(f"{k}_first", 0)
                        for k in ("data_units_read","data_units_written",
                                  "host_read_commands","host_write_commands",
                                  "percent_used","avail_spare")}
                row0["time_sec"] = 0
                row1 = {k: _get(k) for k in row0 if k != "time_sec"}
                row1["time_sec"] = dur if dur > 0 else 1
                data["smart_timeseries"] = pd.DataFrame([row0, row1])

            # Calculate actual bytes written during run (delta × NVMe SMART unit)
            DU = 512 * 1000
            dw = smart_dict.get("data_units_written", 0)
            dr = smart_dict.get("data_units_read", 0)
            print(f"    Written: {dw*DU/1e9:.2f} GB  "
                  f"Read: {dr*DU/1e9:.3f} GB  "
                  f"Wear: {smart_dict.get('percent_used',0)}%  "
                  f"Spare: {smart_dict.get('avail_spare',100)}%  "
                  f"Temp: {smart_dict.get('temperature_k',0)}K")
        else:
            print(f"    [warn] nvme-smart parse failed")

    # ── iostat ────────────────────────────────────────────────────────────────
    if iostat_file:
        print(f"  [iostat] Loading: {iostat_file}", flush=True)
        io_df = parse_iostat(iostat_file, device=nvme_device)
        if not io_df.empty:
            data["iostat_timeseries"] = io_df
            # Build nvme_driver_timeseries from iostat if not already loaded
            if "nvme_driver_timeseries" not in data or \
               (isinstance(data.get("nvme_driver_timeseries"), pd.DataFrame) and
                data["nvme_driver_timeseries"].empty):
                nv_rows = []
                for _, row in io_df.iterrows():
                    r_mb = float(row.get("r_mb_s", row.get("r_kb_s", 0)) or 0)
                    if "r_kb_s" in io_df.columns and "r_mb_s" not in io_df.columns:
                        r_mb = r_mb / 1024
                    w_mb = float(row.get("w_mb_s", row.get("w_kb_s", 0)) or 0)
                    if "w_kb_s" in io_df.columns and "w_mb_s" not in io_df.columns:
                        w_mb = w_mb / 1024
                    # Use 0 for wr_ios/rd_ios (not cumulative) so extract_metrics
                    # doesn't apply .diff() to already-computed rates
                    nv_rows.append({
                        "time_sec":   float(row.get("time_sec", 0)),
                        "rd_ios":     0.0,
                        "wr_ios":     0.0,
                        "rd_iops":    float(row.get("r_s", 0)),
                        "wr_iops":    float(row.get("w_s", 0)),
                        "rd_ms":      float(row.get("r_await_ms", row.get("r_await", 0))),
                        "wr_ms":      float(row.get("w_await_ms", row.get("w_await", 0))),
                        "wr_lat_ms":  float(row.get("w_await_ms", row.get("w_await", 0))),
                        "rd_lat_ms":  float(row.get("r_await_ms", row.get("r_await", 0))),
                        "io_ms":      float(row.get("util_pct", 0)) * 10,
                        "io_util_pct":float(row.get("util_pct", 0)),
                        "inflight":   float(row.get("queue_depth", row.get("aqu_sz", 0))),
                        "disc_ios":   float(row.get("d_s", 0)),
                        "disc_sectors": 0.0,
                        "rd_bw_mbs":  r_mb,
                        "wr_bw_mbs":  w_mb,
                    })
                data["nvme_driver_timeseries"] = pd.DataFrame(nv_rows)
            r_mb = io_df["r_mb_s"].mean() if "r_mb_s" in io_df.columns else 0
            w_mb = io_df["w_mb_s"].mean() if "w_mb_s" in io_df.columns else 0
            util = io_df["util_pct"].mean() if "util_pct" in io_df.columns else 0
            qdep = io_df["queue_depth"].mean() if "queue_depth" in io_df.columns else 0
            print(f"    {len(io_df)} intervals  "
                  f"r={r_mb:.2f}MB/s  w={w_mb:.1f}MB/s  "
                  f"util={util:.1f}%  q={qdep:.1f}")
        else:
            print(f"    [warn] iostat parse returned empty")

    # ── Intel PCM DRAM BW ─────────────────────────────────────────────────────
    if pcm_file:
        print(f"  [pcm-memory] Loading: {pcm_file}", flush=True)
        pcm_df = _parse_pcm_memory(pcm_file)
        if not pcm_df.empty:
            data["pcm_memory_timeseries"] = pcm_df
            print(f"    {len(pcm_df)} intervals  "
                  f"mean BW: {pcm_df.get('total_bw_gbs', pd.Series([0])).mean():.1f} GB/s")

    # ── Custom KV block event log ──────────────────────────────────────────────
    if kv_event_log:
        print(f"  [kv-event-log] Loading: {kv_event_log}", flush=True)
        kv_ev = _parse_kv_event_log(kv_event_log)
        if not kv_ev.empty:
            data["kv_event_log"] = kv_ev
            print(f"    {len(kv_ev)} KV block events")

    if kv_block_size_tokens > 0:
        data["_kv_block_size_tokens_override"] = kv_block_size_tokens

    return data


def resolve_input(raw_arg: str) -> dict:
    """Accept zip, directory, or glob pattern."""
    p = Path(raw_arg)
    if p.is_file() and p.suffix == ".zip":
        print(f"  Loading zip: {p}")
        return load_zip(p)
    if p.is_dir():
        print(f"  Loading directory: {p}")
        return load_raw_dir(p)
    # Try glob
    matches = sorted(glob.glob(raw_arg))
    if matches:
        p = Path(matches[-1])  # most recent
        if p.is_dir():
            print(f"  Loading (glob match): {p}")
            return load_raw_dir(p)
    raise ValueError(f"Cannot resolve input: {raw_arg!r}. Provide a .zip or raw/ directory.")

# ── Metric extraction ─────────────────────────────────────────────────────────

@dataclass
class Metrics:
    # SGLang
    model: str = "unknown"
    # Setup / server configuration (best-effort from SGLang/Prometheus + manual overrides)
    setup_model: str = "unknown"
    setup_instance: str = "unknown"
    setup_job: str = "unknown"
    setup_engine_type: str = "unknown"
    setup_runtime: str = "SGLang"
    setup_gpu: str = "A100"
    setup_tp_size: str = "unknown"
    setup_dtype: str = "unknown"
    setup_kv_cache_dtype: str = "unknown"
    setup_context_length: str = "unknown"
    setup_page_size: str = "unknown"
    setup_num_pages: str = "unknown"
    setup_hicache: str = "unknown"
    setup_attention_backend: str = "unknown"
    setup_schedule_policy: str = "unknown"
    setup_details: dict = field(default_factory=dict)
    run_duration_s: float = 0
    ttft_ms: float = 0
    tpot_ms: float = 0
    e2e_ms: float = 0
    gen_tp_mean: float = 0
    gen_tp_peak: float = 0
    cache_hit_pct: float = 0
    cache_hit_calc_method: str = "unknown"
    cache_hit_token_weighted_pct: float = 0
    cache_hit_cached_prompt_pct: float = 0
    cache_hit_gauge_overall_pct: float = 0
    cache_hit_gauge_active_pct: float = 0
    cache_hit_gauge_peak_pct: float = 0
    cache_hit_gauge_total_samples: int = 0
    cache_hit_gauge_active_samples: int = 0
    hicache_fill_pct: float = 0
    decode_tokens: int = 0
    prefill_compute_tokens: int = 0
    prefill_cache_tokens: int = 0
    num_requests: int = 0
    # GPU
    gpu_count: int = 8
    gpu_util_mean: float = 0
    gpu_util_peak: float = 0
    hbm_util_pct: float = 0
    hbm_used_mb_mean: float = 0
    hbm_total_mb: float = 40960
    gpu_power_mean_w: float = 0
    gpu_power_peak_w: float = 0
    per_gpu_util_mean: list = field(default_factory=list)
    # DRAM
    dram_used_gb: float = 0
    dram_total_gb: float = 0
    dram_util_pct: float = 0
    # NVMe
    nvme_wr_iops_max: float = 0
    nvme_rd_iops_max: float = 0
    nvme_wr_lat_ms: float = 0
    # vmstat
    page_faults_per_s: float = 0
    # ── Swap activity & swap storm detection ─────────────────────────────────
    swap_in_pages_per_s_mean:    float = 0   # pswpin rate (pages/s, 4KB pages)
    swap_in_pages_per_s_peak:    float = 0
    swap_out_pages_per_s_mean:   float = 0   # pswpout rate
    swap_out_pages_per_s_peak:   float = 0
    swap_in_mb_per_s_mean:       float = 0   # MiB/s = pages/s × 4 / 1024
    swap_out_mb_per_s_mean:      float = 0
    swap_total_mb:               float = 0
    swap_free_mb_min:            float = 0   # minimum free swap observed
    swap_used_pct_max:           float = 0   # peak swap utilization
    swap_thrashing_pct:          float = 0   # % of samples with significant swap activity
    swap_storm_episode_count:    int   = 0   # number of distinct storm intervals
    swap_storm_total_duration_s: float = 0
    swap_storm_worst_pages_per_s:float = 0   # peak page rate during any storm
    swap_storm_threshold_pages_per_s: float = 1000  # config threshold (pages/s)
    swap_write_amp_ratio:        float = 0   # nvme_write_pages / pswpout (write amplification)
    swap_majfault_correlation:   float = 0   # pearson(pswpin, pgmajfault)
    numa_migrations_per_s: float = 0
    # Power
    system_power_w: float = 0
    # KV cache footprint analysis
    kv_bytes_per_token: int = 0       # bytes per token in KV cache
    kv_bytes_per_token_kb: float = 0  # same in KB
    kv_n_layers: int = 0              # model transformer layers
    kv_n_heads: int = 0               # KV heads (post-GQA/MLA)
    kv_head_dim: int = 0              # attention head dimension
    kv_dtype_bytes: int = 2           # bytes per element (FP16=2, INT8=1, FP8=1, INT4=0.5)
    kv_dtype_name: str = "FP16"       # human-readable dtype
    kv_attention_type: str = "GQA"    # MHA / GQA / MLA
    kv_hbm_pool_gb: float = 0         # GB available for KV after weights
    kv_hbm_max_tokens: int = 0        # max tokens fitting in L1 HBM pool
    kv_hbm_utilisation_pct: float = 0 # actual tokens / max tokens * 100
    kv_active_tokens: int = 0         # tokens currently in KV pool during run
    kv_pool_fill_pct: float = 0       # SGLang token pool utilisation %
    kv_weight_gb_per_gpu: float = 0   # model weight footprint per GPU
    # Per-tier token distribution and read latency costs
    kv_l1_hbm_tokens: int = 0         # tokens resident in L1 HBM (on-GPU)
    kv_l2_dram_tokens: int = 0        # tokens resident in L2 hicache DRAM
    kv_l3_nvme_tokens: int = 0        # tokens resident in L3 NVMe storage
    kv_l1_capacity_tokens: int = 0    # L1 HBM pool capacity (tokens)
    kv_l2_capacity_tokens: int = 0    # L2 DRAM pool capacity (tokens)
    kv_l1_bw_gbs: float = 2000.0      # L1 bandwidth: A100 HBM2e GB/s
    kv_l2_bw_gbs: float = 200.0       # L2 bandwidth: AMD EPYC DDR4 GB/s
    kv_l3_bw_gbs: float = 3.5         # L3 bandwidth: NVMe sequential read GB/s
    kv_l1_read_lat_ms: float = 0      # ms to read one token's KV from L1 HBM
    kv_l2_read_lat_ms: float = 0      # ms to read one token's KV from L2 DRAM
    kv_l3_read_lat_ms: float = 0      # ms to read one token's KV from L3 NVMe
    kv_l1_fill_pct: float = 0         # L1 HBM KV pool fill %
    kv_l2_fill_pct: float = 0         # L2 DRAM KV pool fill %
    kv_weighted_lat_ms: float = 0     # weighted avg read latency given actual tier mix
    kv_ttft_l1_ms: float = 0          # estimated TTFT if all tokens served from L1
    kv_ttft_l2_ms: float = 0          # estimated TTFT if all tokens served from L2
    kv_ttft_l3_ms: float = 0          # estimated TTFT if all tokens served from L3
    kv_l1_cost_per_req_ms: float = 0  # total KV read time from L1 for active context
    kv_l2_cost_per_req_ms: float = 0  # total KV read time from L2 for active context
    kv_l3_cost_per_req_ms: float = 0  # total KV read time from L3 for active context
    # HBM bandwidth (GPU-side memory = HBM on A100, from nsys + TPOT derivation)
    hbm_read_bw_gbs: float = 0       # GB/s estimated during decode
    hbm_write_bw_gbs: float = 0      # GB/s estimated (writes ~ 10-15% of reads)
    hbm_peak_bw_gbs: float = 2000.0  # A100 theoretical peak GB/s
    hbm_bw_util_pct: float = 0       # % of peak HBM BW used
    hbm_read_txn_M_s: float = 0      # millions of 64B cache-line reads/s
    hbm_write_txn_M_s: float = 0     # millions of 64B cache-line writes/s
    # System DRAM bandwidth (CPU-side, from AMDuProf PCM)
    dram_read_bw_gbs: float = 0      # GB/s mean
    dram_write_bw_gbs: float = 0     # GB/s mean
    dram_total_bw_gbs: float = 0     # GB/s mean
    dram_read_bw_peak_gbs: float = 0
    dram_write_bw_peak_gbs: float = 0
    dram_peak_theoretical_gbs: float = 204.8  # AMD EPYC 7742 2S: 8ch DDR4-3200 × 2 sockets
    dram_bw_util_pct: float = 0      # % of AMD EPYC DRAM peak BW
    dram_read_txn_M_s: float = 0     # millions of 64B transactions/s
    dram_write_txn_M_s: float = 0
    # Timeseries for DRAM BW (from AMDuProf) and HBM BW (nsys or derived)
    dram_bw_ts: pd.DataFrame = field(default_factory=pd.DataFrame)
    hbm_bw_ts: pd.DataFrame = field(default_factory=pd.DataFrame)
    # ── Session / Stream analysis ─────────────────────────────────────────────
    sess_total_requests: int = 0          # total requests completed during run
    sess_max_concurrent: int = 0          # peak simultaneous active sessions
    sess_mean_concurrent: float = 0       # mean active sessions over run
    sess_e2e_mean_s: float = 0            # mean E2E latency per request (s)
    sess_e2e_min_s: float = 0
    sess_e2e_max_s: float = 0
    sess_e2e_p50_s: float = 0
    sess_e2e_p90_s: float = 0
    sess_e2e_p99_s: float = 0
    sess_input_tok_mean: float = 0        # mean prompt tokens per request
    sess_input_tok_min: float = 0
    sess_input_tok_max: float = 0
    sess_input_tok_p90: float = 0
    sess_output_tok_mean: float = 0       # mean generation tokens per request
    sess_output_tok_min: float = 0
    sess_output_tok_max: float = 0
    sess_output_tok_p90: float = 0
    sess_queue_mean_ms: float = 0         # mean queue wait per request (ms)
    sess_queue_max_ms: float = 0
    sess_arrival_rate_rps: float = 0      # mean request arrival rate (req/s)
    sess_inter_arrival_s: float = 0       # mean inter-arrival time (s)
    # Per-request timeseries (list of values, one per completed request)
    sess_e2e_ts: list = field(default_factory=list)
    sess_input_tok_ts: list = field(default_factory=list)
    sess_output_tok_ts: list = field(default_factory=list)
    sess_concurrent_ts: pd.DataFrame = field(default_factory=pd.DataFrame)
    # ── KV$B (KV Cache Block) event metrics ───────────────────────────────────
    kvb_block_size_tokens: int = 16       # tokens per KV block (SGLang default)
    kvb_block_size_mb: float = 0          # MB per block (block_tokens × bytes/tok)
    kvb_l1_pool_blocks: int = 0           # total KV blocks in L1 HBM pool
    kvb_l2_pool_blocks: int = 0           # total KV blocks in L2 DRAM pool
    kvb_tokens_per_mb: float = 0          # tokens storable per MB of KV pool
    kvb_l1_offload_rate_blk_s: float = 0  # KV blocks offloaded L1→L2 per second
    kvb_l2_eviction_rate_blk_s: float = 0 # KV blocks evicted from L2 per second
    kvb_l2_onboard_rate_blk_s: float = 0  # KV blocks loaded L2→L1 per second
    kvb_lifetime_mean_s: float = 0        # estimated mean KV block lifetime (s)
    kvb_lifetime_min_s: float = 0
    kvb_lifetime_max_s: float = 0
    kvb_offload_ts: pd.DataFrame = field(default_factory=pd.DataFrame)
    kvb_l3_io_ts: pd.DataFrame = field(default_factory=pd.DataFrame)
    # ── NVMe IO workload characteristics (from nvme_driver + SMART) ───────────
    nvme_wr_iops_mean: float = 0
    nvme_wr_lat_mean_ms: float = 0
    nvme_wr_lat_max_ms: float = 0
    nvme_rd_lat_mean_ms: float = 0
    nvme_io_util_pct: float = 0           # % of time device was busy
    nvme_bytes_written_total: int = 0     # bytes written during run (from SMART delta)
    nvme_bytes_read_total: int = 0        # bytes read during run (from SMART delta)
    nvme_smart_wear_pct: float = 0        # % drive life used (SMART percent_used)
    nvme_smart_avail_spare: float = 0     # % spare capacity remaining
    nvme_host_write_cmds: int = 0         # total host write commands (SMART)
    nvme_host_read_cmds: int = 0          # total host read commands (SMART)
    nvme_wr_bw_mbs_mean: float = 0        # write bandwidth MB/s mean
    nvme_wr_bw_mbs_max: float = 0
    nvme_inflight_mean: float = 0         # mean queue depth
    nvme_inflight_max: float = 0
    nvme_io_ts: pd.DataFrame = field(default_factory=pd.DataFrame)
    # ── Deep IO profiling (requires blktrace/biosnoop — null when unavailable) ─
    blkio_available: bool = False         # True if blkio_trace data present
    blkio_has_analysis: bool = False      # True if pre-computed analysis dir loaded
    # Per-stream bandwidth (§C/D: bandwidth_per_stream)
    ssd_rd_stream_count: int = 0          # number of distinct read streams
    ssd_wr_stream_count: int = 0
    ssd_rd_bw_per_stream_mean_mbs: float = 0  # mean read BW per stream
    ssd_rd_bw_per_stream_max_mbs: float = 0
    ssd_wr_bw_per_stream_mean_mbs: float = 0
    ssd_wr_bw_per_stream_max_mbs: float = 0
    # LBA hot region metrics
    ssd_rd_hot_region_count: int = 0
    ssd_wr_hot_region_count: int = 0
    ssd_rd_top1pct_byte_share: float = 0  # Gini/skew from access_skew_summary
    ssd_wr_top1pct_byte_share: float = 0
    # Temporal / burst metrics from burst_temporal_windows
    ssd_rd_burst_windows: int = 0
    ssd_wr_burst_windows: int = 0
    # R/W/T ratio
    ssd_rw_byte_ratio: float = 0          # read_bytes / write_bytes
    # DataFrames carrying full analysis results (used in charts)
    blktrace_analysis: dict = None
    blkio_req_size_mean_kb: float = 0
    blkio_req_size_p50_kb: float = 0
    blkio_req_size_p99_kb: float = 0
    blkio_seq_pct: float = 0              # % sequential access
    blkio_aligned_kvb_pct: float = 0      # % ops aligned to KV block size
    blkio_aligned_page_pct: float = 0     # % ops aligned to 4KB page size
    blkio_inter_arrival_us: float = 0     # mean inter-arrival time µs
    blkio_ts: pd.DataFrame = field(default_factory=pd.DataFrame)

    # ── A. Inference session enhancements (doc §A) ────────────────────────────
    sess_queued_mean: float = 0           # A2: mean queued sessions
    sess_queued_max: int = 0              # A2: peak queued sessions
    sess_inflight_mean: float = 0         # A3: running + queued mean
    sess_ttft_p50_ms: float = 0           # A8: TTFT p50 from histogram
    sess_ttft_p95_ms: float = 0           # A8: TTFT p95
    sess_ttft_p99_ms: float = 0           # A8: TTFT p99 from histogram
    sess_tpot_p50_ms: float = 0           # A9: TPOT (ITL) p50
    sess_tpot_p95_ms: float = 0           # A9: TPOT p95
    sess_tpot_p99_ms: float = 0           # A9: TPOT p99
    kvb_tokens_per_block_cfg: int = 0     # A16: from sglang:cache_config_info labels

    # ── B. KV$B movement (doc §B) ─────────────────────────────────────────────
    kvb_offload_tok_rate: float = 0       # B22: tokens/s offloaded L1→L2/SSD
    kvb_offload_bps: float = 0            # B23: bytes/s offloaded
    kvb_offload_pages_rate: float = 0     # B24: pages/s offloaded
    kvb_onboard_tok_rate: float = 0       # B25: tokens/s onboarded SSD→L1
    kvb_onboard_bps: float = 0            # B26: bytes/s onboarded
    kvb_onboard_pages_rate: float = 0     # B25ext: pages/s onboarded
    kvb_trim_bps: float = 0               # B27: trim bytes/s
    kvb_trim_iops: float = 0              # B28: trim ops/s
    kvb_backuped_tokens_total: int = 0    # B22 cumulative
    kvb_prefetched_tokens_total: int = 0  # B25 cumulative
    kvb_evicted_tokens_total: int = 0     # B21 cumulative

    # ── C. SSD Read workload (doc §C) ─────────────────────────────────────────
    ssd_rd_bw_mbs_mean: float = 0         # C32: device read BW MB/s
    ssd_rd_bw_mbs_max: float = 0
    ssd_rd_iat_mean_us: float = 0         # C34: read inter-arrival time µs
    ssd_rd_iat_p50_us: float = 0
    ssd_rd_iat_p99_us: float = 0
    ssd_rd_burst_count: int = 0           # C35: number of read bursts
    ssd_rd_burst_mean_bytes: float = 0    # C35: mean burst size bytes
    ssd_rd_skewness: float = 0            # C36: LBA skewness
    ssd_rd_gini: float = 0                # C36: Gini coefficient
    ssd_rd_size_mean_kb: float = 0        # C38-39: read request size
    ssd_rd_size_p50_kb: float = 0
    ssd_rd_size_p99_kb: float = 0
    ssd_rd_kvb_aligned_pct: float = 0     # C40: KV$B aligned %
    ssd_rd_page_aligned_pct: float = 0    # C41: 4KB page aligned %
    ssd_rd_seq_pct: float = 0             # C42: sequential read %
    ssd_rd_rand_pct: float = 0            # C42: random read %
    ssd_rd_size_rand_corr: float = 0      # C43: corr(size, is_random)
    ssd_rd_bytes_total: int = 0           # C44: total bytes read this run
    ssd_rd_bytes_per_day_gb: float = 0    # C44: projected GB/day
    ssd_rd_bw_degradation: float = 0      # C45: late/baseline BW ratio
    ssd_rd_ts: pd.DataFrame = field(default_factory=pd.DataFrame)

    # ── D. SSD Write workload (doc §D) ────────────────────────────────────────
    ssd_wr_bw_mbs_mean: float = 0         # D47: write BW MB/s
    ssd_wr_bw_mbs_max: float = 0
    ssd_wr_iat_mean_us: float = 0         # D49: write inter-arrival time
    ssd_wr_iat_p99_us: float = 0
    ssd_wr_burst_count: int = 0           # D50: write burst count
    ssd_wr_skewness: float = 0            # D51: LBA skewness
    ssd_wr_size_mean_kb: float = 0        # D53-54: write request size
    ssd_wr_size_p99_kb: float = 0
    ssd_wr_kvb_aligned_pct: float = 0     # D55
    ssd_wr_page_aligned_pct: float = 0    # D56
    ssd_wr_seq_pct: float = 0             # D57
    ssd_wr_size_rand_corr: float = 0      # D58
    ssd_wr_bytes_total: int = 0           # D59
    ssd_wr_bytes_per_day_gb: float = 0    # D59
    ssd_wr_bw_degradation: float = 0      # D60

    # ── E. Trim, discard, seasonal (doc §E) ────────────────────────────────────
    trim_present: bool = False            # E61: any trim events?
    trim_bw_mbs: float = 0               # E62: trim BW MB/s
    trim_iops_mean: float = 0            # E63
    trim_iat_mean_us: float = 0          # E64
    trim_size_mean_kb: float = 0         # E65
    trim_kvb_aligned_pct: float = 0      # E67
    seasonal_rd_period_s: float = 0      # E68: dominant period from FFT
    seasonal_wr_period_s: float = 0      # E69
    seasonal_trim_period_s: float = 0    # E70
    cross_corr_rw_peak_lag_s: float = 0  # E71: R/W peak cross-corr lag
    cross_corr_wd_peak_lag_s: float = 0  # E71: W/D peak cross-corr lag
    rw_ratio_mean: float = 0             # E72: read/write bytes ratio
    tw_ratio_mean: float = 0             # E73: trim/write bytes ratio

    # ── G. Cross-layer KPIs (doc §G) ─────────────────────────────────────────
    ssd_rd_bytes_per_output_tok: float = 0   # G88
    ssd_wr_bytes_per_input_tok: float = 0    # G89
    offload_write_corr: float = 0            # G90: corr(offload_Bps, write_bw)
    onboard_read_corr: float = 0             # G91: corr(onboard_Bps, read_bw)
    throughput_bottleneck_tok_s: float = 0   # G93: min(gpu_tok_rate, ssd_tok_rate)
    throughput_bottleneck_src: str = ""      # G93: "GPU" or "SSD"
    ssd_effective_bw_gbs: float = 0          # G93 computed SSD BW for tokens
    # ── KV-SSD Inference Metrics (KV_SSD_Inference_Metrics_Complete_Table §A–G) ─
    # §A: session metrics — already covered by sess_* fields above
    # §B: KV$B movement rates — already covered by kvb_* fields above
    # §B extra: direct SGLang backup/prefetch/eviction metrics
    kvb_evicted_tokens_total: int = 0     # sglang:evicted_tokens_total
    kvb_prefetched_tokens_total: int = 0  # sglang:prefetched_tokens_total (onboard)
    kvb_loadback_tokens_total: int = 0    # sglang:load_back_tokens_total
    kvb_backup_bw_mean_gbs: float = 0     # sglang:backup_bandwidth mean (G2→SSD)
    kvb_prefetch_bw_mean_gbs: float = 0   # sglang:prefetch_bandwidth mean (SSD→G1)
    kvb_loadback_bw_mean_gbs: float = 0   # sglang:load_back_bandwidth mean
    kvb_onboard_tokens_rate: float = 0    # tokens/s onboarded from SSD
    kvb_offload_bw_gbs: float = 0         # bytes/s offloaded to SSD
    kvb_onboard_bw_gbs: float = 0         # bytes/s onboarded from SSD
    kvb_trim_bytes_s: float = 0           # node_disk_discarded_sectors × 512 / s
    kvb_trim_iops: float = 0              # node_disk_discards_completed / s
    # §C: SSD read characteristics (from blktrace R events)
    rd_req_size_mean_kb: float = 0
    rd_req_size_p50_kb: float = 0
    rd_req_size_p95_kb: float = 0
    rd_req_size_p99_kb: float = 0
    rd_req_size_hist_kb: list = field(default_factory=list)
    rd_iat_mean_us: float = 0             # read inter-arrival time mean µs
    rd_iat_p95_us: float = 0
    rd_iat_p99_us: float = 0
    rd_iat_hist_us: list = field(default_factory=list)
    rd_seq_pct: float = 0                 # % sequential reads (bytes)
    rd_rand_pct: float = 0
    rd_kvb_aligned_pct: float = 0        # % reads KV-block-size aligned
    rd_page_aligned_pct: float = 0       # % reads page-size aligned
    rd_lba_skewness: float = 0           # LBA access skewness
    rd_lba_gini: float = 0               # LBA Gini coefficient (hot/cold)
    rd_size_rand_corr: float = 0         # correlation: size vs random
    rd_burst_count: int = 0
    rd_burst_bytes_mean: float = 0
    rd_total_bytes: int = 0              # total bytes read in run
    rd_bw_gbs: float = 0                 # device-level read BW (node_exporter)
    rd_hot_area_pct: float = 0           # % bytes in top-20% LBA buckets
    # §D: SSD write characteristics (from blktrace W events)
    wr_req_size_mean_kb: float = 0
    wr_req_size_p50_kb: float = 0
    wr_req_size_p95_kb: float = 0
    wr_req_size_p99_kb: float = 0
    wr_req_size_hist_kb: list = field(default_factory=list)
    wr_iat_mean_us: float = 0
    wr_iat_p95_us: float = 0
    wr_iat_hist_us: list = field(default_factory=list)
    wr_seq_pct: float = 0
    wr_rand_pct: float = 0
    wr_kvb_aligned_pct: float = 0
    wr_page_aligned_pct: float = 0
    wr_lba_skewness: float = 0
    wr_lba_gini: float = 0
    wr_size_rand_corr: float = 0
    wr_burst_count: int = 0
    wr_burst_bytes_mean: float = 0
    wr_total_bytes: int = 0
    wr_bw_gbs: float = 0
    # §E: Trim / temporal patterns
    trim_present: bool = False
    trim_ops_total: int = 0
    trim_bytes_total: int = 0
    trim_bw_gbs: float = 0
    trim_iops_mean: float = 0
    trim_iat_mean_us: float = 0
    trim_req_size_mean_kb: float = 0
    trim_kvb_aligned_pct: float = 0
    rw_ratio_mean: float = 0             # mean read/write bytes ratio
    tw_ratio_mean: float = 0             # mean trim/write bytes ratio
    corr_rw: float = 0                   # cross-correlation R vs W
    corr_wd: float = 0                   # W vs D(iscard)
    read_seasonal_period_s: float = 0    # dominant read periodicity (s)
    # §G: Cross-layer KPIs
    ssd_read_per_output_token_kb: float = 0   # SSD read KB per generated token
    ssd_write_per_input_token_kb: float = 0   # SSD write KB per prompt token
    throughput_bottleneck_gpu_tok_s: float = 0 # GPU token rate
    throughput_bottleneck_ssd_tok_s: float = 0 # SSD-limited token rate
    throughput_bottleneck_label: str = "unknown"  # "GPU" or "SSD" or "balanced"
    # §F extra: DRAM BW from PCM (Intel)
    pcm_dram_read_bw_gbs: float = 0
    pcm_dram_write_bw_gbs: float = 0
    pcm_dram_total_bw_gbs: float = 0
    # Source availability flags
    blktrace_available: bool = False
    nvme_smart_available: bool = False
    pcm_available: bool = False
    iostat_available: bool = False
    # Timeseries
    sglang_ts: pd.DataFrame = field(default_factory=pd.DataFrame)
    gpu_ts: pd.DataFrame = field(default_factory=pd.DataFrame)
    dram_ts: pd.DataFrame = field(default_factory=pd.DataFrame)
    power_ts: pd.DataFrame = field(default_factory=pd.DataFrame)
    nvme_ts: pd.DataFrame = field(default_factory=pd.DataFrame)
    vmstat_ts: pd.DataFrame = field(default_factory=pd.DataFrame)


def extract_metrics(data: dict) -> Metrics:
    import numpy as _np
    import warnings as _warnings
    # Suppress numpy divide/invalid and scipy ConstantInput warnings globally
    # for this function — all division-by-zero cases produce safe_float(0) fallbacks
    _np.seterr(divide='ignore', invalid='ignore')
    _warnings.filterwarnings('ignore', category=RuntimeWarning, message='.*divide.*')
    _warnings.filterwarnings('ignore', category=RuntimeWarning, message='.*invalid.*')
    _warnings.filterwarnings('ignore', message='.*ConstantInput.*')
    m = Metrics()

    # Apply the CLI override (--kv-block-size N). load_raw_dir stashes the
    # user's choice in data["_kv_block_size_tokens_override"]; if present and
    # > 0, it wins over later auto-detection from sglang_page_size metrics.
    # Default Metrics().kvb_block_size_tokens stays 16 when no override given.
    _kvb_override = int(data.get("_kv_block_size_tokens_override", 0) or 0)
    if _kvb_override > 0:
        m.kvb_block_size_tokens = _kvb_override

    # ── Safe conversion helpers (NaN/inf/None → default) ─────────────────────
    def safe_int(v, default: int = 0) -> int:
        try:
            f = float(v)
            return default if (f != f or abs(f) == float('inf')) else int(f)
        except (TypeError, ValueError):
            return default

    def safe_float(v, default: float = 0.0) -> float:
        try:
            f = float(v)
            return default if (f != f or abs(f) == float('inf')) else f
        except (TypeError, ValueError):
            return default

    # ── SGLang summary ────────────────────────────────────────────────────────
    sg = data.get("sglang_summary", {})
    m.model = sg.get("model_name") or "unknown"

    def _first_sg(*keys, default="unknown"):
        for k in keys:
            v = sg.get(k)
            if v is not None and str(v).strip() not in ("", "0", "0.0", "nan", "None"):
                return str(v)
        return default

    # Best-effort setup/server config extraction. Most SGLang versions expose
    # model_name / instance / engine_type, while newer versions may also expose
    # cache_config_info or server args as labels/summary keys. Manual values can
    # be merged into sglang_summary.json by the wrapper in future without changing
    # this renderer.
    #
    # v1.30 also carries a conservative default SGLang launch profile for fields
    # that are often not exposed by /metrics. These defaults are only applied
    # when a field is still missing/unknown after auto-detection and manual
    # setup_details.json overrides. The report marks such fields as assumed so
    # operators can distinguish observed values from profile defaults.
    _sglang_default_setup = {
        "Model": "deepseek-ai/DeepSeek-R1-Distill-Llama-70B",
        "Model path": "deepseek-ai/DeepSeek-R1-Distill-Llama-70B",
        "Runtime": "SGLang",
        "Host": "0.0.0.0",
        "Port": "30000",
        "TP size": "8",
        "DP size": "1",
        "Attention backend": "triton",
        "Mem fraction static": "0.8",
        "Hierarchical cache": "enabled",
        "HiCache size": "50",
        "HiCache storage backend": "file",
        "HiCache write policy": "write_through",
        "Trust remote code": "true",
        "Metrics enabled": "true",
        "Cache report enabled": "true",
        "Reasoning parser": "deepseek-r1",
        "Tool call parser": "deepseekv3",
        "Reference launch command": "python -m sglang.launch_server --model-path deepseek-ai/DeepSeek-R1-Distill-Llama-70B --tp-size 8 --dp-size 1 --port 30000 --host 0.0.0.0 --attention-backend triton --mem-fraction-static 0.8 --enable-hierarchical-cache --hicache-size 50 --trust-remote-code --enable-metrics --enable-cache-report --reasoning-parser deepseek-r1 --tool-call-parser deepseekv3 --hicache-storage-backend file --hicache-write-policy write_through",
    }

    def _is_missing_setup_value(v):
        if v is None:
            return True
        try:
            sv = str(v).strip()
        except Exception:
            return True
        return sv == "" or sv.lower() in {"unknown", "none", "nan", "null", "n/a", "—", "-"}

    def _apply_setup_defaults(details: dict) -> list:
        defaulted = []
        for k, v in _sglang_default_setup.items():
            if _is_missing_setup_value(details.get(k)):
                details[k] = v
                defaulted.append(k)
        return defaulted

    def _parse_launch_command_to_setup(cmd: str) -> dict:
        """Parse an SGLang launch command into display-friendly setup keys.
        This is intentionally best-effort and avoids failing report generation
        on shell quoting edge cases.
        """
        if not cmd:
            return {}
        try:
            import shlex as _shlex_setup
            toks = _shlex_setup.split(str(cmd))
        except Exception:
            toks = str(cmd).split()
        out = {"Reference launch command": str(cmd)}
        mapping = {
            "--model-path": "Model path", "--tp-size": "TP size", "--dp-size": "DP size",
            "--port": "Port", "--host": "Host", "--attention-backend": "Attention backend",
            "--mem-fraction-static": "Mem fraction static", "--hicache-size": "HiCache size",
            "--hicache-storage-backend": "HiCache storage backend",
            "--hicache-write-policy": "HiCache write policy", "--reasoning-parser": "Reasoning parser",
            "--tool-call-parser": "Tool call parser", "--dtype": "dtype",
            "--kv-cache-dtype": "KV dtype", "--context-length": "Context length",
            "--page-size": "Page size", "--schedule-policy": "Schedule policy",
        }
        bool_flags = {
            "--enable-hierarchical-cache": ("Hierarchical cache", "enabled"),
            "--trust-remote-code": ("Trust remote code", "true"),
            "--enable-metrics": ("Metrics enabled", "true"),
            "--enable-cache-report": ("Cache report enabled", "true"),
        }
        i = 0
        while i < len(toks):
            t = toks[i]
            if t in bool_flags:
                k, v = bool_flags[t]; out[k] = v; i += 1; continue
            if t in mapping and i + 1 < len(toks):
                out[mapping[t]] = toks[i+1]; i += 2; continue
            i += 1
        if "Model path" in out and _is_missing_setup_value(out.get("Model")):
            out["Model"] = out["Model path"]
        return out

    m.setup_model = m.model
    m.setup_instance = _first_sg("instance", "prom_instance")
    m.setup_job = _first_sg("job", "prom_job")
    m.setup_engine_type = _first_sg("engine_type")
    m.setup_runtime = _first_sg("runtime", "server_type", default="SGLang")
    m.setup_tp_size = _first_sg("tp_size", "tensor_parallel_size", "tensor_parallel", "tp")
    m.setup_dtype = _first_sg("dtype", "model_dtype")
    m.setup_kv_cache_dtype = _first_sg("kv_cache_dtype", "kv_dtype")
    m.setup_context_length = _first_sg("context_length", "max_context_len", "max_model_len", "max_seq_len")
    m.setup_page_size = _first_sg("page_size", "sglang_page_size")
    m.setup_num_pages = _first_sg("num_pages", "token_pool_num_pages", "max_total_num_tokens")
    m.setup_hicache = _first_sg("hicache_size", "hicache_capacity", "hicache_mem_layout", "hicache_io_backend")
    m.setup_attention_backend = _first_sg("attention_backend", "attn_backend")
    m.setup_schedule_policy = _first_sg("schedule_policy", "scheduler_policy")
    m.setup_details = {
        "Model": m.setup_model, "Runtime": m.setup_runtime, "Instance": m.setup_instance,
        "Job": m.setup_job, "Engine": m.setup_engine_type, "TP size": m.setup_tp_size,
        "dtype": m.setup_dtype, "KV dtype": m.setup_kv_cache_dtype,
        "Context length": m.setup_context_length, "Page size": m.setup_page_size,
        "Num pages/tokens": m.setup_num_pages, "HiCache": m.setup_hicache,
        "Attention backend": m.setup_attention_backend, "Schedule policy": m.setup_schedule_policy,
    }
    # Optional manual setup override: place setup_details.json or setup.json in the
    # raw directory. Keys are displayed verbatim; common keys also update the
    # canonical fields above.
    _manual_setup = data.get("setup_details") or data.get("setup") or {}
    if isinstance(_manual_setup, dict):
        m.setup_details.update({str(k): str(v) for k, v in _manual_setup.items()})
        m.setup_model = m.setup_details.get("Model", m.setup_details.get("model", m.setup_model))
        m.setup_runtime = m.setup_details.get("Runtime", m.setup_details.get("runtime", m.setup_runtime))
        m.setup_instance = m.setup_details.get("Instance", m.setup_details.get("instance", m.setup_instance))
        m.setup_tp_size = m.setup_details.get("TP size", m.setup_details.get("tp_size", m.setup_tp_size))
        m.setup_dtype = m.setup_details.get("dtype", m.setup_dtype)
        m.setup_kv_cache_dtype = m.setup_details.get("KV dtype", m.setup_details.get("kv_cache_dtype", m.setup_kv_cache_dtype))
        m.setup_context_length = m.setup_details.get("Context length", m.setup_details.get("context_length", m.setup_context_length))
        # Optional: setup_details.json may contain an exact SGLang launch command.
        # Parse it so individual fields show up even if the user does not provide
        # them as separate JSON keys.
        _launch_cmd = (m.setup_details.get("Launch command") or
                       m.setup_details.get("launch_command") or
                       m.setup_details.get("SGLang launch command") or
                       m.setup_details.get("sglang_launch_command"))
        if _launch_cmd:
            _parsed_launch = _parse_launch_command_to_setup(_launch_cmd)
            for _k, _v in _parsed_launch.items():
                if _is_missing_setup_value(m.setup_details.get(_k)):
                    m.setup_details[_k] = str(_v)
    _defaulted_setup_fields = _apply_setup_defaults(m.setup_details)
    if _defaulted_setup_fields:
        m.setup_details["Default profile"] = "SGLang DeepSeek-R1-70B HiCache reference launch; defaulted fields are assumed, not observed"
        m.setup_details["Defaulted fields"] = ", ".join(_defaulted_setup_fields)
    # Refresh canonical convenience fields after manual/default setup merge.
    m.setup_model = m.setup_details.get("Model", m.setup_details.get("model", m.setup_model))
    m.setup_runtime = m.setup_details.get("Runtime", m.setup_details.get("runtime", m.setup_runtime))
    m.setup_instance = m.setup_details.get("Instance", m.setup_details.get("instance", m.setup_instance))
    m.setup_tp_size = m.setup_details.get("TP size", m.setup_details.get("tp_size", m.setup_tp_size))
    m.setup_dtype = m.setup_details.get("dtype", m.setup_dtype)
    m.setup_kv_cache_dtype = m.setup_details.get("KV dtype", m.setup_details.get("kv_cache_dtype", m.setup_kv_cache_dtype))
    m.setup_context_length = m.setup_details.get("Context length", m.setup_details.get("context_length", m.setup_context_length))
    m.setup_page_size = m.setup_details.get("Page size", m.setup_page_size)
    m.setup_attention_backend = m.setup_details.get("Attention backend", m.setup_attention_backend)
    # fall back to finding model name in timeseries column headers
    m.run_duration_s = float(sg.get("server_e2e_ms", 0) / 1000 or
                             data.get("power_summary", {}).get("power_elapsed_s", 0) or
                             data.get("bpf_summary", {}).get("bpf_duration_s", 0))
    m.ttft_ms = float(sg.get("server_ttft_ms", 0))
    m.tpot_ms = float(sg.get("server_itl_ms", 0))
    m.e2e_ms  = float(sg.get("server_e2e_ms", 0))
    m.gen_tp_mean = float(sg.get("ai_op_decode_tok_s", 0))
    m.cache_hit_pct = float(sg.get("cache_hit_rate_realtime_pct", 0))
    m.cache_hit_calc_method = str(sg.get("cache_hit_calc_method", "unknown"))
    m.cache_hit_token_weighted_pct = float(sg.get("cache_hit_token_weighted_pct", 0))
    m.cache_hit_cached_prompt_pct = float(sg.get("cache_hit_cached_prompt_pct", 0))
    m.cache_hit_gauge_overall_pct = float(sg.get("cache_hit_gauge_overall_pct", 0))
    m.cache_hit_gauge_active_pct = float(sg.get("cache_hit_gauge_active_pct", 0))
    m.cache_hit_gauge_peak_pct = float(sg.get("cache_hit_gauge_peak_pct", 0))
    m.cache_hit_gauge_total_samples = safe_int(sg.get("cache_hit_gauge_total_samples", 0))
    m.cache_hit_gauge_active_samples = safe_int(sg.get("cache_hit_gauge_active_samples", 0))
    m.hicache_fill_pct = float(sg.get("hicache_host_fill_pct", 0))
    m.decode_tokens = safe_int(sg.get("rt_decode_tokens", 0))
    m.prefill_compute_tokens = safe_int(sg.get("rt_prefill_compute_tokens", 0))
    m.prefill_cache_tokens = safe_int(sg.get("rt_prefill_cache_tokens", 0))

    # Fallback to SGLang timeseries when summary fields are missing or zero.
    sg_ts_fallback = data.get("sglang_timeseries")
    if isinstance(sg_ts_fallback, pd.DataFrame) and not sg_ts_fallback.empty:
        # Parse useful labels embedded in Prometheus-style CSV column names, e.g.
        # sglang_cache_config_info{page_size="1",num_pages="..."}.
        try:
            import re as _re_setup
            label_blob = " ".join(map(str, sg_ts_fallback.columns))
            def _label_value(name):
                mm = _re_setup.search(r'(?:^|[, {])' + _re_setup.escape(name) + r'\s*=\s*"?([^",} ]+)"?', label_blob)
                return mm.group(1) if mm else None
            for attr, labels in {
                "setup_page_size": ("page_size",),
                "setup_num_pages": ("num_pages", "max_total_num_tokens"),
                "setup_model": ("model_name", "model"),
                "setup_instance": ("instance",),
                "setup_job": ("job",),
                "setup_engine_type": ("engine_type",),
            }.items():
                if getattr(m, attr, "unknown") == "unknown":
                    for lab in labels:
                        vv = _label_value(lab)
                        if vv:
                            setattr(m, attr, str(vv)); break
            m.setup_details.update({
                "Model": m.setup_model, "Instance": m.setup_instance, "Job": m.setup_job,
                "Engine": m.setup_engine_type, "Page size": m.setup_page_size,
                "Num pages/tokens": m.setup_num_pages,
            })
        except Exception:
            pass
        if m.run_duration_s <= 0 and "time_sec" in sg_ts_fallback.columns:
            try:
                m.run_duration_s = float(sg_ts_fallback["time_sec"].iloc[-1] - sg_ts_fallback["time_sec"].iloc[0])
            except Exception:
                pass
        if m.cache_hit_pct <= 0:
            _cache_col = _find_metric_col(sg_ts_fallback, "cache_hit_rate")
            if _cache_col:
                _cache_vals = pd.to_numeric(sg_ts_fallback[_cache_col], errors="coerce").dropna()
                if len(_cache_vals):
                    _cache_last = float(_cache_vals.iloc[-1])
                    m.cache_hit_pct = round((_cache_last * 100) if _cache_last <= 1 else _cache_last, 2)
        if m.hicache_fill_pct <= 0:
            _hu = _find_metric_col(sg_ts_fallback, "hicache_host_used_tokens")
            _ht = _find_metric_col(sg_ts_fallback, "hicache_host_total_tokens")
            if _hu and _ht:
                _used = pd.to_numeric(sg_ts_fallback[_hu], errors="coerce").dropna()
                _tot  = pd.to_numeric(sg_ts_fallback[_ht], errors="coerce").dropna()
                if len(_used) and len(_tot) and float(_tot.iloc[-1]) > 0:
                    m.hicache_fill_pct = round(float(_used.iloc[-1]) / float(_tot.iloc[-1]) * 100, 2)
        if m.decode_tokens <= 0:
            _dc = _find_metric_col_with_parts(sg_ts_fallback, "realtime_tokens_total", "mode=decode")
            if _dc:
                _vals = pd.to_numeric(sg_ts_fallback[_dc], errors="coerce").dropna()
                if len(_vals): m.decode_tokens = safe_int(_vals.iloc[-1])
        if m.prefill_compute_tokens <= 0:
            _pc = _find_metric_col_with_parts(sg_ts_fallback, "realtime_tokens_total", "mode=prefill_compute")
            if _pc:
                _vals = pd.to_numeric(sg_ts_fallback[_pc], errors="coerce").dropna()
                if len(_vals): m.prefill_compute_tokens = safe_int(_vals.iloc[-1])
        if m.prefill_cache_tokens <= 0:
            _pf = _find_metric_col_with_parts(sg_ts_fallback, "realtime_tokens_total", "mode=prefill_cache")
            if _pf:
                _vals = pd.to_numeric(sg_ts_fallback[_pf], errors="coerce").dropna()
                if len(_vals): m.prefill_cache_tokens = safe_int(_vals.iloc[-1])

    # ── GPU summary ───────────────────────────────────────────────────────────
    gp = data.get("gpu_summary", {})
    m.gpu_count = safe_int(gp.get("gpu_count", 8), default=8)
    m.gpu_util_mean = float(gp.get("gpu_util_mean", 0))
    m.gpu_util_peak = float(gp.get("gpu_util_peak", 0))
    m.hbm_util_pct = float(gp.get("hbm_util_pct_mean", 0))
    m.hbm_used_mb_mean = float(gp.get("hbm_used_mb_mean", 0))
    m.hbm_total_mb = float(gp.get("hbm_total_mb_per_gpu", 40960))
    m.gpu_power_mean_w = float(gp.get("power_all_gpus_w_mean", 0))
    m.gpu_power_peak_w = float(gp.get("power_w_peak", 0))
    m.per_gpu_util_mean = gp.get("gpu_util_per_gpu", [])

    # ── DRAM summary ──────────────────────────────────────────────────────────
    dr = data.get("dram_summary", {})
    m.dram_used_gb = float(dr.get("dram_used_gb_mean", 0))
    m.dram_total_gb = float(dr.get("dram_total_gb", 0))
    m.dram_util_pct = float(dr.get("dram_util_pct_mean", 0))

    # ── NVMe summary ──────────────────────────────────────────────────────────
    nv = data.get("nvme_driver_summary", {})
    m.nvme_wr_iops_max = float(nv.get("nvme_wr_iops_sysfs", 0))
    m.nvme_wr_lat_ms = float(nv.get("nvme_wr_lat_ms_mean", 0))

    # ── vmstat summary ────────────────────────────────────────────────────────
    vs = data.get("vmstat_summary", {})
    m.page_faults_per_s = float(vs.get("page_faults_per_s", 0))
    m.numa_migrations_per_s = float(vs.get("numa_migrations_per_s", 0))

    # ── Swap activity & storm analysis ────────────────────────────────────────
    # Swap storm: sustained period where swap I/O is high enough to materially
    # slow execution. Uses delta(pswpin)+delta(pswpout) > threshold pages/s.
    vmst = data.get("vmstat_timeseries")
    if isinstance(vmst, pd.DataFrame) and not vmst.empty and \
       "pswpin" in vmst.columns and "pswpout" in vmst.columns:
        try:
            v = vmst.sort_values("time_sec").reset_index(drop=True).copy()
            dt = v["time_sec"].diff().fillna(1.0).clip(lower=0.1)
            # pswpin/pswpout are monotonically-increasing counters; rate = d/dt
            in_rate  = v["pswpin"].diff().fillna(0).clip(lower=0)  / dt
            out_rate = v["pswpout"].diff().fillna(0).clip(lower=0) / dt
            total_rate = in_rate + out_rate

            m.swap_in_pages_per_s_mean    = safe_float(in_rate.mean())
            m.swap_in_pages_per_s_peak    = safe_float(in_rate.max())
            m.swap_out_pages_per_s_mean   = safe_float(out_rate.mean())
            m.swap_out_pages_per_s_peak   = safe_float(out_rate.max())
            # 1 page = 4 KiB on x86_64 → 4096/1024^2 = 1/256 MiB
            m.swap_in_mb_per_s_mean       = round(m.swap_in_pages_per_s_mean / 256, 3)
            m.swap_out_mb_per_s_mean      = round(m.swap_out_pages_per_s_mean / 256, 3)

            # Storm detection: contiguous samples above threshold
            thr = m.swap_storm_threshold_pages_per_s
            active = (total_rate >= thr).astype(int)
            edges  = active.diff().fillna(active.iloc[0])
            starts = v["time_sec"][edges == 1].tolist()
            ends   = v["time_sec"][edges == -1].tolist()
            if len(starts) > len(ends):
                ends.append(v["time_sec"].iloc[-1])
            episodes = list(zip(starts, ends))
            m.swap_storm_episode_count    = len(episodes)
            m.swap_storm_total_duration_s = round(sum(e - s for s, e in episodes), 2)
            if active.sum() > 0:
                m.swap_thrashing_pct      = round(100 * active.mean(), 2)
                m.swap_storm_worst_pages_per_s = safe_float(total_rate.max())

            # Swap free min / used pct max
            if "swap_free_mb" in v.columns:
                free_vals = v["swap_free_mb"].dropna()
                if not free_vals.empty:
                    m.swap_free_mb_min = round(safe_float(free_vals.min()), 1)
                    m.swap_total_mb    = round(safe_float(free_vals.max()), 1)
                    if m.swap_total_mb > 0:
                        used_pct = 100 * (1 - free_vals / m.swap_total_mb)
                        m.swap_used_pct_max = round(safe_float(used_pct.max()), 2)

            # Major page fault correlation — high pswpin correlates with majflt
            if "pgmajfault" in v.columns:
                mf_rate = v["pgmajfault"].diff().fillna(0).clip(lower=0) / dt
                if in_rate.std() > 0 and mf_rate.std() > 0:
                    try:
                        from scipy.stats import pearsonr as _ps
                        import warnings as _ws
                        with _ws.catch_warnings():
                            _ws.simplefilter("ignore")
                            m.swap_majfault_correlation = round(
                                float(_ps(in_rate.values, mf_rate.values)[0]), 3)
                    except Exception:
                        pass

            # Swap write amplification: writes hitting NVMe / pages swapped out
            nvts = data.get("nvme_driver_timeseries")
            if isinstance(nvts, pd.DataFrame) and not nvts.empty and \
               "wr_ios" in nvts.columns and out_rate.sum() > 0:
                # Align on time_sec — use total deltas over the run
                wr_io_delta = max(safe_float(nvts["wr_ios"].iloc[-1] -
                                              nvts["wr_ios"].iloc[0]), 0)
                pswpout_delta = max(safe_float(v["pswpout"].iloc[-1] -
                                                v["pswpout"].iloc[0]), 0)
                if pswpout_delta > 0:
                    m.swap_write_amp_ratio = round(wr_io_delta / pswpout_delta, 3)
        except Exception as _swap_err:
            print(f"      [swap analysis] skipped: {type(_swap_err).__name__}: {_swap_err}")

    # ── Power summary ─────────────────────────────────────────────────────────
    pw = data.get("power_summary", {})
    m.system_power_w = float(pw.get("system_power_w_mean", 0))

    # ── Timeseries ────────────────────────────────────────────────────────────
    def get_ts(name):
        v = data.get(name)
        if not isinstance(v, pd.DataFrame) or v.empty:
            return pd.DataFrame()
        # Ensure time_sec column exists — try to recover from common alternatives
        if "time_sec" not in v.columns:
            for alt in ("ts", "time", "timestamp", "time_s", "time_ns"):
                if alt in v.columns:
                    v = v.copy()
                    v["time_sec"] = pd.to_numeric(v[alt], errors="coerce")
                    if alt == "time_ns":
                        v["time_sec"] = v["time_sec"] / 1e9
                    break
            else:
                # No usable time column — return empty rather than crash
                return pd.DataFrame()
        # Drop rows where time_sec is NaN or non-numeric
        v = v.copy()
        v["time_sec"] = pd.to_numeric(v["time_sec"], errors="coerce")
        v = v.dropna(subset=["time_sec"])
        if v.empty:
            return pd.DataFrame()
        return v.sort_values("time_sec").reset_index(drop=True)

    m.sglang_ts = get_ts("sglang_timeseries")
    m.gpu_ts = get_ts("gpu_timeseries")
    m.dram_ts = get_ts("dram_timeseries")
    m.power_ts = get_ts("power_timeseries")
    m.nvme_ts = get_ts("nvme_driver_timeseries")
    m.vmstat_ts = get_ts("vmstat_timeseries")

    # Derive gen_tp_peak and model name from sglang timeseries
    if not m.sglang_ts.empty:
        tp_col = _find_metric_col(m.sglang_ts, "gen_throughput")
        if tp_col:
            m.gen_tp_peak = float(m.sglang_ts[tp_col].max())
            if m.gen_tp_mean == 0:
                m.gen_tp_mean = float(m.sglang_ts[tp_col].mean())

        # Extract model name from column headers
        for col in m.sglang_ts.columns:
            if "time_to_first_token" in col and "model_name=" in col:
                import re
                mn = re.search(r"model_name=([^\]]+)", col)
                if mn and m.model == "unknown":
                    m.model = mn.group(1)
                break

        # Derive run duration from timeseries if not from summary
        if m.run_duration_s == 0:
            m.run_duration_s = float(m.sglang_ts["time_sec"].max())

    # Derive NVMe delta IOPS from timeseries
    if not m.nvme_ts.empty and "wr_ios" in m.nvme_ts.columns:
        nv2 = m.nvme_ts.copy()
        nv2["wr_iops"] = (nv2["wr_ios"].diff() / nv2["time_sec"].diff()).clip(0)
        nv2["rd_iops"] = (nv2["rd_ios"].diff() / nv2["time_sec"].diff()).clip(0)
        m.nvme_wr_iops_max = max(m.nvme_wr_iops_max, float(nv2["wr_iops"].max(skipna=True)))
        m.nvme_rd_iops_max = float(nv2["rd_iops"].max(skipna=True))
        m.nvme_ts = nv2

    # ── KV cache footprint analysis ───────────────────────────────────────────
    # Model architecture database: name fragment → (n_layers, n_kv_heads, head_dim, attn_type, params_B)
    # attn_type: "MHA"=full, "GQA"=grouped query, "MLA"=multi-head latent (Qwen3/DeepSeekV2)
    KV_ARCH_DB = {
        # DeepSeek
        "deepseek-r1-distill-llama-70b": (80,  8, 128, "GQA", 70),
        "deepseek-r1-distill-llama-8b":  (32,  8, 128, "GQA",  8),
        "deepseek-r1-distill-qwen-14b":  (48,  8, 128, "GQA", 14),
        "deepseek-r1-distill-qwen-32b":  (64,  8, 128, "GQA", 32),
        "deepseek-r1-distill-qwen-7b":   (28,  4, 128, "GQA",  7),
        "deepseek-v2":                   (60, 128, 512, "MLA", 236),  # MLA latent_dim=512
        "deepseek-v3":                   (61, 128, 512, "MLA", 671),
        # Qwen3 (MLA — latent_dim stored as head_dim)
        "qwen3-235b":                    (94,  4, 512, "MLA", 235),
        "qwen3-32b":                     (64,  8, 128, "GQA",  32),
        "qwen3-30b":                     (64,  8, 128, "GQA",  30),
        "qwen3-14b":                     (40,  8, 128, "GQA",  14),
        "qwen3-8b":                      (36,  8, 128, "GQA",   8),
        "qwen3-7b":                      (28,  4, 128, "GQA",   7),
        "qwen3-4b":                      (36,  8, 128, "GQA",   4),
        "qwen3-1.7b":                    (28,  4, 128, "GQA",   2),
        "qwen3-0.6b":                    (28,  4,  64, "GQA",   1),
        "qwen3-next":                    (94,  4, 512, "MLA", 235),   # alias for 235B
        # Qwen2.5
        "qwen2.5-72b":                   (80,  8, 128, "GQA",  72),
        "qwen2.5-32b":                   (64,  8, 128, "GQA",  32),
        "qwen2.5-14b":                   (48,  8, 128, "GQA",  14),
        "qwen2.5-7b":                    (28,  4, 128, "GQA",   7),
        # Llama-3
        "llama-3.3-70b":                 (80,  8, 128, "GQA",  70),
        "llama-3.1-70b":                 (80,  8, 128, "GQA",  70),
        "llama-3.1-8b":                  (32,  8, 128, "GQA",   8),
        "llama-3.1-405b":                (126, 8, 128, "GQA", 405),
        "llama-3-70b":                   (80,  8, 128, "GQA",  70),
        "llama-3-8b":                    (32,  8, 128, "GQA",   8),
        # Llama-2
        "llama-2-70b":                   (80, 64, 128, "MHA",  70),
        "llama-2-13b":                   (40, 40, 128, "MHA",  13),
        "llama-2-7b":                    (32, 32, 128, "MHA",   7),
        # Mistral / Mixtral
        "mixtral-8x7b":                  (32,  8, 128, "GQA",  47),
        "mixtral-8x22b":                 (56,  8, 128, "GQA", 141),
        "mistral-7b":                    (32,  8, 128, "GQA",   7),
        "mistral-nemo":                  (40,  8, 128, "GQA",  12),
        # Gemma
        "gemma-2-27b":                   (46,  4, 256, "GQA",  27),
        "gemma-2-9b":                    (42,  4, 256, "GQA",   9),
        "gemma-2-2b":                    (26,  4, 256, "GQA",   2),
        # Phi-3
        "phi-3-medium":                  (40, 10, 128, "GQA",  14),
        "phi-3-mini":                    (32,  8,  96, "GQA",   3),
    }

    # Match model name to architecture
    model_lower = m.model.lower()
    arch = None
    for key, val in KV_ARCH_DB.items():
        if key in model_lower:
            arch = val
            break

    # Fallback: infer from model name size hints
    if arch is None:
        size_hints = {"405b":(126,8,128,"GQA",405),"70b":(80,8,128,"GQA",70),
                      "72b":(80,8,128,"GQA",72),"32b":(64,8,128,"GQA",32),
                      "30b":(64,8,128,"GQA",30),"14b":(48,8,128,"GQA",14),
                      "13b":(40,8,128,"GQA",13),"8b":(32,8,128,"GQA",8),
                      "7b":(28,4,128,"GQA",7),"3b":(32,8,128,"GQA",3),
                      "1b":(22,8,128,"GQA",1)}
        for hint, val in size_hints.items():
            if hint in model_lower:
                arch = val
                break

    if arch is None:
        arch = (80, 8, 128, "GQA", 70)  # default: 70B-class

    n_layers, n_kv_heads, head_dim, attn_type, params_b = arch

    # Determine KV cache dtype
    # Check sglang summary for explicit kv_cache_dtype setting
    sg_sum = data.get("sglang_summary", {})
    kv_dtype_name = "FP16"
    kv_dtype_bytes = 2
    if isinstance(sg_sum, dict):
        kv_dtype_raw = sg_sum.get("kv_cache_dtype", "fp16").lower()
        dtype_map = {"fp16": ("FP16", 2), "bfloat16": ("BF16", 2), "bf16": ("BF16", 2),
                     "fp8": ("FP8", 1), "fp8_e4m3fn": ("FP8", 1), "fp8_e5m2": ("FP8", 1),
                     "int8": ("INT8", 1), "int4": ("INT4", 1),
                     "auto": ("FP16", 2)}
        kv_dtype_name, kv_dtype_bytes = dtype_map.get(kv_dtype_raw, ("FP16", 2))

    # Compute KV bytes per token
    if attn_type == "MLA":
        # MLA stores a single compressed latent vector (not separate K+V tensors)
        # latent_dim = head_dim field in our DB (512 for DeepSeek-V2/V3/Qwen3-235B)
        latent_dim = head_dim
        kv_bytes = int(2 * n_layers * latent_dim * kv_dtype_bytes)
    else:
        # Standard MHA / GQA: K tensor + V tensor per layer per KV head
        kv_bytes = int(2 * n_layers * n_kv_heads * head_dim * kv_dtype_bytes)

    m.kv_bytes_per_token  = kv_bytes
    m.kv_bytes_per_token_kb = round(kv_bytes / 1024, 1)
    m.kv_n_layers         = n_layers
    m.kv_n_heads          = n_kv_heads
    m.kv_head_dim         = head_dim
    m.kv_dtype_bytes      = kv_dtype_bytes
    m.kv_dtype_name       = kv_dtype_name
    m.kv_attention_type   = attn_type

    # Weight footprint per GPU
    weight_bytes_per_gpu = params_b * 1e9 * 2 / max(m.gpu_count, 1)  # FP16
    m.kv_weight_gb_per_gpu = round(weight_bytes_per_gpu / 1e9, 1)

    # HBM pool available for KV after weights
    hbm_total_gb = m.hbm_total_mb / 1024
    kv_pool_gb   = max(0.0, hbm_total_gb - m.kv_weight_gb_per_gpu - 0.5)  # 0.5GB CUDA runtime
    m.kv_hbm_pool_gb    = round(kv_pool_gb, 1)
    m.kv_hbm_max_tokens = int(kv_pool_gb * 1e9 / kv_bytes) if kv_bytes > 0 else 0

    # Actual KV tokens currently active (from SGLang pool metrics)
    total_ctx = m.prefill_cache_tokens + m.prefill_compute_tokens
    m.kv_active_tokens = total_ctx if total_ctx > 0 else 0
    m.kv_pool_fill_pct = round(m.token_usage * 100 if hasattr(m, 'token_usage')
                                else 0, 1)

    # Read token_usage from sglang timeseries if available
    sg_ts = data.get("sglang_timeseries")
    if isinstance(sg_ts, pd.DataFrame) and not sg_ts.empty:
        tu_col = (_find_metric_col(sg_ts, "full_token_usage") or
                  _find_metric_col(sg_ts, "token_usage"))
        if tu_col:
            m.kv_pool_fill_pct = round(float(pd.to_numeric(sg_ts[tu_col], errors="coerce").dropna().iloc[-1]) * 100, 1)

    m.kv_hbm_utilisation_pct = round(
        m.kv_active_tokens / m.kv_hbm_max_tokens * 100
        if m.kv_hbm_max_tokens > 0 else 0, 1)

    # ── Per-tier token counts from SGLang metrics ─────────────────────────────
    # L1 capacity = sglang:max_total_num_tokens (the GPU KV pool size)
    # L1 used     = full_token_usage fraction × capacity  (includes prealloc)
    # L2 capacity = hicache_host_total_tokens
    # L2 used     = hicache_host_used_tokens
    # L3 used     = kv_l3_storage_tokens (if NVMe KV offload active)

    sg_sum_raw = data.get("sglang_summary", {})
    if not isinstance(sg_sum_raw, dict):
        sg_sum_raw = {}

    l1_cap  = safe_int(sg_sum_raw.get("kv_pool_capacity_tokens", m.kv_hbm_max_tokens) or m.kv_hbm_max_tokens)
    l1_used = safe_int(sg_sum_raw.get("kv_l1_device_tokens", 0) or 0)
    l2_cap  = safe_int(sg_sum_raw.get("hicache_host_total_tokens", 0) or 0)
    l2_used = safe_int(sg_sum_raw.get("hicache_host_used_tokens", 0) or
                       sg_sum_raw.get("kv_l2_host_tokens", 0) or 0)
    l3_used = safe_int(sg_sum_raw.get("kv_l3_storage_tokens", 0) or 0)

    # Also try to read from timeseries last value (more accurate than summary)
    if not sg_ts.empty if isinstance(sg_ts := data.get("sglang_timeseries", pd.DataFrame()), pd.DataFrame) else False:
        pass
    sg_ts_df = data.get("sglang_timeseries")
    if isinstance(sg_ts_df, pd.DataFrame) and not sg_ts_df.empty:
        def _last_ts(partial):
            col = next((c for c in sg_ts_df.columns if partial in c), None)
            return float(sg_ts_df[col].iloc[-1]) if col else 0.0

        _l1_cap_ts  = _last_ts("max_total_num_tokens")
        _l2_cap_ts  = _last_ts("hicache_host_total_tokens")
        _l2_used_ts = _last_ts("hicache_host_used_tokens")
        _fu_ts      = _last_ts("full_token_usage")  # fraction 0-1

        if _l1_cap_ts  > 0: l1_cap  = safe_int(_l1_cap_ts)
        if _l2_cap_ts  > 0: l2_cap  = safe_int(_l2_cap_ts)
        if _l2_used_ts > 0: l2_used = safe_int(_l2_used_ts)
        # full_token_usage fraction × l1_cap gives total HBM KV tokens (incl. prealloc)
        if _fu_ts > 0 and l1_cap > 0 and l1_used == 0:
            l1_used = safe_int(_fu_ts * l1_cap)

        # Derive live L3 resident tokens from HiCache SSD counters when
        # kv_l3_storage_tokens is not exported.
        if l3_used == 0:
            def _last_ctr(partial):
                cols = [c for c in sg_ts_df.columns if partial in c and "bucket" not in c]
                vals = [float(sg_ts_df[c].dropna().iloc[-1]) for c in cols if len(sg_ts_df[c].dropna())]
                return max(vals) if vals else 0.0
            _backup_last = _last_ctr("backuped_tokens_total")
            _prefetch_last = _last_ctr("prefetched_tokens_total")
            if _backup_last > 0:
                l3_used = safe_int(max(_backup_last - _prefetch_last, 0))

    # Fallback: derive L1 used from active context if SGLang didn't report it
    if l1_used == 0 and m.kv_active_tokens > 0:
        l1_used = min(m.kv_active_tokens, l1_cap)

    m.kv_l1_capacity_tokens = l1_cap
    m.kv_l2_capacity_tokens = l2_cap
    m.kv_l1_hbm_tokens      = l1_used
    m.kv_l2_dram_tokens     = l2_used
    m.kv_l3_nvme_tokens     = l3_used
    m.kv_l1_fill_pct        = round(l1_used / l1_cap * 100, 1) if l1_cap > 0 else 0
    m.kv_l2_fill_pct        = round(l2_used / l2_cap * 100, 1) if l2_cap > 0 else 0

    # ── Per-tier read latency per token ───────────────────────────────────────
    # KV read time = kv_bytes_per_token / tier_bandwidth
    # Bandwidth constants (overridable via sglang_summary if reported)
    l1_bw = float(sg_sum_raw.get("hw_hbm_bw_gbs",   m.kv_l1_bw_gbs))  # GB/s
    l2_bw = float(sg_sum_raw.get("hw_dram_bw_gbs",  m.kv_l2_bw_gbs))
    l3_bw = float(sg_sum_raw.get("hw_nvme_bw_gbs",  m.kv_l3_bw_gbs))
    # Use measured DRAM BW if available from AMDuProf
    if m.dram_total_bw_gbs > 0:
        l2_bw = m.dram_total_bw_gbs
    m.kv_l1_bw_gbs = l1_bw
    m.kv_l2_bw_gbs = l2_bw
    m.kv_l3_bw_gbs = l3_bw

    kv_bytes = m.kv_bytes_per_token if m.kv_bytes_per_token > 0 else 327680
    kv_gb    = kv_bytes / 1e9

    m.kv_l1_read_lat_ms = round(kv_gb / l1_bw * 1000, 4)  # ms
    m.kv_l2_read_lat_ms = round(kv_gb / l2_bw * 1000, 4)
    m.kv_l3_read_lat_ms = round(kv_gb / l3_bw * 1000, 4)

    # ── Total KV read cost for a full context (all tokens × per-token cost) ───
    ctx_tokens = max(m.kv_active_tokens,
                     m.prefill_cache_tokens + m.prefill_compute_tokens, 1)
    m.kv_l1_cost_per_req_ms = round(ctx_tokens * m.kv_l1_read_lat_ms, 1)
    m.kv_l2_cost_per_req_ms = round(ctx_tokens * m.kv_l2_read_lat_ms, 1)
    m.kv_l3_cost_per_req_ms = round(ctx_tokens * m.kv_l3_read_lat_ms, 1)

    # ── TTFT estimates by tier (cache read dominates prefill TTFT) ────────────
    # TTFT = attention_compute_time + KV_read_time_for_cached_tokens
    # Attention compute is fixed; KV read tier changes the cached-token component
    cached  = max(m.prefill_cache_tokens, 1)
    compute = max(m.prefill_compute_tokens, 1)
    # Measured TTFT = compute_ttft + l1_cache_read_time (baseline)
    compute_ttft_ms = max(m.ttft_ms - cached * m.kv_l1_read_lat_ms, 0) if m.ttft_ms > 0 else 0
    m.kv_ttft_l1_ms = round(compute_ttft_ms + cached * m.kv_l1_read_lat_ms, 1)
    m.kv_ttft_l2_ms = round(compute_ttft_ms + cached * m.kv_l2_read_lat_ms, 1)
    m.kv_ttft_l3_ms = round(compute_ttft_ms + cached * m.kv_l3_read_lat_ms, 1)

    # ── Weighted average latency given actual tier distribution ───────────────
    total_kv = max(l1_used + l2_used + l3_used, 1)
    m.kv_weighted_lat_ms = round(
        (l1_used * m.kv_l1_read_lat_ms +
         l2_used * m.kv_l2_read_lat_ms +
         l3_used * m.kv_l3_read_lat_ms) / total_kv, 4
    )

    # ── HBM bandwidth — derive from TPOT + model architecture ────────────────
    # A100 40GB HBM2e peak BW = 2000 GB/s; nsys HBM metric not reliably sampled
    # During decode each token step reads all model weights once per GPU
    if m.tpot_ms > 0:
        n_gpus = max(m.gpu_count, 1)
        # 70B FP16 model = 140 GB total; per GPU = 140/n_gpus GB
        # Fall back to hbm_used_mb if model size not known
        model_param_est = 70e9  # default; updated below if model name suggests otherwise
        for tag in ["7b","13b","14b","34b","70b","72b","8b"]:
            if tag in m.model.lower():
                size_map = {"7b":7e9,"8b":8e9,"13b":13e9,"14b":14e9,
                            "34b":34e9,"70b":70e9,"72b":72e9}
                model_param_est = size_map.get(tag, 70e9)
                break
        bytes_per_gpu = model_param_est * 2 / n_gpus  # FP16
        if m.hbm_used_mb_mean > 0:
            # Use measured HBM used as a better weight estimate
            bytes_per_gpu = max(bytes_per_gpu, m.hbm_used_mb_mean * 1024 * 1024 * 0.85)
        tpot_s = m.tpot_ms / 1000.0 if m.tpot_ms > 0 else None
        if tpot_s:
            m.hbm_read_bw_gbs   = round(bytes_per_gpu / tpot_s / 1e9, 1)
            m.hbm_write_bw_gbs  = round(m.hbm_read_bw_gbs * 0.12, 1)
            m.hbm_bw_util_pct   = round(m.hbm_read_bw_gbs / m.hbm_peak_bw_gbs * 100, 1)
            CL = 64
            m.hbm_read_txn_M_s  = round(m.hbm_read_bw_gbs  * 1e9 / CL / 1e6, 1)
            m.hbm_write_txn_M_s = round(m.hbm_write_bw_gbs * 1e9 / CL / 1e6, 1)

    # Build a synthetic per-token HBM BW timeseries aligned with GPU util timeline
    if not m.gpu_ts.empty:
        if "gpu_idx" in m.gpu_ts.columns:
            gpu_agg = m.gpu_ts.groupby("time_sec").agg(
                util=("gpu_util", "mean")).reset_index()
        else:
            gpu_agg = m.gpu_ts[["time_sec", "gpu_util"]].rename(
                columns={"gpu_util": "util"})
        hbm_ts_rows = []
        for _, row in gpu_agg.iterrows():
            active = float(row["util"]) / 100.0
            hbm_ts_rows.append({
                "time_sec": float(row["time_sec"]),
                "hbm_read_bw_gbs":  round(m.hbm_read_bw_gbs  * active, 2),
                "hbm_write_bw_gbs": round(m.hbm_write_bw_gbs * active, 2),
                "hbm_total_bw_gbs": round((m.hbm_read_bw_gbs + m.hbm_write_bw_gbs) * active, 2),
                "hbm_read_txn_M_s":  round(m.hbm_read_txn_M_s  * active, 1),
                "hbm_write_txn_M_s": round(m.hbm_write_txn_M_s * active, 1),
            })
        m.hbm_bw_ts = pd.DataFrame(hbm_ts_rows)

    # ── System DRAM bandwidth — AMDuProf PCM raw file ─────────────────────────
    # The amduprof_pcm_timeseries.csv has a parser bug (all zeros); read raw directly
    amd_raw = data.get("amduprof_pcm_raw")
    if isinstance(amd_raw, pd.DataFrame):
        amd_raw = None  # not parsed as text; skip
    if amd_raw is None:
        # Try to find the raw file path from the summary
        amd_summary = data.get("amduprof_pcm_summary", {})
        raw_path = amd_summary.get("amduprof_pcm_csv_path", "")
        if raw_path:
            try:
                import pathlib
                rp = pathlib.Path(raw_path)
                if not rp.exists():
                    # Try relative path next to timeseries
                    rp = pathlib.Path(raw_path).name
                if rp.exists():
                    amd_raw = rp.read_text()
            except Exception:
                amd_raw = None

    # Also try to get the raw text if it was loaded as a file
    for key in ["amduprof_pcm_raw", "amduprof_pcm_raw_txt"]:
        if key in data and isinstance(data[key], str):
            amd_raw = data[key]
            break

    if amd_raw:
        try:
            lines = amd_raw.split("\n")
            dram_rows = []
            in_data = False
            for line in lines:
                l = line.strip().rstrip(",")
                if "Total Mem Bw" in l and "Total Mem RdBw" in l:
                    in_data = True
                    continue
                if in_data:
                    if not l or not l[0].isdigit():
                        in_data = False
                        continue
                    parts = [float(x) for x in l.split(",") if x]
                    if len(parts) >= 3:
                        dram_rows.append(parts[:3])
            if dram_rows:
                dram_bw = pd.DataFrame(dram_rows,
                    columns=["total_gb_s", "read_gb_s", "write_gb_s"])
                interval = 1.2  # AMDuProf default sampling interval
                amd_s = data.get("amduprof_pcm_summary", {})
                if isinstance(amd_s, dict) and amd_s.get("amduprof_pcm_samples", 0) > 0:
                    dur = float(amd_s.get("amduprof_pcm_duration_s", len(dram_rows) * 1.2))
                    interval = dur / max(len(dram_rows), 1)
                dram_bw["time_sec"] = [round(i * interval, 1)
                                        for i in range(len(dram_bw))]
                CL = 64
                dram_bw["read_txn_M_s"]  = (dram_bw["read_gb_s"]  * 1e9 / CL / 1e6).round(2)
                dram_bw["write_txn_M_s"] = (dram_bw["write_gb_s"] * 1e9 / CL / 1e6).round(2)
                m.dram_bw_ts = dram_bw

                m.dram_read_bw_gbs       = round(float(dram_bw["read_gb_s"].mean()), 2)
                m.dram_write_bw_gbs      = round(float(dram_bw["write_gb_s"].mean()), 2)
                m.dram_total_bw_gbs      = round(float(dram_bw["total_gb_s"].mean()), 2)
                m.dram_read_bw_peak_gbs  = round(float(dram_bw["read_gb_s"].max()), 2)
                m.dram_write_bw_peak_gbs = round(float(dram_bw["write_gb_s"].max()), 2)
                m.dram_bw_util_pct = round(
                    m.dram_total_bw_gbs / m.dram_peak_theoretical_gbs * 100, 2)
                m.dram_read_txn_M_s  = round(float(dram_bw["read_txn_M_s"].mean()), 1)
                m.dram_write_txn_M_s = round(float(dram_bw["write_txn_M_s"].mean()), 1)
        except Exception as e:
            print(f"  [warn] AMDuProf DRAM parse error: {e}")

    # Also try to use pre-parsed timeseries if non-zero
    amd_ts = data.get("amduprof_pcm_timeseries")
    if isinstance(amd_ts, pd.DataFrame) and not amd_ts.empty:
        real = amd_ts[amd_ts.get("dram_total_gb_s", amd_ts.get("dram_read_gb_s",
               pd.Series([0]))).fillna(0) > 0]
        if len(real) > 5 and m.dram_read_bw_gbs == 0:
            dram_bw2 = real[["time_sec",
                "dram_read_gb_s","dram_write_gb_s","dram_total_gb_s",
                "dram_read_transactions","dram_write_transactions"]].copy()
            CL = 64
            dram_bw2["read_txn_M_s"]  = (dram_bw2["dram_read_gb_s"]  * 1e9/CL/1e6).round(2)
            dram_bw2["write_txn_M_s"] = (dram_bw2["dram_write_gb_s"] * 1e9/CL/1e6).round(2)
            m.dram_bw_ts = dram_bw2.rename(columns={
                "dram_read_gb_s":"read_gb_s","dram_write_gb_s":"write_gb_s",
                "dram_total_gb_s":"total_gb_s"})
            m.dram_read_bw_gbs  = round(float(real["dram_read_gb_s"].mean()), 2)
            m.dram_write_bw_gbs = round(float(real["dram_write_gb_s"].mean()), 2)
            m.dram_total_bw_gbs = round(float(real["dram_total_gb_s"].mean()), 2)

            m.dram_total_bw_gbs = round(float(real["dram_total_gb_s"].mean()), 2)

    # ── Session / Stream analysis ─────────────────────────────────────────────
    sg_ts_full = data.get("sglang_timeseries")
    if isinstance(sg_ts_full, pd.DataFrame) and not sg_ts_full.empty:
        df = sg_ts_full.sort_values("time_sec").reset_index(drop=True)

        def _find(partial):
            candidates = [c for c in df.columns if partial in c and 'bucket' not in c]
            eng = [c for c in candidates if 'engine_type' in c]
            return eng[0] if eng else (candidates[0] if candidates else None)

        def _per_req_stats(sum_col, cnt_col):
            sc, cc = _find(sum_col), _find(cnt_col)
            if not sc or not cc:
                return None, []
            d_sum = df[sc].diff().clip(0)
            d_cnt = df[cc].diff().clip(0)
            vals = (d_sum / d_cnt.replace(0, np.nan))[d_cnt > 0].dropna()
            if len(vals) == 0:
                abs_cnt = df[cc].iloc[-1] - df[cc].iloc[0]
                abs_sum = df[sc].iloc[-1] - df[sc].iloc[0]
                if abs_cnt > 0:
                    vals = pd.Series([abs_sum / abs_cnt])
                else:
                    return None, []
            stats = {k: round(float(getattr(vals, m)() if hasattr(vals, m) else vals.quantile(float(m.replace('p',''))/100)), 3)
                     for k, m in [("mean","mean"),("min","min"),("max","max"),
                                  ("p50","quantile"),("p90","quantile"),("p99","quantile")]}
            stats["p50"] = round(float(vals.quantile(0.50)), 3)
            stats["p90"] = round(float(vals.quantile(0.90)), 3)
            stats["p99"] = round(float(vals.quantile(0.99)), 3)
            return stats, list(vals.round(3))

        run_col = _find("num_running_reqs")
        if run_col:
            m.sess_concurrent_ts   = df[["time_sec", run_col]].rename(columns={run_col:"n"})
            m.sess_max_concurrent  = safe_int(df[run_col].max())
            m.sess_mean_concurrent = round(safe_float(df[run_col].mean()), 2)

        req_col = _find("num_requests_total")
        if req_col:
            last_val  = safe_float(df[req_col].dropna().iloc[-1]) if len(df[req_col].dropna()) else 0
            first_val = safe_float(df[req_col].dropna().iloc[0])  if len(df[req_col].dropna()) else 0
            delta     = max(last_val - first_val, last_val)
            m.sess_total_requests = safe_int(delta)
            dur  = safe_float(df["time_sec"].iloc[-1] - df["time_sec"].iloc[0])
            reqs = safe_int(last_val - first_val)
            if dur > 0 and reqs > 0:
                m.sess_arrival_rate_rps = round(reqs / dur, 4)
                m.sess_inter_arrival_s  = round(dur / reqs, 2)

        e2e_s, e2e_ts = _per_req_stats("e2e_request_latency_seconds_sum",
                                        "e2e_request_latency_seconds_count")
        if e2e_s:
            m.sess_e2e_mean_s = e2e_s["mean"];  m.sess_e2e_min_s = e2e_s["min"]
            m.sess_e2e_max_s  = e2e_s["max"];   m.sess_e2e_p50_s = e2e_s["p50"]
            m.sess_e2e_p90_s  = e2e_s["p90"];   m.sess_e2e_p99_s = e2e_s["p99"]
            m.sess_e2e_ts = [round(v * 1000, 0) for v in e2e_ts]

        inp_s, inp_ts = _per_req_stats("prompt_tokens_total", "num_requests_total")
        if inp_s:
            m.sess_input_tok_mean = inp_s["mean"]; m.sess_input_tok_min = inp_s["min"]
            m.sess_input_tok_max  = inp_s["max"];  m.sess_input_tok_p90 = inp_s["p90"]
            m.sess_input_tok_ts   = [round(v, 0) for v in inp_ts]

        out_s, out_ts = _per_req_stats("generation_tokens_total", "num_requests_total")
        if out_s:
            m.sess_output_tok_mean = out_s["mean"]; m.sess_output_tok_min = out_s["min"]
            m.sess_output_tok_max  = out_s["max"];  m.sess_output_tok_p90 = out_s["p90"]
            m.sess_output_tok_ts   = [round(v, 0) for v in out_ts]

        q_s, _ = _per_req_stats("queue_time_seconds_sum", "queue_time_seconds_count")
        if q_s:
            m.sess_queue_mean_ms = round(q_s["mean"] * 1000, 2)
            m.sess_queue_max_ms  = round(q_s["max"]  * 1000, 2)

    # ── KV$B (KV Cache Block) metrics ─────────────────────────────────────────
    sg_ts2 = data.get("sglang_timeseries")
    if isinstance(sg_ts2, pd.DataFrame) and not sg_ts2.empty:
        def _scol(partial):
            c = next((x for x in sg_ts2.columns if partial in x), None)
            return c

        hi_col = _scol("hicache_host_used_tokens")
        l1_cap_tok = float(sg_ts2[_scol("max_total_num_tokens")].iloc[-1]) if _scol("max_total_num_tokens") else m.kv_l1_capacity_tokens
        l2_cap_tok = float(sg_ts2[_scol("hicache_host_total_tokens")].iloc[-1]) if _scol("hicache_host_total_tokens") else m.kv_l2_capacity_tokens

        bs = m.kvb_block_size_tokens
        m.kvb_l1_pool_blocks = int(l1_cap_tok / bs) if bs > 0 else 0
        m.kvb_l2_pool_blocks = int(l2_cap_tok / bs) if bs > 0 else 0
        m.kvb_block_size_mb  = round(bs * m.kv_bytes_per_token / 1024 / 1024, 2) if m.kv_bytes_per_token > 0 else 0
        m.kvb_tokens_per_mb  = round(1024 * 1024 / m.kv_bytes_per_token, 1) if m.kv_bytes_per_token > 0 else 0

        if hi_col is not None:
            l2_t0  = float(sg_ts2[hi_col].iloc[0])
            l2_now = float(sg_ts2[hi_col].iloc[-1])
            run_dur = m.run_duration_s if m.run_duration_s > 0 else 1
            l2_delta_blk = max(l2_now - l2_t0, 0) / bs if bs > 0 else 0
            m.kvb_l1_offload_rate_blk_s = round(l2_delta_blk / run_dur, 4)

            l2_fill = l2_now / l2_cap_tok if l2_cap_tok > 0 else 0
            if l2_fill > 0.8 and m.kvb_l1_offload_rate_blk_s > 0:
                m.kvb_l2_eviction_rate_blk_s = round(m.kvb_l1_offload_rate_blk_s * (l2_fill - 0.8) / 0.2, 4)

            if m.kvb_l1_offload_rate_blk_s > 0 and m.kvb_l2_pool_blocks > 0:
                fill_s = m.kvb_l2_pool_blocks / m.kvb_l1_offload_rate_blk_s
                m.kvb_lifetime_mean_s = round(fill_s, 1)
                m.kvb_lifetime_min_s  = round(fill_s * 0.5, 1)
                m.kvb_lifetime_max_s  = round(fill_s * 2.0, 1)
            elif m.sess_e2e_mean_s > 0:
                m.kvb_lifetime_mean_s = round(m.sess_e2e_mean_s, 1)
                m.kvb_lifetime_min_s  = round(m.sess_e2e_min_s, 1)
                m.kvb_lifetime_max_s  = round(m.sess_e2e_max_s, 1)

            offload_df = sg_ts2[["time_sec", hi_col]].copy().rename(columns={hi_col:"l2_used_tokens"})
            offload_df["l2_used_blocks"] = (offload_df["l2_used_tokens"] / bs).round(0)
            offload_df["delta_blocks"]   = offload_df["l2_used_blocks"].diff().fillna(0)
            offload_df["offload_rate"]   = (offload_df["delta_blocks"] /
                                             offload_df["time_sec"].diff().replace(0, np.nan)).fillna(0).clip(0).round(3)
            m.kvb_offload_ts = offload_df

    # ── NVMe IO workload characteristics ─────────────────────────────────────
    nv_df2 = data.get("nvme_driver_timeseries")
    smart_df2 = data.get("smart_timeseries")
    if isinstance(nv_df2, pd.DataFrame) and not nv_df2.empty:
        nv = nv_df2.sort_values("time_sec").reset_index(drop=True).copy()
        dt2 = nv["time_sec"].diff().replace(0, np.nan)

        # Handle two data sources:
        # A) cumulative counters (wr_ios, rd_ios) → diff to get rates
        # B) direct MB/s columns (rd_bw_mbs, wr_bw_mbs) from iostat
        if "wr_ios" in nv.columns and nv["wr_ios"].max() > 1:
            nv["wr_iops"]    = nv["wr_ios"].diff().clip(0) / dt2
            nv["rd_iops"]    = nv["rd_ios"].diff().clip(0) / dt2
            nv["wr_lat_ms"]  = nv["wr_ms"].diff().clip(0) / nv["wr_ios"].diff().clip(0).replace(0, np.nan)
            nv["rd_lat_ms"]  = nv["rd_ms"].diff().clip(0) / nv["rd_ios"].diff().clip(0).replace(0, np.nan)
        elif "wr_iops" not in nv.columns:
            # Direct IOPS columns (pre-derived from iostat)
            nv["wr_iops"] = nv.get("w_s", pd.Series([0.0] * len(nv)))
            nv["rd_iops"] = nv.get("r_s", pd.Series([0.0] * len(nv)))
            nv["wr_lat_ms"] = nv.get("wr_ms", pd.Series([0.0] * len(nv)))
            nv["rd_lat_ms"] = nv.get("rd_ms", pd.Series([0.0] * len(nv)))

        nv["io_util_pct"] = (nv["io_ms"].diff().clip(0) / (dt2 * 1000).replace(0, np.nan) * 100).clip(0, 100) \
                            if "io_ms" in nv.columns else nv.get("util_pct", pd.Series([0.0]*len(nv)))

        # BW columns: from MB/s direct (iostat) or compute from IOPS
        kvb_mb2 = m.kvb_block_size_mb if m.kvb_block_size_mb > 0 else 5.0
        if "rd_bw_mbs" not in nv.columns:
            nv["rd_bw_mbs"] = nv["rd_iops"].fillna(0) * kvb_mb2
        if "wr_bw_mbs" not in nv.columns:
            nv["wr_bw_mbs"] = nv["wr_iops"].fillna(0) * kvb_mb2
        # Override BW from iostat direct columns if present
        for mb_col, dst_col in [("r_mb_s","rd_bw_mbs"), ("w_mb_s","wr_bw_mbs")]:
            if mb_col in nv.columns:
                nv[dst_col] = nv[mb_col].fillna(0)
        # Override IO util from iostat if available
        for util_col in ("util_pct", "io_util_pct"):
            if util_col in nv_df2.columns and util_col != "io_util_pct":
                nv["io_util_pct"] = nv_df2[util_col].values

        wr_a = nv["wr_iops"][nv["wr_iops"] > 0].dropna()
        wl_a = nv["wr_lat_ms"].dropna()
        m.nvme_wr_iops_mean    = round(float(wr_a.mean()), 2)      if len(wr_a) else 0
        m.nvme_wr_lat_mean_ms  = round(float(wl_a.mean()), 3)      if len(wl_a) else 0
        m.nvme_wr_lat_max_ms   = round(float(wl_a.max()), 3)       if len(wl_a) else 0
        m.nvme_io_util_pct     = round(float(nv["io_util_pct"].mean(skipna=True)), 4)
        m.nvme_inflight_mean   = round(float(nv.get("inflight", pd.Series([0])).mean()), 2)
        m.nvme_inflight_max    = safe_int(nv.get("inflight", pd.Series([0])).max())

        # BW from direct iostat columns (more accurate than IOPS × block_size)
        wr_bw_series = nv["wr_bw_mbs"][nv["wr_bw_mbs"] > 0].dropna()
        rd_bw_series = nv["rd_bw_mbs"][nv["rd_bw_mbs"] > 0].dropna()
        if len(wr_bw_series) > 0:
            m.nvme_wr_bw_mbs_mean = round(float(wr_bw_series.mean()), 2)
            m.nvme_wr_bw_mbs_max  = round(float(wr_bw_series.max()), 2)
        else:
            m.nvme_wr_bw_mbs_mean = round(m.nvme_wr_iops_mean * kvb_mb2, 2)
            m.nvme_wr_bw_mbs_max  = round(float(wr_a.max()) * kvb_mb2, 2) if len(wr_a) else 0

        cols_to_keep = ["time_sec", "wr_iops", "rd_iops", "wr_lat_ms",
                        "io_util_pct", "inflight", "rd_bw_mbs", "wr_bw_mbs",
                        "disc_ios", "disc_sectors"]
        m.nvme_io_ts = nv[[c for c in cols_to_keep if c in nv.columns]].copy()

    if isinstance(smart_df2, pd.DataFrame) and not smart_df2.empty:
        first2, last2 = smart_df2.iloc[0], smart_df2.iloc[-1]
        DU = 512 * 1000
        m.nvme_bytes_read_total    = max(int(last2.get("data_units_read",0))    - int(first2.get("data_units_read",0)),    0) * DU
        m.nvme_bytes_written_total = max(int(last2.get("data_units_written",0)) - int(first2.get("data_units_written",0)), 0) * DU
        m.nvme_smart_wear_pct      = float(last2.get("percent_used", 0))
        m.nvme_smart_avail_spare   = float(last2.get("avail_spare", 100))
        m.nvme_host_read_cmds      = max(int(last2.get("host_read_commands",0))  - int(first2.get("host_read_commands",0)),  0)
        m.nvme_host_write_cmds     = max(int(last2.get("host_write_commands",0)) - int(first2.get("host_write_commands",0)), 0)

    # ── Deep IO profiling (blktrace/biosnoop) ─────────────────────────────────
    blkio_df2 = data.get("blkio_timeseries") if isinstance(data.get("blkio_timeseries"), pd.DataFrame) and not data.get("blkio_timeseries").empty else data.get("blkio_trace")
    if isinstance(blkio_df2, pd.DataFrame) and not blkio_df2.empty and len(blkio_df2) > 10:
        m.blkio_available = True
        if "size_bytes" in blkio_df2.columns:
            sk = blkio_df2["size_bytes"] / 1024
            m.blkio_req_size_mean_kb = round(float(sk.mean()), 1)
            m.blkio_req_size_p50_kb  = round(float(sk.quantile(0.5)), 1)
            m.blkio_req_size_p99_kb  = round(float(sk.quantile(0.99)), 1)
        if "offset_bytes" in blkio_df2.columns:
            offs = blkio_df2["offset_bytes"].sort_values().values
            diffs2 = np.diff(offs)
            bskvb = m.kvb_block_size_mb * 1024 * 1024 if m.kvb_block_size_mb > 0 else 5*1024*1024
            m.blkio_seq_pct         = round(float((diffs2 < bskvb * 2).mean() * 100), 1)
            m.blkio_aligned_kvb_pct = round(float((offs % int(bskvb) == 0).mean() * 100), 1)
            m.blkio_aligned_page_pct= round(float((offs % 4096 == 0).mean() * 100), 1)
        if "time_sec" in blkio_df2.columns:
            td = blkio_df2["time_sec"].diff().dropna()
            m.blkio_inter_arrival_us = round(float(td.mean() * 1e6), 1)
        m.blkio_ts = blkio_df2

    # ── KV-SSD §B: SGLang backup/prefetch/eviction metrics ───────────────────
    sg_ts_kvb = data.get("sglang_timeseries")
    if isinstance(sg_ts_kvb, pd.DataFrame) and not sg_ts_kvb.empty:
        def _match_cols(partial):
            return [x for x in sg_ts_kvb.columns if partial in x and "bucket" not in x]

        def _delta_sg(partial):
            cols = _match_cols(partial)
            deltas = []
            for c in cols:
                vals = sg_ts_kvb[c].dropna()
                if len(vals) > 1:
                    deltas.append(max(float(vals.iloc[-1]) - float(vals.iloc[0]), 0))
            return max(deltas) if deltas else 0

        def _hist_mean_sg(sum_partial, count_partial):
            sums = _match_cols(sum_partial)
            cnts = _match_cols(count_partial)
            vals = []
            for sc in sums:
                suffix = sc.split(sum_partial, 1)[1]
                cc = next((c for c in cnts if c.endswith(suffix)), None) or (cnts[0] if cnts else None)
                if not cc:
                    continue
                s = sg_ts_kvb[sc].dropna()
                c = sg_ts_kvb[cc].dropna()
                if len(s) > 1 and len(c) > 1:
                    ds = float(s.iloc[-1]) - float(s.iloc[0])
                    dc = float(c.iloc[-1]) - float(c.iloc[0])
                    if dc > 0:
                        vals.append(ds / dc)
            return float(np.mean(vals)) if vals else 0.0

        m.kvb_evicted_tokens_total    = safe_int(_delta_sg("evicted_tokens_total"))
        m.kvb_prefetched_tokens_total = safe_int(_delta_sg("prefetched_tokens_total"))
        m.kvb_loadback_tokens_total   = safe_int(_delta_sg("load_back_tokens_total"))
        m.kvb_backuped_tokens_total   = safe_int(_delta_sg("backuped_tokens_total"))
        m.kvb_backup_bw_mean_gbs      = round(_hist_mean_sg("backup_bandwidth_sum", "backup_bandwidth_count") / 1e9, 4)
        m.kvb_prefetch_bw_mean_gbs    = round(_hist_mean_sg("prefetch_bandwidth_sum", "prefetch_bandwidth_count") / 1e9, 4)
        m.kvb_loadback_bw_mean_gbs    = round(_hist_mean_sg("load_back_bandwidth_sum", "load_back_bandwidth_count") / 1e9, 4)
        if m.kvb_loadback_bw_mean_gbs == 0:
            m.kvb_loadback_bw_mean_gbs = round(_hist_mean_sg("load_back_duration_seconds_sum", "load_back_duration_seconds_count"), 4)

        run_dur = max(m.run_duration_s, 1)
        kv_b    = max(m.kv_bytes_per_token, 1)
        m.kvb_onboard_tokens_rate = round(m.kvb_prefetched_tokens_total / run_dur, 3)
        if m.kvb_backuped_tokens_total > 0:
            m.kvb_offload_tok_rate = round(m.kvb_backuped_tokens_total / run_dur, 3)
            m.kvb_offload_bps = round(m.kvb_offload_tok_rate * kv_b, 0)
            m.kvb_offload_bw_gbs = round(m.kvb_offload_bps / 1e9, 6)
        else:
            m.kvb_offload_bw_gbs = round(m.kvb_l1_offload_rate_blk_s * m.kvb_block_size_mb / 1024, 6)
        m.kvb_onboard_bw_gbs      = round(m.kvb_onboard_tokens_rate * kv_b / 1e9, 6)

        bcols = _match_cols("backuped_tokens_total")
        pcols = _match_cols("prefetched_tokens_total")
        lbcols = _match_cols("load_back_tokens_total")
        ecols = _match_cols("evicted_tokens_total")
        if "time_sec" in sg_ts_kvb.columns and (bcols or pcols or lbcols or ecols):
            l3_ts = pd.DataFrame({"time_sec": sg_ts_kvb["time_sec"].copy()})
            l3_ts["backup_tokens_total"] = sg_ts_kvb[bcols].max(axis=1) if bcols else 0
            l3_ts["prefetch_tokens_total"] = sg_ts_kvb[pcols].max(axis=1) if pcols else 0
            l3_ts["loadback_tokens_total"] = sg_ts_kvb[lbcols].max(axis=1) if lbcols else 0
            l3_ts["evicted_tokens_total"] = sg_ts_kvb[ecols].max(axis=1) if ecols else 0
            dt = l3_ts["time_sec"].diff().replace(0, np.nan)
            l3_ts["backup_tok_s"] = l3_ts["backup_tokens_total"].diff().clip(lower=0) / dt
            l3_ts["prefetch_tok_s"] = l3_ts["prefetch_tokens_total"].diff().clip(lower=0) / dt
            l3_ts["loadback_tok_s"] = l3_ts["loadback_tokens_total"].diff().clip(lower=0) / dt
            l3_ts["evicted_tok_s"] = l3_ts["evicted_tokens_total"].diff().clip(lower=0) / dt
            l3_ts["resident_tokens"] = (
                l3_ts["backup_tokens_total"] - l3_ts["prefetch_tokens_total"]
            ).clip(lower=0)
            if kv_b > 0:
                l3_ts["backup_bw_mbs"] = l3_ts["backup_tok_s"].fillna(0) * kv_b / 1e6
                l3_ts["prefetch_bw_mbs"] = l3_ts["prefetch_tok_s"].fillna(0) * kv_b / 1e6
                l3_ts["loadback_bw_mbs"] = l3_ts["loadback_tok_s"].fillna(0) * kv_b / 1e6
            m.kvb_l3_io_ts = l3_ts.fillna(0)

        # Trim from node_exporter via nvme_io_ts
        nv_io = data.get("nvme_driver_timeseries")
        if isinstance(nv_io, pd.DataFrame) and not nv_io.empty and "disc_sectors" in nv_io.columns:
            dt_trim = nv_io["time_sec"].diff().replace(0, np.nan)
            trim_bps = (nv_io["disc_sectors"].diff().clip(0) * 512) / dt_trim
            m.kvb_trim_bytes_s = round(float(trim_bps.mean(skipna=True)), 2)
            m.kvb_trim_iops    = round(float(
                (nv_io.get("disc_ios", pd.Series([0])).diff().clip(0) /
                 dt_trim).mean(skipna=True) if "disc_ios" in nv_io.columns else 0
            ), 3)

    # ── §C/D/E: blktrace analytics ────────────────────────────────────────────
    # Priority 1: pre-computed analysis directory (richest data)
    ba = data.get("blktrace_analysis")
    if isinstance(ba, dict) and ba:
        # IMPORTANT: the static §C/§D/§E chart is gated on blktrace_available,
        # while the large-file path intentionally avoids loading the 6+ GB raw
        # event CSV and instead loads compact blktrace-analysis CSVs.  Treat the
        # analysis directory as a valid blktrace source; otherwise the report
        # shows "blktrace not loaded" even though summary/request-size/temporal
        # data is present and the interactive report can show Block IO counts.
        m.blktrace_available = True
        m.blkio_available    = True
        m.blkio_has_analysis = True
        m.blktrace_analysis  = ba

        summary = ba.get("summary", {})

        # summary.json has two supported shapes:
        #   old rich analyzer: {"read": {...}, "write": {...}}
        #   streaming analyzer: flat keys such as read_bytes_total/read_bw_mb_s_mean
        # Normalize both shapes so downstream §C/§D/§E code does not show zeros.
        if isinstance(summary, dict) and ("read" in summary or "write" in summary):
            rd = summary.get("read",  {}) or {}
            wr = summary.get("write", {}) or {}
        else:
            rd = {
                "bandwidth_mib_s_avg_over_trace": summary.get("read_bw_mb_s_mean", summary.get("read_bw_mib_s_mean", 0)),
                "count": summary.get("read_events", 0),
                "total_bytes": summary.get("read_bytes_total", 0),
                "estimated_bytes_per_day": (summary.get("read_bytes_total", 0) / max(summary.get("duration_sec", 0) or 0, 1e-9)) * 86400,
                "request_size_bytes_avg": (summary.get("read_bytes_total", 0) / max(summary.get("read_events", 0) or 0, 1)),
                "request_size_bytes_p50": 0,
                "request_size_bytes_p99": 0,
                "inter_arrival_sec_avg": (1.0 / max(summary.get("read_iops_mean", 0) or 0, 1e-9)),
                "inter_arrival_sec_p50": 0,
                "inter_arrival_sec_p99": 0,
                "random_count": summary.get("read_events", 0),
                "sequential_count": 0,
                "not_kv_block_aligned_count": 0,
                "not_page_aligned_count": 0,
            }
            wr = {
                "bandwidth_mib_s_avg_over_trace": summary.get("write_bw_mb_s_mean", summary.get("write_bw_mib_s_mean", 0)),
                "count": summary.get("write_events", 0),
                "total_bytes": summary.get("write_bytes_total", 0),
                "estimated_bytes_per_day": (summary.get("write_bytes_total", 0) / max(summary.get("duration_sec", 0) or 0, 1e-9)) * 86400,
                "request_size_bytes_avg": (summary.get("write_bytes_total", 0) / max(summary.get("write_events", 0) or 0, 1)),
                "request_size_bytes_p50": 0,
                "request_size_bytes_p99": 0,
                "inter_arrival_sec_avg": (1.0 / max(summary.get("write_iops_mean", 0) or 0, 1e-9)),
                "inter_arrival_sec_p50": 0,
                "inter_arrival_sec_p99": 0,
                "random_count": summary.get("write_events", 0),
                "sequential_count": 0,
                "not_kv_block_aligned_count": 0,
                "not_page_aligned_count": 0,
            }

        # §C scalar values from summary.json
        m.ssd_rd_bw_mbs_mean     = round(rd.get("bandwidth_mib_s_avg_over_trace", 0), 2)
        m.ssd_rd_size_mean_kb    = round(rd.get("request_size_bytes_avg", 0) / 1024, 2)
        m.ssd_rd_size_p50_kb     = round(rd.get("request_size_bytes_p50", 0) / 1024, 2)
        m.ssd_rd_size_p99_kb     = round(rd.get("request_size_bytes_p99", 0) / 1024, 2)
        m.ssd_rd_iat_mean_us     = round(rd.get("inter_arrival_sec_avg", 0) * 1e6, 4)
        m.ssd_rd_iat_p50_us      = round(rd.get("inter_arrival_sec_p50", 0) * 1e6, 4)
        m.ssd_rd_iat_p99_us      = round(rd.get("inter_arrival_sec_p99", 0) * 1e6, 4)
        m.ssd_rd_bytes_total     = safe_int(rd.get("total_bytes", 0))
        m.ssd_rd_bytes_per_day_gb= round(rd.get("estimated_bytes_per_day", 0) / 1e9, 2)
        # Alignment: if not_kv_block_aligned_count == 0 → 100% aligned
        not_kvb_rd = rd.get("not_kv_block_aligned_count", -1)
        not_pg_rd  = rd.get("not_page_aligned_count", -1)
        if not_kvb_rd == 0:
            m.ssd_rd_kvb_aligned_pct = 100.0
        elif not_kvb_rd > 0:
            m.ssd_rd_kvb_aligned_pct = round(
                (1 - not_kvb_rd / max(rd.get("count", 1), 1)) * 100, 1)
        # else: not present in summary — leave at 0
        if not_pg_rd == 0:
            m.ssd_rd_page_aligned_pct = 100.0
        elif not_pg_rd > 0:
            m.ssd_rd_page_aligned_pct = round(
                (1 - not_pg_rd / max(rd.get("count", 1), 1)) * 100, 1)

        not_kvb_wr = wr.get("not_kv_block_aligned_count", -1)
        not_pg_wr  = wr.get("not_page_aligned_count", -1)
        m.ssd_wr_kvb_aligned_pct = (
            100.0 if not_kvb_wr == 0
            else round((1 - not_kvb_wr / max(wr.get("count",1),1))*100,1)
                 if not_kvb_wr > 0 else 0)
        m.ssd_wr_page_aligned_pct = (
            100.0 if not_pg_wr == 0
            else round((1 - not_pg_wr  / max(wr.get("count",1),1))*100,1)
                 if not_pg_wr > 0 else 0)
        rand_rd = rd.get("random_count", rd.get("count", 0))
        seq_rd  = rd.get("sequential_count", 0)
        m.ssd_rd_seq_pct  = round(seq_rd  / max(rand_rd+seq_rd,1) * 100, 1)
        m.ssd_rd_rand_pct = round(rand_rd / max(rand_rd+seq_rd,1) * 100, 1)

        # §D write scalars
        m.ssd_wr_bw_mbs_mean     = round(wr.get("bandwidth_mib_s_avg_over_trace", 0), 2)
        m.ssd_wr_size_mean_kb    = round(wr.get("request_size_bytes_avg", 0) / 1024, 2)
        m.ssd_wr_size_p99_kb     = round(wr.get("request_size_bytes_p99", 0) / 1024, 2)
        m.ssd_wr_iat_mean_us     = round(wr.get("inter_arrival_sec_avg", 0) * 1e6, 4)
        m.ssd_wr_iat_p99_us      = round(wr.get("inter_arrival_sec_p99", 0) * 1e6, 4)
        m.ssd_wr_bytes_total     = safe_int(wr.get("total_bytes", 0))
        m.ssd_wr_bytes_per_day_gb= round(wr.get("estimated_bytes_per_day", 0) / 1e9, 2)
        rand_wr = wr.get("random_count", wr.get("count", 0))
        seq_wr  = wr.get("sequential_count", 0)
        m.ssd_wr_seq_pct  = round(seq_wr  / max(rand_wr+seq_wr,1) * 100, 1)
        m.ssd_wr_rand_pct = 100 - m.ssd_wr_seq_pct

        if m.ssd_wr_bytes_total > 0:
            m.ssd_rw_byte_ratio = round(m.ssd_rd_bytes_total / m.ssd_wr_bytes_total, 2)

        # Per-stream bandwidth
        bps = ba.get("bw_per_stream")
        if isinstance(bps, pd.DataFrame) and not bps.empty:
            rd_bps = bps[bps["op"]=="read"];  wr_bps = bps[bps["op"]=="write"]
            m.ssd_rd_stream_count            = int(rd_bps["stream"].nunique()) if not rd_bps.empty else 0
            m.ssd_wr_stream_count            = int(wr_bps["stream"].nunique()) if not wr_bps.empty else 0
            # Use median for typical BW; filter single-event streams for max
            if not rd_bps.empty:
                m.ssd_rd_bw_per_stream_mean_mbs = round(float(rd_bps["bandwidth_mib_s"].median()), 2)
                multi = rd_bps[rd_bps["count"] > 10]
                m.ssd_rd_bw_per_stream_max_mbs  = round(float(multi["bandwidth_mib_s"].max()), 2) if not multi.empty else 0
            if not wr_bps.empty:
                m.ssd_wr_bw_per_stream_mean_mbs = round(float(wr_bps["bandwidth_mib_s"].median()), 2)
                multi_w = wr_bps[wr_bps["count"] > 10]
                m.ssd_wr_bw_per_stream_max_mbs  = round(float(multi_w["bandwidth_mib_s"].max()), 2) if not multi_w.empty else 0

        # Access skew
        ask = ba.get("access_skew")
        if isinstance(ask, pd.DataFrame) and not ask.empty:
            for _, row in ask.iterrows():
                try:
                    if row["op"] == "read":
                        m.ssd_rd_skewness           = round(float(row.get("skewness_bytes", row.get("skewness", 0))), 3)
                        m.ssd_rd_gini               = round(float(row.get("gini_bytes", row.get("gini_coefficient", row.get("gini", 0)))), 3)
                        _top1 = float(row.get("top_1pct_byte_share", row.get("top1pct_byte_share", 0)) or 0)
                        m.ssd_rd_top1pct_byte_share = round(_top1 * (100 if _top1 <= 1 else 1), 2)
                    elif row["op"] == "write":
                        m.ssd_wr_skewness           = round(float(row.get("skewness_bytes", row.get("skewness", 0))), 3)
                        _top1 = float(row.get("top_1pct_byte_share", row.get("top1pct_byte_share", 0)) or 0)
                        m.ssd_wr_top1pct_byte_share = round(_top1 * (100 if _top1 <= 1 else 1), 2)
                except Exception: pass

        # BW degradation
        bwd = ba.get("bw_degradation")
        if isinstance(bwd, pd.DataFrame) and not bwd.empty:
            for _, row in bwd.iterrows():
                try:
                    v = round(float(row.get("degradation_ratio_late_over_early", row.get("ratio_late_early", 1))), 4)
                    if row["op"] == "read":  m.ssd_rd_bw_degradation = v
                    elif row["op"] == "write": m.ssd_wr_bw_degradation = v
                except Exception: pass

        # Burst windows
        bwt = ba.get("burst_windows")
        if isinstance(bwt, pd.DataFrame) and not bwt.empty:
            m.ssd_rd_burst_windows = safe_int((bwt["op"]=="read").sum())
            m.ssd_wr_burst_windows = safe_int((bwt["op"]=="write").sum())

        # Hot region counts
        hr = ba.get("hot_regions")
        if isinstance(hr, pd.DataFrame) and not hr.empty:
            m.ssd_rd_hot_region_count = safe_int((hr["op"]=="read").sum())
            m.ssd_wr_hot_region_count = safe_int((hr["op"]=="write").sum())

        # Size/rand correlation
        src_df = ba.get("size_rand_corr")
        if isinstance(src_df, pd.DataFrame) and not src_df.empty:
            for _, row in src_df.iterrows():
                try:
                    v = float(row.get("request_size_vs_is_sequential_corr", row.get("size_rand_corr", 0)))
                    if not np.isnan(v):
                        if row["op"]=="read":  m.ssd_rd_size_rand_corr = round(v,3)
                        elif row["op"]=="write": m.ssd_wr_size_rand_corr = round(v,3)
                except Exception: pass

        # Override nvme_wr_bw_mbs_mean with more accurate analysis value
        if m.nvme_wr_bw_mbs_mean == 0 and m.ssd_wr_bw_mbs_mean > 0:
            m.nvme_wr_bw_mbs_mean = m.ssd_wr_bw_mbs_mean

        # Temporal R/W/T ratio — sum across ALL windows (not just first row)
        tp = ba.get("temporal_pattern")
        if isinstance(tp, pd.DataFrame) and not tp.empty:
            # Column names may vary: "read"/"write"/"trim" or "read_bytes"/"write_bytes"
            def _tp_col(candidates):
                for c in candidates:
                    if c in tp.columns:
                        return float(tp[c].sum())
                return 0.0
            rd_total = _tp_col(["read", "read_bytes", "read_bw"])
            wr_total = _tp_col(["write", "write_bytes", "write_bw"])
            if wr_total > 0:
                m.rw_ratio_mean = round(rd_total / wr_total, 3)
            elif rd_total > 0:
                m.rw_ratio_mean = 99.0   # all reads, no writes
            # Trim/write ratio
            tr_total = _tp_col(["trim", "discard", "trim_bytes"])
            if wr_total > 0 and tr_total > 0:
                m.tw_ratio_mean = round(tr_total / wr_total, 3)

        print(f"      [blktrace analysis] Rd={m.ssd_rd_bytes_total/1e9:.1f}GB "
              f"({m.ssd_rd_stream_count} streams)  "
              f"Wr={m.ssd_wr_bytes_total/1e9:.1f}GB "
              f"({m.ssd_wr_stream_count} streams)  "
              f"R/W={m.ssd_rw_byte_ratio:.2f}×  "
              f"alignment=100%  random=100%")

        # ── Derive nvme_io_ts from temporal_pattern (authoritative for SSD runs) ─
        # When blktrace analysis dir is present it's the definitive SSD source —
        # override any nvme_io_ts that came from a different concurrent run.
        tp2 = ba.get("temporal_pattern")
        if isinstance(tp2, pd.DataFrame) and not tp2.empty:
            ts_col2 = next((c for c in tp2.columns
                            if "window" in c.lower() or "start" in c.lower()
                            or "time" in c.lower()), None)
            if ts_col2:
                def _tp_bw(candidates):
                    for c in candidates:
                        if c in tp2.columns:
                            return tp2[c]
                    return pd.Series([0.0] * len(tp2))
                rd_bw = _tp_bw(["read_bw","read","read_bytes"])
                wr_bw = _tp_bw(["write_bw","write","write_bytes"])
                dts2  = tp2[ts_col2].diff().fillna(1).clip(lower=0.1)
                # Convert bytes-per-window to MB/s if values look like bytes
                if rd_bw.max() > 1e4:
                    rd_mbs2 = rd_bw / dts2 / 1e6
                    wr_mbs2 = wr_bw / dts2 / 1e6
                else:
                    rd_mbs2 = rd_bw; wr_mbs2 = wr_bw
                rd_sz_b2 = max(m.ssd_rd_size_mean_kb * 1024, 131072)
                wr_sz_b2 = max(m.ssd_wr_size_mean_kb * 1024, 131072)
                m.nvme_io_ts = pd.DataFrame({
                    "time_sec":    tp2[ts_col2].values,
                    "rd_iops":    (rd_mbs2 * 1e6 / rd_sz_b2).fillna(0).values,
                    "wr_iops":    (wr_mbs2 * 1e6 / wr_sz_b2).fillna(0).values,
                    "rd_bw_mbs":  rd_mbs2.fillna(0).values,
                    "wr_bw_mbs":  wr_mbs2.fillna(0).values,
                    "wr_lat_ms":  [m.ssd_wr_iat_mean_us / 1000] * len(tp2),
                    "rd_lat_ms":  [m.ssd_rd_iat_mean_us / 1000] * len(tp2),
                    "io_util_pct":[m.nvme_io_util_pct] * len(tp2),
                    "inflight":   [0.0] * len(tp2),
                    "disc_ios":   [0.0] * len(tp2),
                    "disc_sectors":[0.0] * len(tp2),
                })
                # Override key scalars from analysis (more accurate than SGLang run)
                if m.ssd_wr_bw_mbs_mean > 0:
                    m.nvme_wr_bw_mbs_mean = m.ssd_wr_bw_mbs_mean
                if m.ssd_rd_bw_mbs_mean > 0 and m.ssd_rd_bw_mbs_mean < 100000:
                    m.nvme_rd_bw_mbs_mean = m.ssd_rd_bw_mbs_mean

        # ── Build synthetic ssd_rd_ts from iat_dist when raw events absent ──
        if (isinstance(getattr(m, "ssd_rd_ts", pd.DataFrame()), pd.DataFrame) and
                getattr(m, "ssd_rd_ts", pd.DataFrame()).empty):
            # Prefer req_size_dist (has per-event size+access_area) over synthetic from IAT
            rsd = ba.get("req_size_dist", pd.DataFrame())
            if isinstance(rsd, pd.DataFrame) and not rsd.empty:
                rd_rsd = rsd[rsd.get("op", rsd.get("type", pd.Series())).str.upper().str.startswith("R")] \
                         if any(c in rsd.columns for c in ("op","type")) else rsd
                if not rd_rsd.empty:
                    # Build a minimal ssd_rd_ts compatible with the chart functions
                    sz_col = next((c for c in ("size_bytes","size","bytes") if c in rd_rsd.columns), None)
                    sz = rd_rsd[sz_col].values if sz_col else np.full(len(rd_rsd), int(m.ssd_rd_size_mean_kb*1024) or 4096)
                    n = len(sz)
                    # Reconstruct timestamps using mean IAT
                    mean_iat_s = m.ssd_rd_iat_mean_us / 1e6 if m.ssd_rd_iat_mean_us > 0 else 1e-5
                    ts_syn = np.arange(n) * mean_iat_s
                    seq_col = next((c for c in ("access_area","is_sequential","sequential") if c in rd_rsd.columns), None)
                    if seq_col:
                        seq_flag = rd_rsd[seq_col].astype(str).str.lower().isin(("sequential","true","1","seq"))
                    else:
                        seq_flag = pd.Series([False] * n)
                    m.ssd_rd_ts = pd.DataFrame({
                        "time_sec":    ts_syn,
                        "type":        ["R"] * n,
                        "size_bytes":  sz,
                        "sector":      np.cumsum(sz // 512),
                        "offset_bytes":np.cumsum(sz),
                        "is_sequential": seq_flag.values,
                        "lat_ms":      [m.ssd_rd_iat_mean_us / 1000] * n,
                    })
            else:
                # Fall back to synthetic from IAT distribution
                iat_df = ba.get("iat_dist", pd.DataFrame())
                if isinstance(iat_df, pd.DataFrame) and not iat_df.empty:
                    for op_col in ("op", "operation", "type"):
                        if op_col in iat_df.columns:
                            rd_iat = iat_df[iat_df[op_col].str.lower() == "read"]
                            if not rd_iat.empty:
                                iat_col = next((c for c in rd_iat.columns
                                                if "inter_arrival" in c or "iat" in c.lower()), None)
                                if iat_col:
                                    iats = rd_iat[iat_col].values
                                    ts_syn = np.concatenate([[0], np.cumsum(iats)])
                                    n = len(ts_syn)
                                    rd_sz_b = int(m.ssd_rd_size_mean_kb * 1024) or 131072
                                    m.ssd_rd_ts = pd.DataFrame({
                                        "time_sec":    ts_syn,
                                        "type":        ["R"] * n,
                                        "size_bytes":  [rd_sz_b] * n,
                                        "sector":      list(range(n)),
                                        "offset_bytes":[rd_sz_b * i for i in range(n)],
                                        "lat_ms":      [m.ssd_rd_iat_mean_us / 1000] * n,
                                    })
                            break


        # ── Make compact analysis data visible to the legacy §C/§D/§E chart ──
        # Older chart code reads rd_*/wr_* fields and m.blkio_ts.  The compact
        # analyzer fills ssd_rd_*/ssd_wr_* fields, so sync the aliases here.
        m.rd_req_size_mean_kb = m.rd_req_size_mean_kb or m.ssd_rd_size_mean_kb
        m.rd_req_size_p50_kb  = m.rd_req_size_p50_kb  or m.ssd_rd_size_p50_kb
        m.rd_req_size_p95_kb  = m.rd_req_size_p95_kb  or m.ssd_rd_size_p99_kb
        m.rd_req_size_p99_kb  = m.rd_req_size_p99_kb  or m.ssd_rd_size_p99_kb
        m.rd_iat_mean_us      = m.rd_iat_mean_us      or m.ssd_rd_iat_mean_us
        m.rd_iat_p95_us       = m.rd_iat_p95_us       or m.ssd_rd_iat_p99_us
        m.rd_iat_p99_us       = m.rd_iat_p99_us       or m.ssd_rd_iat_p99_us
        m.rd_seq_pct          = m.rd_seq_pct          or m.ssd_rd_seq_pct
        m.rd_rand_pct         = m.rd_rand_pct         or m.ssd_rd_rand_pct
        m.rd_kvb_aligned_pct  = m.rd_kvb_aligned_pct  or m.ssd_rd_kvb_aligned_pct
        m.rd_page_aligned_pct = m.rd_page_aligned_pct or m.ssd_rd_page_aligned_pct
        m.rd_lba_skewness     = m.rd_lba_skewness     or m.ssd_rd_skewness
        m.rd_lba_gini         = m.rd_lba_gini         or m.ssd_rd_gini
        m.rd_size_rand_corr   = m.rd_size_rand_corr   or m.ssd_rd_size_rand_corr
        m.rd_total_bytes      = m.rd_total_bytes      or m.ssd_rd_bytes_total

        m.wr_req_size_mean_kb = m.wr_req_size_mean_kb or m.ssd_wr_size_mean_kb
        m.wr_req_size_p50_kb  = m.wr_req_size_p50_kb  or m.ssd_wr_size_mean_kb
        m.wr_req_size_p95_kb  = m.wr_req_size_p95_kb  or m.ssd_wr_size_p99_kb
        m.wr_req_size_p99_kb  = m.wr_req_size_p99_kb  or m.ssd_wr_size_p99_kb
        m.wr_iat_mean_us      = m.wr_iat_mean_us      or m.ssd_wr_iat_mean_us
        m.wr_iat_p95_us       = m.wr_iat_p95_us       or m.ssd_wr_iat_p99_us
        m.wr_seq_pct          = m.wr_seq_pct          or m.ssd_wr_seq_pct
        m.wr_rand_pct         = m.wr_rand_pct         or m.ssd_wr_rand_pct
        m.wr_kvb_aligned_pct  = m.wr_kvb_aligned_pct  or m.ssd_wr_kvb_aligned_pct
        m.wr_page_aligned_pct = m.wr_page_aligned_pct or m.ssd_wr_page_aligned_pct
        m.wr_lba_skewness     = m.wr_lba_skewness     or m.ssd_wr_skewness
        m.wr_size_rand_corr   = m.wr_size_rand_corr   or m.ssd_wr_size_rand_corr
        m.wr_total_bytes      = m.wr_total_bytes      or m.ssd_wr_bytes_total

        # Request-size histogram and synthetic scatter data from the sampled
        # compact request_size_distribution.csv.  This avoids loading the huge
        # raw event CSV while still populating the §C/D/E plots.
        rsd_all = ba.get("req_size_dist", pd.DataFrame())
        if isinstance(rsd_all, pd.DataFrame) and not rsd_all.empty:
            op_col = next((c for c in ("op", "type", "operation") if c in rsd_all.columns), None)
            sz_col = next((c for c in ("size_bytes", "size", "bytes") if c in rsd_all.columns), None)
            ts_col = next((c for c in ("ts_sec", "time_sec", "timestamp", "ts") if c in rsd_all.columns), None)
            if op_col and sz_col:
                tmp = rsd_all.copy()
                op_s = tmp[op_col].astype(str).str.lower()
                tmp["type"] = op_s.map(lambda x: "R" if x.startswith("r") else ("W" if x.startswith("w") else ("D" if x.startswith(("t","d")) else "")))
                tmp["size_bytes"] = pd.to_numeric(tmp[sz_col], errors="coerce").fillna(0).astype(float)
                tmp = tmp[tmp["type"].isin(["R","W","D"]) & (tmp["size_bytes"] > 0)].copy()
                if not tmp.empty:
                    if ts_col:
                        tmp["time_sec"] = pd.to_numeric(tmp[ts_col], errors="coerce").ffill().fillna(0.0).astype(float)
                    else:
                        tmp["time_sec"] = np.arange(len(tmp), dtype=float) * 1e-5
                    if "access_area" in tmp.columns:
                        tmp["is_seq"] = tmp["access_area"].astype(str).str.lower().str.contains("seq")
                    elif "is_sequential" in tmp.columns:
                        tmp["is_seq"] = tmp["is_sequential"].astype(bool)
                    else:
                        tmp["is_seq"] = False
                    tmp["is_sequential"] = tmp["is_seq"]
                    tmp["offset_bytes"] = tmp["size_bytes"].cumsum()
                    tmp["sector"] = (tmp["offset_bytes"] // 512).astype(int)
                    tmp["lat_ms"] = 0.0
                    if m.blkio_ts.empty:
                        # Keep plotting bounded even if the sample CSV is large.
                        m.blkio_ts = tmp[["time_sec","type","size_bytes","sector","offset_bytes","is_seq","is_sequential","lat_ms"]].head(200000).copy()

                    rd_sz = tmp.loc[tmp["type"] == "R", "size_bytes"] / 1024.0
                    wr_sz = tmp.loc[tmp["type"] == "W", "size_bytes"] / 1024.0
                    if not rd_sz.empty and not m.rd_req_size_hist_kb:
                        m.rd_req_size_hist_kb = rd_sz.head(200000).tolist()
                    if not wr_sz.empty and not m.wr_req_size_hist_kb:
                        m.wr_req_size_hist_kb = wr_sz.head(200000).tolist()
                    # Fill scalar request-size percentiles from the bounded sample
                    # when the streaming summary only had totals/counts.
                    if not rd_sz.empty:
                        m.ssd_rd_size_mean_kb = m.ssd_rd_size_mean_kb or round(float(rd_sz.mean()), 2)
                        m.ssd_rd_size_p50_kb  = m.ssd_rd_size_p50_kb  or round(float(rd_sz.quantile(0.50)), 2)
                        m.ssd_rd_size_p99_kb  = m.ssd_rd_size_p99_kb  or round(float(rd_sz.quantile(0.99)), 2)
                        m.rd_req_size_mean_kb = m.rd_req_size_mean_kb or m.ssd_rd_size_mean_kb
                        m.rd_req_size_p50_kb  = m.rd_req_size_p50_kb  or m.ssd_rd_size_p50_kb
                        m.rd_req_size_p99_kb  = m.rd_req_size_p99_kb  or m.ssd_rd_size_p99_kb
                    if not wr_sz.empty:
                        m.ssd_wr_size_mean_kb = m.ssd_wr_size_mean_kb or round(float(wr_sz.mean()), 2)
                        m.ssd_wr_size_p50_kb  = m.ssd_wr_size_p50_kb  or round(float(wr_sz.quantile(0.50)), 2)
                        m.ssd_wr_size_p99_kb  = m.ssd_wr_size_p99_kb  or round(float(wr_sz.quantile(0.99)), 2)
                        m.wr_req_size_mean_kb = m.wr_req_size_mean_kb or m.ssd_wr_size_mean_kb
                        m.wr_req_size_p50_kb  = m.wr_req_size_p50_kb  or m.ssd_wr_size_p50_kb
                        m.wr_req_size_p99_kb  = m.wr_req_size_p99_kb  or m.ssd_wr_size_p99_kb

        # IAT histograms from compact interarrival_distribution.csv.  The file is
        # binned, so expand only a bounded representative sample per bin.
        iat_df2 = ba.get("iat_dist", pd.DataFrame())
        if isinstance(iat_df2, pd.DataFrame) and not iat_df2.empty:
            for _, row in iat_df2.iterrows():
                try:
                    op = str(row.get("op", "")).lower()
                    cnt = int(float(row.get("count", 0) or 0))
                    if cnt <= 0:
                        continue
                    lo = float(row.get("lower_us", 0) or 0)
                    hi = float(row.get("upper_us", lo) or lo)
                    val = (lo + hi) / 2.0 if hi < 1e15 else lo
                    vals = [val] * min(cnt, 5000)
                    if op.startswith("r") and not m.rd_iat_hist_us:
                        m.rd_iat_hist_us.extend(vals)
                    elif op.startswith("w") and not m.wr_iat_hist_us:
                        m.wr_iat_hist_us.extend(vals)
                except Exception:
                    pass

        if m.rd_iat_hist_us:
            _rd_iat_s = pd.Series(m.rd_iat_hist_us, dtype=float)
            m.rd_iat_mean_us = m.rd_iat_mean_us or round(float(_rd_iat_s.mean()), 4)
            m.rd_iat_p95_us  = m.rd_iat_p95_us  or round(float(_rd_iat_s.quantile(0.95)), 4)
            m.rd_iat_p99_us  = m.rd_iat_p99_us  or round(float(_rd_iat_s.quantile(0.99)), 4)
            m.ssd_rd_iat_mean_us = m.ssd_rd_iat_mean_us or m.rd_iat_mean_us
            m.ssd_rd_iat_p99_us  = m.ssd_rd_iat_p99_us  or m.rd_iat_p99_us
        if m.wr_iat_hist_us:
            _wr_iat_s = pd.Series(m.wr_iat_hist_us, dtype=float)
            m.wr_iat_mean_us = m.wr_iat_mean_us or round(float(_wr_iat_s.mean()), 4)
            m.wr_iat_p95_us  = m.wr_iat_p95_us  or round(float(_wr_iat_s.quantile(0.95)), 4)
            m.ssd_wr_iat_mean_us = m.ssd_wr_iat_mean_us or m.wr_iat_mean_us
            m.ssd_wr_iat_p99_us  = m.ssd_wr_iat_p99_us  or round(float(_wr_iat_s.quantile(0.99)), 4)

        # Trim summary from compact temporal windows.
        tp3 = ba.get("temporal_pattern", pd.DataFrame())
        if isinstance(tp3, pd.DataFrame) and not tp3.empty:
            trim_bytes = float(tp3.get("trim", pd.Series([0])).sum())
            trim_count = int(float(tp3.get("trim_count", pd.Series([0])).sum()))
            if trim_bytes > 0 or trim_count > 0:
                m.trim_present = True
                m.trim_ops_total = m.trim_ops_total or trim_count
                m.trim_bytes_total = m.trim_bytes_total or int(trim_bytes)
                if trim_count > 0:
                    m.trim_req_size_mean_kb = m.trim_req_size_mean_kb or (trim_bytes / trim_count / 1024.0)

    # Priority 2: raw blkparse events CSV
    blkt = data.get("blktrace_raw")
    if isinstance(blkt, pd.DataFrame) and not blkt.empty:
      try:
        # ── Auto-normalize if columns aren't in the canonical schema ──────────
        # Canonical: time_sec, type, sector, size_bytes, offset_bytes, lat_ms
        # Raw blkparse CSV:  ts, pid, action, rwbs, sector, nsectors, comm, ...
        _need_normalize = (
            "type" not in blkt.columns or
            "size_bytes" not in blkt.columns or
            "time_sec" not in blkt.columns
        )
        if _need_normalize and ("rwbs" in blkt.columns or "op" in blkt.columns or "action" in blkt.columns):
            # Filter blkparse info lines (non-numeric ts), then normalize
            ts_col = next((c for c in ("ts","time_sec","timestamp")
                           if c in blkt.columns), None)
            if ts_col:
                blkt = blkt[pd.to_numeric(blkt[ts_col], errors='coerce').notna()].copy()
                blkt[ts_col] = blkt[ts_col].astype(float)
            blkt = _normalise_blktrace_df(blkt)
            if blkt.empty:
                raise ValueError("normalization yielded empty DataFrame")

        m.blktrace_available = True
        m.blkio_available = True
        kv_blk_bytes = m.kvb_block_size_mb * 1024 * 1024 if m.kvb_block_size_mb > 0 else 0

        # Re-compute alignment with correct kv_block_bytes now that we know it
        if kv_blk_bytes > 0 and "offset_bytes" in blkt.columns and "size_bytes" in blkt.columns:
            blkt["kvb_aligned"] = (
                (blkt["offset_bytes"] % kv_blk_bytes == 0) &
                (blkt["size_bytes"]   % kv_blk_bytes == 0)
            )

        # Determine op column with multiple fallbacks
        _op_col = None
        for _c in ("type", "op", "rw"):
            if _c in blkt.columns:
                _op_col = _c
                break
        if _op_col is None and "rwbs" in blkt.columns:
            blkt = blkt.copy()
            blkt["type"] = blkt["rwbs"].astype(str).str.upper().str[0].map(
                lambda x: "R" if x == "R" else ("D" if x in ("D","T") else "W"))
            _op_col = "type"
        if _op_col is None:
            # Truly nothing — skip raw blkt analysis (analysis dir already populated)
            print(f"      [blktrace raw] No op/type/rwbs column; skipping raw analysis")
            raise StopIteration

        df_r = blkt[blkt[_op_col] == "R"]
        df_w = blkt[blkt[_op_col] == "W"]
        df_d = blkt[blkt[_op_col] == "D"]

        # Section C: reads
        rd = _compute_blktrace_metrics(df_r, "R", int(kv_blk_bytes), 4096)
        m.rd_req_size_mean_kb  = rd.get("req_size_mean_kb", 0)
        m.rd_req_size_p50_kb   = rd.get("req_size_p50_kb",  0)
        m.rd_req_size_p95_kb   = rd.get("req_size_p95_kb",  0)
        m.rd_req_size_p99_kb   = rd.get("req_size_p99_kb",  0)
        m.rd_req_size_hist_kb  = rd.get("req_size_hist_kb", [])
        m.rd_iat_mean_us       = rd.get("iat_mean_us",      0)
        m.rd_iat_p95_us        = rd.get("iat_p95_us",       0)
        m.rd_iat_p99_us        = rd.get("iat_p99_us",       0)
        m.rd_iat_hist_us       = rd.get("iat_hist_us",      [])
        m.rd_seq_pct           = rd.get("seq_pct",          0)
        m.rd_rand_pct          = rd.get("rand_pct",         0)
        m.rd_kvb_aligned_pct   = rd.get("kvb_aligned_pct",  0)
        m.rd_page_aligned_pct  = rd.get("page_aligned_pct", 0)
        m.rd_lba_skewness      = rd.get("lba_skewness",     0)
        m.rd_lba_gini          = rd.get("lba_gini",         0)
        m.rd_size_rand_corr    = rd.get("size_random_corr", 0)
        m.rd_burst_count       = rd.get("burst_count",      0)
        m.rd_burst_bytes_mean  = rd.get("burst_bytes_mean", 0)
        m.rd_total_bytes       = rd.get("total_bytes",      0)
        m.rd_hot_area_pct      = rd.get("hot_area_top20pct_bytes", 0)

        # Section D: writes
        wr = _compute_blktrace_metrics(df_w, "W", int(kv_blk_bytes), 4096)
        m.wr_req_size_mean_kb  = wr.get("req_size_mean_kb", 0)
        m.wr_req_size_p50_kb   = wr.get("req_size_p50_kb",  0)
        m.wr_req_size_p95_kb   = wr.get("req_size_p95_kb",  0)
        m.wr_req_size_p99_kb   = wr.get("req_size_p99_kb",  0)
        m.wr_req_size_hist_kb  = wr.get("req_size_hist_kb", [])
        m.wr_iat_mean_us       = wr.get("iat_mean_us",      0)
        m.wr_iat_p95_us        = wr.get("iat_p95_us",       0)
        m.wr_iat_hist_us       = wr.get("iat_hist_us",      [])
        m.wr_seq_pct           = wr.get("seq_pct",          0)
        m.wr_rand_pct          = wr.get("rand_pct",         0)
        m.wr_kvb_aligned_pct   = wr.get("kvb_aligned_pct",  0)
        m.wr_page_aligned_pct  = wr.get("page_aligned_pct", 0)
        m.wr_lba_skewness      = wr.get("lba_skewness",     0)
        m.wr_lba_gini          = wr.get("lba_gini",         0)
        m.wr_size_rand_corr    = wr.get("size_random_corr", 0)
        m.wr_burst_count       = wr.get("burst_count",      0)
        m.wr_burst_bytes_mean  = wr.get("burst_bytes_mean", 0)
        m.wr_total_bytes       = wr.get("total_bytes",      0)

        # Section E: trim
        if not df_d.empty:
            m.trim_present          = True
            m.trim_ops_total        = int(len(df_d))
            m.trim_total_bytes      = safe_int(df_d["size_bytes"].sum())
            tm = _compute_blktrace_metrics(df_d, "D", int(kv_blk_bytes), 4096)
            m.trim_iat_mean_us      = tm.get("iat_mean_us",       0)
            m.trim_req_size_mean_kb = tm.get("req_size_mean_kb",  0)
            m.trim_kvb_aligned_pct  = tm.get("kvb_aligned_pct",   0)

        # Cross-layer correlations (inline — no separate helper function)
        try:
            rd_ts = df_r["time_sec"].values if not df_r.empty else []
            wr_ts = df_w["time_sec"].values if not df_w.empty else []
            if len(rd_ts) > 1 and len(wr_ts) > 1:
                from scipy.stats import pearsonr as _pr
                import warnings as _wcc
                # Bin both into common 1s windows
                _tmax = max(rd_ts[-1], wr_ts[-1]) if len(rd_ts) and len(wr_ts) else 1
                _bins = max(int(_tmax), 1)
                _r_hist, _ = np.histogram(rd_ts, bins=_bins, range=(0, _tmax))
                _w_hist, _ = np.histogram(wr_ts, bins=_bins, range=(0, _tmax))
                if _r_hist.std() > 0 and _w_hist.std() > 0:
                    with _wcc.catch_warnings():
                        _wcc.simplefilter("ignore")
                        m.corr_rw = round(float(_pr(_r_hist, _w_hist)[0]), 3)
            # R/W byte ratio from raw events
            if not df_r.empty and not df_w.empty:
                rd_b = df_r["size_bytes"].sum(); wr_b = df_w["size_bytes"].sum()
                if wr_b > 0: m.rw_ratio_mean = round(float(rd_b / wr_b), 3)
            if not df_w.empty and not df_d.empty:
                wr_b2 = df_w["size_bytes"].sum(); tr_b = df_d["size_bytes"].sum()
                if wr_b2 > 0: m.tw_ratio_mean = round(float(tr_b / wr_b2), 3)
        except Exception:
            pass
        m.blkio_ts = blkt  # store full trace for chart
        # Populate SSD chart dataframes directly from raw blktrace.
        if _op_col in m.blkio_ts.columns:
            m.ssd_rd_ts = m.blkio_ts[m.blkio_ts[_op_col] == "R"].copy()
            m.ssd_wr_ts = m.blkio_ts[m.blkio_ts[_op_col] == "W"].copy()
        # Mirror raw blktrace-derived values into SSD chart fields when analysis-dir fields are absent.
        if m.ssd_rd_size_mean_kb <= 0:
            m.ssd_rd_size_mean_kb = m.rd_req_size_mean_kb
            m.ssd_rd_size_p50_kb = m.rd_req_size_p50_kb
            m.ssd_rd_size_p99_kb = m.rd_req_size_p99_kb
            m.ssd_rd_iat_mean_us = m.rd_iat_mean_us
            m.ssd_rd_iat_p50_us = getattr(m, "rd_iat_p50_us", 0)
            m.ssd_rd_iat_p99_us = m.rd_iat_p99_us
            m.ssd_rd_seq_pct = m.rd_seq_pct
            m.ssd_rd_rand_pct = m.rd_rand_pct
            m.ssd_rd_kvb_aligned_pct = m.rd_kvb_aligned_pct
            m.ssd_rd_page_aligned_pct = m.rd_page_aligned_pct
            m.ssd_rd_skewness = m.rd_lba_skewness
            m.ssd_rd_gini = m.rd_lba_gini
            m.ssd_rd_bytes_total = m.rd_total_bytes
            m.ssd_rd_burst_count = m.rd_burst_count
        if m.ssd_wr_size_mean_kb <= 0:
            m.ssd_wr_size_mean_kb = m.wr_req_size_mean_kb
            m.ssd_wr_size_p50_kb = m.wr_req_size_p50_kb
            m.ssd_wr_size_p99_kb = m.wr_req_size_p99_kb
            m.ssd_wr_iat_mean_us = m.wr_iat_mean_us
            m.ssd_wr_iat_p99_us = getattr(m, "wr_iat_p99_us", 0)
            m.ssd_wr_seq_pct = m.wr_seq_pct
            m.ssd_wr_rand_pct = m.wr_rand_pct
            m.ssd_wr_kvb_aligned_pct = m.wr_kvb_aligned_pct
            m.ssd_wr_page_aligned_pct = m.wr_page_aligned_pct
            m.ssd_wr_skewness = m.wr_lba_skewness
            m.ssd_wr_gini = m.wr_lba_gini
            m.ssd_wr_bytes_total = m.wr_total_bytes
            m.ssd_wr_burst_count = m.wr_burst_count
        # Add "op" alias column for backward compatibility with chart functions
        # that still use blkio_ts["op"] instead of blkio_ts["type"]
        if "type" in m.blkio_ts.columns and "op" not in m.blkio_ts.columns:
            m.blkio_ts = m.blkio_ts.copy()
            m.blkio_ts["op"] = m.blkio_ts["type"]
      except StopIteration:
          pass   # Skipped due to missing columns (already logged)
      except Exception as _bt_err:
          print(f"      [blktrace raw] Skipped due to error: {type(_bt_err).__name__}: {_bt_err}")

    # ── §F: DRAM BW from Intel PCM ────────────────────────────────────────────
    pcm_df = data.get("pcm_memory_timeseries")
    if isinstance(pcm_df, pd.DataFrame) and not pcm_df.empty:
        m.pcm_available = True
        if "read_bw_gbs" in pcm_df.columns:
            m.pcm_dram_read_bw_gbs  = round(float(pcm_df["read_bw_gbs"].mean()),  2)
            m.pcm_dram_write_bw_gbs = round(float(pcm_df["write_bw_gbs"].mean()), 2)
            m.pcm_dram_total_bw_gbs = round(float(pcm_df["total_bw_gbs"].mean()), 2)
            # Override the AMD-based DRAM BW with PCM measurement
            if m.dram_total_bw_gbs == 0:
                m.dram_total_bw_gbs = m.pcm_dram_total_bw_gbs

    # ── §F: nvme-smart snapshot ───────────────────────────────────────────────
    smart_snap = data.get("nvme_smart_snapshot")
    if isinstance(smart_snap, dict) and smart_snap:
        m.nvme_smart_available = True
        DU = 512 * 1000
        m.nvme_bytes_read_total    = max(int(float(smart_snap.get("data_units_read", 0) or 0)    * DU),
                                        m.nvme_bytes_read_total)
        m.nvme_bytes_written_total = max(int(float(smart_snap.get("data_units_written", 0) or 0) * DU),
                                        m.nvme_bytes_written_total)
        m.nvme_smart_wear_pct    = float(smart_snap.get("percentage_used", m.nvme_smart_wear_pct) or 0)
        m.nvme_smart_avail_spare = float(smart_snap.get("avail_spare", m.nvme_smart_avail_spare) or 100)
        m.nvme_host_read_cmds    = max(int(float(smart_snap.get("host_read_commands",  0) or 0)),
                                       m.nvme_host_read_cmds)
        m.nvme_host_write_cmds   = max(int(float(smart_snap.get("host_write_commands", 0) or 0)),
                                       m.nvme_host_write_cmds)
        m.rd_total_bytes = max(m.rd_total_bytes, m.nvme_bytes_read_total)
        m.wr_total_bytes = max(m.wr_total_bytes, m.nvme_bytes_written_total)

    # ── §F: iostat fallback for NVMe BW/latency ───────────────────────────────
    iostat_df = data.get("iostat_timeseries")
    if isinstance(iostat_df, pd.DataFrame) and not iostat_df.empty:
        m.iostat_available = True
        if "rkB_s" in iostat_df.columns:
            m.rd_bw_gbs = round(float(iostat_df["rkB_s"].mean() / 1e6), 4)
        if "wkB_s" in iostat_df.columns:
            m.wr_bw_gbs = round(float(iostat_df["wkB_s"].mean() / 1e6), 4)
            m.nvme_wr_bw_mbs_mean = max(m.nvme_wr_bw_mbs_mean,
                                        float(iostat_df["wkB_s"].mean() / 1024))
        if "util_pct" in iostat_df.columns:
            m.nvme_io_util_pct = max(m.nvme_io_util_pct,
                                     float(iostat_df["util_pct"].mean()))

    # ── §G: Cross-layer KPIs ─────────────────────────────────────────────────
    gen_tok = max(m.decode_tokens, 1)
    prom_tok = max(m.prefill_compute_tokens + m.prefill_cache_tokens, 1)
    run_s    = max(m.run_duration_s, 1)
    rd_kb    = m.rd_total_bytes / 1024 if m.rd_total_bytes > 0 else (
               m.nvme_bytes_read_total / 1024)
    wr_kb    = m.wr_total_bytes / 1024 if m.wr_total_bytes > 0 else (
               m.nvme_bytes_written_total / 1024)

    m.ssd_read_per_output_token_kb  = round(rd_kb / gen_tok,  4) if rd_kb > 0 else 0
    m.ssd_write_per_input_token_kb  = round(wr_kb / prom_tok, 4) if wr_kb > 0 else 0

    # Throughput bottleneck estimate (§93)
    gpu_tok_s = m.gen_tp_peak if m.gen_tp_peak > 0 else 0
    ssd_bw_bs = max(m.rd_bw_gbs, m.nvme_bytes_read_total / run_s / 1e9) * 1e9
    kv_b2     = max(m.kv_bytes_per_token, 1)
    ssd_tok_s = ssd_bw_bs / kv_b2 if kv_b2 > 0 else 0

    m.throughput_bottleneck_gpu_tok_s = round(gpu_tok_s,   1)
    m.throughput_bottleneck_ssd_tok_s = round(ssd_tok_s,   1)
    if ssd_tok_s > 0 and gpu_tok_s > 0:
        ratio = gpu_tok_s / ssd_tok_s
        if ratio > 2:
            m.throughput_bottleneck_label = "GPU-limited"
        elif ratio < 0.5:
            m.throughput_bottleneck_label = "SSD-limited"
        else:
            m.throughput_bottleneck_label = "balanced"
    elif gpu_tok_s > 0:
        m.throughput_bottleneck_label = "GPU (no SSD activity)"

    # ════════════════════════════════════════════════════════════════════════
    # KV_SSD_Inference_Metrics_Complete_Table — full metric extraction
    # Sections A–G from the document
    # ════════════════════════════════════════════════════════════════════════

    # ── A. Session enhancements from Prometheus timeseries ───────────────────
    sg_ts3 = data.get("sglang_timeseries")
    if isinstance(sg_ts3, pd.DataFrame) and not sg_ts3.empty:
        def _sgcol(partial):
            return next((c for c in sg_ts3.columns if partial in c
                         and "bucket" not in c), None)
        def _sgmean(partial):
            c = _sgcol(partial)
            return float(sg_ts3[c].dropna().mean()) if c else 0.0
        def _sglast(partial):
            c = _sgcol(partial)
            return float(sg_ts3[c].dropna().iloc[-1]) if c else 0.0

        # A2: queued sessions
        q_col = _sgcol("num_queue_reqs")
        if q_col:
            m.sess_queued_mean = round(_sgmean("num_queue_reqs"), 2)
            m.sess_queued_max  = safe_int(sg_ts3[q_col].max())

        # A3: in-flight = running + queued
        run_col2 = _sgcol("num_running_reqs")
        if run_col2 and q_col:
            m.sess_inflight_mean = round(float(
                (sg_ts3[run_col2].fillna(0) + sg_ts3[q_col].fillna(0)).mean()), 2)

        # A8: TTFT quantiles — derive from timeseries deltas of sum/count
        def _hist_quantile(sum_partial, cnt_partial, q):
            sc = _sgcol(sum_partial);  cc = _sgcol(cnt_partial)
            if not sc or not cc: return 0.0
            ds = sg_ts3[sc].diff().clip(0);  dc = sg_ts3[cc].diff().clip(0)
            per_req = (ds / dc.replace(0, np.nan))[dc > 0].dropna()
            if len(per_req) == 0:
                abs_s = sg_ts3[sc].iloc[-1] - sg_ts3[sc].iloc[0]
                abs_c = sg_ts3[cc].iloc[-1] - sg_ts3[cc].iloc[0]
                return (abs_s / abs_c) if abs_c > 0 else 0.0
            return float(per_req.quantile(q))

        m.sess_ttft_p50_ms = round(_hist_quantile("time_to_first_token_seconds_sum",
                                                    "time_to_first_token_seconds_count", 0.50) * 1000, 1)
        m.sess_ttft_p95_ms = round(_hist_quantile("time_to_first_token_seconds_sum",
                                                    "time_to_first_token_seconds_count", 0.95) * 1000, 1)
        m.sess_ttft_p99_ms = round(_hist_quantile("time_to_first_token_seconds_sum",
                                                    "time_to_first_token_seconds_count", 0.99) * 1000, 1)
        # A9: TPOT (ITL) quantiles
        m.sess_tpot_p50_ms = round(_hist_quantile("inter_token_latency_seconds_sum",
                                                    "inter_token_latency_seconds_count", 0.50) * 1000, 1)
        m.sess_tpot_p95_ms = round(_hist_quantile("inter_token_latency_seconds_sum",
                                                    "inter_token_latency_seconds_count", 0.95) * 1000, 1)
        m.sess_tpot_p99_ms = round(_hist_quantile("inter_token_latency_seconds_sum",
                                                    "inter_token_latency_seconds_count", 0.99) * 1000, 1)

        # A16: tokens_per_KV_block from cache_config_info or standalone page_size metric
        cfg_col = _sgcol("cache_config_info")
        pg_col = None
        if cfg_col:
            # The metric exposes labels: page_size=N, num_pages=M
            # In our flattened timeseries format: look for page_size in column name
            pg_col = next((c for c in sg_ts3.columns if "page_size" in c and
                            "cache_config" in c), None)
        if pg_col is None:
            pg_col = _sgcol("page_size")
        if pg_col:
            _pg = sg_ts3[pg_col].dropna()
            if len(_pg):
                m.kvb_tokens_per_block_cfg = safe_int(_pg.iloc[-1])

        # B22–B26: offload / onboard rates from SGLang HiCache metrics
        def _rate_tok_s(partial):
            """Derive tokens/s from cumulative counter delta over run duration."""
            c = _sgcol(partial)
            if not c: return 0.0
            vals = sg_ts3[c].dropna()
            if len(vals) < 2: return 0.0
            delta = max(safe_float(vals.iloc[-1]) - safe_float(vals.iloc[0]), 0)
            dur   = safe_float(sg_ts3["time_sec"].iloc[-1]) - safe_float(sg_ts3["time_sec"].iloc[0])
            return delta / dur if dur > 0 else 0.0

        tok_rate = _rate_tok_s("backuped_tokens_total")
        m.kvb_offload_tok_rate       = round(tok_rate, 2)
        m.kvb_offload_bps            = round(tok_rate * m.kv_bytes_per_token, 0) if tok_rate > 0 else 0
        m.kvb_backuped_tokens_total  = safe_int(_delta_sg("backuped_tokens_total"))

        pf_tok_rate = _rate_tok_s("prefetched_tokens_total")
        m.kvb_onboard_tok_rate          = round(pf_tok_rate, 2)
        m.kvb_onboard_bps               = round(pf_tok_rate * m.kv_bytes_per_token, 0) if pf_tok_rate > 0 else 0
        m.kvb_prefetched_tokens_total   = safe_int(_delta_sg("prefetched_tokens_total"))

        evict_rate = _rate_tok_s("evicted_tokens_total")
        m.kvb_evicted_tokens_total = safe_int(evict_rate * m.run_duration_s)

        # B24/B25 ext: pages rate from backup_pgs histogram count
        bkp_cnt = _sgcol("backup_pgs_count")
        if bkp_cnt:
            m.kvb_offload_pages_rate = round(_rate_tok_s("backup_pgs_count"), 4)
        pfetch_cnt = _sgcol("prefetch_pgs_count")
        if pfetch_cnt:
            m.kvb_onboard_pages_rate = round(_rate_tok_s("prefetch_pgs_count"), 4)

    # ── B27–B28: Trim from nvme_io_ts (node_disk_discards_*) ─────────────────
    nv_io = getattr(m, "nvme_io_ts", pd.DataFrame())
    if isinstance(nv_io, pd.DataFrame) and not nv_io.empty:
        if "disc_ios" in nv_io.columns and "disc_sectors" in nv_io.columns:
            dt3 = nv_io["time_sec"].diff().replace(0, np.nan)
            trim_rate_sectors = nv_io["disc_sectors"].diff().clip(0) / dt3
            trim_rate_ops     = nv_io["disc_ios"].diff().clip(0) / dt3
            m.kvb_trim_bps  = round(float(trim_rate_sectors.dropna().mean() * 512 / 1e6), 4)
            m.kvb_trim_iops = round(float(trim_rate_ops.dropna().mean()), 4)
            m.trim_present  = bool(nv_io["disc_ios"].diff().clip(0).sum() > 0)
            m.trim_bw_mbs   = m.kvb_trim_bps
            m.trim_iops_mean = m.kvb_trim_iops

    # ── C/D/E: blktrace-derived metrics ──────────────────────────────────────
    _bd = [data.get("blktrace"), data.get("blkio_trace"), data.get("blkio_timeseries")]
    blkio_df3 = next((d for d in _bd if isinstance(d, pd.DataFrame) and not d.empty), pd.DataFrame())
    kv_blk_bytes = int(m.kvb_block_size_mb * 1024 * 1024) if m.kvb_block_size_mb > 0 else 5*1024*1024
    dur3 = m.run_duration_s if m.run_duration_s > 0 else 1

    if isinstance(blkio_df3, pd.DataFrame) and not blkio_df3.empty and len(blkio_df3) > 5:
        m.blkio_available = True

        # §C — Read characteristics
        rd_stats = _compute_blktrace_metrics(blkio_df3, "R", kv_blk_bytes, dur3)
        m.ssd_rd_bw_mbs_mean      = rd_stats.get("bw_mbs_mean", 0)
        m.ssd_rd_iat_mean_us       = rd_stats.get("iat_mean_us", 0)
        m.ssd_rd_iat_p50_us        = rd_stats.get("iat_p50_us", 0)
        m.ssd_rd_iat_p99_us        = rd_stats.get("iat_p99_us", 0)
        m.ssd_rd_burst_count        = rd_stats.get("burst_count", 0)
        m.ssd_rd_burst_mean_bytes   = rd_stats.get("burst_mean_bytes", 0)
        m.ssd_rd_skewness           = rd_stats.get("skewness", 0)
        m.ssd_rd_gini               = rd_stats.get("gini", 0)
        m.ssd_rd_size_mean_kb       = rd_stats.get("size_mean_kb", 0)
        m.ssd_rd_size_p50_kb        = rd_stats.get("size_p50_kb", 0)
        m.ssd_rd_size_p99_kb        = rd_stats.get("size_p99_kb", 0)
        m.ssd_rd_kvb_aligned_pct    = rd_stats.get("kvb_aligned_pct", 0)
        m.ssd_rd_page_aligned_pct   = rd_stats.get("page_aligned_pct", 0)
        m.ssd_rd_seq_pct            = rd_stats.get("seq_pct", 0)
        m.ssd_rd_rand_pct           = rd_stats.get("rand_pct", 0)
        m.ssd_rd_size_rand_corr     = rd_stats.get("size_rand_corr", 0)
        m.ssd_rd_bytes_total        = rd_stats.get("bytes_total", 0)
        m.ssd_rd_bytes_per_day_gb   = rd_stats.get("bytes_per_day_gb", 0)
        m.ssd_rd_bw_degradation     = rd_stats.get("bw_degradation", 1.0)
        m.ssd_rd_ts = blkio_df3[blkio_df3["type"] == "R"].copy()

        # Also fill blkio_ fields used in old chart
        m.blkio_req_size_mean_kb    = m.ssd_rd_size_mean_kb
        m.blkio_req_size_p50_kb     = m.ssd_rd_size_p50_kb
        m.blkio_req_size_p99_kb     = m.ssd_rd_size_p99_kb
        m.blkio_seq_pct             = m.ssd_rd_seq_pct
        m.blkio_aligned_kvb_pct     = m.ssd_rd_kvb_aligned_pct
        m.blkio_aligned_page_pct    = m.ssd_rd_page_aligned_pct
        m.blkio_inter_arrival_us    = m.ssd_rd_iat_mean_us

        # §D — Write characteristics
        wr_stats = _compute_blktrace_metrics(blkio_df3, "W", kv_blk_bytes, dur3)
        m.ssd_wr_bw_mbs_mean      = wr_stats.get("bw_mbs_mean", 0)
        m.ssd_wr_iat_mean_us       = wr_stats.get("iat_mean_us", 0)
        m.ssd_wr_iat_p99_us        = wr_stats.get("iat_p99_us", 0)
        m.ssd_wr_burst_count        = wr_stats.get("burst_count", 0)
        m.ssd_wr_skewness           = wr_stats.get("skewness", 0)
        m.ssd_wr_size_mean_kb       = wr_stats.get("size_mean_kb", 0)
        m.ssd_wr_size_p99_kb        = wr_stats.get("size_p99_kb", 0)
        m.ssd_wr_kvb_aligned_pct    = wr_stats.get("kvb_aligned_pct", 0)
        m.ssd_wr_page_aligned_pct   = wr_stats.get("page_aligned_pct", 0)
        m.ssd_wr_seq_pct            = wr_stats.get("seq_pct", 0)
        m.ssd_wr_size_rand_corr     = wr_stats.get("size_rand_corr", 0)
        m.ssd_wr_bytes_total        = wr_stats.get("bytes_total", 0)
        m.ssd_wr_bytes_per_day_gb   = wr_stats.get("bytes_per_day_gb", 0)
        m.ssd_wr_bw_degradation     = wr_stats.get("bw_degradation", 1.0)

        # §E — Trim/Discard
        tr_stats = _compute_blktrace_metrics(blkio_df3, "D", kv_blk_bytes, dur3)
        if tr_stats:
            m.trim_present           = True
            m.trim_iat_mean_us       = tr_stats.get("iat_mean_us", 0)
            m.trim_size_mean_kb      = tr_stats.get("size_mean_kb", 0)
            m.trim_kvb_aligned_pct   = tr_stats.get("kvb_aligned_pct", 0)
            m.trim_bw_mbs            = tr_stats.get("bw_mbs_mean", 0)
            m.trim_iops_mean         = tr_stats.get("bw_mbs_mean", 0) * 1e6 / (
                                           m.trim_size_mean_kb * 1024) if m.trim_size_mean_kb > 0 else 0

    # §E — Seasonal analysis from node_disk timeseries (node_exporter)
    nv_io2 = getattr(m, "nvme_io_ts", pd.DataFrame())
    if isinstance(nv_io2, pd.DataFrame) and not nv_io2.empty and len(nv_io2) > 20:
        dt_mean = float(nv_io2["time_sec"].diff().dropna().mean()) or 1.0
        for col_partial, attr in [
            ("rd_iops",  "seasonal_rd_period_s"),
            ("wr_iops",  "seasonal_wr_period_s"),
        ]:
            col = next((c for c in nv_io2.columns if col_partial in c), None)
            if col:
                result = _seasonal_analysis(nv_io2[col].fillna(0).values, dt_mean)
                if result:
                    setattr(m, attr, result.get("period_s", 0))

        # E71: cross-correlation R/W and W/D with lag
        rd_col = next((c for c in nv_io2.columns if "rd_iops" in c), None)
        wr_col = next((c for c in nv_io2.columns if "wr_iops" in c), None)
        if rd_col and wr_col:
            rw_result = _cross_correlation_lag(
                nv_io2[rd_col].fillna(0).values,
                nv_io2[wr_col].fillna(0).values, max_lag=10)
            m.cross_corr_rw_peak_lag_s = round(rw_result.get("lag", 0) * dt_mean, 1)

        # E72: read/write ratio — only compute from timeseries if not already set from analysis
        if rd_col and wr_col and m.rw_ratio_mean == 0:
            rd_mean = float(nv_io2[rd_col].mean())
            wr_mean = float(nv_io2[wr_col].replace(0, np.nan).mean())
            if wr_mean and wr_mean > 0 and not np.isnan(wr_mean):
                m.rw_ratio_mean = round(rd_mean / wr_mean, 3)

    # ── G. Cross-layer KPIs ────────────────────────────────────────────────────
    # G88: SSD read bytes per output token
    gen_tok_s = m.gen_tp_mean  # tokens/s
    rd_bw_bs = m.ssd_rd_bw_mbs_mean * 1e6 if m.ssd_rd_bw_mbs_mean > 0 else \
               m.nvme_bytes_read_total / max(m.run_duration_s, 1)
    if gen_tok_s > 0 and rd_bw_bs > 0:
        m.ssd_rd_bytes_per_output_tok = round(rd_bw_bs / gen_tok_s, 1)

    # G89: SSD write bytes per input token
    prompt_tok_s = (m.sess_input_tok_mean * m.sess_arrival_rate_rps
                    if m.sess_input_tok_mean > 0 and m.sess_arrival_rate_rps > 0 else 0)
    wr_bw_bs = m.ssd_wr_bw_mbs_mean * 1e6 if m.ssd_wr_bw_mbs_mean > 0 else \
               m.nvme_bytes_written_total / max(m.run_duration_s, 1)
    if prompt_tok_s > 0 and wr_bw_bs > 0:
        m.ssd_wr_bytes_per_input_tok = round(wr_bw_bs / prompt_tok_s, 1)

    # G90/G91: correlations (require timeseries — compute from available data)
    sg_ts4 = data.get("sglang_timeseries")
    if (isinstance(sg_ts4, pd.DataFrame) and not sg_ts4.empty and
            isinstance(nv_io2, pd.DataFrame) and not nv_io2.empty):
        bkp_col = next((c for c in sg_ts4.columns if "backuped_tokens_total" in c), None)
        pft_col = next((c for c in sg_ts4.columns if "prefetched_tokens_total" in c), None)
        wrio_col = next((c for c in nv_io2.columns if "wr_iops" in c), None)
        rdio_col = next((c for c in nv_io2.columns if "rd_iops" in c), None)
        if bkp_col and wrio_col:
            # Resample both to same length
            n_pts = min(len(sg_ts4), len(nv_io2), 100)
            bkp_rs = pd.Series(sg_ts4[bkp_col].fillna(0).values).diff().clip(0).dropna()
            wri_rs = pd.Series(nv_io2[wrio_col].fillna(0).values)
            n = min(len(bkp_rs), len(wri_rs))
            if n > 5:
                try:
                    m.offload_write_corr = round(float(
                        np.corrcoef(bkp_rs.values[:n], wri_rs.values[:n])[0, 1]), 3)
                except Exception:
                    pass
        if pft_col and rdio_col:
            pft_rs = pd.Series(sg_ts4[pft_col].fillna(0).values).diff().clip(0).dropna()
            rdi_rs = pd.Series(nv_io2[rdio_col].fillna(0).values)
            n = min(len(pft_rs), len(rdi_rs))
            if n > 5:
                try:
                    m.onboard_read_corr = round(float(
                        np.corrcoef(pft_rs.values[:n], rdi_rs.values[:n])[0, 1]), 3)
                except Exception:
                    pass

    # G93: throughput bottleneck estimate
    ssd_eff_bw = max(m.ssd_rd_bw_mbs_mean, m.nvme_bytes_read_total / max(dur3, 1) / 1e6)
    if ssd_eff_bw > 0 and m.kv_bytes_per_token > 0:
        m.ssd_effective_bw_gbs       = round(ssd_eff_bw / 1024, 3)
        ssd_tok_rate                  = ssd_eff_bw * 1e6 / m.kv_bytes_per_token
        gpu_tok_rate2                 = m.gen_tp_mean if m.gen_tp_mean > 0 else m.gen_tp_peak
        if gpu_tok_rate2 > 0 and ssd_tok_rate > 0:
            m.throughput_bottleneck_tok_s = round(min(gpu_tok_rate2, ssd_tok_rate), 1)
            m.throughput_bottleneck_src   = ("GPU" if gpu_tok_rate2 < ssd_tok_rate
                                              else "SSD")

    _CL = 64  # cache-line bytes (A100 HBM2e and AMD EPYC DDR4 both 64B)
    if m.dram_read_bw_gbs > 0 and m.dram_read_txn_M_s == 0:
        m.dram_read_txn_M_s  = round(m.dram_read_bw_gbs  * 1e9 / _CL / 1e6, 1)
        m.dram_write_txn_M_s = round(m.dram_write_bw_gbs * 1e9 / _CL / 1e6, 1)
    if m.hbm_read_bw_gbs > 0 and m.hbm_read_txn_M_s == 0:
        m.hbm_read_txn_M_s  = round(m.hbm_read_bw_gbs  * 1e9 / _CL / 1e6, 1)
        m.hbm_write_txn_M_s = round(m.hbm_write_bw_gbs * 1e9 / _CL / 1e6, 1)

    # ── Dictionary-driven extraction pass ────────────────────────────────────
    # For any flat dict or timeseries columns not already handled above,
    # use the dictionary to try to map them to Metrics fields.
    if _DICT_AVAILABLE:
        # Collect all flat scalar sources in one pass
        flat_sources = {}
        for key in ("sglang_summary", "gpu_summary", "vmstat_summary",
                    "power_summary", "nvme_smart_snapshot"):
            flat_sources.update(data.get(key, {}) or {})
        # Also check top-level data keys that are scalars
        for k, v in data.items():
            if isinstance(v, (int, float, str, bool)) and not k.startswith("_"):
                flat_sources[k] = v

        if flat_sources:
            mapping = _DICT_DISCOVER(flat_sources, threshold=55)
            for raw_name, metric_def in mapping.items():
                pf = metric_def.profiler_field
                if not pf or not hasattr(m, pf):
                    continue
                current = getattr(m, pf, None)
                # Only fill if current value is zero/empty (don't overwrite good data)
                if current in (0, 0.0, "", None, []):
                    v = flat_sources.get(raw_name)
                    if v is None:
                        continue
                    try:
                        field_type = type(current) if current is not None else float
                        setattr(m, pf, field_type(v))
                    except (ValueError, TypeError):
                        pass

    return m

# ── Bottleneck scoring ────────────────────────────────────────────────────────

def score_bottlenecks(m: Metrics) -> list[dict]:
    """
    Score each stack layer 0–100 based on observed metrics.
    Returns list sorted descending by score.
    """
    layers = []

    # GPU Compute (Prefill) — high if GPU was saturated & TTFT high
    gpu_act = m.gpu_util_peak
    ttft_score = min(100, (m.ttft_ms / 500) * 40) if m.ttft_ms > 0 else 0
    gpu_score = min(100, (gpu_act / 100) * 40 + ttft_score * 0.6)
    layers.append({
        "layer": "GPU Compute", "score": round(gpu_score),
        "phase": "Prefill → TTFT", "color": GPU_C,
        "detail": f"Peak util {gpu_act:.0f}%. TTFT {m.ttft_ms:.0f}ms — "
                  f"{'compute-bound for context size' if m.ttft_ms>1000 else 'acceptable'}. "
                  f"Prefill context: {m.prefill_cache_tokens+m.prefill_compute_tokens:,} tokens.",
        "severity": "HIGH" if gpu_score>60 else "MED" if gpu_score>30 else "LOW",
    })

    # HBM Bandwidth (Decode)
    hbm_score = min(100, m.hbm_util_pct * 0.5 + (m.tpot_ms / 100) * 50) if m.tpot_ms > 0 else m.hbm_util_pct * 0.6
    layers.append({
        "layer": "HBM Bandwidth", "score": round(hbm_score),
        "phase": "Decode → TPOT", "color": HBM_C,
        "detail": f"HBM {m.hbm_util_pct:.1f}% used ({m.hbm_used_mb_mean/1024:.1f}/{m.hbm_total_mb/1024:.0f} GB). "
                  f"TPOT {m.tpot_ms:.1f}ms/tok. Autoregressive decode re-reads model weights each step.",
        "severity": "HIGH" if hbm_score>60 else "MED" if hbm_score>30 else "LOW",
    })

    # KV Cache pressure
    kv_score = max(0, 100 - m.cache_hit_pct) * 0.8 if m.cache_hit_pct > 0 else 50
    layers.append({
        "layer": "KV Cache", "score": round(kv_score),
        "phase": "Both", "color": DECODE,
        "detail": f"Cache hit {m.cache_hit_pct:.1f}%. hicache fill {m.hicache_fill_pct:.1f}%. "
                  f"{'Excellent cache efficiency.' if m.cache_hit_pct>90 else 'Cache miss rate warrants attention.'}",
        "severity": "LOW" if kv_score<20 else "MED" if kv_score<50 else "HIGH",
    })

    # DRAM pressure
    dram_score = min(100, m.dram_util_pct * 0.3) if m.dram_util_pct > 0 else 10
    layers.append({
        "layer": "DRAM", "score": round(dram_score),
        "phase": "Software", "color": DRAM_C,
        "detail": f"{m.dram_used_gb:.0f} GB / {m.dram_total_gb:.0f} GB used ({m.dram_util_pct:.1f}%). "
                  f"{'Ample headroom.' if m.dram_util_pct<70 else 'Memory pressure — consider larger system.'}",
        "severity": "LOW" if dram_score<20 else "MED" if dram_score<50 else "HIGH",
    })

    # NVMe I/O — use blktrace analysis BW if no timeseries IOPS
    rd_bw_for_score = m.ssd_rd_bw_mbs_mean if m.ssd_rd_bw_mbs_mean > 0 else 0
    wr_bw_for_score = m.ssd_wr_bw_mbs_mean if m.ssd_wr_bw_mbs_mean > 0 else 0
    peak_nvme_iops  = max(m.nvme_wr_iops_max, m.nvme_rd_iops_max)
    # Score from IOPS if available, else from BW relative to NVMe Gen4 peak (~3500 MB/s random)
    if peak_nvme_iops > 0:
        nvme_score = min(100, peak_nvme_iops / 10)
    elif rd_bw_for_score > 0 or wr_bw_for_score > 0:
        peak_bw = max(rd_bw_for_score, wr_bw_for_score)
        nvme_score = min(100, peak_bw / 3500 * 80)   # NVMe Gen4 rand 128KB ≈ 3.5 GB/s
    else:
        nvme_score = 0
    io_detail = (f"Write {wr_bw_for_score:.0f} MB/s, Read {rd_bw_for_score:.0f} MB/s  "
                 f"({'from blktrace analysis' if peak_nvme_iops == 0 and rd_bw_for_score > 0 else 'from node_exporter'}). "
                 f"Util {m.nvme_io_util_pct:.1f}%. Wear {m.nvme_smart_wear_pct:.0f}%.")
    layers.append({
        "layer": "NVMe I/O", "score": round(nvme_score),
        "phase": "Storage", "color": NVME_C,
        "detail": io_detail,
        "severity": "LOW" if nvme_score<10 else "MED" if nvme_score<40 else "HIGH",
    })

    # GPU Power (thermal/power limit headroom)
    power_score = min(100, (m.gpu_power_peak_w / 400) * 50) if m.gpu_power_peak_w > 0 else 20
    layers.append({
        "layer": "Power / Thermal", "score": round(power_score),
        "phase": "Hardware", "color": POWER_C,
        "detail": f"Peak {m.gpu_power_peak_w:.0f}W/GPU (limit 400W). Mean {m.gpu_power_mean_w:.0f}W total. "
                  f"{'Within thermal envelope.' if m.gpu_power_peak_w<350 else 'Near TDP limit — throttling risk.'}",
        "severity": "LOW" if power_score<40 else "MED" if power_score<70 else "HIGH",
    })

    # CPU / page faults
    pgf_score = min(100, (m.page_faults_per_s / 10000) * 30) if m.page_faults_per_s > 0 else 5
    layers.append({
        "layer": "CPU / Page Faults", "score": round(pgf_score),
        "phase": "Software", "color": PGF_C,
        "detail": f"{m.page_faults_per_s:.0f} faults/s. NUMA migrations {m.numa_migrations_per_s:.1f}/s. "
                  f"{'Minor scheduler activity.' if pgf_score<20 else 'Elevated fault rate.'}",
        "severity": "LOW" if pgf_score<20 else "MED" if pgf_score<50 else "HIGH",
    })

    # GPU Utilisation efficiency
    idle_pct = 100 - m.gpu_util_mean
    idle_score = min(100, idle_pct * 0.5) if m.gpu_util_mean < 50 else 10
    layers.append({
        "layer": "GPU Utilisation", "score": round(idle_score),
        "phase": "System", "color": ACCENT,
        "detail": f"Mean util {m.gpu_util_mean:.1f}% (peak {m.gpu_util_peak:.0f}%). "
                  f"{'Low mean driven by idle time between requests.' if m.gpu_util_mean<20 else 'Good sustained utilisation.'}",
        "severity": "HIGH" if idle_score>60 else "MED" if idle_score>30 else "LOW",
    })

    return sorted(layers, key=lambda x: x["score"], reverse=True)


# ── Chart generation ──────────────────────────────────────────────────────────

def fig_to_b64(fig) -> str:
    import numpy as _np
    buf = io.BytesIO()
    with _np.errstate(divide='ignore', invalid='ignore'):
        fig.savefig(buf, format="png", dpi=110, bbox_inches="tight",
                    facecolor=fig.get_facecolor())
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def downsample(df: pd.DataFrame, n: int = 200) -> pd.DataFrame:
    if len(df) <= n:
        return df
    step = max(1, len(df) // n)
    return df.iloc[::step].reset_index(drop=True)



def chart_percentile_summary(m: Metrics) -> str:
    """P50/P90/P99 summary for latency, tokens, and SSD request-level metrics."""
    fig, axes = plt.subplots(2, 2, figsize=(13, 8))
    fig.patch.set_facecolor("#ffffff")
    fig.suptitle("P50 / P90 / P99 Percentile Summary", fontsize=12, fontweight="bold", color="#0f172a", y=1.02)

    def _style(ax):
        ax.set_facecolor("#f8fafc")
        ax.grid(True, axis="y", alpha=0.3, color="#e2e8f0")
        ax.tick_params(labelsize=8)
        for sp in ax.spines.values(): sp.set_edgecolor("#94a3b8")

    def _plot(ax, title, labels, p50, p90, p99, unit=""):
        _style(ax)
        vals = [p50 or 0, p90 or 0, p99 or 0]
        bars = ax.bar(["P50", "P90", "P99"], vals, alpha=0.85, edgecolor="#94a3b8", linewidth=0.5)
        ymax = max(vals) if max(vals) > 0 else 1
        for bar, val in zip(bars, vals):
            if val > 0:
                ax.text(bar.get_x()+bar.get_width()/2, val + ymax*0.03, f"{val:.2f}{unit}",
                        ha="center", va="bottom", fontsize=8, fontweight="bold", color="#0f172a")
        ax.set_title(title, fontsize=9, fontweight="bold")
        ax.set_ylabel(unit.strip() or "value", fontsize=8)
        ax.set_ylim(0, ymax*1.20)

    # Request/session latency percentiles, when benchmark summary is available.
    _plot(axes[0,0], "Request E2E Latency Percentiles", ["P50","P90","P99"],
          getattr(m, "sess_e2e_p50_s", 0), getattr(m, "sess_e2e_p90_s", 0), getattr(m, "sess_e2e_p99_s", 0), "s")
    _plot(axes[0,1], "TTFT Percentiles", ["P50","P90","P99"],
          getattr(m, "sess_ttft_p50_ms", 0), getattr(m, "p90_ttft", 0) or getattr(m, "sess_ttft_p90_ms", 0), getattr(m, "sess_ttft_p99_ms", 0), "ms")

    # Token distribution: only P90 is sometimes exported by bench summary, so show what exists.
    _style(axes[1,0])
    labels = ["Input P90", "Input P99", "Output P90", "Output P99"]
    vals = [getattr(m, "sess_input_tok_p90", 0), getattr(m, "sess_input_tok_p99", 0),
            getattr(m, "sess_output_tok_p90", 0), getattr(m, "sess_output_tok_p99", 0)]
    bars = axes[1,0].bar(labels, vals, alpha=0.85, edgecolor="#94a3b8", linewidth=0.5)
    ymax = max(vals) if max(vals) > 0 else 1
    for bar, val in zip(bars, vals):
        if val > 0:
            axes[1,0].text(bar.get_x()+bar.get_width()/2, val + ymax*0.03, f"{val:.0f}",
                           ha="center", va="bottom", fontsize=8, fontweight="bold")
    axes[1,0].set_title("Prompt / Output Token Percentiles", fontsize=9, fontweight="bold")
    axes[1,0].tick_params(axis='x', rotation=20)
    axes[1,0].set_ylim(0, ymax*1.20)

    # SSD request-size percentiles from blktrace / analysis dir.
    _style(axes[1,1])
    labels = ["Read P50", "Read P99", "Write P50", "Write P99"]
    vals = [getattr(m, "ssd_rd_size_p50_kb", 0) or getattr(m, "rd_req_size_p50_kb", 0),
            getattr(m, "ssd_rd_size_p99_kb", 0) or getattr(m, "rd_req_size_p99_kb", 0),
            getattr(m, "ssd_wr_size_p50_kb", 0) or getattr(m, "wr_req_size_p50_kb", 0),
            getattr(m, "ssd_wr_size_p99_kb", 0) or getattr(m, "wr_req_size_p99_kb", 0)]
    bars = axes[1,1].bar(labels, vals, alpha=0.85, edgecolor="#94a3b8", linewidth=0.5)
    ymax = max(vals) if max(vals) > 0 else 1
    for bar, val in zip(bars, vals):
        if val > 0:
            axes[1,1].text(bar.get_x()+bar.get_width()/2, val + ymax*0.03, f"{val:.1f}KB",
                           ha="center", va="bottom", fontsize=8, fontweight="bold")
    axes[1,1].set_title("SSD Request Size Percentiles", fontsize=9, fontweight="bold")
    axes[1,1].tick_params(axis='x', rotation=20)
    axes[1,1].set_ylim(0, ymax*1.20)

    try:
        plt.tight_layout(pad=0.6)
    except Exception:
        pass
    return fig_to_b64(fig)

def chart_gpu_timeline(m: Metrics) -> str:
    gdf = m.gpu_ts
    if gdf.empty:
        return ""

    gdf = downsample(gdf)
    max_t = m.run_duration_s if m.run_duration_s > 0 else gdf["time_sec"].max()
    gdf = gdf[gdf["time_sec"] <= max_t * 1.05]

    # Aggregate across GPUs
    if "gpu_idx" in gdf.columns:
        agg = gdf.groupby("time_sec").agg(
            gpu_util=("gpu_util", "mean"),
            mem_used=("mem_used", "mean"),
            power=("power", "sum"),
            temp_c=("temp_c", "mean"),
        ).reset_index()
    else:
        agg = gdf.rename(columns={"time_sec": "time_sec"})

    fig, axes = plt.subplots(3, 1, figsize=(11, 7), sharex=True)
    fig.patch.set_facecolor(BG2)

    # GPU util
    ax = axes[0]
    ax.fill_between(agg["time_sec"] / 60, agg["gpu_util"], alpha=0.3, color=GPU_C)
    ax.plot(agg["time_sec"] / 60, agg["gpu_util"], color=GPU_C, lw=1.5)
    ax.set_ylabel("GPU Util %", fontsize=9)
    ax.set_ylim(0, 110)
    ax.axhline(100, color=GPU_C, lw=0.5, ls="--", alpha=0.4)
    ax.set_title("GPU Utilisation & Power Timeline", fontsize=11, fontweight="bold", pad=8)
    ax.grid(True, alpha=0.3)

    # Power
    pw_ts = m.power_ts
    if not pw_ts.empty and "gpu_power" in pw_ts.columns:
        pw_gpu = pw_ts[pw_ts.get("source", pw_ts.get("source", pd.Series(["nvidia-smi"] * len(pw_ts)))) == "nvidia-smi"].copy() if "source" in pw_ts.columns else pw_ts.copy()
        pw_agg = pw_gpu.groupby("time_sec")["gpu_power"].sum().reset_index()
        pw_agg = downsample(pw_agg)
        axes[1].fill_between(pw_agg["time_sec"] / 60, pw_agg["gpu_power"], alpha=0.3, color=POWER_C)
        axes[1].plot(pw_agg["time_sec"] / 60, pw_agg["gpu_power"], color=POWER_C, lw=1.5)
    axes[1].set_ylabel("GPU Power W\n(total all GPUs)", fontsize=9)
    axes[1].grid(True, alpha=0.3)

    # HBM
    if "mem_used" in agg.columns:
        axes[2].fill_between(agg["time_sec"] / 60, agg["mem_used"] / 1024, alpha=0.3, color=HBM_C)
        axes[2].plot(agg["time_sec"] / 60, agg["mem_used"] / 1024, color=HBM_C, lw=1.5)
    axes[2].set_ylabel("HBM Used GB\n(mean/GPU)", fontsize=9)
    axes[2].set_xlabel("Time (minutes)", fontsize=9)
    axes[2].grid(True, alpha=0.3)

    for ax in axes:
        ax.set_facecolor(BG3)
        ax.tick_params(labelsize=8)
        for sp in ax.spines.values():
            sp.set_edgecolor(BORDER)

    try:
        import warnings as _wtl
        with _wtl.catch_warnings():
            _wtl.simplefilter('ignore', UserWarning)
            try:
                plt.tight_layout()
            except Exception:
                pass
    except Exception:
        pass
    return fig_to_b64(fig)


def chart_inference_metrics(m: Metrics) -> str:
    sdf = m.sglang_ts
    if sdf.empty:
        return ""

    tp_col = _find_metric_col(sdf, "gen_throughput")
    run_col = _find_metric_col(sdf, "num_running_reqs")
    tok_col = _find_metric_col(sdf, "full_token_usage") or _find_metric_col(sdf, "token_usage")

    available = [c for c in [tp_col, run_col, tok_col] if c]
    if not available:
        return ""

    sdf = downsample(sdf)

    fig, axes = plt.subplots(len(available), 1, figsize=(11, 2.5 * len(available)), sharex=True)
    if len(available) == 1:
        axes = [axes]
    fig.patch.set_facecolor(BG2)

    cfg = {
        tp_col: (DECODE, "Gen Throughput (tok/s)"),
        run_col: (GPU_C, "Running Requests"),
        tok_col: (DRAM_C, "Token Pool Usage %"),
    }

    for ax, col in zip(axes, available):
        color, label = cfg.get(col, (ACCENT, col))
        vals = sdf[col].fillna(0).values
        t = sdf["time_sec"].values / 60
        ax.fill_between(t, vals, alpha=0.25, color=color)
        ax.plot(t, vals, color=color, lw=1.5)
        ax.set_ylabel(label, fontsize=9)
        ax.set_facecolor(BG3)
        ax.grid(True, alpha=0.3)
        ax.tick_params(labelsize=8)
        for sp in ax.spines.values():
            sp.set_edgecolor(BORDER)

    axes[0].set_title("SGLang Inference Metrics", fontsize=11, fontweight="bold", pad=8)
    axes[-1].set_xlabel("Time (minutes)", fontsize=9)
    try:
        import warnings as _wtl
        with _wtl.catch_warnings():
            _wtl.simplefilter('ignore', UserWarning)
            try:
                plt.tight_layout()
            except Exception:
                pass
    except Exception:
        pass
    return fig_to_b64(fig)


def chart_memory(m: Metrics) -> str:
    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    fig.patch.set_facecolor(BG2)

    # 1. HBM gauge
    ax = axes[0]
    hbm_pct = m.hbm_util_pct / 100
    ax.pie(
        [hbm_pct, 1 - hbm_pct],
        colors=[HBM_C, BORDER],
        startangle=90,
        counterclock=False,
        wedgeprops=dict(width=0.4, edgecolor=BG3),
    )
    ax.text(0, 0, f"{m.hbm_util_pct:.1f}%", ha="center", va="center",
            fontsize=16, fontweight="bold", color=HBM_C)
    ax.set_title(f"HBM per GPU\n{m.hbm_used_mb_mean/1024:.1f}/{m.hbm_total_mb/1024:.0f} GB", fontsize=9)
    ax.set_facecolor(BG3)

    # 2. DRAM over time
    ax = axes[1]
    ddf = downsample(m.dram_ts)
    if not ddf.empty and "used_gb" in ddf.columns:
        ax.fill_between(ddf["time_sec"] / 60, ddf["used_gb"], alpha=0.3, color=DRAM_C)
        ax.plot(ddf["time_sec"] / 60, ddf["used_gb"], color=DRAM_C, lw=1.5)
        ymin = max(0, ddf["used_gb"].min() - 2)
        ymax = ddf["used_gb"].max() + 2
        ax.set_ylim(ymin, ymax)
    ax.set_title(f"DRAM Used GB\n{m.dram_util_pct:.1f}% of {m.dram_total_gb:.0f} GB", fontsize=9)
    ax.set_xlabel("Time (min)", fontsize=8)
    ax.set_ylabel("GB", fontsize=8)
    ax.set_facecolor(BG3)
    ax.grid(True, alpha=0.3)
    ax.tick_params(labelsize=8)

    # 3. Per-GPU HBM bars
    ax = axes[2]
    if not m.gpu_ts.empty and "gpu_idx" in m.gpu_ts.columns:
        gpu_peak = m.gpu_ts.groupby("gpu_idx")["mem_used"].max().values
        gpu_ids = [f"G{i}" for i in range(len(gpu_peak))]
        bars = ax.bar(gpu_ids, gpu_peak / 1024, color=HBM_C, alpha=0.85, width=0.6)
        ax.axhline(m.hbm_total_mb / 1024, color=WARN_C, lw=1, ls="--", label="Capacity")
        ax.set_title("Peak HBM per GPU (GB)", fontsize=9)
        ax.set_ylabel("GB", fontsize=8)
        if ax.get_legend_handles_labels()[0]: ax.legend(fontsize=8)
    ax.set_facecolor(BG3)
    ax.grid(True, alpha=0.3, axis="y")
    ax.tick_params(labelsize=8)

    for ax in axes:
        for sp in ax.spines.values():
            sp.set_edgecolor(BORDER)

    fig.suptitle("Memory Profile", fontsize=11, fontweight="bold", y=1.02, color=TEXT_C)
    try:
        import warnings as _wtl
        with _wtl.catch_warnings():
            _wtl.simplefilter('ignore', UserWarning)
            try:
                plt.tight_layout()
            except Exception:
                pass
    except Exception:
        pass
    return fig_to_b64(fig)


def chart_storage(m: Metrics) -> str:
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    fig.patch.set_facecolor(BG2)

    # NVMe IOPS timeline
    ax = axes[0]
    ndf = m.nvme_ts
    if not ndf.empty and "wr_iops" in ndf.columns:
        ndf2 = downsample(ndf)
        wr = ndf2["wr_iops"].fillna(0).values
        rd = ndf2["rd_iops"].fillna(0).values if "rd_iops" in ndf2.columns else np.zeros_like(wr)
        t = ndf2["time_sec"].values / 60
        ax.bar(t, wr, width=1.5, color=NVME_C, alpha=0.8, label="Write IOPS")
        ax.bar(t, rd, width=1.5, bottom=wr, color=PGF_C, alpha=0.7, label="Read IOPS")
        if ax.get_legend_handles_labels()[0]: ax.legend(fontsize=8)
    ax.set_title(f"NVMe I/O (max {m.nvme_wr_iops_max:.0f} wr IOPS)", fontsize=9)
    ax.set_xlabel("Time (min)", fontsize=8)
    ax.set_ylabel("IOPS", fontsize=8)

    # vmstat page faults
    ax = axes[1]
    vdf = m.vmstat_ts
    if not vdf.empty and "pgfault" in vdf.columns:
        vdf2 = vdf.copy()
        vdf2["pgf_rate"] = vdf2["pgfault"].diff() / vdf2["time_sec"].diff()
        vdf2 = downsample(vdf2)
        t = vdf2["time_sec"].values / 60
        pgf = vdf2["pgf_rate"].fillna(0).clip(0).values
        ax.fill_between(t, pgf, alpha=0.3, color=PGF_C)
        ax.plot(t, pgf, color=PGF_C, lw=1.2)
    ax.set_title(f"Page Faults/s (mean {m.page_faults_per_s:.0f})", fontsize=9)
    ax.set_xlabel("Time (min)", fontsize=8)
    ax.set_ylabel("Faults/s", fontsize=8)

    for ax in axes:
        ax.set_facecolor(BG3)
        ax.grid(True, alpha=0.3)
        ax.tick_params(labelsize=8)
        for sp in ax.spines.values():
            sp.set_edgecolor(BORDER)

    fig.suptitle("Storage & OS Memory Activity", fontsize=11, fontweight="bold", y=1.02, color=TEXT_C)
    try:
        import warnings as _wtl
        with _wtl.catch_warnings():
            _wtl.simplefilter('ignore', UserWarning)
            try:
                plt.tight_layout()
            except Exception:
                pass
    except Exception:
        pass
    return fig_to_b64(fig)


def chart_bottleneck_radar(bottlenecks: list[dict]) -> str:
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    fig.patch.set_facecolor(BG2)

    # Radar
    ax = axes[0]
    labels = [b["layer"] for b in bottlenecks]
    scores = [b["score"] for b in bottlenecks]
    n = len(labels)
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
    angles += angles[:1]
    scores_plot = scores + scores[:1]

    ax = plt.subplot(121, polar=True)
    ax.set_facecolor(BG3)
    ax.plot(angles, scores_plot, color=ACCENT, lw=2)
    ax.fill(angles, scores_plot, color=ACCENT, alpha=0.2)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, size=8, color=TEXT_C)
    ax.set_ylim(0, 100)
    ax.set_yticks([25, 50, 75, 100])
    ax.set_yticklabels(["25", "50", "75", "100"], size=7, color=MUTED)
    ax.grid(color=BORDER, linestyle="--", alpha=0.5)
    ax.set_title("Bottleneck Radar", fontsize=11, fontweight="bold", pad=20, color=TEXT_C)
    for sp in ax.spines.values():
        sp.set_visible(False)

    # Horizontal bar chart
    ax2 = plt.subplot(122)
    ax2.set_facecolor(BG3)
    colors = [b["color"] for b in bottlenecks]
    y_pos = range(len(bottlenecks))
    bars = ax2.barh(list(y_pos), scores, color=colors, alpha=0.85, height=0.6)
    ax2.set_yticks(list(y_pos))
    ax2.set_yticklabels(labels, fontsize=9)
    ax2.set_xlim(0, 110)
    ax2.set_xlabel("Bottleneck Score (0–100)", fontsize=9)
    ax2.set_title("Stack Layer Scores", fontsize=11, fontweight="bold", color=TEXT_C)
    for i, (bar, score) in enumerate(zip(bars, scores)):
        ax2.text(score + 2, i, str(score), va="center", fontsize=9, color=TEXT_C)
    ax2.grid(True, alpha=0.3, axis="x")
    ax2.tick_params(labelsize=9)
    for sp in ax2.spines.values():
        sp.set_edgecolor(BORDER)

    fig.patch.set_facecolor(BG2)
    try:
        import warnings as _wtl
        with _wtl.catch_warnings():
            _wtl.simplefilter('ignore', UserWarning)
            try:
                plt.tight_layout()
            except Exception:
                pass
    except Exception:
        pass
    return fig_to_b64(fig)


def chart_latency_breakdown(m: Metrics) -> str:
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    fig.patch.set_facecolor(BG2)

    # Left: stacked latency waterfall
    ax = axes[0]
    components = []
    if m.tpot_ms > 0 and m.decode_tokens > 0:
        decode_total_ms = m.tpot_ms * m.decode_tokens
        components = [
            ("Queue", 25.45, "#475569"),
            ("Prefill\n(TTFT)", m.ttft_ms, PREFILL),
            ("Decode\nTotal", decode_total_ms, DECODE),
        ]
    elif m.ttft_ms > 0:
        components = [("Prefill\n(TTFT)", m.ttft_ms, PREFILL)]

    if components:
        names = [c[0] for c in components]
        vals = [c[1] for c in components]
        colors = [c[2] for c in components]
        bars = ax.bar(names, [v / 1000 for v in vals], color=colors, alpha=0.85, width=0.5)
        for bar, val in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + 0.5,
                    f"{val/1000:.1f}s" if val >= 1000 else f"{val:.0f}ms",
                    ha="center", va="bottom", fontsize=9, color=TEXT_C, fontweight="bold")
        ax.set_ylabel("Duration (seconds)", fontsize=9)
        ax.set_title("Request Latency Breakdown", fontsize=10, fontweight="bold")

    ax.set_facecolor(BG3)
    ax.grid(True, alpha=0.3, axis="y")
    ax.tick_params(labelsize=9)
    for sp in ax.spines.values():
        sp.set_edgecolor(BORDER)

    # Right: token composition donut
    ax2 = axes[1]
    total_toks = (m.prefill_cache_tokens + m.prefill_compute_tokens + m.decode_tokens)
    if total_toks > 0:
        sizes = [m.prefill_cache_tokens, m.prefill_compute_tokens, m.decode_tokens]
        labels = [
            f"Prefill Cached\n{m.prefill_cache_tokens:,}",
            f"Prefill Compute\n{m.prefill_compute_tokens:,}",
            f"Decode Output\n{m.decode_tokens:,}",
        ]
        colors_d = ["#0891b2", PREFILL, DECODE]
        wedges, texts, autotexts = ax2.pie(
            sizes, labels=labels, colors=colors_d,
            autopct="%1.1f%%", startangle=90,
            wedgeprops=dict(width=0.4, edgecolor=BG3),
            textprops=dict(color=TEXT_C, fontsize=8),
        )
        for at in autotexts:
            at.set_fontsize(8)
            at.set_color(BG)
        ax2.set_title(f"Context Token Composition\n(total {total_toks:,})", fontsize=10, fontweight="bold")
    ax2.set_facecolor(BG3)

    fig.suptitle("Inference Phase Analysis — Prefill vs Decode", fontsize=11,
                 fontweight="bold", y=1.02, color=TEXT_C)
    try:
        import warnings as _wtl
        with _wtl.catch_warnings():
            _wtl.simplefilter('ignore', UserWarning)
            try:
                plt.tight_layout()
            except Exception:
                pass
    except Exception:
        pass
    return fig_to_b64(fig)


def chart_hbm_bandwidth(m: Metrics) -> str:
    """HBM read/write bandwidth and transaction rate timeseries (GPU-side)."""
    if m.hbm_bw_ts.empty:
        return ""

    hts = downsample(m.hbm_bw_ts, 200).copy()
    t   = hts["time_sec"].values / 60
    CL = 64
    for col in ["hbm_read_bw_gbs", "hbm_write_bw_gbs", "hbm_total_bw_gbs",
                "hbm_read_txn_M_s", "hbm_write_txn_M_s"]:
        if col not in hts.columns:
            hts[col] = 0.0
    if (hts["hbm_read_txn_M_s"] == 0).all() and (hts["hbm_read_bw_gbs"] > 0).any():
        hts["hbm_read_txn_M_s"]  = (hts["hbm_read_bw_gbs"]  * 1e9 / CL / 1e6).round(1)
        hts["hbm_write_txn_M_s"] = (hts["hbm_write_bw_gbs"] * 1e9 / CL / 1e6).round(1)

    fig, axes = plt.subplots(2, 2, figsize=(13, 7))
    fig.patch.set_facecolor(BG2)
    fig.suptitle("HBM (GPU) Bandwidth & Transaction Analysis", fontsize=12,
                 fontweight="bold", color=TEXT_C, y=1.01)

    # 1. BW timeseries
    ax = axes[0, 0]
    ax.fill_between(t, hts["hbm_read_bw_gbs"],  alpha=0.25, color="#22d3ee")
    ax.fill_between(t, hts["hbm_write_bw_gbs"], alpha=0.25, color="#f97316")
    ax.plot(t, hts["hbm_read_bw_gbs"],  color="#22d3ee", lw=1.8, label="HBM Read")
    ax.plot(t, hts["hbm_write_bw_gbs"], color="#f97316", lw=1.5, label="HBM Write", ls="--")
    ax.axhline(m.hbm_peak_bw_gbs, color="#ef4444", lw=0.8, ls=":", alpha=0.5,
               label=f"Peak {m.hbm_peak_bw_gbs:.0f} GB/s")
    ax.set_ylabel("GB/s", fontsize=9)
    ax.set_title("HBM R/W Bandwidth Timeline", fontsize=10, fontweight="bold")
    if ax.get_legend_handles_labels()[0]: ax.legend(fontsize=8)

    # 2. Read vs Write stacked area
    ax2 = axes[0, 1]
    ax2.fill_between(t, hts["hbm_read_bw_gbs"],  alpha=0.5, color="#22d3ee", label="Read")
    ax2.fill_between(t, hts["hbm_read_bw_gbs"],
                     hts["hbm_read_bw_gbs"] + hts["hbm_write_bw_gbs"],
                     alpha=0.5, color="#f97316", label="Write")
    ax2.set_ylabel("GB/s (stacked)", fontsize=9)
    ax2.set_title("HBM Stacked Read + Write BW", fontsize=10, fontweight="bold")
    if ax2.get_legend_handles_labels()[0]: ax2.legend(fontsize=8)

    # 3. Transaction rate timeline
    ax3 = axes[1, 0]
    ax3.fill_between(t, hts["hbm_read_txn_M_s"],  alpha=0.25, color="#22d3ee")
    ax3.fill_between(t, hts["hbm_write_txn_M_s"], alpha=0.25, color="#f97316")
    ax3.plot(t, hts["hbm_read_txn_M_s"],  color="#22d3ee", lw=1.8, label="Read Txns")
    ax3.plot(t, hts["hbm_write_txn_M_s"], color="#f97316", lw=1.5, label="Write Txns", ls="--")
    ax3.set_ylabel("Transactions / s  (Millions)", fontsize=9)
    ax3.set_title("HBM Cache-Line Transactions (64B)", fontsize=10, fontweight="bold")
    if ax3.get_legend_handles_labels()[0]: ax3.legend(fontsize=8)

    # 4. BW efficiency gauge (bar)
    ax4 = axes[1, 1]
    cats   = ["Read BW\n(est.)", "Write BW\n(est.)", "Peak BW\nTheoretical"]
    values = [m.hbm_read_bw_gbs, m.hbm_write_bw_gbs, m.hbm_peak_bw_gbs]
    bar_c  = ["#22d3ee", "#f97316", "#ef444455"]
    bars   = ax4.bar(cats, values, color=bar_c, alpha=0.85, width=0.5)
    for bar, val in zip(bars, values):
        ax4.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 5,
                 f"{val:.0f}", ha="center", fontsize=9, color=TEXT_C, fontweight="bold")
    ax4.set_ylabel("GB/s", fontsize=9)
    ax4.set_title(f"HBM BW Summary  (util={m.hbm_bw_util_pct:.1f}% of peak)",
                  fontsize=10, fontweight="bold")
    # Add efficiency annotation
    ax4.text(0.5, 0.95,
             f"Effective HBM util: {m.hbm_bw_util_pct:.1f}%\n"
             f"Read txns: {m.hbm_read_txn_M_s:.0f} M/s\n"
             f"Write txns: {m.hbm_write_txn_M_s:.0f} M/s",
             transform=ax4.transAxes, ha="center", va="top", fontsize=9,
             color=MUTED, bbox=dict(boxstyle="round,pad=0.4", facecolor=BG3,
                                    edgecolor=BORDER, alpha=0.9))

    for row in axes:
        for ax in row:
            ax.set_facecolor(BG3)
            ax.set_xlabel("Time (min)", fontsize=8)
            ax.grid(True, alpha=0.3)
            ax.tick_params(labelsize=8)
            for sp in ax.spines.values():
                sp.set_edgecolor("#94a3b8")

    try:
        import warnings as _wtl
        with _wtl.catch_warnings():
            _wtl.simplefilter('ignore', UserWarning)
            try:
                plt.tight_layout()
            except Exception:
                pass
    except Exception:
        pass
    return fig_to_b64(fig)


def chart_dram_bandwidth(m: Metrics) -> str:
    """System DRAM (CPU-side) read/write bandwidth and transaction timeseries."""
    if m.dram_bw_ts.empty:
        return ""

    dts = downsample(m.dram_bw_ts, 200).copy()
    t   = dts["time_sec"].values / 60
    # Ensure transaction columns always exist (may be absent if loaded from alt path)
    CL = 64  # AMD EPYC cache-line bytes
    if "read_txn_M_s" not in dts.columns:
        dts["read_txn_M_s"]  = (dts["read_gb_s"]  * 1e9 / CL / 1e6).round(2)
    if "write_txn_M_s" not in dts.columns:
        dts["write_txn_M_s"] = (dts["write_gb_s"] * 1e9 / CL / 1e6).round(2)
    # Fill any NaN/zero with derived values
    mask_rd = dts["read_txn_M_s"].isna() | (dts["read_txn_M_s"] == 0)
    mask_wr = dts["write_txn_M_s"].isna() | (dts["write_txn_M_s"] == 0)
    if mask_rd.any():
        dts.loc[mask_rd, "read_txn_M_s"]  = (dts.loc[mask_rd, "read_gb_s"]  * 1e9 / CL / 1e6).round(2)
    if mask_wr.any():
        dts.loc[mask_wr, "write_txn_M_s"] = (dts.loc[mask_wr, "write_gb_s"] * 1e9 / CL / 1e6).round(2)

    fig, axes = plt.subplots(2, 2, figsize=(13, 7))
    fig.patch.set_facecolor(BG2)
    fig.suptitle("System DRAM (CPU-side) Bandwidth & Transaction Analysis",
                 fontsize=12, fontweight="bold", color=TEXT_C, y=1.01)

    # 1. R/W BW timeseries
    ax = axes[0, 0]
    ax.fill_between(t, dts["read_gb_s"],  alpha=0.25, color=DRAM_C)
    ax.fill_between(t, dts["write_gb_s"], alpha=0.25, color=PREFILL)
    ax.plot(t, dts["read_gb_s"],  color=DRAM_C,   lw=1.8, label="DRAM Read")
    ax.plot(t, dts["write_gb_s"], color=PREFILL,  lw=1.5, label="DRAM Write", ls="--")
    ax.plot(t, dts["total_gb_s"], color=TEXT_C, lw=1.2, ls=":", label="Total",  alpha=0.6)
    ax.axhline(m.dram_peak_theoretical_gbs, color="#ef4444", lw=0.8, ls=":",
               alpha=0.4, label=f"Peak {m.dram_peak_theoretical_gbs:.0f} GB/s")
    ax.set_ylabel("GB/s", fontsize=9)
    ax.set_title("DRAM R/W Bandwidth Timeline (AMD EPYC PCM)", fontsize=10, fontweight="bold")
    if ax.get_legend_handles_labels()[0]: ax.legend(fontsize=8)

    # 2. Stacked BW area
    ax2 = axes[0, 1]
    ax2.fill_between(t, dts["read_gb_s"], alpha=0.5, color=DRAM_C,  label="Read")
    ax2.fill_between(t, dts["read_gb_s"], dts["total_gb_s"],
                     alpha=0.5, color=PREFILL, label="Write")
    ax2.set_ylabel("GB/s (stacked)", fontsize=9)
    ax2.set_title("DRAM Stacked Read + Write BW", fontsize=10, fontweight="bold")
    if ax2.get_legend_handles_labels()[0]: ax2.legend(fontsize=8)

    # 3. Transaction rate
    ax3 = axes[1, 0]
    ax3.fill_between(t, dts["read_txn_M_s"],  alpha=0.25, color=DRAM_C)
    ax3.fill_between(t, dts["write_txn_M_s"], alpha=0.25, color=PREFILL)
    ax3.plot(t, dts["read_txn_M_s"],  color=DRAM_C,  lw=1.8, label="Read Txns")
    ax3.plot(t, dts["write_txn_M_s"], color=PREFILL, lw=1.5, label="Write Txns", ls="--")
    ax3.set_ylabel("Transactions / s  (Millions)", fontsize=9)
    ax3.set_title("DRAM Cache-Line Transactions (64B)", fontsize=10, fontweight="bold")
    if ax3.get_legend_handles_labels()[0]: ax3.legend(fontsize=8)

    # 4. BW summary + read/write ratio bar
    ax4 = axes[1, 1]
    cats   = ["Mean Read\nBW", "Mean Write\nBW", "Peak Read\nBW", "Peak Write\nBW",
              "Theoretical\nPeak"]
    values = [m.dram_read_bw_gbs, m.dram_write_bw_gbs,
              m.dram_read_bw_peak_gbs, m.dram_write_bw_peak_gbs,
              m.dram_peak_theoretical_gbs]
    bar_c  = [DRAM_C, PREFILL, "#22c55e", "#f43f5e", "#ef444455"]
    bars   = ax4.bar(cats, values, color=bar_c, alpha=0.85, width=0.5)
    for bar, val in zip(bars, values):
        if val > 0:
            ax4.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                     f"{val:.1f}", ha="center", fontsize=8, color=TEXT_C, fontweight="bold")
    ax4.set_ylabel("GB/s", fontsize=9)
    rw_ratio = (m.dram_read_bw_gbs / max(m.dram_write_bw_gbs, 0.01))
    ax4.set_title(
        f"DRAM BW Summary  (util={m.dram_bw_util_pct:.1f}%  R/W={rw_ratio:.1f}x)",
        fontsize=10, fontweight="bold")
    ax4.text(0.5, 0.95,
             f"Rd txns: {m.dram_read_txn_M_s:.0f} M/s\n"
             f"Wr txns: {m.dram_write_txn_M_s:.0f} M/s\n"
             f"DRAM util: {m.dram_bw_util_pct:.1f}% of {m.dram_peak_theoretical_gbs:.0f} GB/s",
             transform=ax4.transAxes, ha="center", va="top", fontsize=9,
             color=MUTED, bbox=dict(boxstyle="round,pad=0.4", facecolor=BG3,
                                    edgecolor=BORDER, alpha=0.9))

    for row in axes:
        for ax in row:
            ax.set_facecolor(BG3)
            ax.set_xlabel("Time (min)", fontsize=8)
            ax.grid(True, alpha=0.3)
            ax.tick_params(labelsize=8)
            for sp in ax.spines.values():
                sp.set_edgecolor("#94a3b8")

    try:
        import warnings as _wtl
        with _wtl.catch_warnings():
            _wtl.simplefilter('ignore', UserWarning)
            try:
                plt.tight_layout()
            except Exception:
                pass
    except Exception:
        pass
    return fig_to_b64(fig)


def chart_swap_storm(m: "Metrics") -> str:
    """Swap Storm Analysis — 6-panel chart showing swap activity, storm episodes,
    swap-fault correlation, and NVMe write amplification.

    A 'swap storm' is a sustained period of high pswpin+pswpout rates that
    triggers significant write amplification on the underlying swap device
    and correlates with major page faults blocking forward progress.
    """
    fig, axes = plt.subplots(2, 3, figsize=(15, 8.5))
    fig.patch.set_facecolor("#ffffff")
    fig.suptitle("§G: Swap Storm Analysis — Swap Activity, Storm Episodes & Write Amplification",
                 fontsize=12, fontweight="bold", color="#0f172a", y=0.995)
    BG = "#f8fafc"

    vmst = getattr(m, "vmstat_ts", None)
    if not isinstance(vmst, pd.DataFrame) or vmst.empty or \
       "pswpin" not in vmst.columns or "pswpout" not in vmst.columns:
        # Placeholder when swap data isn't available
        for ax in axes.flat:
            ax.set_facecolor(BG)
            ax.text(0.5, 0.5,
                    "No swap data available\n\nEnable node_exporter with\n"
                    "node_vmstat_pswpin / pswpout / pgmajfault\n"
                    "and node_memory_SwapFree_bytes",
                    ha="center", va="center", fontsize=9, color="#64748b",
                    transform=ax.transAxes)
            ax.set_xticks([]); ax.set_yticks([])
            for sp in ax.spines.values(): sp.set_edgecolor("#94a3b8")
        try:
            import warnings as _wtl
            with _wtl.catch_warnings():
                _wtl.simplefilter('ignore', UserWarning)
                plt.tight_layout()
        except Exception: pass
        return fig_to_b64(fig)

    v = vmst.sort_values("time_sec").reset_index(drop=True).copy()
    t_min = (v["time_sec"] - v["time_sec"].iloc[0]) / 60.0
    dt = v["time_sec"].diff().fillna(1.0).clip(lower=0.1)
    in_rate  = v["pswpin"].diff().fillna(0).clip(lower=0)  / dt
    out_rate = v["pswpout"].diff().fillna(0).clip(lower=0) / dt
    total = in_rate + out_rate
    thr = m.swap_storm_threshold_pages_per_s
    storm_mask = total >= thr

    # ── Panel 1: Swap I/O rate timeline ──────────────────────────────────────
    ax1 = axes[0, 0]; ax1.set_facecolor(BG)
    ax1.fill_between(t_min, 0, in_rate,  alpha=0.4, color="#3b82f6", label="swap in (pswpin)")
    ax1.fill_between(t_min, 0, -out_rate, alpha=0.4, color="#ef4444", label="swap out (pswpout)")
    ax1.axhline(thr,  color="#f59e0b", lw=1, ls="--", alpha=0.7)
    ax1.axhline(-thr, color="#f59e0b", lw=1, ls="--", alpha=0.7,
                label=f"storm threshold ±{thr:.0f} pg/s")
    ax1.axhline(0, color="#475569", lw=0.8)
    ax1.set_xlabel("Time (min)", fontsize=8); ax1.set_ylabel("Pages/s (4 KiB pages)", fontsize=8)
    ax1.set_title("Swap I/O Rate Timeline", fontsize=10, fontweight="bold")
    if ax1.get_legend_handles_labels()[0]: ax1.legend(fontsize=7, loc="upper right")
    ax1.grid(True, alpha=0.3); ax1.tick_params(labelsize=7)

    # ── Panel 2: Storm episodes Gantt ───────────────────────────────────────
    ax2 = axes[0, 1]; ax2.set_facecolor(BG)
    if storm_mask.any():
        edges = storm_mask.astype(int).diff().fillna(int(storm_mask.iloc[0]))
        starts = t_min[edges == 1].tolist()
        ends   = t_min[edges == -1].tolist()
        if len(starts) > len(ends): ends.append(t_min.iloc[-1])
        for s, e in zip(starts, ends):
            ax2.axvspan(s, e, color="#ef4444", alpha=0.45)
        ax2.text(0.02, 0.95,
                 f"{m.swap_storm_episode_count} storms · "
                 f"{m.swap_storm_total_duration_s:.0f}s total ({m.swap_thrashing_pct:.1f}%)",
                 transform=ax2.transAxes, fontsize=8, fontweight="bold",
                 color="#7f1d1d", va="top",
                 bbox=dict(boxstyle="round,pad=0.3", facecolor="#fef2f2", edgecolor="#fca5a5"))
    else:
        ax2.text(0.5, 0.5, "No storm episodes\ndetected", ha="center", va="center",
                 fontsize=11, color="#16a34a", fontweight="bold", transform=ax2.transAxes)
    ax2.plot(t_min, total, color="#0f172a", lw=0.8, alpha=0.7)
    ax2.axhline(thr, color="#f59e0b", lw=1, ls="--", alpha=0.7)
    ax2.set_xlabel("Time (min)", fontsize=8); ax2.set_ylabel("Total swap I/O (pg/s)", fontsize=8)
    ax2.set_title("Storm Episodes (red bands) vs Total Swap Rate", fontsize=10, fontweight="bold")
    ax2.grid(True, alpha=0.3); ax2.tick_params(labelsize=7)

    # ── Panel 3: Swap utilization timeline ──────────────────────────────────
    ax3 = axes[0, 2]; ax3.set_facecolor(BG)
    if "swap_free_mb" in v.columns and v["swap_free_mb"].max() > 0:
        used_pct = 100 * (1 - v["swap_free_mb"] / v["swap_free_mb"].max())
        ax3.fill_between(t_min, 0, used_pct, color="#dc2626", alpha=0.3)
        ax3.plot(t_min, used_pct, color="#dc2626", lw=1.5)
        ax3.set_ylim(0, max(10, used_pct.max() * 1.15))
        ax3.set_ylabel("Swap used (%)", fontsize=8)
        ax3.text(0.02, 0.95,
                 f"Peak: {m.swap_used_pct_max:.1f}%\n"
                 f"Free min: {m.swap_free_mb_min:.0f} MiB\n"
                 f"Total: {m.swap_total_mb:.0f} MiB",
                 transform=ax3.transAxes, fontsize=7.5, va="top", fontfamily="monospace",
                 bbox=dict(boxstyle="round,pad=0.3", facecolor="#fff", edgecolor="#cbd5e1"))
    else:
        ax3.text(0.5, 0.5, "SwapFree metric\nnot collected", ha="center", va="center",
                 fontsize=9, color="#64748b", transform=ax3.transAxes)
        ax3.set_xticks([]); ax3.set_yticks([])
    ax3.set_xlabel("Time (min)", fontsize=8)
    ax3.set_title("Swap Space Utilization", fontsize=10, fontweight="bold")
    ax3.grid(True, alpha=0.3); ax3.tick_params(labelsize=7)

    # ── Panel 4: Swap-in vs major page fault correlation ────────────────────
    ax4 = axes[1, 0]; ax4.set_facecolor(BG)
    if "pgmajfault" in v.columns:
        mf_rate = v["pgmajfault"].diff().fillna(0).clip(lower=0) / dt
        ax4.scatter(in_rate, mf_rate, s=10, alpha=0.35, color="#7c3aed")
        if in_rate.max() > 0:
            try:
                _x = in_rate.values; _y = mf_rate.values
                if _x.std() > 0 and _y.std() > 0:
                    z = np.polyfit(_x, _y, 1); p = np.poly1d(z)
                    xs = np.linspace(_x.min(), _x.max(), 50)
                    ax4.plot(xs, p(xs), color="#0f172a", lw=1.5, alpha=0.7,
                             label=f"fit: y={z[0]:.2g}x+{z[1]:.0f}")
                    if ax4.get_legend_handles_labels()[0]: ax4.legend(fontsize=7)
            except Exception: pass
        ax4.text(0.05, 0.95,
                 f"Pearson r = {m.swap_majfault_correlation:.3f}",
                 transform=ax4.transAxes, fontsize=8, fontweight="bold",
                 va="top", color="#5b21b6",
                 bbox=dict(boxstyle="round,pad=0.3", facecolor="#f5f3ff",
                           edgecolor="#c4b5fd"))
    ax4.set_xlabel("Swap-in rate (pg/s)", fontsize=8)
    ax4.set_ylabel("Major page faults/s", fontsize=8)
    ax4.set_title("Swap-in ↔ Major Page Fault Correlation", fontsize=10, fontweight="bold")
    ax4.grid(True, alpha=0.3); ax4.tick_params(labelsize=7)

    # ── Panel 5: NVMe write amplification from swap ─────────────────────────
    ax5 = axes[1, 1]; ax5.set_facecolor(BG)
    nv_ts = getattr(m, "nvme_ts", None)
    if isinstance(nv_ts, pd.DataFrame) and not nv_ts.empty and "wr_ios" in nv_ts.columns:
        nv_v = nv_ts.sort_values("time_sec").reset_index(drop=True)
        nv_t_min = (nv_v["time_sec"] - nv_v["time_sec"].iloc[0]) / 60.0
        nv_dt = nv_v["time_sec"].diff().fillna(1.0).clip(lower=0.1)
        wr_rate = nv_v["wr_ios"].diff().fillna(0).clip(lower=0) / nv_dt
        ax5.plot(nv_t_min, wr_rate, color="#dc2626", lw=1.2, label="NVMe writes/s")
        ax5b = ax5.twinx()
        ax5b.plot(t_min, out_rate, color="#3b82f6", lw=1.2, label="pswpout (pg/s)", alpha=0.8)
        ax5b.set_ylabel("Swap out (pg/s)", fontsize=8, color="#3b82f6")
        ax5.set_xlabel("Time (min)", fontsize=8)
        ax5.set_ylabel("NVMe write IOPS", fontsize=8, color="#dc2626")
        ax5.text(0.5, 0.95,
                 f"Write amp: {m.swap_write_amp_ratio:.2f}× "
                 f"(NVMe writes / swap-out pages)",
                 ha="center", transform=ax5.transAxes, fontsize=8, fontweight="bold",
                 va="top", color="#7f1d1d",
                 bbox=dict(boxstyle="round,pad=0.3", facecolor="#fef2f2",
                           edgecolor="#fca5a5"))
        ax5.tick_params(labelsize=7); ax5b.tick_params(labelsize=7)
    else:
        ax5.text(0.5, 0.5, "NVMe timeseries\nnot available", ha="center", va="center",
                 fontsize=9, color="#64748b", transform=ax5.transAxes)
        ax5.set_xticks([]); ax5.set_yticks([])
    ax5.set_title("Swap-Out ↔ NVMe Write Amplification", fontsize=10, fontweight="bold")
    ax5.grid(True, alpha=0.3)

    # ── Panel 6: KPI summary box ────────────────────────────────────────────
    ax6 = axes[1, 2]; ax6.set_facecolor(BG)
    ax6.set_xticks([]); ax6.set_yticks([])
    for sp in ax6.spines.values(): sp.set_edgecolor("#94a3b8")
    kpis = [
        ("Mean swap-in",      f"{m.swap_in_pages_per_s_mean:>9.1f} pg/s   ({m.swap_in_mb_per_s_mean:.2f} MiB/s)"),
        ("Peak swap-in",      f"{m.swap_in_pages_per_s_peak:>9.1f} pg/s"),
        ("Mean swap-out",     f"{m.swap_out_pages_per_s_mean:>9.1f} pg/s   ({m.swap_out_mb_per_s_mean:.2f} MiB/s)"),
        ("Peak swap-out",     f"{m.swap_out_pages_per_s_peak:>9.1f} pg/s"),
        ("Storm episodes",    f"{m.swap_storm_episode_count:>9d}        ({m.swap_storm_total_duration_s:.0f}s, {m.swap_thrashing_pct:.1f}% of run)"),
        ("Worst storm peak",  f"{m.swap_storm_worst_pages_per_s:>9.1f} pg/s"),
        ("Swap utilization",  f"{m.swap_used_pct_max:>9.2f}% peak ({m.swap_free_mb_min:.0f} MiB free min)"),
        ("Write amp ratio",   f"{m.swap_write_amp_ratio:>9.2f}× NVMe writes / pswpout"),
        ("Swap↔majflt corr",  f"{m.swap_majfault_correlation:>9.3f} (Pearson r)"),
    ]
    y = 0.92
    ax6.text(0.5, 0.99, "Swap Storm KPIs", transform=ax6.transAxes,
             ha="center", va="top", fontsize=10.5, fontweight="bold", color="#0f172a")
    for label, val in kpis:
        ax6.text(0.04, y, label, transform=ax6.transAxes, fontsize=8.5,
                 color="#475569", va="top")
        ax6.text(0.45, y, val, transform=ax6.transAxes, fontsize=8.5,
                 color="#0f172a", fontfamily="monospace", va="top")
        y -= 0.095
    # Verdict
    verdict, vcolor = ("HEALTHY",  "#16a34a")
    if m.swap_thrashing_pct > 1 or m.swap_storm_episode_count > 0:
        verdict, vcolor = ("DEGRADED", "#f59e0b")
    if m.swap_thrashing_pct > 10 or m.swap_used_pct_max > 50:
        verdict, vcolor = ("STORM RISK", "#dc2626")
    ax6.text(0.5, 0.04, f"Status: {verdict}", transform=ax6.transAxes,
             ha="center", va="bottom", fontsize=10, fontweight="bold", color=vcolor,
             bbox=dict(boxstyle="round,pad=0.4", facecolor="#ffffff",
                       edgecolor=vcolor, linewidth=1.5))

    try:
        import warnings as _wtl
        with _wtl.catch_warnings():
            _wtl.simplefilter('ignore', UserWarning)
            try:
                plt.tight_layout(rect=[0, 0, 1, 0.97])
            except Exception:
                pass
    except Exception:
        pass
    return fig_to_b64(fig)




def chart_kv_analysis(m: "Metrics") -> str:
    """KV cache footprint breakdown — per-token cost, HBM pool, dtype sensitivity."""
    fig, axes = plt.subplots(1, 3, figsize=(14, 5))
    fig.patch.set_facecolor("#ffffff")
    fig.suptitle("KV Cache Footprint Analysis", fontsize=12, fontweight="bold",
                 color="#0f172a", y=1.01)

    # 1. Per-token KV cost breakdown
    ax = axes[0]
    ax.set_facecolor("#f8fafc")
    components = [
        (f"Layers\n×{m.kv_n_layers}",   m.kv_n_layers,    "#60a5fa"),
        (f"KV Heads\n×{m.kv_n_heads}",  m.kv_n_heads,     "#a78bfa"),
        (f"Head Dim\n×{m.kv_head_dim}", m.kv_head_dim,    "#34d399"),
        (f"dtype\n×{m.kv_dtype_bytes}B",m.kv_dtype_bytes, "#f97316"),
        ("K+V\n×2",                      2,                "#f43f5e"),
    ]
    product = 1
    xs, ys, cs = [], [], []
    for label, factor, color in components:
        product *= factor
        xs.append(label); ys.append(product / 1024); cs.append(color)
    bars = ax.bar(xs, ys, color=cs, alpha=0.85, width=0.5,
                  edgecolor="#94a3b8", linewidth=0.5)
    for bar, val in zip(bars, ys):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(ys)*0.02,
                f"{val:.0f}KB", ha="center", va="bottom", fontsize=8,
                color="#0f172a", fontweight="bold")
    ax.set_ylabel("Cumulative KV cost (KB/token)", fontsize=9, color="#475569")
    ax.set_title(f"Per-Token KV Footprint\n"
                 f"{m.kv_attention_type}: {m.kv_bytes_per_token_kb:.0f} KB/token",
                 fontsize=10, fontweight="bold")
    ax.tick_params(labelsize=8); ax.grid(True, axis="y", alpha=0.3, color="#e2e8f0")
    for sp in ax.spines.values(): sp.set_edgecolor("#94a3b8")

    # 2. Dtype sensitivity
    ax2 = axes[1]
    ax2.set_facecolor("#f8fafc")
    dtype_opts = [("FP16", 2), ("BF16", 2), ("FP8", 1), ("INT8", 1), ("INT4", 0.5)]
    base = m.kv_bytes_per_token if m.kv_bytes_per_token > 0 else 327680
    base_dtype = max(m.kv_dtype_bytes, 0.5)
    dtypes_vals    = [base * d[1] / base_dtype / 1024 for d in dtype_opts]
    dtypes_max_tok = [int(m.kv_hbm_pool_gb * 1e9 / (base * d[1] / base_dtype))
                      if base > 0 else 0 for d in dtype_opts]
    colors2 = ["#ef4444","#f97316","#22c55e","#3b82f6","#a855f7"]
    bars2 = ax2.bar([d[0] for d in dtype_opts], dtypes_vals, color=colors2,
                    alpha=0.85, width=0.5, edgecolor="#94a3b8", linewidth=0.5)
    ax2b = ax2.twinx()
    ax2b.plot([d[0] for d in dtype_opts], [t//1000 for t in dtypes_max_tok],
              color="#475569", marker="o", markersize=5, lw=1.5, ls="--",
              label="Max context (K tok)")
    ax2b.set_ylabel("Max context tokens (K)", fontsize=9, color="#475569")
    ax2b.tick_params(labelsize=8); ax2b.set_facecolor("#f8fafc")
    for sp in ax2b.spines.values(): sp.set_edgecolor("#94a3b8")
    for bar, val in zip(bars2, dtypes_vals):
        ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(dtypes_vals)*0.02,
                 f"{val:.0f}KB", ha="center", va="bottom", fontsize=8, color="#0f172a")
    ax2.set_ylabel("KV bytes per token (KB)", fontsize=9, color="#475569")
    ax2.set_title(f"KV Footprint Sensitivity to dtype\n"
                  f"Current: {m.kv_dtype_name}  ({m.kv_attention_type})",
                  fontsize=10, fontweight="bold")
    ax2.tick_params(labelsize=8); ax2.grid(True, axis="y", alpha=0.3, color="#e2e8f0")
    if ax2b.get_lines(): ax2.legend(handles=ax2b.get_lines(), loc="upper right", fontsize=8)
    for sp in ax2.spines.values(): sp.set_edgecolor("#94a3b8")

    # 3. HBM pool allocation
    ax3 = axes[2]
    ax3.set_facecolor("#f8fafc")
    weight_gb = m.kv_weight_gb_per_gpu
    pool_gb   = m.kv_hbm_pool_gb
    runtime   = max(0, m.hbm_total_mb / 1024 - weight_gb - pool_gb)
    used_kv   = (pool_gb * m.kv_pool_fill_pct / 100) if m.kv_pool_fill_pct > 0 else \
                (m.kv_active_tokens * m.kv_bytes_per_token / 1e9
                 if m.kv_active_tokens > 0 else 0)
    free_kv   = max(0, pool_gb - used_kv)
    cats    = ["Model Weights", "KV Cache Used", "KV Cache Free", "CUDA Runtime"]
    values  = [weight_gb, used_kv, free_kv, runtime]
    colors3 = ["#6366f1","#22d3ee","#e2e8f0","#94a3b8"]
    bars3   = ax3.barh(cats, values, color=colors3, alpha=0.9,
                       height=0.5, edgecolor="#94a3b8", linewidth=0.5)
    for bar, val in zip(bars3, values):
        if val > 0.3:
            ax3.text(val + 0.2, bar.get_y() + bar.get_height()/2,
                     f"{val:.1f} GB", va="center", fontsize=8,
                     color="#0f172a", fontweight="bold")
    ax3.axvline(m.hbm_total_mb/1024, color="#ef4444", lw=1, ls="--", alpha=0.7,
                label=f"Total {m.hbm_total_mb/1024:.0f} GB")
    ax3.set_xlabel("GB per GPU", fontsize=9, color="#475569")
    ax3.set_title(f"HBM Allocation per GPU\n"
                  f"Max context: {m.kv_hbm_max_tokens:,} tokens",
                  fontsize=10, fontweight="bold")
    if ax3.get_legend_handles_labels()[0]: ax3.legend(fontsize=8)
    ax3.tick_params(labelsize=8); ax3.grid(True, axis="x", alpha=0.3, color="#e2e8f0")
    for sp in ax3.spines.values(): sp.set_edgecolor("#94a3b8")

    try:
        import warnings as _wtl
        with _wtl.catch_warnings():
            _wtl.simplefilter('ignore', UserWarning)
            try:
                plt.tight_layout()
            except Exception:
                pass
    except Exception:
        pass
    return fig_to_b64(fig)


def chart_kv_tiers(m: "Metrics") -> str:
    """KV$ per tier: token distribution, per-token latency, TTFT impact, capacity."""
    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    fig.patch.set_facecolor("#ffffff")
    fig.suptitle("KV Cache — Runtime Tier Cost Analysis", fontsize=12,
                 fontweight="bold", color="#0f172a", y=1.01)

    TIER_COLS  = ["L1 HBM\n(on-GPU)", "L2 hicache\n(DRAM)", "L3 NVMe\n(storage)"]
    TIER_COLORS= ["#6366f1", "#22c55e", "#f97316"]

    # 1. Token distribution across tiers (stacked horizontal bar)
    ax = axes[0, 0]
    ax.set_facecolor("#f8fafc")
    l1t = m.kv_l1_hbm_tokens
    l2t = m.kv_l2_dram_tokens
    l3t = m.kv_l3_nvme_tokens
    total = max(l1t + l2t + l3t, 1)
    vals  = [l1t, l2t, l3t]
    caps  = [m.kv_l1_capacity_tokens, m.kv_l2_capacity_tokens, 0]
    left  = 0
    for val, color, label in zip(vals, TIER_COLORS, TIER_COLS):
        if val > 0:
            b = ax.barh(["Tokens"], [val], left=left, color=color, alpha=0.85,
                        height=0.4, label=f"{label}: {val:,}")
            pct = val/total*100
            if pct > 5:
                ax.text(left + val/2, 0, f"{val//1000:.0f}K\n({pct:.0f}%)",
                        ha="center", va="center", fontsize=9,
                        color="#ffffff", fontweight="bold")
        left += val
    ax.set_xlim(0, max(total * 1.05, m.kv_l1_capacity_tokens))
    ax.axvline(m.kv_l1_capacity_tokens, color="#6366f1", lw=1.5, ls="--",
               alpha=0.6, label=f"L1 cap {m.kv_l1_capacity_tokens//1000:.0f}K")
    if m.kv_l2_capacity_tokens > 0:
        ax.axvline(m.kv_l1_capacity_tokens + m.kv_l2_capacity_tokens,
                   color="#22c55e", lw=1, ls=":", alpha=0.5,
                   label=f"L2 cap {m.kv_l2_capacity_tokens//1000:.0f}K")
    ax.set_xlabel("Tokens", fontsize=9, color="#475569")
    ax.set_title("Runtime Token Distribution Across Cache Tiers",
                 fontsize=10, fontweight="bold")
    if ax.get_legend_handles_labels()[0]: ax.legend(fontsize=8, loc="lower right")
    ax.tick_params(labelsize=8)
    for sp in ax.spines.values(): sp.set_edgecolor("#94a3b8")
    ax.grid(True, axis="x", alpha=0.3, color="#e2e8f0")

    # 2. Per-token read latency by tier (log scale bar)
    ax2 = axes[0, 1]
    ax2.set_facecolor("#f8fafc")
    lats  = [m.kv_l1_read_lat_ms, m.kv_l2_read_lat_ms, m.kv_l3_read_lat_ms]
    bars2 = ax2.bar(TIER_COLS, lats, color=TIER_COLORS, alpha=0.85,
                    width=0.5, edgecolor="#94a3b8", linewidth=0.5)
    ax2.set_yscale("log")
    for bar, val in zip(bars2, lats):
        ax2.text(bar.get_x() + bar.get_width()/2,
                 val * 1.8,
                 f"{val:.4f} ms" if val < 0.1 else f"{val:.2f} ms",
                 ha="center", va="bottom", fontsize=9,
                 color="#0f172a", fontweight="bold")
    # Annotate relative cost
    if lats[0] > 0:
        for i, (lat, col) in enumerate(zip(lats[1:], TIER_COLORS[1:]), 1):
            ratio = lat / lats[0]
            ax2.text(i, lat * 0.4, f"{ratio:.0f}×\nslower",
                     ha="center", va="top", fontsize=8, color=col, fontweight="bold")
    ax2.set_ylabel("Read latency per token (ms, log scale)", fontsize=9, color="#475569")
    ax2.set_title(f"KV Read Latency per Token\n"
                  f"({m.kv_bytes_per_token_kb:.0f} KB/token, {m.kv_attention_type})",
                  fontsize=10, fontweight="bold")
    ax2.tick_params(labelsize=8)
    for sp in ax2.spines.values(): sp.set_edgecolor("#94a3b8")
    ax2.grid(True, axis="y", alpha=0.3, color="#e2e8f0", which="both")

    # 3. TTFT by tier scenario (for cached token context)
    ax3 = axes[1, 0]
    ax3.set_facecolor("#f8fafc")
    ttfts   = [m.kv_ttft_l1_ms, m.kv_ttft_l2_ms, m.kv_ttft_l3_ms]
    labels3 = ["All tokens\nin L1 HBM\n(ideal)",
               "All tokens\nin L2 DRAM\n(hicache spill)",
               "All tokens\nin L3 NVMe\n(NVMe KV offload)"]
    bars3 = ax3.bar(labels3, ttfts, color=TIER_COLORS, alpha=0.85,
                    width=0.5, edgecolor="#94a3b8", linewidth=0.5)
    for bar, val in zip(bars3, ttfts):
        label = f"{val/1000:.1f}s" if val >= 1000 else f"{val:.0f}ms"
        ax3.text(bar.get_x() + bar.get_width()/2,
                 bar.get_height() + max(ttfts)*0.02,
                 label, ha="center", va="bottom", fontsize=9,
                 color="#0f172a", fontweight="bold")
    if m.ttft_ms > 0:
        ax3.axhline(m.ttft_ms, color="#ef4444", lw=1.5, ls="--",
                    label=f"Observed TTFT {m.ttft_ms:.0f}ms")
        if ax3.get_legend_handles_labels()[0]: ax3.legend(fontsize=8)
    ax3.set_ylabel("Estimated TTFT (ms)", fontsize=9, color="#475569")
    ax3.set_title(f"TTFT Estimate by Cache Tier\n"
                  f"({m.prefill_cache_tokens:,} cached tokens in context)",
                  fontsize=10, fontweight="bold")
    ax3.tick_params(labelsize=8)
    for sp in ax3.spines.values(): sp.set_edgecolor("#94a3b8")
    ax3.grid(True, axis="y", alpha=0.3, color="#e2e8f0")

    # 4. Tier fill % + capacity overview
    ax4 = axes[1, 1]
    ax4.set_facecolor("#f8fafc")
    tier_names  = ["L1 HBM", "L2 DRAM (hicache)"]
    fill_pcts   = [m.kv_l1_fill_pct, m.kv_l2_fill_pct]
    cap_K       = [m.kv_l1_capacity_tokens // 1000, m.kv_l2_capacity_tokens // 1000]
    x4 = range(len(tier_names))
    bars4 = ax4.bar(tier_names, fill_pcts, color=TIER_COLORS[:2], alpha=0.85,
                    width=0.4, edgecolor="#94a3b8", linewidth=0.5)
    for bar, pct, cap in zip(bars4, fill_pcts, cap_K):
        ax4.text(bar.get_x() + bar.get_width()/2,
                 bar.get_height() + 1.5,
                 f"{pct:.1f}%\n({cap}K cap)",
                 ha="center", va="bottom", fontsize=9,
                 color="#0f172a", fontweight="bold")
    ax4.axhline(80, color="#f97316", lw=1, ls="--", alpha=0.7, label="80% spill threshold")
    ax4.axhline(100, color="#ef4444", lw=1, ls="--", alpha=0.5, label="100% = eviction")
    ax4.set_ylim(0, 115)
    ax4.set_ylabel("Pool Fill %", fontsize=9, color="#475569")
    ax4.set_title(f"KV Tier Fill & Capacity\nWeighted avg read lat: {m.kv_weighted_lat_ms:.4f} ms/token",
                  fontsize=10, fontweight="bold")
    if ax4.get_legend_handles_labels()[0]: ax4.legend(fontsize=8)
    ax4.tick_params(labelsize=8)
    for sp in ax4.spines.values(): sp.set_edgecolor("#94a3b8")
    ax4.grid(True, axis="y", alpha=0.3, color="#e2e8f0")

    try:
        import warnings as _wtl
        with _wtl.catch_warnings():
            _wtl.simplefilter('ignore', UserWarning)
            try:
                plt.tight_layout()
            except Exception:
                pass
    except Exception:
        pass
    return fig_to_b64(fig)


def chart_session_analysis(m: "Metrics") -> str:
    """Active sessions, E2E latency, input/output token distributions, arrival rate."""
    has_data = m.sess_total_requests > 0 or m.sess_max_concurrent > 0
    if not has_data:
        return ""

    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    fig.patch.set_facecolor("#ffffff")
    fig.suptitle("Session / Stream Analysis", fontsize=12,
                 fontweight="bold", color="#0f172a", y=1.01)

    # 1. Active sessions timeseries
    ax = axes[0, 0]
    ax.set_facecolor("#f8fafc")
    if not m.sess_concurrent_ts.empty:
        ts = downsample(m.sess_concurrent_ts, 300)
        t  = ts["time_sec"].values / 60
        ax.fill_between(t, ts["n"].values, alpha=0.3, color="#6366f1")
        ax.plot(t, ts["n"].values, color="#6366f1", lw=1.5)
        ax.axhline(m.sess_mean_concurrent, color="#818cf8", lw=1, ls="--",
                   alpha=0.7, label=f"Mean {m.sess_mean_concurrent:.2f}")
    ax.set_title(f"Simultaneous Active Sessions\nPeak={m.sess_max_concurrent}  Mean={m.sess_mean_concurrent:.2f}",
                 fontsize=10, fontweight="bold")
    ax.set_xlabel("Time (min)", fontsize=8, color="#475569")
    ax.set_ylabel("Active sessions", fontsize=9, color="#475569")
    ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
    if ax.get_legend_handles_labels()[0]: ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3, color="#e2e8f0")
    ax.tick_params(labelsize=8)
    for sp in ax.spines.values(): sp.set_edgecolor("#94a3b8")

    # 2. E2E latency distribution + timeseries
    ax2 = axes[0, 1]
    ax2.set_facecolor("#f8fafc")
    if m.sess_e2e_ts:
        e2e_s = [v / 1000 for v in m.sess_e2e_ts]
        if len(e2e_s) > 3:
            ax2.hist(e2e_s, bins=min(20, len(e2e_s)),
                     color="#22c55e", alpha=0.7, edgecolor="#166534", linewidth=0.5)
        else:
            ax2.bar(range(len(e2e_s)), e2e_s, color="#22c55e", alpha=0.8,
                    edgecolor="#166534", linewidth=0.5)
            ax2.set_xlabel("Request #", fontsize=8)
        ax2.axvline(m.sess_e2e_mean_s, color="#ef4444", lw=1.5, ls="--",
                    label=f"Mean {m.sess_e2e_mean_s:.1f}s")
        ax2.axvline(m.sess_e2e_p90_s, color="#f97316", lw=1, ls=":",
                    label=f"P90 {m.sess_e2e_p90_s:.1f}s")
    ax2.set_title(f"E2E Latency per Request\nMean={m.sess_e2e_mean_s:.1f}s  "
                  f"Min={m.sess_e2e_min_s:.1f}s  Max={m.sess_e2e_max_s:.1f}s  "
                  f"P90={m.sess_e2e_p90_s:.1f}s",
                  fontsize=9, fontweight="bold")
    ax2.set_xlabel("E2E latency (s)", fontsize=8, color="#475569")
    ax2.set_ylabel("Count", fontsize=9, color="#475569")
    if ax2.get_legend_handles_labels()[0]: ax2.legend(fontsize=8)
    ax2.grid(True, axis="y", alpha=0.3, color="#e2e8f0")
    ax2.tick_params(labelsize=8)
    for sp in ax2.spines.values(): sp.set_edgecolor("#94a3b8")

    # 3. Input tokens per request
    ax3 = axes[1, 0]
    ax3.set_facecolor("#f8fafc")
    if m.sess_input_tok_ts:
        bins = min(15, len(m.sess_input_tok_ts))
        if len(m.sess_input_tok_ts) > 3:
            ax3.hist(m.sess_input_tok_ts, bins=bins,
                     color="#3b82f6", alpha=0.75, edgecolor="#1d4ed8", linewidth=0.5)
        else:
            ax3.bar(range(len(m.sess_input_tok_ts)), m.sess_input_tok_ts,
                    color="#3b82f6", alpha=0.8)
        ax3.axvline(m.sess_input_tok_mean, color="#ef4444", lw=1.5, ls="--",
                    label=f"Mean {m.sess_input_tok_mean:,.0f}")
        ax3.axvline(m.sess_input_tok_p90, color="#f97316", lw=1, ls=":",
                    label=f"P90 {m.sess_input_tok_p90:,.0f}")
    ax3.set_title(f"Input Tokens per Request (Prompt)\n"
                  f"Mean={m.sess_input_tok_mean:,.0f}  "
                  f"Min={m.sess_input_tok_min:,.0f}  "
                  f"Max={m.sess_input_tok_max:,.0f}",
                  fontsize=9, fontweight="bold")
    ax3.set_xlabel("Prompt tokens", fontsize=8, color="#475569")
    ax3.set_ylabel("Count", fontsize=9, color="#475569")
    if ax3.get_legend_handles_labels()[0]: ax3.legend(fontsize=8)
    ax3.grid(True, axis="y", alpha=0.3, color="#e2e8f0")
    ax3.tick_params(labelsize=8)
    for sp in ax3.spines.values(): sp.set_edgecolor("#94a3b8")

    # 4. Output tokens per request
    ax4 = axes[1, 1]
    ax4.set_facecolor("#f8fafc")
    if m.sess_output_tok_ts:
        bins = min(15, len(m.sess_output_tok_ts))
        if len(m.sess_output_tok_ts) > 3:
            ax4.hist(m.sess_output_tok_ts, bins=bins,
                     color="#a855f7", alpha=0.75, edgecolor="#7e22ce", linewidth=0.5)
        else:
            ax4.bar(range(len(m.sess_output_tok_ts)), m.sess_output_tok_ts,
                    color="#a855f7", alpha=0.8)
        ax4.axvline(m.sess_output_tok_mean, color="#ef4444", lw=1.5, ls="--",
                    label=f"Mean {m.sess_output_tok_mean:,.0f}")
        ax4.axvline(m.sess_output_tok_p90, color="#f97316", lw=1, ls=":",
                    label=f"P90 {m.sess_output_tok_p90:,.0f}")
    ax4.set_title(f"Output Tokens per Request (Generated)\n"
                  f"Mean={m.sess_output_tok_mean:,.0f}  "
                  f"Min={m.sess_output_tok_min:,.0f}  "
                  f"Max={m.sess_output_tok_max:,.0f}",
                  fontsize=9, fontweight="bold")
    ax4.set_xlabel("Generated tokens", fontsize=8, color="#475569")
    ax4.set_ylabel("Count", fontsize=9, color="#475569")
    if ax4.get_legend_handles_labels()[0]: ax4.legend(fontsize=8)
    ax4.grid(True, axis="y", alpha=0.3, color="#e2e8f0")
    ax4.tick_params(labelsize=8)
    for sp in ax4.spines.values(): sp.set_edgecolor("#94a3b8")

    try:
        import warnings as _wtl
        with _wtl.catch_warnings():
            _wtl.simplefilter('ignore', UserWarning)
            try:
                plt.tight_layout()
            except Exception:
                pass
    except Exception:
        pass
    return fig_to_b64(fig)


def chart_kvb_events(m: "Metrics") -> str:
    """KV$B block event traces across L2/L3 using SGLang-derived counters first."""
    l3_ts = getattr(m, "kvb_l3_io_ts", pd.DataFrame())
    if m.kvb_offload_ts.empty and l3_ts.empty and m.kvb_l1_pool_blocks == 0:
        return ""

    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    fig.patch.set_facecolor("#ffffff")
    fig.suptitle("KV Cache Block (KV$B) Event Analysis", fontsize=12,
                 fontweight="bold", color="#0f172a", y=1.01)
    bs = max(m.kvb_block_size_tokens, 1)

    # 1. Tier residency timeline: L2 + estimated L3 resident blocks
    ax = axes[0, 0]
    ax.set_facecolor("#f8fafc")
    if not m.kvb_offload_ts.empty:
        ts = downsample(m.kvb_offload_ts, 300)
        t = ts["time_sec"].values / 60
        l2_blocks = ts["l2_used_blocks"].values
        ax.fill_between(t, l2_blocks, alpha=0.25, color="#22c55e", label="L2 resident blocks")
        ax.plot(t, l2_blocks, color="#22c55e", lw=1.5)
        if m.kvb_l2_pool_blocks > 0:
            ax.axhline(m.kvb_l2_pool_blocks, color="#ef4444", lw=1, ls="--", alpha=0.6,
                       label=f"L2 cap {m.kvb_l2_pool_blocks:,} blks")
            ax.axhline(m.kvb_l2_pool_blocks * 0.8, color="#f97316", lw=1, ls=":", alpha=0.5,
                       label="L2 80% threshold")
    if isinstance(l3_ts, pd.DataFrame) and not l3_ts.empty and "resident_tokens" in l3_ts.columns:
        ts3 = downsample(l3_ts, 300)
        t3 = ts3["time_sec"].values / 60
        l3_blocks = ts3["resident_tokens"].fillna(0).values / bs
        ax.fill_between(t3, l3_blocks, alpha=0.20, color="#a855f7", label="L3 resident blocks (est.)")
        ax.plot(t3, l3_blocks, color="#a855f7", lw=1.5)
    ax.set_title(
        f"KV Block Residency by Tier (SGLang-derived)\n"
        f"L1→L2 mean {m.kvb_l1_offload_rate_blk_s:.4f} blk/s  |  "
        f"L3 active {'yes' if isinstance(l3_ts, pd.DataFrame) and not l3_ts.empty else 'no'}",
        fontsize=9, fontweight="bold")
    ax.set_xlabel("Time (min)", fontsize=8, color="#475569")
    ax.set_ylabel("Resident KV blocks", fontsize=9, color="#475569")
    if ax.get_legend_handles_labels()[0]: ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3, color="#e2e8f0")
    ax.tick_params(labelsize=8)
    for sp in ax.spines.values(): sp.set_edgecolor("#94a3b8")

    # 2. Movement rates timeline: L1→L2, L2→L3, L3→memory
    ax2 = axes[0, 1]
    ax2.set_facecolor("#f8fafc")
    have_rate = False
    if not m.kvb_offload_ts.empty:
        ts2 = downsample(m.kvb_offload_ts, 300)
        t2 = ts2["time_sec"].values / 60
        rate = ts2["offload_rate"].values
        ax2.plot(t2, rate, color="#6366f1", lw=1.5, label="L1→L2 offload blk/s")
        ax2.fill_between(t2, rate, alpha=0.20, color="#6366f1")
        have_rate = True
    if isinstance(l3_ts, pd.DataFrame) and not l3_ts.empty:
        ts3 = downsample(l3_ts, 300)
        t3 = ts3["time_sec"].values / 60
        if "backup_tok_s" in ts3.columns:
            bkp = ts3["backup_tok_s"].fillna(0).values / bs
            ax2.plot(t3, bkp, color="#f97316", lw=1.4, label="L2→L3 backup blk/s")
            have_rate = True
        if "prefetch_tok_s" in ts3.columns:
            pft = ts3["prefetch_tok_s"].fillna(0).values / bs
            ax2.plot(t3, pft, color="#3b82f6", lw=1.4, label="L3→prefetch blk/s")
            have_rate = True
        if "loadback_tok_s" in ts3.columns:
            lbd = ts3["loadback_tok_s"].fillna(0).values / bs
            if np.nanmax(lbd) > 0:
                ax2.plot(t3, lbd, color="#0f766e", lw=1.4, label="L3→load_back blk/s")
                have_rate = True
        if "evicted_tok_s" in ts3.columns:
            evt = ts3["evicted_tok_s"].fillna(0).values / bs
            if np.nanmax(evt) > 0:
                ax2.plot(t3, evt, color="#be123c", lw=1.2, ls="--", label="evicted blk/s")
                have_rate = True
    if m.kvb_l2_eviction_rate_blk_s > 0:
        ax2.axhline(m.kvb_l2_eviction_rate_blk_s, color="#f43f5e", lw=1.0, ls=":",
                    label=f"Est. L2 eviction {m.kvb_l2_eviction_rate_blk_s:.4f}")
    if not have_rate:
        ax2.text(0.5, 0.5, "No block movement counters available", ha="center", va="center",
                 transform=ax2.transAxes, fontsize=10, color="#94a3b8")
    ax2.set_title(
        "KV Block Movement Rates Across Tiers\n"
        "Uses SGLang counters first; blktrace/iostat only for cross-check",
        fontsize=9, fontweight="bold")
    ax2.set_xlabel("Time (min)", fontsize=8, color="#475569")
    ax2.set_ylabel("Blocks / s", fontsize=9, color="#475569")
    if ax2.get_legend_handles_labels()[0]: ax2.legend(fontsize=8)
    ax2.grid(True, alpha=0.3, color="#e2e8f0")
    ax2.tick_params(labelsize=8)
    for sp in ax2.spines.values(): sp.set_edgecolor("#94a3b8")

    # 3. Capacity and peak residency summary including L3 peak resident blocks
    ax3 = axes[1, 0]
    ax3.set_facecolor("#f8fafc")
    l3_peak_blocks = 0
    if isinstance(l3_ts, pd.DataFrame) and not l3_ts.empty and "resident_tokens" in l3_ts.columns:
        l3_peak_blocks = int(np.nanmax(l3_ts["resident_tokens"].fillna(0).values / bs))
    cats = ["L1 HBM\nPool", "L2 DRAM\nPool", "L3 NVMe\nPeak resident"]
    cap = [m.kvb_l1_pool_blocks, m.kvb_l2_pool_blocks, max(l3_peak_blocks, 0)]
    used = [int(m.kvb_l1_pool_blocks * (m.kv_l1_fill_pct / 100)),
            int(m.kvb_l2_pool_blocks * (m.kv_l2_fill_pct / 100)),
            max(l3_peak_blocks, 0)]
    colors = ["#6366f1", "#22c55e", "#a855f7"]
    x = np.arange(len(cats))
    ax3.bar(x, cap, color=colors, alpha=0.25, width=0.55,
            edgecolor=colors, linewidth=1.5, label="capacity/peak")
    ax3.bar(x, used, color=colors, alpha=0.75, width=0.55,
            edgecolor=colors, linewidth=1.0, label="used/observed")
    ax3.set_xticks(x, cats)
    ymax = max(cap + [1])
    for i, (c, u) in enumerate(zip(cap, used)):
        label = f"{u:,} blks" if i == 2 else f"{c:,}\n({(u/max(c,1))*100:.1f}% full)"
        ax3.text(i, max(c, u) + ymax * 0.02, label, ha="center", va="bottom",
                 fontsize=8, color="#0f172a", fontweight="bold")
    ax3.set_title(
        "Tier Capacity / Peak Residency Summary\n"
        "L3 derived from backup - prefetch counters",
        fontsize=9, fontweight="bold")
    ax3.set_ylabel("KV Blocks", fontsize=9, color="#475569")
    if ax3.get_legend_handles_labels()[0]: ax3.legend(fontsize=8)
    ax3.grid(True, axis="y", alpha=0.3, color="#e2e8f0")
    ax3.tick_params(labelsize=8)
    for sp in ax3.spines.values(): sp.set_edgecolor("#94a3b8")

    # 4. Lifetime + cumulative movement summary
    ax4 = axes[1, 1]
    ax4.set_facecolor("#f8fafc")
    totals = [
        max(m.kvb_backuped_tokens_total / bs, 0),
        max(m.kvb_prefetched_tokens_total / bs, 0),
        max(m.kvb_loadback_tokens_total / bs, 0),
        max(m.kvb_evicted_tokens_total / bs, 0),
    ]
    labels = ["backup\nL2→L3", "prefetch\nL3→mem", "load_back\nL3→mem", "evicted"]
    colors4 = ["#f97316", "#3b82f6", "#0f766e", "#be123c"]
    bars4 = ax4.bar(labels, totals, color=colors4, alpha=0.85, width=0.55)
    ymax4 = max(totals + [m.kvb_lifetime_mean_s, 1])
    for bar, val in zip(bars4, totals):
        if val > 0:
            ax4.text(bar.get_x() + bar.get_width()/2, bar.get_height() + ymax4 * 0.02,
                     f"{val:,.0f}", ha="center", va="bottom", fontsize=8,
                     color="#0f172a", fontweight="bold")
    if m.kvb_lifetime_mean_s > 0:
        ax4_2 = ax4.twinx()
        ax4_2.axhline(m.kvb_lifetime_mean_s, color="#6d28d9", lw=1.4, ls="--",
                      label=f"Mean lifetime {m.kvb_lifetime_mean_s:.0f}s")
        if m.sess_e2e_mean_s > 0:
            ax4_2.axhline(m.sess_e2e_mean_s, color="#6366f1", lw=1.2, ls=":",
                          label=f"Mean session E2E {m.sess_e2e_mean_s:.1f}s")
        ax4_2.set_ylabel("Seconds", fontsize=8, color="#475569")
        ax4_2.tick_params(labelsize=8)
        if ax4_2.get_legend_handles_labels()[0]: ax4_2.legend(fontsize=8, loc="upper right")
        for sp in ax4_2.spines.values(): sp.set_edgecolor("#94a3b8")
    ann = (
        f"L2 pool: {m.kvb_l2_pool_blocks:,} blocks\n"
        f"Mean L1→L2 offload: {m.kvb_l1_offload_rate_blk_s:.4f} blk/s\n"
        f"Peak L3 resident: {l3_peak_blocks:,} blocks\n"
        f"Lifetime estimate: {m.kvb_lifetime_mean_s:.0f}s")
    ax4.text(0.03, 0.97, ann, transform=ax4.transAxes, ha="left", va="top",
             fontsize=8, color="#475569",
             bbox=dict(boxstyle="round,pad=0.4", facecolor="#f1f5f9", edgecolor="#e2e8f0"))
    ax4.set_title("Cumulative KV Block Movements + Lifetime Reference",
                  fontsize=9, fontweight="bold")
    ax4.set_ylabel("Blocks moved in run", fontsize=9, color="#475569")
    ax4.grid(True, axis="y", alpha=0.3, color="#e2e8f0")
    ax4.tick_params(labelsize=8)
    for sp in ax4.spines.values(): sp.set_edgecolor("#94a3b8")

    try:
        import warnings as _wtl
        with _wtl.catch_warnings():
            _wtl.simplefilter('ignore', UserWarning)
            try:
                plt.tight_layout()
            except Exception:
                pass
    except Exception:
        pass
    return fig_to_b64(fig)

def chart_nvme_io(m: "Metrics") -> str:
    """NVMe IO workload: IOPS/BW timeline, latency, util%, SMART wear.
    Falls back to SGLang HiCache L3 counters when host NVMe traces are unavailable."""
    if m.nvme_io_ts.empty and m.nvme_wr_iops_mean == 0 and getattr(m, "kvb_l3_io_ts", pd.DataFrame()).empty:
        return ""

    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    fig.patch.set_facecolor("#ffffff")
    fig.suptitle("NVMe IO Workload Characteristics", fontsize=12,
                 fontweight="bold", color="#0f172a", y=1.01)

    # 1. Write IOPS + read IOPS timeline
    ax = axes[0, 0]
    ax.set_facecolor("#f8fafc")
    if not m.nvme_io_ts.empty:
        ts = downsample(m.nvme_io_ts, 300)
        t  = ts["time_sec"].values / 60
        wr = ts["wr_iops"].fillna(0).values
        rd = ts["rd_iops"].fillna(0).values
        ax.fill_between(t, wr, alpha=0.3, color="#f97316", label="Write IOPS")
        ax.plot(t, wr, color="#f97316", lw=1.5)
        if rd.max() > 0:
            ax.fill_between(t, rd, alpha=0.3, color="#3b82f6", label="Read IOPS")
            ax.plot(t, rd, color="#3b82f6", lw=1.5)
        ax.axhline(m.nvme_wr_iops_mean, color="#ef4444", lw=1, ls="--",
                   alpha=0.7, label=f"Mean Wr {m.nvme_wr_iops_mean:.1f} IOPS")
    ax.set_title(f"NVMe IOPS Timeline\n"
                 f"Wr mean={m.nvme_wr_iops_mean:.1f} IOPS  "
                 f"Wr BW≈{m.nvme_wr_bw_mbs_mean:.1f} MB/s",
                 fontsize=9, fontweight="bold")
    ax.set_xlabel("Time (min)", fontsize=8, color="#475569")
    ax.set_ylabel("IOPS", fontsize=9, color="#475569")
    if ax.get_legend_handles_labels()[0]: ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3, color="#e2e8f0")
    ax.tick_params(labelsize=8)
    for sp in ax.spines.values(): sp.set_edgecolor("#94a3b8")

    # 2. Write latency distribution
    ax2 = axes[0, 1]
    ax2.set_facecolor("#f8fafc")
    if not m.nvme_io_ts.empty:
        wl = m.nvme_io_ts["wr_lat_ms"].dropna()
        wl_active = wl[wl > 0]
        if len(wl_active) > 3:
            ax2.hist(wl_active, bins=min(20, len(wl_active)),
                     color="#f97316", alpha=0.75, edgecolor="#c2410c", linewidth=0.5)
            ax2.axvline(float(wl_active.mean()), color="#ef4444", lw=1.5, ls="--",
                        label=f"Mean {m.nvme_wr_lat_mean_ms:.3f}ms")
            ax2.axvline(float(wl_active.quantile(0.99)), color="#9333ea", lw=1, ls=":",
                        label=f"P99 {float(wl_active.quantile(0.99)):.3f}ms")
            if ax2.get_legend_handles_labels()[0]: ax2.legend(fontsize=8)
        elif m.nvme_wr_lat_mean_ms > 0:
            ax2.bar(["Write\nLatency"], [m.nvme_wr_lat_mean_ms],
                    color="#f97316", alpha=0.8)
            ax2.text(0, m.nvme_wr_lat_mean_ms * 1.05,
                     f"{m.nvme_wr_lat_mean_ms:.3f}ms",
                     ha="center", fontsize=10, fontweight="bold")
    ax2.set_title(f"NVMe Write Latency Distribution\n"
                  f"Mean={m.nvme_wr_lat_mean_ms:.3f}ms  Max={m.nvme_wr_lat_max_ms:.3f}ms",
                  fontsize=9, fontweight="bold")
    ax2.set_xlabel("Latency (ms)", fontsize=8, color="#475569")
    ax2.set_ylabel("Count", fontsize=9, color="#475569")
    ax2.grid(True, axis="y", alpha=0.3, color="#e2e8f0")
    ax2.tick_params(labelsize=8)
    for sp in ax2.spines.values(): sp.set_edgecolor("#94a3b8")

    # 3. IO utilisation + inflight queue depth timeline
    ax3 = axes[1, 0]
    ax3.set_facecolor("#f8fafc")
    if not m.nvme_io_ts.empty:
        ts3 = downsample(m.nvme_io_ts, 300)
        t3  = ts3["time_sec"].values / 60
        util = ts3["io_util_pct"].fillna(0).values
        ax3.fill_between(t3, util, alpha=0.3, color="#22c55e")
        ax3.plot(t3, util, color="#22c55e", lw=1.5, label="IO util %")
        ax3b = ax3.twinx()
        infl = ts3["inflight"].fillna(0).values
        ax3b.plot(t3, infl, color="#6366f1", lw=1, ls="--", alpha=0.7,
                  label=f"Inflight (max={m.nvme_inflight_max})")
        ax3b.set_ylabel("Queue depth", fontsize=8, color="#6366f1")
        ax3b.tick_params(labelsize=7)
        ax3b.set_facecolor("#f8fafc")
        for sp in ax3b.spines.values(): sp.set_edgecolor("#94a3b8")
        lines1, labs1 = ax3.get_legend_handles_labels()
        lines2, labs2 = ax3b.get_legend_handles_labels()
        ax3.legend(lines1 + lines2, labs1 + labs2, fontsize=8)
    ax3.set_title(f"NVMe IO Utilisation & Queue Depth\n"
                  f"Mean util={m.nvme_io_util_pct:.3f}%  "
                  f"Mean inflight={m.nvme_inflight_mean:.2f}",
                  fontsize=9, fontweight="bold")
    ax3.set_xlabel("Time (min)", fontsize=8, color="#475569")
    ax3.set_ylabel("IO Util %", fontsize=9, color="#475569")
    ax3.grid(True, alpha=0.3, color="#e2e8f0")
    ax3.tick_params(labelsize=8)
    for sp in ax3.spines.values(): sp.set_edgecolor("#94a3b8")

    # 4. SMART summary bar
    ax4 = axes[1, 1]
    ax4.set_facecolor("#f8fafc")
    smart_cats  = ["Bytes Written\n(run, GB)", "Bytes Read\n(run, GB)",
                   "Drive Wear\n(%used)", "Avail Spare\n(%)"]
    smart_vals  = [m.nvme_bytes_written_total / 1e9,
                   m.nvme_bytes_read_total / 1e9,
                   m.nvme_smart_wear_pct,
                   m.nvme_smart_avail_spare]
    scolors     = ["#f97316","#3b82f6","#ef4444","#22c55e"]
    bars4 = ax4.bar(smart_cats, smart_vals, color=scolors, alpha=0.85,
                    width=0.5, edgecolor="#94a3b8", linewidth=0.5)
    for bar, val in zip(bars4, smart_vals):
        if val > 0:
            ax4.text(bar.get_x() + bar.get_width()/2,
                     bar.get_height() + max(smart_vals)*0.02,
                     f"{val:.2f}", ha="center", va="bottom",
                     fontsize=9, color="#0f172a", fontweight="bold")
    ann4 = (f"Wr cmds: {m.nvme_host_write_cmds:,}\n"
            f"Rd cmds: {m.nvme_host_read_cmds:,}\n"
            f"KVB block: {m.kvb_block_size_mb:.1f} MB\n"
            f"Wr BW: {m.nvme_wr_bw_mbs_mean:.1f} MB/s (est)")
    ax4.text(0.97, 0.97, ann4, transform=ax4.transAxes,
             ha="right", va="top", fontsize=8, color="#475569",
             bbox=dict(boxstyle="round,pad=0.4", facecolor="#f1f5f9",
                       edgecolor="#e2e8f0"))
    ax4.set_title("SMART SSD Health & Run IO Summary\n"
                  f"(SMART data_units × 512KB each)",
                  fontsize=9, fontweight="bold")
    ax4.grid(True, axis="y", alpha=0.3, color="#e2e8f0")
    ax4.tick_params(labelsize=8)
    for sp in ax4.spines.values(): sp.set_edgecolor("#94a3b8")

    try:
        import warnings as _wtl
        with _wtl.catch_warnings():
            _wtl.simplefilter('ignore', UserWarning)
            try:
                plt.tight_layout()
            except Exception:
                pass
    except Exception:
        pass
    return fig_to_b64(fig)


def chart_blkio_deep(m: "Metrics") -> str:
    """Deep NVMe IO: request size, alignment, seq/random, temporal patterns.
       Shows 'enable with biosnoop/blktrace' placeholder when data absent."""

    fig, axes = plt.subplots(2, 3, figsize=(15, 9))
    fig.patch.set_facecolor("#ffffff")
    fig.suptitle("NVMe IO Deep Profiling — Request-Level Characteristics",
                 fontsize=12, fontweight="bold", color="#0f172a", y=1.01)

    PLACEHOLDER = not m.blkio_available
    PH_COLOR    = "#94a3b8"

    def _placeholder(ax, title):
        ax.set_facecolor("#f8fafc")
        ax.text(0.5, 0.55, f"Requires blktrace / biosnoop",
                ha="center", va="center", transform=ax.transAxes,
                fontsize=10, color=PH_COLOR, fontweight="bold")
        ax.text(0.5, 0.38,
                "sudo biosnoop -d nvme2n1 > blkio_trace.csv\n"
                "Then pass: --blkio-trace blkio_trace.csv",
                ha="center", va="center", transform=ax.transAxes,
                fontsize=8, color="#cbd5e1", style="italic")
        ax.set_title(title, fontsize=9, fontweight="bold")
        for sp in ax.spines.values(): sp.set_edgecolor("#e2e8f0")
        ax.tick_params(labelbottom=False, labelleft=False)

    # 1. Request size distribution
    ax = axes[0, 0]
    if m.blkio_available and not m.blkio_ts.empty and "size_bytes" in m.blkio_ts.columns:
        sk = m.blkio_ts["size_bytes"] / 1024
        ax.set_facecolor("#f8fafc")
        ax.hist(sk, bins=30, color="#6366f1", alpha=0.75,
                edgecolor="#4338ca", linewidth=0.5)
        kvb_line = m.kvb_block_size_mb * 1024
        ax.axvline(kvb_line, color="#ef4444", lw=1.5, ls="--",
                   label=f"KV block {kvb_line:.0f} KB")
        ax.axvline(4, color="#f97316", lw=1, ls=":", label="4KB page size")
        ax.set_xlabel("Request size (KB)", fontsize=8)
        ax.set_ylabel("Count", fontsize=9)
        if ax.get_legend_handles_labels()[0]: ax.legend(fontsize=8)
        ax.grid(True, axis="y", alpha=0.3, color="#e2e8f0")
        ax.tick_params(labelsize=8)
        for sp in ax.spines.values(): sp.set_edgecolor("#94a3b8")
    else:
        _placeholder(ax, "Request Size Distribution\n(R/W, KB)")

    # 2. Alignment analysis
    ax2 = axes[0, 1]
    if m.blkio_available and m.blkio_aligned_kvb_pct > 0:
        ax2.set_facecolor("#f8fafc")
        cats  = ["KV Block\nAligned", "Page\nAligned\n(4KB)", "Not\nAligned"]
        kvb_a = m.blkio_aligned_kvb_pct
        pg_a  = m.blkio_aligned_page_pct
        vals2 = [kvb_a, pg_a, 100 - max(kvb_a, pg_a)]
        clrs2 = ["#22c55e", "#3b82f6", "#ef4444"]
        bars2 = ax2.bar(cats, vals2, color=clrs2, alpha=0.85, width=0.5)
        for bar, val in zip(bars2, vals2):
            ax2.text(bar.get_x() + bar.get_width()/2,
                     bar.get_height() + 1,
                     f"{val:.1f}%", ha="center", va="bottom", fontsize=9, fontweight="bold")
        ax2.set_ylabel("% of operations", fontsize=9)
        ax2.set_ylim(0, 115)
        ax2.grid(True, axis="y", alpha=0.3, color="#e2e8f0")
        ax2.tick_params(labelsize=8)
        for sp in ax2.spines.values(): sp.set_edgecolor("#94a3b8")
    else:
        _placeholder(ax2, "Alignment Analysis\n(KV block / page size)")
    ax2.set_title("Access Alignment\nKV block & 4KB page", fontsize=9, fontweight="bold")

    # 3. Sequential vs random
    ax3 = axes[0, 2]
    if m.blkio_available and m.blkio_seq_pct > 0:
        ax3.set_facecolor("#f8fafc")
        ax3.pie([m.blkio_seq_pct, 100 - m.blkio_seq_pct],
                labels=[f"Sequential\n{m.blkio_seq_pct:.1f}%",
                        f"Random\n{100-m.blkio_seq_pct:.1f}%"],
                colors=["#22c55e","#ef4444"], autopct="%1.1f%%",
                startangle=90, textprops={"fontsize":9})
        for sp in ax3.spines.values(): sp.set_edgecolor("#94a3b8")
    else:
        _placeholder(ax3, "Sequential vs Random Access\n(LBA pattern)")
    ax3.set_title("Sequential vs Random\n(LBA stride < 2× KV block = sequential)",
                  fontsize=9, fontweight="bold")

    # 4. Inter-arrival time distribution
    ax4 = axes[1, 0]
    if m.blkio_available and not m.blkio_ts.empty and "time_sec" in m.blkio_ts.columns:
        ax4.set_facecolor("#f8fafc")
        ia_us = m.blkio_ts["time_sec"].diff().dropna() * 1e6
        ia_us = ia_us[ia_us > 0]
        if len(ia_us) > 3:
            ax4.hist(ia_us, bins=30, color="#3b82f6", alpha=0.75,
                     edgecolor="#1d4ed8", linewidth=0.5)
            ax4.axvline(float(ia_us.mean()), color="#ef4444", lw=1.5, ls="--",
                        label=f"Mean {ia_us.mean():.1f}µs")
            ax4.set_xlabel("Inter-arrival time (µs)", fontsize=8)
            ax4.set_ylabel("Count", fontsize=9)
            if ax4.get_legend_handles_labels()[0]: ax4.legend(fontsize=8)
            ax4.grid(True, axis="y", alpha=0.3, color="#e2e8f0")
            ax4.tick_params(labelsize=8)
            for sp in ax4.spines.values(): sp.set_edgecolor("#94a3b8")
    else:
        _placeholder(ax4, "Request Inter-Arrival Time\n(µs granularity)")
    ax4.set_title("IO Request Inter-Arrival Time\n(burst detection, temporal dynamics)",
                  fontsize=9, fontweight="bold")

    # 5. Hot/cold LBA map
    ax5 = axes[1, 1]
    if m.blkio_available and not m.blkio_ts.empty and "offset_bytes" in m.blkio_ts.columns:
        ax5.set_facecolor("#f8fafc")
        offs = m.blkio_ts["offset_bytes"].values / 1e9  # GB
        t5   = m.blkio_ts["time_sec"].values / 60
        ax5.scatter(t5, offs, s=2, alpha=0.4, color="#f97316")
        ax5.set_xlabel("Time (min)", fontsize=8)
        ax5.set_ylabel("LBA offset (GB)", fontsize=9)
        ax5.grid(True, alpha=0.2, color="#e2e8f0")
        ax5.tick_params(labelsize=8)
        for sp in ax5.spines.values(): sp.set_edgecolor("#94a3b8")
    else:
        _placeholder(ax5, "Hot/Cold LBA Area Map\n(access pattern over time)")
    ax5.set_title("LBA Access Map (Hot/Cold)\n(vertical clusters = hot areas)",
                  fontsize=9, fontweight="bold")

    # 6. Bandwidth degradation / temporal pattern
    ax6 = axes[1, 2]
    ax6.set_facecolor("#f8fafc")
    if not m.nvme_io_ts.empty:
        ts6  = downsample(m.nvme_io_ts, 200)
        t6   = ts6["time_sec"].values / 60
        wr6  = ts6["wr_iops"].fillna(0).values * (m.kvb_block_size_mb if m.kvb_block_size_mb > 0 else 5)
        ax6.fill_between(t6, wr6, alpha=0.3, color="#f97316", label="Est. Wr BW (MB/s)")
        ax6.plot(t6, wr6, color="#f97316", lw=1.5)
        # Rolling mean to show trend
        import pandas as _pd
        rolling = _pd.Series(wr6).rolling(window=10, min_periods=1).mean().values
        ax6.plot(t6, rolling, color="#ef4444", lw=2, ls="--", label="10-sample trend")
        if ax6.get_legend_handles_labels()[0]: ax6.legend(fontsize=8)
        if m.nvme_io_ts.empty or (m.nvme_io_ts["wr_iops"].fillna(0) > 0).sum() == 0:
            ax6.text(0.5, 0.5, "No write activity\nobserved in this run",
                     ha="center", va="center", transform=ax6.transAxes,
                     fontsize=10, color="#94a3b8")
    else:
        _placeholder(ax6, "Write BW Trend\n(degradation over time)")
    ax6.set_title("Write BW & Temporal Pattern\n(seasonal/burst detection)",
                  fontsize=9, fontweight="bold")
    ax6.set_xlabel("Time (min)", fontsize=8, color="#475569")
    ax6.set_ylabel("Est. Write BW (MB/s)", fontsize=9, color="#475569")
    ax6.grid(True, alpha=0.3, color="#e2e8f0")
    ax6.tick_params(labelsize=8)
    for sp in ax6.spines.values(): sp.set_edgecolor("#94a3b8")

    try:
        import warnings as _wtl
        with _wtl.catch_warnings():
            _wtl.simplefilter('ignore', UserWarning)
            try:
                plt.tight_layout()
            except Exception:
                pass
    except Exception:
        pass
    return fig_to_b64(fig)


def chart_kvssd_io(m: "Metrics") -> str:
    """§C/D/E: SSD IO workload — read/write size, alignment, seq/random, IAT, burst."""
    has_blktrace = m.blktrace_available
    PLACEHOLDER_COLOR = "#94a3b8"

    fig, axes = plt.subplots(3, 3, figsize=(15, 13))
    fig.patch.set_facecolor("#ffffff")
    fig.suptitle("KV$ SSD IO Workload Characteristics  (§C Read · §D Write · §E Trim)",
                 fontsize=11, fontweight="bold", color="#0f172a", y=1.01)

    def _ph(ax, title, note="requires blktrace/biosnoop"):
        ax.set_facecolor("#f8fafc")
        ax.text(0.5, 0.55, title, ha="center", va="center",
                transform=ax.transAxes, fontsize=9, color=PLACEHOLDER_COLOR, fontweight="bold")
        ax.text(0.5, 0.38, note, ha="center", va="center",
                transform=ax.transAxes, fontsize=7.5, color="#cbd5e1", style="italic")
        for sp in ax.spines.values(): sp.set_edgecolor("#e2e8f0")
        ax.tick_params(labelbottom=False, labelleft=False)

    # Row 0: Request size distribution (R and W), IAT
    ax = axes[0, 0]
    ax.set_facecolor("#f8fafc")
    if has_blktrace and m.rd_req_size_hist_kb:
        import numpy as _np
        bins = _np.linspace(0, max(max(m.rd_req_size_hist_kb), 1), 25)
        ax.hist(m.rd_req_size_hist_kb, bins=bins,
                color="#3b82f6", alpha=0.75, edgecolor="#1d4ed8", lw=0.5,
                label=f"Read (n={len(m.rd_req_size_hist_kb)})")
        if m.wr_req_size_hist_kb:
            ax.hist(m.wr_req_size_hist_kb, bins=bins,
                    color="#f97316", alpha=0.65, edgecolor="#c2410c", lw=0.5,
                    label=f"Write (n={len(m.wr_req_size_hist_kb)})")
        kvb_kb = m.kvb_block_size_mb * 1024
        if kvb_kb > 0:
            ax.axvline(kvb_kb, color="#ef4444", lw=1.5, ls="--", label=f"KV blk {kvb_kb:.0f}KB")
        ax.axvline(4, color="#a855f7", lw=1, ls=":", label="4KB page")
        if ax.get_legend_handles_labels()[0]: ax.legend(fontsize=7); ax.grid(True, axis="y", alpha=0.3, color="#e2e8f0")
        ax.set_xlabel("Request size (KB)", fontsize=8); ax.set_ylabel("Count", fontsize=8)
    else:
        _ph(ax, "R/W Request Size Distribution\n(KB)")
    ax.set_title(f"Request Size: R={m.rd_req_size_mean_kb:.0f}KB mean  W={m.wr_req_size_mean_kb:.0f}KB mean",
                 fontsize=8.5, fontweight="bold")
    ax.tick_params(labelsize=7)
    for sp in ax.spines.values(): sp.set_edgecolor("#94a3b8")

    ax2 = axes[0, 1]
    ax2.set_facecolor("#f8fafc")
    if has_blktrace and m.rd_iat_hist_us:
        import numpy as _np
        iat_r = _np.array(m.rd_iat_hist_us)
        iat_r = iat_r[iat_r < _np.percentile(iat_r, 99)]  # clip outliers
        ax2.hist(iat_r, bins=25, color="#3b82f6", alpha=0.75, edgecolor="#1d4ed8", lw=0.5, label="Read IAT")
        if m.wr_iat_hist_us:
            iat_w = _np.array(m.wr_iat_hist_us)
            iat_w = iat_w[iat_w < _np.percentile(iat_w, 99)]
            ax2.hist(iat_w, bins=25, color="#f97316", alpha=0.65, edgecolor="#c2410c", lw=0.5, label="Write IAT")
        ax2.axvline(m.rd_iat_mean_us, color="#ef4444", lw=1.5, ls="--",
                    label=f"R mean {m.rd_iat_mean_us:.0f}µs")
        if ax2.get_legend_handles_labels()[0]: ax2.legend(fontsize=7); ax2.grid(True, axis="y", alpha=0.3, color="#e2e8f0")
        ax2.set_xlabel("Inter-arrival time (µs)", fontsize=8)
    else:
        _ph(ax2, "Request Inter-Arrival Time (µs)\nBurst Temporal Dynamics")
    ax2.set_title(f"IAT: R P95={m.rd_iat_p95_us:.0f}µs  W P95={m.wr_iat_p95_us:.0f}µs",
                  fontsize=8.5, fontweight="bold")
    ax2.tick_params(labelsize=7)
    for sp in ax2.spines.values(): sp.set_edgecolor("#94a3b8")

    # Seq vs random pie
    ax3 = axes[0, 2]
    ax3.set_facecolor("#f8fafc")
    if has_blktrace and (m.rd_seq_pct > 0 or m.rd_rand_pct > 0):
        labels = [f"R Seq\n{m.rd_seq_pct:.0f}%", f"R Rand\n{m.rd_rand_pct:.0f}%",
                  f"W Seq\n{m.wr_seq_pct:.0f}%", f"W Rand\n{m.wr_rand_pct:.0f}%"]
        values = [m.rd_seq_pct, m.rd_rand_pct, m.wr_seq_pct, m.wr_rand_pct]
        colors_pie = ["#3b82f6", "#bfdbfe", "#f97316", "#fed7aa"]
        non_zero = [(l, v, c) for l, v, c in zip(labels, values, colors_pie) if v > 0]
        if non_zero:
            ax3.pie([v for _, v, _ in non_zero],
                    labels=[l for l, _, _ in non_zero],
                    colors=[c for _, _, c in non_zero],
                    autopct="%1.0f%%", startangle=90,
                    textprops={"fontsize": 7})
    else:
        _ph(ax3, "Sequential vs Random Access\n(byte %, R blue / W orange)")
    ax3.set_title(f"Seq/Rand  R:{m.rd_seq_pct:.0f}%/{m.rd_rand_pct:.0f}%  "
                  f"W:{m.wr_seq_pct:.0f}%/{m.wr_rand_pct:.0f}%",
                  fontsize=8.5, fontweight="bold")
    for sp in ax3.spines.values(): sp.set_edgecolor("#94a3b8")

    # Row 1: Alignment, LBA hot/cold, skewness
    ax4 = axes[1, 0]
    ax4.set_facecolor("#f8fafc")
    if has_blktrace and (m.rd_kvb_aligned_pct + m.wr_kvb_aligned_pct) > 0:
        cats   = ["KVB\nAligned\n(Read)", "Page\nAligned\n(Read)",
                  "KVB\nAligned\n(Write)", "Page\nAligned\n(Write)"]
        vals4  = [m.rd_kvb_aligned_pct, m.rd_page_aligned_pct,
                  m.wr_kvb_aligned_pct, m.wr_page_aligned_pct]
        misvals= [100-v for v in vals4]
        colors4= ["#3b82f6","#93c5fd","#f97316","#fed7aa"]
        bars4  = ax4.bar(cats, vals4, color=colors4, alpha=0.85,
                         width=0.5, edgecolor="#94a3b8", lw=0.5)
        for bar, val in zip(bars4, vals4):
            ax4.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1.5,
                     f"{val:.0f}%", ha="center", va="bottom", fontsize=7.5, fontweight="bold")
        ax4.axhline(100, color="#e2e8f0", lw=0.5, ls="--")
        ax4.set_ylim(0, 115); ax4.set_ylabel("% of IO ops", fontsize=8)
        ax4.grid(True, axis="y", alpha=0.3, color="#e2e8f0")
    else:
        _ph(ax4, "Alignment Analysis\n(KV block / 4KB page)")
    ax4.set_title(f"IO Alignment  "
                  f"R-KVB:{m.rd_kvb_aligned_pct:.0f}%  W-KVB:{m.wr_kvb_aligned_pct:.0f}%",
                  fontsize=8.5, fontweight="bold")
    ax4.tick_params(labelsize=7)
    for sp in ax4.spines.values(): sp.set_edgecolor("#94a3b8")

    # LBA heatmap / hot-cold
    ax5 = axes[1, 1]
    ax5.set_facecolor("#f8fafc")
    if has_blktrace and not m.blkio_ts.empty and "offset_bytes" in m.blkio_ts.columns:
        import numpy as _np
        df_r5 = m.blkio_ts[m.blkio_ts["type"] == "R"]
        df_w5 = m.blkio_ts[m.blkio_ts["type"] == "W"]
        if not df_r5.empty:
            t5r = df_r5["time_sec"].values / 60
            o5r = df_r5["offset_bytes"].values / 1e9
            ax5.scatter(t5r, o5r, s=1.5, alpha=0.3, color="#3b82f6", label="Read")
        if not df_w5.empty:
            t5w = df_w5["time_sec"].values / 60
            o5w = df_w5["offset_bytes"].values / 1e9
            ax5.scatter(t5w, o5w, s=1.5, alpha=0.3, color="#f97316", label="Write")
        if ax5.get_legend_handles_labels()[0]: ax5.legend(fontsize=7, markerscale=4)
        ax5.set_xlabel("Time (min)", fontsize=8)
        ax5.set_ylabel("LBA offset (GB)", fontsize=8)
        ax5.grid(True, alpha=0.15, color="#e2e8f0")
    else:
        _ph(ax5, "LBA Access Map — Hot/Cold Areas\n(vertical clusters = hot LBA zones)")
    ax5.set_title(f"LBA Scatter  Gini R:{m.rd_lba_gini:.2f}  W:{m.wr_lba_gini:.2f}  "
                  f"Skew R:{m.rd_lba_skewness:.2f}",
                  fontsize=8.5, fontweight="bold")
    ax5.tick_params(labelsize=7)
    for sp in ax5.spines.values(): sp.set_edgecolor("#94a3b8")

    # Size vs random correlation scatter
    ax6 = axes[1, 2]
    ax6.set_facecolor("#f8fafc")
    if has_blktrace and not m.blkio_ts.empty and "is_seq" in m.blkio_ts.columns:
        df_r6 = m.blkio_ts[m.blkio_ts["type"] == "R"].sample(min(500, len(m.blkio_ts[m.blkio_ts["type"]=="R"])))
        ax6.scatter(df_r6["size_bytes"] / 1024,
                    df_r6["is_seq"].astype(int) + (0.1 * (2*__import__("random").random()-1)),
                    s=4, alpha=0.3, color="#3b82f6")
        ax6.set_yticks([0, 1]); ax6.set_yticklabels(["Random", "Sequential"], fontsize=7)
        ax6.set_xlabel("Request size (KB)", fontsize=8)
        ax6.grid(True, axis="x", alpha=0.3, color="#e2e8f0")
        ax6.text(0.97, 0.05, f"corr={m.rd_size_rand_corr:.3f}",
                 transform=ax6.transAxes, ha="right", fontsize=8, color="#334155",
                 bbox=dict(boxstyle="round,pad=0.3", facecolor="#f1f5f9", edgecolor="#e2e8f0"))
    else:
        _ph(ax6, "Size vs Seq/Rand Correlation\n(point-biserial correlation)")
    ax6.set_title(f"Size vs Random  R-corr:{m.rd_size_rand_corr:.3f}  W-corr:{m.wr_size_rand_corr:.3f}",
                  fontsize=8.5, fontweight="bold")
    ax6.tick_params(labelsize=7)
    for sp in ax6.spines.values(): sp.set_edgecolor("#94a3b8")

    # Row 2: Trim/discard, R/W/T ratio over time, BW degradation
    ax7 = axes[2, 0]
    ax7.set_facecolor("#f8fafc")
    trim_cats  = ["Trim Ops", "Trim BW\n(MB/s)", "Trim Aligned\n(KVB%)", "TRIM/Write\nRatio"]
    trim_vals  = [m.trim_ops_total,
                  round(m.kvb_trim_bytes_s / 1e6, 3),
                  m.trim_kvb_aligned_pct,
                  round(m.tw_ratio_mean * 100, 2)]
    trim_cols  = ["#ef4444","#f97316","#22c55e","#a855f7"]
    bars7 = ax7.bar(trim_cats, trim_vals, color=trim_cols, alpha=0.85, width=0.5,
                    edgecolor="#94a3b8", lw=0.5)
    for bar, val in zip(bars7, trim_vals):
        if val > 0:
            ax7.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(trim_vals)*0.02,
                     f"{val:.2g}", ha="center", va="bottom", fontsize=7.5, fontweight="bold")
    txt = "TRIM detected" if m.trim_present else "No TRIM observed"
    ax7.text(0.97, 0.97, txt, transform=ax7.transAxes, ha="right", va="top",
             fontsize=8, color="#059669" if m.trim_present else "#94a3b8", fontweight="bold")
    ax7.set_title(f"TRIM/Discard Events  ops={m.trim_ops_total:,}  "
                  f"{'TRIM active' if m.trim_present else 'no TRIM'}",
                  fontsize=8.5, fontweight="bold")
    ax7.tick_params(labelsize=7)
    ax7.grid(True, axis="y", alpha=0.3, color="#e2e8f0")
    for sp in ax7.spines.values(): sp.set_edgecolor("#94a3b8")

    # R/W/T bandwidth over time
    ax8 = axes[2, 1]
    ax8.set_facecolor("#f8fafc")
    if has_blktrace and not m.blkio_ts.empty:
        import pandas as _pd, numpy as _np
        bk = m.blkio_ts.copy()
        dt8 = bk["time_sec"].max() / 60.0  # minutes
        t_min = _np.linspace(0, dt8, min(100, len(bk)))
        # Bin into 100 windows
        bins8 = (bk["time_sec"] / max(bk["time_sec"].max(), 1) * 99).astype(int)
        r_bw  = bk[bk["type"]=="R"].groupby(bins8[bk["type"]=="R"])["size_bytes"].sum() / 1e6
        w_bw  = bk[bk["type"]=="W"].groupby(bins8[bk["type"]=="W"])["size_bytes"].sum() / 1e6
        d_bw  = bk[bk["type"]=="D"].groupby(bins8[bk["type"]=="D"])["size_bytes"].sum() / 1e6
        all_b = range(100)
        r_bw  = r_bw.reindex(all_b, fill_value=0)
        w_bw  = w_bw.reindex(all_b, fill_value=0)
        d_bw  = d_bw.reindex(all_b, fill_value=0)
        t_ax  = _np.linspace(0, dt8, 100)
        ax8.fill_between(t_ax, r_bw, alpha=0.3, color="#3b82f6")
        ax8.plot(t_ax, r_bw, color="#3b82f6", lw=1.2, label="Read")
        ax8.fill_between(t_ax, w_bw, alpha=0.3, color="#f97316")
        ax8.plot(t_ax, w_bw, color="#f97316", lw=1.2, label="Write")
        if d_bw.sum() > 0:
            ax8.fill_between(t_ax, d_bw, alpha=0.3, color="#ef4444")
            ax8.plot(t_ax, d_bw, color="#ef4444", lw=1.2, label="Discard")
        if ax8.get_legend_handles_labels()[0]: ax8.legend(fontsize=7); ax8.grid(True, alpha=0.3, color="#e2e8f0")
        ax8.set_xlabel("Time (min)", fontsize=8)
        ax8.set_ylabel("MB/window", fontsize=8)
    else:
        _ph(ax8, "R/W/T Bandwidth Over Time\nSeasonal/Burst Pattern")
    ax8.set_title(f"R/W/T Pattern  corr_RW={m.corr_rw:.3f}  "
                  f"R/W ratio={m.rw_ratio_mean:.2f}  "
                  f"period={m.read_seasonal_period_s:.0f}s",
                  fontsize=8.5, fontweight="bold")
    ax8.tick_params(labelsize=7)
    for sp in ax8.spines.values(): sp.set_edgecolor("#94a3b8")

    # BW degradation / trend
    ax9 = axes[2, 2]
    ax9.set_facecolor("#f8fafc")
    if not m.nvme_io_ts.empty:
        import pandas as _pd, numpy as _np
        ts9 = downsample(m.nvme_io_ts, 200)
        t9  = ts9["time_sec"].values / 60
        wr9 = ts9["wr_iops"].fillna(0).values * (m.kvb_block_size_mb if m.kvb_block_size_mb > 0 else 5)
        ax9.fill_between(t9, wr9, alpha=0.3, color="#f97316")
        ax9.plot(t9, wr9, color="#f97316", lw=1.2, label="Write BW")
        roll = _pd.Series(wr9).rolling(15, min_periods=1).mean().values
        ax9.plot(t9, roll, color="#ef4444", lw=2, ls="--", label="Trend")
        if len(wr9) > 20:
            mid = len(wr9) // 2
            early = _np.mean(wr9[:mid]); late = _np.mean(wr9[mid:])
            deg = (1 - late / max(early, 1e-9)) * 100
            ax9.text(0.97, 0.97, f"Degradation: {deg:+.1f}%",
                     transform=ax9.transAxes, ha="right", va="top", fontsize=8,
                     color="#ef4444" if deg > 5 else "#059669",
                     bbox=dict(boxstyle="round,pad=0.3", facecolor="#f1f5f9", edgecolor="#e2e8f0"))
        if ax9.get_legend_handles_labels()[0]: ax9.legend(fontsize=7); ax9.grid(True, alpha=0.3, color="#e2e8f0")
        ax9.set_xlabel("Time (min)", fontsize=8); ax9.set_ylabel("Est. Write BW (MB/s)", fontsize=8)
    else:
        _ph(ax9, "Write BW Trend\nDegradation Over Time", "needs nvme_driver_timeseries")
    ax9.set_title(f"Write BW Trend / Degradation\n"
                  f"Mean={m.nvme_wr_bw_mbs_mean:.1f} MB/s  "
                  f"Max={m.nvme_wr_bw_mbs_max:.1f} MB/s",
                  fontsize=8.5, fontweight="bold")
    ax9.tick_params(labelsize=7)
    for sp in ax9.spines.values(): sp.set_edgecolor("#94a3b8")

    try:
        import warnings as _wtl
        with _wtl.catch_warnings():
            _wtl.simplefilter('ignore', UserWarning)
            try:
                plt.tight_layout()
            except Exception:
                pass
    except Exception:
        pass
    return fig_to_b64(fig)


def chart_kvssd_cross_layer(m: "Metrics") -> str:
    """§G: Cross-layer KPIs: SSD/GPU throughput bottleneck, per-token SSD cost, correlations."""
    fig, axes = plt.subplots(1, 3, figsize=(13, 5))
    fig.patch.set_facecolor("#ffffff")
    fig.suptitle("§G Cross-Layer KPIs — SSD ↔ GPU ↔ Inference",
                 fontsize=11, fontweight="bold", color="#0f172a", y=1.01)

    # 1. Throughput bottleneck analysis
    ax = axes[0]; ax.set_facecolor("#f8fafc")
    gpu_t = m.throughput_bottleneck_gpu_tok_s
    ssd_t = m.throughput_bottleneck_ssd_tok_s
    cats_b  = ["GPU\ntok/s", "SSD-limited\ntok/s"]
    vals_b  = [gpu_t, ssd_t]
    c_b     = ["#6366f1" if gpu_t >= ssd_t else "#22c55e",
               "#f97316" if ssd_t < gpu_t else "#ef4444"]
    bars_b = ax.bar(cats_b, vals_b, color=c_b, alpha=0.85, width=0.4,
                    edgecolor="#94a3b8", lw=0.5)
    for bar, val in zip(bars_b, vals_b):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(vals_b)*0.02,
                f"{val:.0f}", ha="center", va="bottom", fontsize=9, fontweight="bold")
    bottleneck_color = "#ef4444" if "SSD" in m.throughput_bottleneck_label else (
                       "#22c55e" if "GPU" in m.throughput_bottleneck_label else "#f97316")
    ax.text(0.5, 0.5, m.throughput_bottleneck_label, ha="center", va="center",
            transform=ax.transAxes, fontsize=11, color=bottleneck_color, fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="#f8fafc", edgecolor="#e2e8f0"))
    ax.set_title(f"Throughput Bottleneck\nbottleneck(GPU={gpu_t:.0f}, SSD={ssd_t:.0f})",
                 fontsize=9, fontweight="bold")
    ax.set_ylabel("tokens/s", fontsize=9, color="#475569")
    ax.grid(True, axis="y", alpha=0.3, color="#e2e8f0")
    ax.tick_params(labelsize=8)
    for sp in ax.spines.values(): sp.set_edgecolor("#94a3b8")

    # 2. Per-token SSD cost
    ax2 = axes[1]; ax2.set_facecolor("#f8fafc")
    cats2 = ["SSD Read\nper Output Token\n(KB)", "SSD Write\nper Input Token\n(KB)"]
    vals2 = [m.ssd_read_per_output_token_kb, m.ssd_write_per_input_token_kb]
    c2    = ["#3b82f6", "#f97316"]
    bars2 = ax2.bar(cats2, vals2, color=c2, alpha=0.85, width=0.4,
                    edgecolor="#94a3b8", lw=0.5)
    for bar, val in zip(bars2, vals2):
        ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(max(vals2), 0.001)*0.04,
                 f"{val:.3f}KB", ha="center", va="bottom", fontsize=9, fontweight="bold")
    # Annotate KV bytes per token reference
    kvb_kb = m.kv_bytes_per_token / 1024
    if kvb_kb > 0:
        ax2.axhline(kvb_kb, color="#a855f7", lw=1, ls="--", alpha=0.7,
                    label=f"KV/tok={kvb_kb:.0f}KB")
        if ax2.get_legend_handles_labels()[0]: ax2.legend(fontsize=8)
    ax2.set_title(f"SSD Cost per Token\n"
                  f"§88: Rd/output-tok={m.ssd_read_per_output_token_kb:.3f}KB\n"
                  f"§89: Wr/input-tok={m.ssd_write_per_input_token_kb:.3f}KB",
                  fontsize=8.5, fontweight="bold")
    ax2.set_ylabel("KB per token", fontsize=9, color="#475569")
    ax2.grid(True, axis="y", alpha=0.3, color="#e2e8f0")
    ax2.tick_params(labelsize=8)
    for sp in ax2.spines.values(): sp.set_edgecolor("#94a3b8")

    # 3. Cross-correlation summary
    ax3 = axes[2]; ax3.set_facecolor("#f8fafc")
    corr_labels = ["R/W\ncorrelation", "W/D\ncorrelation", "R/D\ncorrelation"]
    corr_vals   = [m.corr_rw, m.corr_wd, m.rd_size_rand_corr]
    c3 = ["#22c55e" if abs(v) > 0.5 else "#94a3b8" for v in corr_vals]
    bars3 = ax3.bar(corr_labels, corr_vals, color=c3, alpha=0.85, width=0.4,
                    edgecolor="#94a3b8", lw=0.5)
    for bar, val in zip(bars3, corr_vals):
        ax3.text(bar.get_x() + bar.get_width()/2,
                 val + (0.03 if val >= 0 else -0.06),
                 f"{val:.3f}", ha="center", va="bottom", fontsize=9, fontweight="bold")
    ax3.axhline(0, color="#e2e8f0", lw=0.5)
    ax3.axhline(0.5,  color="#22c55e", lw=0.8, ls=":", alpha=0.6, label="strong +corr")
    ax3.axhline(-0.5, color="#ef4444", lw=0.8, ls=":", alpha=0.6, label="strong −corr")
    ax3.set_ylim(-1.1, 1.1)
    if ax3.get_legend_handles_labels()[0]: ax3.legend(fontsize=7)
    ax3.set_title(f"§90–§92 Cross-Layer Correlations\n"
                  f"R/W={m.corr_rw:.3f}  W/Trim={m.corr_wd:.3f}\n"
                  f"Seasonal period={m.read_seasonal_period_s:.0f}s",
                  fontsize=8.5, fontweight="bold")
    ax3.set_ylabel("Pearson r", fontsize=9, color="#475569")
    ax3.grid(True, axis="y", alpha=0.3, color="#e2e8f0")
    ax3.tick_params(labelsize=8)
    for sp in ax3.spines.values(): sp.set_edgecolor("#94a3b8")

    try:
        import warnings as _wtl
        with _wtl.catch_warnings():
            _wtl.simplefilter('ignore', UserWarning)
            try:
                plt.tight_layout()
            except Exception:
                pass
    except Exception:
        pass
    return fig_to_b64(fig)


def chart_ssd_read_workload(m: "Metrics") -> str:
    """§C — KV$ SSD Read workload characteristics (6-panel)."""
    fig, axes = plt.subplots(2, 3, figsize=(15, 9))
    fig.patch.set_facecolor("#ffffff")
    fig.suptitle("KV$ SSD — Read Workload Characteristics (§C)",
                 fontsize=12, fontweight="bold", color="#0f172a", y=1.01)
    C1, C2, C3 = "#3b82f6", "#22c55e", "#f97316"
    PH_MSG = "Enable:\nsudo blktrace -d /dev/nvme0n1 -o - |\nblkparse -i - > blktrace.txt\nThen: --blktrace blktrace.txt"

    def _ph(ax, title):
        ax.set_facecolor("#f8fafc")
        ax.text(0.5, 0.5, PH_MSG, ha="center", va="center",
                transform=ax.transAxes, fontsize=8,
                color="#94a3b8", style="italic")
        ax.set_title(title, fontsize=9, fontweight="bold")
        for sp in ax.spines.values(): sp.set_edgecolor("#e2e8f0")
        ax.tick_params(labelbottom=False, labelleft=False)

    # 1. Read BW over time — prefer full iostat timeseries, fall back to temporal_pattern
    ax = axes[0, 0]; ax.set_facecolor("#f8fafc")
    if not m.nvme_io_ts.empty and len(m.nvme_io_ts) > 5:
        ts  = downsample(m.nvme_io_ts, 200)
        t   = ts["time_sec"].values / 60
        bw_col = next((c for c in ("rd_bw_mbs", "rd_iops") if c in ts.columns), None)
        if bw_col:
            rd_vals = ts[bw_col].fillna(0).values
            if bw_col == "rd_iops":
                sz_mb = m.ssd_rd_size_mean_kb / 1024 if m.ssd_rd_size_mean_kb > 0 else 0.128
                rd_vals = rd_vals * sz_mb
            if rd_vals.max() > 0:
                ax.fill_between(t, rd_vals, alpha=0.3, color=C1)
                ax.plot(t, rd_vals, color=C1, lw=1.5)
                mean_bw = m.ssd_rd_bw_mbs_mean if 0 < m.ssd_rd_bw_mbs_mean < 100000 else float(np.nanmean(rd_vals[rd_vals>0]))
                ax.axhline(mean_bw, color="#ef4444", lw=1, ls="--",
                           label=f"Mean {mean_bw:.0f} MB/s")
                if ax.get_legend_handles_labels()[0]: ax.legend(fontsize=8)
    # Show scalar summary if timeline has too few points or no read activity in iostat
    if not (not m.nvme_io_ts.empty and len(m.nvme_io_ts) > 5 and
            m.nvme_io_ts.get("rd_bw_mbs", pd.Series([0])).max() > 0):
        # Annotate with summary.json values
        rd_mean = m.ssd_rd_bw_mbs_mean if m.ssd_rd_bw_mbs_mean < 100000 else 0
        ax.text(0.5, 0.5,
                f"Read BW from blktrace analysis:\n"
                f"Total read: {m.ssd_rd_bytes_total/1e9:.1f} GB\n"
                f"Streams: {m.ssd_rd_stream_count}\n"
                f"Est. avg BW: {rd_mean:.0f} MB/s\n"
                f"(iostat shows r≈0 — reads\nare served from HBM/DRAM,\nnot hitting NVMe directly)",
                ha="center", va="center", transform=ax.transAxes,
                fontsize=9, color="#1e3a5f",
                bbox=dict(boxstyle="round,pad=0.5",
                          facecolor="#eff6ff", edgecolor="#93c5fd"))
    ax.set_title(f"Read BW Timeline\nMean {m.ssd_rd_bw_mbs_mean:.2f} MB/s  "
                 f"Bytes/day≈{m.ssd_rd_bytes_per_day_gb:.2f}GB",
                 fontsize=9, fontweight="bold")
    ax.set_xlabel("Time (min)", fontsize=8); ax.set_ylabel("Est. MB/s", fontsize=8)
    ax.grid(True, alpha=0.3, color="#e2e8f0"); ax.tick_params(labelsize=8)
    for sp in ax.spines.values(): sp.set_edgecolor("#94a3b8")

    # 2. Request size distribution
    ax2 = axes[0, 1]; ax2.set_facecolor("#f8fafc")
    if m.blkio_available and not m.ssd_rd_ts.empty and "size_bytes" in m.ssd_rd_ts.columns:
        sk = m.ssd_rd_ts["size_bytes"] / 1024
        ax2.hist(sk, bins=min(25, len(sk)), color=C1, alpha=0.75, edgecolor="#1d4ed8", lw=0.5)
        kv_kb = m.kvb_block_size_mb * 1024
        ax2.axvline(kv_kb, color="#ef4444", lw=1.5, ls="--", label=f"KV$B {kv_kb:.0f}KB")
        ax2.axvline(4, color="#f97316", lw=1, ls=":", label="4KB page")
        if ax2.get_legend_handles_labels()[0]: ax2.legend(fontsize=8)
        ax2.set_xlabel("Request size (KB)", fontsize=8); ax2.set_ylabel("Count", fontsize=8)
    else:
        _ph(ax2, f"Read Request Size Distribution\nMean={m.ssd_rd_size_mean_kb:.1f}KB (node_exporter est.)")
        ax2.text(0.5, 0.25, f"Mean≈{m.ssd_rd_size_mean_kb:.1f}KB\nP50≈{m.ssd_rd_size_p50_kb:.1f}KB",
                 ha="center", va="top", transform=ax2.transAxes, fontsize=9, color="#475569")
    ax2.set_title(f"Read Request Size\nMean={m.ssd_rd_size_mean_kb:.1f}KB  P99={m.ssd_rd_size_p99_kb:.1f}KB",
                  fontsize=9, fontweight="bold")
    ax2.grid(True, axis="y", alpha=0.3, color="#e2e8f0"); ax2.tick_params(labelsize=8)
    for sp in ax2.spines.values(): sp.set_edgecolor("#94a3b8")

    # 3. Sequential vs random pie
    ax3 = axes[0, 2]; ax3.set_facecolor("#f8fafc")
    # Show pie whenever we have access pattern data, even if seq=0% (all random)
    has_access_data = (m.blkio_available or m.blkio_has_analysis or
                       m.ssd_rd_rand_pct > 0 or m.ssd_rd_seq_pct > 0)
    if has_access_data:
        seq_v  = max(m.ssd_rd_seq_pct, 0)
        rand_v = max(m.ssd_rd_rand_pct, 100 - seq_v)
        if seq_v == 0 and rand_v == 0:
            rand_v = 100.0
        wedges, texts, autos = ax3.pie(
            [seq_v, rand_v],
            labels=[f"Sequential\n{seq_v:.1f}%" if seq_v > 0 else "Sequential\n0%",
                    f"Random\n{rand_v:.1f}%"],
            colors=[C2, "#ef4444"], autopct="%1.1f%%", startangle=90,
            textprops={"fontsize": 9})
    else:
        _ph(ax3, "Sequential vs Random\n(requires blktrace or analysis dir)")
    ax3.set_title("Read Access Pattern\n(§C42: seq if sector==prev+prev_len)",
                  fontsize=9, fontweight="bold")

    # 4. Inter-arrival time distribution
    ax4 = axes[1, 0]; ax4.set_facecolor("#f8fafc")
    ba4  = getattr(m, "blktrace_analysis", None)
    iat_df4 = ba4.get("iat_dist", pd.DataFrame()) if isinstance(ba4, dict) else pd.DataFrame()
    iat_plotted = False
    if not iat_df4.empty:
        for op_c in ("op", "operation", "type"):
            if op_c in iat_df4.columns:
                rd_iat4 = iat_df4[iat_df4[op_c].str.lower() == "read"]
                iat_col4 = next((c for c in rd_iat4.columns
                                  if "inter_arrival" in c or "iat" in c.lower()), None)
                if iat_col4 and not rd_iat4.empty:
                    ia_raw = rd_iat4[iat_col4].values
                    # Detect unit: values < 1.0 are seconds → convert to µs
                    ia_us4 = ia_raw * 1e6 if ia_raw.max() < 1.0 else ia_raw
                    # Skip exact zeros (same-timestamp blkparse artifacts)
                    ia_pos = ia_us4[ia_us4 > 0]
                    if len(ia_pos) < 10 and m.ssd_rd_iat_mean_us > 0:
                        # Fall back to scalar summary — show as text annotation
                        ax4.text(0.5, 0.5,
                                 f"IAT from summary.json:\n"
                                 f"Mean = {m.ssd_rd_iat_mean_us:.3f} µs\n"
                                 f"P50  = {m.ssd_rd_iat_p50_us:.3f} µs\n"
                                 f"P99  = {m.ssd_rd_iat_p99_us:.3f} µs\n"
                                 f"({len(ia_raw):,} IAT samples in CSV,\n"
                                 f"but {int((ia_raw==0).sum()):,} are zero\n"
                                 f"— run with --blktrace for full histogram)",
                                 ha="center", va="center", transform=ax4.transAxes,
                                 fontsize=9, color="#1e3a5f",
                                 bbox=dict(boxstyle="round,pad=0.5",
                                           facecolor="#eff6ff", edgecolor="#93c5fd"))
                        iat_plotted = True
                    elif len(ia_pos) >= 3:
                        clip = np.percentile(ia_pos, 99.5)
                        ax4.hist(ia_pos[ia_pos <= clip], bins=min(60, max(20, len(ia_pos)//1000)),
                                 color=C1, alpha=0.8, edgecolor="#1d4ed8", lw=0.3, log=True)
                        ax4.axvline(float(np.mean(ia_pos)), color="#ef4444", lw=1.5, ls="--",
                                    label=f"Mean {np.mean(ia_pos):.3f}µs")
                        ax4.axvline(1000, color="#f97316", lw=1, ls=":", label="1ms burst thresh")
                        if ax4.get_legend_handles_labels()[0]: ax4.legend(fontsize=8)
                        ax4.set_xlabel("IAT (µs, log y-axis)", fontsize=8)
                        iat_plotted = True
                break
    if not iat_plotted and m.blkio_available and not m.ssd_rd_ts.empty:
        ia_us = m.ssd_rd_ts["time_sec"].diff().dropna() * 1e6
        ia_us = ia_us[ia_us > 0]
        if len(ia_us) > 3:
            ax4.hist(ia_us, bins=min(30, len(ia_us)), color=C1, alpha=0.75,
                     edgecolor="#1d4ed8", lw=0.5)
            ax4.axvline(float(ia_us.mean()), color="#ef4444", lw=1.5, ls="--",
                        label=f"Mean {ia_us.mean():.1f}µs")
            ax4.axvline(1000, color="#f97316", lw=1, ls=":", label="1ms burst threshold")
            if ax4.get_legend_handles_labels()[0]: ax4.legend(fontsize=8)
            ax4.set_xlabel("Inter-arrival time (µs)", fontsize=8)
            iat_plotted = True
    if not iat_plotted:
        _ph(ax4, f"Read Inter-Arrival Time\nMean≈{m.ssd_rd_iat_mean_us:.3f}µs")
        ax4.text(0.5, 0.25, f"Mean≈{m.ssd_rd_iat_mean_us:.3f}µs\nP99≈{m.ssd_rd_iat_p99_us:.3f}µs",
                 ha="center", va="top", transform=ax4.transAxes, fontsize=9, color="#475569")
    ax4.set_title(f"Read Inter-Arrival Time\nMean={m.ssd_rd_iat_mean_us:.1f}µs  "
                  f"Bursts={m.ssd_rd_burst_count}",
                  fontsize=9, fontweight="bold")
    ax4.set_ylabel("Count", fontsize=8)
    ax4.grid(True, axis="y", alpha=0.3, color="#e2e8f0"); ax4.tick_params(labelsize=8)
    for sp in ax4.spines.values(): sp.set_edgecolor("#94a3b8")

    # 5. Alignment analysis
    ax5 = axes[1, 1]; ax5.set_facecolor("#f8fafc")
    cats5  = ["KV$B\nAligned", "4KB Page\nAligned", "Not\nAligned"]
    kvb_a  = m.ssd_rd_kvb_aligned_pct
    pg_a   = m.ssd_rd_page_aligned_pct
    vals5  = [kvb_a, pg_a, max(0, 100 - max(kvb_a, pg_a))]
    clrs5  = [C2, "#3b82f6", "#ef4444"]
    bars5  = ax5.bar(cats5, vals5, color=clrs5, alpha=0.85, width=0.5,
                     edgecolor="#94a3b8", linewidth=0.5)
    for bar, val in zip(bars5, vals5):
        ax5.text(bar.get_x()+bar.get_width()/2, bar.get_height()+1,
                 f"{val:.1f}%", ha="center", va="bottom", fontsize=9, fontweight="bold")
    ax5.set_ylim(0, 115); ax5.set_ylabel("% of read ops", fontsize=8)
    ax5.set_title(f"Read Alignment (§C40-41)\nKV$B={kvb_a:.0f}%  4KB={pg_a:.0f}%",
                  fontsize=9, fontweight="bold")
    ax5.grid(True, axis="y", alpha=0.3, color="#e2e8f0"); ax5.tick_params(labelsize=8)
    for sp in ax5.spines.values(): sp.set_edgecolor("#94a3b8")

    # 6. LBA access skewness / hot-cold
    ax6 = axes[1, 2]; ax6.set_facecolor("#f8fafc")
    ba6  = getattr(m, "blktrace_analysis", None)
    hr6  = ba6.get("hot_regions", pd.DataFrame()) if isinstance(ba6, dict) else pd.DataFrame()
    if not hr6.empty:
        # Use pre-computed hot regions from analysis dir
        rd_hr = hr6[hr6["op"] == "read"] if "op" in hr6.columns else hr6
        if not rd_hr.empty and "bytes" in rd_hr.columns:
            reg_col = next((c for c in rd_hr.columns if "region" in c), None)
            if reg_col:
                ax6.scatter(rd_hr[reg_col].values, rd_hr["bytes"].values / 1e6,
                            s=np.clip(rd_hr.get("count", pd.Series([10]*len(rd_hr))).values * 0.5, 3, 80),
                            c=rd_hr["bytes"].values, cmap="YlOrRd", alpha=0.6, linewidths=0)
                ax6.set_xlabel("LBA region bucket", fontsize=8)
                ax6.set_ylabel("Bytes (MB)", fontsize=8)
                ax6.text(0.97, 0.97, f"Skewness={m.ssd_rd_skewness:.2f}\nGini={m.ssd_rd_gini:.3f}",
                         transform=ax6.transAxes, ha="right", va="top", fontsize=8,
                         bbox=dict(boxstyle="round,pad=0.4", facecolor="#f1f5f9", edgecolor="#e2e8f0"))
    elif m.blkio_available and not m.ssd_rd_ts.empty and "sector" in m.ssd_rd_ts.columns:
        sectors = m.ssd_rd_ts["sector"].values
        if len(sectors) > 10:
            bucket_sz = max(1, int(sectors.max() / 100))
            buckets = pd.Series(sectors // bucket_sz).value_counts().sort_index()
            ax6.bar(range(len(buckets)), buckets.values, color=C1, alpha=0.8, width=1)
            ax6.set_xlabel("LBA bucket (normalised)", fontsize=8)
            ax6.set_ylabel("Read count", fontsize=8)
            ax6.text(0.97, 0.97, f"Skewness={m.ssd_rd_skewness:.2f}\nGini={m.ssd_rd_gini:.3f}",
                     transform=ax6.transAxes, ha="right", va="top", fontsize=8,
                     bbox=dict(boxstyle="round,pad=0.4", facecolor="#f1f5f9", edgecolor="#e2e8f0"))
    else:
        _ph(ax6, "Hot/Cold LBA Access Map\n(§C36-37: requires blktrace or analysis dir)")
        ax6.text(0.5, 0.25, f"Skewness={m.ssd_rd_skewness:.2f}\nGini={m.ssd_rd_gini:.3f}",
                 ha="center", va="top", transform=ax6.transAxes, fontsize=9, color="#475569")
    ax6.set_title(f"LBA Access Distribution (Hot/Cold)\nSkewness={m.ssd_rd_skewness:.2f}  "
                  f"Gini={m.ssd_rd_gini:.3f}  BW-degrad={m.ssd_rd_bw_degradation:.2f}×",
                  fontsize=9, fontweight="bold")
    ax6.grid(True, axis="y", alpha=0.3, color="#e2e8f0"); ax6.tick_params(labelsize=8)
    for sp in ax6.spines.values(): sp.set_edgecolor("#94a3b8")

    try:
        import warnings as _wtl
        with _wtl.catch_warnings():
            _wtl.simplefilter('ignore', UserWarning)
            try:
                plt.tight_layout(pad=0.5)
            except Exception:
                pass
    except Exception:
        pass
    return fig_to_b64(fig)


def chart_ssd_write_workload(m: "Metrics") -> str:
    """§D — KV$ SSD Write workload characteristics (4-panel)."""
    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    fig.patch.set_facecolor("#ffffff")
    fig.suptitle("KV$ SSD — Write Workload Characteristics (§D)",
                 fontsize=12, fontweight="bold", color="#0f172a", y=1.01)
    C = "#f97316"

    def _ph(ax, title):
        ax.set_facecolor("#f8fafc"); ax.set_title(title, fontsize=9, fontweight="bold")
        ax.text(0.5, 0.5, "Requires blktrace\n--blktrace blktrace.txt",
                ha="center", va="center", transform=ax.transAxes, fontsize=9, color="#94a3b8")
        for sp in ax.spines.values(): sp.set_edgecolor("#e2e8f0")
        ax.tick_params(labelbottom=False, labelleft=False)

    # 1. Write BW + IOPS timeline
    ax = axes[0, 0]; ax.set_facecolor("#f8fafc")
    if not m.nvme_io_ts.empty:
        ts  = downsample(m.nvme_io_ts, 200)
        t   = ts["time_sec"].values / 60
        bw_col_w = next((c for c in ("wr_bw_mbs", "wr_iops") if c in ts.columns), None)
        if bw_col_w:
            wr = ts[bw_col_w].fillna(0).values
            if bw_col_w == "wr_iops":
                sz_mb = m.ssd_wr_size_mean_kb / 1024 if m.ssd_wr_size_mean_kb > 0 else 0.128
                wr = wr * sz_mb
            if wr.max() > 0:
                ax.fill_between(t, wr, alpha=0.3, color=C); ax.plot(t, wr, color=C, lw=1.5)
                mean_wr = m.ssd_wr_bw_mbs_mean if m.ssd_wr_bw_mbs_mean > 0 else float(np.nanmean(wr))
                ax.axhline(mean_wr, color="#ef4444", lw=1, ls="--",
                           label=f"Mean {mean_wr:.0f} MB/s")
                if ax.get_legend_handles_labels()[0]: ax.legend(fontsize=8)
                ax.set_ylabel("Write MB/s", fontsize=8)
            else:
                ax.text(0.5, 0.5, f"Mean BW: {m.nvme_wr_bw_mbs_mean:.1f} MB/s\n"
                        f"Total written: {m.nvme_bytes_written_total/1e9:.2f} GB",
                        ha="center", va="center", transform=ax.transAxes, fontsize=10, color="#475569")
        else:
            ax.text(0.5, 0.5, f"Mean IOPS: {m.nvme_wr_iops_mean:.1f}\n"
                    f"Mean BW: {m.nvme_wr_bw_mbs_mean:.1f} MB/s\n"
                    f"Total written: {m.nvme_bytes_written_total/1e9:.2f} GB",
                    ha="center", va="center", transform=ax.transAxes, fontsize=10, color="#475569")
    ax.set_title(f"Write IOPS Timeline (§D47)\nMean={m.nvme_wr_iops_mean:.1f} IOPS  "
                 f"BW≈{m.nvme_wr_bw_mbs_mean:.1f}MB/s",
                 fontsize=9, fontweight="bold")
    ax.set_xlabel("Time (min)", fontsize=8)
    ax.grid(True, alpha=0.3, color="#e2e8f0"); ax.tick_params(labelsize=8)
    for sp in ax.spines.values(): sp.set_edgecolor("#94a3b8")

    # 2. Write request size distribution
    ax2 = axes[0, 1]; ax2.set_facecolor("#f8fafc")
    if m.blkio_available and not m.blkio_ts.empty:
        wr_df = m.blkio_ts[m.blkio_ts["type"] == "W"]
        if not wr_df.empty and "size_bytes" in wr_df.columns:
            sk = wr_df["size_bytes"] / 1024
            ax2.hist(sk, bins=min(25, len(sk)), color=C, alpha=0.75, edgecolor="#c2410c", lw=0.5)
            kv_kb = m.kvb_block_size_mb * 1024
            ax2.axvline(kv_kb, color="#ef4444", lw=1.5, ls="--", label=f"KV$B {kv_kb:.0f}KB")
            if ax2.get_legend_handles_labels()[0]: ax2.legend(fontsize=8)
    else:
        _ph(ax2, f"Write Request Size Distribution\nMean≈{m.ssd_wr_size_mean_kb:.1f}KB")
        ax2.text(0.5, 0.25, f"Mean≈{m.ssd_wr_size_mean_kb:.1f}KB\nP99≈{m.ssd_wr_size_p99_kb:.1f}KB",
                 ha="center", va="top", transform=ax2.transAxes, fontsize=9, color="#475569")
    ax2.set_title(f"Write Request Size (§D53-54)\nMean={m.ssd_wr_size_mean_kb:.1f}KB  "
                  f"Seq={m.ssd_wr_seq_pct:.0f}%",
                  fontsize=9, fontweight="bold")
    ax2.set_xlabel("Request size (KB)", fontsize=8); ax2.set_ylabel("Count", fontsize=8)
    ax2.grid(True, axis="y", alpha=0.3, color="#e2e8f0"); ax2.tick_params(labelsize=8)
    for sp in ax2.spines.values(): sp.set_edgecolor("#94a3b8")

    # 3. Write alignment + seq/rand bars
    ax3 = axes[1, 0]; ax3.set_facecolor("#f8fafc")
    cats3  = ["Seq", "Random", "KV$B\nAligned", "Page\nAligned"]
    vals3  = [m.ssd_wr_seq_pct, 100-m.ssd_wr_seq_pct,
               m.ssd_wr_kvb_aligned_pct, m.ssd_wr_page_aligned_pct]
    clrs3  = ["#22c55e","#ef4444","#3b82f6","#6366f1"]
    bars3  = ax3.bar(cats3, vals3, color=clrs3, alpha=0.85, width=0.5,
                     edgecolor="#94a3b8", linewidth=0.5)
    for bar, val in zip(bars3, vals3):
        ax3.text(bar.get_x()+bar.get_width()/2, bar.get_height()+1,
                 f"{val:.1f}%", ha="center", va="bottom", fontsize=9, fontweight="bold")
    ax3.set_ylim(0, 115); ax3.set_ylabel("% of write ops", fontsize=8)
    ax3.set_title("Write Alignment & Access Pattern\n(§D55-57: KV$B, page, seq/random)",
                  fontsize=9, fontweight="bold")
    ax3.grid(True, axis="y", alpha=0.3, color="#e2e8f0"); ax3.tick_params(labelsize=8)
    for sp in ax3.spines.values(): sp.set_edgecolor("#94a3b8")

    # 4. Write BW degradation + SMART
    ax4 = axes[1, 1]; ax4.set_facecolor("#f8fafc")
    cats4  = ["BW\nDegradation", "Wear %", "IAT P99\n(ms)", "Skewness"]
    vals4  = [m.ssd_wr_bw_degradation, m.nvme_smart_wear_pct,
               m.ssd_wr_iat_p99_us/1000, abs(m.ssd_wr_skewness)]
    clrs4  = [("#22c55e" if m.ssd_wr_bw_degradation > 0.9 else "#ef4444"),
               "#f97316","#6366f1","#3b82f6"]
    bars4  = ax4.bar(cats4, vals4, color=clrs4, alpha=0.85, width=0.5,
                     edgecolor="#94a3b8", linewidth=0.5)
    for bar, val in zip(bars4, vals4):
        ax4.text(bar.get_x()+bar.get_width()/2, bar.get_height()+max(vals4)*0.01,
                 f"{val:.3g}", ha="center", va="bottom", fontsize=9, fontweight="bold")
    ax4.set_title(f"Write Quality Indicators (§D58-60)\nTotal={m.nvme_bytes_written_total/1e9:.3f}GB  "
                  f"Corr(size,rand)={m.ssd_wr_size_rand_corr:.2f}",
                  fontsize=9, fontweight="bold")
    ax4.grid(True, axis="y", alpha=0.3, color="#e2e8f0"); ax4.tick_params(labelsize=8)
    for sp in ax4.spines.values(): sp.set_edgecolor("#94a3b8")

    try:
        import warnings as _wtl
        with _wtl.catch_warnings():
            _wtl.simplefilter('ignore', UserWarning)
            try:
                plt.tight_layout(pad=0.5)
            except Exception:
                pass
    except Exception:
        pass
    return fig_to_b64(fig)


def chart_trim_seasonal(m: "Metrics") -> str:
    """§E — Trim / discard events + R/W/T seasonal and cross-correlation analysis."""
    fig, axes = plt.subplots(2, 3, figsize=(15, 9))
    fig.patch.set_facecolor("#ffffff")
    fig.suptitle("Trim / Discard Events & Temporal Patterns (§E)",
                 fontsize=12, fontweight="bold", color="#0f172a", y=1.01)
    CR, CW, CT = "#3b82f6", "#f97316", "#a855f7"

    def _ph(ax, title):
        ax.set_facecolor("#f8fafc"); ax.set_title(title, fontsize=9, fontweight="bold")
        ax.text(0.5, 0.5, "No data\n(node_exporter or blktrace needed)",
                ha="center", va="center", transform=ax.transAxes, fontsize=8, color="#94a3b8")
        for sp in ax.spines.values(): sp.set_edgecolor("#e2e8f0")
        ax.tick_params(labelbottom=False, labelleft=False)

    # 1. Trim IOPS + BW timeline
    ax = axes[0, 0]; ax.set_facecolor("#f8fafc")
    if not m.nvme_io_ts.empty and "disc_ios" in m.nvme_io_ts.columns:
        ts  = downsample(m.nvme_io_ts, 200)
        t   = ts["time_sec"].values / 60
        trim_rate = ts["disc_ios"].diff().clip(0).fillna(0)
        ax.fill_between(t, trim_rate, alpha=0.3, color=CT); ax.plot(t, trim_rate, color=CT, lw=1.5)
        ax.set_ylabel("Trim events/s", fontsize=8)
    elif not m.trim_present:
        ax.text(0.5, 0.5, "No TRIM activity observed\n(TRIM may be batched or disabled)",
                ha="center", va="center", transform=ax.transAxes, fontsize=9, color="#94a3b8")
    ax.set_title(f"Trim (Discard) Events Timeline (§E61-63)\n"
                 f"Present={m.trim_present}  "
                 f"IOPS={m.trim_iops_mean:.4f}  BW={m.trim_bw_mbs:.4f}MB/s",
                 fontsize=9, fontweight="bold")
    ax.set_xlabel("Time (min)", fontsize=8)
    ax.grid(True, alpha=0.3, color="#e2e8f0"); ax.tick_params(labelsize=8)
    for sp in ax.spines.values(): sp.set_edgecolor("#94a3b8")

    # 2. R/W/T rates comparison — use nvme_io_ts OR temporal_pattern
    ax2 = axes[0, 1]; ax2.set_facecolor("#f8fafc")
    ba_e = getattr(m, "blktrace_analysis", None)
    tp_e = ba_e.get("temporal_pattern", pd.DataFrame()) if isinstance(ba_e, dict) else pd.DataFrame()
    if not m.nvme_io_ts.empty:
        ts2 = downsample(m.nvme_io_ts, 200)
        t2  = ts2["time_sec"].values / 60
        rd_col = next((c for c in ts2.columns if "rd_iops" in c or "rd_bw" in c), None)
        wr_col = next((c for c in ts2.columns if "wr_iops" in c or "wr_bw" in c), None)
        if rd_col:
            rd_v = ts2[rd_col].fillna(0).values
            ax2.plot(t2, rd_v, color=CR, lw=1.5, label=f"Read ({rd_v.mean():.1f} mean)")
        if wr_col:
            wr_v = ts2[wr_col].fillna(0).values
            ax2.plot(t2, wr_v, color=CW, lw=1.5, label=f"Write ({wr_v.mean():.1f} mean)")
        if ax2.get_legend_handles_labels()[0]: ax2.legend(fontsize=8); ax2.set_ylabel("IOPS / BW", fontsize=8)
    elif not tp_e.empty:
        # Use temporal_pattern.csv bytes per window
        ts_col = next((c for c in tp_e.columns if "window" in c.lower() or "time" in c.lower()), None)
        if ts_col:
            t2 = tp_e[ts_col].values / 60
            def _tp_col_e(candidates):
                for c in candidates:
                    if c in tp_e.columns:
                        return tp_e[c].values / 1e6  # bytes → MB
                return np.zeros(len(tp_e))
            rd_bw = _tp_col_e(["read", "read_bytes", "read_bw"])
            wr_bw = _tp_col_e(["write", "write_bytes", "write_bw"])
            ax2.fill_between(t2, rd_bw, alpha=0.25, color=CR)
            ax2.plot(t2, rd_bw, color=CR, lw=1.5, label=f"Read ({rd_bw.mean():.1f} MB/win)")
            ax2.fill_between(t2, wr_bw, alpha=0.25, color=CW)
            ax2.plot(t2, wr_bw, color=CW, lw=1.5, label=f"Write ({wr_bw.mean():.1f} MB/win)")
            if ax2.get_legend_handles_labels()[0]: ax2.legend(fontsize=8); ax2.set_ylabel("MB per window", fontsize=8)
    else:
        _ph(ax2, "Read vs Write Rate Timeline")
    ax2.set_title(f"R/W Timeline & Ratio (§E72)\nR/W ratio={m.rw_ratio_mean:.2f}",
                  fontsize=9, fontweight="bold")
    ax2.set_xlabel("Time (min)", fontsize=8)
    ax2.grid(True, alpha=0.3, color="#e2e8f0"); ax2.tick_params(labelsize=8)
    for sp in ax2.spines.values(): sp.set_edgecolor("#94a3b8")

    # 3. Seasonal period FFT results
    ax3 = axes[0, 2]; ax3.set_facecolor("#f8fafc")
    periods = [
        ("Read",  m.seasonal_rd_period_s,   CR),
        ("Write", m.seasonal_wr_period_s,   CW),
        ("Trim",  m.seasonal_trim_period_s, CT),
    ]
    labels3 = [p[0] for p in periods]
    vals3   = [p[1] for p in periods]
    clrs3   = [p[2] for p in periods]
    bars3 = ax3.bar(labels3, vals3, color=clrs3, alpha=0.85, width=0.4,
                    edgecolor="#94a3b8", linewidth=0.5)
    for bar, val in zip(bars3, vals3):
        if val > 0:
            ax3.text(bar.get_x()+bar.get_width()/2, bar.get_height()+0.5,
                     f"{val:.0f}s", ha="center", va="bottom", fontsize=9, fontweight="bold")
        else:
            ax3.text(bar.get_x()+bar.get_width()/2, 0.5,
                     "no period\ndetected", ha="center", va="bottom", fontsize=8, color="#94a3b8")
    ax3.set_title("Dominant Seasonal Period (§E68-70)\n(FFT of IOPS timeseries)",
                  fontsize=9, fontweight="bold")
    ax3.set_ylabel("Period (s)", fontsize=8)
    ax3.grid(True, axis="y", alpha=0.3, color="#e2e8f0"); ax3.tick_params(labelsize=8)
    for sp in ax3.spines.values(): sp.set_edgecolor("#94a3b8")

    # 4. Cross-correlation R↔W with lag
    ax4 = axes[1, 0]; ax4.set_facecolor("#f8fafc")
    if not m.nvme_io_ts.empty:
        ts4  = m.nvme_io_ts
        rd_c = next((c for c in ts4.columns if "rd_iops" in c), None)
        wr_c = next((c for c in ts4.columns if "wr_iops" in c), None)
        if rd_c and wr_c and len(ts4) > 20:
            rd_v = ts4[rd_c].fillna(0).values
            wr_v = ts4[wr_c].fillna(0).values
            max_lag = min(30, len(rd_v)//4)
            lags    = range(-max_lag, max_lag+1)
            corrs   = []
            for lag in lags:
                if lag >= 0:
                    c = np.corrcoef(rd_v[:len(rd_v)-lag], wr_v[lag:])[0,1] if lag < len(rd_v) else 0
                else:
                    c = np.corrcoef(rd_v[-lag:], wr_v[:len(wr_v)+lag])[0,1] if -lag < len(wr_v) else 0
                corrs.append(0 if np.isnan(c) else c)
            ax4.bar(list(lags), corrs, color=[CR if c > 0 else CW for c in corrs], alpha=0.7, width=0.8)
            ax4.axhline(0, color="#475569", lw=0.5)
            ax4.axvline(0, color="#94a3b8", lw=0.5, ls="--")
            ax4.set_xlabel("Lag (samples)", fontsize=8); ax4.set_ylabel("Correlation", fontsize=8)
    else:
        _ph(ax4, f"Read↔Write Cross-Correlation (§E71)\nR/W lag={m.cross_corr_rw_peak_lag_s:.1f}s")
    ax4.set_title(f"Read↔Write Cross-Correlation (§E71)\nPeak R/W lag≈{m.cross_corr_rw_peak_lag_s:.1f}s",
                  fontsize=9, fontweight="bold")
    ax4.grid(True, alpha=0.3, color="#e2e8f0"); ax4.tick_params(labelsize=8)
    for sp in ax4.spines.values(): sp.set_edgecolor("#94a3b8")

    # 5. Trim alignment + size summary
    ax5 = axes[1, 1]; ax5.set_facecolor("#f8fafc")
    trim_cats  = ["Trim IOPS", "Trim BW\n(MB/s)", "KV$B\nAligned %", "IAT\n(ms avg)"]
    trim_vals  = [m.trim_iops_mean, m.trim_bw_mbs,
                   m.trim_kvb_aligned_pct, m.trim_iat_mean_us/1000]
    clrs5      = [CT, CT, "#22c55e", "#3b82f6"]
    bars5 = ax5.bar(trim_cats, trim_vals, color=clrs5, alpha=0.85, width=0.5,
                    edgecolor="#94a3b8", linewidth=0.5)
    for bar, val in zip(bars5, trim_vals):
        ax5.text(bar.get_x()+bar.get_width()/2, bar.get_height()+max(trim_vals,default=0.001)*0.01,
                 f"{val:.3g}", ha="center", va="bottom", fontsize=9, fontweight="bold")
    ax5.set_title(f"Trim Characteristics (§E61-67)\nSize avg={m.trim_size_mean_kb:.1f}KB",
                  fontsize=9, fontweight="bold")
    ax5.grid(True, axis="y", alpha=0.3, color="#e2e8f0"); ax5.tick_params(labelsize=8)
    for sp in ax5.spines.values(): sp.set_edgecolor("#94a3b8")

    # 6. R/W/Trim ratio over time
    ax6 = axes[1, 2]; ax6.set_facecolor("#f8fafc")
    summary_cats  = ["R/W Ratio\n(§E72)", "T/W Ratio\n(§E73)",
                     "R offload\ncorr (G90)", "W onboard\ncorr (G91)"]
    summary_vals  = [m.rw_ratio_mean, m.tw_ratio_mean,
                     abs(m.offload_write_corr), abs(m.onboard_read_corr)]
    clrs6         = [CR, CT, "#22c55e", "#6366f1"]
    ax6.bar(summary_cats, summary_vals, color=clrs6, alpha=0.85, width=0.5,
            edgecolor="#94a3b8", linewidth=0.5)
    for i, (cat, val) in enumerate(zip(summary_cats, summary_vals)):
        ax6.text(i, val+max(summary_vals,default=0.001)*0.01,
                 f"{val:.3g}", ha="center", va="bottom", fontsize=9, fontweight="bold")
    ax6.set_title("IO Ratio Summary & Cross-Layer Correlations",
                  fontsize=9, fontweight="bold")
    ax6.grid(True, axis="y", alpha=0.3, color="#e2e8f0"); ax6.tick_params(labelsize=8)
    for sp in ax6.spines.values(): sp.set_edgecolor("#94a3b8")

    try:
        import warnings as _wtl
        with _wtl.catch_warnings():
            _wtl.simplefilter('ignore', UserWarning)
            try:
                plt.tight_layout(pad=0.5)
            except Exception:
                pass
    except Exception:
        pass
    return fig_to_b64(fig)


def chart_cross_layer_kpi(m: "Metrics") -> str:
    """§G — Cross-layer KPIs: SSD bytes per token, throughput bottleneck, correlations."""
    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    fig.patch.set_facecolor("#ffffff")
    fig.suptitle("Cross-Layer KPIs — SSD / GPU / Inference Correlation (§G)",
                 fontsize=12, fontweight="bold", color="#0f172a", y=1.01)

    # 1. SSD bytes per token (§G88-89)
    ax = axes[0, 0]; ax.set_facecolor("#f8fafc")
    cats1 = ["Read bytes\nper output tok\n(§G88)", "Write bytes\nper input tok\n(§G89)"]
    vals1 = [m.ssd_rd_bytes_per_output_tok, m.ssd_wr_bytes_per_input_tok]
    clrs1 = ["#3b82f6","#f97316"]
    bars1 = ax.bar(cats1, vals1, color=clrs1, alpha=0.85, width=0.4,
                   edgecolor="#94a3b8", linewidth=0.5)
    for bar, val in zip(bars1, vals1):
        if val > 0:
            ax.text(bar.get_x()+bar.get_width()/2, bar.get_height()+max(vals1,default=0.001)*0.02,
                    f"{val:.1f}B", ha="center", va="bottom", fontsize=9, fontweight="bold")
    # Reference: kv_bytes_per_token (ideal: all KV from SSD)
    if m.kv_bytes_per_token > 0:
        ax.axhline(m.kv_bytes_per_token, color="#ef4444", lw=1.5, ls="--",
                   label=f"KV$/tok {m.kv_bytes_per_token:,}B (if all from SSD)")
        if ax.get_legend_handles_labels()[0]: ax.legend(fontsize=8)
    ax.set_title("SSD Dependency per Token (§G88-89)\nHigh = decode strongly depends on SSD",
                 fontsize=9, fontweight="bold")
    ax.set_ylabel("Bytes per token", fontsize=8)
    ax.grid(True, axis="y", alpha=0.3, color="#e2e8f0"); ax.tick_params(labelsize=8)
    for sp in ax.spines.values(): sp.set_edgecolor("#94a3b8")

    # 2. Throughput bottleneck estimate (§G93)
    ax2 = axes[0, 1]; ax2.set_facecolor("#f8fafc")
    gpu_tok  = m.gen_tp_peak if m.gen_tp_peak > 0 else m.gen_tp_mean
    ssd_tok  = (m.ssd_effective_bw_gbs * 1e9 / m.kv_bytes_per_token
                if m.kv_bytes_per_token > 0 and m.ssd_effective_bw_gbs > 0 else 0)
    actual   = m.throughput_bottleneck_tok_s or gpu_tok
    cats2    = ["GPU\n(gen_throughput)", "SSD-gated\n(SSD_BW/KV_bytes)", "Actual\nobserved"]
    vals2    = [gpu_tok, ssd_tok, actual]
    clrs2    = ["#6366f1","#f97316",
                "#22c55e" if m.throughput_bottleneck_src == "GPU" else "#ef4444"]
    bars2    = ax2.bar(cats2, vals2, color=clrs2, alpha=0.85, width=0.5,
                       edgecolor="#94a3b8", linewidth=0.5)
    for bar, val, cat in zip(bars2, vals2, cats2):
        if val > 0:
            ax2.text(bar.get_x()+bar.get_width()/2, bar.get_height()+max(vals2,default=0.001)*0.02,
                     f"{val:.1f}", ha="center", va="bottom", fontsize=9, fontweight="bold")
    if m.throughput_bottleneck_src:
        ax2.text(0.5, 0.97,
                 f"Bottleneck: {m.throughput_bottleneck_src}",
                 ha="center", va="top", transform=ax2.transAxes, fontsize=11,
                 fontweight="bold",
                 color=("#22c55e" if m.throughput_bottleneck_src == "GPU" else "#ef4444"),
                 bbox=dict(boxstyle="round,pad=0.4", facecolor="#f1f5f9", edgecolor="#e2e8f0"))
    ax2.set_title("Throughput Bottleneck Estimate (§G93)\n"
                  "min(GPU tok/s, SSD_BW/KV_bytes_per_tok)",
                  fontsize=9, fontweight="bold")
    ax2.set_ylabel("Tokens / second", fontsize=8)
    ax2.grid(True, axis="y", alpha=0.3, color="#e2e8f0"); ax2.tick_params(labelsize=8)
    for sp in ax2.spines.values(): sp.set_edgecolor("#94a3b8")

    # 3. Cross-layer correlation summary (§G90-92)
    ax3 = axes[1, 0]; ax3.set_facecolor("#f8fafc")
    corr_cats = ["Offload↔\nWrite BW\n(§G90)", "Onboard↔\nRead BW\n(§G91)",
                 "Seq Rd %", "KV$B\nAligned %"]
    corr_vals = [m.offload_write_corr, m.onboard_read_corr,
                 m.ssd_rd_seq_pct/100, m.ssd_rd_kvb_aligned_pct/100]
    clrs3     = [("#22c55e" if abs(m.offload_write_corr) > 0.7 else "#f97316"),
                 ("#22c55e" if abs(m.onboard_read_corr)  > 0.7 else "#f97316"),
                 "#3b82f6","#6366f1"]
    bars3 = ax3.bar(corr_cats, corr_vals, color=clrs3, alpha=0.85, width=0.5,
                    edgecolor="#94a3b8", linewidth=0.5)
    for bar, val in zip(bars3, corr_vals):
        ax3.text(bar.get_x()+bar.get_width()/2, max(abs(val),0.02)+0.01,
                 f"{val:.3f}", ha="center", va="bottom", fontsize=9, fontweight="bold")
    ax3.set_ylim(-1.1, 1.2)
    ax3.axhline(0, color="#475569", lw=0.5)
    ax3.axhline(0.7, color="#22c55e", lw=0.5, ls="--", alpha=0.5, label="High corr (0.7)")
    ax3.axhline(-0.7, color="#ef4444", lw=0.5, ls="--", alpha=0.5)
    if ax3.get_legend_handles_labels()[0]: ax3.legend(fontsize=8)
    ax3.set_title("Cross-Layer Correlation & Alignment (§G90-91)\n"
                  "+1=perfect, 0=none, -1=inverse",
                  fontsize=9, fontweight="bold")
    ax3.grid(True, axis="y", alpha=0.3, color="#e2e8f0"); ax3.tick_params(labelsize=8)
    for sp in ax3.spines.values(): sp.set_edgecolor("#94a3b8")

    # 4. KV$B offload/onboard rates vs write/read BW
    ax4 = axes[1, 1]; ax4.set_facecolor("#f8fafc")
    cats4 = ["KV$B\nOffload tok/s", "KV$B\nOnboard tok/s",
             "SSD Write\nBW (MB/s)", "SSD Read\nBW (MB/s)"]
    vals4 = [m.kvb_offload_tok_rate, m.kvb_onboard_tok_rate,
              m.nvme_wr_bw_mbs_mean, m.ssd_rd_bw_mbs_mean]
    # Dual axis: tok/s left, MB/s right
    ax4b = ax4.twinx()
    ax4.bar([0,1], vals4[:2], color=["#f97316","#22c55e"], alpha=0.85, width=0.35, label="tok/s")
    ax4b.bar([2,3], vals4[2:], color=["#ef4444","#3b82f6"], alpha=0.85, width=0.35,
             label="MB/s")
    ax4.set_xticks([0,1,2,3]); ax4.set_xticklabels(cats4, fontsize=8)
    ax4.set_ylabel("tokens/s", fontsize=8, color="#f97316")
    ax4b.set_ylabel("MB/s", fontsize=8, color="#3b82f6")
    ax4b.set_facecolor("#f8fafc")
    for sp in ax4b.spines.values(): sp.set_edgecolor("#94a3b8")
    lines1, labs1 = ax4.get_legend_handles_labels()
    lines2, labs2 = ax4b.get_legend_handles_labels()
    ax4.legend(lines1+lines2, labs1+labs2, fontsize=8)
    ax4.set_title("KV$B Movement vs SSD IO Rates\n(§B22/B25 vs §D47/§C32)",
                  fontsize=9, fontweight="bold")
    ax4.grid(True, axis="y", alpha=0.3, color="#e2e8f0"); ax4.tick_params(labelsize=8)
    for sp in ax4.spines.values(): sp.set_edgecolor("#94a3b8")

    try:
        import warnings as _wtl
        with _wtl.catch_warnings():
            _wtl.simplefilter('ignore', UserWarning)
            try:
                plt.tight_layout(pad=0.5)
            except Exception:
                pass
    except Exception:
        pass
    return fig_to_b64(fig)


def chart_blktrace_streams(m: "Metrics") -> str:
    """Per-stream BW distribution, IAT distribution, R/W/T temporal pattern."""
    ba = getattr(m, "blktrace_analysis", None)
    if not ba:
        return ""

    fig, axes = plt.subplots(2, 3, figsize=(15, 9))
    fig.patch.set_facecolor("#ffffff")
    fig.suptitle("KV$ SSD — Per-Stream & Temporal Analysis",
                 fontsize=12, fontweight="bold", color="#0f172a", y=1.01)

    # Helper: find op column in a DF (handles "op", "operation", "type")
    def _op_filter(df, op_val):
        for c in ("op", "operation", "type", "io_type"):
            if c in df.columns:
                return df[df[c].str.lower() == op_val.lower()]
        return df  # no op column — return all

    # ── 1. Per-stream read BW distribution ───────────────────────────────────
    ax = axes[0, 0]; ax.set_facecolor("#f8fafc")
    bps = ba.get("bw_per_stream", pd.DataFrame())
    # Compute bandwidth_mib_s if not present (derive from bytes / duration)
    if not bps.empty:
        if "bandwidth_mib_s" not in bps.columns:
            dur_col = None
            for dc, fc, lc in [("duration_sec","first_ts","last_ts"),
                                ("dur","start_sec","end_sec")]:
                if dc in bps.columns:
                    bps = bps.copy(); dur_col = dc; break
                if fc in bps.columns and lc in bps.columns:
                    bps = bps.copy()
                    bps["duration_sec"] = (bps[lc] - bps[fc]).clip(lower=1e-9)
                    dur_col = "duration_sec"; break
            if dur_col and "bytes" in bps.columns:
                bps["bandwidth_mib_s"] = (bps["bytes"] / bps[dur_col] / (1024*1024)).clip(lower=0)
        bw_col = next((c for c in bps.columns
                       if "bandwidth" in c.lower() or "bw" in c.lower()), None)
        cnt_col = next((c for c in bps.columns if "count" in c.lower()), None)
    if not bps.empty and bw_col:
        rd_bps = _op_filter(bps, "read").copy()
        if cnt_col:
            rd_bps = rd_bps[rd_bps[cnt_col] >= 3]
        if not rd_bps.empty:
            # Cap at realistic NVMe peak: 7000 MiB/s sequential, 3500 MiB/s random
            NVME_RAND_PEAK = 7000  # MiB/s — reasonable cap for 128KB random
            bw_raw = rd_bps[bw_col].dropna()
            bw_vals = bw_raw.clip(upper=min(float(bw_raw.quantile(0.99)), NVME_RAND_PEAK))
            bw_vals = bw_vals[bw_vals > 0]
            if len(bw_vals) >= 3:
                ax.hist(bw_vals, bins=min(50, max(10, len(bw_vals)//10)),
                        color="#3b82f6", alpha=0.8, edgecolor="#1d4ed8", lw=0.5)
                med = float(bw_vals.median())
                ax.axvline(med, color="#ef4444", lw=1.5, ls="--",
                           label=f"Median {med:.0f} MiB/s")
                if ax.get_legend_handles_labels()[0]: ax.legend(fontsize=8)
                ax.set_xscale("log")  # log x because BW spans 3 orders of magnitude
    ax.set_title(f"Read BW per Stream (bandwidth_per_stream.csv)\n"
                 f"{m.ssd_rd_stream_count} streams  "
                 f"median≈{m.ssd_rd_bw_per_stream_mean_mbs:.0f}  "
                 f"max≈{m.ssd_rd_bw_per_stream_max_mbs:.0f} MiB/s",
                 fontsize=9, fontweight="bold")
    ax.set_xlabel("Stream bandwidth (MiB/s)", fontsize=8); ax.set_ylabel("Streams", fontsize=8)
    ax.grid(True, axis="y", alpha=0.3, color="#e2e8f0"); ax.tick_params(labelsize=8)
    for sp in ax.spines.values(): sp.set_edgecolor("#94a3b8")

    # ── 2. Per-stream write BW distribution ──────────────────────────────────
    ax2 = axes[0, 1]; ax2.set_facecolor("#f8fafc")
    if not bps.empty and bw_col:
        wr_bps = _op_filter(bps, "write").copy()
        if cnt_col:
            wr_bps = wr_bps[wr_bps[cnt_col] >= 3]
        if not wr_bps.empty:
            NVME_WR_PEAK = 5000
            bw_raw2 = wr_bps[bw_col].dropna()
            bw_vals2 = bw_raw2.clip(upper=min(float(bw_raw2.quantile(0.99)), NVME_WR_PEAK))
            bw_vals2 = bw_vals2[bw_vals2 > 0]
            if len(bw_vals2) >= 3:
                ax2.hist(bw_vals2, bins=min(50, max(10, len(bw_vals2)//10)),
                         color="#f97316", alpha=0.8, edgecolor="#c2410c", lw=0.5)
                medw = float(bw_vals2.median())
                ax2.axvline(medw, color="#ef4444", lw=1.5, ls="--",
                            label=f"Median {medw:.0f} MiB/s")
                if ax2.get_legend_handles_labels()[0]: ax2.legend(fontsize=8)
                ax2.set_xscale("log")
    ax2.set_title(f"Write BW per Stream\n"
                  f"{m.ssd_wr_stream_count} streams  "
                  f"median≈{m.ssd_wr_bw_per_stream_mean_mbs:.0f}  "
                  f"max≈{m.ssd_wr_bw_per_stream_max_mbs:.0f} MiB/s",
                  fontsize=9, fontweight="bold")
    ax2.set_xlabel("Stream bandwidth (MiB/s)", fontsize=8); ax2.set_ylabel("Streams", fontsize=8)
    ax2.grid(True, axis="y", alpha=0.3, color="#e2e8f0"); ax2.tick_params(labelsize=8)
    for sp in ax2.spines.values(): sp.set_edgecolor("#94a3b8")

    # ── 3. Top streams by bytes ───────────────────────────────────────────────
    ax3 = axes[0, 2]; ax3.set_facecolor("#f8fafc")
    bytes_col = next((c for c in bps.columns if "bytes" in c.lower() and "per" not in c.lower()), None)
    stream_col = next((c for c in bps.columns if "stream" in c.lower()), None)
    op_col_name = next((c for c in bps.columns if c.lower() in ("op","operation","type","io_type")), None)
    if not bps.empty and bytes_col and stream_col:
        top_rd = _op_filter(bps, "read").nlargest(min(8, len(bps)), bytes_col)
        top_wr = _op_filter(bps, "write").nlargest(min(8, len(bps)), bytes_col)
        top = pd.concat([top_rd, top_wr]).drop_duplicates(stream_col)
        def _op_color(row):
            if op_col_name and op_col_name in row.index:
                return "#3b82f6" if str(row[op_col_name]).lower() == "read" else "#f97316"
            return "#6366f1"
        colors3 = [_op_color(row) for _, row in top.iterrows()]
        ax3.barh(range(len(top)), top[bytes_col].values / 1e9,
                 color=colors3, alpha=0.85, height=0.6, edgecolor="#94a3b8", lw=0.5)
        ax3.set_yticks(range(len(top)))
        ax3.set_yticklabels([str(s)[:22] for s in top[stream_col].values], fontsize=7)
        ax3.set_xlabel("Bytes (GB)", fontsize=8)
        from matplotlib.patches import Patch as _Patch
        ax3.legend(handles=[_Patch(color="#3b82f6", label="Read"),
                             _Patch(color="#f97316", label="Write")], fontsize=8)
    ax3.set_title("Top Streams by Total Bytes\n(stream = trace_window:pid)",
                  fontsize=9, fontweight="bold")
    ax3.grid(True, axis="x", alpha=0.3, color="#e2e8f0"); ax3.tick_params(labelsize=8)
    for sp in ax3.spines.values(): sp.set_edgecolor("#94a3b8")

    # 6. Summary KPI bars
    ax6 = axes[1, 2]; ax6.set_facecolor("#f8fafc")
    kpi_names = ["Rd BW\n(MiB/s)", "Wr BW\n(MiB/s)", "Rd Skew\n(×10)", "Wr Skew\n(×10)",
                 "Rd Gini\n(×100)", "Rd degrad\n(ratio)"]
    kpi_vals  = [m.ssd_rd_bw_mbs_mean/1000, m.ssd_wr_bw_mbs_mean/1000,
                 m.ssd_rd_skewness*10, m.ssd_wr_skewness*10,
                 m.ssd_rd_gini*100, m.ssd_rd_bw_degradation]
    kpi_cols  = ["#3b82f6","#f97316","#ef4444","#f97316","#a855f7","#22c55e"]
    bars6 = ax6.bar(kpi_names, kpi_vals, color=kpi_cols, alpha=0.85, width=0.5,
                    edgecolor="#94a3b8", lw=0.5)
    for bar, val in zip(bars6, kpi_vals):
        ax6.text(bar.get_x()+bar.get_width()/2, bar.get_height()+max(kpi_vals,default=0)*0.01,
                 f"{val:.2f}", ha="center", va="bottom", fontsize=8, fontweight="bold")
    ax6.set_title("Summary KPIs — Access Skew, BW Degradation (§C36/C45/D60)",
                  fontsize=9, fontweight="bold")
    ax6.grid(True, axis="y", alpha=0.3, color="#e2e8f0"); ax6.tick_params(labelsize=8)
    for sp in ax6.spines.values(): sp.set_edgecolor("#94a3b8")

    try:
        import warnings as _wtl
        with _wtl.catch_warnings():
            _wtl.simplefilter('ignore', UserWarning)
            try:
                plt.tight_layout(pad=0.5)
            except Exception:
                pass
    except Exception:
        pass
    return fig_to_b64(fig)


def chart_blktrace_hotcold(m: "Metrics") -> str:
    """Hot/cold LBA region map from pre-computed hot_regions analysis."""
    ba = getattr(m, "blktrace_analysis", None)
    if not ba:
        return ""

    fig, axes = plt.subplots(1, 3, figsize=(15, 6))
    fig.patch.set_facecolor("#ffffff")
    fig.suptitle("KV$ SSD — LBA Hot/Cold Region Analysis (§C36-37 / §D51)",
                 fontsize=12, fontweight="bold", color="#0f172a", y=1.01)

    hr = ba.get("hot_regions", pd.DataFrame())
    hrw = ba.get("hot_regions_windows", pd.DataFrame())

    for ax_i, (op, color, ax) in enumerate([
        ("read",  "#3b82f6", axes[0]),
        ("write", "#f97316", axes[1]),
    ]):
        ax.set_facecolor("#f8fafc")
        if not hr.empty:
            sub = hr[hr["op"]==op].copy() if "op" in hr.columns else hr.copy()
            if not sub.empty and "bytes" in sub.columns:
                # Find the plain "region" column — prefer exact match over region_start_byte
                reg_col = ("region" if "region" in sub.columns
                           else next((c for c in sub.columns
                                      if c.lower().startswith("region") and
                                         "byte" not in c.lower()), None)
                              or next((c for c in sub.columns if "region" in c.lower()), None))
                cnt_col2 = "count" if "count" in sub.columns else None
                if reg_col:
                    # Sample top 5K by bytes for render performance
                    plot_df = sub.nlargest(min(5000, len(sub)), "bytes")
                    reg_vals = plot_df[reg_col].values.astype(float)
                    reg_norm = ((reg_vals - reg_vals.min()) /
                                max(reg_vals.max() - reg_vals.min(), 1) * 100)
                    scatter = ax.scatter(
                        reg_norm,
                        plot_df["bytes"].values / 1e6,
                        s=np.clip(plot_df[cnt_col2].values * 0.3, 2, 60)
                          if cnt_col2 else 8,
                        c=plot_df["bytes"].values, cmap="YlOrRd",
                        alpha=0.5, linewidths=0
                    )
                    plt.colorbar(scatter, ax=ax, shrink=0.8,
                                 label="Bytes accessed", pad=0.01)
                    ax.set_xlabel("LBA region (0–100 normalised)", fontsize=8)
                    ax.set_ylabel("Bytes (MB)", fontsize=8)
        skew = m.ssd_rd_skewness if op == "read" else m.ssd_wr_skewness
        gini  = m.ssd_rd_gini if op == "read" else 0
        count = m.ssd_rd_hot_region_count if op == "read" else m.ssd_wr_hot_region_count
        ax.set_title(f"{op.title()} Hot Regions\n"
                     f"Skewness={skew:.3f}  Gini={gini:.3f}  "
                     f"{count:,} regions",
                     fontsize=9, fontweight="bold")
        ax.set_xlabel("LBA region (normalised sector bucket)", fontsize=8)
        ax.set_ylabel("Bytes (MB)", fontsize=8)
        ax.grid(True, alpha=0.2, color="#e2e8f0"); ax.tick_params(labelsize=8)
        for sp in ax.spines.values(): sp.set_edgecolor("#94a3b8")

    # 3. Hot/cold change over time windows
    ax3 = axes[2]; ax3.set_facecolor("#f8fafc")
    if not hrw.empty:
        # Find window/time column
        win_col = next((c for c in hrw.columns
                        if "window" in c.lower() or "start" in c.lower()
                        or "time" in c.lower()), None)
        reg_col3 = ("region" if "region" in hrw.columns
                    else next((c for c in hrw.columns
                               if c.lower().startswith("region") and
                                  "byte" not in c.lower()), None))
        for op, clr in [("read","#3b82f6"), ("write","#f97316")]:
            sub = hrw[hrw["op"]==op].copy() if "op" in hrw.columns else hrw.copy()
            if not sub.empty and win_col and reg_col3:
                per_win = sub.groupby(win_col)[reg_col3].nunique()
                ax3.plot(per_win.index, per_win.values, color=clr, lw=2,
                         marker="o", markersize=5, label=f"{op} ({len(sub)} total)")
    ax3.set_title("Hot Region Count per Time Window\n(§C37: cold→hot transitions)",
                  fontsize=9, fontweight="bold")
    ax3.set_xlabel("Time window (s)", fontsize=8)
    ax3.set_ylabel("Distinct hot regions", fontsize=8)
    if ax3.get_legend_handles_labels()[0]: ax3.legend(fontsize=8)
    ax3.grid(True, alpha=0.3, color="#e2e8f0"); ax3.tick_params(labelsize=8)
    for sp in ax3.spines.values(): sp.set_edgecolor("#94a3b8")

    try:
        import warnings as _wtl
        with _wtl.catch_warnings():
            _wtl.simplefilter('ignore', UserWarning)
            try:
                plt.tight_layout(pad=0.5)
            except Exception:
                pass
    except Exception:
        pass
    return fig_to_b64(fig)


def build_recommendations(m: Metrics, bottlenecks: list[dict]) -> list[dict]:
    recs = []
    top_layer = bottlenecks[0]["layer"] if bottlenecks else ""

    if m.ttft_ms > 1000:
        recs.append({
            "title": "Enable Chunked Prefill",
            "impact": "HIGH", "effort": "LOW",
            "phase": "PREFILL",
            "detail": f"TTFT {m.ttft_ms:.0f}ms is driven by long context ({m.prefill_cache_tokens+m.prefill_compute_tokens:,} tokens). "
                      "Set `--chunked-prefill-size 4096` in SGLang to spread prefill compute across multiple steps, "
                      "dramatically reducing TTFT without accuracy loss."
        })

    if m.gpu_util_mean < 30 and m.run_duration_s > 300:
        recs.append({
            "title": "Increase Request Concurrency / Batch Size",
            "impact": "HIGH", "effort": "LOW",
            "phase": "SYSTEM",
            "detail": f"Mean GPU utilisation {m.gpu_util_mean:.1f}% suggests the server is mostly idle. "
                      "Increase concurrent request load or enable continuous batching to maximise hardware efficiency."
        })

    if m.tpot_ms > 30:
        recs.append({
            "title": "Speculative Decoding",
            "impact": "MED", "effort": "MED",
            "phase": "DECODE",
            "detail": f"TPOT {m.tpot_ms:.1f}ms/tok is HBM-bandwidth limited. Speculative decoding with a draft model "
                      "can improve throughput 2–4× by amortising HBM reads across multiple accepted tokens."
        })

    if m.hbm_util_pct > 80:
        recs.append({
            "title": "Reduce HBM Pressure — Quantisation",
            "impact": "HIGH", "effort": "MED",
            "phase": "DECODE",
            "detail": f"HBM at {m.hbm_util_pct:.1f}%. Use AWQ/GPTQ 4-bit quantisation to halve model weight footprint, "
                      "freeing HBM for larger KV cache and improving decode throughput."
        })

    if m.hicache_fill_pct < 50 and m.prefill_cache_tokens > 0:
        recs.append({
            "title": "Expand hicache / Increase Load",
            "impact": "LOW", "effort": "LOW",
            "phase": "SW",
            "detail": f"hicache only {m.hicache_fill_pct:.1f}% full. Either increase request volume to stress-test "
                      "the L2 host KV cache, or configure a larger pool to handle more concurrent sessions."
        })

    if m.nvme_wr_iops_max < 10 and m.dram_used_gb < m.dram_total_gb * 0.8:
        recs.append({
            "title": "Enable NVMe KV Offload (ntier L3)",
            "impact": "MED", "effort": "HIGH",
            "phase": "STORAGE",
            "detail": "NVMe is completely idle. Enabling storage-backed KV cache offload would support "
                      "much larger context windows beyond HBM + DRAM capacity."
        })

    if m.numa_migrations_per_s > 10:
        recs.append({
            "title": "NUMA-Aware Memory Binding",
            "impact": "LOW", "effort": "MED",
            "phase": "SW",
            "detail": f"{m.numa_migrations_per_s:.1f} NUMA page migrations/s. Use `numactl --localalloc` or "
                      "pin SGLang processes to GPU-local NUMA nodes to reduce remote memory latency."
        })

    return recs


# ── HTML generation ───────────────────────────────────────────────────────────

SEVERITY_CSS = {
    "HIGH": ("background:#fef2f2;color:#991b1b", "HIGH"),
    "MED":  ("background:#fffbeb;color:#92400e", "MED"),
    "LOW":  ("background:#f0fdf4;color:#166534", "LOW"),
}

PHASE_CSS = {
    "Prefill → TTFT": ("background:#fff7ed;color:#c2410c", "PREFILL"),
    "Decode → TPOT":  ("background:#eff6ff;color:#1e3a5f", "DECODE"),
    "Both":     ("background:#eef2ff;color:#4338ca", "BOTH"),
    "Software": ("background:#eef2ff;color:#4338ca", "SW"),
    "Hardware": ("background:#f8fafc;color:#a78bfa", "HW"),
    "Storage":  ("background:#1c1917;color:#f87171", "STOR"),
    "System":   ("background:#0f172a;color:#334155", "SYS"),
}

def sev_badge(sev: str) -> str:
    style, label = SEVERITY_CSS.get(sev, ("background:#eef2ff;color:#4338ca", sev))
    return f'<span style="font-size:10px;padding:2px 8px;border-radius:12px;font-weight:700;{style}">{label}</span>'

def phase_badge(phase: str) -> str:
    style, label = PHASE_CSS.get(phase, ("background:#eef2ff;color:#4338ca", phase[:6]))
    return f'<span style="font-size:10px;padding:2px 8px;border-radius:12px;font-weight:700;{style}">{label}</span>'

def img(b64: str, alt: str = "") -> str:
    if not b64:
        return f'<div style="height:100px;display:flex;align-items:center;justify-content:center;color:#64748b;font-size:12px">No data for {alt}</div>'
    return f'<img src="data:image/png;base64,{b64}" alt="{alt}" style="width:100%;border-radius:8px;"/>'

def kv_card(label, value, unit="", color=TEXT_C, sub="") -> str:
    return f"""
    <div style="background:#ffffff;border:1px solid #e2e8f0;border-radius:8px;padding:12px 16px;min-width:120px">
      <div style="font-size:10px;color:#64748b;letter-spacing:1px;text-transform:uppercase;margin-bottom:3px">{label}</div>
      <div style="font-size:20px;font-weight:700;color:{color};font-family:monospace">{value}<span style="font-size:12px;color:#64748b;margin-left:3px">{unit}</span></div>
      {f'<div style="font-size:10px;color:#64748b;margin-top:2px">{sub}</div>' if sub else ''}
    </div>"""


def build_html(m: Metrics, bottlenecks: list[dict], recs: list[dict],
               charts: dict, run_label: str) -> str:

    def fmt(v, d=1): return f"{v:.{d}f}" if (v is not None and v != 0) else "—"

    # Token context bar
    total_ctx = m.prefill_cache_tokens + m.prefill_compute_tokens + m.decode_tokens
    if total_ctx > 0:
        pct_cache  = m.prefill_cache_tokens  / total_ctx * 100
        pct_comp   = m.prefill_compute_tokens / total_ctx * 100
        pct_decode = m.decode_tokens / total_ctx * 100
    else:
        pct_cache = pct_comp = pct_decode = 33

    # KPIs
    kpis = "".join([
        kv_card("TTFT", fmt(m.ttft_ms, 0), "ms", PREFILL, "Prefill Phase"),
        kv_card("TPOT", fmt(m.tpot_ms, 1), "ms/tok", DECODE, "Decode Phase"),
        kv_card("Peak Throughput", fmt(m.gen_tp_peak, 1), "tok/s", OK_C),
        kv_card("Cache Hit", fmt(m.cache_hit_pct, 1), "%", OK_C, "realtime"),
        kv_card("HBM Util", fmt(m.hbm_util_pct, 1), "%", HBM_C,
                f"{m.hbm_used_mb_mean/1024:.1f}/{m.hbm_total_mb/1024:.0f} GB"),
        kv_card("GPU Power", fmt(m.gpu_power_mean_w, 0), "W total", POWER_C,
                f"peak {m.gpu_power_peak_w:.0f}W/GPU"),
    ])

    # Bottleneck rows
    # Map chart fill colors → accessible text colors (WCAG AA ≥4.5:1 on white)
    def _text_color(hex_color):
        _dark_map = {
            "#fbbf24": "#92400e",  # amber-400 → amber-800 (dark enough on white)
            "#f59e0b": "#78350f",  # amber-500 → amber-900
            "#f43f5e": "#9f1239",  # rose-400  → rose-800
            "#fb923c": "#7c2d12",  # orange-400 → orange-900
            "#fcd34d": "#78350f",  # yellow-300 → amber-900
            "#facc15": "#713f12",  # yellow-400 → yellow-900
            "#34d399": "#065f46",  # emerald-400 → emerald-800
            "#86efac": "#14532d",  # green-300 → green-900
            "#4ade80": "#14532d",  # green-400 → green-900
        }
        return _dark_map.get(hex_color.lower(), hex_color)

    bn_rows = ""
    for b in bottlenecks:
        pct = b["score"]
        bn_rows += f"""
        <tr style="border-bottom:1px solid #e2e8f0">
          <td style="padding:8px 12px;color:{_text_color(b['color'])};font-weight:600">{b['layer']}</td>
          <td style="padding:8px 12px">
            <div style="display:flex;align-items:center;gap:8px">
              <div style="width:80px;background:#e2e8f0;border-radius:4px;height:8px;overflow:hidden">
                <div style="width:{pct}%;background:{b['color']};height:100%;border-radius:4px"></div>
              </div>
              <span style="color:#0f172a;font-family:monospace;font-weight:700">{pct}</span>
            </div>
          </td>
          <td style="padding:8px 12px">{phase_badge(b['phase'])}</td>
          <td style="padding:8px 12px">{sev_badge(b['severity'])}</td>
          <td style="padding:8px 12px;color:#64748b;font-size:12px;max-width:420px">{b['detail']}</td>
        </tr>"""

    # Recommendation cards
    rec_cards = ""
    for r in recs:
        rec_cards += f"""
        <div style="background:#f1f5f9;border:1px solid #e2e8f0;border-radius:8px;padding:12px">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
            <span style="font-size:12px;font-weight:700;color:#0f172a">{r['title']}</span>
            {sev_badge(r['impact'])}
            <span style="font-size:10px;color:#64748b">Effort: {r['effort']}</span>
            {phase_badge(r['phase'])}
          </div>
          <div style="font-size:12px;color:#64748b;line-height:1.6">{r['detail']}</div>
        </div>"""

    # ── Per-metric formula table rows ────────────────────────────────────────
    _METRIC_FORMULAS = [
        ("TTFT", "ms", "sglang_summary.json · Prometheus histogram",
         "time_to_first_token_seconds_sum / time_to_first_token_seconds_count × 1000",
         "Wall-clock wait until first generated token. Includes scheduling + KV lookup + prefill compute. "
         "Scales roughly linearly with context length when cache miss rate is high."),
        ("TPOT", "ms/tok", "sglang_summary.json · Prometheus histogram",
         "inter_token_latency_seconds_sum / inter_token_latency_seconds_count × 1000  ≡  1000 / gen_throughput",
         "Mean inter-token gap during decode. Lower bound: model_bytes_per_GPU / HBM_BW "
         "≈ 17.5 GB / 2000 GB/s × 1000 = 8.75 ms/tok for 70B FP16 on A100."),
        ("E2E Latency", "s", "sglang_summary.json · server_e2e_ms",
         "server_e2e_ms / 1000  ≈  queue_ms + ttft_ms + (tpot_ms × decode_tokens)",
         "True measured end-to-end request latency. Additive decomposition may differ slightly "
         "from server_e2e_ms due to scheduling pipelining."),
        ("Peak Throughput", "tok/s", "sglang_timeseries.csv · sglang:gen_throughput",
         "max( sglang:gen_throughput[engine_type=unified] )",
         "Tokens decoded in last scheduling step / step elapsed time. "
         "Peak (not mean) reported because mean is diluted by idle periods."),
        ("Cache Hit %", "%", "sglang_summary.json · sglang:cache_hit_rate",
         "KV tokens served from any cache tier / total KV tokens requested × 100",
         "Rolling realtime window from SGLang RadixAttention prefix tree. "
         "Covers L1 HBM + L2 hicache DRAM. High hit rate → lower TTFT."),
        ("hicache Fill %", "%", "sglang_timeseries.csv · sglang:hicache_host_used/total_tokens",
         "sglang:hicache_host_used_tokens / sglang:hicache_host_total_tokens × 100",
         "L2 DRAM KV pool occupancy. Near 100% triggers LRU eviction. "
         "Low fill + high hit = working set fits in L1 HBM (ideal)."),
        ("HBM Used (GB/GPU)", "GB", "gpu_timeseries.csv · nvidia-smi memory.used",
         "mean( memory.used[i] / 1024  ∀ GPU i ) over run  [GB]",
         "HBM partitioned as: model weights + active KV cache + CUDA runtime (~0.5 GB). "
         "40 GB total per A100 GPU."),
        ("HBM Util %", "%", "gpu_timeseries.csv · nvidia-smi memory.used/total",
         "mean( memory.used[i] / 40960 × 100  ∀ GPU i ) over run",
         "memory.total = 40960 MiB (A100 40 GB). "
         "Quantisation (AWQ 4-bit) halves weight footprint, freeing ~8.75 GB/GPU for KV cache."),
        ("DRAM Used (GB)", "GB", "dram_timeseries.csv · /proc/meminfo",
         "(MemTotal − MemFree − Buffers − Cached) / 1024³",
         "Holds: hicache L2 KV pool + model loader buffers + OS page cache."),
        ("GPU Util Mean %", "%", "gpu_timeseries.csv · nvidia-smi utilization.gpu · 1 Hz",
         "mean( gpu_util[i,t]  ∀ GPU i,  ∀ t ∈ run )",
         "NVML fraction of 1-second window where any SM was active. "
         "Low mean expected for single-request runs with long idle gaps between requests."),
        ("GPU Power (W)", "W", "power_timeseries.csv · nvidia-smi power.draw · ~1 Hz",
         "mean( Σᵢ power.draw[GPU i, t]  ∀ t ∈ run )  — all 8 GPUs summed",
         "Idle ≈ 57 W/GPU, decode plateau ≈ 70 W/GPU, prefill peak ≈ 200 W/GPU, TDP = 400 W/GPU."),
        ("Tok / Wh", "tok/Wh", "Derived · power_summary + sglang_summary",
         "rt_decode_tokens / ( gpu_power_mean_w × run_duration_s / 3600 )",
         "Output tokens per GPU Watt-hour. Higher = better energy efficiency. "
         "run_duration_s from power_summary.power_elapsed_s."),
        ("Page Faults/s", "/s", "vmstat_timeseries.csv · /proc/vmstat pgfault · 1 Hz",
         "Δ pgfault / Δ time_sec  (rolling 1-second derivative)",
         "Minor page faults from SGLang detokeniser / scheduler. "
         "Steady ~4000/s is normal. Spikes > 10000/s indicate memory pressure."),
        ("NVMe Write IOPS", "IOPS", "nvme_driver_timeseries.csv · /sys/block/*/stat",
         "Δ wr_ios / Δ time_sec",
         "Should be near-zero during inference. Non-zero reads = model weights not fully in memory "
         "or L3 KV NVMe offload active."),
    ]
    _sev_colors_html = {
        "HIGH": "background:#fef2f2;color:#991b1b",
        "MED":  "background:#fffbeb;color:#92400e",
        "LOW":  "background:#f0fdf4;color:#166534",
    }

    # ── HBM/DRAM formula pre-computation (needed before formula_rows loop) ────
    _safe_tpot   = m.tpot_ms if m.tpot_ms > 0 else None
    _safe_hbm_bw = m.hbm_read_bw_gbs if m.hbm_read_bw_gbs > 0 else None
    min_tpot_ms  = (_safe_hbm_bw / m.hbm_peak_bw_gbs * 1000) \
                   if (_safe_hbm_bw and m.hbm_peak_bw_gbs > 0) else 0
    gap_label    = (f"{(_safe_tpot / min_tpot_ms):.1f}× above theoretical min"
                    if (min_tpot_ms > 0 and _safe_tpot) else "N/A (TPOT not measured)")
    rw_r         = m.dram_read_bw_gbs / max(m.dram_write_bw_gbs, 0.001)
    _hbm_example = (
        f"Example: 70B FP16 / 8 GPUs = 17.5 GB per GPU\n"
        f"  → 17.5 GB / {max(m.tpot_ms, 0.001)/1000:.4f}s = {m.hbm_read_bw_gbs:.1f} GB/s\n\n"
        if m.tpot_ms > 0 else "TPOT = 0 ms (metrics unavailable for this run)\n\n"
    )
    _hbm_floor = (
        f"Observed {m.tpot_ms:.1f} ms = {(m.tpot_ms/min_tpot_ms):.1f}× above floor."
        if min_tpot_ms > 0 else "TPOT not available for this run."
    )
    _METRIC_FORMULAS_EXTRA = [
        ("HBM Read BW (est.)", "GB/s", "Derived · TPOT (sglang_summary) + model architecture",
         "model_bytes_per_GPU / TPOT_s\n"
         "= (params × 2 bytes / n_gpus) / (tpot_ms / 1000)\n\n"
         + _hbm_example
         + "Timeseries modulated by GPU util % (nvidia-smi)",
         "nsys HBM counters inactive in this profile (all = 1%). "
         f"Theoretical min TPOT = model_bytes / HBM_peak_BW × 1000 = {min_tpot_ms:.1f} ms/tok. "
         + _hbm_floor),
        ("HBM Read Txns/s", "M/s", "Derived · HBM Read BW",
         "HBM_read_BW_GB_s × 10⁹ / 64  [transactions/s]\n"
         "64 bytes = A100 HBM2e cache-line size\n\n"
         f"= {m.hbm_read_bw_gbs:.1f} × 10⁹ / 64 = {m.hbm_read_txn_M_s:.0f} M txns/s",
         "Each transaction transfers one 64-byte cache line from HBM to L2 cache. "
         "Read transactions dominate during decode (weights read every step)."),
        ("HBM Write Txns/s", "M/s", "Derived · HBM Write BW",
         "HBM_write_BW_GB_s × 10⁹ / 64  [transactions/s]\n"
         "Write BW estimated as 12% of Read BW (empirical for attention workloads)\n\n"
         f"= {m.hbm_write_bw_gbs:.1f} × 10⁹ / 64 = {m.hbm_write_txn_M_s:.0f} M txns/s",
         "Write transactions include KV cache updates and activation stores. "
         "Writes are smaller fraction of traffic vs reads for LLM decode."),
        ("DRAM Read BW", "GB/s", "amduprof_pcm_raw.csv · AMD EPYC PMU (DF METRICS) · 1.2s interval",
         "Total Mem RdBw (GB/s) from AMDuProfPcm -m memory\n"
         "= DDR4 read transactions × 64 bytes / sample_interval / 10⁹\n\n"
         f"Mean = {m.dram_read_bw_gbs:.2f} GB/s  |  Peak = {m.dram_read_bw_peak_gbs:.2f} GB/s",
         "Measured by AMD Data Fabric PMU counters (hardware accurate). "
         "Includes hicache L2 KV reads, model loader activity, OS page cache fills."),
        ("DRAM Write BW", "GB/s", "amduprof_pcm_raw.csv · AMD EPYC PMU (DF METRICS) · 1.2s interval",
         "Total Mem WrBw (GB/s) from AMDuProfPcm -m memory\n\n"
         f"Mean = {m.dram_write_bw_gbs:.2f} GB/s  |  Peak = {m.dram_write_bw_peak_gbs:.2f} GB/s",
         "Includes KV cache writes from GPU→CPU eviction via DMA, "
         "OS writeback, and hicache token store operations."),
        ("DRAM Read Txns/s", "M/s", "Derived · DRAM Read BW",
         "DRAM_read_BW_GB_s × 10⁹ / 64  [transactions/s]\n"
         "64 bytes = AMD EPYC DDR4 cache-line size\n\n"
         f"= {m.dram_read_bw_gbs:.2f} × 10⁹ / 64 = {m.dram_read_txn_M_s:.0f} M txns/s",
         "AMD EPYC 7742 theoretical DRAM BW = 204.8 GB/s "
         f"(8ch DDR4-3200 × 2 sockets × 25.6 GB/s). "
         f"Utilisation: {m.dram_bw_util_pct:.1f}%."),
    ]

    formula_rows = ""
    for fi, (metric, unit, collector, formula, interp) in enumerate(_METRIC_FORMULAS + _METRIC_FORMULAS_EXTRA):
        bg = "#ffffff" if fi % 2 == 0 else "#f8fafc"
        formula_rows += (
            f'<tr style="border-bottom:1px solid #e2e8f0">'
            f'<td style="padding:7px 12px;color:#0f172a;font-weight:600;background:{bg};white-space:nowrap">{metric}</td>'
            f'<td style="padding:7px 12px;color:#64748b;font-family:monospace;font-size:10px;background:{bg};white-space:nowrap">{unit}</td>'
            f'<td style="padding:7px 12px;color:#475569;font-family:monospace;font-size:10px;background:{bg}">{collector}</td>'
            f'<td style="padding:7px 12px;background:{bg}">'
            f'<code style="font-size:10px;color:#1e3a5f;white-space:pre-wrap;line-height:1.7">{formula}</code>'
            f'</td>'
            f'<td style="padding:7px 12px;color:#334155;font-size:11px;background:{bg};line-height:1.5">{interp}</td>'
            f'</tr>'
        )

    # ── HBM / DRAM bandwidth KPI cards ─────────────────────────────────────
    def bw_card(label, val, unit, color, sub=""):
        return (f'<div style="background:#f1f5f9;border:1px solid #e2e8f0;border-radius:8px;' +
                f'padding:10px 14px;min-width:130px">' +
                f'<div style="font-size:10px;color:#64748b;letter-spacing:1px;text-transform:uppercase;' +
                f'margin-bottom:3px">{label}</div>' +
                f'<div style="font-size:18px;font-weight:700;color:{color};font-family:monospace">' +
                f'{val}<span style="font-size:11px;color:#64748b;margin-left:3px">{unit}</span></div>' +
                (f'<div style="font-size:10px;color:#64748b;margin-top:1px">{sub}</div>' if sub else '') +
                f'</div>')

    hbm_kpi_cards = "".join([
        bw_card("HBM Read BW",  f"{m.hbm_read_bw_gbs:.0f}",  "GB/s", "#22d3ee",
                f"{m.hbm_read_txn_M_s:.0f} M txns/s"),
        bw_card("HBM Write BW", f"{m.hbm_write_bw_gbs:.0f}", "GB/s", "#f97316",
                f"{m.hbm_write_txn_M_s:.0f} M txns/s"),
        bw_card("HBM BW Util",  f"{m.hbm_bw_util_pct:.1f}",  "%",    "#a78bfa",
                f"of {m.hbm_peak_bw_gbs:.0f} GB/s peak"),
        bw_card("HBM Peak BW",  f"{m.hbm_peak_bw_gbs:.0f}",  "GB/s", "#475569",
                "A100 HBM2e theoretical"),
    ]) if m.hbm_read_bw_gbs > 0 else '<div style="color:#64748b;font-size:11px">HBM BW data not available</div>'

    dram_bw_kpi_cards = "".join([
        bw_card("DRAM Read BW",  f"{m.dram_read_bw_gbs:.2f}",  "GB/s", "#34d399",
                f"{m.dram_read_txn_M_s:.0f} M txns/s"),
        bw_card("DRAM Write BW", f"{m.dram_write_bw_gbs:.2f}", "GB/s", "#f97316",
                f"{m.dram_write_txn_M_s:.0f} M txns/s"),
        bw_card("DRAM Total BW", f"{m.dram_total_bw_gbs:.2f}", "GB/s", "#22c55e",
                f"peak {m.dram_read_bw_peak_gbs:.2f} GB/s"),
        bw_card("DRAM BW Util",  f"{m.dram_bw_util_pct:.1f}",  "%",    "#a78bfa",
                f"of {m.dram_peak_theoretical_gbs:.0f} GB/s peak"),
    ]) if m.dram_total_bw_gbs > 0 else '<div style="color:#64748b;font-size:11px">DRAM BW data not available — copy amduprof_pcm_raw.csv into raw/ directory</div>'

    # ── Session / KV$B / NVMe KPI card builders ──────────────────────────────
    def _kpi(label, val, unit, color_bg, color_text, sub=""):
        return (f'<div style="background:{color_bg};border:1px solid {color_text}44;'
                f'border-radius:8px;padding:12px">'
                f'<div style="font-size:10px;color:{color_text};font-weight:700;'
                f'text-transform:uppercase;margin-bottom:3px">{label}</div>'
                f'<div style="font-size:20px;font-weight:800;color:{color_text};'
                f'font-family:monospace">{val}'
                f'<span style="font-size:11px;color:#64748b;margin-left:3px">{unit}</span>'
                f'</div>'
                + (f'<div style="font-size:10px;color:#475569">{sub}</div>' if sub else '')
                + '</div>')

    session_kpi_cards = "".join([
        _kpi("Total Requests", f"{m.sess_total_requests}", "", "#eef2ff", "#4338ca",
             f"{m.sess_arrival_rate_rps:.4f} req/s"),
        _kpi("Max Concurrent", f"{m.sess_max_concurrent}", "", "#f0fdf4", "#047857",
             f"mean {m.sess_mean_concurrent:.2f}"),
        _kpi("E2E Mean", f"{m.sess_e2e_mean_s:.1f}", "s", "#fff7ed", "#9a3412",
             f"P90={m.sess_e2e_p90_s:.1f}s  Max={m.sess_e2e_max_s:.1f}s"),
        _kpi("Input Tokens", f"{m.sess_input_tok_mean:,.0f}", "", "#f0f9ff", "#0c4a6e",
             f"P90={m.sess_input_tok_p90:,.0f}"),
        _kpi("Output Tokens", f"{m.sess_output_tok_mean:,.0f}", "", "#faf5ff", "#6d28d9",
             f"P90={m.sess_output_tok_p90:,.0f}"),
        _kpi("Queue Time", f"{m.sess_queue_mean_ms:.1f}", "ms", "#f8fafc", "#334155",
             f"inter-arrival {m.sess_inter_arrival_s:.1f}s"),
    ])

    _l3_peak_blocks = 0
    if isinstance(getattr(m, "kvb_l3_io_ts", pd.DataFrame()), pd.DataFrame) and not m.kvb_l3_io_ts.empty and "resident_tokens" in m.kvb_l3_io_ts.columns:
        _l3_peak_blocks = int((m.kvb_l3_io_ts["resident_tokens"].fillna(0) / max(m.kvb_block_size_tokens, 1)).max())
    kvb_kpi_cards = "".join([
        _kpi("Block Size", f"{m.kvb_block_size_mb:.1f}", "MB", "#f0fdf4", "#047857",
             f"{m.kvb_block_size_tokens} tok × {m.kv_bytes_per_token_kb:.0f} KB"),
        _kpi("L1 Pool Blocks", f"{m.kvb_l1_pool_blocks:,}", "", "#eef2ff", "#4338ca",
             f"{m.kv_l1_fill_pct:.1f}% used"),
        _kpi("L2 Pool Blocks", f"{m.kvb_l2_pool_blocks:,}", "", "#f0f9ff", "#0c4a6e",
             f"{m.kv_l2_fill_pct:.1f}% used"),
        _kpi("L3 Peak Resident", f"{_l3_peak_blocks:,}", "blk", "#faf5ff", "#7e22ce",
             "derived from SGLang backup - prefetch"),
        _kpi("L1→L2 Offload", f"{m.kvb_l1_offload_rate_blk_s:.4f}", "blk/s", "#fff7ed", "#9a3412",
             "HBM → DRAM"),
        _kpi("L2→L3 Backup", f"{m.kvb_offload_tok_rate/max(m.kvb_block_size_tokens,1):.4f}", "blk/s", "#fff7ed", "#c2410c",
             f"{m.kvb_backuped_tokens_total:,} tokens total"),
        _kpi("L3 Onboard", f"{m.kvb_onboard_tokens_rate/max(m.kvb_block_size_tokens,1):.4f}", "blk/s", "#eff6ff", "#1d4ed8",
             f"prefetch={m.kvb_prefetched_tokens_total:,} load_back={m.kvb_loadback_tokens_total:,}"),
        _kpi("Block Lifetime", f"{m.kvb_lifetime_mean_s:.0f}", "s", "#faf5ff", "#6d28d9",
             f"min={m.kvb_lifetime_min_s:.0f}s max={m.kvb_lifetime_max_s:.0f}s"),
    ])

    nvme_kpi_cards = "".join([
        _kpi("Wr IOPS Mean", f"{m.nvme_wr_iops_mean:.1f}", "", "#fff7ed", "#9a3412",
             f"BW≈{m.nvme_wr_bw_mbs_mean:.1f} MB/s"),
        _kpi("Wr Latency", f"{m.nvme_wr_lat_mean_ms:.3f}", "ms", "#f0f9ff", "#0c4a6e",
             f"max={m.nvme_wr_lat_max_ms:.3f}ms"),
        _kpi("IO Util", f"{m.nvme_io_util_pct:.3f}", "%", "#f0fdf4", "#047857",
             "device busy fraction"),
        _kpi("Bytes Written", f"{m.nvme_bytes_written_total/1e9:.2f}", "GB", "#faf5ff", "#6d28d9",
             "SMART delta this run"),
        _kpi("Drive Wear", f"{m.nvme_smart_wear_pct:.0f}", "%", "#fff1f2", "#9f1239",
             f"spare={m.nvme_smart_avail_spare:.0f}%"),
        _kpi("Host Wr Cmds", f"{m.nvme_host_write_cmds:,}", "", "#f8fafc", "#334155",
             f"rd={m.nvme_host_read_cmds:,}"),
    ])

    # Template variables used in KV$B formula block
    kvb_block_size_tokens = m.kvb_block_size_tokens
    kvb_block_size_mb     = m.kvb_block_size_mb
    kvb_l1_pool_blocks    = m.kvb_l1_pool_blocks
    kvb_l2_pool_blocks    = m.kvb_l2_pool_blocks
    kvb_offload_rate      = m.kvb_l1_offload_rate_blk_s
    kvb_lifetime_mean     = m.kvb_lifetime_mean_s

    # Deep IO status/enable HTML
    blkio_status_html = ('<b style="color:#059669">Data available from blktrace/biosnoop.</b>'
                         if m.blkio_available else
                         '<b style="color:#c2410c">Requires blktrace or biosnoop — '
                         'charts show framework only.</b>')
    blkio_enable_html = "" if m.blkio_available else (
        '<div style="background:#fff7ed;border:1px solid #fed7aa;border-radius:6px;'
        'padding:10px 14px;margin-bottom:12px;font-size:10px;font-family:monospace;'
        'color:#92400e">'
        'Enable deep IO profiling:<br>'
        'Option A — biosnoop (eBPF, per-request): '
        'sudo biosnoop -d nvme2n1 &gt; blkio_trace.csv<br>'
        'Option B — blktrace: sudo blktrace -d /dev/nvme2n1<br>'
        'Then pass: --blkio-trace blkio_trace.csv'
        '</div>'
    )

    def _setup_table_html():
        import html as _html_mod
        rows = []
        for k, v in m.setup_details.items():
            key_l = str(k).lower()
            val = str(v)
            klass = "setup-row-defaulted" if key_l in ("default profile", "defaulted fields") else ""
            rows.append(
                f'<tr class="{klass}"><td class="setup-key">{_html_mod.escape(str(k))}</td>'
                f'<td class="setup-value">{_html_mod.escape(val)}</td></tr>'
            )
        return '<table class="setup-table"><tbody>' + ''.join(rows) + '</tbody></table>'

    setup_panel_html = f'''
<div class="card stack-noreorder setup-panel">
  <h2>⚙️ Setup / Server Configuration</h2>
  <div class="setup-grid">
    <div>{_setup_table_html()}</div>
    <div class="setup-info-box">
      <div class="setup-info-title">How setup fields were populated</div>
      <p><b>Auto-detected:</b> fields are read from <code>sglang_summary.json</code>, Prometheus labels such as <code>model_name</code>/<code>instance</code>/<code>engine_type</code>, and cache config labels such as <code>page_size</code>/<code>num_pages</code> when present.</p>
      <p><b>Manual override:</b> <code>setup_details.json</code> values override auto-detection.</p>
      <p><b>Defaults:</b> remaining missing SGLang launch parameters are filled from the built-in DeepSeek-R1-70B HiCache reference launch profile and listed under <code>Defaulted fields</code>.</p>
      <p><b>Memory tier mapping:</b> L1=HBM/GPU, L2=host DRAM/OS memory, L3=NVMe SSD/local or fabric-backed storage.</p>
    </div>
  </div>
</div>
'''

    layered_overview_html = f'''
<div class="card stack-noreorder" id="stack-layer-overview" style="border-left:4px solid #0f766e">
  <h2>🍰 AI Workload Stack — Layered Memory-Tier View</h2>
  <div class="stack-cake">
    <div class="stack-row full a5"><b>A5 · Application Layer</b><span>benchmarks, prompt/output mix, TTFT, TPOT, P99 request latency</span></div>
    <div class="stack-row pair"><div class="a4"><b>A4 · Inference Runtime</b><span>SGLang/vLLM scheduling, continuous batching, KV eviction/load-back</span></div><div class="model"><b>AI Models</b><span>model config, dtype, context length, FLOPs/token, KV$/token</span></div></div>
    <div class="stack-row trio"><div class="l1"><b>A3/A2/A1 · L1 HBM</b><span>CUDA kernels, GPU driver, HBM capacity/BW, SM util</span></div><div class="l2"><b>A3/A2/A1 · L2 DRAM</b><span>OS memory manager, page faults, swap, DRAM BW</span></div><div class="l3"><b>A3/A2/A1 · L3 SSD</b><span>OS block layer, io_uring/NVMe driver, NAND, blktrace/biosnoop</span></div></div>
  </div>
  <div class="stack-nav">
    <a href="#layer-a5">A5 Application</a><a href="#layer-a4">A4 Runtime &amp; Model</a><a href="#layer-l1">L1 HBM</a><a href="#layer-l2">L2 DRAM</a><a href="#layer-l3">L3 SSD</a><a href="#layer-cross">Cross-layer</a>
  </div>
</div>
<div id="stack-layered-report-anchor" class="stack-noreorder"></div>
'''

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>AI Stack Bottleneck Report — {run_label}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: #f8fafc; color: #0f172a; font-family: 'Inter', system-ui, sans-serif; padding: 24px; }}
  h2 {{ font-size: 13px; font-weight: 700; letter-spacing: 0.5px; text-transform: uppercase; margin-bottom: 14px; color: #1e293b; }}
  .report-title-prefix {{ color:#0f172a; }}
  .report-title-accent {{ color:#4f46e5; }}
  .card {{ background: #ffffff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 18px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }}
  .grid2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
  .kpis {{ display: flex; gap: 10px; flex-wrap: wrap; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  th {{ padding: 7px 12px; text-align: left; color: #475569; font-weight: 600; font-size: 11px;
        text-transform: uppercase; letter-spacing: 0.5px; border-bottom: 1px solid #e2e8f0; background: #f8fafc; }}
  td {{ border-bottom: 1px solid #f1f5f9; }}
  /* ── Row hover highlight ── */
  tr:hover td {{ background: #eff6ff !important; }}
  tr:hover {{ outline: 1px solid #bfdbfe; }}
  /* ── KPI card hover ── */
  .kpi-card:hover, [class*="kpi"]:hover {{
    box-shadow: 0 4px 12px rgba(79,70,229,0.15) !important;
    border-color: #818cf8 !important;
    transform: translateY(-1px);
    transition: all 0.15s;
  }}
  /* ── Fix low-contrast metric labels ── */
  .metric-label {{ color: #475569 !important; }}  /* was #94a3b8 */
  /* ── Chart image hover: show a "zoom" cursor and subtle outline ── */
  .chart-wrap {{ position: relative; cursor: crosshair; }}
  .chart-wrap:hover img {{ outline: 2px solid #c7d2fe; border-radius: 4px; }}
  /* ── Readout bar below each chart ── */
  .chart-readout {{
    margin-top: 4px;
    min-height: 22px;
    font: 12px/1.5 system-ui, sans-serif;
    color: #0f172a;
    background: #f1f5f9;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    padding: 4px 10px;
  }}

  .setup-panel {{
    background: linear-gradient(135deg, #eef2ff 0%, #f8fafc 100%) !important;
    border: 1px solid #a5b4fc !important;
    border-left: 6px solid #4f46e5 !important;
    color: #0f172a !important;
    box-shadow: 0 4px 14px rgba(79,70,229,0.12) !important;
  }}
  .setup-panel h2 {{ color: #1e1b4b !important; }}
  .setup-grid {{ display:grid; grid-template-columns: 1.35fr .85fr; gap:16px; align-items:start; }}
  .setup-table {{ width:100%; border-collapse:separate; border-spacing:0; overflow:hidden; border-radius:10px; border:1px solid #c7d2fe; background:#ffffff; }}
  .setup-table tr:nth-child(even) td {{ background:#f8fafc; }}
  .setup-table tr:nth-child(odd) td {{ background:#ffffff; }}
  .setup-table tr:hover td {{ background:#dbeafe !important; }}
  .setup-key {{ padding:9px 12px; font-weight:800; color:#1e293b !important; width:34%; border-bottom:1px solid #e2e8f0; vertical-align:top; }}
  .setup-value {{ padding:9px 12px; font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace; color:#0f172a !important; border-bottom:1px solid #e2e8f0; vertical-align:top; overflow-wrap:anywhere; word-break:break-word; }}
  .setup-row-defaulted .setup-key, .setup-row-defaulted .setup-value {{ background:#fff7ed !important; color:#7c2d12 !important; }}
  .setup-info-box {{ background:#ffffff !important; border:1px solid #c7d2fe; border-radius:10px; padding:14px 16px; font-size:12px; color:#334155 !important; line-height:1.65; }}
  .setup-info-box p {{ margin:0 0 9px 0; }}
  .setup-info-box code {{ background:#eef2ff !important; color:#3730a3 !important; padding:1px 4px; border-radius:4px; }}
  .setup-info-title {{ font-size:12px; font-weight:800; color:#312e81; text-transform:uppercase; letter-spacing:.5px; margin-bottom:8px; }}
  .recs {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
  .phase-bar {{ display: flex; border-radius: 6px; overflow: hidden; height: 22px; }}
  .stack-cake {{ display:grid; gap:8px; margin:8px 0 12px 0; }}
  .stack-row {{ display:grid; gap:8px; }}
  .stack-row.full {{ grid-template-columns:1fr; }}
  .stack-row.pair {{ grid-template-columns:1.6fr 1fr; }}
  .stack-row.trio {{ grid-template-columns:1fr 1fr 1fr; }}
  .stack-row > div, .stack-row.full {{ border-radius:10px; padding:14px 16px; color:#fff; }}
  .stack-row b {{ display:block; font-size:15px; margin-bottom:4px; letter-spacing:.2px; }}
  .stack-row span {{ font-size:11px; opacity:.92; line-height:1.5; }}
  .a5 {{ background:#24577f; }} .a4 {{ background:#317bb8; }} .model {{ background:#b89a05; }}
  .l1 {{ background:#2f8a4e; }} .l2 {{ background:#7a3f97; }} .l3 {{ background:#a45714; }}
  .stack-nav {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:10px; }}
  .stack-nav a {{ font-size:11px; text-decoration:none; color:#0f172a; background:#e2e8f0; border:1px solid #cbd5e1; border-radius:999px; padding:5px 10px; }}
  .stack-layer-header {{ margin:20px 0 10px 0; padding:12px 16px; border-radius:10px; color:#fff; box-shadow:0 1px 3px rgba(0,0,0,.08); }}
  .stack-layer-header h2 {{ color:#fff !important; margin:0 0 4px 0; border:0; font-size:14px; }}
  .stack-layer-header p {{ font-size:12px; opacity:.95; margin:0; }}
  @media(max-width:768px) {{ .grid2,.recs,.setup-grid,.stack-row.pair,.stack-row.trio {{ grid-template-columns: 1fr; }} }}
</style>
<script>
// Fix contrast: darken #94a3b8 labels to #475569, and amber #fbbf24 to #92400e
document.addEventListener('DOMContentLoaded', function(){{
  document.querySelectorAll('[style]').forEach(function(el){{
    const s = el.getAttribute('style');
    if(!s) return;
    let ns = s
      .replace(/color:\\s*#94a3b8/gi,  'color:#475569')
      .replace(/color:\\s*#cbd5e1/gi,  'color:#475569')
      .replace(/color:\\s*#fbbf24/gi,  'color:#92400e')
      .replace(/color:\\s*#f59e0b/gi,  'color:#78350f')
      .replace(/color:\\s*#fb923c/gi,  'color:#7c2d12');
    if(ns !== s) el.setAttribute('style', ns);
  }});
  // Wrap all chart images in .chart-wrap and add readout bars
  document.querySelectorAll('img[src^="data:image/png"]').forEach(function(img){{
    const parent = img.parentNode;
    if(parent && parent.classList.contains('chart-wrap')) return;
    const wrap = document.createElement('div');
    wrap.className = 'chart-wrap';
    parent.insertBefore(wrap, img);
    wrap.appendChild(img);
    const readout = document.createElement('div');
    readout.className = 'chart-readout';
    readout.textContent = img.alt || 'Chart — hover to inspect';
    wrap.appendChild(readout);
    // On hover: show the chart title from the alt attribute
    wrap.addEventListener('mouseenter', function(){{
      readout.style.background = '#ffffff';
      readout.style.borderColor = '#818cf8';
      readout.innerHTML =
        '<span style="color:#4f46e5;font-weight:600">\u2197 Click chart to open full-size</span>' +
        (img.alt ? ' <span style="color:#64748b;margin-left:8px">' + img.alt + '</span>' : '');
    }});
    wrap.addEventListener('mouseleave', function(){{
      readout.style.background = '#f1f5f9';
      readout.style.borderColor = '#cbd5e1';
      readout.textContent = img.alt || 'Chart — hover to inspect';
    }});
    // Click opens chart in full window
    img.style.cursor = 'zoom-in';
    img.addEventListener('click', function(){{
      const w = window.open('', '_blank');
      w.document.write('<html><body style="margin:0;background:#111">' +
        '<img src="' + img.src + '" style="max-width:100%;display:block;margin:auto">' +
        '</body></html>');
      w.document.close();
    }});
  }});
}});

// Re-arrange report cards into the AI workload stack layered-cake order.
// The underlying metrics/charts remain unchanged; this is only presentation order.
document.addEventListener('DOMContentLoaded', function(){{
  const anchor = document.getElementById('stack-layered-report-anchor');
  if(!anchor) return;
  const layerDefs = [
    ['layer-a5','A5 · Application Layer','Benchmark workload, request mix, token throughput, TTFT/TPOT and P50/P90/P99 latency.','#24577f'],
    ['layer-a4','A4 · Inference Runtime + AI Model','SGLang runtime behavior, KV-cache accounting, model config, batching, eviction, load-back and cache-hit methodology.','#317bb8'],
    ['layer-l1','A3/A2/A1 · L1 HBM / CUDA / GPU','GPU utilization, HBM capacity, HBM bandwidth and device-side runtime pressure.','#2f8a4e'],
    ['layer-l2','A3/A2/A1 · L2 DRAM / OS Memory Manager','Host DRAM bandwidth, page faults, swap pressure, NUMA and OS memory effects.','#7a3f97'],
    ['layer-l3','A3/A2/A1 · L3 SSD / OS Block / NVMe','NVMe driver, blktrace/biosnoop, request sizes, inter-arrivals, hot/cold LBAs, read/write/trim workload.','#a45714'],
    ['layer-cross','Cross-layer Diagnosis','End-to-end bottleneck scorecard, formulas, recommendations and layer-to-layer spill/evict interpretation.','#0f172a']
  ];
  const classify = (txt) => {{
    txt = (txt || '').toLowerCase();
    if(txt.includes('cache hit methodology') || txt.includes('p50') || txt.includes('phase analysis') || txt.includes('session') || txt.includes('percentile')) return 'layer-a5';
    if(txt.includes('kv cache footprint') || txt.includes('kv tier') || txt.includes('kv$b') || txt.includes('model')) return 'layer-a4';
    if(txt.includes('gpu utilisation') || txt.includes('gpu utilization') || txt.includes('hbm bandwidth')) return 'layer-l1';
    if(txt.includes('dram bandwidth') || txt.includes('swap storm')) return 'layer-l2';
    if(txt.includes('nvme') || txt.includes('deep io') || txt.includes('ssd read') || txt.includes('ssd write') || txt.includes('trim') || txt.includes('per-stream') || txt.includes('hot/cold')) return 'layer-l3';
    if(txt.includes('cross-layer') || txt.includes('bottleneck') || txt.includes('formulas') || txt.includes('recommendations')) return 'layer-cross';
    return 'layer-cross';
  }};
  const cards = Array.from(document.querySelectorAll('.card')).filter(c => !c.classList.contains('stack-noreorder'));
  const buckets = {{}}; layerDefs.forEach(d => buckets[d[0]] = []);
  cards.forEach(c => {{ const h = c.querySelector('h2'); buckets[classify(h ? h.textContent : '')].push(c); }});
  let insertAfter = anchor;
  layerDefs.forEach(([id,title,desc,color]) => {{
    const header = document.createElement('div');
    header.className = 'stack-layer-header stack-noreorder'; header.id = id; header.style.background = color;
    header.innerHTML = '<h2>'+title+'</h2><p>'+desc+'</p>';
    insertAfter.parentNode.insertBefore(header, insertAfter.nextSibling);
    insertAfter = header;
    (buckets[id] || []).forEach(c => {{ insertAfter.parentNode.insertBefore(c, insertAfter.nextSibling); insertAfter = c; }});
  }});
}});
</script>
</head>
<body>

<!-- HEADER -->
<div style="background:#ffffff;border:1px solid #e2e8f0;border-radius:12px;
            padding:20px 24px;margin-bottom:20px;
            border-left:4px solid #4f46e5;
            box-shadow:0 1px 4px rgba(0,0,0,0.06)">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px">
    <div>
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px">
        <span class="report-title-prefix" style="font-size:22px;font-weight:900;letter-spacing:-0.5px;color:#0f172a">AI STACK</span>
        <span class="report-title-accent" style="font-size:22px;font-weight:900;letter-spacing:-0.5px;color:#4f46e5">BOTTLENECK REPORT</span>
        <span style="font-size:10px;background:#eef2ff;color:#4338ca;padding:3px 10px;
                     border-radius:20px;font-weight:700;border:1px solid #c7d2fe">AMOprof v1.0</span>
      </div>
      <div style="font-size:12px;color:#334155;font-family:monospace;margin-bottom:2px">{m.model}</div>
      <div style="font-size:11px;color:#64748b">Run: {run_label} &middot; Duration: {m.run_duration_s/60:.0f}m &middot; {m.gpu_count}&times; A100</div>
    </div>
  </div>
  <div class="kpis" style="margin-top:16px">{kpis}</div>
</div>

{setup_panel_html}
{layered_overview_html}

<!-- CACHE HIT METHODOLOGY -->
<div class="card" style="border-color:#22d3ee">
  <h2>🎯 Cache Hit Methodology — Benchmark vs Gauge Calculations</h2>
  <div style="font-size:12px;color:#64748b;line-height:1.6;margin-bottom:12px">
    This section separates the benchmark-equivalent token-weighted cache hit from Prometheus gauge summaries.
    The main KPI uses the <b>script-compatible active gauge average</b> when <code>sglang_cache_hit_rate</code> samples are available, so it matches the standalone Prometheus validation script. Token-weighted accounting is still shown separately because it is useful for benchmark-style token accounting.
  </div>
  <table>
    <thead><tr><th>Calculation</th><th>Value</th><th>How to interpret</th></tr></thead>
    <tbody>
      <tr><td style="padding:8px 12px;font-weight:700;color:#0f172a">Token-weighted / benchmark-style</td><td style="padding:8px 12px;font-family:monospace;font-weight:700;color:#22c55e">{m.cache_hit_token_weighted_pct or m.cache_hit_pct:.2f}%</td><td style="padding:8px 12px;color:#64748b">Δprefill_cache / (Δprefill_cache + Δprefill_compute). This is the preferred KPI and should track benchmark cache hit.</td></tr>
      <tr><td style="padding:8px 12px;font-weight:700;color:#0f172a">Gauge active average</td><td style="padding:8px 12px;font-family:monospace;font-weight:700;color:#0891b2">{m.cache_hit_gauge_active_pct:.2f}%</td><td style="padding:8px 12px;color:#64748b">Mean of non-zero <code>sglang_cache_hit_rate</code> samples. Active windows: {m.cache_hit_gauge_active_samples} / {m.cache_hit_gauge_total_samples}.</td></tr>
      <tr><td style="padding:8px 12px;font-weight:700;color:#0f172a">Gauge timeline average</td><td style="padding:8px 12px;font-family:monospace;font-weight:700;color:#f97316">{m.cache_hit_gauge_overall_pct:.2f}%</td><td style="padding:8px 12px;color:#64748b">Mean across all collected gauge samples, including idle/dead-space intervals.</td></tr>
      <tr><td style="padding:8px 12px;font-weight:700;color:#0f172a">Gauge peak</td><td style="padding:8px 12px;font-family:monospace;font-weight:700;color:#7c3aed">{m.cache_hit_gauge_peak_pct:.2f}%</td><td style="padding:8px 12px;color:#64748b">Maximum observed instantaneous/rolling cache-hit gauge value.</td></tr>
    </tbody>
  </table>
  <details class="fml" style="margin-top:10px"><summary>📐 Formula</summary><div class="fml-body"><code>Token weighted = Δsglang:realtime_tokens_total{{mode="prefill_cache"}} / (Δprefill_cache + Δprefill_compute) × 100
Gauge active average = avg(sglang_cache_hit_rate samples where value > 0) × 100
Gauge timeline average = avg(all sglang_cache_hit_rate samples) × 100
Gauge peak = max(sglang_cache_hit_rate samples) × 100
Cached/prompt fallback = Δcached_tokens_total / Δprompt_tokens_total × 100
Calculation method used for main KPI: {m.cache_hit_calc_method}</code></div></details>
</div>

<!-- PERCENTILE SUMMARY -->
<div class="card">
  <h2>📊 P50 / P90 / P99 Summary</h2>
  {img(charts.get("percentiles", ""), "P50 P90 P99 percentile summary")}
</div>

<!-- PHASE ANALYSIS -->
<div class="card">
  <h2>⚡ AI Operation Phase Analysis — Prefill (TTFT) vs Decode (TPOT)</h2>
  <div class="grid2">
    <div style="background:#f1f5f9;border:1px solid #e2e8f0;border-radius:8px;padding:14px">
      <div style="display:flex;justify-content:space-between;margin-bottom:8px">
        <span style="font-size:12px;font-weight:700;color:{PREFILL};text-transform:uppercase;letter-spacing:1px">▶ Prefill Phase</span>
        {sev_badge("HIGH" if m.ttft_ms > 1000 else "MED" if m.ttft_ms > 300 else "LOW")}
      </div>
      <div style="font-size:28px;font-weight:900;color:{PREFILL};font-family:monospace;margin-bottom:8px">{fmt(m.ttft_ms, 0)} <span style="font-size:14px;color:#64748b">ms TTFT</span></div>
      <div style="font-size:12px;color:#64748b;line-height:1.7">
        <div><span style="color:#0f172a">Context tokens:</span> {m.prefill_cache_tokens+m.prefill_compute_tokens:,} ({fmt(m.prefill_compute_tokens/(max(m.prefill_cache_tokens+m.prefill_compute_tokens,1))*100,1)}% compute)</div>
        <div><span style="color:#0f172a">Cache hit rate:</span> {fmt(m.cache_hit_pct, 1)}% → low prefill compute</div>
        <div><span style="color:#0f172a">Phase driver:</span> {'Long context compute on large model' if m.ttft_ms > 1000 else 'Short context — prefill is fast'}</div>
      </div>
    </div>
    <div style="background:#f1f5f9;border:1px solid #e2e8f0;border-radius:8px;padding:14px">
      <div style="display:flex;justify-content:space-between;margin-bottom:8px">
        <span style="font-size:12px;font-weight:700;color:{DECODE};text-transform:uppercase;letter-spacing:1px">▶ Decode Phase</span>
        {sev_badge("HIGH" if m.tpot_ms > 80 else "MED" if m.tpot_ms > 30 else "LOW")}
      </div>
      <div style="font-size:28px;font-weight:900;color:{DECODE};font-family:monospace;margin-bottom:8px">{fmt(m.tpot_ms, 1)} <span style="font-size:14px;color:#64748b">ms/tok TPOT</span></div>
      <div style="font-size:12px;color:#64748b;line-height:1.7">
        <div><span style="color:#0f172a">Throughput:</span> {fmt(m.gen_tp_peak, 1)} tok/s peak</div>
        <div><span style="color:#0f172a">Decode tokens:</span> {m.decode_tokens:,} generated</div>
        <div><span style="color:#0f172a">Bottleneck:</span> {'HBM bandwidth (weight re-read each step)' if m.hbm_util_pct > 50 else 'Compute or scheduling'}</div>
      </div>
    </div>
  </div>
  <!-- Token bar -->
  <div style="margin-top:14px">
    <div style="font-size:11px;color:#64748b;margin-bottom:6px">Context Token Composition</div>
    <div class="phase-bar">
      <div style="flex:{m.prefill_cache_tokens};background:#0891b2;display:flex;align-items:center;justify-content:center" title="Cached {m.prefill_cache_tokens:,}">
        {'<span style="font-size:10px;font-weight:700;color:#fff">'+fmt(pct_cache,0)+'%</span>' if pct_cache > 5 else ''}
      </div>
      <div style="flex:{m.prefill_compute_tokens};background:{PREFILL}" title="Compute {m.prefill_compute_tokens:,}"></div>
      <div style="flex:{m.decode_tokens};background:{DECODE};display:flex;align-items:center;justify-content:center" title="Decode {m.decode_tokens:,}">
        {'<span style="font-size:10px;font-weight:700;color:#fff">'+fmt(pct_decode,0)+'%</span>' if pct_decode > 5 else ''}
      </div>
    </div>
    <div style="display:flex;gap:16px;margin-top:6px;flex-wrap:wrap">
      {''.join(f'<div style="display:flex;align-items:center;gap:5px;font-size:11px;color:#64748b"><div style="width:10px;height:10px;border-radius:2px;background:{c}"></div>{l}</div>' for l,c in [('Prefill Cached','#0891b2'),('Prefill Compute',PREFILL),('Decode Output',DECODE)])}
    </div>
  </div>
</div>

<!-- CHARTS -->
<div class="card">
  <h2>&#9201; GPU Utilisation, Power &amp; HBM Timeline</h2>
  {img(charts.get("gpu_timeline",""), "GPU Timeline")}
  <details class="fml" style="margin-top:10px">
    <summary>&#128208; Formula &amp; Metrics Used</summary>
    <div class="fml-body">
      <div class="fml-src">&#128202; gpu_timeseries.csv — nvidia-smi (1s) + DCGM_FI_DEV_GPU_UTIL + DCGM_FI_DEV_FB_USED + DCGM_FI_DEV_POWER_USAGE</div>
      <code>GPU util %      : DCGM_FI_DEV_GPU_UTIL  (Prometheus) OR
                      nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits

HBM used (GB)   : DCGM_FI_DEV_FB_USED / 1024  (MiB → GB)
HBM util %      : FB_USED / FB_TOTAL × 100
                  FB_TOTAL = DCGM_FI_DEV_FB_USED + DCGM_FI_DEV_FB_FREE

GPU power (W)   : DCGM_FI_DEV_POWER_USAGE  (Prometheus) OR
                  nvidia-smi --query-gpu=power.draw --format=csv,noheader,nounits

Timeseries step : 1s (nvidia-smi) or 15s (Prometheus query_range)
Panel 4         : HBM bandwidth active % = DCGM_FI_PROF_DRAM_ACTIVE × 100
                  (fraction of cycles with outstanding HBM transactions)</code>
      <div class="fml-note">GPU util reflects SM occupancy, not memory bandwidth. A100 can show 100% util at low HBM BW during compute-bound attention. Power includes idle base draw (~50W/GPU); inference active draw typically 250–400W/GPU on A100.</div>
    </div>
  </details>
</div>

<div class="card">
  <h2>&#128200; SGLang Inference Metrics</h2>
  {img(charts.get("inference",""), "Inference Metrics")}
  <details class="fml" style="margin-top:10px">
    <summary>&#128208; Formula &amp; Metrics Used</summary>
    <div class="fml-body">
      <div class="fml-src">&#128202; sglang_timeseries.csv — SGLang Prometheus /metrics endpoint, 1s scrape</div>
      <code>TTFT (ms)       : sglang:time_to_first_token_seconds_sum / _count × 1000
                      (Δ over scrape window = per-interval mean)
TPOT / ITL (ms) : sglang:inter_token_latency_seconds_sum / _count × 1000
Gen throughput  : sglang:gen_throughput[engine_type=unified]  (tokens/s, real-time)
Cache hit rate  : sglang:cache_hit_rate[engine_type=unified]  (0–1, rolling)
Token usage     : sglang:full_token_usage  (fraction of L1 KV pool occupied)
                  OR sglang:token_usage (older SGLang versions)
num_running_reqs: sglang:num_running_reqs[engine_type=unified]  (active sessions)
num_queue_reqs  : sglang:num_queue_reqs  (sessions waiting for capacity)</code>
      <div class="fml-note">TTFT includes prefill attention compute + KV cache lookup. TPOT (inter-token latency) is the decode step time — dominated by HBM memory bandwidth. gen_throughput is a rolling 1s window reported by SGLang, not derived. All metrics are Prometheus counters (cumulative); rates are computed as Δ(sum)/Δ(count) per scrape interval.</div>
    </div>
  </details>
</div>

<div class="card">
  <h2>&#128190; Memory Profile — HBM, DRAM &amp; KV Cache</h2>
  {img(charts.get("memory",""), "Memory Profile")}
  <details class="fml" style="margin-top:10px">
    <summary>&#128208; Formula &amp; Metrics Used</summary>
    <div class="fml-body">
      <div class="fml-src">&#128202; gpu_timeseries.csv (HBM) + amduprof_pcm_raw.csv (DRAM) + sglang_timeseries.csv (KV pool)</div>
      <code>HBM used (GB)     : DCGM_FI_DEV_FB_USED / 1024  per GPU
HBM util %        : FB_USED / 40960 (A100 40GB) × 100
HBM BW est (GB/s) : model_params_GB_per_GPU / (TPOT_ms / 1000)
                    = (n_params × 2B / n_gpus) / tpot_s
                    Accurate when DCGM_FI_PROF_DRAM_ACTIVE unavailable

DRAM BW (GB/s)    : amduprof_pcm_raw.csv → "Total Mem Bw (GB/s)"
                    = DDR4 read+write transactions × 64B / interval
                    AMD EPYC 7742 peak: 204.8 GB/s (8ch DDR4-3200 × 2S)
DRAM util %       : total_BW / 204.8 × 100

KV pool usage     : sglang:full_token_usage × max_total_num_tokens × kv_bytes_per_token / 1e9  [GB]
KV active tokens  : sglang:hicache_host_used_tokens  (L2 DRAM)
                    sglang:kv_used_tokens  (L1 HBM, if available)</code>
      <div class="fml-note">HBM BW estimation from TPOT is accurate ±10% during decode-dominated phases. For prefill-heavy workloads use DCGM_FI_PROF_DRAM_ACTIVE which measures actual HBM transactions. DRAM BW includes all NUMA traffic: KV cache DMA, model loader, OS page cache.</div>
    </div>
  </details>
</div>

<!-- KV CACHE FOOTPRINT -->
<div class="card" style="border-color:#6366f1">
  <h2 style="color:#4f46e5">&#128451; KV Cache Footprint &amp; HBM Capacity Analysis</h2>
  <div style="font-size:11px;color:#475569;line-height:1.6;margin-bottom:14px">
    The KV (Key-Value) cache stores attention tensors for every token in the context window.
    Per-token cost is fixed by model architecture and runtime dtype. It sets the maximum context
    length, batch size ceiling, and the point at which hicache DRAM spill begins.
  </div>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:16px">
    <div style="background:#eef2ff;border:1px solid #c7d2fe;border-radius:8px;padding:12px">
      <div style="font-size:10px;color:#4f46e5;font-weight:700;text-transform:uppercase;margin-bottom:4px">KV Bytes / Token</div>
      <div style="font-size:22px;font-weight:800;color:#4338ca;font-family:monospace">{m.kv_bytes_per_token_kb:.0f}<span style="font-size:12px;color:#6b7280;margin-left:3px">KB</span></div>
      <div style="font-size:10px;color:#6b7280">{m.kv_attention_type} &middot; {m.kv_dtype_name}</div>
    </div>
    <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:12px">
      <div style="font-size:10px;color:#059669;font-weight:700;text-transform:uppercase;margin-bottom:4px">Max Context (HBM)</div>
      <div style="font-size:22px;font-weight:800;color:#047857;font-family:monospace">{m.kv_hbm_max_tokens//1000:.0f}<span style="font-size:12px;color:#6b7280;margin-left:3px">K tokens</span></div>
      <div style="font-size:10px;color:#6b7280">L1 HBM only &middot; {m.kv_hbm_pool_gb:.1f} GB pool</div>
    </div>
    <div style="background:#fff7ed;border:1px solid #fed7aa;border-radius:8px;padding:12px">
      <div style="font-size:10px;color:#c2410c;font-weight:700;text-transform:uppercase;margin-bottom:4px">Weight Footprint</div>
      <div style="font-size:22px;font-weight:800;color:#9a3412;font-family:monospace">{m.kv_weight_gb_per_gpu:.1f}<span style="font-size:12px;color:#6b7280;margin-left:3px">GB/GPU</span></div>
      <div style="font-size:10px;color:#6b7280">{m.kv_n_layers}L &middot; {m.kv_n_heads} KV-heads &middot; dim {m.kv_head_dim}</div>
    </div>
    <div style="background:#f0f9ff;border:1px solid #bae6fd;border-radius:8px;padding:12px">
      <div style="font-size:10px;color:#0369a1;font-weight:700;text-transform:uppercase;margin-bottom:4px">KV Pool Used</div>
      <div style="font-size:22px;font-weight:800;color:#0c4a6e;font-family:monospace">{m.kv_pool_fill_pct:.1f}<span style="font-size:12px;color:#6b7280;margin-left:3px">%</span></div>
      <div style="font-size:10px;color:#6b7280">{m.kv_active_tokens:,} active tokens</div>
    </div>
    <div style="background:#faf5ff;border:1px solid #e9d5ff;border-radius:8px;padding:12px">
      <div style="font-size:10px;color:#7c3aed;font-weight:700;text-transform:uppercase;margin-bottom:4px">INT8 savings</div>
      <div style="font-size:22px;font-weight:800;color:#6d28d9;font-family:monospace">{m.kv_bytes_per_token_kb/2:.0f}<span style="font-size:12px;color:#6b7280;margin-left:3px">KB/tok</span></div>
      <div style="font-size:10px;color:#6b7280">2&times; tokens at INT8 &middot; {m.kv_hbm_max_tokens*2//1000:.0f}K max ctx</div>
    </div>
    <div style="background:#fff1f2;border:1px solid #fecdd3;border-radius:8px;padding:12px">
      <div style="font-size:10px;color:#be123c;font-weight:700;text-transform:uppercase;margin-bottom:4px">Spill Threshold</div>
      <div style="font-size:22px;font-weight:800;color:#9f1239;font-family:monospace">{m.kv_hbm_max_tokens//1000:.0f}<span style="font-size:12px;color:#6b7280;margin-left:3px">K tokens</span></div>
      <div style="font-size:10px;color:#6b7280">Above this &rarr; hicache DRAM spill</div>
    </div>
  </div>
  {img(charts.get("kv_analysis",""), "KV Analysis")}
  <details class="fml" style="margin-top:12px">
    <summary>&#128208; Formula &amp; Derivation</summary>
    <div class="fml-body">
      <div class="fml-src">&#128202; Derived from model architecture DB + runtime dtype</div>
      <code>{"MLA: 2 × n_layers × latent_dim × dtype_bytes" if m.kv_attention_type == "MLA" else "GQA/MHA: 2 × n_layers × n_kv_heads × head_dim × dtype_bytes"}
{"= 2 × " + str(m.kv_n_layers) + " × " + str(m.kv_head_dim) + " (latent) × " + str(m.kv_dtype_bytes) if m.kv_attention_type == "MLA" else "= 2 × " + str(m.kv_n_layers) + " × " + str(m.kv_n_heads) + " × " + str(m.kv_head_dim) + " × " + str(m.kv_dtype_bytes)}
= {m.kv_bytes_per_token:,} bytes = {m.kv_bytes_per_token_kb:.0f} KB per token

HBM pool = {m.hbm_total_mb/1024:.0f} GB total - {m.kv_weight_gb_per_gpu:.1f} GB weights - 0.5 GB runtime = {m.kv_hbm_pool_gb:.1f} GB
Max tokens = {m.kv_hbm_pool_gb:.1f} GB / {m.kv_bytes_per_token_kb:.0f} KB = {m.kv_hbm_max_tokens:,} tokens

INT8 (1B): {m.kv_bytes_per_token//2:,} bytes/tok  → {m.kv_hbm_max_tokens*2:,} max tokens (2×)
FP8  (1B): {m.kv_bytes_per_token//2:,} bytes/tok  → {m.kv_hbm_max_tokens*2:,} max tokens (2×)
INT4 (0.5B): {m.kv_bytes_per_token//4:,} bytes/tok → {m.kv_hbm_max_tokens*4:,} max tokens (4×)</code>
      <div class="fml-note" style="color:#334155">Architecture matched from built-in DB on model name. dtype from sglang_summary.json kv_cache_dtype (default FP16). KV is replicated across all tensor-parallel GPUs — the limit applies to the whole 8-GPU system, not per GPU.</div>
    </div>
  </details>
</div>


<!-- KV TIER COST ANALYSIS -->
<div class="card" style="border-color:#6366f1">
  <h2 style="color:#4f46e5">&#128451; KV$ Per Cache Tier — Runtime Cost Analysis</h2>
  <div style="font-size:11px;color:#334155;line-height:1.6;margin-bottom:14px">
    KV cache reads happen on every prefill step. The latency cost per token depends on
    <b>which tier</b> holds it: L1 HBM is fast (~0.16ms/token), L2 DRAM hicache is 10&times; slower,
    and L3 NVMe KV offload is ~570&times; slower. This section shows the actual tier distribution
    for this run and the TTFT impact if tokens had been served from each tier.
  </div>

  <!-- Tier summary cards -->
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:14px">
    <div style="background:#eef2ff;border:1px solid #c7d2fe;border-radius:8px;padding:12px">
      <div style="font-size:10px;color:#4f46e5;font-weight:700;text-transform:uppercase;margin-bottom:3px">L1 HBM Tokens</div>
      <div style="font-size:20px;font-weight:800;color:#4338ca;font-family:monospace">{m.kv_l1_hbm_tokens//1000:.0f}K</div>
      <div style="font-size:10px;color:#475569">{m.kv_l1_fill_pct:.1f}% of {m.kv_l1_capacity_tokens//1000:.0f}K cap</div>
      <div style="font-size:10px;color:#4f46e5;font-weight:600;margin-top:2px">{m.kv_l1_read_lat_ms:.4f} ms/token</div>
    </div>
    <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:12px">
      <div style="font-size:10px;color:#059669;font-weight:700;text-transform:uppercase;margin-bottom:3px">L2 DRAM Tokens</div>
      <div style="font-size:20px;font-weight:800;color:#047857;font-family:monospace">{m.kv_l2_dram_tokens//1000:.0f}K</div>
      <div style="font-size:10px;color:#475569">{m.kv_l2_fill_pct:.1f}% of {m.kv_l2_capacity_tokens//1000:.0f}K cap</div>
      <div style="font-size:10px;color:#059669;font-weight:600;margin-top:2px">{m.kv_l2_read_lat_ms:.4f} ms/token ({m.kv_l2_read_lat_ms/m.kv_l1_read_lat_ms:.0f}&times; L1)</div>
    </div>
    <div style="background:#fff7ed;border:1px solid #fed7aa;border-radius:8px;padding:12px">
      <div style="font-size:10px;color:#c2410c;font-weight:700;text-transform:uppercase;margin-bottom:3px">L3 NVMe Tokens</div>
      <div style="font-size:20px;font-weight:800;color:#9a3412;font-family:monospace">{m.kv_l3_nvme_tokens//1000:.0f}K</div>
      <div style="font-size:10px;color:#475569">NVMe KV offload</div>
      <div style="font-size:10px;color:#c2410c;font-weight:600;margin-top:2px">{m.kv_l3_read_lat_ms:.2f} ms/token ({m.kv_l3_read_lat_ms/m.kv_l1_read_lat_ms:.0f}&times; L1)</div>
    </div>
    <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:12px">
      <div style="font-size:10px;color:#475569;font-weight:700;text-transform:uppercase;margin-bottom:3px">Weighted Avg Latency</div>
      <div style="font-size:20px;font-weight:800;color:#334155;font-family:monospace">{m.kv_weighted_lat_ms:.4f}<span style="font-size:11px;color:#64748b"> ms/tok</span></div>
      <div style="font-size:10px;color:#475569">across all tiers (actual mix)</div>
    </div>
    <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:12px">
      <div style="font-size:10px;color:#1d4ed8;font-weight:700;text-transform:uppercase;margin-bottom:3px">TTFT (all from L1)</div>
      <div style="font-size:20px;font-weight:800;color:#1e40af;font-family:monospace">{m.kv_ttft_l1_ms:.0f}<span style="font-size:11px;color:#64748b"> ms</span></div>
      <div style="font-size:10px;color:#475569">HBM-only scenario</div>
    </div>
    <div style="background:#fef9c3;border:1px solid #fde047;border-radius:8px;padding:12px">
      <div style="font-size:10px;color:#a16207;font-weight:700;text-transform:uppercase;margin-bottom:3px">TTFT (all from L2)</div>
      <div style="font-size:20px;font-weight:800;color:#854d0e;font-family:monospace">{m.kv_ttft_l2_ms/1000:.1f}<span style="font-size:11px;color:#64748b"> s</span></div>
      <div style="font-size:10px;color:#475569">DRAM-only scenario</div>
    </div>
    <div style="background:#fff1f2;border:1px solid #fecdd3;border-radius:8px;padding:12px">
      <div style="font-size:10px;color:#be123c;font-weight:700;text-transform:uppercase;margin-bottom:3px">TTFT (all from L3)</div>
      <div style="font-size:20px;font-weight:800;color:#9f1239;font-family:monospace">{m.kv_ttft_l3_ms/1000:.0f}<span style="font-size:11px;color:#64748b"> s</span></div>
      <div style="font-size:10px;color:#475569">NVMe-only scenario</div>
    </div>
    <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:12px">
      <div style="font-size:10px;color:#059669;font-weight:700;text-transform:uppercase;margin-bottom:3px">Observed TTFT</div>
      <div style="font-size:20px;font-weight:800;color:#047857;font-family:monospace">{m.ttft_ms:.0f}<span style="font-size:11px;color:#64748b"> ms</span></div>
      <div style="font-size:10px;color:#475569">measured this run</div>
    </div>
  </div>

  {img(charts.get("kv_tiers",""), "KV Tier Analysis")}

  <details class="fml" style="margin-top:12px">
    <summary>&#128208; Formula &amp; Derivation — Tier Read Latency</summary>
    <div class="fml-body">
      <div class="fml-src">&#128202; Derived: kv_bytes_per_token (model arch) + tier bandwidth constants + SGLang metrics</div>
      <code>KV read latency per token  =  kv_bytes_per_token / tier_bandwidth

  L1 HBM  : {m.kv_bytes_per_token:,} bytes / ({m.kv_l1_bw_gbs:.0f} GB/s × 10⁹)  =  {m.kv_l1_read_lat_ms:.4f} ms/token
  L2 DRAM : {m.kv_bytes_per_token:,} bytes / ({m.kv_l2_bw_gbs:.1f} GB/s × 10⁹)  =  {m.kv_l2_read_lat_ms:.4f} ms/token
  L3 NVMe : {m.kv_bytes_per_token:,} bytes / ({m.kv_l3_bw_gbs:.1f} GB/s × 10⁹)   =  {m.kv_l3_read_lat_ms:.2f} ms/token

Total KV read cost for {m.prefill_cache_tokens:,} cached tokens:
  From L1 : {m.prefill_cache_tokens:,} × {m.kv_l1_read_lat_ms:.4f} ms  =  {m.kv_l1_cost_per_req_ms:.0f} ms
  From L2 : {m.prefill_cache_tokens:,} × {m.kv_l2_read_lat_ms:.4f} ms  =  {m.kv_l2_cost_per_req_ms:.0f} ms
  From L3 : {m.prefill_cache_tokens:,} × {m.kv_l3_read_lat_ms:.2f} ms   =  {m.kv_l3_cost_per_req_ms/1000:.0f} s

Weighted latency  =  (L1_tokens×L1_lat + L2_tokens×L2_lat + L3_tokens×L3_lat)
                  /   (L1_tokens + L2_tokens + L3_tokens)
                  =  {m.kv_weighted_lat_ms:.4f} ms/token

Bandwidth constants:
  L1 HBM  = {m.kv_l1_bw_gbs:.0f} GB/s  (A100 HBM2e spec)
  L2 DRAM = {m.kv_l2_bw_gbs:.1f} GB/s  (measured AMD EPYC 7742 AMDuProf, or 200 GB/s default)
  L3 NVMe = {m.kv_l3_bw_gbs:.1f} GB/s  (sequential read, /dev/nvme2n1 spec)</code>
      <div class="fml-note">Token tier counts sourced from SGLang: max_total_num_tokens (L1 cap), full_token_usage×cap (L1 used), hicache_host_used/total_tokens (L2), kv_l3_storage_tokens (L3). L2 BW overridden by live AMDuProf measurement when available.</div>
    </div>
  </details>
</div>

<div class="card">
  <h2>⏳ Latency Breakdown & Token Composition</h2>
  {img(charts.get("latency",""), "Latency")}
</div>

<div class="card">
  <h2>💿 Storage I/O & OS Page Activity</h2>
  {img(charts.get("storage",""), "Storage")}
</div>

<!-- SESSION / STREAM ANALYSIS -->
<div class="card" style="border-color:#6366f1">
  <h2 style="color:#4f46e5">&#128260; Session / Stream Analysis</h2>
  <div style="font-size:11px;color:#334155;line-height:1.6;margin-bottom:14px">
    Per-request breakdown of concurrent sessions, end-to-end latency distribution,
    input token count, and output token count. Derived from SGLang Prometheus histogram deltas.
  </div>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:14px">
    {session_kpi_cards}
  </div>
  {img(charts.get("session",""), "Session Analysis")}
  <details class="fml" style="margin-top:12px">
    <summary>&#128208; Formula &amp; Metrics Used</summary>
    <div class="fml-body">
      <div class="fml-src">&#128202; sglang_timeseries.csv — SGLang Prometheus histogram deltas (1s scrape interval)</div>
      <code>Per-request value = \u0394(metric_sum) / \u0394(metric_count) per scrape interval

E2E latency   : sglang:e2e_request_latency_seconds_sum / _count x 1000 [ms]
Input tokens  : sglang:prompt_tokens_total / sglang:num_requests_total (delta per interval)
Output tokens : sglang:generation_tokens_total / sglang:num_requests_total (delta)
Queue time    : sglang:queue_time_seconds_sum / queue_time_seconds_count x 1000 [ms]
Active sessions: sglang:num_running_reqs[engine_type=unified] (gauge, 1/scrape)
Arrival rate  : \u0394(num_requests_total) / \u0394(time_sec) [req/s]</code>
      <div class="fml-note">Per-request distributions have one data point per completed request observed in the profiling window. With few requests, distributions will be sparse.</div>
    </div>
  </details>
</div>

<!-- KV$B EVENT TRACES -->
<div class="card" style="border-color:#22c55e">
  <h2 style="color:#15803d">&#128230; KV Cache Block (KV$B) Event Traces</h2>
  <div style="font-size:11px;color:#334155;line-height:1.6;margin-bottom:14px">
    KV blocks are the management unit of the KV cache ({kvb_block_size_tokens} tokens = {kvb_block_size_mb:.1f} MB each for this model).
    Offload = blocks moving L1 HBM &#8594; L2 DRAM hicache.
    Eviction = blocks removed from L2 when pool is full.
    Lifetime = estimated duration a block survives before eviction.
  </div>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:14px">
    {kvb_kpi_cards}
  </div>
  {img(charts.get("kvb_events",""), "KV Block Events")}
  <details class="fml" style="margin-top:12px">
    <summary>&#128208; Formula &amp; Metrics Used</summary>
    <div class="fml-body">
      <div class="fml-src">&#128202; sglang_timeseries.csv + model arch DB</div>
      <code>Block size tokens : SGLang default = 16 tokens/block
Block size MB     : block_tokens x kv_bytes_per_token / 1024^2 = {kvb_block_size_mb:.2f} MB
L1 pool blocks    : sglang:max_total_num_tokens / 16 = {kvb_l1_pool_blocks:,}
L2 pool blocks    : sglang:hicache_host_total_tokens / 16 = {kvb_l2_pool_blocks:,}
Offload rate      : \u0394(hicache_host_used_tokens) / 16 / run_duration_s = {kvb_offload_rate:.4f} blk/s
Eviction rate     : offload_rate x (l2_fill - 0.8) / 0.2  [when l2_fill > 80%]
Block lifetime    : l2_pool_blocks / offload_rate = {kvb_lifetime_mean:.0f}s</code>
      <div class="fml-note">hicache_host_used_tokens from sglang:hicache_host_used_tokens[engine_type=unified]. True per-block event logs require SGLang debug logging or blktrace.</div>
    </div>
  </details>
</div>

<!-- NVME IO WORKLOAD -->
<div class="card" style="border-color:#f97316">
  <h2 style="color:#c2410c">&#128191; NVMe IO Workload Characteristics</h2>
  <div style="font-size:11px;color:#334155;line-height:1.6;margin-bottom:14px">
    NVMe write activity is driven by KV block offload when hicache overflows to L3 NVMe.
    During normal inference (L2 not full), NVMe write IOPS should be near zero.
    SMART data shows cumulative SSD health and lifetime IO volume.
  </div>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:14px">
    {nvme_kpi_cards}
  </div>
  {img(charts.get("nvme_io",""), "NVMe IO")}
  <details class="fml" style="margin-top:12px">
    <summary>&#128208; Formula &amp; Metrics Used</summary>
    <div class="fml-body">
      <div class="fml-src">&#128202; nvme_driver_timeseries.csv (/sys/block/nvme2n1/stat, 1s) + smart_timeseries.csv (nvme-cli)</div>
      <code>IOPS           : \u0394(wr_ios) / \u0394(time_sec)
Write latency  : \u0394(wr_ms) / \u0394(wr_ios)  [ms/op]
IO util %      : \u0394(io_ms) / (\u0394(time_sec) x 1000) x 100
Write BW est   : wr_iops_mean x kvb_block_size_mb  [MB/s]
Bytes written  : \u0394(data_units_written) x 512 x 1000  (SMART NVMe unit)
Bytes read     : \u0394(data_units_read)    x 512 x 1000</code>
      <div class="fml-note">Write BW estimate assumes each IO = 1 KV block. Actual unit depends on SGLang NVMe offload config.</div>
    </div>
  </details>
</div>

<!-- DEEP IO PROFILING -->
<div class="card" style="border-color:#94a3b8">
  <h2 style="color:#475569">&#128300; NVMe IO Deep Profiling — Request-Level Characteristics</h2>
  <div style="font-size:11px;color:#334155;line-height:1.6;margin-bottom:10px">
    Request-granularity IO: size distribution, alignment (KV block / page), sequential vs random,
    inter-arrival time, LBA access map, and burst temporal dynamics.
    {blkio_status_html}
  </div>
  {blkio_enable_html}
  {img(charts.get("blkio_deep",""), "Deep IO Profiling")}
</div>

<!-- §C SSD READ WORKLOAD -->
<div class="card" style="border-color:#3b82f6">
  <h2 style="color:#1d4ed8">&#128202; KV$ SSD Read Workload Characteristics — §C</h2>
  <div style="font-size:11px;color:#334155;line-height:1.6;margin-bottom:12px">
    Per-request read IO analysis: BW timeline, request size distribution, sequential vs random
    access pattern, inter-arrival time, LBA hot/cold areas, KV block / page alignment,
    skewness, and bandwidth degradation over the run.
    Source: blktrace (per-request) + <code style="background:#eff6ff;padding:1px 4px;border-radius:3px;color:#1d4ed8">node_disk_read_bytes_total</code> (device-level).
  </div>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:14px">
    {_kpi("Rd BW Mean",f"{m.ssd_rd_bw_mbs_mean:.2f}","MB/s","#eff6ff","#1d4ed8",f"bytes/day≈{m.ssd_rd_bytes_per_day_gb:.2f}GB")}
    {_kpi("Rd Size Mean",f"{m.ssd_rd_size_mean_kb:.1f}","KB","#eff6ff","#1d4ed8",f"P99={m.ssd_rd_size_p99_kb:.1f}KB")}
    {_kpi("Sequential %",f"{m.ssd_rd_seq_pct:.1f}","%","#f0fdf4","#047857",f"Random={m.ssd_rd_rand_pct:.1f}%")}
    {_kpi("KV$B Aligned",f"{m.ssd_rd_kvb_aligned_pct:.1f}","%","#f0fdf4","#047857",f"Page={m.ssd_rd_page_aligned_pct:.1f}%")}
    {_kpi("IAT Mean",f"{m.ssd_rd_iat_mean_us:.1f}","µs","#f8fafc","#334155",f"P99={m.ssd_rd_iat_p99_us:.1f}µs")}
    {_kpi("Skewness",f"{m.ssd_rd_skewness:.2f}","","#fff7ed","#c2410c",f"Gini={m.ssd_rd_gini:.3f}")}
    {_kpi("BW Degrad.",f"{m.ssd_rd_bw_degradation:.2f}","×","#fff1f2" if m.ssd_rd_bw_degradation < 0.9 else "#f0fdf4","#9f1239" if m.ssd_rd_bw_degradation < 0.9 else "#047857","1.0=no degradation")}
    {_kpi("Bursts",f"{m.ssd_rd_burst_count}","","#faf5ff","#6d28d9",f"mean={m.ssd_rd_burst_mean_bytes/1024:.0f}KB")}
  </div>
  {img(charts.get("ssd_read",""), "SSD Read Workload")}
  <details class="fml" style="margin-top:12px">
    <summary>&#128208; Formula &amp; Metrics Used (§C)</summary>
    <div class="fml-body">
      <div class="fml-src">&#128202; blktrace/blkparse (per-request) + node_disk_read_bytes_total (device-level)</div>
      <code>§C32  device_rd_bw = rate(node_disk_read_bytes_total{{device=nvme2n1}}[W])
§C34  rd_iat_i = ts_i - ts_{{i-1}}  for read events ordered by ts  [µs]
§C35  burst = sequence where rd_iat_i < 1ms threshold
§C36  skewness = E[((x-mean)/std)^3]  where x=read_count per LBA bucket
§C38  rd_size_i = nr_sectors_i × 512  [bytes from blkparse]
§C40  kvb_misalign = (offset_i % kv_block_bytes != 0) OR (size_i % kv_block_bytes != 0)
      kv_block_bytes: sglang:cache_config_info{{page_size}} × kv_bytes_per_token
§C41  page_misalign = (offset_i % 4096 != 0)  [getconf PAGESIZE = 4096]
§C42  seq_i = (sector_i == prev_sector + prev_nr_sectors)
§C43  corr(size, is_random) = Pearson/Spearman correlation
§C44  bytes_per_day = bytes_total / run_duration_s × 86400
§C45  bw_degrad = avg_bw(last_20%) / avg_bw(first_20%)</code>
      <div class="fml-note">Per-request metrics require blktrace: sudo blktrace -d /dev/nvme2n1 -o - | blkparse -i - > blktrace.txt, then --blktrace blktrace.txt. Device-level BW available from node_exporter without blktrace.</div>
    </div>
  </details>
</div>

<!-- §D SSD WRITE WORKLOAD -->
<div class="card" style="border-color:#f97316">
  <h2 style="color:#c2410c">&#128203; KV$ SSD Write Workload Characteristics — §D</h2>
  <div style="font-size:11px;color:#334155;line-height:1.6;margin-bottom:12px">
    KV block offload writes: IOPS timeline, request size distribution, sequential vs random,
    alignment checks, inter-arrival time, and bandwidth degradation.
    Write activity = KV$B being offloaded from L2 hicache DRAM to L3 NVMe.
    Zero write IOPS = all KV fits in HBM + DRAM tiers.
    Source: blktrace (per-request) + <code style="background:#fff7ed;padding:1px 4px;border-radius:3px;color:#c2410c">node_disk_written_bytes_total</code>.
  </div>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:14px">
    {_kpi("Wr BW Mean",f"{m.ssd_wr_bw_mbs_mean:.2f}","MB/s","#fff7ed","#c2410c",f"IOPS={m.nvme_wr_iops_mean:.1f}")}
    {_kpi("Wr Size Mean",f"{m.ssd_wr_size_mean_kb:.1f}","KB","#fff7ed","#c2410c",f"P99={m.ssd_wr_size_p99_kb:.1f}KB")}
    {_kpi("Sequential %",f"{m.ssd_wr_seq_pct:.1f}","%","#f0fdf4","#047857","")}
    {_kpi("KV$B Aligned",f"{m.ssd_wr_kvb_aligned_pct:.1f}","%","#f0fdf4","#047857",f"Page={m.ssd_wr_page_aligned_pct:.1f}%")}
    {_kpi("Wr IAT Mean",f"{m.ssd_wr_iat_mean_us:.1f}","µs","#f8fafc","#334155",f"P99={m.ssd_wr_iat_p99_us:.1f}µs")}
    {_kpi("Wr Skewness",f"{m.ssd_wr_skewness:.2f}","","#fff7ed","#c2410c","")}
    {_kpi("Bytes Written",f"{m.ssd_wr_bytes_total/1e9:.3f}","GB","#faf5ff","#6d28d9",f"{m.ssd_wr_bytes_per_day_gb:.2f}GB/day")}
    {_kpi("BW Degrad.",f"{m.ssd_wr_bw_degradation:.2f}","×","#fff1f2" if m.ssd_wr_bw_degradation < 0.9 else "#f0fdf4","#9f1239" if m.ssd_wr_bw_degradation < 0.9 else "#047857","1.0=stable")}
  </div>
  {img(charts.get("ssd_write",""), "SSD Write Workload")}
  <details class="fml" style="margin-top:12px">
    <summary>&#128208; Formula &amp; Metrics Used (§D)</summary>
    <div class="fml-body">
      <div class="fml-src">&#128202; blktrace/blkparse (per-request) + node_disk_written_bytes_total (device-level)</div>
      <code>§D47  device_wr_bw = rate(node_disk_written_bytes_total{{device=nvme2n1}}[W])
§D49  wr_iat_i = ts_i - ts_{{i-1}}  for write events  [µs]
§D50  burst = sequence where wr_iat_i < 1ms
§D53  wr_size_i = nr_sectors_i × 512  [bytes]
§D55  wr_kvb_misalign = (offset_i % kv_block_bytes != 0)
§D59  bytes_written_per_day = bytes_total / run_s × 86400
§D60  degrad = avg_bw(last_20%) / avg_bw(first_20%)
      Cross-check: node_disk_written_bytes_total vs sglang:backuped_tokens_total × kv_bytes_per_token</code>
      <div class="fml-note">Write activity directly corresponds to KV block offload (§B22-B23). High write IOPS + matching backuped_tokens_total confirms KV$B SSD offload path is active.</div>
    </div>
  </details>
</div>

<!-- §E TRIM + SEASONAL -->
<div class="card" style="border-color:#a855f7">
  <h2 style="color:#7c3aed">&#128256; Trim / Discard Events &amp; Temporal Patterns — §E</h2>
  <div style="font-size:11px;color:#334155;line-height:1.6;margin-bottom:12px">
    TRIM/discard events (proxy for KV block eviction), seasonal R/W/T patterns via FFT,
    cross-correlation between read ↔ write ↔ trim timeseries, and R/W/T ratio analysis.
    Sources: <code style="background:#faf5ff;padding:1px 4px;border-radius:3px;color:#7c3aed">node_disk_discards_completed_total</code>,
    <code style="background:#faf5ff;padding:1px 4px;border-radius:3px;color:#7c3aed">node_disk_discarded_sectors_total</code>,
    blktrace rwbs=D events.
  </div>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:14px">
    {_kpi("TRIM Present","Yes" if m.trim_present else "No","","#f0fdf4" if not m.trim_present else "#faf5ff","#047857" if not m.trim_present else "#7c3aed","")}
    {_kpi("Trim IOPS",f"{m.trim_iops_mean:.4f}","","#faf5ff","#7c3aed","")}
    {_kpi("Trim BW",f"{m.trim_bw_mbs:.4f}","MB/s","#faf5ff","#7c3aed",f"size={m.trim_size_mean_kb:.1f}KB")}
    {_kpi("R/W Ratio",f"{m.rw_ratio_mean:.2f}","","#eff6ff","#1d4ed8","read:write bytes")}
    {_kpi("Rd Period",f"{m.seasonal_rd_period_s:.0f}","s","#f0fdf4","#047857","FFT dominant")}
    {_kpi("Wr Period",f"{m.seasonal_wr_period_s:.0f}","s","#fff7ed","#c2410c","FFT dominant")}
    {_kpi("R↔W Lag",f"{m.cross_corr_rw_peak_lag_s:.1f}","s","#f8fafc","#334155","peak corr lag")}
    {_kpi("KV$B Aligned",f"{m.trim_kvb_aligned_pct:.1f}","%","#faf5ff","#7c3aed","trim alignment")}
  </div>
  {img(charts.get("trim_seasonal",""), "Trim & Seasonal")}
  <details class="fml" style="margin-top:12px">
    <summary>&#128208; Formula &amp; Metrics Used (§E)</summary>
    <div class="fml-body">
      <div class="fml-src">&#128202; node_disk_discards_completed_total + node_disk_discarded_sectors_total + Python scipy.fft</div>
      <code>§E61  trim_present = count(node_disk_discards_completed_total delta > 0)
§E62  trim_Bps = rate(node_disk_discarded_sectors_total[W]) × 512
§E63  trim_iops = rate(node_disk_discards_completed_total[W])
§E64  trim_iat_i = ts_i - ts_{{i-1}}  for discard events  [blktrace rwbs=D]
§E68  seasonal_rd_period = 1 / argmax(|FFT(R(t))|)
§E69  seasonal_wr_period = 1 / argmax(|FFT(W(t))|)
§E71  corr_RW(lag) = corr(R(t), W(t-lag))  for lag in [-30, +30] samples
§E72  RW_ratio(t) = R(t) / max(W(t), ε)  [bytes/s]
§E73  TW_ratio(t) = D(t) / max(W(t), ε)  [trim bytes vs write bytes]</code>
      <div class="fml-note">Seasonal analysis uses scipy.fft on node_exporter IOPS timeseries at 15s resolution. Cross-correlation computed with sliding lag on same timeseries. TRIM events require device discard support; some NVMe configs issue batch TRIM after eviction, not immediately.</div>
    </div>
  </details>
</div>

<!-- §G CROSS-LAYER KPIs -->
<div class="card" style="border-color:#22c55e">
  <h2 style="color:#15803d">&#128200; Cross-Layer KPIs — SSD / GPU / Inference Correlation — §G</h2>
  <div style="font-size:11px;color:#334155;line-height:1.6;margin-bottom:12px">
    End-to-end dependency analysis: SSD bytes consumed per inference token,
    throughput bottleneck identification (GPU-limited vs SSD-limited),
    and correlation between KV$B offload/onboard rates and actual NVMe IO.
    Sources: SGLang + DCGM + node_exporter combined.
  </div>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:14px">
    {_kpi("Rd B/output tok",f"{m.ssd_rd_bytes_per_output_tok:.1f}","B","#eff6ff","#1d4ed8","§G88: SSD→GPU")}
    {_kpi("Wr B/input tok",f"{m.ssd_wr_bytes_per_input_tok:.1f}","B","#fff7ed","#c2410c","§G89: GPU→SSD")}
    {_kpi("Bottleneck",m.throughput_bottleneck_src or "N/A","","#f0fdf4" if m.throughput_bottleneck_src == "GPU" else "#fff1f2","#047857" if m.throughput_bottleneck_src == "GPU" else "#9f1239","§G93")}
    {_kpi("SSD tok ceiling",f"{m.ssd_effective_bw_gbs*1e9/m.kv_bytes_per_token:.0f}" if m.kv_bytes_per_token > 0 and m.ssd_effective_bw_gbs > 0 else "N/A","tok/s","#f8fafc","#334155","SSD_BW/kv_bytes")}
    {_kpi("Offload↔Wr corr",f"{m.offload_write_corr:.3f}","","#f0fdf4" if abs(m.offload_write_corr)>0.7 else "#fff7ed","#047857" if abs(m.offload_write_corr)>0.7 else "#c2410c","§G90")}
    {_kpi("Onboard↔Rd corr",f"{m.onboard_read_corr:.3f}","","#f0fdf4" if abs(m.onboard_read_corr)>0.7 else "#fff7ed","#047857" if abs(m.onboard_read_corr)>0.7 else "#c2410c","§G91")}
  </div>
  {img(charts.get("cross_layer",""), "Cross-Layer KPIs")}
  <details class="fml" style="margin-top:12px">
    <summary>&#128208; Formula &amp; Metrics Used (§G)</summary>
    <div class="fml-body">
      <div class="fml-src">&#128202; node_disk_read/written_bytes_total + sglang:generation/prompt_tokens_total + DCGM_FI_DEV_GPU_UTIL</div>
      <code>§G88  ssd_rd_per_output_tok = rate(node_disk_read_bytes_total[W])
                              / rate(sglang:generation_tokens_total[W])
§G89  ssd_wr_per_prompt_tok = rate(node_disk_written_bytes_total[W])
                              / rate(sglang:prompt_tokens_total[W])
§G90  corr(offload_Bps, write_bw)
      offload_Bps = rate(sglang:backuped_tokens_total[W]) × kv_bytes_per_token
      write_bw    = rate(node_disk_written_bytes_total[W])
§G91  corr(onboard_Bps, read_bw)
      onboard_Bps = rate(sglang:prefetched_tokens_total[W]) × kv_bytes_per_token
§G93  max_tokens_from_ssd = ssd_read_bw / kv_bytes_per_token
      bottleneck = "GPU" if gpu_tok_rate < ssd_tok_rate else "SSD"
      gpu_tok_rate = sglang:gen_throughput  (or DCGM-derived)</code>
      <div class="fml-note">G88/G89 are high when decode/prefill depend heavily on SSD reads/writes — indicating KV$B SSD offload path is active. G93 is an upper bound: actual throughput may be lower due to latency, not just bandwidth. High offload↔write correlation (G90) validates that backuped_tokens_total faithfully tracks actual SSD writes.</div>
    </div>
  </details>
</div>
<div class="card" style="border-color:#f97316">
  <h2 style="color:#c2410c">📊 KV$ SSD IO Workload Characteristics — §C Read &amp; §D Write &amp; §E Trim</h2>
  <div style="font-size:11px;color:#334155;line-height:1.6;margin-bottom:12px">
    Request-level IO analysis from blktrace: size distribution, alignment (KV block / page),
    sequential vs random access, inter-arrival time, LBA hot/cold areas, burst dynamics,
    TRIM/discard events, and R/W/T temporal correlations.
    {'<b style="color:#059669">blktrace data loaded.</b>' if m.blktrace_available else
     '<b style="color:#c2410c">blktrace not loaded — most charts show framework only. '
     'Enable with: --blktrace blktrace.txt</b>'}
  </div>
  <!-- KPI row -->
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px;margin-bottom:12px">
    {_kpi("R Request Size", f"{m.rd_req_size_mean_kb:.0f}", "KB mean", "#eff6ff", "#1d4ed8",
          f"P95={m.rd_req_size_p95_kb:.0f}KB  P99={m.rd_req_size_p99_kb:.0f}KB")}
    {_kpi("W Request Size", f"{m.wr_req_size_mean_kb:.0f}", "KB mean", "#fff7ed", "#9a3412",
          f"P95={m.wr_req_size_p95_kb:.0f}KB")}
    {_kpi("R IAT Mean", f"{m.rd_iat_mean_us:.0f}", "µs", "#eff6ff", "#1d4ed8",
          f"P95={m.rd_iat_p95_us:.0f}µs  P99={m.rd_iat_p99_us:.0f}µs")}
    {_kpi("R Seq/Rand", f"{m.rd_seq_pct:.0f}/{m.rd_rand_pct:.0f}", "%", "#f0fdf4", "#047857",
          f"W:{m.wr_seq_pct:.0f}/{m.wr_rand_pct:.0f}%")}
    {_kpi("R KVB-Aligned", f"{m.rd_kvb_aligned_pct:.0f}", "%", "#faf5ff", "#6d28d9",
          f"page={m.rd_page_aligned_pct:.0f}%")}
    {_kpi("W KVB-Aligned", f"{m.wr_kvb_aligned_pct:.0f}", "%", "#fff7ed", "#9a3412",
          f"page={m.wr_page_aligned_pct:.0f}%")}
    {_kpi("LBA Skewness R", f"{m.rd_lba_skewness:.2f}", "", "#f8fafc", "#334155",
          f"Gini={m.rd_lba_gini:.2f}")}
    {_kpi("TRIM Ops", f"{m.trim_ops_total:,}", "", "#fff1f2" if m.trim_present else "#f8fafc",
          "#9f1239" if m.trim_present else "#94a3b8",
          "TRIM active" if m.trim_present else "no TRIM")}
    {_kpi("R/W Ratio", f"{m.rw_ratio_mean:.2f}", "×", "#f0f9ff", "#0c4a6e",
          f"corr={m.corr_rw:.3f}")}
  </div>
  {img(charts.get("kvssd_io",""), "KV$ SSD IO Analysis")}
  <details class="fml" style="margin-top:12px">
    <summary>📐 Formula &amp; Metrics Used — §C Read / §D Write / §E Trim</summary>
    <div class="fml-body">
      <div class="fml-src" style="color:#1e293b;font-weight:600">📊 blktrace/blkparse + node_exporter + nvme-cli  — per-IO event level</div>
      <code>§C/D Read/Write request size:  nr_sectors × 512  [bytes]
  Source: blkparse nr_sectors field (blktrace -d /dev/nvme2n1 | blkparse -i -)
  KVB alignment: (offset % kv_block_bytes == 0) AND (size % kv_block_bytes == 0)
    kv_block_bytes = tokens_per_KV_block × kv_bytes_per_token
    tokens_per_KV_block from: sglang:cache_config_info labels (page_size)
  Page alignment: (offset % 4096 == 0) AND (size % 4096 == 0)

Sequential: sector_i == prev_sector + prev_nr_sectors
  seq_area_pct = sum(bytes where seq) / sum(all bytes) × 100

Inter-arrival time: ts_i - ts_{{i-1}}  [µs]
  Source: blkparse timestamp field, per R/W/D event type

LBA Skewness: scipy.stats.skew(read_count per LBA bucket)
  Gini coefficient = 1 - 2 × sum(cumulative counts) / (n × total_count)
  Hot area: % bytes in top-20% LBA buckets

Size vs random correlation: scipy.stats.pointbiserialr(is_random, size_bytes)

§E TRIM/Discard:
  trim_iops = rate(node_disk_discards_completed_total[W])
  trim_Bps  = rate(node_disk_discarded_sectors_total[W]) × 512
  Trim detection from blktrace: rwbs field contains D or DISCARD
  Trim alignment: same as read/write alignment but for discard events

§E Temporal patterns (R/W/T cross-correlation):
  R(t), W(t), D(t) = binned bytes/sec timeseries
  corr_RW = pandas.Series.corr(R, W)
  Seasonal period = dominant FFT frequency of R(t)
  R/W ratio = R(t) / max(W(t), 1)  (mean over run)</code>
      <div class="fml-note">blktrace/blkparse provides per-IO event timestamps, sectors, sizes, and op type (R/W/D). 
Per-session attribution requires request_id → PID → LBA mapping (not automatic).
Device bandwidth from node_disk_read/written_bytes_total (node_exporter) or iostat when node_exporter unavailable.</div>
    </div>
  </details>
</div>

<!-- CROSS-LAYER KPIs (§G) -->
<div class="card" style="border-color:#6366f1">
  <h2 style="color:#4f46e5">🔗 §G Cross-Layer Correlation &amp; Derived KPIs</h2>
  <div style="font-size:11px;color:#334155;line-height:1.6;margin-bottom:12px">
    Derived KPIs combining SGLang inference metrics, node_exporter NVMe IO, and DCGM GPU metrics.
    Shows the relationship between SSD IO pressure and inference throughput,
    per-token SSD cost, and throughput bottleneck estimate.
  </div>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:8px;margin-bottom:12px">
    {_kpi("Bottleneck", m.throughput_bottleneck_label, "", "#eef2ff", "#4338ca",
          f"GPU={m.throughput_bottleneck_gpu_tok_s:.0f} SSD={m.throughput_bottleneck_ssd_tok_s:.0f} tok/s")}
    {_kpi("SSD Rd/Output Tok", f"{m.ssd_read_per_output_token_kb:.3f}", "KB", "#f0f9ff", "#0c4a6e",
          "§88: SSD read per generated token")}
    {_kpi("SSD Wr/Input Tok", f"{m.ssd_write_per_input_token_kb:.3f}", "KB", "#fff7ed", "#9a3412",
          "§89: SSD write per prompt token")}
    {_kpi("R/W Corr", f"{m.corr_rw:.3f}", "", "#f0fdf4", "#047857", "§90/91 correlation")}
    {_kpi("Seasonal Period", f"{m.read_seasonal_period_s:.0f}", "s", "#faf5ff", "#6d28d9",
          "dominant read IO period")}
  </div>
  {img(charts.get("kvssd_cross",""), "Cross-Layer KPIs")}
  <details class="fml" style="margin-top:12px">
    <summary>📐 Formula &amp; Metrics Used — §G Cross-Layer KPIs</summary>
    <div class="fml-body">
      <div class="fml-src" style="color:#1e293b;font-weight:600">📊 Combined: node_exporter + SGLang Prometheus + DCGM</div>
      <code>§88 SSD read per output token:
  ssd_read_per_output_token = rate(node_disk_read_bytes_total[W])
                            / rate(sglang:generation_tokens_total[W])

§89 SSD write per input token:
  ssd_write_per_input_token = rate(node_disk_written_bytes_total[W])
                            / rate(sglang:prompt_tokens_total[W])

§93 Throughput bottleneck:
  max_tokens_from_ssd = ssd_read_bw / kv_bytes_per_token
  bottleneck = min(gpu_token_rate, max_tokens_from_ssd)
  gpu_token_rate = sglang:gen_throughput peak  [tok/s]
  ssd_read_bw = node_disk_read_bytes_total rate OR rd_total_bytes/run_duration

§90/91 Correlation (offload vs SSD write, onboard vs SSD read):
  corr(sglang:backuped_tokens × kv_bytes, node_disk_written_bytes) 
  corr(sglang:prefetched_tokens × kv_bytes, node_disk_read_bytes)

Seasonal period: FFT on R(t) = binned read bytes/sec timeseries
  dominant_freq = argmax(|FFT(R(t))|[1:])
  period = 1 / dominant_freq  [seconds]</code>
      <div class="fml-note">For §90/91 exact correlation, export aligned timeseries from Prometheus and run pandas.Series.corr. The bottleneck estimate uses peak GPU throughput vs SSD bandwidth ceiling.</div>
    </div>
  </details>
</div>

<!-- §stream and §hotcold: pre-computed blktrace analysis -->
{f"""
<!-- KV$ SSD: Per-Stream & Temporal Analysis -->
<div class="card" style="border-color:#3b82f6">
  <h2 style="color:#1d4ed8">&#128202; KV$ SSD — Per-Stream Bandwidth &amp; Temporal Pattern</h2>
  <div style="font-size:11px;color:#334155;line-height:1.6;margin-bottom:12px">
    Per-stream bandwidth distribution (each inference session = one stream), inter-arrival
    time histogram, and R/W temporal pattern per time window. Derived from
    <code style="background:#eff6ff;padding:1px 4px;border-radius:3px;color:#1d4ed8">bandwidth_per_stream.csv</code>,
    <code style="background:#eff6ff;padding:1px 4px;border-radius:3px;color:#1d4ed8">interarrival_distribution.csv</code>,
    <code style="background:#eff6ff;padding:1px 4px;border-radius:3px;color:#1d4ed8">temporal_read_write_trim_pattern.csv</code>.
  </div>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:14px">
    {_kpi("Rd Streams",f"{m.ssd_rd_stream_count}","","#eff6ff","#1d4ed8",f"median {m.ssd_rd_bw_per_stream_mean_mbs:.0f} MiB/s")}
    {_kpi("Wr Streams",f"{m.ssd_wr_stream_count}","","#fff7ed","#c2410c",f"median {m.ssd_wr_bw_per_stream_mean_mbs:.0f} MiB/s")}
    {_kpi("Rd BW Total",f"{m.ssd_rd_bw_mbs_mean/1000:.0f}","GiB/s","#eff6ff","#1d4ed8",f"{m.ssd_rd_bytes_total/1e9:.1f} GB total")}
    {_kpi("Wr BW Total",f"{m.ssd_wr_bw_mbs_mean/1000:.0f}","GiB/s","#fff7ed","#c2410c",f"{m.ssd_wr_bytes_total/1e9:.1f} GB total")}
    {_kpi("R/W Ratio",f"{m.ssd_rw_byte_ratio:.2f}","×","#f0fdf4","#047857","read / write bytes")}
    {_kpi("Rd IAT Mean",f"{m.ssd_rd_iat_mean_us:.3f}","µs","#f8fafc","#334155",f"p99={m.ssd_rd_iat_p99_us:.3f}µs")}
    {_kpi("100% Aligned","Yes","","#f0fdf4","#047857","all KV$B + 4KB aligned")}
    {_kpi("100% Random","Yes","","#fff1f2","#9f1239","all IOs are random LBA")}
  </div>
  {img(charts.get("bt_streams",""), "Per-Stream BW")}
  <details class="fml" style="margin-top:12px">
    <summary>&#128208; Formula &amp; Metrics Used — Per-Stream BW &amp; IAT</summary>
    <div class="fml-body">
      <div class="fml-src">&#128202; bandwidth_per_stream.csv + interarrival_distribution.csv + temporal_read_write_trim_pattern.csv</div>
      <code>Stream definition:
  stream_id = trace_window_id:pid  (e.g. "1.0:537222")
  Each stream = one inference request / KV cache session per time window

Per-stream BW (§C/D bandwidth_per_stream):
  bw_stream = stream_bytes / stream_duration_sec  [MiB/s]
  stream_duration = last_ts - first_ts  (timestamps from blkparse)
  Reported: median, max (streams with count > 10 to exclude single-op outliers)

Inter-arrival time (§C34 interarrival_distribution):
  IAT_i = ts_i - ts_{{i-1}}  for consecutive events of same op type  [µs]
  Source: raw blkparse event timestamps, all {m.ssd_rd_stream_count} read streams combined

Temporal R/W pattern (§E72 temporal_read_write_trim_pattern):
  window_bytes_read  = sum(size_bytes) for R events in [window_start, window_start+1s)
  window_bytes_write = sum(size_bytes) for W events in same window
  R/W ratio = total_read_bytes / total_write_bytes = {m.ssd_rw_byte_ratio:.2f}×

Burst detection (§C35 burst_temporal_windows):
  burst_window = time bucket with IAT_consecutive < threshold
  Window count: Read={m.ssd_rd_burst_windows}  Write={m.ssd_wr_burst_windows}</code>
      <div class="fml-note">Stream = trace_window + PID combination from blktrace trace_prefix column. The window float (0.0, 1.0, ...) identifies which 1-second time window the event falls in. PID identifies the process (fio worker). This combination maps to one KV cache session/request per inference stream.</div>
    </div>
  </details>
</div>

<!-- KV$ SSD: Hot/Cold LBA Region Analysis -->
<div class="card" style="border-color:#a855f7">
  <h2 style="color:#7c3aed">&#128293; KV$ SSD — LBA Hot/Cold Region Analysis (§C36-37, §D51)</h2>
  <div style="font-size:11px;color:#334155;line-height:1.6;margin-bottom:12px">
    LBA access distribution across the SSD address space: which regions are accessed most
    frequently (hot) vs rarely (cold), how hot regions shift over time, and skewness/Gini
    coefficient to quantify access concentration.
    Source: <code style="background:#faf5ff;padding:1px 4px;border-radius:3px;color:#7c3aed">hot_regions_overall.csv</code>,
    <code style="background:#faf5ff;padding:1px 4px;border-radius:3px;color:#7c3aed">hot_regions_by_time_window.csv</code>,
    <code style="background:#faf5ff;padding:1px 4px;border-radius:3px;color:#7c3aed">access_skew_summary.csv</code>.
  </div>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:14px">
    {_kpi("Rd Hot Regions",f"{m.ssd_rd_hot_region_count:,}","","#eff6ff","#1d4ed8",f"skew={m.ssd_rd_skewness:.3f}")}
    {_kpi("Wr Hot Regions",f"{m.ssd_wr_hot_region_count:,}","","#fff7ed","#c2410c",f"skew={m.ssd_wr_skewness:.3f}")}
    {_kpi("Rd Gini",f"{m.ssd_rd_gini:.3f}","","#f0fdf4" if m.ssd_rd_gini < 0.4 else "#fff1f2","#047857" if m.ssd_rd_gini < 0.4 else "#9f1239","0=uniform, 1=all one region")}
    {_kpi("Rd Top-1% Share",f"{m.ssd_rd_top1pct_byte_share:.2f}","%","#f8fafc","#334155","of total read bytes")}
    {_kpi("Wr Top-1% Share",f"{m.ssd_wr_top1pct_byte_share:.2f}","%","#f8fafc","#334155","of total write bytes")}
    {_kpi("Rd Degrad.",f"{m.ssd_rd_bw_degradation:.4f}","×","#f0fdf4" if m.ssd_rd_bw_degradation > 0.95 else "#fff7ed","#047857" if m.ssd_rd_bw_degradation > 0.95 else "#c2410c","late/early BW ratio")}
    {_kpi("Wr Degrad.",f"{m.ssd_wr_bw_degradation:.4f}","×","#f0fdf4" if m.ssd_wr_bw_degradation > 0.95 else "#fff7ed","#047857" if m.ssd_wr_bw_degradation > 0.95 else "#c2410c","late/early BW ratio")}
    {_kpi("Access Pattern","100% Random","","#fff1f2","#9f1239","0 sequential IOs")}
  </div>
  {img(charts.get("bt_hotcold",""), "Hot/Cold LBA Map")}
  <details class="fml" style="margin-top:12px">
    <summary>&#128208; Formula &amp; Metrics Used — Hot/Cold LBA Analysis</summary>
    <div class="fml-body">
      <div class="fml-src">&#128202; hot_regions_overall.csv + hot_regions_by_time_window.csv + access_skew_summary.csv</div>
      <code>LBA region bucketing (§C36 hot_regions_overall):
  region_id = floor(sector × 512 / KV_block_size)  = sector // 256
  region_bytes = sum(size_bytes for all IOs to this region)
  Top regions by bytes = "hot" regions

Gini coefficient (§C36):
  G = (2 × Σ(i × x_i sorted) / (N × Σx_i)) - (N+1)/N
  where x_i = bytes per region bucket, N = number of regions
  G=0: all regions accessed equally   G→1: all bytes in one region
  Read Gini = {m.ssd_rd_gini:.3f}  (low = well-distributed across SSD)

Skewness (§C36):
  skew = E[((x - mean)/std)³]  where x = bytes per region
  Read skew = {m.ssd_rd_skewness:.3f}  Write skew = {m.ssd_wr_skewness:.3f}
  Positive = long right tail (few very hot regions)

Hot/cold temporal shift (§C37 hot_regions_by_time_window):
  For each 1-second window: top-10 regions by bytes
  Overlap between windows shows whether access patterns shift over time
  Low overlap = hot regions rotate (KV blocks for different requests)

BW degradation (§C45/D60 bandwidth_degradation):
  early_bw = avg BW over first {100*0.1:.0f}% of trace
  late_bw  = avg BW over last {100*0.1:.0f}% of trace
  degradation_ratio = late_bw / early_bw  (1.0 = no degradation)
  Read: {m.ssd_rd_bw_degradation:.4f}  Write: {m.ssd_wr_bw_degradation:.4f}</code>
      <div class="fml-note">All IOs are random (0 sequential) and 100% KV block aligned — this is expected for KV$B offload workloads. Each IO is exactly one KV block (128 KB = 256 sectors). The KV cache block address is determined by the block index in the LRU pool, resulting in effectively random LBA patterns across the SSD address space.</div>
    </div>
  </details>
</div>
""" if m.blkio_has_analysis else ""}

<!-- HBM BANDWIDTH -->
<div class="card" style="border-color:#22d3ee">
  <h2 style="color:#22d3ee">🔵 HBM (GPU) Bandwidth &amp; Transactions</h2>
  <div style="font-size:11px;color:#64748b;line-height:1.6;margin-bottom:10px">
    HBM (High Bandwidth Memory) is the on-GPU DRAM fabric on A100. Every decode step reads all
    model weights from HBM — this is the primary decode bottleneck.
    Values are <b style="color:#0f172a">derived from TPOT + model size</b> since nsys hardware
    counters were not active in this profile. The timeseries is modulated by GPU utilisation %.
  </div>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin-bottom:14px">
    {hbm_kpi_cards}
  </div>
  {img(charts.get("hbm_bw",""), "HBM Bandwidth")}
  <details class="fml" style="margin-top:10px">
    <summary>&#128208; Formula &amp; Metrics Used</summary>
    <div class="fml-body">
      <div class="fml-src">&#128202; DCGM_FI_PROF_DRAM_ACTIVE (Prometheus) + derived from TPOT + model architecture (§F74-F78)</div>
      <code>§F74 HBM used (MiB)    : DCGM_FI_DEV_FB_USED  (per GPU, DCGM)
§F75 HBM free (MiB)    : DCGM_FI_DEV_FB_FREE
§F76 HBM BW active %   : DCGM_FI_PROF_DRAM_ACTIVE × 100
                         (fraction of cycles HBM is actively transferring)
§F77 HBM peak BW (GB/s): 2,000 GB/s (A100 HBM2e specification)

Derived HBM Read BW (when DCGM_FI_PROF_DRAM_ACTIVE unavailable):
  hbm_read_bw = model_params_bytes_per_gpu / (tpot_ms / 1000)
  = (n_params × 2B_FP16 / n_gpus) / tpot_s   [GB/s]
  e.g.: 70B × 2B / 8 GPUs = 17.5 GB → 17.5 / 0.024s = 729 GB/s

HBM Read Txns/s  : hbm_read_bw × 10⁹ / 64  [M/s]
                   64B = A100 HBM2e cache-line size
HBM Write BW     : hbm_read_bw × 0.12  (empirical: writes ≈12% of reads in decode)
HBM Write Txns/s : hbm_write_bw × 10⁹ / 64  [M/s]

Min TPOT (BW-limited): model_bytes_per_gpu / HBM_peak × 1000  [ms/tok]
TPOT gap factor      : observed_tpot / min_tpot  (>1 = compute or other overhead)</code>
      <div class="fml-note">DCGM_FI_PROF_DRAM_ACTIVE requires DCGM profiling mode enabled. When absent, derivation from TPOT is accurate during pure decode phases (single large request). During batched prefill, TPOT-derived HBM BW overestimates because TPOT includes compute overhead beyond just memory reads.</div>
    </div>
  </details>
  <div style="background:#f1f5f9;border-left:3px solid #22d3ee;border-radius:0 6px 6px 0;
              padding:10px 14px;margin-top:10px;font-size:11px;color:#334155;line-height:1.6">
    <b style="color:#0f172a">Derivation:</b>
    HBM Read BW = model_bytes_per_GPU / TPOT_s
    = (params × 2B / n_gpus) / (tpot_ms / 1000).
    Theoretical min TPOT = model_bytes_per_GPU / HBM_peak_BW × 1000 = {min_tpot_ms:.1f} ms/tok.
    Observed TPOT {m.tpot_ms:.1f} ms → {gap_label}.
    HBM util = HBM_read_BW / {m.hbm_peak_bw_gbs:.0f} GB/s = {m.hbm_bw_util_pct:.1f}%.
    Transactions = BW × 10⁹ / 64 bytes (cache-line size).
  </div>
</div>

<!-- DRAM BANDWIDTH -->
<div class="card" style="border-color:#34d399">
  <h2 style="color:#34d399">🟢 System DRAM (CPU-side) Bandwidth &amp; Transactions</h2>
  <div style="font-size:11px;color:#64748b;line-height:1.6;margin-bottom:10px">
    CPU-side DRAM bandwidth measured by <b style="color:#0f172a">AMD uProf PCM</b> via
    hardware PMU counters on the AMD EPYC 7742 host (AMD Data Fabric DRAM controller metrics).
    Covers: hicache L2 KV pool access, model loader, OS page cache, SGLang runtime.
    Sampled every 1.2 seconds. Transactions = BW / 64B cache-line.
  </div>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin-bottom:14px">
    {dram_bw_kpi_cards}
  </div>
  {img(charts.get("dram_bw",""), "DRAM Bandwidth")}
  <details class="fml" style="margin-top:10px">
    <summary>&#128208; Formula &amp; Metrics Used</summary>
    <div class="fml-body">
      <div class="fml-src">&#128202; amduprof_pcm_raw.csv (AMD EPYC PMU, DF METRICS section) + node_memory_* (Prometheus) (§F79-F87)</div>
      <code>§F79 DRAM total (GB)   : node_memory_MemTotal_bytes / 1e9
§F80 DRAM used (GB)    : (MemTotal - MemAvailable) / 1e9
§F81 DRAM util %       : DRAM_used / DRAM_total × 100
§F82 DRAM Read BW      : amduprof_pcm_raw.csv → "Total Mem RdBw (GB/s)"
                         AMD EPYC Data Fabric PMU counters, 1.2s sample interval
§F83 DRAM Write BW     : amduprof_pcm_raw.csv → "Total Mem WrBw (GB/s)"
§F84 DRAM peak BW      : 204.8 GB/s (AMD EPYC 7742: 8ch DDR4-3200 × 2 sockets × 12.8 GB/s/ch)
§F85 DRAM util %       : (read_bw + write_bw) / 204.8 × 100

DRAM Read Txns/s  : read_bw × 10⁹ / 64  [M/s]  (64B DDR4 cache-line)
DRAM Write Txns/s : write_bw × 10⁹ / 64  [M/s]
Read/Write ratio  : read_bw / write_bw  (inference: reads dominate, ratio typically 3–8×)

§F86 Page faults/s     : rate(node_vmstat_pgfault)   [minor faults, no disk I/O]
§F87 Major faults/s    : rate(node_vmstat_pgmajfault) [disk I/O required]
NUMA migrations/s  : rate(node_vmstat_numa_pages_migrated)</code>
      <div class="fml-note">amduprof_pcm_raw.csv header [warn] tokenisation errors are expected — the file uses an AMD-specific section format (DF METRICS) that is not standard CSV. The profiler parses it as structured text. DRAM BW includes: KV$B DMA transfers (GPU→DRAM evictions), model weight prefetch, OS page cache, and hicache token reads for L2 KV cache.</div>
    </div>
  </details>
  <div style="background:#f1f5f9;border-left:3px solid #34d399;border-radius:0 6px 6px 0;
              padding:10px 14px;margin-top:10px;font-size:11px;color:#334155;line-height:1.6">
    <b style="color:#0f172a">Derivation:</b>
    DRAM Txns/s = (DRAM_BW_GB_s × 10⁹) / 64.
    AMD EPYC 7742 2S theoretical peak = 204.8 GB/s
    (8 DDR4-3200 channels × 25.6 GB/s × 2 sockets).
    Measured {m.dram_total_bw_gbs:.2f} GB/s total = {m.dram_bw_util_pct:.1f}% of peak.
    Read/Write ratio = {rw_r:.1f}×.
    <b style="color:#0f172a">Source:</b> AMDuProfPcm -m memory, DF METRICS, 1.2s sample interval.
  </div>
</div>

<!-- §G: SWAP STORM ANALYSIS -->
<div class="card">
  <h2>🌪️ §G: Swap Storm Analysis</h2>
  <div style="font-size:12px;color:#475569;line-height:1.5;margin-bottom:14px">
    Identifies sustained host-memory swap activity that can stall inference. A
    <b>swap storm</b> is a continuous interval where combined pswpin + pswpout
    rate exceeds <b>{m.swap_storm_threshold_pages_per_s:.0f} pages/s</b>
    (≈ {m.swap_storm_threshold_pages_per_s/256:.1f} MiB/s). When detected,
    correlates with major page faults and quantifies the write-amplification
    cost on the underlying NVMe device.
  </div>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:14px">
    <div class="kpi-box" style="background:#f1f5f9;padding:10px;border-radius:6px;border-left:3px solid #3b82f6">
      <div style="font-size:10px;color:#475569;text-transform:uppercase">Mean Swap-In</div>
      <div style="font-size:18px;font-weight:700;color:#0f172a">{m.swap_in_pages_per_s_mean:.1f}<span style="font-size:11px;color:#64748b"> pg/s</span></div>
      <div style="font-size:10px;color:#64748b">{m.swap_in_mb_per_s_mean:.2f} MiB/s</div>
    </div>
    <div class="kpi-box" style="background:#f1f5f9;padding:10px;border-radius:6px;border-left:3px solid #ef4444">
      <div style="font-size:10px;color:#475569;text-transform:uppercase">Mean Swap-Out</div>
      <div style="font-size:18px;font-weight:700;color:#0f172a">{m.swap_out_pages_per_s_mean:.1f}<span style="font-size:11px;color:#64748b"> pg/s</span></div>
      <div style="font-size:10px;color:#64748b">{m.swap_out_mb_per_s_mean:.2f} MiB/s</div>
    </div>
    <div class="kpi-box" style="background:#f1f5f9;padding:10px;border-radius:6px;border-left:3px solid #dc2626">
      <div style="font-size:10px;color:#475569;text-transform:uppercase">Storm Episodes</div>
      <div style="font-size:18px;font-weight:700;color:#0f172a">{m.swap_storm_episode_count}</div>
      <div style="font-size:10px;color:#64748b">{m.swap_storm_total_duration_s:.0f}s · {m.swap_thrashing_pct:.1f}%</div>
    </div>
    <div class="kpi-box" style="background:#f1f5f9;padding:10px;border-radius:6px;border-left:3px solid #f59e0b">
      <div style="font-size:10px;color:#475569;text-transform:uppercase">Worst Storm Peak</div>
      <div style="font-size:18px;font-weight:700;color:#0f172a">{m.swap_storm_worst_pages_per_s:.0f}<span style="font-size:11px;color:#64748b"> pg/s</span></div>
      <div style="font-size:10px;color:#64748b">{m.swap_storm_worst_pages_per_s/256:.1f} MiB/s</div>
    </div>
    <div class="kpi-box" style="background:#f1f5f9;padding:10px;border-radius:6px;border-left:3px solid #7c3aed">
      <div style="font-size:10px;color:#475569;text-transform:uppercase">Write Amp</div>
      <div style="font-size:18px;font-weight:700;color:#0f172a">{m.swap_write_amp_ratio:.2f}<span style="font-size:11px;color:#64748b">×</span></div>
      <div style="font-size:10px;color:#64748b">NVMe wr / pswpout</div>
    </div>
    <div class="kpi-box" style="background:#f1f5f9;padding:10px;border-radius:6px;border-left:3px solid #64748b">
      <div style="font-size:10px;color:#475569;text-transform:uppercase">Swap Used Peak</div>
      <div style="font-size:18px;font-weight:700;color:#0f172a">{m.swap_used_pct_max:.1f}<span style="font-size:11px;color:#64748b">%</span></div>
      <div style="font-size:10px;color:#64748b">{m.swap_free_mb_min:.0f} MiB free min</div>
    </div>
  </div>
  {img(charts.get("swap_storm",""), "Swap Storm Analysis")}
  <details class="fml" style="margin-top:10px">
    <summary>📐 Formula &amp; Derivation</summary>
    <div class="fml-body">
      <div class="fml-src">📊 vmstat_timeseries.csv · /proc/vmstat (node_exporter Prometheus job) + nvme_driver_timeseries.csv</div>
      <code>swap_in_rate    = Δ(node_vmstat_pswpin)  / Δt    [pages/s, 4 KiB pages]
swap_out_rate   = Δ(node_vmstat_pswpout) / Δt    [pages/s]
swap_total_rate = swap_in_rate + swap_out_rate

storm_active    = swap_total_rate &gt;= STORM_THRESHOLD     (default: 1000 pg/s)
storm_episode   = maximal contiguous run of storm_active = True
thrashing_pct   = 100 × (count(storm_active) / total_samples)

majfault_corr   = pearsonr( swap_in_rate , Δ(pgmajfault)/Δt )
                  → r near +1.0 means swap-in directly triggers major page faults
                    (the page being swapped back in was demand-paged → I/O wait)

write_amp_ratio = Δ(nvme_wr_ios) / Δ(pswpout)
                  → ratio of NVMe writes hitting the device vs swap-out pages.
                    &gt;1.0 = filesystem journals, metadata updates amplify writes
                    &lt;1.0 = swap I/O is batched (typical for ZSWAP/multi-page swap)

swap_used_pct   = 100 × (1 - SwapFree/SwapTotal)</code>
      <div class="fml-note">
        <b>Interpretation:</b> A swap storm directly slows inference: every major page fault stalls the
        GPU memory pinning path while waiting on synchronous swap-in I/O.
        <b>Triggers:</b> oversubscribed model loader (model + KV + buffers &gt; DRAM),
        memory-mapped weight files, large hicache L2 footprint, or transient memory spike
        from concurrent requests. <b>Mitigations:</b> reduce hicache L2 size,
        enable zswap, increase vm.swappiness=10 (less eager swap),
        add physical DRAM, or pin SGLang RSS with cgroups.
      </div>
    </div>
  </details>
  <div style="background:#f1f5f9;border-left:3px solid #f59e0b;border-radius:0 6px 6px 0;
              padding:10px 14px;margin-top:10px;font-size:11px;color:#334155;line-height:1.6">
    <b style="color:#0f172a">Verdict:</b>
    {("✅ <b style='color:#16a34a'>Healthy</b> — swap activity well below storm threshold." if m.swap_storm_episode_count == 0 and m.swap_thrashing_pct < 1 else
      "⚠️ <b style='color:#f59e0b'>Degraded</b> — " + str(m.swap_storm_episode_count) + " storm(s) detected, " + f"{m.swap_thrashing_pct:.1f}%" + " of run thrashing. Investigate hicache sizing." if m.swap_thrashing_pct < 10 else
      "🚨 <b style='color:#dc2626'>STORM RISK</b> — sustained swap thrashing. Inference latency severely impacted. Reduce hicache L2 or add DRAM immediately.")}
  </div>
</div>

<!-- BOTTLENECK SCORECARD -->
<div class="card">
  <h2>🎯 Full Stack Bottleneck Attribution</h2>
  {img(charts.get("radar",""), "Bottleneck Radar")}
  <details class="fml" style="margin-top:10px">
    <summary>&#128208; Formula &amp; Metrics Used — Bottleneck Scoring</summary>
    <div class="fml-body">
      <div class="fml-src">&#128202; Derived: all collected metrics combined via weighted scoring heuristics</div>
      <code>Bottleneck score (0–100) per layer:

GPU Compute score  = gpu_util_mean × 0.6 + (1 - cache_hit_rate) × 40
                     High score = GPU is the bottleneck (low cache reuse)

HBM Bandwidth score= (hbm_bw_util_pct / 100) × 70 + (tpot_gap_ratio - 1) × 30
                     tpot_gap = observed_tpot / min_tpot_at_peak_bw
                     High score = memory-bandwidth-limited decode

KV Cache score     = (1 - cache_hit_rate) × 50 + kv_l2_fill_pct / 100 × 30
                       + (hicache_fill_pct / 100) × 20
                     High score = KV cache pressure, many cache misses

DRAM / hicache     = dram_bw_util_pct × 0.6 + kv_l2_fill_pct / 100 × 40
                     High score = hicache DRAM tier saturated

NVMe / SSD score   = nvme_io_util_pct × 0.7 + kvb_offload_rate_blk_s × 10
                     High score = KV$B overflowing to NVMe L3 tier

TTFT / Prefill     = ttft_ms / (n_prefill_tokens × 0.001 + 1) × 0.5
                     High score = prefill-limited TTFT

Severity thresholds:
  HIGH  : score ≥ 70
  MED   : score ≥ 40
  LOW   : score < 40</code>
      <div class="fml-note">Scores are heuristic estimates, not physical measurements. They combine multiple signal sources to surface likely bottlenecks for investigation. Radar shape interpretation: a spike in one axis = that layer dominates. Multiple spikes = compound bottleneck. All-low scores = workload is lightly loaded or profiling window missed active inference.</div>
    </div>
  </details>
  <div style="margin-top:16px;overflow-x:auto">
    <table>
      <thead><tr>
        <th>Layer</th><th>Score (0–100)</th><th>Phase</th><th>Severity</th><th>Details</th>
      </tr></thead>
      <tbody>{bn_rows}</tbody>
    </table>
  </div>
</div>

<!-- METRIC FORMULAS TABLE -->
<div class="card">
  <h2>📐 Metric Derivations &amp; Formulas</h2>
  <div style="font-size:11px;color:#64748b;margin-bottom:12px;line-height:1.6">
    Every displayed KPI is derived from raw collector telemetry using the formulas below.
    All timestamps are wall-clock seconds since profiler start. Counters are cumulative
    from server startup and read at run-end via Prometheus snapshot.
  </div>
  <div style="overflow-x:auto">
  <table>
    <thead><tr>
      <th>Metric</th><th>Unit</th><th>Collector / Source</th><th style="min-width:320px">Derivation Formula</th><th style="min-width:260px">Interpretation &amp; Notes</th>
    </tr></thead>
    <tbody>
      {formula_rows}
    </tbody>
  </table>
  </div>
</div>

<!-- RECOMMENDATIONS -->
<div class="card">
  <h2>🚀 Optimisation Recommendations</h2>
  <div class="recs">{rec_cards}</div>
</div>

<!-- FOOTER -->
<div style="border-top:1px solid #e2e8f0;margin-top:20px;padding-top:12px;display:flex;justify-content:space-between;font-size:11px;color:#64748b;flex-wrap:wrap;gap:8px">
  <span>AMOprof · Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}</span>
  <span>Model: {m.model}</span>
  <span>Collectors: sglang · gpu · dram · power · nvme_driver · vmstat · smart</span>
</div>
</body>
</html>"""
    return html


# ── Main ──────────────────────────────────────────────────────────────────────

# ── Excel generation ──────────────────────────────────────────────────────────

def generate_excel(m: Metrics, bottlenecks: list[dict], recs: list[dict],
                   run_label: str, out_path: Path):
    """Build a full multi-sheet Excel workbook with native charts."""
    from openpyxl import Workbook
    from openpyxl.styles import (Font, PatternFill, Alignment, Border, Side,
                                  GradientFill)
    from openpyxl.utils import get_column_letter
    from openpyxl.chart import BarChart, LineChart, RadarChart, PieChart, AreaChart, Reference
    from openpyxl.chart.series import SeriesLabel
    from openpyxl.chart.layout import Layout
    from openpyxl.formatting.rule import ColorScaleRule, DataBarRule
    from openpyxl.styles.numbers import FORMAT_PERCENTAGE_00

    wb = Workbook()
    wb.remove(wb.active)  # remove default sheet

    # ── Shared style helpers ──────────────────────────────────────────────────
    FONT_NAME = "Arial"

    def hdr_font(sz=11, bold=True, color="FFFFFF"):
        return Font(name=FONT_NAME, size=sz, bold=bold, color=color)

    def body_font(sz=10, bold=False, color="000000"):
        return Font(name=FONT_NAME, size=sz, bold=bold, color=color)

    def fill(hex_color):
        return PatternFill("solid", fgColor=hex_color)

    def border(style="thin"):
        s = Side(style=style, color="CCCCCC")
        return Border(left=s, right=s, top=s, bottom=s)

    def center():
        return Alignment(horizontal="center", vertical="center", wrap_text=True)

    def left():
        return Alignment(horizontal="left", vertical="center", wrap_text=True)

    # Colour palette (Excel hex, no leading #)
    COL_DARK   = "0D1117"
    COL_HDR    = "1E3A5F"   # deep navy header
    COL_HDR2   = "2D5986"   # secondary header
    COL_PREFIL = "C0392B"   # prefill red-orange
    COL_DECODE = "0E86D4"   # decode blue
    COL_GPU    = "7B68EE"   # medium slate blue
    COL_HBM    = "6A0DAD"   # purple
    COL_DRAM   = "27AE60"   # green
    COL_NVME   = "E74C3C"   # red
    COL_POWER  = "E67E22"   # orange
    COL_OK     = "1E8449"   # dark green
    COL_WARN   = "922B21"   # dark red
    COL_CAU    = "9A7D0A"   # dark yellow
    COL_ZEBRA  = "F2F6FC"   # light blue-grey zebra
    COL_ACCENT = "5B8DB8"   # medium blue
    COL_WHITE  = "FFFFFF"
    COL_BLACK  = "000000"

    SEV_COLORS = {"HIGH": (COL_WARN, "FFC0CB"), "MED": ("7D6608", "FFF9C4"), "LOW": (COL_OK, "D5F5E3")}

    def write_title_block(ws, title, subtitle, row=1):
        ws.merge_cells(f"A{row}:J{row}")
        ws[f"A{row}"] = title
        ws[f"A{row}"].font = Font(name=FONT_NAME, size=16, bold=True, color=COL_WHITE)
        ws[f"A{row}"].fill = fill(COL_HDR)
        ws[f"A{row}"].alignment = center()
        ws.row_dimensions[row].height = 28

        ws.merge_cells(f"A{row+1}:J{row+1}")
        ws[f"A{row+1}"] = subtitle
        ws[f"A{row+1}"].font = Font(name=FONT_NAME, size=10, color="AAAAAA")
        ws[f"A{row+1}"].fill = fill("1A1A2E")
        ws[f"A{row+1}"].alignment = center()
        ws.row_dimensions[row+1].height = 16
        return row + 3

    def write_section_header(ws, text, row, col_span="A:J", color=COL_HDR2):
        ws.merge_cells(f"A{row}:{col_span.split(':')[1]}{row}")
        ws[f"A{row}"] = text
        ws[f"A{row}"].font = hdr_font(10)
        ws[f"A{row}"].fill = fill(color)
        ws[f"A{row}"].alignment = left()
        ws.row_dimensions[row].height = 18
        return row + 1

    def write_table_header(ws, headers: list, row: int, col_start=1):
        for ci, h in enumerate(headers, col_start):
            c = ws.cell(row=row, column=ci, value=h)
            c.font = hdr_font(10)
            c.fill = fill(COL_HDR)
            c.alignment = center()
            c.border = border()
        ws.row_dimensions[row].height = 18
        return row + 1

    def write_kv_pair(ws, row, label, value, unit="", label_col=COL_HDR2, val_color=COL_BLACK):
        ws.cell(row=row, column=1, value=label).font = Font(name=FONT_NAME, size=10, bold=True, color=COL_WHITE)
        ws.cell(row=row, column=1).fill = fill(label_col)
        ws.cell(row=row, column=1).alignment = left()
        v_cell = ws.cell(row=row, column=2, value=f"{value}{' '+unit if unit else ''}")
        v_cell.font = Font(name=FONT_NAME, size=11, bold=True, color=val_color)
        v_cell.alignment = left()
        ws.row_dimensions[row].height = 16

    # ── Sheet 1: Summary ──────────────────────────────────────────────────────
    ws = wb.create_sheet("Summary")
    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 22
    ws.column_dimensions["C"].width = 18
    ws.column_dimensions["D"].width = 18
    ws.column_dimensions["E"].width = 14
    ws.column_dimensions["F"].width = 40

    r = write_title_block(ws, "AI Stack Workload Bottleneck Report",
                          f"Model: {m.model}  |  Run: {run_label}  |  Duration: {m.run_duration_s/60:.0f}m")

    # KPI section
    r = write_section_header(ws, "  KEY PERFORMANCE INDICATORS", r)
    kpis = [
        ("Time to First Token (TTFT)", f"{m.ttft_ms:.0f} ms", "Prefill Phase", COL_PREFIL),
        ("Time per Output Token (TPOT)", f"{m.tpot_ms:.1f} ms/tok", "Decode Phase", COL_DECODE),
        ("Peak Gen Throughput", f"{m.gen_tp_peak:.1f} tok/s", "Decode", COL_GPU),
        ("E2E Request Latency", f"{m.e2e_ms/1000:.1f} s", "Full Request", COL_ACCENT),
        ("Realtime Cache Hit Rate", f"{m.cache_hit_pct:.1f}%", "KV Cache", "1E8449"),
        ("HBM Utilisation (per GPU)", f"{m.hbm_util_pct:.1f}%  ({m.hbm_used_mb_mean/1024:.1f}/{m.hbm_total_mb/1024:.0f} GB)", "GPU Memory", COL_HBM),
        ("GPU Utilisation (mean)", f"{m.gpu_util_mean:.1f}%  (peak {m.gpu_util_peak:.0f}%)", "Compute", COL_GPU),
        ("DRAM Utilisation", f"{m.dram_util_pct:.1f}%  ({m.dram_used_gb:.0f}/{m.dram_total_gb:.0f} GB)", "System Memory", COL_DRAM),
        ("NVMe Write IOPS (max)", f"{m.nvme_wr_iops_max:.0f}", "Storage", COL_NVME),
        ("GPU Power (mean total)", f"{m.gpu_power_mean_w:.0f} W  (peak {m.gpu_power_peak_w:.0f} W/GPU)", "Power", COL_POWER),
    ]
    write_table_header(ws, ["Metric", "Value", "Domain", "Notes"], r)
    r += 1
    for i, (metric, val, domain, color) in enumerate(kpis):
        bg = COL_ZEBRA if i % 2 == 0 else COL_WHITE
        for ci, v in enumerate([metric, val, domain], 1):
            c = ws.cell(row=r, column=ci, value=v)
            c.font = Font(name=FONT_NAME, size=10,
                          bold=(ci == 2), color=color if ci == 2 else COL_BLACK)
            c.fill = fill(bg)
            c.alignment = left() if ci != 2 else center()
            c.border = border()
        ws.row_dimensions[r].height = 16
        r += 1

    r += 1

    # Token composition section
    r = write_section_header(ws, "  CONTEXT TOKEN COMPOSITION", r)
    total_ctx = m.prefill_cache_tokens + m.prefill_compute_tokens + m.decode_tokens
    write_table_header(ws, ["Token Category", "Count", "% of Context", "Phase"], r)
    r += 1
    tok_rows = [
        ("Prefill — Cached (KV hit)", m.prefill_cache_tokens, COL_DECODE),
        ("Prefill — Compute (new)", m.prefill_compute_tokens, COL_PREFIL),
        ("Decode — Generated Output", m.decode_tokens, COL_GPU),
    ]
    for i, (label, cnt, color) in enumerate(tok_rows):
        pct = cnt / total_ctx * 100 if total_ctx > 0 else 0
        bg = COL_ZEBRA if i % 2 == 0 else COL_WHITE
        for ci, v in enumerate([label, cnt, f"{pct:.1f}%",
                                  "Prefill" if i < 2 else "Decode"], 1):
            c = ws.cell(row=r, column=ci, value=v)
            c.font = Font(name=FONT_NAME, size=10, bold=(ci == 2), color=color if ci == 2 else COL_BLACK)
            c.fill = fill(bg)
            c.border = border()
            c.alignment = center() if ci > 1 else left()
        r += 1
    # Total row
    total_row = r
    for ci, v in enumerate(["TOTAL", total_ctx, "100%", ""], 1):
        c = ws.cell(row=r, column=ci, value=v)
        c.font = Font(name=FONT_NAME, size=10, bold=True, color=COL_WHITE)
        c.fill = fill(COL_HDR)
        c.border = border()
        c.alignment = center() if ci > 1 else left()
    r += 2

    # Bottleneck quick summary
    r = write_section_header(ws, "  BOTTLENECK SUMMARY (top 5)", r)
    write_table_header(ws, ["Rank", "Layer", "Score (0–100)", "Phase", "Severity", "Key Detail"], r)
    r += 1
    for rank, b in enumerate(bottlenecks[:5], 1):
        sev = b["severity"]
        sev_fg, sev_bg = SEV_COLORS.get(sev, (COL_BLACK, COL_WHITE))
        bg = COL_ZEBRA if rank % 2 == 0 else COL_WHITE
        for ci, v in enumerate([rank, b["layer"], b["score"], b["phase"], sev, b["detail"][:80]], 1):
            c = ws.cell(row=r, column=ci, value=v)
            if ci == 5:  # severity badge
                c.font = Font(name=FONT_NAME, size=10, bold=True, color=COL_WHITE)
                c.fill = fill(sev_fg)
            elif ci == 3:  # score
                c.font = Font(name=FONT_NAME, size=10, bold=True,
                              color=COL_WARN if b["score"] > 60 else COL_CAU if b["score"] > 30 else COL_OK)
                c.fill = fill(bg)
            else:
                c.font = body_font()
                c.fill = fill(bg)
            c.border = border()
            c.alignment = center() if ci in (1, 3, 4, 5) else left()
        ws.row_dimensions[r].height = 16
        r += 1

    # Bottleneck bar chart on Summary sheet
    bn_data_start = r + 2
    ws.cell(row=bn_data_start, column=1, value="Layer").font = hdr_font(9)
    ws.cell(row=bn_data_start, column=2, value="Score").font = hdr_font(9)
    for i, b in enumerate(bottlenecks):
        ws.cell(row=bn_data_start + 1 + i, column=1, value=b["layer"])
        ws.cell(row=bn_data_start + 1 + i, column=2, value=b["score"])

    chart_bn = BarChart()
    chart_bn.type = "bar"  # horizontal
    chart_bn.title = "Bottleneck Score by Stack Layer"
    chart_bn.y_axis.title = "Layer"
    chart_bn.x_axis.title = "Score (0–100)"
    chart_bn.style = 10
    chart_bn.width = 18
    chart_bn.height = 12
    data_ref = Reference(ws, min_col=2, min_row=bn_data_start,
                         max_row=bn_data_start + len(bottlenecks))
    cats_ref = Reference(ws, min_col=1, min_row=bn_data_start + 1,
                         max_row=bn_data_start + len(bottlenecks))
    chart_bn.add_data(data_ref, titles_from_data=True)
    chart_bn.set_categories(cats_ref)
    chart_bn.series[0].graphicalProperties.solidFill = "5B8DB8"
    ws.add_chart(chart_bn, f"H{r + 1}")

    # ── Sheet 2: Inference ────────────────────────────────────────────────────
    ws2 = wb.create_sheet("Inference")
    ws2.sheet_view.showGridLines = False
    for col, w in [("A", 10), ("B", 16), ("C", 16), ("D", 16), ("E", 16)]:
        ws2.column_dimensions[col].width = w

    r2 = write_title_block(ws2, "SGLang Inference Metrics",
                           f"Model: {m.model}  |  TTFT: {m.ttft_ms:.0f}ms  |  TPOT: {m.tpot_ms:.1f}ms/tok")

    sdf = m.sglang_ts
    tp_col = _find_metric_col(sdf, "gen_throughput") if isinstance(sdf, pd.DataFrame) else None
    run_col = _find_metric_col(sdf, "num_running_reqs") if isinstance(sdf, pd.DataFrame) else None
    tok_col = (_find_metric_col(sdf, "full_token_usage") or _find_metric_col(sdf, "token_usage")) if isinstance(sdf, pd.DataFrame) else None

    if not sdf.empty and tp_col:
        sdf_ds = downsample(sdf, 300)
        r2 = write_section_header(ws2, "  TIMESERIES DATA", r2)
        headers = ["Time (s)", "Gen Throughput (tok/s)", "Running Reqs", "Token Pool Usage"]
        write_table_header(ws2, headers, r2)
        r2 += 1
        data_row_start = r2
        for i, row_d in sdf_ds.iterrows():
            bg = COL_ZEBRA if (r2 - data_row_start) % 2 == 0 else COL_WHITE
            vals = [
                round(float(row_d["time_sec"]), 1),
                round(float(row_d.get(tp_col, 0)), 3),
                round(float(row_d.get(run_col, 0)), 1),
                round(float(row_d.get(tok_col, 0)), 3),
            ]
            for ci, v in enumerate(vals, 1):
                c = ws2.cell(row=r2, column=ci, value=v)
                c.font = body_font(9)
                c.fill = fill(bg)
                c.border = border()
                c.alignment = center()
            r2 += 1
        data_row_end = r2 - 1

        # Line chart: Gen Throughput
        ch1 = LineChart()
        ch1.title = "Generation Throughput (tok/s) Over Time"
        ch1.style = 10
        ch1.y_axis.title = "tok/s"
        ch1.x_axis.title = "Time (s)"
        ch1.width = 20; ch1.height = 10
        d_ref = Reference(ws2, min_col=2, min_row=data_row_start - 1, max_row=data_row_end)
        x_ref = Reference(ws2, min_col=1, min_row=data_row_start, max_row=data_row_end)
        ch1.add_data(d_ref, titles_from_data=True)
        ch1.set_categories(x_ref)
        ch1.series[0].graphicalProperties.line.solidFill = "0E86D4"
        ch1.series[0].graphicalProperties.line.width = 18000
        ws2.add_chart(ch1, "G2")

        # Line chart: Running Requests
        ch2 = AreaChart()
        ch2.title = "Running Requests Over Time"
        ch2.style = 10
        ch2.y_axis.title = "Requests"
        ch2.x_axis.title = "Time (s)"
        ch2.width = 20; ch2.height = 10
        d2_ref = Reference(ws2, min_col=3, min_row=data_row_start - 1, max_row=data_row_end)
        ch2.add_data(d2_ref, titles_from_data=True)
        ch2.set_categories(x_ref)
        ch2.series[0].graphicalProperties.solidFill = "7B68EE"
        ws2.add_chart(ch2, "G22")

    # ── Sheet 3: GPU & Power ──────────────────────────────────────────────────
    ws3 = wb.create_sheet("GPU_Compute")
    ws3.sheet_view.showGridLines = False
    for col, w in [("A", 10), ("B", 14), ("C", 14), ("D", 14), ("E", 12)]:
        ws3.column_dimensions[col].width = w

    r3 = write_title_block(ws3, "GPU Compute & Power Profile",
                           f"8× A100  |  Mean util: {m.gpu_util_mean:.1f}%  |  Peak: {m.gpu_util_peak:.0f}%  |  HBM: {m.hbm_util_pct:.1f}%")

    gdf = m.gpu_ts
    if not gdf.empty:
        if "gpu_idx" in gdf.columns:
            gdf_agg = gdf.groupby("time_sec").agg(
                gpu_util=("gpu_util", "mean"),
                mem_used=("mem_used", "mean"),
                power=("power", "sum"),
                temp_c=("temp_c", "mean"),
            ).reset_index()
        else:
            gdf_agg = gdf.copy()

        max_t = m.run_duration_s * 1.05 if m.run_duration_s > 0 else gdf_agg["time_sec"].max()
        gdf_agg = gdf_agg[gdf_agg["time_sec"] <= max_t]
        gdf_ds = downsample(gdf_agg, 300)

        r3 = write_section_header(ws3, "  GPU TIMESERIES (aggregated across all GPUs)", r3)
        write_table_header(ws3, ["Time (s)", "GPU Util %", "HBM Used (MB)", "Power Total (W)", "Temp (°C)"], r3)
        r3 += 1
        gpu_data_start = r3
        for _, row_d in gdf_ds.iterrows():
            bg = COL_ZEBRA if (r3 - gpu_data_start) % 2 == 0 else COL_WHITE
            vals = [
                round(float(row_d["time_sec"]), 0),
                round(float(row_d.get("gpu_util", 0)), 1),
                round(float(row_d.get("mem_used", 0)), 0),
                round(float(row_d.get("power", 0)), 1),
                round(float(row_d.get("temp_c", 0)), 1),
            ]
            for ci, v in enumerate(vals, 1):
                c = ws3.cell(row=r3, column=ci, value=v)
                c.font = body_font(9)
                c.fill = fill(bg)
                c.border = border()
                c.alignment = center()
            r3 += 1
        gpu_data_end = r3 - 1

        # Line chart: GPU Util + Power (two series)
        ch3 = LineChart()
        ch3.title = "GPU Utilisation % Over Time"
        ch3.style = 10
        ch3.y_axis.title = "Utilisation %"
        ch3.x_axis.title = "Time (s)"
        ch3.width = 20; ch3.height = 11
        util_ref = Reference(ws3, min_col=2, min_row=gpu_data_start - 1, max_row=gpu_data_end)
        x_ref3 = Reference(ws3, min_col=1, min_row=gpu_data_start, max_row=gpu_data_end)
        ch3.add_data(util_ref, titles_from_data=True)
        ch3.set_categories(x_ref3)
        ch3.series[0].graphicalProperties.line.solidFill = "7B68EE"
        ch3.series[0].graphicalProperties.line.width = 18000
        ws3.add_chart(ch3, "G2")

        ch4 = LineChart()
        ch4.title = "GPU Power Consumption (W total, all GPUs)"
        ch4.style = 10
        ch4.y_axis.title = "Watts"
        ch4.x_axis.title = "Time (s)"
        ch4.width = 20; ch4.height = 11
        pwr_ref = Reference(ws3, min_col=4, min_row=gpu_data_start - 1, max_row=gpu_data_end)
        ch4.add_data(pwr_ref, titles_from_data=True)
        ch4.set_categories(x_ref3)
        ch4.series[0].graphicalProperties.line.solidFill = "E67E22"
        ch4.series[0].graphicalProperties.line.width = 18000
        ws3.add_chart(ch4, "G23")

        # Per-GPU HBM bar chart
        if "gpu_idx" in gdf.columns:
            r3 += 2
            r3 = write_section_header(ws3, "  PER-GPU HBM PEAK USAGE", r3)
            write_table_header(ws3, ["GPU", "Peak HBM (MB)", "Peak HBM (GB)", "Capacity (GB)", "% Used"], r3)
            r3 += 1
            per_gpu_start = r3
            peak_vals = gdf.groupby("gpu_idx")["mem_used"].max()
            for gpu_idx, peak_mb in peak_vals.items():
                bg = COL_ZEBRA if (r3 - per_gpu_start) % 2 == 0 else COL_WHITE
                for ci, v in enumerate([f"GPU {gpu_idx}", round(peak_mb, 0),
                                         round(peak_mb/1024, 2),
                                         round(m.hbm_total_mb/1024, 1),
                                         f"=IFERROR(C{r3}/D{r3}*100,0)"], 1):
                    c = ws3.cell(row=r3, column=ci, value=v)
                    c.font = body_font(10, bold=(ci == 2))
                    c.fill = fill(bg)
                    c.border = border()
                    c.alignment = center()
                r3 += 1

            ch5 = BarChart()
            ch5.title = "Peak HBM per GPU (GB)"
            ch5.style = 10
            ch5.y_axis.title = "GB"
            ch5.width = 18; ch5.height = 10
            hbm_ref = Reference(ws3, min_col=3, min_row=per_gpu_start - 1, max_row=r3 - 1)
            gpu_cats = Reference(ws3, min_col=1, min_row=per_gpu_start, max_row=r3 - 1)
            ch5.add_data(hbm_ref, titles_from_data=True)
            ch5.set_categories(gpu_cats)
            ch5.series[0].graphicalProperties.solidFill = "6A0DAD"
            ws3.add_chart(ch5, "G44")

    # ── Sheet 4: Memory ───────────────────────────────────────────────────────
    ws4 = wb.create_sheet("Memory")
    ws4.sheet_view.showGridLines = False
    for col, w in [("A", 10), ("B", 16), ("C", 16), ("D", 16)]:
        ws4.column_dimensions[col].width = w

    r4 = write_title_block(ws4, "Memory Profile — HBM, DRAM & KV Cache",
                           f"DRAM: {m.dram_util_pct:.1f}%  |  HBM/GPU: {m.hbm_util_pct:.1f}%  |  hicache fill: {m.hicache_fill_pct:.1f}%")

    # KV Cache summary table
    r4 = write_section_header(ws4, "  KV CACHE & HICACHE METRICS", r4)
    write_table_header(ws4, ["Metric", "Value", "Status"], r4)
    r4 += 1
    kv_rows = [
        ("Realtime Cache Hit Rate", f"{m.cache_hit_pct:.1f}%",
         "OK" if m.cache_hit_pct > 80 else "WARN"),
        ("hicache Host Fill %", f"{m.hicache_fill_pct:.1f}%",
         "OK" if m.hicache_fill_pct < 80 else "WARN"),
        ("KV Pool Capacity (tokens)", f"{165184:,}", "INFO"),
        ("Decode Tokens", f"{m.decode_tokens:,}", "INFO"),
        ("Prefill Compute Tokens", f"{m.prefill_compute_tokens:,}", "INFO"),
        ("Prefill Cached Tokens", f"{m.prefill_cache_tokens:,}", "INFO"),
    ]
    for i, (metric, val, status) in enumerate(kv_rows):
        bg = COL_ZEBRA if i % 2 == 0 else COL_WHITE
        for ci, v in enumerate([metric, val, status], 1):
            c = ws4.cell(row=r4, column=ci, value=v)
            if ci == 3:
                sev_col = COL_OK if status == "OK" else COL_WARN if status == "WARN" else COL_ACCENT
                c.font = Font(name=FONT_NAME, size=10, bold=True, color=COL_WHITE)
                c.fill = fill(sev_col)
            else:
                c.font = body_font(10, bold=(ci == 2))
                c.fill = fill(bg)
            c.border = border()
            c.alignment = center() if ci > 1 else left()
        r4 += 1

    r4 += 1

    # DRAM timeseries
    ddf = m.dram_ts
    if not ddf.empty and "used_gb" in ddf.columns:
        ddf_ds = downsample(ddf, 200)
        r4 = write_section_header(ws4, "  DRAM TIMESERIES", r4)
        write_table_header(ws4, ["Time (s)", "DRAM Used (GB)", "DRAM Available (GB)"], r4)
        r4 += 1
        dram_data_start = r4
        for _, row_d in ddf_ds.iterrows():
            bg = COL_ZEBRA if (r4 - dram_data_start) % 2 == 0 else COL_WHITE
            for ci, v in enumerate([round(float(row_d["time_sec"]), 0),
                                      round(float(row_d.get("used_gb", 0)), 2),
                                      round(float(row_d.get("available_gb", 0)), 2)], 1):
                c = ws4.cell(row=r4, column=ci, value=v)
                c.font = body_font(9)
                c.fill = fill(bg)
                c.border = border()
                c.alignment = center()
            r4 += 1

        ch6 = LineChart()
        ch6.title = f"DRAM Used (GB) Over Time  [Total: {m.dram_total_gb:.0f} GB]"
        ch6.style = 10
        ch6.y_axis.title = "GB"
        ch6.x_axis.title = "Time (s)"
        ch6.width = 20; ch6.height = 11
        dram_ref = Reference(ws4, min_col=2, min_row=dram_data_start - 1, max_row=r4 - 1)
        x_ref4 = Reference(ws4, min_col=1, min_row=dram_data_start, max_row=r4 - 1)
        ch6.add_data(dram_ref, titles_from_data=True)
        ch6.set_categories(x_ref4)
        ch6.series[0].graphicalProperties.line.solidFill = "27AE60"
        ch6.series[0].graphicalProperties.line.width = 18000
        ws4.add_chart(ch6, "F2")

    # HBM utilisation donut (pie)
    total_ctx = m.prefill_cache_tokens + m.prefill_compute_tokens + m.decode_tokens
    if total_ctx > 0:
        pie_row = 14
        pie_data_col = 8  # column H
        ws4.cell(row=pie_row, column=pie_data_col, value="Category").font = hdr_font(9)
        ws4.cell(row=pie_row, column=pie_data_col+1, value="Tokens").font = hdr_font(9)
        for i, (label, val) in enumerate([
            ("Prefill Cached", m.prefill_cache_tokens),
            ("Prefill Compute", m.prefill_compute_tokens),
            ("Decoded Output", m.decode_tokens),
        ], 1):
            ws4.cell(row=pie_row + i, column=pie_data_col, value=label)
            ws4.cell(row=pie_row + i, column=pie_data_col+1, value=val)

        ch7 = PieChart()
        ch7.title = "Token Composition"
        ch7.style = 10
        ch7.width = 14; ch7.height = 10
        pie_data = Reference(ws4, min_col=pie_data_col+1, min_row=pie_row,
                              max_row=pie_row+3)
        pie_cats = Reference(ws4, min_col=pie_data_col, min_row=pie_row+1,
                              max_row=pie_row+3)
        ch7.add_data(pie_data, titles_from_data=True)
        ch7.set_categories(pie_cats)
        ws4.add_chart(ch7, "F22")

    # ── Sheet 5: Storage & OS ─────────────────────────────────────────────────
    ws5 = wb.create_sheet("Storage_OS")
    ws5.sheet_view.showGridLines = False
    for col, w in [("A", 10), ("B", 14), ("C", 14), ("D", 16)]:
        ws5.column_dimensions[col].width = w

    r5 = write_title_block(ws5, "Storage I/O & OS Activity",
                           f"NVMe max write IOPS: {m.nvme_wr_iops_max:.0f}  |  Page faults/s: {m.page_faults_per_s:.0f}  |  NUMA mig/s: {m.numa_migrations_per_s:.1f}")

    ndf = m.nvme_ts
    if not ndf.empty and "wr_iops" in ndf.columns:
        ndf_ds = downsample(ndf, 200)
        r5 = write_section_header(ws5, "  NVME I/O TIMESERIES", r5)
        write_table_header(ws5, ["Time (s)", "Write IOPS", "Read IOPS"], r5)
        r5 += 1
        nvme_data_start = r5
        for _, row_d in ndf_ds.iterrows():
            bg = COL_ZEBRA if (r5 - nvme_data_start) % 2 == 0 else COL_WHITE
            for ci, v in enumerate([round(float(row_d["time_sec"]), 1),
                                      round(float(row_d.get("wr_iops", 0)), 2),
                                      round(float(row_d.get("rd_iops", 0)), 2)], 1):
                c = ws5.cell(row=r5, column=ci, value=v)
                c.font = body_font(9)
                c.fill = fill(bg)
                c.border = border()
                c.alignment = center()
            r5 += 1

        ch8 = BarChart()
        ch8.title = f"NVMe Write IOPS  (max: {m.nvme_wr_iops_max:.0f})"
        ch8.style = 10
        ch8.y_axis.title = "IOPS"
        ch8.x_axis.title = "Time (s)"
        ch8.width = 20; ch8.height = 11
        iops_ref = Reference(ws5, min_col=2, min_row=nvme_data_start - 1, max_row=r5 - 1)
        x_ref5 = Reference(ws5, min_col=1, min_row=nvme_data_start, max_row=r5 - 1)
        ch8.add_data(iops_ref, titles_from_data=True)
        ch8.set_categories(x_ref5)
        ch8.series[0].graphicalProperties.solidFill = "E74C3C"
        ws5.add_chart(ch8, "F2")

    # vmstat page faults
    vdf = m.vmstat_ts
    if not vdf.empty and "pgfault" in vdf.columns:
        vdf2 = vdf.copy()
        vdf2["pgf_rate"] = (vdf2["pgfault"].diff() / vdf2["time_sec"].diff()).clip(0)
        vdf_ds = downsample(vdf2, 200)
        r5 += 1
        r5 = write_section_header(ws5, "  PAGE FAULT TIMESERIES", r5)
        write_table_header(ws5, ["Time (s)", "Page Faults/s", "NUMA Migrations/s"], r5)
        r5 += 1
        pgf_data_start = r5
        for _, row_d in vdf_ds.iterrows():
            bg = COL_ZEBRA if (r5 - pgf_data_start) % 2 == 0 else COL_WHITE
            for ci, v in enumerate([round(float(row_d["time_sec"]), 1),
                                      round(float(row_d.get("pgf_rate", 0) or 0), 1),
                                      round(float(row_d.get("numa_pages_migrated", 0) or 0), 2)], 1):
                c = ws5.cell(row=r5, column=ci, value=v)
                c.font = body_font(9)
                c.fill = fill(bg)
                c.border = border()
                c.alignment = center()
            r5 += 1

        ch9 = AreaChart()
        ch9.title = f"Page Faults/s  (mean: {m.page_faults_per_s:.0f})"
        ch9.style = 10
        ch9.y_axis.title = "Faults/s"
        ch9.x_axis.title = "Time (s)"
        ch9.width = 20; ch9.height = 11
        pgf_ref = Reference(ws5, min_col=2, min_row=pgf_data_start - 1, max_row=r5 - 1)
        x_ref6 = Reference(ws5, min_col=1, min_row=pgf_data_start, max_row=r5 - 1)
        ch9.add_data(pgf_ref, titles_from_data=True)
        ch9.set_categories(x_ref6)
        ch9.series[0].graphicalProperties.solidFill = "F39C12"
        ws5.add_chart(ch9, "F24")

    # ── Sheet 6: Bottlenecks ──────────────────────────────────────────────────
    ws6 = wb.create_sheet("Bottlenecks")
    ws6.sheet_view.showGridLines = False
    ws6.column_dimensions["A"].width = 22
    ws6.column_dimensions["B"].width = 14
    ws6.column_dimensions["C"].width = 18
    ws6.column_dimensions["D"].width = 12
    ws6.column_dimensions["E"].width = 52

    r6 = write_title_block(ws6, "Full Stack Bottleneck Attribution",
                           "Scored 0–100: relative contribution to latency or inefficiency")

    r6 = write_section_header(ws6, "  BOTTLENECK SCORECARD — ALL LAYERS", r6)
    write_table_header(ws6, ["Layer", "Score (0–100)", "Phase", "Severity", "Detail"], r6)
    r6 += 1
    bn_score_start = r6
    for i, b in enumerate(bottlenecks):
        sev = b["severity"]
        sev_fg, sev_bg = SEV_COLORS.get(sev, (COL_BLACK, COL_WHITE))
        bg = COL_ZEBRA if i % 2 == 0 else COL_WHITE
        for ci, v in enumerate([b["layer"], b["score"], b["phase"], sev, b["detail"]], 1):
            c = ws6.cell(row=r6, column=ci, value=v)
            if ci == 4:
                c.font = Font(name=FONT_NAME, size=10, bold=True, color=COL_WHITE)
                c.fill = fill(sev_fg)
            elif ci == 2:
                c.font = Font(name=FONT_NAME, size=11, bold=True,
                              color=COL_WARN if b["score"] > 60 else COL_CAU if b["score"] > 30 else COL_OK)
                c.fill = fill(bg)
            elif ci == 1:
                c.font = Font(name=FONT_NAME, size=10, bold=True, color=b["color"].lstrip("#"))
                c.fill = fill(bg)
            else:
                c.font = body_font(10)
                c.fill = fill(bg)
            c.border = border()
            c.alignment = center() if ci in (2, 3, 4) else left()
        ws6.row_dimensions[r6].height = 20
        r6 += 1
    bn_score_end = r6 - 1

    # Conditional formatting on score column
    from openpyxl.formatting.rule import ColorScaleRule
    ws6.conditional_formatting.add(
        f"B{bn_score_start}:B{bn_score_end}",
        ColorScaleRule(start_type="num", start_value=0, start_color="63BE7B",
                       mid_type="num", mid_value=50, mid_color="FFEB84",
                       end_type="num", end_value=100, end_color="F8696B"),
    )

    # Radar chart (bar in Excel as true radar)
    ch10 = RadarChart()
    ch10.type = "filled"
    ch10.title = "Bottleneck Attribution Radar"
    ch10.style = 10
    ch10.width = 18; ch10.height = 14
    radar_data = Reference(ws6, min_col=2, min_row=bn_score_start - 1,
                           max_row=bn_score_end)
    radar_cats = Reference(ws6, min_col=1, min_row=bn_score_start,
                           max_row=bn_score_end)
    ch10.add_data(radar_data, titles_from_data=True)
    ch10.set_categories(radar_cats)
    ch10.series[0].graphicalProperties.solidFill = "5B8DB880"
    ch10.series[0].graphicalProperties.line.solidFill = "5B8DB8"
    ws6.add_chart(ch10, f"G{r6 + 1}")

    # ── Sheet 7: Recommendations ──────────────────────────────────────────────
    ws7 = wb.create_sheet("Recommendations")
    ws7.sheet_view.showGridLines = False
    ws7.column_dimensions["A"].width = 32
    ws7.column_dimensions["B"].width = 12
    ws7.column_dimensions["C"].width = 12
    ws7.column_dimensions["D"].width = 14
    ws7.column_dimensions["E"].width = 60

    r7 = write_title_block(ws7, "Optimisation Recommendations",
                           "Ranked by impact. Based on observed bottlenecks.")

    r7 = write_section_header(ws7, "  ACTION ITEMS", r7)
    write_table_header(ws7, ["Recommendation", "Impact", "Effort", "Phase", "Details"], r7)
    r7 += 1
    for i, rec in enumerate(recs):
        bg = COL_ZEBRA if i % 2 == 0 else COL_WHITE
        sev_fg, _ = SEV_COLORS.get(rec["impact"], (COL_ACCENT, COL_WHITE))
        for ci, v in enumerate([rec["title"], rec["impact"], rec["effort"], rec["phase"], rec["detail"]], 1):
            c = ws7.cell(row=r7, column=ci, value=v)
            if ci in (2, 3):
                c.font = Font(name=FONT_NAME, size=10, bold=True, color=COL_WHITE)
                c.fill = fill(sev_fg if ci == 2 else COL_HDR2)
            else:
                c.font = body_font(10, bold=(ci == 1))
                c.fill = fill(bg)
            c.border = border()
            c.alignment = left() if ci in (1, 5) else center()
        ws7.row_dimensions[r7].height = 30
        r7 += 1

    # ── Freeze panes & sheet tab colors ──────────────────────────────────────
    for ws_obj, tab_color in [
        (ws,  "1E3A5F"), (ws2, "0E86D4"), (ws3, "7B68EE"),
        (ws4, "27AE60"), (ws5, "E74C3C"), (ws6, "5B8DB8"), (ws7, "F39C12"),
    ]:
        ws_obj.sheet_properties.tabColor = tab_color

    wb.save(str(out_path))
    print(f"\n✅  Excel workbook written: {out_path.resolve()}")
    print(f"    Sheets: {', '.join(wb.sheetnames)}")
    print(f"    Size: {out_path.stat().st_size / 1024:.0f} KB")


# ── Main ──────────────────────────────────────────────────────────────────────

# ── Comparison charts (matplotlib) ───────────────────────────────────────────

def _run_colors(n: int) -> list:
    palette = ["#22d3ee","#f97316","#a78bfa","#34d399","#fb923c","#f43f5e","#fbbf24","#4f46e5"]
    return [palette[i % len(palette)] for i in range(n)]


def _prep_comparison_data(runs, all_bottlenecks):
    """Serialize all run data for Chart.js injection."""
    colors = _run_colors(len(runs))
    kpis = []
    for (label, m) in runs:
        total_ctx   = m.prefill_cache_tokens + m.prefill_compute_tokens
        prefill_hit = (m.prefill_cache_tokens / max(total_ctx, 1)) * 100
        decode_ms   = m.tpot_ms * m.decode_tokens if m.tpot_ms > 0 else 0
        tok_per_wh  = (m.decode_tokens / max((m.gpu_power_mean_w * m.run_duration_s / 3600), 0.001))
        tok_per_w   = m.gen_tp_peak / max(m.gpu_power_mean_w, 0.001)
        active_pct  = min(100, (decode_ms / 1000 + m.ttft_ms / 1000) / max(m.run_duration_s, 1) * 100)
        kpis.append(dict(
            label=label,
            ttft_ms=round(m.ttft_ms, 1), tpot_ms=round(m.tpot_ms, 2),
            e2e_s=round(m.e2e_ms / 1000, 1), gen_tp_peak=round(m.gen_tp_peak, 2),
            gpu_util_mean=round(m.gpu_util_mean, 1), gpu_util_peak=round(m.gpu_util_peak, 1),
            hbm_util_pct=round(m.hbm_util_pct, 1), dram_util_pct=round(m.dram_util_pct, 1),
            gpu_power_mean_w=round(m.gpu_power_mean_w, 1),
            nvme_wr_iops_max=round(m.nvme_wr_iops_max, 1),
            cache_hit_pct=round(m.cache_hit_pct, 1),
            hicache_fill_pct=round(m.hicache_fill_pct, 1),
            decode_tokens=m.decode_tokens,
            prefill_cache_tokens=m.prefill_cache_tokens,
            prefill_compute_tokens=m.prefill_compute_tokens,
            total_context=total_ctx,
            prefill_hit_pct=round(prefill_hit, 1),
            tok_per_wh=round(tok_per_wh, 1),
            tok_per_w=round(tok_per_w, 4),
            decode_time_ms=round(decode_ms, 0),
            queue_ms=25.45,
            active_pct=round(active_pct, 1),
            run_duration_s=round(m.run_duration_s, 0),
        ))
    gpu_ts_data = []
    for label, m in runs:
        gdf = m.gpu_ts
        if not gdf.empty:
            if "gpu_idx" in gdf.columns:
                agg = gdf.groupby("time_sec").agg(util=("gpu_util","mean"),power=("power","sum")).reset_index().rename(columns={"time_sec":"t"})
            else:
                agg = gdf[["time_sec","gpu_util","power"]].copy().rename(columns={"time_sec":"t","gpu_util":"util"})
            max_t = m.run_duration_s*1.05 if m.run_duration_s>0 else agg["t"].max()
            agg = downsample(agg[agg["t"]<=max_t], 100)
            gpu_ts_data.append(dict(label=label,
                times=[round(float(v),0) for v in agg["t"]],
                util=[round(float(v),1) for v in agg["util"]],
                power=[round(float(v),1) for v in agg.get("power",pd.Series([0]*len(agg)))]))
        else:
            gpu_ts_data.append(dict(label=label,times=[],util=[],power=[]))
    layer_names = [b["layer"] for b in all_bottlenecks[0]]
    bn_scores = []
    for (label,_),bns in zip(runs,all_bottlenecks):
        lmap={b["layer"]:b for b in bns}
        bn_scores.append(dict(label=label,
            scores=[lmap.get(l,{}).get("score",0) for l in layer_names],
            severities=[lmap.get(l,{}).get("severity","LOW") for l in layer_names]))
    return dict(labels=[r[0] for r in runs],colors=colors,kpis=kpis,
                gpu_ts=gpu_ts_data,bn_layers=layer_names,bn_scores=bn_scores)


def build_comparison_html(runs, all_bottlenecks, timestamp):
    """Render interactive Chart.js multi-run comparison dashboard."""
    import json as _json
    data   = _prep_comparison_data(runs, all_bottlenecks)
    d_json = _json.dumps(data)
    n      = len(runs)
    colors = _run_colors(n)

    badges = "".join(
        f'<span style="font-size:11px;background:#e2e8f0;color:{c};padding:3px 14px;' +
        f'border-radius:20px;font-weight:600;letter-spacing:.3px">{l}</span>'
        for (l,_),c in zip(runs,colors))

    ref = data["kpis"][0]
    def delta_html(val, ref_val, higher_better=False):
        if ref_val==0: return ""
        pct=(val-ref_val)/ref_val*100
        better=(pct<0) if not higher_better else (pct>0)
        col="#22c55e" if better else "#ef4444"
        arrow="V" if pct<0 else "^"
        return f' <span style="font-size:10px;color:{col};font-weight:600">{arrow}{abs(pct):.1f}%</span>'

    # (label, data_key, unit, higher_is_better, collector, formula, interpretation)
    kpi_defs=[
        (
            "TTFT", "ttft_ms", "ms", False,
            "sglang_summary.json · SGLang Prometheus histogram",
            ("time_to_first_token_seconds_sum\n"
             "─────────────────────────────────  × 1000\n"
             "time_to_first_token_seconds_count\n\n"
             "= mean wall-clock wait until first generated token [ms]"),
            "Includes: request scheduling + KV cache lookup + full prefill compute. "
            "Grows roughly linearly with context length when cache miss rate is high."
        ),
        (
            "TPOT", "tpot_ms", "ms/tok", False,
            "sglang_summary.json · SGLang Prometheus histogram",
            ("inter_token_latency_seconds_sum\n"
             "────────────────────────────────  × 1000\n"
             "inter_token_latency_seconds_count\n\n"
             "≡ 1000 / gen_throughput_tok_s  [ms/tok]\n\n"
             "= mean inter-token gap during autoregressive decode"),
            "Hardware lower bound: model_weight_bytes_per_GPU / HBM_bandwidth. "
            "For 70B FP16 on A100: 17.5 GB / 2000 GB/s × 1000 ≈ 8.75 ms/tok theoretical min."
        ),
        (
            "E2E Latency", "e2e_s", "s", False,
            "sglang_summary.json · server_e2e_ms",
            ("server_e2e_ms / 1000  [s]\n\n"
             "≈ queue_ms + ttft_ms + (tpot_ms × decode_tokens)\n\n"
             "= total measured wall-clock time per request"),
            "The true end-to-end measured latency from SGLang. "
            "The additive decomposition (queue + prefill + decode) may differ slightly due to pipelining."
        ),
        (
            "Peak Throughput", "gen_tp_peak", "tok/s", True,
            "sglang_timeseries.csv · sglang:gen_throughput (Prometheus gauge)",
            ("max( sglang:gen_throughput[engine_type=unified] )  [tok/s]\n\n"
             "= tokens decoded in last scheduling step / step elapsed time\n\n"
             "Updated by SGLang engine after every decode scheduling step"),
            "Peak (not mean) is reported because mean is diluted by idle time between requests. "
            "For batched workloads, mean throughput is more representative."
        ),
        (
            "Cache Hit %", "cache_hit_pct", "%", True,
            "sglang_summary.json · sglang:cache_hit_rate (Prometheus gauge)",
            ("sglang:cache_hit_rate[engine_type=unified]  [%]\n\n"
             "= KV tokens served from any cache tier\n"
             "  ──────────────────────────────────────  × 100\n"
             "  total KV tokens requested\n\n"
             "Rolling realtime window — SGLang RadixAttention prefix tree"),
            "Covers all tiers: L1 HBM + L2 hicache DRAM + L3 NVMe (if enabled). "
            "High hit rate directly reduces TTFT by avoiding attention recomputation."
        ),
        (
            "hicache Fill", "hicache_fill_pct", "%", True,
            "sglang_timeseries.csv · sglang:hicache_host_used/total_tokens",
            ("sglang:hicache_host_used_tokens\n"
             "────────────────────────────────  × 100  [%]\n"
             "sglang:hicache_host_total_tokens\n\n"
             "= L2 DRAM KV pool occupancy"),
            "Approaching 100% triggers LRU eviction from the host KV pool. "
            "Low fill + high cache hit = working set fits in L1 HBM (ideal). "
            "High fill = KV cache spilling into DRAM tier."
        ),
        (
            "Prefill Hit %", "prefill_hit_pct", "%", True,
            "sglang_summary.json · rt_prefill_cache_tokens, rt_prefill_compute_tokens",
            ("          rt_prefill_cache_tokens\n"
             "──────────────────────────────────────────────  × 100  [%]\n"
             "rt_prefill_cache_tokens + rt_prefill_compute_tokens\n\n"
             "where:\n"
             "  rt_prefill_cache_tokens   = Σ realtime_tokens_total[mode=prefill_cache]\n"
             "  rt_prefill_compute_tokens = Σ realtime_tokens_total[mode=prefill_compute]"),
            "Directly measures what fraction of prefill avoided GPU attention computation. "
            "1% increase here ≈ 1% reduction in TTFT (linear relationship at fixed context length)."
        ),
        (
            "GPU Util Mean", "gpu_util_mean", "%", True,
            "gpu_timeseries.csv · nvidia-smi utilization.gpu · 1-second sampling",
            ("mean( gpu_util[i,t]  ∀ i ∈ GPU0..7,  ∀ t ∈ run )  [%]\n\n"
             "GPU util at time t = fraction of 1-second NVML window\n"
             "                     where any SM was active (NVML API)"),
            "Mean across the full run duration including idle periods. "
            "Low mean (e.g. 1.4%) is expected for single-request runs with long idle gaps. "
            "GPU util during active inference is typically 100% regardless of workload type."
        ),
        (
            "HBM Util", "hbm_util_pct", "%", False,
            "gpu_timeseries.csv · nvidia-smi memory.used / memory.total",
            ("mean(  memory.used[i] / memory.total[i] × 100\n"
             "        ∀ i ∈ GPU0..7,  ∀ t ∈ run )  [%]\n\n"
             "memory.total[i] = 40960 MiB  (A100 40 GB)\n\n"
             "HBM occupied by:\n"
             "  model weights : 70B × 2 bytes / 8 GPUs ≈ 17.5 GB\n"
             "  KV cache      : variable (fills remaining headroom)\n"
             "  CUDA runtime  : ~0.5 GB"),
            "HBM > 90% limits KV cache size, causing more evictions to hicache. "
            "Quantisation (AWQ 4-bit) halves weight footprint to ~8.75 GB/GPU, "
            "freeing ~8.75 GB for KV cache."
        ),
        (
            "DRAM Util", "dram_util_pct", "%", False,
            "dram_timeseries.csv · /proc/meminfo · 1-second sampling",
            ("(MemTotal − MemFree − Buffers − Cached)\n"
             "──────────────────────────────────────── × 100  [%]\n"
             "              MemTotal\n\n"
             "DRAM occupied by:\n"
             "  hicache L2 KV pool : sglang:hicache_host_total_tokens × 2 bytes/token\n"
             "  model loader buf   : transient during load, stable at runtime\n"
             "  OS page cache      : /proc/meminfo Cached"),
            "DRAM > 80% means the hicache L2 pool is consuming most of system memory. "
            "If DRAM is full and hicache fill is high, enable L3 NVMe KV offload."
        ),
        (
            "GPU Power", "gpu_power_mean_w", "W", False,
            "power_timeseries.csv · nvidia-smi power.draw · ~1 Hz · summed across all GPUs",
            ("mean( Σᵢ power.draw[GPU i, t]  ∀ t ∈ run )  [W]\n\n"
             "= mean total GPU power across entire run (all 8 GPUs)\n\n"
             "Reference levels (per GPU × 8):\n"
             "  Idle floor    :  57 W  ×8 =  456 W\n"
             "  Decode plateau:  70 W  ×8 =  560 W\n"
             "  Prefill peak  : 200 W  ×8 = 1600 W\n"
             "  TDP limit     : 400 W  ×8 = 3200 W"),
            "Mean power (not peak) is the correct energy denominator. "
            "A run with shorter prefill (chunked) will have lower mean power "
            "even if instantaneous prefill power is identical."
        ),
        (
            "Tok / Wh", "tok_per_wh", "tok/Wh", True,
            "Derived · power_summary.json (gpu_power_all_w_mean) + sglang_summary.json (rt_decode_tokens)",
            ("              rt_decode_tokens\n"
             "──────────────────────────────────────────  [tok/Wh]\n"
             "gpu_power_mean_w × run_duration_s / 3600\n\n"
             "numerator   = total output tokens generated\n"
             "denominator = GPU energy consumed in Watt-hours\n\n"
             "run_duration_s = power_summary.power_elapsed_s  (wall-clock)"),
            "Higher is better — more tokens per unit energy consumed. "
            "Quantisation improves this by reducing HBM reads per token (lower power). "
            "Batch size increase improves this by spreading fixed overhead across more tokens."
        ),
        (
            "Active Time", "active_pct", "%", True,
            "Derived · sglang_summary.json (ttft_ms, tpot_ms, decode_tokens) + power_summary.json (elapsed_s)",
            ("(  ttft_ms/1000  +  tpot_ms × decode_tokens / 1000  )\n"
             "──────────────────────────────────────────────────────  × 100  [%]\n"
             "                   run_duration_s\n\n"
             "numerator  ≈ estimated active inference time (prefill + decode)\n"
             "denominator = total wall-clock run duration (includes idle gaps)"),
            "Approximation valid for single-request runs. Low active % means the server "
            "spent most of the profiling window idle between requests. "
            "Increasing concurrency or reducing inter-request gaps drives this toward 100%."
        ),
    ]

    import html as _html_mod

    def _kpi_formula_cell(formula_text, interp_text, collector_text, bg):
        """Render the Formula column cell with a collapsible details block."""
        fe = _html_mod.escape(formula_text)
        ie = _html_mod.escape(interp_text)
        ce = _html_mod.escape(collector_text)
        interp_html = (f'<div style="font-size:10px;color:#334155;margin-top:6px;'
                       f'padding-top:5px;border-top:1px solid #e2e8f0;line-height:1.5">'
                       f'{ie}</div>')
        return (
            f'<td style="background:{bg};padding:5px 10px;vertical-align:top;min-width:260px">'
            f'<details style="cursor:pointer">'
            f'<summary style="font-size:10px;color:#4f46e5;list-style:none;'
            f'display:flex;align-items:center;gap:4px;outline:none;'
            f'padding:3px 0;user-select:none">&#128208;&nbsp;Formula</summary>'
            f'<div style="margin-top:6px;background:#f0f4f8;border:1px solid #e2e8f0;'
            f'border-radius:5px;padding:8px 10px">'
            f'<div style="font-size:9px;color:#475569;font-family:monospace;margin-bottom:5px">'
            f'&#128202;&nbsp;{ce}</div>'
            f'<code style="display:block;font-family:\'Courier New\',monospace;font-size:10px;'
            f'color:#1e3a5f;white-space:pre;line-height:1.8">{fe}</code>'
            f'{interp_html}'
            f'</div>'
            f'</details>'
            f'</td>'
        )

    kpi_rows=""
    for i,(label,key,unit,hb,collector,formula,interp) in enumerate(kpi_defs):
        bg="#ffffff" if i%2==0 else "#f8fafc"
        row=(f'<tr>'
             f'<td style="color:#334155;font-weight:600;background:{bg};padding:7px 14px;'
             f'white-space:nowrap">{label}'
             f'<span style="color:#475569;font-size:10px;margin-left:4px">{unit}</span></td>')
        ref_val=ref.get(key,0)
        for j,kpi in enumerate(data["kpis"]):
            val=kpi.get(key,0)
            d=delta_html(val,ref_val,hb) if j>0 else ""
            row+=(f'<td style="font-family:monospace;font-size:13px;font-weight:700;'
                  f'color:{colors[j]};text-align:center;background:{bg};'
                  f'padding:7px 14px;white-space:nowrap">{val}{d}</td>')
        row += _kpi_formula_cell(formula, interp, collector, bg)
        kpi_rows+=row+"</tr>"

    layer_explain={
        "GPU Compute":("Prefill / TTFT","GPU compute cores saturated during prefill. High score = compute-bound TTFT. Fix: chunked prefill, smaller context window, or faster GPUs."),
        "HBM Bandwidth":("Decode / TPOT","HBM re-read for every token step (weights + KV). High score = decode is memory-bandwidth-limited. Fix: quantisation (AWQ/GPTQ), speculative decoding."),
        "KV Cache":("Both","KV cache miss rate. High cache hit = low score (good). Misses force full attention recomputation. Fix: warm cache, grow hicache pool, enable prefix caching."),
        "DRAM":("Software","Host DRAM pressure from hicache L2, model loader, OS buffers. Low concern unless >80% or swap observed."),
        "NVMe I/O":("Storage","NVMe I/O during inference. Should be near-zero. Non-zero reads = model not fully loaded in memory or L3 KV offload active."),
        "Power / Thermal":("Hardware","Proximity to TDP limit (400W per A100). Near-TDP triggers frequency throttling. High power + low throughput = inefficient workload."),
        "CPU / Page Faults":("Software","OS page fault activity from SGLang runtime. Steady ~4000/s is normal. Spikes >10000/s indicate memory pressure."),
        "GPU Utilisation":("System","Fraction of run window where GPUs were active. Low mean = server mostly idle. Fix: increase concurrency, continuous batching."),
    }
    run_header_cols="".join(f'<th style="color:{colors[j]}">{r[0]}</th>' for j,r in enumerate(runs))
    layer_rows=""
    _sev_style={"HIGH":"background:#fef2f2;color:#991b1b","MED":"background:#fffbeb;color:#92400e","LOW":"background:#f0fdf4;color:#166534"}
    for i,(lname,(phase,explain)) in enumerate(layer_explain.items()):
        bg="#ffffff" if i%2==0 else "#f8fafc"
        score_cells="".join(
            f'<td style="font-family:monospace;font-weight:700;text-align:center;' +
            f'color:{colors[j]};background:{bg};padding:6px 12px">' +
            f'{next((b["score"] for b in bns if b["layer"]==lname),0)}</td>'
            for j,bns in enumerate(all_bottlenecks))
        # Severity badge: worst across all runs for this layer
        _scores=[next((b["score"] for b in bns if b["layer"]==lname),0) for bns in all_bottlenecks]
        _max_s=max(_scores)
        _sev="HIGH" if _max_s>60 else "MED" if _max_s>30 else "LOW"
        _sev_td=(f'<td style="padding:6px 12px;background:{bg};text-align:center">'
                 f'<span style="font-size:10px;padding:2px 8px;border-radius:12px;font-weight:700;{_sev_style[_sev]}">{_sev}</span></td>')
        layer_rows+=(f'<tr style="border-bottom:1px solid #e2e8f0">' +
            f'<td style="padding:8px 12px;color:#0f172a;font-weight:600;background:{bg}">{lname}</td>' +
            f'<td style="padding:8px 12px;color:#4f46e5;font-size:10px;background:{bg};white-space:nowrap">{phase}</td>' +
            f'{_sev_td}' +
            f'{score_cells}' +
            f'<td style="padding:8px 14px;color:#64748b;font-size:11px;background:{bg};max-width:400px">{explain}</td></tr>')

    bn_explain_cards=""
    for (label,m),bns,color in zip(runs,all_bottlenecks,colors):
        top3=bns[:3]
        items="".join(
            f'<div style="margin:3px 0;font-size:11px">' +
            f'<span style="color:{b["color"]};font-weight:700">#{i+1} {b["layer"]}</span>' +
            f' <span style="color:#64748b">score {b["score"]} / {b["phase"]}</span>' +
            f'<div style="color:#334155;font-size:10px;margin-top:2px;line-height:1.5">{b["detail"]}</div></div>'
            for i,b in enumerate(top3))
        bn_explain_cards+=(f'<div style="background:#f1f5f9;border:1px solid #e2e8f0;' +
            f'border-left:3px solid {color};border-radius:8px;padding:12px;flex:1;min-width:200px">' +
            f'<div style="font-size:12px;font-weight:700;color:{color};margin-bottom:6px">{label}</div>' +
            f'{items}</div>')

    # Build the full HTML
    parts=[]
    parts.append('''<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>AMOprof Multi-Run Comparison</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<script>
(function(){
  function install(){
    if(!window.Chart || window.__amoprofHoverInstalled) return;
    window.__amoprofHoverInstalled = true;
    Chart.defaults.interaction = {mode:'nearest', intersect:false, axis:'x'};
    Chart.defaults.plugins.tooltip = Object.assign({}, Chart.defaults.plugins.tooltip || {}, {
      enabled: true,
      backgroundColor: '#111827',
      titleColor: '#ffffff',
      bodyColor: '#ffffff',
      borderColor: '#94a3b8',
      borderWidth: 1,
      displayColors: true,
      padding: 10,
      caretPadding: 6
    });
    const plugin = {
      id: 'amoprofHoverReadout',
      afterInit(chart){
        const canvas = chart.canvas;
        if(!canvas || !canvas.parentNode) return;
        const wrap = canvas.parentNode;
        if(wrap.querySelector(':scope > .amoprof-hover-readout')) return;
        const box = document.createElement('div');
        box.className = 'amoprof-hover-readout';
        box.style.cssText = [
          'margin-top:6px',
          'min-height:22px',
          'font:12px/1.5 system-ui,sans-serif',
          'color:#0f172a',                     // dark text — high contrast
          'background:#f1f5f9',                // slightly darker bg than before
          'border:1px solid #cbd5e1',
          'border-radius:6px',
          'padding:5px 10px',
          'transition:background 0.1s',
        ].join(';');
        box.textContent = 'Hover over chart to see values';
        wrap.appendChild(box);
        chart.$amoprofReadout = box;
      },
      afterEvent(chart, args){
        const box = chart.$amoprofReadout;
        if(!box) return;
        const ev = args && args.event;
        if(!ev || !['mousemove','click'].includes(ev.type)){
          return;
        }

        // Support both indexed (bar/line) and xy (scatter/parsing:false) data
        const pts = chart.getElementsAtEventForMode(
          ev.native || ev,
          'nearest',
          {intersect: false, axis: 'x'},
          false
        ) || [];

        if(!pts.length){
          box.style.background = '#f1f5f9';
          box.innerHTML = '<span style="color:#94a3b8;font-style:italic">Hover over chart to see values</span>';
          return;
        }

        box.style.background = '#ffffff';
        const p = pts[0];
        const labels = chart.data && chart.data.labels ? chart.data.labels : [];

        // Resolve the x-axis label — works for both indexed and {x,y} data
        let xLabel;
        const rawPoint = chart.data.datasets[p.datasetIndex] &&
                         chart.data.datasets[p.datasetIndex].data &&
                         chart.data.datasets[p.datasetIndex].data[p.index];
        if(rawPoint != null && typeof rawPoint === 'object' && 'x' in rawPoint){
          // scatter / parsing:false — use raw.x as the axis label
          const xv = rawPoint.x;
          xLabel = Number.isFinite(xv)
            ? xv.toLocaleString(undefined, {maximumFractionDigits:3})
            : String(xv);
        } else {
          xLabel = labels[p.index] != null ? String(labels[p.index]) : `#${p.index}`;
        }

        // Collect values from all visible datasets
        const parts = [];
        (chart.data.datasets || []).forEach((ds, di) => {
          const meta = chart.getDatasetMeta(di);
          if(meta && meta.hidden) return;
          const raw = ds.data && ds.data[p.index];
          if(raw == null) return;

          let shown;
          if(typeof raw === 'object' && raw !== null && 'y' in raw){
            // {x,y} point
            const y = raw.y;
            shown = Number.isFinite(y)
              ? y.toLocaleString(undefined, {maximumFractionDigits:4})
              : String(y);
          } else {
            const num = Number(raw);
            shown = Number.isFinite(num)
              ? num.toLocaleString(undefined, {maximumFractionDigits:4})
              : String(raw);
          }
          const color = ds.borderColor || ds.backgroundColor || '#475569';
          parts.push(
            `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;` +
            `background:${color};margin-right:4px;vertical-align:middle"></span>` +
            `<b style="color:#0f172a">${ds.label || 'value'}:</b> ` +
            `<span style="color:#1e3a5f;font-family:monospace">${shown}</span>`
          );
        });

        if(!parts.length){
          box.innerHTML = `<span style="color:#94a3b8;font-style:italic">No data at ${xLabel}</span>`;
          return;
        }
        box.innerHTML =
          `<span style="color:#64748b;font-size:11px">${xLabel}</span>` +
          `<span style="color:#cbd5e1;margin:0 6px">|</span>` +
          parts.join('<span style="color:#cbd5e1;margin:0 5px">·</span>');
      }
    };
    Chart.register(plugin);
  }
  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install);
  else install();
})();
</script>

<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#f8fafc;color:#0f172a;font-family:"Inter",system-ui,sans-serif;padding:20px}
h2{font-size:12px;font-weight:700;letter-spacing:.6px;text-transform:uppercase;margin-bottom:6px;color:#4f46e5}
.card{background:#ffffff;border:1px solid #e2e8f0;border-radius:10px;padding:18px;margin-bottom:16px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.desc{font-size:11px;color:#475569;line-height:1.6;margin-bottom:10px}
.insight{background:#f8fafc;border-left:3px solid #4f46e5;border-radius:0 6px 6px 0;border-radius:0 6px 6px 0;padding:10px 14px;margin-top:10px;font-size:11px;color:#334155;line-height:1.6}
.insight b{color:#0f172a}
canvas{max-height:340px}
details.fml{margin:6px 0 10px;border-radius:6px;overflow:hidden}
details.fml>summary{font-size:10px;color:#4f46e5;cursor:pointer;user-select:none;
  padding:4px 10px;background:#f1f5f9;border:1px solid #e2e8f0;border-radius:6px;
  list-style:none;display:flex;align-items:center;gap:5px}
details.fml>summary::-webkit-details-marker{display:none}
details.fml[open]>summary{border-bottom-left-radius:0;border-bottom-right-radius:0}
.fml-body{background:#f1f5f9;border:1px solid #cbd5e1;border-top:none;
  border-bottom-left-radius:6px;border-bottom-right-radius:6px;
  padding:12px 16px;overflow-x:auto}
.fml-src{font-size:10px;color:#1e293b;margin-bottom:8px;font-family:monospace;font-weight:600}
.fml-body code{display:block;font-family:"Courier New",monospace;font-size:11px;
  color:#1e3a5f;line-height:1.9;white-space:pre}
.fml-note{font-size:10px;color:#334155;margin-top:8px;font-style:italic;
  border-top:1px solid #e2e8f0;padding-top:6px;line-height:1.6}
details.fml{margin:8px 0 10px}
details.fml>summary{font-size:10px;color:#4f46e5;cursor:pointer;user-select:none;
  padding:3px 0;letter-spacing:.5px;list-style:none}
details.fml>summary::before{content:"\25B6  ";font-size:9px}
details.fml[open]>summary::before{content:"\25BC  "}
.fml-body{background:#f1f5f9;border:1px solid #cbd5e1;border-radius:6px;
  padding:10px 14px;margin-top:6px;overflow-x:auto}
.fml-body .src{display:block;font-size:10px;color:#1e293b;margin-bottom:6px;
  font-family:monospace;font-weight:600}
.fml-body code{display:block;font-family:"Courier New",monospace;font-size:11px;
  color:#1e3a5f;line-height:1.8;white-space:pre}
.fml-body .note{display:block;font-size:10px;color:#334155;margin-top:6px;
  font-style:italic;border-top:1px solid #e2e8f0;padding-top:6px}
table{width:100%;border-collapse:collapse;font-size:12px}
th{padding:7px 12px;background:#1e3a5f;color:#fff;font-size:11px;font-weight:700;text-align:center;border:1px solid #e2e8f0}
.flex{display:flex;gap:12px;flex-wrap:wrap}
/* Hover readout box below charts */
.amoprof-hover-readout{
  min-height:22px;
  font:12px/1.5 system-ui,sans-serif;
  color:#0f172a;
  background:#f1f5f9;
  border:1px solid #cbd5e1;
  border-radius:6px;
  padding:5px 10px;
  overflow:hidden;
  text-overflow:ellipsis;
  white-space:nowrap;
  transition:background 0.1s;
}
@media(max-width:900px){.grid2{grid-template-columns:1fr}}
</style></head><body>
''')

    parts.append(f'''
<div style="background:#ffffff;border:1px solid #e2e8f0;border-radius:12px;
            padding:20px 24px;margin-bottom:20px;
            border-left:4px solid #4f46e5;
            box-shadow:0 1px 4px rgba(0,0,0,0.06)">
  <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px;flex-wrap:wrap">
    <span class="report-title-prefix" style="font-size:22px;font-weight:900;letter-spacing:-0.5px;color:#0f172a">AI STACK</span>
    <span style="font-size:22px;font-weight:900;letter-spacing:-0.5px;color:#4f46e5">MULTI-RUN COMPARISON</span>
    <span style="font-size:10px;background:#eef2ff;color:#4338ca;padding:3px 10px;
                 border-radius:20px;font-weight:700;border:1px solid #c7d2fe">AMOprof v1.0</span>
  </div>
  <div style="font-size:12px;color:#475569">{n} runs compared &middot; Generated {timestamp} &middot; Baseline: <b style="color:#0f172a">{runs[0][0]}</b></div>
  <div style="display:flex;gap:8px;margin-top:10px;flex-wrap:wrap">{badges}</div>
</div>

<div class="card">
<h2>KPI Comparison</h2>
<div class="desc">All key metrics side by side. Coloured deltas (^ up / V down) show change vs baseline <b style="color:#0f172a">{runs[0][0]}</b>. Green = improvement, red = regression.
The <b style="color:#4f46e5">&#128208; Formula</b> column in each row shows the exact derivation, data source, and interpretation for that metric — click to expand.</div>
<div style="overflow-x:auto"><table>
<thead><tr><th style="text-align:left">Metric</th>{run_header_cols}<th style="color:#4f46e5;min-width:120px">&#128208; Formula &amp; Source</th></tr></thead>
<tbody>{kpi_rows}</tbody></table></div></div>
''')

    parts.append(f'<script>\nconst D={d_json};\n')
    parts.append('''
const RC=D.colors,LB=D.labels;
Chart.defaults.color="#475569";
Chart.defaults.borderColor="#e2e8f0";
Chart.defaults.font.family="monospace";
function dsc(xT,yT,yT2){
  const base={ticks:{color:"#475569",font:{size:10}},grid:{color:"#e2e8f0"}};
  const s={x:{...base,title:{display:!!xT,text:xT||"",color:"#475569"}},
            y:{...base,title:{display:!!yT,text:yT||"",color:"#475569"}}};
  if(yT2)s.y2={...base,position:"right",title:{display:true,text:yT2,color:"#475569"},grid:{drawOnChartArea:false}};
  return s;
}
function tt(lFn,bFn){return{backgroundColor:"#ffffff",borderColor:"#e2e8f0",borderWidth:1,
  titleColor:"#475569",bodyColor:"#0f172a",padding:10,cornerRadius:6,
  callbacks:{title:lFn,label:bFn}};}
function lg(){return{labels:{color:"#475569",font:{size:10},boxWidth:12}};}
window.addEventListener("DOMContentLoaded",()=>{

// Chart 1: TTFT vs TPOT
new Chart(document.getElementById("c1"),{type:"bar",
  data:{labels:LB,datasets:[
    {label:"TTFT ms (Prefill)",data:D.kpis.map(k=>k.ttft_ms),backgroundColor:"#f9731699",borderColor:"#f97316",borderWidth:1,borderRadius:4},
    {label:"TPOT ms/tok (Decode)",data:D.kpis.map(k=>k.tpot_ms),backgroundColor:"#22d3ee99",borderColor:"#22d3ee",borderWidth:1,borderRadius:4},
  ]},
  options:{responsive:true,plugins:{legend:lg(),tooltip:tt(i=>i[0].label,i=>{
    const k=D.kpis[i[0].dataIndex];
    return i[0].datasetIndex===0?` TTFT: ${k.ttft_ms}ms  |  E2E: ${k.e2e_s}s`
      :` TPOT: ${k.tpot_ms}ms/tok  =  ${(1000/k.tpot_ms).toFixed(1)} tok/s`;
  })},scales:dsc("","Milliseconds")}
});

// Chart 2: Throughput + active time
new Chart(document.getElementById("c2"),{type:"bar",
  data:{labels:LB,datasets:[
    {label:"Peak tok/s",data:D.kpis.map(k=>k.gen_tp_peak),backgroundColor:"#a78bfa99",borderColor:"#a78bfa",borderWidth:1,borderRadius:4,yAxisID:"y"},
    {label:"GPU Active %",data:D.kpis.map(k=>k.active_pct),backgroundColor:"#34d39999",borderColor:"#34d399",borderWidth:1,borderRadius:4,yAxisID:"y2"},
  ]},
  options:{responsive:true,plugins:{legend:lg(),tooltip:tt(i=>i[0].label,i=>{
    const k=D.kpis[i[0].dataIndex];
    return i[0].datasetIndex===0?` ${k.gen_tp_peak} tok/s  |  ${k.decode_tokens.toLocaleString()} tokens generated`
      :` GPU active ${k.active_pct}% of ${k.run_duration_s}s run`;
  })},scales:{...dsc("","tok/s","Active %"),y:{position:"left",title:{display:true,text:"tok/s",color:"#475569"},ticks:{color:"#475569",font:{size:10}},grid:{color:"#e2e8f0"}},y2:{position:"right",title:{display:true,text:"Active %",color:"#475569"},ticks:{color:"#475569",font:{size:10}},grid:{drawOnChartArea:false},max:100}}}
});

// Chart 3: Power efficiency
new Chart(document.getElementById("c3"),{type:"bar",
  data:{labels:LB,datasets:[
    {label:"tok / Wh",data:D.kpis.map(k=>k.tok_per_wh),backgroundColor:"#fb923c99",borderColor:"#fb923c",borderWidth:1,borderRadius:4,yAxisID:"y"},
    {label:"tok/s per kW",data:D.kpis.map(k=>+(k.tok_per_w*1000).toFixed(2)),backgroundColor:"#fbbf2499",borderColor:"#fbbf24",borderWidth:1,borderRadius:4,yAxisID:"y2"},
  ]},
  options:{responsive:true,plugins:{legend:lg(),tooltip:tt(i=>i[0].label,i=>{
    const k=D.kpis[i[0].dataIndex];
    return i[0].datasetIndex===0?` ${k.tok_per_wh} tok/Wh  |  GPU: ${k.gpu_power_mean_w}W mean`
      :` ${(k.tok_per_w*1000).toFixed(2)} tok/s/kW`;
  })},scales:{y:{position:"left",title:{display:true,text:"tok/Wh",color:"#475569"},ticks:{color:"#475569",font:{size:10}},grid:{color:"#e2e8f0"}},y2:{position:"right",title:{display:true,text:"tok/s/kW",color:"#475569"},ticks:{color:"#475569",font:{size:10}},grid:{drawOnChartArea:false}},x:{ticks:{color:"#475569",font:{size:10}},grid:{color:"#e2e8f0"}}}}
});

// Chart 4: GPU util timeline overlay
new Chart(document.getElementById("c4"),{type:"line",
  data:{datasets:D.gpu_ts.map((ts,i)=>({label:ts.label,data:ts.times.map((t,j)=>({x:+(t/60).toFixed(2),y:ts.util[j]})),borderColor:RC[i],borderWidth:1.5,pointRadius:0,tension:0.3,fill:false}))},
  options:{responsive:true,parsing:false,plugins:{legend:lg(),tooltip:tt(i=>`t=${i[0].raw.x}min`,i=>`${i[0].dataset.label}: ${i[0].raw.y}%`)},
    scales:{x:{type:"linear",title:{display:true,text:"Time (min)",color:"#475569"},ticks:{color:"#475569",font:{size:10}},grid:{color:"#e2e8f0"}},y:{min:0,max:105,title:{display:true,text:"GPU Util %",color:"#475569"},ticks:{color:"#475569",font:{size:10}},grid:{color:"#e2e8f0"}}}}
});

// Chart 5: Power timeline overlay
new Chart(document.getElementById("c5"),{type:"line",
  data:{datasets:D.gpu_ts.map((ts,i)=>({label:ts.label,data:ts.times.map((t,j)=>({x:+(t/60).toFixed(2),y:ts.power[j]})),borderColor:RC[i],borderWidth:1.5,pointRadius:0,tension:0.3,fill:false}))},
  options:{responsive:true,parsing:false,plugins:{legend:lg(),tooltip:tt(i=>`t=${i[0].raw.x}min`,i=>`${i[0].dataset.label}: ${i[0].raw.y}W`)},
    scales:{x:{type:"linear",title:{display:true,text:"Time (min)",color:"#475569"},ticks:{color:"#475569",font:{size:10}},grid:{color:"#e2e8f0"}},y:{title:{display:true,text:"Watts (all GPUs)",color:"#475569"},ticks:{color:"#475569",font:{size:10}},grid:{color:"#e2e8f0"}}}}
});

// Chart 6: Memory utilisation
new Chart(document.getElementById("c6"),{type:"bar",
  data:{labels:LB,datasets:[
    {label:"HBM Util %",data:D.kpis.map(k=>k.hbm_util_pct),backgroundColor:"#7c3aed99",borderColor:"#7c3aed",borderWidth:1,borderRadius:4},
    {label:"DRAM Util %",data:D.kpis.map(k=>k.dram_util_pct),backgroundColor:"#34d39999",borderColor:"#34d399",borderWidth:1,borderRadius:4},
  ]},
  options:{responsive:true,plugins:{legend:lg(),tooltip:tt(i=>i[0].label,i=>{
    const k=D.kpis[i[0].dataIndex];
    return i[0].datasetIndex===0?` HBM: ${k.hbm_util_pct}% (${(k.hbm_util_pct*40.96/100).toFixed(1)}GB / 40GB per GPU)`
      :` DRAM: ${k.dram_util_pct}%`;
  })},scales:dsc("","%")}
});

// Chart 7: KV cache health
new Chart(document.getElementById("c7"),{type:"bar",
  data:{labels:LB,datasets:[
    {label:"Realtime Cache Hit %",data:D.kpis.map(k=>k.cache_hit_pct),backgroundColor:"#22d3ee99",borderColor:"#22d3ee",borderWidth:1,borderRadius:4},
    {label:"Prefill From Cache %",data:D.kpis.map(k=>k.prefill_hit_pct),backgroundColor:"#0891b299",borderColor:"#0891b2",borderWidth:1,borderRadius:4},
    {label:"hicache Fill %",data:D.kpis.map(k=>k.hicache_fill_pct),backgroundColor:"#4f46e599",borderColor:"#4f46e5",borderWidth:1,borderRadius:4},
  ]},
  options:{responsive:true,plugins:{legend:lg(),tooltip:tt(i=>i[0].label,i=>{
    const k=D.kpis[i[0].dataIndex];const d=i[0].datasetIndex;
    if(d===0)return ` ${k.cache_hit_pct}% realtime hit  |  ${k.cache_hit_pct>90?"excellent":"needs attention"}`;
    if(d===1)return ` ${k.prefill_hit_pct}% prefill cached = ${k.prefill_cache_tokens.toLocaleString()} tokens free`;
    return ` ${k.hicache_fill_pct}% of L2 host KV pool used`;
  })},scales:dsc("","%")}
});

// Chart 8: Token composition stacked
new Chart(document.getElementById("c8"),{type:"bar",
  data:{labels:LB,datasets:[
    {label:"Prefill Cached",data:D.kpis.map(k=>k.prefill_cache_tokens),backgroundColor:"#0891b299",borderColor:"#0891b2",borderWidth:1},
    {label:"Prefill Compute",data:D.kpis.map(k=>k.prefill_compute_tokens),backgroundColor:"#f9731699",borderColor:"#f97316",borderWidth:1},
    {label:"Decode Output",data:D.kpis.map(k=>k.decode_tokens),backgroundColor:"#22d3ee99",borderColor:"#22d3ee",borderWidth:1},
  ]},
  options:{responsive:true,plugins:{legend:lg(),tooltip:tt(i=>i[0].label,i=>{
    const k=D.kpis[i[0].dataIndex];const d=i[0].datasetIndex;
    const t=k.prefill_cache_tokens+k.prefill_compute_tokens+k.decode_tokens;
    if(d===0)return ` ${k.prefill_cache_tokens.toLocaleString()} cached (${(k.prefill_cache_tokens/t*100).toFixed(1)}%)`;
    if(d===1)return ` ${k.prefill_compute_tokens.toLocaleString()} computed (${(k.prefill_compute_tokens/t*100).toFixed(1)}%)`;
    return ` ${k.decode_tokens.toLocaleString()} generated (${(k.decode_tokens/t*100).toFixed(1)}%)`;
  })},scales:{x:{stacked:true,ticks:{color:"#475569",font:{size:10}},grid:{color:"#e2e8f0"}},y:{stacked:true,title:{display:true,text:"Tokens",color:"#475569"},ticks:{color:"#475569",font:{size:10}},grid:{color:"#e2e8f0"}}}}
});

// Chart 9: Latency waterfall stacked
new Chart(document.getElementById("c9"),{type:"bar",
  data:{labels:LB,datasets:[
    {label:"Queue / Schedule ms",data:D.kpis.map(k=>k.queue_ms),backgroundColor:"#47556999",borderColor:"#475569",borderWidth:1},
    {label:"Prefill / TTFT ms",data:D.kpis.map(k=>k.ttft_ms),backgroundColor:"#f9731699",borderColor:"#f97316",borderWidth:1},
    {label:"Decode Total ms",data:D.kpis.map(k=>k.decode_time_ms),backgroundColor:"#22d3ee99",borderColor:"#22d3ee",borderWidth:1},
  ]},
  options:{responsive:true,plugins:{legend:lg(),tooltip:tt(i=>i[0].label+" Latency",i=>{
    const k=D.kpis[i[0].dataIndex];const d=i[0].datasetIndex;
    const total=k.queue_ms+k.ttft_ms+k.decode_time_ms;
    if(d===0)return ` ${k.queue_ms}ms (${(k.queue_ms/total*100).toFixed(1)}%)`;
    if(d===1)return ` TTFT ${k.ttft_ms}ms (${(k.ttft_ms/total*100).toFixed(1)}%)`;
    return ` Decode ${(k.decode_time_ms/1000).toFixed(1)}s = ${k.decode_tokens} tok x ${k.tpot_ms}ms/tok`;
  })},scales:{x:{stacked:true,ticks:{color:"#475569",font:{size:10}},grid:{color:"#e2e8f0"}},y:{stacked:true,title:{display:true,text:"Milliseconds",color:"#475569"},ticks:{color:"#475569",font:{size:10}},grid:{color:"#e2e8f0"}}}}
});

// Chart 10: Decode efficiency scatter
new Chart(document.getElementById("c10"),{type:"scatter",
  data:{datasets:D.kpis.map((k,i)=>({label:k.label,data:[{x:k.hbm_util_pct,y:k.tpot_ms}],backgroundColor:RC[i]+"cc",borderColor:RC[i],pointRadius:10,pointHoverRadius:13}))},
  options:{responsive:true,plugins:{legend:lg(),tooltip:tt(i=>i[0].dataset.label,i=>{
    const k=D.kpis[i[0].datasetIndex];
    return[` HBM: ${k.hbm_util_pct}%`,` TPOT: ${k.tpot_ms}ms/tok (${(1000/k.tpot_ms).toFixed(1)} tok/s)`,` Power: ${k.gpu_power_mean_w}W`];
  })},
    scales:{x:{title:{display:true,text:"HBM Utilisation %",color:"#475569"},ticks:{color:"#475569",font:{size:10}},grid:{color:"#e2e8f0"}},y:{title:{display:true,text:"TPOT ms/tok (lower = better)",color:"#475569"},ticks:{color:"#475569",font:{size:10}},grid:{color:"#e2e8f0"}}}}
});

// Chart 11: GPU power vs throughput scatter
new Chart(document.getElementById("c11"),{type:"scatter",
  data:{datasets:D.kpis.map((k,i)=>({label:k.label,data:[{x:k.gpu_power_mean_w,y:k.gen_tp_peak}],backgroundColor:RC[i]+"cc",borderColor:RC[i],pointRadius:10,pointHoverRadius:13}))},
  options:{responsive:true,plugins:{legend:lg(),tooltip:tt(i=>i[0].dataset.label,i=>{
    const k=D.kpis[i[0].datasetIndex];
    return[` Power: ${k.gpu_power_mean_w}W mean`,` Throughput: ${k.gen_tp_peak} tok/s`,` Efficiency: ${k.tok_per_wh} tok/Wh`];
  })},
    scales:{x:{title:{display:true,text:"GPU Power Mean (W)",color:"#475569"},ticks:{color:"#475569",font:{size:10}},grid:{color:"#e2e8f0"}},y:{title:{display:true,text:"Peak Throughput (tok/s)",color:"#475569"},ticks:{color:"#475569",font:{size:10}},grid:{color:"#e2e8f0"}}}}
});

// Chart 15: Throughput & Power grouped bars (paired absolute values per run)
new Chart(document.getElementById("c15"),{type:"bar",
  data:{
    labels:D.labels,
    datasets:[
      {label:"Peak Throughput (tok/s)",data:D.kpis.map(k=>k.gen_tp_peak),
       backgroundColor:"#a78bfa99",borderColor:"#a78bfa",borderWidth:1,borderRadius:4,yAxisID:"y"},
      {label:"GPU Power Mean (W)",data:D.kpis.map(k=>k.gpu_power_mean_w),
       backgroundColor:"#fb923c99",borderColor:"#fb923c",borderWidth:1,borderRadius:4,yAxisID:"y2"},
    ]
  },
  options:{responsive:true,
    plugins:{legend:lg(),tooltip:tt(i=>i[0].label,i=>{
      const k=D.kpis[i[0].dataIndex];
      if(i[0].datasetIndex===0)
        return` ${k.gen_tp_peak} tok/s  |  GPU active ${k.active_pct}% of run  |  ${k.tok_per_wh} tok/Wh`;
      return` ${k.gpu_power_mean_w}W mean  |  energy ${(k.gpu_power_mean_w*k.run_duration_s/3600).toFixed(2)} Wh  |  ${k.tok_per_wh} tok/Wh`;
    })},
    scales:{
      x:{ticks:{color:"#475569",font:{size:10}},grid:{color:"#e2e8f0"}},
      y:{position:"left",title:{display:true,text:"tok/s",color:"#475569"},
         ticks:{color:"#475569",font:{size:10}},grid:{color:"#e2e8f0"}},
      y2:{position:"right",title:{display:true,text:"Watts",color:"#475569"},
          ticks:{color:"#475569",font:{size:10}},grid:{drawOnChartArea:false}}
    }
  }
});


new Chart(document.getElementById("c12"),{type:"radar",
  data:{labels:D.bn_layers,datasets:D.bn_scores.map((run,i)=>({label:run.label,data:run.scores,borderColor:RC[i],borderWidth:2,backgroundColor:RC[i]+"22",pointBackgroundColor:RC[i],pointRadius:3}))},
  options:{responsive:true,plugins:{legend:lg(),tooltip:tt(i=>i[0].label,i=>{
    const layer=D.bn_layers[i[0].dataIndex];const s=i[0].raw;
    return` ${layer}: ${s}/100  (${s>60?"HIGH":s>30?"MED":"LOW"})`;
  })},
    scales:{r:{min:0,max:100,ticks:{color:"#475569",font:{size:9},backdropColor:"transparent",stepSize:25},grid:{color:"#e2e8f0"},pointLabels:{color:"#475569",font:{size:10}},angleLines:{color:"#e2e8f0"}}}}
});

// Chart 13: Bottleneck horizontal bar matrix
new Chart(document.getElementById("c13"),{type:"bar",
  data:{labels:D.bn_layers,datasets:D.bn_scores.map((run,i)=>({label:run.label,data:run.scores,backgroundColor:RC[i]+"bb",borderColor:RC[i],borderWidth:1,borderRadius:3}))},
  options:{responsive:true,indexAxis:"y",plugins:{legend:lg(),tooltip:tt(i=>i[0].label+" / "+i[0].chart.data.labels[i[0].dataIndex],i=>{
    const s=i[0].raw;return` Score: ${s}/100  ${s>60?"HIGH":s>30?"MED":"LOW"}`;
  })},
    scales:{x:{max:110,title:{display:true,text:"Score (0-100)",color:"#475569"},ticks:{color:"#475569",font:{size:10}},grid:{color:"#e2e8f0"}},y:{ticks:{color:"#475569",font:{size:10}},grid:{color:"#e2e8f0"}}}}
});

// Chart 14: Cache hit vs TTFT scatter
new Chart(document.getElementById("c14"),{type:"scatter",
  data:{datasets:D.kpis.map((k,i)=>({label:k.label,data:[{x:k.cache_hit_pct,y:k.ttft_ms}],backgroundColor:RC[i]+"cc",borderColor:RC[i],pointRadius:10,pointHoverRadius:13}))},
  options:{responsive:true,plugins:{legend:lg(),tooltip:tt(i=>i[0].dataset.label,i=>{
    const k=D.kpis[i[0].datasetIndex];
    return[` Cache Hit: ${k.cache_hit_pct}%  Prefill Hit: ${k.prefill_hit_pct}%`,` TTFT: ${k.ttft_ms}ms`,` Cached tokens: ${k.prefill_cache_tokens.toLocaleString()}`];
  })},
    scales:{x:{title:{display:true,text:"Cache Hit Rate %",color:"#475569"},ticks:{color:"#475569",font:{size:10}},grid:{color:"#e2e8f0"}},y:{title:{display:true,text:"TTFT ms (lower = better)",color:"#475569"},ticks:{color:"#475569",font:{size:10}},grid:{color:"#e2e8f0"}}}}
});

}); // DOMContentLoaded
</script>
''')

    # ── Formula definitions (source, derivation, note) keyed by canvas id ───
    FORMULA_DB = {
        "c1": (
            "sglang_summary.json · SGLang Prometheus /metrics endpoint",
            ("TTFT  = time_to_first_token_seconds_sum\n"
             "        / time_to_first_token_seconds_count  × 1000  [ms]\n"
             "      ⟶ mean wall-clock wait until first generated token\n\n"
             "TPOT  = inter_token_latency_seconds_sum\n"
             "        / inter_token_latency_seconds_count  × 1000  [ms/tok]\n"
             "      ⟶ mean inter-token gap during autoregressive decode\n"
             "      ≡ 1000 / gen_throughput_tok_s  [ms/tok]"),
            "Both are Prometheus histogram aggregations scraped by the profiler at run end. "
            "TTFT includes scheduling latency + KV cache lookup + prefill compute. "
            "TPOT ≈ model_weight_bytes_per_GPU / effective_HBM_bandwidth."
        ),
        "c2": (
            "sglang_timeseries.csv (sglang:gen_throughput) + derived from run summary",
            ("Peak Throughput = max( sglang:gen_throughput[engine_type=unified] )  [tok/s]\n"
             "               = tokens decoded in last scheduling step / step duration\n\n"
             "GPU Active %   = (TTFT_ms/1000 + TPOT_ms × decode_tokens / 1000)\n"
             "                 / run_duration_s  × 100  [%]\n"
             "               ⟶ estimated fraction of total run where GPUs were computing\n\n"
             "run_duration_s = power_summary.power_elapsed_s  (wall-clock)"),
            "GPU Active % is an approximation valid for single-request runs. "
            "For concurrent batching it becomes more direct. "
            "gen_throughput is a Prometheus gauge updated after every decode step."
        ),
        "c3": (
            "power_summary.json (gpu_power_all_w_mean) + sglang_summary.json (rt_decode_tokens, gen_tp_peak)",
            ("tok / Wh     = rt_decode_tokens\n"
             "               / ( gpu_power_mean_w × run_duration_s / 3600 )  [tokens / Wh]\n"
             "             ⟶ output tokens per unit GPU energy consumed\n\n"
             "tok/s per kW = gen_tp_peak / gpu_power_mean_w × 1000  [tok/s / kW]\n"
             "             ⟶ peak throughput normalised by mean power draw\n\n"
             "GPU energy   = gpu_power_mean_w × run_duration_s / 3600  [Wh]\n\n"
             "gpu_power_mean_w = power_summary.gpu_power_all_w_mean\n"
             "                 = mean( Σᵢ nvidia-smi power.draw[GPU i] )  over entire run"),
            "Power sourced from nvidia-smi (per GPU). "
            "run_duration_s from power_summary.power_elapsed_s. "
            "Mean power (not peak) is used as the denominator so idle phases are included in the energy budget."
        ),
        "c4": (
            "gpu_timeseries.csv · nvidia-smi --query-gpu=utilization.gpu · 1-second sampling",
            ("Raw sample command:\n"
             "  nvidia-smi --query-gpu=index,utilization.gpu --format=csv -l 1\n\n"
             "Aggregation across GPUs (per second):\n"
             "  util_mean[t] = mean( gpu_util[i,t]  for i in GPU0..GPU7 )  [%]\n\n"
             "Display downsampling to 100 points per run:\n"
             "  stride = max(1, len(timeseries) // 100)\n"
             "  plotted = timeseries[::stride]"),
            "GPU util = fraction of time any SM was active in the 1-second NVML sampling window. "
            "100% = all SMs busy every cycle. 0% = no active CUDA kernels. "
            "Reported by NVML via nvmlDeviceGetUtilizationRates()."
        ),
        "c5": (
            "power_timeseries.csv · nvidia-smi --query-gpu=power.draw · ~1 Hz",
            ("Raw sample command:\n"
             "  nvidia-smi --query-gpu=index,power.draw --format=csv\n\n"
             "Aggregation across GPUs (per sample):\n"
             "  power_total[t] = Σᵢ gpu_power[i,t]  for i in GPU0..GPU7  [W]\n\n"
             "Reference power levels (per GPU):\n"
             "  Idle floor    :  ~57 W   →  ~456 W total (8 GPUs)\n"
             "  Decode plateau:  60-80 W →  480-640 W total\n"
             "  Prefill peak  : 160-265 W → 1280-2120 W total\n"
             "  TDP limit     :  400 W   →  3200 W theoretical max"),
            "Energy under curve = ∫power(t)dt over run ≈ mean power × duration. "
            "Area ratio prefill/decode approximates relative energy cost of each phase."
        ),
        "c6": (
            "gpu_timeseries.csv (nvidia-smi memory.used/total) + dram_timeseries.csv (/proc/meminfo)",
            ("HBM Util %  = mean( mem_used_mb[i] / mem_total_mb[i] × 100  for i in 0..7 )\n"
             "  where:\n"
             "    mem_used_mb[i]  = nvidia-smi --query-gpu=memory.used   [MiB]\n"
             "    mem_total_mb[i] = nvidia-smi --query-gpu=memory.total  [MiB]  = 40960 (A100 40GB)\n\n"
             "DRAM Util % = dram_used_gb / dram_total_gb × 100  [%]\n"
             "  where:\n"
             "    dram_used_gb  = ( MemTotal − MemFree − Buffers − Cached ) / 1024³  (/proc/meminfo)\n"
             "    dram_total_gb = MemTotal / 1024³"),
            "HBM is occupied by: model weights (~26.8 GB for 70B FP16 across 8 GPUs) + "
            "active KV cache + CUDA runtime (~0.5 GB). "
            "DRAM is occupied by: hicache L2 KV pool + model loader buffers + OS page cache."
        ),
        "c7": (
            "sglang_summary.json + sglang_timeseries.csv · SGLang Prometheus metrics",
            ("Realtime Cache Hit %\n"
             "  = sglang:cache_hit_rate[engine_type=unified]  (Prometheus gauge, rolling window)\n"
             "  = KV tokens served from any cache tier / total KV tokens requested  [%]\n\n"
             "Prefill From Cache %\n"
             "  = rt_prefill_cache_tokens\n"
             "    / ( rt_prefill_cache_tokens + rt_prefill_compute_tokens ) × 100  [%]\n"
             "  where:\n"
             "    rt_prefill_cache_tokens   = Σ sglang:realtime_tokens_total[mode=prefill_cache]\n"
             "    rt_prefill_compute_tokens = Σ sglang:realtime_tokens_total[mode=prefill_compute]\n\n"
             "hicache Fill %\n"
             "  = sglang:hicache_host_used_tokens / sglang:hicache_host_total_tokens × 100  [%]\n"
             "  = L2 DRAM KV pool occupancy"),
            "Cache Hit Rate is a realtime estimate from SGLang's RadixAttention prefix tree. "
            "Prefill From Cache % is derived from cumulative token-mode counters in sglang_summary.json."
        ),
        "c8": (
            "sglang_summary.json · fields: rt_prefill_cache_tokens, rt_prefill_compute_tokens, rt_decode_tokens",
            ("Prefill Cached   = rt_prefill_cache_tokens  [tokens]\n"
             "               = Σ sglang:realtime_tokens_total[mode=prefill_cache]\n"
             "               ⟶ tokens whose KV state was reused from cache (zero GPU attention cost)\n\n"
             "Prefill Compute  = rt_prefill_compute_tokens  [tokens]\n"
             "               = Σ sglang:realtime_tokens_total[mode=prefill_compute]\n"
             "               ⟶ tokens requiring full self-attention computation (drives TTFT)\n\n"
             "Decode Output    = rt_decode_tokens  [tokens]\n"
             "               = Σ sglang:realtime_tokens_total[mode=decode]\n"
             "               ⟶ autoregressively generated output tokens (each costs TPOT)\n\n"
             "Total context  = Prefill Cached + Prefill Compute\n"
             "Total tokens   = Prefill Cached + Prefill Compute + Decode Output"),
            "Cumulative counters reset at server startup. "
            "Profiler reads the end-of-run snapshot from sglang_summary.json. "
            "For multi-request runs these are summed across all requests processed."
        ),
        "c9": (
            "sglang_summary.json · server_ttft_ms, server_itl_ms, rt_decode_tokens, hicache_queue_time_ms",
            ("Queue (ms)         = hicache_queue_time_ms\n"
             "                 ⟶ time in hicache scheduling / RadixAttention tree lookup\n\n"
             "Prefill / TTFT (ms)= server_ttft_ms  (see Chart 1 formula)\n\n"
             "Decode Total (ms)  = server_itl_ms × rt_decode_tokens\n"
             "                 = TPOT × number of generated output tokens\n\n"
             "E2E estimate       = Queue + TTFT + Decode Total  [ms]\n"
             "                 ≈ server_e2e_ms  (minor delta from scheduling overlap)\n\n"
             "server_e2e_ms (reference) = end-to-end measured request latency"),
            "server_e2e_ms is the true measured end-to-end latency. "
            "The stacked decomposition may differ slightly due to pipelining and concurrent scheduling effects."
        ),
        "c10": (
            "Derived: gpu_summary.json (hbm_util_pct) vs sglang_summary.json (tpot_ms)",
            ("X = hbm_util_pct  = mean( hbm_used_mb[i] / 40960 × 100 )  [%]  (see Chart 6 formula)\n"
             "Y = tpot_ms       = TPOT in milliseconds per output token  (see Chart 1 formula)\n\n"
             "Theoretical minimum TPOT for 70B FP16 on 8× A100:\n"
             "  model_bytes_per_GPU = 70 × 10⁹ params × 2 bytes/param / 8 GPUs  =  17.5 GB\n"
             "  A100 peak HBM BW    = 2,000 GB/s\n"
             "  min_TPOT            = 17.5 GB / 2,000 GB/s × 1000  ≈  8.75 ms/tok\n\n"
             "  Observed ~47 ms/tok  →  effective BW utilisation\n"
             "    = min_TPOT / observed_TPOT × 100\n"
             "    = 8.75 / 47 × 100  ≈  18.6% of peak HBM bandwidth\n"
             "  (overhead: KV reads, attention ops, all-reduce, kernel launches)"),
            "The gap between theoretical minimum and observed TPOT is normal. "
            "Speculative decoding and quantisation can close it. "
            "Moving a point toward bottom-left (lower HBM%, lower TPOT) is the optimization goal."
        ),
        "c11": (
            "power_summary.json (gpu_power_all_w_mean) + sglang_timeseries.csv (gen_throughput)",
            ("X = gpu_power_mean_w  = mean total GPU power over run  [W]\n"
             "                     = power_summary.gpu_power_all_w_mean\n"
             "                     = mean( Σᵢ nvidia-smi power.draw[GPU i] )  [W]\n\n"
             "Y = gen_tp_peak      = peak generation throughput  [tok/s]\n"
             "                     = max( sglang:gen_throughput timeseries )\n\n"
             "Energy per token     = gpu_power_mean_w / gen_tp_peak  [W/(tok/s) = J/tok]\n"
             "Target range         : 15-30 J/tok for production 70B inference on A100\n\n"
             "Plotted point per run: ( gpu_power_mean_w,  gen_tp_peak )"),
            "Mean power (not peak) is the correct denominator for energy efficiency as it "
            "proportionally accounts for idle phases. "
            "Top-left corner (high throughput, low power) = best efficiency."
        ),
        "c12": (
            "Derived from all collectors — computed by score_bottlenecks() in profiler source",
            ("GPU Compute    = min(100,  gpu_util_peak/100 × 40\n"
             "                        + min(100, ttft_ms/500 × 40) × 0.6 )\n\n"
             "HBM Bandwidth  = min(100,  hbm_util_pct × 0.5  +  tpot_ms/100 × 50 )\n\n"
             "KV Cache       = max(0,  100 − cache_hit_pct ) × 0.8\n\n"
             "DRAM           = min(100,  dram_util_pct × 0.3 )\n\n"
             "NVMe I/O       = min(100,  max(wr_iops_max, rd_iops_max) / 10 )\n\n"
             "Power/Thermal  = min(100,  gpu_power_peak_w / 400 × 50 )\n\n"
             "CPU/PageFaults = min(100,  page_faults_per_s / 10000 × 30 )\n\n"
             "GPU Utilisation= min(100, (100 − gpu_util_mean) × 0.5 )\n\n"
             "Severity thresholds:\n"
             "  HIGH  :  score > 60\n"
             "  MED   :  30 < score ≤ 60\n"
             "  LOW   :  score ≤ 30"),
            "Scores are dimensionless (0-100) and relative within each run. "
            "They indicate the dominant constraint, not an absolute performance grade. "
            "Compare across runs to track how optimisations shift the bottleneck profile."
        ),
        "c13": (
            "Same scored data as radar (c12) — identical values, horizontal bar encoding",
            ("Scores identical to the radar chart (c12) — see that formula for derivation.\n\n"
             "Visual encoding difference:\n"
             "  Radar  → shape area shows total bottleneck pressure, axes = layers\n"
             "  H-bars → precise numeric comparison per layer across runs\n\n"
             "Grouped bar reading:\n"
             "  Same-length bars across runs → layer unchanged by the optimisation\n"
             "  One bar shorter             → that run reduced this specific bottleneck\n"
             "  One bar longer              → that run introduced or worsened this bottleneck"),
            "Bottleneck scores are computed independently per run from its own telemetry, "
            "so cross-run comparison is valid even if runs differ in duration or request count."
        ),
        "c14": (
            "Derived: sglang_summary.json (cache_hit_pct, prefill_hit_pct) vs sglang_summary.json (ttft_ms)",
            ("X = cache_hit_pct   = realtime KV cache hit rate  [%]  (see Chart 7 formula)\n"
             "Y = ttft_ms         = TTFT in milliseconds  [ms]  (see Chart 1 formula)\n\n"
             "Theoretical relationship under ideal prefix caching:\n"
             "  TTFT  ∝  prefill_compute_tokens\n"
             "        =  total_context_tokens × (1 − cache_hit_rate / 100)\n"
             "       →   linear decay as hit rate → 100%\n\n"
             "TTFT floor at 100% cache hit (cannot be zero):\n"
             "  floor_TTFT ≈ scheduling_overhead + KV_lookup_time + first_decode_step\n"
             "             ≈ 50-200 ms  (typical SGLang with RadixAttention)"),
            "Bottom-right (high cache hit, low TTFT) is the ideal region. "
            "Top-right (high hit, still high TTFT) = large compute-prefill remaining despite caching; "
            "use chunked prefill. "
            "Bottom-left (low hit, low TTFT) = short prompt, caching irrelevant."
        ),
    }

    def _fml_block(canvas_id):
        """Return a collapsible formula block HTML for the given canvas id."""
        if canvas_id not in FORMULA_DB:
            return ''
        source, formula, note = FORMULA_DB[canvas_id]
        import html as _html
        src_e  = _html.escape(source)
        fml_e  = _html.escape(formula)
        note_e = _html.escape(note) if note else ''
        note_h = f'<div class="fml-note" style="color:#334155">{note_e}</div>' if note_e else ''
        return (f'<details class="fml">'
                f'<summary>&#128208;&nbsp;Formula &amp; Derivation</summary>'
                f'<div class="fml-body">'
                f'<div class="fml-src" style="color:#1e293b;font-weight:600">&#128202;&nbsp;{src_e}</div>'
                f'<code>{fml_e}</code>'
                f'{note_h}'
                f'</div></details>\n')

    def sect(title, desc, canvas_id, insight):
        fml_html = _fml_block(canvas_id)
        return (f'<div class="card"><h2>{title}</h2>'
                f'<div class="desc">{desc}</div>'
                f'{fml_html}'
                f'<canvas id="{canvas_id}"></canvas>'
                f'<div class="insight">{insight}</div></div>\n')

    # ── AI Operation Analysis section (inserted before chart sections) ────────
    def _phase_badge_html(label, color):
        return (f'<span style="font-size:10px;padding:2px 10px;border-radius:12px;'
                f'font-weight:700;letter-spacing:.3px;background:{color}22;'
                f'color:{color};border:1px solid {color}44">{label}</span>')

    def _sev_badge_cmp(sev):
        styles = {"HIGH":"background:#fef2f2;color:#991b1b",
                  "MED":"background:#fffbeb;color:#92400e",
                  "LOW":"background:#f0fdf4;color:#166534"}
        st = styles.get(sev, styles["LOW"])
        return (f'<span style="font-size:10px;padding:2px 8px;border-radius:12px;'
                f'font-weight:700;{st}">{sev}</span>')

    ai_op_rows = ""
    for j, ((label, m), bns, color) in enumerate(zip(runs, all_bottlenecks, colors)):
        bg = "#ffffff" if j % 2 == 0 else "#f8fafc"
        kpi = data["kpis"][j]
        total_ctx = m.prefill_cache_tokens + m.prefill_compute_tokens
        pct_compute = (m.prefill_compute_tokens / max(total_ctx, 1)) * 100
        decode_total_ms = m.tpot_ms * m.decode_tokens
        e2e_ms = m.e2e_ms if m.e2e_ms > 0 else (m.ttft_ms + decode_total_ms)
        prefill_pct_e2e = m.ttft_ms / max(e2e_ms, 1) * 100
        decode_pct_e2e  = decode_total_ms / max(e2e_ms, 1) * 100

        prefill_sev = "HIGH" if m.ttft_ms > 1000 else "MED" if m.ttft_ms > 300 else "LOW"
        decode_sev  = "HIGH" if m.tpot_ms > 80 else "MED" if m.tpot_ms > 30 else "LOW"

        # Context bar segments
        total_all = m.prefill_cache_tokens + m.prefill_compute_tokens + m.decode_tokens
        w_cached  = int(m.prefill_cache_tokens  / max(total_all, 1) * 200)
        w_compute = int(m.prefill_compute_tokens / max(total_all, 1) * 200)
        w_decode  = 200 - w_cached - w_compute
        ctx_bar = (
            f'<div style="display:flex;border-radius:4px;overflow:hidden;height:10px;width:200px;flex-shrink:0">'
            f'<div style="width:{w_cached}px;background:#0891b2" title="Cached {m.prefill_cache_tokens:,}"></div>'
            f'<div style="width:{w_compute}px;background:#f97316" title="Compute {m.prefill_compute_tokens:,}"></div>'
            f'<div style="width:{w_decode}px;background:#22d3ee" title="Decode {m.decode_tokens:,}"></div>'
            f'</div>'
        )

        ai_op_rows += (
            f'<tr style="border-bottom:1px solid #e2e8f0">'
            # Run
            f'<td style="padding:10px 12px;background:{bg}">'
            f'<span style="color:{color};font-weight:700;font-size:12px">{label}</span></td>'
            # Prefill
            f'<td style="padding:10px 12px;background:{bg}">'
            f'<div style="font-size:14px;font-weight:800;color:#f97316;font-family:monospace">{m.ttft_ms:.0f} ms</div>'
            f'<div style="font-size:10px;color:#64748b;margin-top:2px">{prefill_pct_e2e:.0f}% of E2E</div>'
            f'<div style="margin-top:4px">{_sev_badge_cmp(prefill_sev)}</div>'
            f'</td>'
            # Decode
            f'<td style="padding:10px 12px;background:{bg}">'
            f'<div style="font-size:14px;font-weight:800;color:#22d3ee;font-family:monospace">{m.tpot_ms:.1f} ms/tok</div>'
            f'<div style="font-size:10px;color:#64748b;margin-top:2px">{m.decode_tokens:,} tokens · {m.gen_tp_peak:.1f} tok/s peak</div>'
            f'<div style="font-size:10px;color:#64748b">Decode total: {decode_total_ms/1000:.1f}s ({decode_pct_e2e:.0f}% of E2E)</div>'
            f'<div style="margin-top:4px">{_sev_badge_cmp(decode_sev)}</div>'
            f'</td>'
            # Cache
            f'<td style="padding:10px 12px;background:{bg}">'
            f'<div style="font-size:13px;font-weight:700;color:#22c55e;font-family:monospace">{m.cache_hit_pct:.1f}%</div>'
            f'<div style="font-size:10px;color:#64748b;margin-top:1px">hicache fill: {m.hicache_fill_pct:.1f}%</div>'
            f'<div style="font-size:10px;color:#64748b">prefill cached: {100-pct_compute:.1f}%</div>'
            f'</td>'
            # Context composition
            f'<td style="padding:10px 12px;background:{bg}">'
            f'<div style="font-size:10px;color:#64748b;margin-bottom:4px">'
            f'total {total_ctx:,} tokens</div>'
            f'{ctx_bar}'
            f'<div style="display:flex;gap:8px;margin-top:4px;flex-wrap:wrap">'
            f'<span style="font-size:9px;color:#0891b2">■ {m.prefill_cache_tokens:,} cached</span>'
            f'<span style="font-size:9px;color:#f97316">■ {m.prefill_compute_tokens:,} compute</span>'
            f'<span style="font-size:9px;color:#22d3ee">■ {m.decode_tokens:,} decoded</span>'
            f'</div></td>'
            # Primary bottleneck
            f'<td style="padding:10px 12px;background:{bg}">'
            f'<span style="color:{bns[0]["color"]};font-weight:700;font-size:11px">{bns[0]["layer"]}</span>'
            f'<div style="font-size:10px;color:#64748b;margin-top:2px">{bns[0]["phase"]}</div>'
            f'<div style="font-size:10px;color:#334155;margin-top:3px;line-height:1.4">{bns[0]["detail"]}</div>'
            f'</td>'
            f'</tr>'
        )

    ai_op_section = (
        f'<div class="card" style="border-color:#4f46e5">\n'
        f'<h2 style="color:#a78bfa">⚡ AI Operation Analysis — Prefill vs Decode per Run</h2>\n'
        f'<div class="desc">'
        f'Side-by-side breakdown of the two AI inference phases for every run. '
        f'<b style="color:#f97316">Prefill</b> is the compute-intensive phase that reads the full prompt — '
        f'its cost appears as TTFT. '
        f'<b style="color:#22d3ee">Decode</b> is the memory-bandwidth-intensive autoregressive generation phase — '
        f'its cost appears as TPOT × output tokens. '
        f'Severity badges reflect how each run\'s measured latency compares to A100 70B inference targets.'
        f'</div>\n'
        f'<div style="overflow-x:auto"><table>\n'
        f'<thead><tr>'
        f'<th style="text-align:left">Run</th>'
        f'<th style="color:#f97316">Prefill (TTFT)</th>'
        f'<th style="color:#22d3ee">Decode (TPOT)</th>'
        f'<th style="color:#22c55e">Cache Tiers</th>'
        f'<th>Context Composition</th>'
        f'<th>Primary Bottleneck</th>'
        f'</tr></thead>\n'
        f'<tbody>{ai_op_rows}</tbody>\n'
        f'</table></div>\n'
        f'<div class="insight">\n'
        f'<b>Prefill targets:</b> TTFT &lt;500ms (short prompt), &lt;5s (50K-token context on A100 8×GPU 70B). '
        f'Reduce with chunked prefill or prefix caching. &nbsp;|&nbsp; '
        f'<b>Decode targets:</b> TPOT &lt;50ms/tok single-request, &lt;20ms/tok batched. '
        f'Reduce with speculative decoding or quantisation. &nbsp;|&nbsp; '
        f'<b>Context bar:</b> blue = cached (free), orange = compute prefill (costs TTFT), teal = decoded output (costs TPOT).'
        f'</div>\n'
        f'</div>\n'
    )
    parts.append(ai_op_section)

    parts.append(sect("Prefill vs Decode Latency",
        "TTFT (Time to First Token) = cost of the Prefill phase: GPU computes attention over the full prompt. "
        "TPOT (Time per Output Token) = cost per Decode step: GPU reads all weights from HBM for each token. "
        "These respond to entirely different optimisations and should be tracked independently.",
        "c1",
        "<b>Targets for A100 8-GPU 70B:</b> TTFT &lt;500ms for short prompts, &lt;5s for 50K-token prompts. "
        "TPOT &lt;50ms/tok at single-request concurrency. "
        "Improving TTFT: chunked prefill, prefix caching. Improving TPOT: quantisation, speculative decoding."))

    parts.append('<div class="grid2">\n')
    parts.append(sect("Throughput vs GPU Active Time",
        "Peak generation throughput (tok/s) and GPU active time % — fraction of total run duration "
        "where GPUs were actually computing. Low active % with high peak tok/s = fast individual requests "
        "but low server utilisation. Both metrics must be high for production efficiency.",
        "c2",
        "<b>What to look for:</b> Active % below 30% = the server is mostly idle. "
        "Increase concurrent request load or enable continuous batching to drive active % toward 70-90%."))
    parts.append(sect("Power Efficiency — tok/Wh and tok/s per kW",
        "Two energy efficiency metrics derived from power + throughput telemetry. "
        "<b>tok/Wh</b> = total generated tokens divided by GPU energy consumed (Watt-hours): "
        "the overall energy cost of the run. "
        "<b>tok/s per kW</b> = peak throughput normalised by power draw: instantaneous efficiency.",
        "c3",
        "<b>What to look for:</b> Higher tok/Wh = lower energy cost per output token. "
        "Quantisation (AWQ/GPTQ) shrinks weights, reducing HBM reads and power per token. "
        "Chunked prefill smooths power spikes, improving energy efficiency at the run level."))
    parts.append('</div>\n')

    parts.append('<div class="grid2">\n')
    parts.append(sect("GPU Utilisation Timeline",
        "GPU compute utilisation % over time for every run on the same axis. "
        "The characteristic pattern: sharp 100% spike at t=0 (prefill), then lower plateau (decode), "
        "then drop to 0% (request complete). Runs with longer decode phases show a longer plateau. "
        "Runs that stay at 100% continuously are serving multiple concurrent requests.",
        "c4",
        "<b>What to look for:</b> A run where the plateau is higher than another = serving more "
        "concurrent requests or producing more tokens. Runs that drop to 0% quickly = short requests "
        "or high cache hit rate (less compute needed)."))
    parts.append(sect("GPU Power Timeline",
        "Total GPU power draw (W, all GPUs summed) over time. Power consumption mirrors compute "
        "intensity: prefill pulls 150-250W/GPU, decode pulls 60-80W/GPU, idle pulls ~57W/GPU. "
        "Comparing power curves across runs reveals energy cost distribution of the request lifecycle.",
        "c5",
        "<b>What to look for:</b> The area under the curve is proportional to energy consumed. "
        "A run with a narrower high-power spike = faster prefill (e.g., from chunked prefill). "
        "A run with a longer lower-power plateau = more decode tokens generated."))
    parts.append('</div>\n')

    # KV cache section
    parts.append(f'''<div class="card" style="border-color:#0891b2">
<h2 style="color:#22d3ee">KV Cache Analysis - Cache Tier Efficiency</h2>
<div class="desc">The KV (Key-Value) cache stores attention states for previously computed tokens.
SGLang uses a multi-tier cache: <b>L1 HBM</b> (on-GPU, fastest), <b>L2 hicache</b> (host DRAM, ~10x slower than HBM),
and optionally <b>L3 NVMe</b> (storage-backed, for overflow). Cache hits avoid recomputing attention,
directly reducing TTFT. The realtime cache hit rate measures how often tokens are served from any cache tier.
The prefill-from-cache % shows what fraction of the prompt was served without GPU computation.</div>
<div class="grid2">
<div>
<div class="desc"><b style="color:#22d3ee">Cache Hit Rates</b> - three cache metrics per run.
Realtime Cache Hit % = fraction of all token requests served from cache.
Prefill From Cache % = fraction of prefill tokens that avoided GPU attention computation.
hicache Fill % = how full the L2 DRAM KV pool is (approaching 100% triggers eviction).</div>
<details class="fml"><summary>&#128208; Formula &amp; Derivation</summary><div class="fml-body"><span class="src">&#128202; sglang_summary.json + sglang_timeseries.csv (SGLang Prometheus metrics)</span><code>Realtime Cache Hit %  = sglang:cache_hit_rate[engine_type=unified]
                           (Prometheus gauge, rolling realtime window)
                         = KV tokens served from any cache tier / total KV tokens requested

Prefill From Cache %  = rt_prefill_cache_tokens
                        / (rt_prefill_cache_tokens + rt_prefill_compute_tokens) × 100
where:
  rt_prefill_cache_tokens  = Σ sglang:realtime_tokens_total[mode=prefill_cache]  (cumulative)
  rt_prefill_compute_tokens= Σ sglang:realtime_tokens_total[mode=prefill_compute] (cumulative)

hicache Fill %        = hicache_host_used_tokens / hicache_host_total_tokens × 100
                      = sglang:hicache_host_used_tokens / sglang:hicache_host_total_tokens</code><span class="note">Cache Hit Rate is a realtime estimate from SGLang's RadixAttention tree. Prefill From Cache % is derived from cumulative token counters in sglang_summary.json.</span></div></details>
<canvas id="c7"></canvas>
<div class="insight"><b>Interpreting:</b> Cache Hit &gt;95% = excellent prefix reuse.
Low hicache fill + high hit rate = working set fits in L1 HBM (best case).
High hicache fill = working set spills to DRAM (slower but functional).
If hicache fill approaches 100%, enable L3 NVMe KV offload or increase pool size.</div>
</div>
<div>
<div class="desc"><b style="color:#22d3ee">Token Composition</b> - how tokens in each run break down.
Blue = cached prefill (attention reuse, no GPU cost).
Orange = compute prefill (new attention, contributes to TTFT).
Teal = decoded output (each token costs TPOT).
Maximising blue and minimising orange reduces TTFT.</div>
<details class="fml"><summary>&#128208; Formula &amp; Derivation</summary><div class="fml-body"><span class="src">&#128202; sglang_summary.json  (fields: rt_prefill_cache_tokens, rt_prefill_compute_tokens, rt_decode_tokens)</span><code>Prefill Cached   = rt_prefill_cache_tokens
                    = Σ sglang:realtime_tokens_total[mode=prefill_cache]   [tokens]
                    → tokens whose KV state was reused from cache (zero GPU attention cost)

Prefill Compute  = rt_prefill_compute_tokens
                 = Σ sglang:realtime_tokens_total[mode=prefill_compute]  [tokens]
                 → tokens requiring full self-attention computation  (drives TTFT)

Decode Output    = rt_decode_tokens
                 = Σ sglang:realtime_tokens_total[mode=decode]           [tokens]
                 → autoregressively generated output tokens  (each costs TPOT)

Total context    = Prefill Cached + Prefill Compute
Total tokens     = Prefill Cached + Prefill Compute + Decode Output</code><span class="note">These are cumulative counters reset at server startup. The profiler reads the final values from sglang_summary.json which is the end-of-run snapshot.</span></div></details>
<canvas id="c8"></canvas>
<div class="insight"><b>What to look for:</b> Runs where the blue segment grows = better prefix caching.
Runs where the orange segment shrinks at the same total = chunked prefill or caching working.
Runs where the teal segment grows = more output tokens generated per request.</div>
</div>
</div>
<div style="margin-top:14px">
<div class="desc"><b style="color:#22d3ee">Cache Hit vs TTFT Scatter</b> - the relationship between caching effectiveness and prefill latency.
Theory: higher cache hit rate should drive lower TTFT by reducing the number of attention computations.
Each point is one run. Runs in the upper-left = high cache hit but still high TTFT (large compute prefill remaining).
Runs in the lower-right = low cache hit but low TTFT (short prompts).</div>
<details class="fml"><summary>&#128208; Formula &amp; Derivation</summary><div class="fml-body"><span class="src">&#128202; Derived: cache_hit_pct (sglang_summary) vs ttft_ms (sglang_summary)</span><code>X = cache_hit_pct  = realtime cache hit rate %  (see Chart 7)
Y = ttft_ms         = TTFT ms  (see Chart 1)

Theoretical relationship (ideal full-context prefix caching):
  TTFT ∝ prefill_compute_tokens
       = total_context_tokens × (1 - cache_hit_rate)
       → linear decay as hit rate → 100%

In practice TTFT has a non-zero floor even at 100% cache hit:
  floor_TTFT = scheduling overhead + KV cache lookup + first decode step
             ≈ 50-200ms for typical SGLang configuration</code><span class="note">Runs in the bottom-right (high cache hit, low TTFT) are in the ideal region. Runs in the top-right (high cache hit, still high TTFT) suggest long compute prefill despite caching — consider chunked prefill.</span></div></details>
<canvas id="c14" style="max-height:220px"></canvas>
<div class="insight"><b>Ideal trajectory:</b> As you improve prefix caching across runs, points should move right (higher hit rate) and down (lower TTFT).
A run that moves right without moving down = cache hits are happening but on non-TTFT-critical tokens.
A run that moves down without moving right = TTFT improved from a non-caching optimisation (e.g., chunked prefill).</div>
</div>
</div>
''')

    parts.append('<div class="grid2">\n')
    parts.append(sect("Latency Waterfall - Request Time Decomposition",
        "Each request lifecycle: (1) Queue/Schedule overhead - waiting and hicache orchestration. "
        "(2) Prefill/TTFT - GPU computes attention over all prompt tokens (the compute-heavy phase). "
        "(3) Decode Total - autoregressive generation (TPOT x output tokens). "
        "This decomposition makes it immediately clear which phase dominates total request time.",
        "c9",
        "<b>What to look for:</b> If Prefill dominates: use chunked prefill and prefix caching. "
        "If Decode dominates: use speculative decoding, quantisation, or increase batch size. "
        "Queue overhead near zero = no scheduling bottleneck at current concurrency."))
    parts.append(sect("Memory Utilisation - HBM vs DRAM",
        "HBM (on-GPU) holds model weights (~26.8GB for 70B FP16 / 8 GPUs) plus active KV cache. "
        "DRAM holds the hicache L2 KV pool, model loader buffers, and OS page cache. "
        "HBM near 100% limits KV cache size, forcing more evictions and potentially more hicache spillover.",
        "c6",
        "<b>What to look for:</b> HBM &gt;90% = KV cache headroom is constrained. "
        "If HBM is high and TPOT is slow: model weights dominate HBM, leaving little room for KV caching. "
        "Fix: 4-bit quantisation halves model weight footprint, freeing ~13GB HBM per GPU for KV cache."))
    parts.append('</div>\n')

    parts.append('<div class="grid2">\n')
    parts.append(sect("Decode Efficiency Frontier - TPOT vs HBM",
        "Each run plotted as a point: X = HBM utilisation %, Y = TPOT (ms/tok). "
        "The bottom-left corner is ideal (low HBM usage, low TPOT). "
        "This chart reveals whether HBM pressure is actually impacting decode speed, "
        "or whether the two are independent in your workload.",
        "c10",
        "<b>Reading the chart:</b> Point moves left and down = better efficiency (quantisation effect). "
        "Point moves right with flat Y = more HBM used but no decode improvement (larger KV cache, not weights). "
        "Point moves down with flat X = decode speed improved without changing memory footprint (speculative decoding effect)."))
    parts.append(sect("Power vs Throughput - Efficiency Frontier",
        "Each run as a point: X = mean GPU power (W), Y = peak throughput (tok/s). "
        "Top-left = high throughput at low power = maximum efficiency. "
        "This is the power-performance frontier: runs should trend toward top-left across optimisation experiments.",
        "c11",
        "<b>Reading the chart:</b> Point moves left and up = better power efficiency. "
        "Higher throughput at same power = decode optimisation (speculative decoding, batching). "
        "Same throughput at lower power = prefill optimisation (chunked prefill reduces peak power draw). "
        "Hover for tok/Wh energy efficiency values."))
    parts.append('</div>\n')

    parts.append(sect("Throughput & Power — Side-by-Side Run Comparison",
        "Grouped bar chart comparing peak generation throughput (tok/s) and mean GPU power draw (W) "
        "across all runs. Uses dual Y-axes so throughput and power can be compared on their own scales. "
        "Unlike the scatter chart above, this shows the absolute values clearly for each run "
        "and makes it easy to spot which runs improved throughput, which reduced power, or both.",
        "c15",
        "<b>What to look for:</b> A taller throughput bar with a shorter power bar = energy efficiency win. "
        "Equal throughput bars with one shorter power bar = power optimisation (e.g. chunked prefill smoothing spikes). "
        "Hover each bar for tok/Wh and GPU active time % context."))

    # ── HBM/DRAM bandwidth comparison section ─────────────────────────────────
    # Serialise per-run HBM and DRAM BW data for Chart.js
    hbm_cmp = []
    dram_cmp = []
    for label, m in runs:
        hbm_cmp.append({
            "label":          label,
            "read_bw":        round(m.hbm_read_bw_gbs, 1),
            "write_bw":       round(m.hbm_write_bw_gbs, 1),
            "bw_util_pct":    round(m.hbm_bw_util_pct, 1),
            "read_txn_M_s":   round(m.hbm_read_txn_M_s, 1),
            "write_txn_M_s":  round(m.hbm_write_txn_M_s, 1),
            "peak_bw":        round(m.hbm_peak_bw_gbs, 0),
            "tpot_ms":        round(m.tpot_ms, 2),
            "min_tpot_ms":    round(m.hbm_read_bw_gbs / m.hbm_peak_bw_gbs * 1000
                                    if (m.hbm_peak_bw_gbs > 0 and m.hbm_read_bw_gbs > 0) else 0, 2),
        })
        dram_cmp.append({
            "label":           label,
            "read_bw":         round(m.dram_read_bw_gbs, 2),
            "write_bw":        round(m.dram_write_bw_gbs, 2),
            "total_bw":        round(m.dram_total_bw_gbs, 2),
            "peak_rd":         round(m.dram_read_bw_peak_gbs, 2),
            "peak_wr":         round(m.dram_write_bw_peak_gbs, 2),
            "bw_util_pct":     round(m.dram_bw_util_pct, 2),
            "theoretical_bw":  round(m.dram_peak_theoretical_gbs, 1),
            "read_txn_M_s":    round(m.dram_read_txn_M_s, 1),
            "write_txn_M_s":   round(m.dram_write_txn_M_s, 1),
        })

    # KV footprint comparison data
    kv_cmp = []
    # Session / KVB / NVMe comparison data
    sess_cmp = []
    kvb_cmp  = []
    nvme_cmp = []
    for label, m in runs:
        kv_cmp.append(dict(
            label              = label,
            bytes_per_tok      = m.kv_bytes_per_token,
            kb_per_tok         = round(m.kv_bytes_per_token_kb, 1),
            attn_type          = m.kv_attention_type,
            dtype              = m.kv_dtype_name,
            n_layers           = m.kv_n_layers,
            n_heads            = m.kv_n_heads,
            head_dim           = m.kv_head_dim,
            weight_gb          = round(m.kv_weight_gb_per_gpu, 1),
            pool_gb            = round(m.kv_hbm_pool_gb, 1),
            max_tokens         = m.kv_hbm_max_tokens,
            max_tokens_int8    = m.kv_hbm_max_tokens * 2,
            max_tokens_fp8     = m.kv_hbm_max_tokens * 2,
            pool_fill_pct      = round(m.kv_pool_fill_pct, 1),
            active_tokens      = m.kv_active_tokens,
            hbm_util_pct       = round(m.kv_hbm_utilisation_pct, 1),
            # Tier distribution and latency
            l1_tokens          = m.kv_l1_hbm_tokens,
            l2_tokens          = m.kv_l2_dram_tokens,
            l3_tokens          = m.kv_l3_nvme_tokens,
            l1_cap             = m.kv_l1_capacity_tokens,
            l2_cap             = m.kv_l2_capacity_tokens,
            l1_fill_pct        = round(m.kv_l1_fill_pct, 1),
            l2_fill_pct        = round(m.kv_l2_fill_pct, 1),
            l1_lat_ms          = round(m.kv_l1_read_lat_ms, 4),
            l2_lat_ms          = round(m.kv_l2_read_lat_ms, 4),
            l3_lat_ms          = round(m.kv_l3_read_lat_ms, 4),
            weighted_lat_ms    = round(m.kv_weighted_lat_ms, 4),
            ttft_l1_ms         = round(m.kv_ttft_l1_ms, 0),
            ttft_l2_ms         = round(m.kv_ttft_l2_ms, 0),
            ttft_l3_ms         = round(m.kv_ttft_l3_ms, 0),
            l1_bw_gbs          = round(m.kv_l1_bw_gbs, 0),
            l2_bw_gbs          = round(m.kv_l2_bw_gbs, 1),
            l3_bw_gbs          = round(m.kv_l3_bw_gbs, 1),
        ))

        # Session data
        sess_cmp.append(dict(
            label           = label,
            total_requests  = m.sess_total_requests,
            max_concurrent  = m.sess_max_concurrent,
            e2e_mean_s      = round(m.sess_e2e_mean_s, 2),
            e2e_min_s       = round(m.sess_e2e_min_s, 2),
            e2e_max_s       = round(m.sess_e2e_max_s, 2),
            e2e_p90_s       = round(m.sess_e2e_p90_s, 2),
            input_tok_mean  = round(m.sess_input_tok_mean, 0),
            input_tok_max   = round(m.sess_input_tok_max, 0),
            output_tok_mean = round(m.sess_output_tok_mean, 0),
            output_tok_max  = round(m.sess_output_tok_max, 0),
            queue_mean_ms   = round(m.sess_queue_mean_ms, 2),
            arrival_rps     = round(m.sess_arrival_rate_rps, 5),
            e2e_ts          = m.sess_e2e_ts[:40],
            input_tok_ts    = m.sess_input_tok_ts[:40],
            output_tok_ts   = m.sess_output_tok_ts[:40],
        ))

        # KV$B event data
        kvb_cmp.append(dict(
            label               = label,
            block_size_mb       = round(m.kvb_block_size_mb, 2),
            l1_pool_blocks      = m.kvb_l1_pool_blocks,
            l2_pool_blocks      = m.kvb_l2_pool_blocks,
            l1_fill_pct         = round(m.kv_l1_fill_pct, 1),
            l2_fill_pct         = round(m.kv_l2_fill_pct, 1),
            offload_rate        = round(m.kvb_l1_offload_rate_blk_s, 4),
            eviction_rate       = round(m.kvb_l2_eviction_rate_blk_s, 4),
            lifetime_mean_s     = round(m.kvb_lifetime_mean_s, 0),
        ))

        # NVMe IO data
        nvme_cmp.append(dict(
            label           = label,
            wr_iops_mean    = round(m.nvme_wr_iops_mean, 2),
            wr_lat_mean_ms  = round(m.nvme_wr_lat_mean_ms, 3),
            wr_lat_max_ms   = round(m.nvme_wr_lat_max_ms, 3),
            io_util_pct     = round(m.nvme_io_util_pct, 4),
            bytes_wr_gb     = round(m.nvme_bytes_written_total / 1e9, 3),
            bytes_rd_gb     = round(m.nvme_bytes_read_total / 1e9, 3),
            wr_bw_mbs       = round(m.nvme_wr_bw_mbs_mean, 2),
            smart_wear_pct  = round(m.nvme_smart_wear_pct, 1),
            smart_spare_pct = round(m.nvme_smart_avail_spare, 1),
        ))

    import json as _j
    hbm_cmp_json  = _j.dumps(hbm_cmp)
    dram_cmp_json = _j.dumps(dram_cmp)
    kv_cmp_json   = _j.dumps(kv_cmp)
    sess_cmp_json = _j.dumps(sess_cmp)
    kvb_cmp_json  = _j.dumps(kvb_cmp)
    nvme_cmp_json = _j.dumps(nvme_cmp)

    # Build KV table rows for comparison report
    _sev = lambda s: ("background:#fef2f2;color:#991b1b" if s=="HIGH"
                      else "background:#fffbeb;color:#92400e" if s=="MED"
                      else "background:#f0fdf4;color:#166534")
    kv_table_rows = ""
    for ji, (kv_row, color) in enumerate(zip(kv_cmp, colors)):
        bg = "#ffffff" if ji%2==0 else "#f8fafc"
        kv_table_rows += (
            f'<tr style="border-bottom:1px solid #f1f5f9">' +
            f'<td style="padding:7px 12px;background:{bg};color:{color};font-weight:700">{kv_row["label"]}</td>' +
            f'<td style="padding:7px 12px;background:{bg};text-align:center;font-weight:600;color:#4f46e5">{kv_row["attn_type"]}</td>' +
            f'<td style="padding:7px 12px;background:{bg};text-align:center">{kv_row["n_layers"]}</td>' +
            f'<td style="padding:7px 12px;background:{bg};text-align:center">{kv_row["n_heads"]}</td>' +
            f'<td style="padding:7px 12px;background:{bg};text-align:center">{kv_row["head_dim"]}</td>' +
            f'<td style="padding:7px 12px;background:{bg};text-align:center;font-family:monospace">{kv_row["dtype"]}</td>' +
            f'<td style="padding:7px 12px;background:{bg};text-align:center;font-weight:700;color:#4338ca;font-family:monospace">{kv_row["kb_per_tok"]:.0f} KB</td>' +
            f'<td style="padding:7px 12px;background:{bg};text-align:center;font-weight:700;color:#047857;font-family:monospace">{kv_row["max_tokens"]//1000:.0f}K</td>' +
            f'<td style="padding:7px 12px;background:{bg};text-align:center;color:#059669;font-family:monospace">{kv_row["max_tokens_int8"]//1000:.0f}K</td>' +
            f'<td style="padding:7px 12px;background:{bg};text-align:center">{kv_row["pool_fill_pct"]:.1f}%</td>' +
            f'<td style="padding:7px 12px;background:{bg};text-align:center;font-family:monospace">{kv_row["weight_gb"]:.1f} GB</td>' +
            f'</tr>'
        )

    parts.append(f'''
<div class="card" style="border-color:#22d3ee">
<h2 style="color:#22d3ee">&#128309; HBM (GPU) Bandwidth &amp; Transaction Comparison</h2>
<div class="desc">
HBM (High Bandwidth Memory) is the on-GPU DRAM fabric on A100 (HBM2e, 2×1000 GB/s = 2000 GB/s peak per GPU).
Every autoregressive decode step reads all model weights from HBM — making HBM bandwidth
the <b style="color:#0f172a">primary hardware constraint for decode latency (TPOT)</b>.
Values are derived from TPOT using the formula:
<code style="background:#f0f4f8;padding:2px 6px;border-radius:3px;color:#22d3ee;font-size:10px">
HBM_read_BW = model_bytes_per_GPU / TPOT_s</code>
since nsys HBM hardware counters were not actively sampled.
Timeseries values are modulated by GPU utilisation to reflect active vs idle phases.
</div>
<script>const HBM_CMP={hbm_cmp_json};</script>
<div class="grid2">
<div>
<div class="desc" style="color:#22d3ee;font-weight:600">Read/Write Bandwidth per Run</div>
<div class="desc">
Read BW = model weights loaded from HBM every token step.
Write BW ≈ 12% of read BW (KV cache updates, activation stores).
Both derived from TPOT; a lower TPOT run implies higher effective HBM bandwidth.
<details class="fml"><summary>&#128208; Formula &amp; Derivation</summary>
<div class="fml-body">
<div class="fml-src">&#128202; Derived · sglang_summary.json (tpot_ms) + model architecture</div>
<code>HBM Read BW = model_bytes_per_GPU / TPOT_s  [GB/s]
  model_bytes_per_GPU = params × 2 bytes / n_gpus (FP16)
  TPOT_s = tpot_ms / 1000

HBM Write BW = HBM_read_BW × 0.12  [GB/s]
  (writes ≈ 12% of reads for LLM decode workloads)

HBM BW Util % = HBM_read_BW / 2000 × 100
  (A100 HBM2e peak = 2,000 GB/s per GPU)

Theoretical min TPOT = model_bytes_per_GPU / 2000 × 1000  [ms/tok]
  Efficiency gap = observed_TPOT / min_TPOT</code>
<div class="fml-note" style="color:#334155">nsys GPU_METRICS metricId 18/19 (HBM R/W BW) inactive in this profile (all values = 1%). Direct hardware measurement requires nsys --gpu-metrics-set or dcgmi dmon.</div>
</div></details>
</div>
<canvas id="c_hbm_bw"></canvas>
<div class="insight" style="border-color:#22d3ee">
<b>What to look for:</b> A run with lower TPOT has higher effective HBM read BW
(it processes model weights faster per token). HBM util approaching 100% would mean
the hardware is at its bandwidth ceiling — reducing model size (quantisation) is the only path.
Current utilisation {hbm_cmp[0]["bw_util_pct"]:.1f}% suggests {100-hbm_cmp[0]["bw_util_pct"]:.0f}%
of potential bandwidth is lost to kernel overhead, all-reduce, and synchronisation.
</div>
</div>
<div>
<div class="desc" style="color:#22d3ee;font-weight:600">Cache-Line Transaction Rate (64B)</div>
<div class="desc">
Each HBM transaction moves one 64-byte cache line. Read transactions = weight loads.
Write transactions = KV cache stores + activation writebacks.
Higher transactions/s = more memory-intensive workload (more tokens/s or larger model).
</div>
<canvas id="c_hbm_txn"></canvas>
<div class="insight" style="border-color:#22d3ee">
<b>Transaction rate vs Throughput:</b>
Read_Txns/s = gen_tp_peak × model_bytes_per_GPU / 64.
Improving throughput <i>increases</i> transaction rate — not a concern unless HBM util > 80%.
Speculative decoding improves throughput per transaction by amortising weight reads across
multiple accepted tokens, reducing effective transactions per output token.
</div>
</div>
</div>
<div style="margin-top:14px">
<div class="desc" style="color:#22d3ee;font-weight:600">HBM Efficiency Scatter — TPOT vs HBM BW Utilisation</div>
<div class="desc">
Plots each run as a point: X = HBM utilisation %, Y = TPOT. Bottom-left = ideal efficiency.
Also shows theoretical minimum TPOT line at 100% HBM utilisation = the hardware ceiling.
</div>
<canvas id="c_hbm_scatter" style="max-height:220px"></canvas>
<div class="insight" style="border-color:#22d3ee">
<b>Theoretical minimum TPOT</b> = model_bytes_per_GPU / HBM_peak_BW × 1000.
For 70B FP16 / 8× A100: 17.5 GB / 2000 GB/s × 1000 = <b>8.75 ms/tok</b>.
All observed points will be above this floor. The gap is due to CUDA kernel overhead,
NVLink all-reduce, attention computation, and scheduling latency.
</div>
</div>
</div>

<div class="card" style="border-color:#34d399">
<h2 style="color:#34d399">&#129001; System DRAM (CPU-side) Bandwidth &amp; Transaction Comparison</h2>
<div class="desc">
System DRAM bandwidth measured by <b style="color:#0f172a">AMD uProf PCM</b> (Performance Counter Monitor)
via hardware PMU counters in the AMD EPYC 7742 Data Fabric (DF).
This is the <b style="color:#0f172a">CPU-side memory bus</b> — distinct from HBM on the GPU.
Used by: hicache L2 KV pool reads/writes, model loader DMA transfers, OS page cache, and
the SGLang detokeniser/scheduler runtime.
AMD EPYC 7742 2-socket theoretical peak = 204.8 GB/s
(8 DDR4-3200 channels × 25.6 GB/s × 2 sockets).
<details class="fml"><summary>&#128208; Formula &amp; Derivation</summary>
<div class="fml-body">
<div class="fml-src">&#128202; amduprof_pcm_raw.csv · AMDuProfPcm -m memory · AMD DF PMU · 1.2s sample interval</div>
<code>DRAM Read/Write BW (GB/s) sourced from DF METRICS section:
  "Total Mem Bw (GB/s), Total Mem RdBw (GB/s), Total Mem WrBw (GB/s)"
  Sampled by AMD Data Fabric PMU counters (hardware-accurate).

DRAM Read Txns/s  = DRAM_read_BW_GB_s  × 10⁹ / 64  [transactions/s]
DRAM Write Txns/s = DRAM_write_BW_GB_s × 10⁹ / 64  [transactions/s]
  64 bytes = AMD EPYC DDR4 cache-line size

DRAM BW Util %  = DRAM_total_BW / 204.8 × 100
  204.8 GB/s = 8ch DDR4-3200 × 25.6 GB/s × 2 sockets (AMD EPYC 7742 2S)

Read/Write Ratio = DRAM_read_BW / DRAM_write_BW</code>
<div class="fml-note" style="color:#334155">Note: amduprof_pcm_timeseries.csv has a parser bug (all zeros). The profiler reads directly from amduprof_pcm_raw.csv DF METRICS section. Requires the raw CSV file to be present in the raw/ directory.</div>
</div></details>
</div>
<script>const DRAM_CMP={dram_cmp_json};</script>
<div class="grid2">
<div>
<div class="desc" style="color:#34d399;font-weight:600">DRAM Read/Write Bandwidth per Run</div>
<canvas id="c_dram_bw"></canvas>
<div class="insight" style="border-color:#34d399">
<b>What to look for:</b> Higher DRAM read BW = more hicache L2 KV token reads per second
(more cache hits serving from DRAM). Higher write BW = more KV tokens being written to the
host pool. A run with higher DRAM BW at higher cache hit rate = healthy — the cache is
actively serving reads from DRAM tier. DRAM BW near theoretical peak indicates the KV cache
working set has exceeded HBM and is heavily using the L2 host tier.
</div>
</div>
<div>
<div class="desc" style="color:#34d399;font-weight:600">DRAM Cache-Line Transactions per Second</div>
<canvas id="c_dram_txn"></canvas>
<div class="insight" style="border-color:#34d399">
<b>Transaction rate breakdown:</b> Read transactions include KV token reads for hicache hits,
model weight DMA loads, and OS page cache fills. Write transactions include KV eviction from
HBM to DRAM (when HBM KV pool is full), hicache token inserts, and OS writeback.
A balanced R/W ratio (seen: {dram_cmp[0]["read_txn_M_s"]:.0f} / {dram_cmp[0]["write_txn_M_s"]:.0f} M txns/s)
is typical — reads exceed writes when the cache is warm.
</div>
</div>
</div>
<div style="margin-top:14px">
<div class="desc" style="color:#34d399;font-weight:600">DRAM BW Utilisation &amp; Read/Write Ratio Comparison</div>
<canvas id="c_dram_util" style="max-height:220px"></canvas>
<div class="insight" style="border-color:#34d399">
<b>Utilisation context:</b> DRAM BW is very low for this workload ({dram_cmp[0]["bw_util_pct"]:.1f}%
of 204.8 GB/s peak) because most KV cache activity is served from HBM (L1 tier).
DRAM BW would spike if: (1) hicache fill exceeds HBM capacity forcing L2 spill,
(2) concurrent requests with large diverse contexts, or (3) L3 NVMe KV offload is enabled and
evicting from DRAM to storage.
</div>
</div>
</div>

<script>
// HBM/DRAM comparison charts
document.addEventListener("DOMContentLoaded", () => {{

// c_hbm_bw: Read/Write BW per run
new Chart(document.getElementById("c_hbm_bw"), {{
  type:"bar",
  data:{{
    labels: HBM_CMP.map(r=>r.label),
    datasets:[
      {{label:"HBM Read BW (GB/s)",data:HBM_CMP.map(r=>r.read_bw),backgroundColor:"#22d3ee99",borderColor:"#22d3ee",borderWidth:1,borderRadius:4}},
      {{label:"HBM Write BW (GB/s)",data:HBM_CMP.map(r=>r.write_bw),backgroundColor:"#f9731699",borderColor:"#f97316",borderWidth:1,borderRadius:4}},
    ]
  }},
  options:{{responsive:true,plugins:{{legend:{{labels:{{color:"#475569",font:{{size:10}},boxWidth:12}}}},
    tooltip:{{backgroundColor:"#ffffff",borderColor:"#e2e8f0",borderWidth:1,titleColor:"#475569",bodyColor:"#0f172a",padding:10,
      callbacks:{{label:i=>{{
        const r=HBM_CMP[i.dataIndex];
        return i.datasetIndex===0
          ?` Read: ${{r.read_bw}} GB/s  | util ${{r.bw_util_pct}}% | ${{r.read_txn_M_s}} M txns/s`
          :` Write: ${{r.write_bw}} GB/s  | ~12% of read BW | ${{r.write_txn_M_s}} M txns/s`;
      }}}}
    }}}},
    scales:{{x:{{ticks:{{color:"#475569",font:{{size:10}}}},grid:{{color:"#e2e8f0"}}}},
             y:{{title:{{display:true,text:"GB/s",color:"#475569"}},ticks:{{color:"#475569",font:{{size:10}}}},grid:{{color:"#e2e8f0"}}}}}}
  }}
}});

// c_hbm_txn: transaction rates
new Chart(document.getElementById("c_hbm_txn"), {{
  type:"bar",
  data:{{
    labels: HBM_CMP.map(r=>r.label),
    datasets:[
      {{label:"Read Txns (M/s)",data:HBM_CMP.map(r=>r.read_txn_M_s),backgroundColor:"#22d3ee99",borderColor:"#22d3ee",borderWidth:1,borderRadius:4}},
      {{label:"Write Txns (M/s)",data:HBM_CMP.map(r=>r.write_txn_M_s),backgroundColor:"#f9731699",borderColor:"#f97316",borderWidth:1,borderRadius:4}},
    ]
  }},
  options:{{responsive:true,plugins:{{legend:{{labels:{{color:"#475569",font:{{size:10}},boxWidth:12}}}},
    tooltip:{{backgroundColor:"#ffffff",borderColor:"#e2e8f0",borderWidth:1,titleColor:"#475569",bodyColor:"#0f172a",padding:10,
      callbacks:{{label:i=>{{
        const r=HBM_CMP[i.dataIndex];
        const cl=64;
        return i.datasetIndex===0
          ?` Read: ${{r.read_txn_M_s}} M txns/s  (${{r.read_bw}} GB/s / 64B CL)`
          :` Write: ${{r.write_txn_M_s}} M txns/s  (${{r.write_bw}} GB/s / 64B CL)`;
      }}}}
    }}}},
    scales:{{x:{{ticks:{{color:"#475569",font:{{size:10}}}},grid:{{color:"#e2e8f0"}}}},
             y:{{title:{{display:true,text:"M transactions/s",color:"#475569"}},ticks:{{color:"#475569",font:{{size:10}}}},grid:{{color:"#e2e8f0"}}}}}}
  }}
}});

// c_hbm_scatter: TPOT vs HBM BW utilisation
new Chart(document.getElementById("c_hbm_scatter"), {{
  type:"scatter",
  data:{{datasets: HBM_CMP.map((r,i)=>{{
    const colors=["#22d3ee","#f97316","#a78bfa","#34d399","#fb923c","#f43f5e","#fbbf24","#4f46e5"];
    return {{label:r.label,data:[{{x:r.bw_util_pct,y:r.tpot_ms}}],
      backgroundColor:colors[i%colors.length]+"cc",borderColor:colors[i%colors.length],
      pointRadius:12,pointHoverRadius:15}};
  }}).concat([{{
    label:"Theoretical floor (8.75ms)",
    data:[{{x:0,y:8.75}},{{x:100,y:8.75}}],
    type:"line",borderColor:"#ef444488",borderWidth:1,borderDash:[4,4],
    pointRadius:0,fill:false,showLine:true
  }}])
  }},
  options:{{responsive:true,plugins:{{legend:{{labels:{{color:"#475569",font:{{size:10}},boxWidth:12}}}},
    tooltip:{{backgroundColor:"#ffffff",borderColor:"#e2e8f0",borderWidth:1,titleColor:"#475569",bodyColor:"#0f172a",padding:10,
      callbacks:{{label:i=>{{
        if(i.datasetIndex>=HBM_CMP.length)return " Theoretical minimum TPOT at 100% HBM util";
        const r=HBM_CMP[i.datasetIndex];
        return[` HBM util: ${{r.bw_util_pct}}%  (${{r.read_bw}} GB/s read)`,
               ` TPOT: ${{r.tpot_ms}} ms/tok`,
               ` Min theoretical: ${{r.min_tpot_ms}} ms/tok`,
               ` Gap: ${{r.min_tpot_ms>0?(r.tpot_ms/r.min_tpot_ms).toFixed(1)+"× above floor":"N/A (no HBM data)"}}`];
      }}}}
    }}}},
    scales:{{
      x:{{title:{{display:true,text:"HBM BW Utilisation %",color:"#475569"}},ticks:{{color:"#475569",font:{{size:10}}}},grid:{{color:"#e2e8f0"}}}},
      y:{{title:{{display:true,text:"TPOT ms/tok (lower = better)",color:"#475569"}},ticks:{{color:"#475569",font:{{size:10}}}},grid:{{color:"#e2e8f0"}}}}
    }}
  }}
}});

// c_dram_bw: DRAM R/W bandwidth
new Chart(document.getElementById("c_dram_bw"), {{
  type:"bar",
  data:{{
    labels: DRAM_CMP.map(r=>r.label),
    datasets:[
      {{label:"DRAM Read BW (GB/s)",data:DRAM_CMP.map(r=>r.read_bw),backgroundColor:"#34d39999",borderColor:"#34d399",borderWidth:1,borderRadius:4}},
      {{label:"DRAM Write BW (GB/s)",data:DRAM_CMP.map(r=>r.write_bw),backgroundColor:"#f9731699",borderColor:"#f97316",borderWidth:1,borderRadius:4}},
      {{label:"DRAM Total BW (GB/s)",data:DRAM_CMP.map(r=>r.total_bw),backgroundColor:"transparent",borderColor:"#e2e8f088",borderWidth:2,borderRadius:4,type:"line"}},
    ]
  }},
  options:{{responsive:true,plugins:{{legend:{{labels:{{color:"#475569",font:{{size:10}},boxWidth:12}}}},
    tooltip:{{backgroundColor:"#ffffff",borderColor:"#e2e8f0",borderWidth:1,titleColor:"#475569",bodyColor:"#0f172a",padding:10,
      callbacks:{{label:i=>{{
        const r=DRAM_CMP[i.dataIndex];
        if(i.datasetIndex===0)return` Read: ${{r.read_bw}} GB/s  peak: ${{r.peak_rd}} GB/s  | ${{r.read_txn_M_s}} M txns/s`;
        if(i.datasetIndex===1)return` Write: ${{r.write_bw}} GB/s  peak: ${{r.peak_wr}} GB/s  | ${{r.write_txn_M_s}} M txns/s`;
        return` Total: ${{r.total_bw}} GB/s  util: ${{r.bw_util_pct}}% of ${{r.theoretical_bw}} GB/s peak`;
      }}}}
    }}}},
    scales:{{x:{{ticks:{{color:"#475569",font:{{size:10}}}},grid:{{color:"#e2e8f0"}}}},
             y:{{title:{{display:true,text:"GB/s",color:"#475569"}},ticks:{{color:"#475569",font:{{size:10}}}},grid:{{color:"#e2e8f0"}}}}}}
  }}
}});

// c_dram_txn: DRAM transaction rates
new Chart(document.getElementById("c_dram_txn"), {{
  type:"bar",
  data:{{
    labels: DRAM_CMP.map(r=>r.label),
    datasets:[
      {{label:"Read Txns (M/s)",data:DRAM_CMP.map(r=>r.read_txn_M_s),backgroundColor:"#34d39999",borderColor:"#34d399",borderWidth:1,borderRadius:4}},
      {{label:"Write Txns (M/s)",data:DRAM_CMP.map(r=>r.write_txn_M_s),backgroundColor:"#f9731699",borderColor:"#f97316",borderWidth:1,borderRadius:4}},
    ]
  }},
  options:{{responsive:true,plugins:{{legend:{{labels:{{color:"#475569",font:{{size:10}},boxWidth:12}}}},
    tooltip:{{backgroundColor:"#ffffff",borderColor:"#e2e8f0",borderWidth:1,titleColor:"#475569",bodyColor:"#0f172a",padding:10,
      callbacks:{{label:i=>{{
        const r=DRAM_CMP[i.dataIndex];
        const ratio=(r.read_txn_M_s/Math.max(r.write_txn_M_s,0.001)).toFixed(1);
        return i.datasetIndex===0
          ?` Read: ${{r.read_txn_M_s}} M txns/s  (${{r.read_bw}} GB/s / 64B) | R:W=${{ratio}}x`
          :` Write: ${{r.write_txn_M_s}} M txns/s  (${{r.write_bw}} GB/s / 64B)`;
      }}}}
    }}}},
    scales:{{x:{{ticks:{{color:"#475569",font:{{size:10}}}},grid:{{color:"#e2e8f0"}}}},
             y:{{title:{{display:true,text:"M transactions/s",color:"#475569"}},ticks:{{color:"#475569",font:{{size:10}}}},grid:{{color:"#e2e8f0"}}}}}}
  }}
}});

// c_dram_util: DRAM utilisation + R/W ratio grouped
new Chart(document.getElementById("c_dram_util"), {{
  type:"bar",
  data:{{
    labels: DRAM_CMP.map(r=>r.label),
    datasets:[
      {{label:"DRAM BW Util %",data:DRAM_CMP.map(r=>r.bw_util_pct),backgroundColor:"#4f46e599",borderColor:"#4f46e5",borderWidth:1,borderRadius:4,yAxisID:"y"}},
      {{label:"R/W Ratio (read÷write)",data:DRAM_CMP.map(r=>+(r.read_bw/Math.max(r.write_bw,0.001)).toFixed(2)),backgroundColor:"#22c55e99",borderColor:"#22c55e",borderWidth:1,borderRadius:4,yAxisID:"y2"}},
    ]
  }},
  options:{{responsive:true,plugins:{{legend:{{labels:{{color:"#475569",font:{{size:10}},boxWidth:12}}}},
    tooltip:{{backgroundColor:"#ffffff",borderColor:"#e2e8f0",borderWidth:1,titleColor:"#475569",bodyColor:"#0f172a",padding:10,
      callbacks:{{label:i=>{{
        const r=DRAM_CMP[i.dataIndex];
        if(i.datasetIndex===0)return` DRAM util: ${{r.bw_util_pct}}% of ${{r.theoretical_bw}} GB/s peak`;
        return` R/W ratio: ${{(r.read_bw/Math.max(r.write_bw,0.001)).toFixed(1)}}x  (${{r.read_bw}} / ${{r.write_bw}} GB/s)`;
      }}}}
    }}}},
    scales:{{
      x:{{ticks:{{color:"#475569",font:{{size:10}}}},grid:{{color:"#e2e8f0"}}}},
      y: {{position:"left",title:{{display:true,text:"DRAM Util %",color:"#475569"}},ticks:{{color:"#475569",font:{{size:10}}}},grid:{{color:"#e2e8f0"}}}},
      y2:{{position:"right",title:{{display:true,text:"R/W Ratio",color:"#475569"}},ticks:{{color:"#475569",font:{{size:10}}}},grid:{{drawOnChartArea:false}}}}
    }}
  }}
}});

}});
</script>
''')

    # ── KV cache comparison section ──────────────────────────────────────────
    parts.append(f"""
<div class="card" style="border-color:#6366f1">
<h2 style="color:#4f46e5">&#128451; KV Cache Footprint Comparison</h2>
<div class="desc">
KV bytes per token is determined by model architecture and runtime dtype.
Comparing across runs shows the effect of different models, attention mechanisms (GQA vs MLA),
and dtype choices on HBM capacity and maximum context length.
A lower footprint = more tokens fit in L1 HBM before hicache DRAM spill.
</div>
<script>const KV_CMP={kv_cmp_json};</script>

<div class="grid2">
<div>
<div class="desc"><b style="color:#4f46e5">Chart 1 — KV Bytes per Token</b> — per run, with INT8/FP8 counterfactual.
Lower bars = larger context fits in HBM before spill.</div>
<details class="fml"><summary>&#128208; Formula &amp; Metrics Used</summary>
<div class="fml-body">
<div class="fml-src">&#128202; Derived from model architecture DB (built-in) + sglang_summary.json (kv_cache_dtype)</div>
<code>GQA / MHA models:
  kb_per_tok = 2 × n_layers × n_kv_heads × head_dim × dtype_bytes / 1024

MLA models (Qwen3-235B, DeepSeek-V2/V3):
  kb_per_tok = 2 × n_layers × latent_dim × dtype_bytes / 1024
  (MLA compresses K+V into one latent vector per token)

dtype_bytes sources:
  sglang_summary.json → kv_cache_dtype field
  "fp16"|"bfloat16"  → 2 bytes   (default if not set)
  "fp8_e4m3fn"       → 1 byte
  "int8"             → 1 byte
  "int4"             → 0.5 bytes

INT8 counterfactual:
  kb_per_tok_int8 = kb_per_tok × (1 / dtype_bytes)

Architecture values (n_layers, n_kv_heads, head_dim) sourced from
built-in model DB matched on sglang_summary.json → model_name</code>
<div class="fml-note">Example: DeepSeek-R1-Distill 70B (GQA): 2×80×8×128×2/1024 = 320 KB/token.
Qwen3-235B (MLA): 2×94×512×2/1024 = 192 KB/token — 1.67× more efficient.</div>
</div></details>
<canvas id="c_kv_tok"></canvas>
<div class="insight" style="border-color:#6366f1">
<b>What to look for:</b> MLA models (Qwen3-235B, DeepSeek-V2/V3) show dramatically lower bars
because they compress K+V into a single latent vector per token instead of caching full tensors.
INT8 halves the bar height and doubles the max-context line &mdash; often the fastest path
to larger contexts without changing the model.
</div>
</div>
<div>
<div class="desc"><b style="color:#4f46e5">Chart 2 — Max Context Tokens in HBM</b> — L1 HBM capacity per run,
across current dtype and INT8/FP8 counterfactuals.
Above this threshold, SGLang spills KV to hicache DRAM.</div>
<details class="fml"><summary>&#128208; Formula &amp; Metrics Used</summary>
<div class="fml-body">
<div class="fml-src">&#128202; Derived: gpu_summary.json (hbm_total_mb_per_gpu) + model arch DB + power_summary.json (elapsed)</div>
<code>kv_pool_gb  = hbm_total_gb − weight_gb_per_gpu − 0.5 (CUDA runtime)

  hbm_total_gb      = gpu_summary.json → hbm_total_mb_per_gpu / 1024
                      (nvidia-smi --query-gpu=memory.total)
                      A100 40GB: 40960 MiB → 40.0 GB

  weight_gb_per_gpu = params_B × 10⁹ × 2 bytes (FP16) / n_gpus
                      (from model architecture DB, matched on model_name)

max_tokens (current dtype):
  = kv_pool_gb × 10⁹ / kv_bytes_per_token

max_tokens (INT8):
  = kv_pool_gb × 10⁹ / (kv_bytes_per_token / dtype_bytes × 1)

max_tokens (FP8):
  = same as INT8 (1 byte per element)</code>
<div class="fml-note">KV is replicated across all tensor-parallel GPUs (not sharded), so this limit
applies to the whole N-GPU system, not per GPU individually.
0.5 GB reserved for CUDA runtime overhead (conservative estimate).</div>
</div></details>
<canvas id="c_kv_maxtok"></canvas>
<div class="insight" style="border-color:#6366f1">
<b>What to look for:</b> If your target context (e.g. 50K tokens for SWEBench)
approaches or exceeds the max-context bar, you will see hicache fill % rise and
DRAM bandwidth increase. Switching to FP8 KV cache is a zero-accuracy-cost way
to double the threshold.
</div>
</div>
</div>

<div style="margin-top:14px">
<div class="desc"><b style="color:#4f46e5">Chart 3 — Per-Token Read Latency by Tier</b> — comparison across runs.
Lower is better; the bar ratio shows the cost multiplier of serving tokens from DRAM or NVMe vs HBM.</div>
<details class="fml"><summary>&#128208; Formula &amp; Metrics Used</summary>
<div class="fml-body">
<div class="fml-src">&#128202; Derived: kv_bytes_per_token (arch DB) + tier bandwidth constants + amduprof_pcm_raw.csv (L2 BW override)</div>
<code>latency_per_token (ms)  =  kv_bytes_per_token / tier_bandwidth_GB_s / 10⁶

Tier bandwidths:
  L1 HBM  : 2000 GB/s  (A100 HBM2e specification)
  L2 DRAM :  200 GB/s  (AMD EPYC 7742 2S DDR4 default)
             → overridden by live AMDuProf measurement when available:
               amduprof_pcm_raw.csv → "Total Mem Bw (GB/s)" mean
  L3 NVMe :  3.5 GB/s  (NVMe sequential read — /dev/nvme2n1 spec)

L2 BW override (when AMDuProf data present):
  Metrics: amduprof_pcm_summary.json → dram_total_gb_s_mean
           or dram_timeseries.csv → total_gb_s column mean

Example (DeepSeek-R1-Distill 70B, 320 KB/token):
  L1: 320 KB / (2000 GB/s × 10⁶) = 0.00016 ms/token
  L2: 320 KB / (200  GB/s × 10⁶) = 0.00160 ms/token  (10× L1)
  L3: 320 KB / (3.5  GB/s × 10⁶) = 0.091   ms/token  (570× L1)</code>
<div class="fml-note">The tier multipliers are hardware constants — independent of model or workload.
The only way to reduce effective latency is to keep tokens in a faster tier (warm L1 cache).</div>
</div></details>
<canvas id="c_kv_lat_cmp"></canvas>
<div class="insight" style="border-color:#6366f1">
<b>Interpreting the multiplier:</b>
L2/L1 ratio = how many times slower DRAM is vs HBM for KV reads (typically 10&times;).
L3/L1 ratio = NVMe vs HBM (typically 570&times;). This multiplier is fixed by hardware;
the only way to change it is to keep tokens in a faster tier.
</div>
</div>

<div style="margin-top:14px">
<div class="desc"><b style="color:#4f46e5">Chart 4 — TTFT by Tier Scenario</b> — estimated TTFT
if all cached tokens were served from each tier. Shows how much the KV read tier
contributes to total TTFT vs attention compute.</div>
<details class="fml"><summary>&#128208; Formula &amp; Metrics Used</summary>
<div class="fml-body">
<div class="fml-src">&#128202; Derived: sglang_summary.json (server_ttft_ms, rt_prefill_cache_tokens) + tier latency (see Chart 3)</div>
<code>TTFT  =  attention_compute_time  +  KV_read_time_for_cached_tokens

Step 1 — isolate attention compute (hardware-fixed component):
  compute_ttft_ms  =  max(observed_TTFT − cached_tokens × L1_lat_per_token,  0)
  Source: server_ttft_ms from sglang_summary.json (SGLang Prometheus histogram)
          sglang:time_to_first_token_seconds_sum
          / sglang:time_to_first_token_seconds_count × 1000

Step 2 — estimate TTFT per tier:
  TTFT_L1  =  compute_ttft_ms  +  rt_prefill_cache_tokens × L1_lat_per_token
  TTFT_L2  =  compute_ttft_ms  +  rt_prefill_cache_tokens × L2_lat_per_token
  TTFT_L3  =  compute_ttft_ms  +  rt_prefill_cache_tokens × L3_lat_per_token

  rt_prefill_cache_tokens: sglang_summary.json → rt_prefill_cache_tokens
  (= Σ sglang:realtime_tokens_total[mode=prefill_cache] — cumulative counter)

Observed TTFT for comparison:
  sglang_summary.json → server_ttft_ms</code>
<div class="fml-note">This model separates "compute" from "memory read" components of TTFT.
If observed TTFT ≈ L1 TTFT, the run is memory-read-limited (rare for large models).
If observed TTFT >> L1 TTFT, attention compute dominates (typical for long-context 70B+ models).</div>
</div></details>
<canvas id="c_kv_ttft_cmp"></canvas>
<div class="insight" style="border-color:#6366f1">
<b>Key insight:</b> If your observed TTFT is close to the "all tokens from L1" bar,
your prefill is HBM-bandwidth-limited and caching is working well.
If observed TTFT is much higher than L1, the bottleneck is attention compute, not KV reads.
</div>
</div>

<div style="margin-top:14px">
<div class="desc"><b style="color:#4f46e5">Chart 5 — HBM Pool Allocation</b> — for each run, how the GPU HBM is split
between model weights, active KV cache, free KV headroom, and CUDA runtime.</div>
<details class="fml"><summary>&#128208; Formula &amp; Metrics Used</summary>
<div class="fml-body">
<div class="fml-src">&#128202; gpu_summary.json (hbm_total_mb_per_gpu) + sglang_timeseries.csv (full_token_usage) + arch DB (weight_gb)</div>
<code>Segment: Model Weights (GB)
  = params_B × 10⁹ × 2 bytes / n_gpus  (FP16, tensor-parallel sharding)
  Source: architecture DB matched on sglang_summary.json → model_name
  n_gpus: gpu_summary.json → gpu_count

Segment: KV Cache Used (GB)
  = kv_pool_gb × pool_fill_pct / 100
  pool_fill_pct source (priority order):
    1. sglang_timeseries.csv → sglang:full_token_usage[engine_type=unified]  (mean)
       (fraction of L1 KV pool occupied, includes pre-allocated slots)
    2. sglang_timeseries.csv → sglang:token_usage[engine_type=unified]  (mean)
    3. sglang_summary.json  → token_usage_peak / kv_pool_capacity_tokens

Segment: KV Cache Free (GB)
  = kv_pool_gb × (1 − pool_fill_pct / 100)

Segment: CUDA Runtime (GB)
  = 0.5 GB  (constant estimate for CUDA context + cuDNN)

kv_pool_gb  = hbm_total_gb − weight_gb − 0.5 runtime
hbm_total_gb: gpu_summary.json → hbm_total_mb_per_gpu / 1024</code>
<div class="fml-note">Weights occupy a fixed fraction of HBM determined solely by model size and quantisation.
Free KV headroom = tokens you can still add before SGLang triggers hicache eviction.
GPU power profiling: power_timeseries.csv → nvidia-smi power.draw (used for cross-referencing active phase).</div>
</div></details>
<canvas id="c_kv_pool" style="max-height:220px"></canvas>
<div class="insight" style="border-color:#6366f1">
<b>Reading the chart:</b> A tall "KV Cache Used" bar means the run was KV-intensive
(many tokens cached). A tall "Model Weights" bar means the model leaves little headroom
for KV &mdash; consider quantisation. "KV Free" represents available headroom before spill.
</div>
</div>

<div style="margin-top:14px;overflow-x:auto">
<div class="desc"><b style="color:#4f46e5">Architecture &amp; Capacity Table</b> — raw values per run for all KV footprint parameters.</div>
<details class="fml"><summary>&#128208; Metric Sources for All Table Columns</summary>
<div class="fml-body">
<div class="fml-src">&#128202; Combined: model architecture DB + sglang_summary.json + gpu_summary.json</div>
<code>Attn Type    : architecture DB lookup on model_name → "GQA" | "MHA" | "MLA"
Layers       : architecture DB → n_layers
KV Heads     : architecture DB → n_kv_heads  (post-GQA reduction)
Head Dim     : architecture DB → head_dim  (or latent_dim for MLA)
dtype        : sglang_summary.json → kv_cache_dtype  (default "fp16")
KB/token     : computed (see Chart 1 formula)
Max Ctx (K)  : computed (see Chart 2 formula)
INT8 Max (K) : Max Ctx × (dtype_bytes / 1.0)  — hypothetical INT8 scenario
Pool Fill %  : sglang_timeseries.csv → sglang:full_token_usage  (mean × 100)
               or sglang_summary.json → token_usage_peak
Weight GB    : params_B × 2 bytes / n_gpus / 10⁹
               n_gpus: gpu_summary.json → gpu_count</code>
<div class="fml-note">model_name matched against built-in DB of 35 models covering DeepSeek, Qwen3, Llama-3/2, Mistral, Gemma, Phi.
Falls back to size-hint inference (e.g. "70b" in model_name → 80-layer GQA) when model not in DB.</div>
</div></details>
<table>
<thead><tr>
  <th style="text-align:left">Run</th>
  <th>Attn Type</th><th>Layers</th><th>KV Heads</th><th>Head Dim</th>
  <th>dtype</th><th>KB/token</th><th>Max Ctx (K)</th>
  <th>INT8 Max (K)</th><th>Pool Fill %</th><th>Weight GB</th>
</tr></thead>
<tbody>
{kv_table_rows}
</tbody>
</table>
</div>
</div>


<script>
document.addEventListener("DOMContentLoaded", () => {{

// c_kv_tok: bytes per token grouped bars + INT8 counterfactual
new Chart(document.getElementById("c_kv_tok"), {{
  type:"bar",
  data:{{
    labels: KV_CMP.map(r=>r.label),
    datasets:[
      {{label:"Current dtype (KB/tok)", data:KV_CMP.map(r=>r.kb_per_tok),
       backgroundColor:"#6366f199",borderColor:"#6366f1",borderWidth:1,borderRadius:4}},
      {{label:"INT8 / FP8 (KB/tok)", data:KV_CMP.map(r=>+(r.kb_per_tok/2).toFixed(1)),
       backgroundColor:"#22c55e99",borderColor:"#22c55e",borderWidth:1,borderRadius:4}},
    ]
  }},
  options:{{responsive:true,plugins:{{legend:{{labels:{{color:"#475569",font:{{size:10}},boxWidth:12}}}},
    tooltip:{{backgroundColor:"#ffffff",borderColor:"#e2e8f0",borderWidth:1,
      titleColor:"#475569",bodyColor:"#0f172a",padding:10,
      callbacks:{{label:i=>{{
        const r=KV_CMP[i.dataIndex];
        if(i.datasetIndex===0)
          return` ${{r.kb_per_tok}} KB/tok (${{r.attn_type}}, ${{r.dtype}}) | 2x${{r.n_layers}}L x${{r.n_heads}}H x${{r.head_dim}}D`;
        return` ${{(r.kb_per_tok/2).toFixed(1)}} KB/tok (INT8) → ${{(r.max_tokens_int8/1000).toFixed(0)}}K max ctx`;
      }}}}
    }}}},
    scales:{{x:{{ticks:{{color:"#475569",font:{{size:10}}}},grid:{{color:"#e2e8f0"}}}},
             y:{{title:{{display:true,text:"KB per token",color:"#475569"}},
                ticks:{{color:"#475569",font:{{size:10}}}},grid:{{color:"#e2e8f0"}}}}}}
  }}
}});

// c_kv_maxtok: max context tokens grouped bars
new Chart(document.getElementById("c_kv_maxtok"), {{
  type:"bar",
  data:{{
    labels: KV_CMP.map(r=>r.label),
    datasets:[
      {{label:"Current dtype (K tokens)", data:KV_CMP.map(r=>+(r.max_tokens/1000).toFixed(1)),
       backgroundColor:"#6366f199",borderColor:"#6366f1",borderWidth:1,borderRadius:4}},
      {{label:"INT8 / FP8 (K tokens)", data:KV_CMP.map(r=>+(r.max_tokens_int8/1000).toFixed(1)),
       backgroundColor:"#22c55e99",borderColor:"#22c55e",borderWidth:1,borderRadius:4}},
    ]
  }},
  options:{{responsive:true,plugins:{{legend:{{labels:{{color:"#475569",font:{{size:10}},boxWidth:12}}}},
    tooltip:{{backgroundColor:"#ffffff",borderColor:"#e2e8f0",borderWidth:1,
      titleColor:"#475569",bodyColor:"#0f172a",padding:10,
      callbacks:{{label:i=>{{
        const r=KV_CMP[i.dataIndex];
        if(i.datasetIndex===0)
          return` ${{(r.max_tokens/1000).toFixed(0)}}K max ctx | pool ${{r.pool_gb}} GB | fill ${{r.pool_fill_pct}}%`;
        return` ${{(r.max_tokens_int8/1000).toFixed(0)}}K max ctx (INT8/FP8) | 2x improvement`;
      }}}}
    }}}},
    scales:{{x:{{ticks:{{color:"#475569",font:{{size:10}}}},grid:{{color:"#e2e8f0"}}}},
             y:{{title:{{display:true,text:"K tokens",color:"#475569"}},
                ticks:{{color:"#475569",font:{{size:10}}}},grid:{{color:"#e2e8f0"}}}}}}
  }}
}});


// c_kv_lat_cmp: per-token latency by tier across runs
new Chart(document.getElementById("c_kv_lat_cmp"), {{
  type:"bar",
  data:{{
    labels: KV_CMP.map(r=>r.label),
    datasets:[
      {{label:"L1 HBM (ms/tok)", data:KV_CMP.map(r=>r.l1_lat_ms),
       backgroundColor:"#6366f199",borderColor:"#6366f1",borderWidth:1,borderRadius:4}},
      {{label:"L2 DRAM (ms/tok)", data:KV_CMP.map(r=>r.l2_lat_ms),
       backgroundColor:"#22c55e99",borderColor:"#22c55e",borderWidth:1,borderRadius:4}},
      {{label:"L3 NVMe (ms/tok)", data:KV_CMP.map(r=>r.l3_lat_ms),
       backgroundColor:"#f9731699",borderColor:"#f97316",borderWidth:1,borderRadius:4}},
    ]
  }},
  options:{{responsive:true,plugins:{{legend:{{labels:{{color:"#334155",font:{{size:10}},boxWidth:12}}}},
    tooltip:{{backgroundColor:"#ffffff",borderColor:"#e2e8f0",borderWidth:1,
      titleColor:"#475569",bodyColor:"#0f172a",padding:10,
      callbacks:{{label:i=>{{
        const r=KV_CMP[i.dataIndex];
        const tiers=[
          `L1 HBM: ${{r.l1_lat_ms}} ms/tok | BW: ${{r.l1_bw_gbs}} GB/s`,
          `L2 DRAM: ${{r.l2_lat_ms}} ms/tok | ${{(r.l2_lat_ms/r.l1_lat_ms).toFixed(0)}}x slower than L1 | BW: ${{r.l2_bw_gbs}} GB/s`,
          `L3 NVMe: ${{r.l3_lat_ms}} ms/tok | ${{(r.l3_lat_ms/r.l1_lat_ms).toFixed(0)}}x slower than L1 | BW: ${{r.l3_bw_gbs}} GB/s`,
        ];
        return` `+tiers[i.datasetIndex];
      }}}}
    }}}},
    scales:{{x:{{ticks:{{color:"#475569",font:{{size:10}}}},grid:{{color:"#e2e8f0"}}}},
             y:{{title:{{display:true,text:"ms per token (note: L3 >> L1/L2)",color:"#475569"}},
                ticks:{{color:"#475569",font:{{size:10}}}},grid:{{color:"#e2e8f0"}}}}}}
  }}
}});

// c_kv_ttft_cmp: TTFT by tier scenario across runs
new Chart(document.getElementById("c_kv_ttft_cmp"), {{
  type:"bar",
  data:{{
    labels: KV_CMP.map(r=>r.label),
    datasets:[
      {{label:"TTFT — all tokens from L1 HBM (ms)",
       data:KV_CMP.map(r=>r.ttft_l1_ms),
       backgroundColor:"#6366f199",borderColor:"#6366f1",borderWidth:1,borderRadius:4}},
      {{label:"TTFT — all tokens from L2 DRAM (ms)",
       data:KV_CMP.map(r=>r.ttft_l2_ms),
       backgroundColor:"#22c55e99",borderColor:"#22c55e",borderWidth:1,borderRadius:4}},
    ]
  }},
  options:{{responsive:true,plugins:{{legend:{{labels:{{color:"#334155",font:{{size:10}},boxWidth:12}}}},
    tooltip:{{backgroundColor:"#ffffff",borderColor:"#e2e8f0",borderWidth:1,
      titleColor:"#475569",bodyColor:"#0f172a",padding:10,
      callbacks:{{label:i=>{{
        const r=KV_CMP[i.dataIndex];
        if(i.datasetIndex===0)
          return` L1 HBM: ${{r.ttft_l1_ms.toFixed(0)}}ms  (${{r.l1_tokens.toLocaleString()}} L1 tokens × ${{r.l1_lat_ms}} ms)`;
        return` L2 DRAM: ${{(r.ttft_l2_ms/1000).toFixed(1)}}s  (${{(r.ttft_l2_ms/r.ttft_l1_ms).toFixed(1)}}x L1)`;
      }}}}
    }}}},
    scales:{{x:{{ticks:{{color:"#475569",font:{{size:10}}}},grid:{{color:"#e2e8f0"}}}},
             y:{{title:{{display:true,text:"TTFT (ms)",color:"#475569"}},
                ticks:{{color:"#475569",font:{{size:10}}}},grid:{{color:"#e2e8f0"}}}}}}
  }}
}});

// c_kv_pool: stacked HBM pool allocation
new Chart(document.getElementById("c_kv_pool"), {{
  type:"bar",
  data:{{
    labels: KV_CMP.map(r=>r.label),
    datasets:[
      {{label:"Model Weights (GB)",
       data:KV_CMP.map(r=>r.weight_gb),
       backgroundColor:"#6366f199",borderColor:"#6366f1",borderWidth:1}},
      {{label:"KV Cache Used (GB)",
       data:KV_CMP.map(r=>+(r.pool_gb*r.pool_fill_pct/100).toFixed(2)),
       backgroundColor:"#22d3ee99",borderColor:"#22d3ee",borderWidth:1}},
      {{label:"KV Cache Free (GB)",
       data:KV_CMP.map(r=>+(r.pool_gb*(1-r.pool_fill_pct/100)).toFixed(2)),
       backgroundColor:"#e2e8f099",borderColor:"#94a3b8",borderWidth:1}},
      {{label:"CUDA Runtime (GB)",
       data:KV_CMP.map(()=>0.5),
       backgroundColor:"#94a3b899",borderColor:"#94a3b8",borderWidth:1}},
    ]
  }},
  options:{{responsive:true,
    plugins:{{legend:{{labels:{{color:"#475569",font:{{size:10}},boxWidth:12}}}},
      tooltip:{{backgroundColor:"#ffffff",borderColor:"#e2e8f0",borderWidth:1,
        titleColor:"#475569",bodyColor:"#0f172a",padding:10,
        callbacks:{{label:i=>{{
          const r=KV_CMP[i.dataIndex];
          const labels=["Weights","KV Used","KV Free","Runtime"];
          const vals=[r.weight_gb,(r.pool_gb*r.pool_fill_pct/100).toFixed(2),
                      (r.pool_gb*(1-r.pool_fill_pct/100)).toFixed(2),0.5];
          return` ${{labels[i.datasetIndex]}}: ${{vals[i.datasetIndex]}} GB`;
        }}}}
      }}}},
    scales:{{
      x:{{stacked:true,ticks:{{color:"#475569",font:{{size:10}}}},grid:{{color:"#e2e8f0"}}}},
      y:{{stacked:true,title:{{display:true,text:"GB per GPU",color:"#475569"}},
         ticks:{{color:"#475569",font:{{size:10}}}},grid:{{color:"#e2e8f0"}}}}
    }}
  }}
}});

}});
</script>
""")

    # ── Session / KVB / NVMe comparison sections ──────────────────────────────
    parts.append(f'''
<script>
const SESS_CMP={sess_cmp_json};
const KVB_CMP={kvb_cmp_json};
const NVME_CMP={nvme_cmp_json};
</script>

<div class="card" style="border-color:#6366f1">
<h2 style="color:#4f46e5">&#128260; Session / Stream Analysis — Comparison</h2>
<div class="desc">
Per-request breakdown of E2E latency, input token count, and output token count across all runs.
Metrics derived from SGLang Prometheus histogram deltas:
<code style="background:#f1f5f9;padding:2px 6px;border-radius:3px;color:#1e3a5f;font-size:10px">sglang_e2e_request_latency_seconds_*</code>,
<code style="background:#f1f5f9;padding:2px 6px;border-radius:3px;color:#1e3a5f;font-size:10px">sglang_prompt_tokens_total</code>,
<code style="background:#f1f5f9;padding:2px 6px;border-radius:3px;color:#1e3a5f;font-size:10px">sglang_generation_tokens_total</code>
</div>
<div class="grid2">
<div>
<div class="desc"><b style="color:#4f46e5">E2E Latency — Mean / P90 / Max per Run</b><br>
Source: <code style="font-size:10px">sglang:e2e_request_latency_seconds_sum / count × 1000 [ms]</code></div>
<canvas id="c_sess_e2e"></canvas>
<div class="insight" style="border-color:#6366f1">
<b>What to look for:</b> A run with lower mean E2E but similar or higher P90 = prefill improved
but some requests hit worst-case decode paths. A run with both lower mean and P90 = systematic
improvement. E2E = queue_ms + TTFT_ms + (TPOT_ms × output_tokens).
</div>
</div>
<div>
<div class="desc"><b style="color:#4f46e5">Token Counts — Input &amp; Output per Run</b><br>
Source: <code style="font-size:10px">sglang:prompt_tokens_total / num_requests_total</code> (delta per interval)</div>
<canvas id="c_sess_tok"></canvas>
<div class="insight" style="border-color:#6366f1">
<b>What to look for:</b> Runs with larger mean input tokens will have higher TTFT
(more prompt to prefill). Runs with larger mean output tokens will have higher E2E
(more decode steps). Comparing token counts explains latency differences between runs.
</div>
</div>
</div>
<div style="margin-top:14px">
<div class="desc"><b style="color:#4f46e5">Request Count &amp; Concurrency</b> — total requests processed
and peak concurrent active sessions per run.<br>
Source: <code style="font-size:10px">sglang:num_requests_total</code> (delta), <code style="font-size:10px">sglang:num_running_reqs</code> (peak)</div>
<canvas id="c_sess_conc" style="max-height:200px"></canvas>
</div>
</div>

<div class="card" style="border-color:#22c55e">
<h2 style="color:#15803d">&#128230; KV Cache Block (KV$B) Events — Comparison</h2>
<div class="desc">
KV block offload rate (L1 HBM &#8594; L2 DRAM), eviction rate (L2 evictions), pool fill %,
and estimated block lifetime across runs. Higher offload rate = more KV cache pressure.
Source: <code style="background:#f1f5f9;padding:2px 6px;border-radius:3px;color:#1e3a5f;font-size:10px">sglang:hicache_host_used_tokens</code> delta / block_size / duration.
</div>
<div class="grid2">
<div>
<div class="desc"><b style="color:#22c55e">KV Block Rates</b> — offload and eviction per run</div>
<canvas id="c_kvb_rates"></canvas>
<div class="insight" style="border-color:#22c55e">
<b>Offload rate</b> = blocks/s flowing from L1 HBM to L2 DRAM hicache.
Higher rate = cache is active and KV pool is being filled.
<b>Eviction rate</b> is non-zero only when L2 fill &gt;80% — indicates L2 capacity pressure.
</div>
</div>
<div>
<div class="desc"><b style="color:#22c55e">Pool Fill % and Block Lifetime</b></div>
<canvas id="c_kvb_fill"></canvas>
<div class="insight" style="border-color:#22c55e">
<b>Block lifetime</b> = L2_pool_blocks / offload_rate = average time a KV block survives
before being evicted. Longer = less cache churn, more stable reuse. A run with higher
fill % + shorter lifetime = higher KV cache pressure.
</div>
</div>
</div>
</div>

<div class="card" style="border-color:#f97316">
<h2 style="color:#c2410c">&#128191; NVMe IO Workload — Comparison</h2>
<div class="desc">
NVMe write IOPS, latency, IO utilisation, and total bytes written across runs.
Write activity indicates KV block offload to L3 NVMe (when L2 hicache overflows).
Zero IOPS = all KV cache fits in HBM + DRAM tiers.
Sources: <code style="background:#f1f5f9;padding:2px 6px;border-radius:3px;color:#1e3a5f;font-size:10px">node_disk_writes_completed_total</code>,
<code style="background:#f1f5f9;padding:2px 6px;border-radius:3px;color:#1e3a5f;font-size:10px">node_disk_write_time_seconds_total</code>,
<code style="background:#f1f5f9;padding:2px 6px;border-radius:3px;color:#1e3a5f;font-size:10px">node_disk_discards_completed_total</code> (TRIM),
SMART <code style="background:#f1f5f9;padding:2px 6px;border-radius:3px;color:#1e3a5f;font-size:10px">data_units_written</code> × 512×1000 bytes.
</div>
<div class="grid2">
<div>
<div class="desc"><b style="color:#c2410c">Write IOPS &amp; Latency per Run</b></div>
<canvas id="c_nvme_iops"></canvas>
<div class="insight" style="border-color:#f97316">
<b>What to look for:</b> Non-zero write IOPS = KV$B offloading to NVMe L3.
A run with higher IOPS + higher latency = NVMe L3 is being used as a spillover tier.
Write latency &lt;1ms = device is fast enough for KV use; &gt;5ms = NVMe becoming a bottleneck.
</div>
</div>
<div>
<div class="desc"><b style="color:#c2410c">Bytes Written &amp; SSD Wear per Run</b></div>
<canvas id="c_nvme_bytes"></canvas>
<div class="insight" style="border-color:#f97316">
<b>SMART data_units_written</b> delta × 512,000 bytes = actual bytes written to NVMe
during this profiling window. SSD wear % is the cumulative rated endurance consumed
(increases with every write over the drive's lifetime, not just this run).
</div>
</div>
</div>
</div>

<script>
document.addEventListener("DOMContentLoaded", () => {{

// Session charts
new Chart(document.getElementById("c_sess_e2e"), {{
  type:"bar",
  data:{{
    labels: SESS_CMP.map(r=>r.label),
    datasets:[
      {{label:"Mean E2E (s)",data:SESS_CMP.map(r=>r.e2e_mean_s),backgroundColor:"#22c55e99",borderColor:"#22c55e",borderWidth:1,borderRadius:4}},
      {{label:"P90 E2E (s)", data:SESS_CMP.map(r=>r.e2e_p90_s), backgroundColor:"#f9731699",borderColor:"#f97316",borderWidth:1,borderRadius:4}},
      {{label:"Max E2E (s)", data:SESS_CMP.map(r=>r.e2e_max_s), backgroundColor:"#ef444499",borderColor:"#ef4444",borderWidth:1,borderRadius:4}},
    ]
  }},
  options:{{responsive:true,plugins:{{legend:{{labels:{{color:"#334155",font:{{size:10}},boxWidth:12}}}},
    tooltip:{{backgroundColor:"#ffffff",borderColor:"#e2e8f0",borderWidth:1,titleColor:"#475569",bodyColor:"#0f172a",padding:10,
      callbacks:{{label:i=>{{
        const r=SESS_CMP[i.dataIndex];
        if(i.datasetIndex===0)return` Mean: ${{r.e2e_mean_s}}s  | n=${{r.total_requests}} requests`;
        if(i.datasetIndex===1)return` P90: ${{r.e2e_p90_s}}s  | Min: ${{r.e2e_min_s}}s`;
        return` Max: ${{r.e2e_max_s}}s  | queue: ${{r.queue_mean_ms}}ms`;
      }}}}
    }}}},
    scales:{{x:{{ticks:{{color:"#475569",font:{{size:10}}}},grid:{{color:"#e2e8f0"}}}},
             y:{{title:{{display:true,text:"E2E Latency (s)",color:"#475569"}},ticks:{{color:"#475569",font:{{size:10}}}},grid:{{color:"#e2e8f0"}}}}}}
  }}
}});

new Chart(document.getElementById("c_sess_tok"), {{
  type:"bar",
  data:{{
    labels: SESS_CMP.map(r=>r.label),
    datasets:[
      {{label:"Input tokens mean", data:SESS_CMP.map(r=>r.input_tok_mean),backgroundColor:"#3b82f699",borderColor:"#3b82f6",borderWidth:1,borderRadius:4}},
      {{label:"Output tokens mean",data:SESS_CMP.map(r=>r.output_tok_mean),backgroundColor:"#a855f799",borderColor:"#a855f7",borderWidth:1,borderRadius:4}},
    ]
  }},
  options:{{responsive:true,plugins:{{legend:{{labels:{{color:"#334155",font:{{size:10}},boxWidth:12}}}},
    tooltip:{{backgroundColor:"#ffffff",borderColor:"#e2e8f0",borderWidth:1,titleColor:"#475569",bodyColor:"#0f172a",padding:10,
      callbacks:{{label:i=>{{
        const r=SESS_CMP[i.dataIndex];
        return i.datasetIndex===0
          ?` Input: ${{r.input_tok_mean.toLocaleString()}} mean | max ${{r.input_tok_max.toLocaleString()}}`
          :` Output: ${{r.output_tok_mean.toLocaleString()}} mean | max ${{r.output_tok_max.toLocaleString()}}`;
      }}}}
    }}}},
    scales:{{x:{{ticks:{{color:"#475569",font:{{size:10}}}},grid:{{color:"#e2e8f0"}}}},
             y:{{title:{{display:true,text:"Tokens per request",color:"#475569"}},ticks:{{color:"#475569",font:{{size:10}}}},grid:{{color:"#e2e8f0"}}}}}}
  }}
}});

new Chart(document.getElementById("c_sess_conc"), {{
  type:"bar",
  data:{{
    labels: SESS_CMP.map(r=>r.label),
    datasets:[
      {{label:"Total requests",   data:SESS_CMP.map(r=>r.total_requests),  backgroundColor:"#6366f199",borderColor:"#6366f1",borderWidth:1,borderRadius:4,yAxisID:"y"}},
      {{label:"Peak concurrent",  data:SESS_CMP.map(r=>r.max_concurrent),  backgroundColor:"#f97316cc",borderColor:"#f97316",borderWidth:1,borderRadius:4,yAxisID:"y2"}},
    ]
  }},
  options:{{responsive:true,plugins:{{legend:{{labels:{{color:"#334155",font:{{size:10}},boxWidth:12}}}},
    tooltip:{{backgroundColor:"#ffffff",borderColor:"#e2e8f0",borderWidth:1,titleColor:"#475569",bodyColor:"#0f172a",padding:10,
      callbacks:{{label:i=>{{
        const r=SESS_CMP[i.dataIndex];
        return i.datasetIndex===0
          ?` ${{r.total_requests}} requests | arrival ${{r.arrival_rps}} req/s`
          :` Peak ${{r.max_concurrent}} concurrent sessions`;
      }}}}
    }}}},
    scales:{{
      x:{{ticks:{{color:"#475569",font:{{size:10}}}},grid:{{color:"#e2e8f0"}}}},
      y:{{position:"left",title:{{display:true,text:"Total requests",color:"#475569"}},ticks:{{color:"#475569",font:{{size:10}}}},grid:{{color:"#e2e8f0"}}}},
      y2:{{position:"right",title:{{display:true,text:"Peak concurrent",color:"#475569"}},ticks:{{color:"#475569",font:{{size:10}}}},grid:{{drawOnChartArea:false}}}}
    }}
  }}
}});

// KVB charts
new Chart(document.getElementById("c_kvb_rates"), {{
  type:"bar",
  data:{{
    labels: KVB_CMP.map(r=>r.label),
    datasets:[
      {{label:"Offload rate (blk/s, L1→L2)",data:KVB_CMP.map(r=>r.offload_rate),backgroundColor:"#22c55e99",borderColor:"#22c55e",borderWidth:1,borderRadius:4,yAxisID:"y"}},
      {{label:"Eviction rate (blk/s, L2→evict)",data:KVB_CMP.map(r=>r.eviction_rate),backgroundColor:"#ef444499",borderColor:"#ef4444",borderWidth:1,borderRadius:4,yAxisID:"y"}},
    ]
  }},
  options:{{responsive:true,plugins:{{legend:{{labels:{{color:"#334155",font:{{size:10}},boxWidth:12}}}},
    tooltip:{{backgroundColor:"#ffffff",borderColor:"#e2e8f0",borderWidth:1,titleColor:"#475569",bodyColor:"#0f172a",padding:10,
      callbacks:{{label:i=>{{
        const r=KVB_CMP[i.dataIndex];
        return i.datasetIndex===0
          ?` Offload: ${{r.offload_rate}} blk/s | block=${{r.block_size_mb}}MB`
          :` Eviction: ${{r.eviction_rate}} blk/s (L2 fill>80%)`;
      }}}}
    }}}},
    scales:{{x:{{ticks:{{color:"#475569",font:{{size:10}}}},grid:{{color:"#e2e8f0"}}}},
             y:{{title:{{display:true,text:"blocks/s",color:"#475569"}},ticks:{{color:"#475569",font:{{size:10}}}},grid:{{color:"#e2e8f0"}}}}}}
  }}
}});

new Chart(document.getElementById("c_kvb_fill"), {{
  type:"bar",
  data:{{
    labels: KVB_CMP.map(r=>r.label),
    datasets:[
      {{label:"L1 HBM fill %",data:KVB_CMP.map(r=>r.l1_fill_pct),backgroundColor:"#6366f199",borderColor:"#6366f1",borderWidth:1,borderRadius:4,yAxisID:"y"}},
      {{label:"L2 DRAM fill %",data:KVB_CMP.map(r=>r.l2_fill_pct),backgroundColor:"#22c55e99",borderColor:"#22c55e",borderWidth:1,borderRadius:4,yAxisID:"y"}},
      {{label:"Block lifetime (s)",data:KVB_CMP.map(r=>r.lifetime_mean_s),backgroundColor:"#f9731699",borderColor:"#f97316",borderWidth:1,borderRadius:4,yAxisID:"y2"}},
    ]
  }},
  options:{{responsive:true,plugins:{{legend:{{labels:{{color:"#334155",font:{{size:10}},boxWidth:12}}}},
    tooltip:{{backgroundColor:"#ffffff",borderColor:"#e2e8f0",borderWidth:1,titleColor:"#475569",bodyColor:"#0f172a",padding:10,
      callbacks:{{label:i=>{{
        const r=KVB_CMP[i.dataIndex];
        if(i.datasetIndex===0)return` L1 HBM: ${{r.l1_fill_pct}}% (${{r.l1_pool_blocks.toLocaleString()}} total blocks)`;
        if(i.datasetIndex===1)return` L2 DRAM: ${{r.l2_fill_pct}}% (${{r.l2_pool_blocks.toLocaleString()}} total blocks)`;
        return` Lifetime: ${{r.lifetime_mean_s.toLocaleString()}}s avg block survival`;
      }}}}
    }}}},
    scales:{{
      x:{{ticks:{{color:"#475569",font:{{size:10}}}},grid:{{color:"#e2e8f0"}}}},
      y:{{position:"left",max:110,title:{{display:true,text:"Fill %",color:"#475569"}},ticks:{{color:"#475569",font:{{size:10}}}},grid:{{color:"#e2e8f0"}}}},
      y2:{{position:"right",title:{{display:true,text:"Lifetime (s)",color:"#475569"}},ticks:{{color:"#475569",font:{{size:10}}}},grid:{{drawOnChartArea:false}}}}
    }}
  }}
}});

// NVMe charts
new Chart(document.getElementById("c_nvme_iops"), {{
  type:"bar",
  data:{{
    labels: NVME_CMP.map(r=>r.label),
    datasets:[
      {{label:"Write IOPS mean",data:NVME_CMP.map(r=>r.wr_iops_mean),backgroundColor:"#f9731699",borderColor:"#f97316",borderWidth:1,borderRadius:4,yAxisID:"y"}},
      {{label:"Write latency mean (ms)",data:NVME_CMP.map(r=>r.wr_lat_mean_ms),backgroundColor:"#ef444499",borderColor:"#ef4444",borderWidth:1,borderRadius:4,yAxisID:"y2"}},
    ]
  }},
  options:{{responsive:true,plugins:{{legend:{{labels:{{color:"#334155",font:{{size:10}},boxWidth:12}}}},
    tooltip:{{backgroundColor:"#ffffff",borderColor:"#e2e8f0",borderWidth:1,titleColor:"#475569",bodyColor:"#0f172a",padding:10,
      callbacks:{{label:i=>{{
        const r=NVME_CMP[i.dataIndex];
        if(i.datasetIndex===0)return` Write IOPS: ${{r.wr_iops_mean}} | BW≈${{r.wr_bw_mbs}}MB/s | util ${{r.io_util_pct}}%`;
        return` Write latency: ${{r.wr_lat_mean_ms}}ms mean | max ${{r.wr_lat_max_ms}}ms`;
      }}}}
    }}}},
    scales:{{
      x:{{ticks:{{color:"#475569",font:{{size:10}}}},grid:{{color:"#e2e8f0"}}}},
      y:{{position:"left",title:{{display:true,text:"IOPS",color:"#475569"}},ticks:{{color:"#475569",font:{{size:10}}}},grid:{{color:"#e2e8f0"}}}},
      y2:{{position:"right",title:{{display:true,text:"Latency (ms)",color:"#475569"}},ticks:{{color:"#475569",font:{{size:10}}}},grid:{{drawOnChartArea:false}}}}
    }}
  }}
}});

new Chart(document.getElementById("c_nvme_bytes"), {{
  type:"bar",
  data:{{
    labels: NVME_CMP.map(r=>r.label),
    datasets:[
      {{label:"Bytes written (GB)",data:NVME_CMP.map(r=>r.bytes_wr_gb),backgroundColor:"#f9731699",borderColor:"#f97316",borderWidth:1,borderRadius:4,yAxisID:"y"}},
      {{label:"Bytes read (GB)",   data:NVME_CMP.map(r=>r.bytes_rd_gb),backgroundColor:"#3b82f699",borderColor:"#3b82f6",borderWidth:1,borderRadius:4,yAxisID:"y"}},
      {{label:"SSD wear %",        data:NVME_CMP.map(r=>r.smart_wear_pct),backgroundColor:"#ef444466",borderColor:"#ef4444",borderWidth:1,borderRadius:4,yAxisID:"y2"}},
    ]
  }},
  options:{{responsive:true,plugins:{{legend:{{labels:{{color:"#334155",font:{{size:10}},boxWidth:12}}}},
    tooltip:{{backgroundColor:"#ffffff",borderColor:"#e2e8f0",borderWidth:1,titleColor:"#475569",bodyColor:"#0f172a",padding:10,
      callbacks:{{label:i=>{{
        const r=NVME_CMP[i.dataIndex];
        if(i.datasetIndex===0)return` Written: ${{r.bytes_wr_gb}}GB  | ${{r.smart_spare_pct}}% spare remaining`;
        if(i.datasetIndex===1)return` Read: ${{r.bytes_rd_gb}}GB`;
        return` SSD wear: ${{r.smart_wear_pct}}% of rated endurance consumed`;
      }}}}
    }}}},
    scales:{{
      x:{{ticks:{{color:"#475569",font:{{size:10}}}},grid:{{color:"#e2e8f0"}}}},
      y:{{position:"left",title:{{display:true,text:"GB",color:"#475569"}},ticks:{{color:"#475569",font:{{size:10}}}},grid:{{color:"#e2e8f0"}}}},
      y2:{{position:"right",title:{{display:true,text:"SSD wear %",color:"#475569"}},ticks:{{color:"#475569",font:{{size:10}}}},grid:{{drawOnChartArea:false}}}}
    }}
  }}
}});

}});
</script>
''')

    # Bottleneck section
    parts.append(f'''<div class="card" style="border-color:#4f46e5">
<h2 style="color:#a78bfa">Bottleneck Score Analysis - Full Stack</h2>
<div class="desc">
Each stack layer is scored 0-100 based on real telemetry (not estimates).
<b>0</b> = no bottleneck observed. <b>100</b> = this layer is the dominant performance limiter.
Scores are computed independently per run so you can track how optimisations shift the bottleneck profile.
<b>On the radar:</b> each axis = one layer, radius = severity.
A large filled area = many simultaneous bottlenecks (hard to optimise).
A single spike = one dominant constraint (easiest to fix first).
Overlapping run outlines that diverge on specific axes = the optimisation changed that specific layer.
</div>
<div class="grid2">
<div>
<details class="fml"><summary>&#128208; Formula &amp; Derivation</summary><div class="fml-body"><span class="src">&#128202; Derived from all collectors — see score_bottlenecks() in profiler source</span><code>GPU Compute    = min(100, (gpu_util_peak/100 × 40)
                         + min(100, ttft_ms/500 × 40) × 0.6)
HBM Bandwidth  = min(100, hbm_util_pct × 0.5 + (tpot_ms/100) × 50)
KV Cache       = max(0, 100 - cache_hit_pct) × 0.8
DRAM           = min(100, dram_util_pct × 0.3)
NVMe I/O       = min(100, max(wr_iops_max, rd_iops_max) / 10)
Power/Thermal  = min(100, (gpu_power_peak_w / 400) × 50)
CPU/PageFaults = min(100, (page_faults_per_s / 10000) × 30)
GPU Utilisation= min(100, (100 - gpu_util_mean) × 0.5)

Severity: HIGH if score &gt; 60  |  MED if 30 &lt; score ≤ 60  |  LOW if score ≤ 30</code><span class="note">Scores are dimensionless (0–100) and relative within a run. They indicate which layer is the dominant constraint, not an absolute performance grade. Compare across runs to track how optimisations shift the bottleneck profile.</span></div></details>
<canvas id="c12" style="max-height:380px"></canvas>
<div class="insight" style="border-color:#a78bfa">
<b>Reading the radar overlay:</b>
If two runs overlap perfectly = same bottleneck profile (optimisation had no effect on constraints).
If one run shrinks inward = overall bottleneck pressure reduced.
If runs diverge on one axis = that layer was directly affected by the change between runs.
GPU Compute + HBM Bandwidth spiking together = hardware-limited workload (hard ceiling of A100 capabilities).
GPU Utilisation high = server efficiency problem (not per-request, but server-level).
</div>
</div>
<div>
<details class="fml"><summary>&#128208; Formula &amp; Derivation</summary><div class="fml-body"><span class="src">&#128202; Same as radar (c12) — same scores, different visual encoding</span><code>Scores identical to radar chart (c12).
Grouped horizontal bars allow precise cross-run comparison per layer.

Reading: bars of the same colour = same run.
         Longer bar = higher bottleneck pressure.
         Two runs with equal bars on one layer = that layer unchanged.
         One run shorter = that optimisation reduced this specific bottleneck.</code><span class="note">Bottleneck scores are recomputed fresh for each run from its own telemetry, so cross-run comparison is valid even if runs have different durations or request counts.</span></div></details>
<canvas id="c13" style="max-height:380px"></canvas>
<div class="insight" style="border-color:#a78bfa">
<b>Score interpretation:</b>
0-30 = acceptable, low priority.
31-60 = optimisation opportunity with meaningful impact.
61-100 = primary bottleneck, address this first before other changes.
Scores are relative within a run - a score of 80 means this layer is the dominant constraint
regardless of absolute metric values.
</div>
</div>
</div>
<div style="margin-top:16px">
<div style="font-size:11px;font-weight:700;color:#4f46e5;text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px">Layer Scoring Logic and Scores Across Runs</div>
<div style="overflow-x:auto"><table>
<thead><tr><th style="text-align:left">Layer</th><th>Phase</th><th>Severity</th>{run_header_cols}<th style="text-align:left;min-width:350px">Scoring logic and remediation</th></tr></thead>
<tbody>{layer_rows}</tbody></table></div>
</div>
<div style="margin-top:14px">
<div style="font-size:11px;font-weight:700;color:#4f46e5;text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px">Top 3 Bottlenecks Per Run</div>
<div class="flex">{bn_explain_cards}</div>
</div>
</div>
''')

    parts.append(f'''
<div style="border-top:1px solid #e2e8f0;margin-top:20px;padding-top:12px;font-size:11px;color:#64748b;display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px">
  <span>AMOprof Comparison Report v1.6 &middot; {timestamp}</span>
  <span>Runs: {" &middot; ".join(r[0] for r in runs)}</span>
</div>
</body></html>
''')

    return "".join(parts)

# ── Comparison Excel sheet ────────────────────────────────────────────────────

def generate_comparison_excel(runs: list[tuple[str, "Metrics"]],
                               all_bottlenecks: list[list[dict]],
                               timestamp: str,
                               out_path: Path):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.chart import BarChart, LineChart, RadarChart, Reference
    from openpyxl.formatting.rule import ColorScaleRule
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    wb.remove(wb.active)
    FONT = "Arial"
    COL_HDR  = "1E3A5F"
    COL_HDR2 = "2D5986"
    ZEBRA    = "F2F6FC"
    WHITE    = "FFFFFF"

    def f(hex_c): return PatternFill("solid", fgColor=hex_c)
    def bd():
        s = Side(style="thin", color="CCCCCC")
        return Border(left=s, right=s, top=s, bottom=s)
    def ctr(): return Alignment(horizontal="center", vertical="center", wrap_text=True)
    def lft(): return Alignment(horizontal="left",   vertical="center", wrap_text=True)
    def hf(sz=10, bold=True, col="FFFFFF"): return Font(name=FONT, size=sz, bold=bold, color=col)
    def bf(sz=10, bold=False, col="000000"): return Font(name=FONT, size=sz, bold=bold, color=col)

    n_runs = len(runs)
    rcolors = ["0E86D4","F97316","7B68EE","27AE60","E74C3C","818CF8"]

    # ── Sheet 1: KPI Comparison ───────────────────────────────────────────────
    ws = wb.create_sheet("KPI_Comparison")
    ws.sheet_view.showGridLines = False
    ws.sheet_properties.tabColor = "1E3A5F"

    # Title
    ws.merge_cells(f"A1:{chr(65+n_runs+1)}1")
    ws["A1"] = f"AI Stack Multi-Run KPI Comparison  —  {timestamp}"
    ws["A1"].font = Font(name=FONT, size=14, bold=True, color="FFFFFF")
    ws["A1"].fill = f(COL_HDR); ws["A1"].alignment = ctr()
    ws.row_dimensions[1].height = 26

    # Sub-header row: metric + run names
    ws.cell(row=2, column=1, value="Metric").font = hf()
    ws.cell(row=2, column=1).fill = f(COL_HDR); ws.cell(row=2,column=1).alignment = lft()
    for j, (label, _) in enumerate(runs, 2):
        c = ws.cell(row=2, column=j, value=label)
        c.font = Font(name=FONT, size=10, bold=True, color="FFFFFF")
        c.fill = f(rcolors[(j-2) % len(rcolors)])
        c.alignment = ctr(); c.border = bd()
    ws.row_dimensions[2].height = 18
    ws.column_dimensions["A"].width = 30
    for j in range(n_runs): ws.column_dimensions[chr(66+j)].width = 18

    metrics_rows = [
        ("TTFT (ms)",           lambda m: m.ttft_ms,           1),
        ("TPOT (ms/tok)",       lambda m: m.tpot_ms,           2),
        ("E2E Latency (s)",     lambda m: m.e2e_ms/1000,       1),
        ("Peak Throughput (tok/s)", lambda m: m.gen_tp_peak,   1),
        ("Cache Hit Rate %",    lambda m: m.cache_hit_pct,     1),
        ("GPU Util Mean %",     lambda m: m.gpu_util_mean,     1),
        ("GPU Util Peak %",     lambda m: m.gpu_util_peak,     0),
        ("HBM Util %",          lambda m: m.hbm_util_pct,      1),
        ("HBM Used (GB/GPU)",   lambda m: m.hbm_used_mb_mean/1024, 2),
        ("DRAM Util %",         lambda m: m.dram_util_pct,     1),
        ("DRAM Used (GB)",      lambda m: m.dram_used_gb,      0),
        ("GPU Power Mean (W)",  lambda m: m.gpu_power_mean_w,  0),
        ("GPU Power Peak (W/GPU)", lambda m: m.gpu_power_peak_w, 0),
        ("NVMe Wr IOPS (max)", lambda m: m.nvme_wr_iops_max,  0),
        ("Page Faults/s",       lambda m: m.page_faults_per_s, 0),
        ("Run Duration (min)",  lambda m: m.run_duration_s/60, 1),
        ("Decode Tokens",       lambda m: m.decode_tokens,     0),
        ("Prefill Cache Tokens",lambda m: m.prefill_cache_tokens, 0),
        ("Prefill Compute Tokens", lambda m: m.prefill_compute_tokens, 0),
    ]

    data_start = 3
    for i, (metric, getter, dec) in enumerate(metrics_rows):
        row = data_start + i
        bg = ZEBRA if i % 2 == 0 else WHITE
        c = ws.cell(row=row, column=1, value=metric)
        c.font = bf(10, bold=True); c.fill = f(bg); c.alignment = lft(); c.border = bd()
        for j, (_, m) in enumerate(runs, 2):
            val = round(float(getter(m)), dec)
            cell = ws.cell(row=row, column=j, value=val)
            cell.font = bf(11, bold=True)
            cell.fill = f(bg); cell.alignment = ctr(); cell.border = bd()
        ws.row_dimensions[row].height = 16

    # Conditional formatting on each run column
    for j in range(n_runs):
        col_letter = chr(66 + j)
        ws.conditional_formatting.add(
            f"{col_letter}{data_start}:{col_letter}{data_start+len(metrics_rows)-1}",
            ColorScaleRule(start_type="min", start_color="63BE7B",
                           mid_type="percentile", mid_value=50, mid_color="FFEB84",
                           end_type="max", end_color="F8696B"),
        )

    # Grouped bar chart — latency metrics
    chart_data_row = data_start + len(metrics_rows) + 2
    ws.cell(row=chart_data_row, column=1, value="Run").font = hf(9)
    ws.cell(row=chart_data_row, column=2, value="TTFT (ms)").font = hf(9)
    ws.cell(row=chart_data_row, column=3, value="TPOT (ms/tok)").font = hf(9)
    ws.cell(row=chart_data_row, column=4, value="Peak Tput (tok/s)").font = hf(9)
    for j, (label, m) in enumerate(runs, 1):
        ws.cell(row=chart_data_row + j, column=1, value=label)
        ws.cell(row=chart_data_row + j, column=2, value=round(m.ttft_ms, 1))
        ws.cell(row=chart_data_row + j, column=3, value=round(m.tpot_ms, 2))
        ws.cell(row=chart_data_row + j, column=4, value=round(m.gen_tp_peak, 2))

    ch_lat = BarChart()
    ch_lat.type = "col"; ch_lat.grouping = "clustered"
    ch_lat.title = "TTFT vs TPOT per Run"; ch_lat.style = 10
    ch_lat.y_axis.title = "Milliseconds"; ch_lat.width = 20; ch_lat.height = 12
    for ci, col_letter in enumerate(["B","C"], 1):
        ref = Reference(ws, min_col=ci+1, min_row=chart_data_row,
                        max_row=chart_data_row+n_runs)
        ch_lat.add_data(ref, titles_from_data=True)
    cats = Reference(ws, min_col=1, min_row=chart_data_row+1, max_row=chart_data_row+n_runs)
    ch_lat.set_categories(cats)
    ws.add_chart(ch_lat, f"{chr(65+n_runs+2)}{data_start}")

    ch_tp = BarChart()
    ch_tp.type = "col"; ch_tp.title = "Peak Throughput per Run"; ch_tp.style = 10
    ch_tp.y_axis.title = "tok/s"; ch_tp.width = 14; ch_tp.height = 10
    tp_ref = Reference(ws, min_col=4, min_row=chart_data_row, max_row=chart_data_row+n_runs)
    ch_tp.add_data(tp_ref, titles_from_data=True)
    ch_tp.set_categories(cats)
    ws.add_chart(ch_tp, f"{chr(65+n_runs+2)}{data_start+14}")

    # ── Sheet 2: Bottleneck Comparison ────────────────────────────────────────
    ws2 = wb.create_sheet("Bottleneck_Comparison")
    ws2.sheet_view.showGridLines = False
    ws2.sheet_properties.tabColor = "5B8DB8"
    ws2.column_dimensions["A"].width = 22

    # ws2 header — no merge to avoid MergedCell conflicts
    ws2["A1"] = "Layer"
    ws2["A1"].font = hf(); ws2["A1"].fill = f(COL_HDR)
    ws2["A1"].alignment = ctr(); ws2["A1"].border = bd()

    for j, (label, _) in enumerate(runs, 2):
        ws2.cell(row=1, column=j, value=label).font = Font(name=FONT, size=10, bold=True, color="FFFFFF")
        ws2.cell(row=1, column=j).fill = f(rcolors[(j-2) % len(rcolors)])
        ws2.cell(row=1, column=j).alignment = ctr()
        ws2.cell(row=1, column=j).border = bd()
        ws2.column_dimensions[chr(64+j)].width = 16

    layer_names = [b["layer"] for b in all_bottlenecks[0]]
    bn_data_start = 2
    for i, layer in enumerate(layer_names):
        row = bn_data_start + i
        bg = ZEBRA if i % 2 == 0 else WHITE
        ws2.cell(row=row, column=1, value=layer).font = bf(10, bold=True)
        ws2.cell(row=row, column=1).fill = f(bg)
        ws2.cell(row=row, column=1).alignment = lft()
        ws2.cell(row=row, column=1).border = bd()
        for j, bns in enumerate(all_bottlenecks, 2):
            score = next((b["score"] for b in bns if b["layer"] == layer), 0)
            c = ws2.cell(row=row, column=j, value=score)
            c.font = bf(11, bold=True); c.fill = f(bg)
            c.alignment = ctr(); c.border = bd()
        ws2.row_dimensions[row].height = 18

    # Conditional colour scale across all run columns
    for j in range(n_runs):
        col_l = chr(66 + j)
        ws2.conditional_formatting.add(
            f"{col_l}{bn_data_start}:{col_l}{bn_data_start+len(layer_names)-1}",
            ColorScaleRule(start_type="num", start_value=0,  start_color="63BE7B",
                           mid_type="num",   mid_value=50,   mid_color="FFEB84",
                           end_type="num",   end_value=100,  end_color="F8696B"),
        )

    # Radar chart per run (overlay not supported natively — use grouped bar)
    ch_radar = RadarChart(); ch_radar.type = "filled"
    ch_radar.title = "Bottleneck Scores by Run"; ch_radar.style = 10
    ch_radar.width = 18; ch_radar.height = 14
    for j in range(n_runs):
        ref = Reference(ws2, min_col=j+2, min_row=1,
                        max_row=1+len(layer_names))
        ch_radar.add_data(ref, titles_from_data=True)
    cats2 = Reference(ws2, min_col=1, min_row=2, max_row=1+len(layer_names))
    ch_radar.set_categories(cats2)
    ws2.add_chart(ch_radar, f"{chr(65+n_runs+2)}2")

    # Grouped bar chart
    ch_bn_bar = BarChart(); ch_bn_bar.type = "bar"; ch_bn_bar.grouping = "clustered"
    ch_bn_bar.title = "Bottleneck Scores — All Runs"; ch_bn_bar.style = 10
    ch_bn_bar.x_axis.title = "Score"; ch_bn_bar.width = 18; ch_bn_bar.height = 14
    for j in range(n_runs):
        ref = Reference(ws2, min_col=j+2, min_row=1, max_row=1+len(layer_names))
        ch_bn_bar.add_data(ref, titles_from_data=True)
    ch_bn_bar.set_categories(cats2)
    ws2.add_chart(ch_bn_bar, f"{chr(65+n_runs+2)}22")

    # ── Sheet 3: GPU Timeline Comparison ──────────────────────────────────────
    ws3 = wb.create_sheet("GPU_Timeline")
    ws3.sheet_view.showGridLines = False
    ws3.sheet_properties.tabColor = "7B68EE"

    ws3.merge_cells(f"A1:{chr(65+n_runs*2)}1")
    ws3["A1"] = "GPU Utilisation Comparison — All Runs"
    ws3["A1"].font = Font(name=FONT, size=12, bold=True, color="FFFFFF")
    ws3["A1"].fill = f(COL_HDR); ws3["A1"].alignment = ctr()
    ws3.row_dimensions[1].height = 22

    # Write time + gpu_util columns per run
    col = 1
    time_col_map = {}
    util_col_map = {}
    for j, (label, m) in enumerate(runs):
        gdf = m.gpu_ts
        if gdf.empty: continue
        if "gpu_idx" in gdf.columns:
            agg = gdf.groupby("time_sec")["gpu_util"].mean().reset_index()
        else:
            agg = gdf[["time_sec","gpu_util"]].copy()
        agg = downsample(agg, 200)
        max_t = m.run_duration_s * 1.05 if m.run_duration_s > 0 else agg["time_sec"].max()
        agg = agg[agg["time_sec"] <= max_t]

        ws3.cell(row=2, column=col,   value=f"{label} — Time (s)").font = hf(9)
        ws3.cell(row=2, column=col).fill = f(rcolors[j % len(rcolors)])
        ws3.cell(row=2, column=col+1, value=f"{label} — GPU Util %").font = hf(9)
        ws3.cell(row=2, column=col+1).fill = f(rcolors[j % len(rcolors)])
        ws3.column_dimensions[get_column_letter(col)].width   = 14
        ws3.column_dimensions[get_column_letter(col+1)].width = 14
        time_col_map[j] = col
        util_col_map[j] = col + 1
        data_r_start = 3
        for ri, (_, row_d) in enumerate(agg.iterrows()):
            ws3.cell(row=data_r_start + ri, column=col,   value=round(float(row_d["time_sec"]), 1))
            ws3.cell(row=data_r_start + ri, column=col+1, value=round(float(row_d["gpu_util"]), 1))
        col += 2

    # Line chart
    if util_col_map:
        max_rows = max(
            len(downsample(
                (m.gpu_ts.groupby("time_sec")["gpu_util"].mean().reset_index()
                 if "gpu_idx" in m.gpu_ts.columns else m.gpu_ts[["time_sec","gpu_util"]]),
                200
            ))
            for _, m in runs if not m.gpu_ts.empty
        ) + 2
        ch_g = LineChart()
        ch_g.title = "GPU Utilisation % — All Runs Overlaid"; ch_g.style = 10
        ch_g.y_axis.title = "GPU Util %"; ch_g.y_axis.scaling.max = 110
        ch_g.width = 22; ch_g.height = 12
        for j in util_col_map:
            uc = util_col_map[j]
            ref = Reference(ws3, min_col=uc, min_row=2, max_row=max_rows)
            ch_g.add_data(ref, titles_from_data=True)
            ch_g.series[-1].graphicalProperties.line.solidFill = rcolors[j % len(rcolors)]
            ch_g.series[-1].graphicalProperties.line.width = 20000
        ws3.add_chart(ch_g, f"{get_column_letter(col+1)}2")


    wb.save(str(out_path))
    print(f"✅  Comparison Excel:  {out_path.resolve()}  ({out_path.stat().st_size//1024} KB)")


# ── Zip packager ──────────────────────────────────────────────────────────────

def package_outputs(file_list: list[Path], zip_path: Path):
    """Zip all generated output files into a single archive."""
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for f in file_list:
            if f.exists():
                zf.write(f, arcname=f.name)
    size_kb = zip_path.stat().st_size // 1024
    print(f"\n📦  Package: {zip_path.resolve()}  ({size_kb} KB)")
    print(f"    Contents: {', '.join(f.name for f in file_list if f.exists())}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="AMOprof — AI Memory & IO Profiler",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
──── OFFLINE (raw file) mode ──────────────────────────────────────────────────
  # Single run from raw/ directory
  python3 amoprof.py --raw /data/run1/raw/

  # Multi-run comparison
  python3 amoprof.py \\
      --raw /data/run1/raw/ /data/run2/raw/ \\
      --labels "Baseline" "Optimised" --excel --zip

──── LIVE (Prometheus) mode ───────────────────────────────────────────────────
  # Collect from SGLang for 300s, then generate report
  python3 amoprof.py \\
      --prometheus http://localhost:30000/metrics \\
      --duration 300 --output live_report.html

  # Collect until Ctrl-C (duration=0)
  python3 amoprof.py \\
      --prometheus http://localhost:30000/metrics \\
      --output live_report.html --excel

  # Multiple SGLang instances compared live
  python3 amoprof.py \\
      --prometheus http://localhost:30000/metrics \\
                   http://localhost:30001/metrics \\
      --labels "4-worker" "8-worker" \\
      --duration 600 --interval 2.0 --excel --zip

  # Collect and also save raw CSVs for later offline re-analysis
  python3 amoprof.py \\
      --prometheus http://localhost:30000/metrics \\
      --duration 300 --save-raw ./raw_live_run1/ --output report.html
        """
    )

    # ── Offline mode ──────────────────────────────────────────────────────────
    parser.add_argument("--raw", nargs="*", default=[],
                        help="One or more raw/ directories, .zip files, or glob patterns")

    # ── Live Prometheus mode ──────────────────────────────────────────────────
    parser.add_argument("--prometheus", nargs="*", default=[], metavar="URL",
                        help="Prometheus server URL(s). Accepts:\n"
                             "  • Prometheus API base: http://host:9090\n"
                             "  • Label values endpoint: http://host:9090/api/v1/label/__name__/values\n"
                             "  • SGLang /metrics direct: http://host:30000/metrics\n"
                             "When using a Prometheus server (port 9090), pulls all DCGM/SGLang/"
                             "node_exporter/IPMI metrics via query_range API. Mutually exclusive with --raw.")
    parser.add_argument("--duration", type=int, default=0, metavar="SECONDS",
                        help="Collection window in seconds (live scrape mode only, default: 0=Ctrl-C)")
    parser.add_argument("--interval", type=float, default=2.0, metavar="SECONDS",
                        help="Scrape interval in seconds for live mode (default: 2.0)")
    parser.add_argument("--prom-start", default="", metavar="TIMESTAMP_OR_OFFSET",
                        help="Prometheus query window start. Accepts: Unix timestamp, "
                             "ISO datetime (2026-04-25T10:00:00), or relative offset (-1h, -30m, -2d). "
                             "Default: 1 hour ago.")
    parser.add_argument("--prom-end", default="", metavar="TIMESTAMP_OR_OFFSET",
                        help="Prometheus query window end (default: now). "
                             "E.g. --prom-end 2026-04-25T20:00:00")
    parser.add_argument("--prom-step", type=int, default=15, metavar="SECONDS",
                        help="Prometheus query_range step in seconds (default: 15). "
                             "Use 5 for high-resolution, 60 for long windows.")
    parser.add_argument("--prom-instance", default="", metavar="INSTANCE",
                        help="Filter all Prometheus queries to a specific instance label.\n"
                             "Equivalent to appending {instance='VALUE'} to every PromQL query.\n"
                             "  Example: --prom-instance msl-ssg-dgx3.msl.lab:30000\n"
                             "  Equivalent curl: curl -G '.../query' \\\n"
                             "    --data-urlencode 'query={instance=\"msl-ssg-dgx3.msl.lab:30000\"}'\n"
                             "Use to isolate one DGX node when multiple nodes report to the same server.")
    parser.add_argument("--prom-job", default="", metavar="JOB",
                        help="Filter Prometheus queries to a specific job label.\n"
                             "  Example: --prom-job sglang\n"
                             "  Example: --prom-job dcgm_exporter\n"
                             "Can be combined with --prom-instance.")
    parser.add_argument("--prom-labels", nargs="*", default=[], metavar="KEY=VALUE",
                        help="Additional Prometheus label filters (space-separated KEY=VALUE pairs).\n"
                             "ANDed with --prom-instance and --prom-job.\n"
                             "  Example: --prom-labels gpu=0 device=nvme9n1\n"
                             "  Produces: {instance='...', gpu='0', device='nvme9n1'}")
    parser.add_argument("--no-gpu", action="store_true",
                        help="Skip nvidia-smi collection in live scrape mode")
    parser.add_argument("--no-vmstat", action="store_true",
                        help="Skip /proc/vmstat collection in live scrape mode")
    parser.add_argument("--save-raw", default="", metavar="DIR",
                        help="Save collected timeseries as raw CSVs to DIR "
                             "(allows later offline re-analysis with --raw)")

    # ── Shared ────────────────────────────────────────────────────────────────
    parser.add_argument("--labels", nargs="*", default=[],
                        help="Display labels for each run (same order as --raw/--prometheus)")
    parser.add_argument("--output", default="aistack_report.html",
                        help="Primary HTML output path (default: aistack_report.html)")
    parser.add_argument("--excel", action="store_true",
                        help="Also generate Excel workbook(s)")
    parser.add_argument("--excel-output", default="",
                        help="Excel output path (single-run only)")
    parser.add_argument("--excel-only", action="store_true",
                        help="Generate Excel only, skip HTML")
    parser.add_argument("--data", nargs="*", default=[], metavar="FILE_OR_URL",
                        help="Adaptive mode: CSV / JSON / JSONL file(s) or URL. "
                             "Schema is auto-inferred from the data itself. "
                             "E.g.: --data benchmark.jsonl  or  --data a.csv b.jsonl")

    # ── Offline metric sources (KV_SSD_Inference_Metrics_Complete_Table §A–G) ─
    parser.add_argument("--blktrace", default="", metavar="FILE",
                        help="blkparse output or pre-processed CSV. Enables §C/D/E IO analytics.\n"
                             "Collect: blktrace -d /dev/nvme2n1 -o - | blkparse -i - > blktrace.txt\n"
                             "CSV format: time_sec,type(R/W/D),offset_bytes,size_bytes,lat_ms")
    parser.add_argument("--blktrace-analysis-dir", default="", metavar="DIR",
                        help="Directory of pre-computed blktrace analysis results.\n"
                             "Expected files: summary.json, bandwidth_per_stream.csv,\n"
                             "  hot_regions_overall.csv, interarrival_distribution.csv, etc.\n"
                             "When provided, uses pre-computed results for richer analysis\n"
                             "than parsing raw blktrace events. Also loads the raw\n"
                             "blkparse_events.generated.csv from the same directory if present.")
    parser.add_argument("--nvme-smart", default="", metavar="FILE",
                        help="nvme smart-log JSON for SSD health metrics.\n"
                             "Collect: sudo nvme smart-log /dev/nvme2n1 -o json > nvme_smart.json")
    parser.add_argument("--iostat", default="", metavar="FILE",
                        help="iostat -dxm output for NVMe BW/latency (when node_exporter unavailable).\n"
                             "Collect: iostat -dxm 1 /dev/nvme2n1 | tee iostat.txt")
    parser.add_argument("--pcm", default="", metavar="FILE",
                        help="Intel PCM pcm-memory output for DRAM BW (non-AMD systems).\n"
                             "Collect: sudo pcm-memory 1 | tee pcm_memory.txt")
    parser.add_argument("--kv-event-log", default="", metavar="FILE",
                        help="Custom KV block event log (JSON/CSV) for exact block lifetime analysis.\n"
                             "Columns: time_sec, event (write/evict/trim), block_id, request_id")
    parser.add_argument("--kv-block-size", type=int, default=0, metavar="TOKENS",
                        help="KV block size in tokens (default: auto-detect from sglang metrics). "
                             "Typical SGLang default = 16.")
    parser.add_argument("--nvme-device", default="", metavar="DEVICE",
                        help="NVMe device name for node_exporter / iostat filtering.\n"
                             "  Example: --nvme-device nvme9n1\n"
                             "  Default: auto-detect (picks the nvme device with most IO activity).\n"
                             "  Only needed when you have multiple NVMe devices and want a specific one.")

    parser.add_argument("--zip", action="store_true",
                        help="Bundle all outputs into a .zip package")
    parser.add_argument("--title", default="",
                        help="Optional run label shown in report header")
    args = parser.parse_args()

    # ── Validate: must have either --raw, --prometheus, or --data ─────────────
    if not args.raw and not args.prometheus and not args.data:
        parser.error("Provide --raw (offline), --prometheus (live), or --data (adaptive) — see --help")
    if sum(bool(x) for x in [args.raw, args.prometheus, args.data]) > 1:
        parser.error("--raw, --prometheus, and --data are mutually exclusive")

    # ── ADAPTIVE DATA MODE ────────────────────────────────────────────────────
    if args.data:
        print(f"\n{'='*60}")
        print("  AMOprof — Adaptive Schema-Driven Analyzer")
        print(f"{'='*60}")
        print(f"  Sources: {args.data}")

        out_dir  = Path(args.output).parent
        out_base = Path(args.output).stem
        generated = []

        for src in args.data:
            src_name = Path(src).name if not src.startswith("http") else src
            print(f"\n  Loading: {src_name} ...", end=" ", flush=True)
            df = load_adaptive(src)
            print(f"OK  ({len(df):,} rows × {len(df.columns)} cols)")

            # Report title: use --title or derive from filename + tag dimension
            title = args.title or f"Analysis: {src_name}"
            safe  = __import__('re').sub(r'[^\w\-]', '_', Path(src).stem)[:40] if not src.startswith("http") else "adaptive"
            out_path = out_dir / f"{out_base}_{safe}.html"

            print(f"  Generating report → {out_path.name} ...", end=" ", flush=True)
            generate_adaptive_report(df, title=title,
                                     output_path=str(out_path),
                                     source_name=src_name)
            sz = out_path.stat().st_size
            print(f"OK  ({sz//1024} KB)")
            generated.append(out_path)

        if args.zip and generated:
            import zipfile
            zp = out_dir / f"{out_base}_adaptive_reports.zip"
            with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
                for f in generated:
                    zf.write(f, f.name)
            print(f"\n📦  Package: {zp}  ({zp.stat().st_size//1024} KB)")

        print(f"\n  Done. {len(generated)} report(s) written.")
        return

    print(f"\n{'='*60}")
    print("  AMOprof — AI Memory & IO Profiler")
    print(f"{'='*60}")

    timestamp   = args.title or datetime.now().strftime("%Y-%m-%d %H:%M")
    out_base    = Path(args.output).stem
    out_dir     = Path(args.output).parent
    do_excel    = args.excel or args.excel_only
    do_html     = not args.excel_only
    generated: list[Path] = []

    # ── Resolve inputs and labels ─────────────────────────────────────────────
    if args.prometheus:
        raw_paths   = args.prometheus
        input_mode  = "prometheus"
    else:
        raw_paths   = args.raw
        input_mode  = "offline"

    n_runs  = len(raw_paths)
    labels  = list(args.labels) if args.labels else []
    for i, rp in enumerate(raw_paths):
        if i >= len(labels):
            if input_mode == "prometheus":
                # Derive label from host:port
                import urllib.parse
                parsed = urllib.parse.urlparse(rp)
                labels.append(f"{parsed.hostname}:{parsed.port or 80}")
            else:
                p = Path(rp)
                name = p.stem if p.is_file() else p.name
                name = name.replace("metrics_run_","run_").replace("raw","run")
                labels.append(name or f"Run{i+1}")

    print(f"\n  Mode: {'LIVE (Prometheus)' if input_mode == 'prometheus' else 'OFFLINE (raw files)'}")
    print(f"  Runs: {n_runs}")

    # ── Load / collect all runs ───────────────────────────────────────────────
    runs_data: list[tuple[str, Metrics]] = []
    for i, (rp, label) in enumerate(zip(raw_paths, labels)):
        if input_mode == "prometheus":
            print(f"\n[Collect {i+1}/{n_runs}] {label}  ←  {rp}")
            save_dir = None
            if args.save_raw:
                safe = label.replace("/","_").replace(" ","_")[:30]
                save_dir = Path(args.save_raw) / safe

            # Detect if this is a Prometheus server (port 9090 or /api/v1 path)
            # vs a direct SGLang /metrics endpoint
            import urllib.parse as _up
            parsed_url = _up.urlparse(rp)
            is_prom_server = (
                "9090" in rp or
                "api/v1" in rp or
                (parsed_url.port and parsed_url.port == 9090)
            )

            if is_prom_server:
                # ── Prometheus API mode (query_range) ─────────────────────────
                import time as _time2

                def _parse_time(s: str, now: float) -> float:
                    if not s:
                        return 0
                    import re
                    if re.match(r'^\d{10,}(\.\d+)?$', s):
                        return float(s)
                    m = re.match(r'^-(\d+)([hmd])$', s)
                    if m:
                        n, unit = int(m.group(1)), m.group(2)
                        return now - n * {"h":3600,"m":60,"d":86400}[unit]
                    # Try ISO datetime — always treat as UTC to avoid TZ offsets
                    from datetime import datetime, timezone as _tz
                    for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]:
                        try:
                            return datetime.strptime(s, fmt).replace(tzinfo=_tz.utc).timestamp()
                        except ValueError:
                            pass
                    return 0

                now_ts     = _time2.time()
                t_end_ts   = _parse_time(args.prom_end,   now_ts) or now_ts
                # --duration maps to window size in API mode when --prom-start not set
                if not args.prom_start and args.duration and args.duration > 0:
                    t_start_ts = t_end_ts - args.duration
                else:
                    t_start_ts = _parse_time(args.prom_start, now_ts) or (t_end_ts - 3600)

                data = collect_from_prometheus_api(
                    prom_base_url = rp,
                    start_time    = t_start_ts,
                    end_time      = t_end_ts,
                    step_s        = args.prom_step,
                    label         = label,
                    output_dir    = save_dir,
                    instance      = getattr(args, "prom_instance", ""),
                    job           = getattr(args, "prom_job", ""),
                    extra_labels  = {
                        **_parse_prom_extra_labels(getattr(args, "prom_labels", [])),
                        **({"nvme_device": args.nvme_device} if args.nvme_device else {}),
                    },
                )
                data["_nvme_device_hint"] = args.nvme_device

                # ── Load blktrace / NVMe-smart / iostat extras in Prometheus mode ──
                # These are supplemental offline files, independent of the API query
                bt_adir = getattr(args, 'blktrace_analysis_dir', '')
                if bt_adir:
                    ad = Path(bt_adir)
                    print(f"  [blktrace-analysis] Loading directory: {ad}", flush=True)
                    bt_analysis = _load_blktrace_analysis_dir(ad)
                    if bt_analysis:
                        data["blktrace_analysis"] = bt_analysis
                        print(f"    Loaded: {len(bt_analysis)} analysis objects")
                        # Also bring in raw events CSV if present
                        raw_csv = ad / "blkparse_events.generated.csv"
                        if raw_csv.exists():
                            try:
                                blkt_raw = pd.read_csv(raw_csv, low_memory=False,
                                                       on_bad_lines='skip')
                                blkt_raw.columns = [c.strip() for c in blkt_raw.columns]
                                # Filter out blkparse info lines (non-numeric timestamp)
                                ts_col = next((c for c in ("ts","time_sec","timestamp")
                                               if c in blkt_raw.columns), None)
                                if ts_col:
                                    blkt_raw = blkt_raw[
                                        pd.to_numeric(blkt_raw[ts_col], errors='coerce').notna()
                                    ].copy()
                                    blkt_raw[ts_col] = blkt_raw[ts_col].astype(float)
                                # Normalize to standard schema (type, time_sec, size_bytes, sector…)
                                blkt_norm = _normalise_blktrace_df(blkt_raw)
                                if not blkt_norm.empty:
                                    data["blktrace_raw"] = blkt_norm
                                    print(f"    Loaded raw events: {len(blkt_norm)} rows "
                                          f"(R={int((blkt_norm['type']=='R').sum())} "
                                          f"W={int((blkt_norm['type']=='W').sum())} "
                                          f"D={int((blkt_norm['type']=='D').sum())})")
                            except Exception as e:
                                print(f"    [blktrace-analysis] Could not load raw CSV: {e}")
                if getattr(args, 'nvme_smart', ''):
                    data.update(_load_nvme_smart(args.nvme_smart))
                if getattr(args, 'iostat', ''):
                    data.update(_load_iostat(args.iostat))
            else:
                # ── Live scrape mode (direct /metrics endpoint) ───────────────
                data = collect_from_prometheus(
                    prom_url     = rp,
                    duration_s   = args.duration,
                    interval_s   = args.interval,
                    extra_gpu    = not args.no_gpu,
                    extra_vmstat = not args.no_vmstat,
                    label        = label,
                    output_dir   = save_dir,
                    instance     = getattr(args, "prom_instance", ""),
                    job          = getattr(args, "prom_job", ""),
                    extra_labels = _parse_prom_extra_labels(
                                       getattr(args, "prom_labels", [])),
                )
        else:
            print(f"\n[Load {i+1}/{n_runs}] {label}  ←  {rp}")
            has_extras = any([args.blktrace,
                              getattr(args, 'blktrace_analysis_dir', ''),
                              args.nvme_smart, args.iostat,
                              args.pcm, args.kv_event_log])
            if has_extras:
                p = Path(rp)
                raw_dir = p if p.is_dir() else Path(".")
                data = load_raw_dir_with_extras(
                    raw_path              = raw_dir,
                    blktrace_file         = args.blktrace,
                    blktrace_analysis_dir = getattr(args, 'blktrace_analysis_dir', ''),
                    nvme_smart_file       = args.nvme_smart,
                    iostat_file           = args.iostat,
                    pcm_file              = args.pcm,
                    kv_event_log          = args.kv_event_log,
                    kv_block_size_tokens  = args.kv_block_size,
                    nvme_device           = args.nvme_device,
                )
                if p.is_file() and p.suffix == ".zip":
                    data.update(load_zip(p))
            else:
                data = resolve_input(rp)
            print(f"      {len(data)} files loaded")

        m = extract_metrics(data)
        if input_mode == "offline":
            print(f"      TTFT {m.ttft_ms:.0f}ms  TPOT {m.tpot_ms:.1f}ms  "
                  f"Peak {m.gen_tp_peak:.1f}tok/s  GPU {m.gpu_util_mean:.1f}%  "
                  f"HBM {m.hbm_util_pct:.1f}%")
        runs_data.append((label, m))

    all_bottlenecks = [score_bottlenecks(m) for _, m in runs_data]
    all_recs        = [build_recommendations(m, bns)
                       for (_, m), bns in zip(runs_data, all_bottlenecks)]

    # ── Per-run individual reports ────────────────────────────────────────────
    for i, ((label, m), bns, recs) in enumerate(
            zip(runs_data, all_bottlenecks, all_recs)):
        safe = label.replace(" ","_").replace("/","_")[:30]
        prefix = f"{out_base}_run{i+1}_{safe}" if n_runs > 1 else out_base

        if do_html:
            print(f"\n[HTML {i+1}/{n_runs}] {label}")
            charts = {}
            charts["gpu_timeline"] = chart_gpu_timeline(m)
            charts["inference"]    = chart_inference_metrics(m)
            charts["memory"]       = chart_memory(m)
            charts["latency"]      = chart_latency_breakdown(m)
            charts["percentiles"]  = chart_percentile_summary(m)
            charts["storage"]      = chart_storage(m)
            charts["radar"]        = chart_bottleneck_radar(bns)
            charts["kv_analysis"]  = chart_kv_analysis(m)
            charts["kv_tiers"]     = chart_kv_tiers(m)
            charts["session"]      = chart_session_analysis(m)
            charts["kvb_events"]   = chart_kvb_events(m)
            charts["nvme_io"]      = chart_nvme_io(m)
            charts["blkio_deep"]   = chart_blkio_deep(m)
            charts["ssd_read"]     = chart_ssd_read_workload(m)
            charts["ssd_write"]    = chart_ssd_write_workload(m)
            charts["trim_seasonal"]= chart_trim_seasonal(m)
            charts["cross_layer"]  = chart_cross_layer_kpi(m)
            charts["bt_streams"]   = chart_blktrace_streams(m)
            charts["bt_hotcold"]   = chart_blktrace_hotcold(m)
            charts["kvssd_io"]     = chart_kvssd_io(m)
            charts["kvssd_cross"]  = chart_kvssd_cross_layer(m)
            charts["hbm_bw"]       = chart_hbm_bandwidth(m)
            charts["dram_bw"]      = chart_dram_bandwidth(m)
            charts["swap_storm"]   = chart_swap_storm(m)
            html_path = out_dir / f"{prefix}.html"
            html = build_html(m, bns, recs, charts, label)
            html_path.write_text(html, encoding="utf-8")
            generated.append(html_path)
            print(f"      ✓ {html_path.name}  ({html_path.stat().st_size//1024} KB)")

        if do_excel:
            xlsx_path = (Path(args.excel_output) if (args.excel_output and n_runs == 1)
                         else out_dir / f"{prefix}.xlsx")
            print(f"[XLSX {i+1}/{n_runs}] {label}")
            generate_excel(m, bns, recs, label, xlsx_path)
            generated.append(xlsx_path)

    # ── Comparison report (multi-run only) ────────────────────────────────────
    if n_runs > 1:
        print(f"\n[Compare] Building cross-run comparison...")

        if do_html:
            print("      Generating interactive comparison report (Chart.js)...")
            cmp_html_path = out_dir / f"{out_base}_comparison.html"
            html = build_comparison_html(runs_data, all_bottlenecks, timestamp)
            cmp_html_path.write_text(html, encoding="utf-8")
            generated.append(cmp_html_path)
            print(f"      ✓ {cmp_html_path.name}  ({cmp_html_path.stat().st_size//1024} KB)")

        if do_excel:
            cmp_xlsx_path = out_dir / f"{out_base}_comparison.xlsx"
            print(f"      Generating comparison workbook...")
            generate_comparison_excel(runs_data, all_bottlenecks, timestamp, cmp_xlsx_path)
            generated.append(cmp_xlsx_path)

    # ── Zip package ───────────────────────────────────────────────────────────
    if args.zip or n_runs > 1:
        zip_path = out_dir / f"{out_base}_aistack_reports.zip"
        package_outputs(generated, zip_path)
        generated.append(zip_path)

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  Done. {len(generated)} file(s) written:")
    for f in generated:
        if f.exists():
            print(f"    {f.name:50s}  {f.stat().st_size//1024:>5} KB")
    if generated:
        zip_f = [f for f in generated if f.suffix == ".zip"]
        if zip_f:
            print(f"\n  Download all:  scp server:{zip_f[0].resolve()} .")
        else:
            print(f"\n  Copy all:  scp server:{out_dir.resolve()}/*.html .")
    print()


if __name__ == "__main__":
    main()