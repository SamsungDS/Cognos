#!/usr/bin/env bash
#
# scripts/collect_overhead.sh — measure the resource footprint of an
# already-running amoprof service while a workload is driven.
#
# Assumes:
#   * SGLang is already serving on --sglang-port.
#   * `amoprof service` (or `amoprof collect`) is already running with
#     whichever collector set the operator wants to characterise.
#   * The workload command in --bench-cmd is self-contained and reports
#     TTFT / TPOT / E2E in its stdout/JSON.
#
# What this actually measures:
#   * CPU %, resident memory (RSS), and disk write rate of the amoprof PID
#     throughout the bench.
#   * TTFT / TPOT / E2E from the bench driver's own JSON.
#   * Growth of the amoprof output directory on disk during the run.
#
# What this does NOT measure:
#   * The *marginal impact* of amoprof on the served workload's latency.
#     Answering that requires toggling amoprof off, running the same bench,
#     and comparing.  If you need that, see the paired script
#     `collect_overhead_ab.sh` (not shipped in this revision) or run this
#     script twice manually — once with `systemctl stop amoprof.service`
#     and once with it running.
#
# Verified against amoprof v1.20.23.
#
# Usage:
#   scripts/collect_overhead.sh \
#     --bench-cmd "python -m sglang.bench_serving --host localhost --port 30000 \
#                    --dataset-name random --num-prompts 200 \
#                    --random-input 8192 --random-output 128 --request-rate 4" \
#     --duration-s 900 \
#     --outdir runs/overhead-YYYYMMDD/
#
# Optional:
#   --amoprof-pid PID          Override PID auto-discovery.
#   --amoprof-output-dir PATH  Auto-detects growth if given.
#   --sglang-port N            Default 30000; used only for a readiness ping.

set -euo pipefail

BENCH_CMD=""
DURATION_S=900
OUTDIR=""
AMOPROF_PID=""
AMOPROF_OUTPUT_DIR=""
SGLANG_PORT=30000

while [[ $# -gt 0 ]]; do
    case "$1" in
        --bench-cmd)          BENCH_CMD="$2"; shift 2 ;;
        --duration-s)         DURATION_S="$2"; shift 2 ;;
        --outdir)             OUTDIR="$2"; shift 2 ;;
        --amoprof-pid)        AMOPROF_PID="$2"; shift 2 ;;
        --amoprof-output-dir) AMOPROF_OUTPUT_DIR="$2"; shift 2 ;;
        --sglang-port)        SGLANG_PORT="$2"; shift 2 ;;
        -h|--help)
            sed -n '/^# scripts\/collect_overhead/,/^set -euo/p' "$0"
            exit 0 ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
done

if [[ -z "$BENCH_CMD" || -z "$OUTDIR" ]]; then
    echo "usage: $0 --bench-cmd CMD --outdir D [--duration-s N] [--amoprof-pid PID] [--amoprof-output-dir PATH]" >&2
    exit 2
fi

mkdir -p "$OUTDIR"

# ─── discover the amoprof PID if not given ────────────────────────────────
if [[ -z "$AMOPROF_PID" ]]; then
    # Prefer `amoprof service` (long-lived Prometheus endpoint).  Fall back
    # to `amoprof collect` (spawned per workload).  Rank surviving
    # candidates by RSS so a Python worker beats any wrapper shell (the
    # amoprof.service systemd unit typically wraps the entrypoint in a
    # /bin/sh; pgrep otherwise returned that PID and produced all-zero
    # samples on the first pass).
    AMOPROF_PID=$(ps -eo pid=,rss=,args= 2>/dev/null \
        | awk 'BEGIN{IGNORECASE=1}
               $0 ~ /amoprof/ && $0 !~ /collect_overhead\.sh/ \
                                  && $0 !~ /pgrep/ && $0 !~ /grep/ \
                                  && $3 !~ /^\/?bin\/(sh|bash|dash|zsh)( |$)/ \
                                  && $0 !~ / bash -c / \
                                  && $0 !~ / sh -c /  { print $2, $1 }' \
        | sort -rn | head -n1 | awk '{print $2}')
fi
BASELINE_MODE=0
if [[ -z "$AMOPROF_PID" ]] || ! kill -0 "$AMOPROF_PID" 2>/dev/null; then
    echo "no live amoprof PID found — running in BASELINE mode." >&2
    echo "  (no pidstat sampling, no output-dir growth; workload KPIs only.)" >&2
    BASELINE_MODE=1
    AMOPROF_PID=0
else
    echo "monitoring amoprof PID $AMOPROF_PID"
fi

# ─── quick sglang readiness ping ──────────────────────────────────────────
if ! curl -sSf "http://localhost:${SGLANG_PORT}/metrics" >/dev/null 2>&1; then
    echo "warning: SGLang /metrics at :${SGLANG_PORT} not responding; " \
         "proceeding anyway (bench_serving will surface the failure)." >&2
fi

# ─── record initial output-dir size for growth measurement ────────────────
INITIAL_BYTES=0
if [[ $BASELINE_MODE -eq 0 && -n "$AMOPROF_OUTPUT_DIR" && -d "$AMOPROF_OUTPUT_DIR" ]]; then
    INITIAL_BYTES=$(du -sb "$AMOPROF_OUTPUT_DIR" 2>/dev/null | awk '{print $1+0}')
fi
INITIAL_TS=$(date +%s)

# ─── background pidstat (only when amoprof is actually running) ───────────
PIDSTAT_PID=""
if [[ $BASELINE_MODE -eq 0 ]]; then
    pidstat -h -u -r -d -p "$AMOPROF_PID" 1 > "$OUTDIR/pidstat.log" 2>&1 &
    PIDSTAT_PID=$!
    trap 'kill $PIDSTAT_PID 2>/dev/null || true' EXIT
else
    : > "$OUTDIR/pidstat.log"   # empty file so downstream reads gracefully
fi

# ─── drive the workload ───────────────────────────────────────────────────
echo "=== running --bench-cmd for up to ${DURATION_S}s ==="
( timeout "$DURATION_S" bash -c "$BENCH_CMD" ) \
    > "$OUTDIR/bench.log" 2>&1 || true

if [[ -n "$PIDSTAT_PID" ]]; then
    kill "$PIDSTAT_PID" 2>/dev/null || true
    wait "$PIDSTAT_PID" 2>/dev/null || true
fi

# ─── directory growth ────────────────────────────────────────────────────
FINAL_BYTES=0
if [[ $BASELINE_MODE -eq 0 && -n "$AMOPROF_OUTPUT_DIR" && -d "$AMOPROF_OUTPUT_DIR" ]]; then
    FINAL_BYTES=$(du -sb "$AMOPROF_OUTPUT_DIR" 2>/dev/null | awk '{print $1+0}')
fi
FINAL_TS=$(date +%s)
ELAPSED_S=$((FINAL_TS - INITIAL_TS))
GROWTH_BYTES=$((FINAL_BYTES - INITIAL_BYTES))
GROWTH_MB_PER_MIN=$(awk -v g="$GROWTH_BYTES" -v s="$ELAPSED_S" \
    'BEGIN { if (s>0) printf "%.2f", (g/1048576.0)/(s/60.0); else print 0 }')

# ─── extract KPIs from the bench driver ──────────────────────────────────
if [[ ! -f "$OUTDIR/bench.json" ]]; then
    awk '/^\{/,/^\}$/' "$OUTDIR/bench.log" > "$OUTDIR/bench.json" || true
fi

TTFT_MEAN=0; TTFT_P99=0; TPOT_MEAN=0; E2E_MEAN=0; REQS=0
if [[ -f "$OUTDIR/bench.json" ]] && jq empty "$OUTDIR/bench.json" >/dev/null 2>&1; then
    TTFT_MEAN=$(jq -r '(.mean_ttft_ms      // .median_ttft_ms       // 0) | tonumber' "$OUTDIR/bench.json")
    TTFT_P99=$(jq  -r '(.p99_ttft_ms       // 0)                          | tonumber' "$OUTDIR/bench.json")
    TPOT_MEAN=$(jq -r '(.mean_tpot_ms      // .median_tpot_ms       // 0) | tonumber' "$OUTDIR/bench.json")
    E2E_MEAN=$(jq  -r '(.mean_e2e_latency_ms // .mean_e2e_ms         // 0) | tonumber' "$OUTDIR/bench.json")
    REQS=$(jq      -r '(.completed         // .num_completed        // 0) | tonumber' "$OUTDIR/bench.json")
fi

# ─── summarise pidstat ───────────────────────────────────────────────────
python3 - <<'PY' "$OUTDIR/pidstat.log" "$OUTDIR/bench.log" "$OUTDIR/summary.csv" "$AMOPROF_PID" "$ELAPSED_S" "$GROWTH_MB_PER_MIN"
import sys, re, statistics as s
log, bench_log, out_csv, pid, elapsed, growth_mb_min = sys.argv[1:7]

# ---- amoprof resource footprint (pidstat) ---------------------------
cpu, rss, kbwr = [], [], []
with open(log, errors='replace') as f:
    for line in f:
        line = line.rstrip()
        if (not line) or line.startswith('Linux') or line.startswith('#'):
            continue
        p = line.split()
        # pidstat -h -u -r -d columns after line.split(), given the
        # 'HH:MM:SS AM/PM' timestamp counts as TWO tokens:
        #   [0]=time  [1]=AM/PM  [2]=UID  [3]=PID
        #   [4]=%usr  [5]=%system  [6]=%guest  [7]=%wait  [8]=%CPU
        #   [9]=CPU-core  [10]=minflt/s  [11]=majflt/s
        #   [12]=VSZ  [13]=RSS  [14]=%MEM
        #   [15]=kB_rd/s  [16]=kB_wr/s  [17]=kB_ccwr/s  [18]=iodelay  [19]=Command
        try:
            cpu.append(float(p[8]))     # %CPU
            rss.append(float(p[13]))    # RSS (kB)
            kbwr.append(float(p[16]))   # kB_wr/s
        except (IndexError, ValueError):
            continue

def stat(v, fmt='.2f'):
    if not v: return '0'
    return f'mean {sum(v)/len(v):{fmt}} peak {max(v):{fmt}}'

# ---- sglang.bench_serving 'Serving Benchmark Result' table parser ----
# Each metric renders as '<label>: <value> <unit>' after a header banner.
bench = {}
try:
    text = open(bench_log, errors='replace').read()
except FileNotFoundError:
    text = ''

def grab(pattern, cast=float):
    m = re.search(pattern, text, re.MULTILINE)
    if not m: return None
    try: return cast(m.group(1))
    except (ValueError, TypeError): return None

bench['ttft_mean_ms']  = grab(r'^Mean TTFT \(ms\):\s+([\d.]+)')
bench['ttft_p99_ms']   = grab(r'^P99 TTFT \(ms\):\s+([\d.]+)')
bench['ttft_p90_ms']   = grab(r'^P90 TTFT \(ms\):\s+([\d.]+)')
bench['tpot_mean_ms']  = grab(r'^Mean TPOT \(ms\):\s+([\d.]+)')
bench['tpot_p99_ms']   = grab(r'^P99 TPOT \(ms\):\s+([\d.]+)')
bench['itl_mean_ms']   = grab(r'^Mean ITL \(ms\):\s+([\d.]+)')
bench['e2e_mean_ms']   = grab(r'^Mean E2E Latency \(ms\):\s+([\d.]+)')
bench['e2e_p99_ms']    = grab(r'^P99 E2E Latency \(ms\):\s+([\d.]+)')
bench['requests_completed'] = grab(r'^Successful requests:\s+(\d+)', int)
bench['bench_duration_s']   = grab(r'^Benchmark duration \(s\):\s+([\d.]+)')
bench['output_throughput_toks'] = grab(r'^Output token throughput \(tok/s\):\s+([\d.]+)')
bench['total_throughput_toks']  = grab(r'^Total token throughput \(tok/s\):\s+([\d.]+)')

def show(k):
    v = bench.get(k)
    return 'n/a' if v is None else f'{v}'

print(f'amoprof PID {pid} - {len(cpu)} samples over ~{elapsed}s')
print(f'  CPU %      : {stat(cpu)}')
print(f'  RSS MB     : {stat([r/1024.0 for r in rss], ".1f")}')
print(f'  Disk W MB/s: {stat([k/1024.0 for k in kbwr], ".3f")}')
print(f'  Output-dir growth: {growth_mb_min} MB/min')
print()
print('Workload (parsed from bench.log Serving Benchmark Result):')
print(f'  TTFT mean {show("ttft_mean_ms")} ms  p99 {show("ttft_p99_ms")} ms')
print(f'  TPOT mean {show("tpot_mean_ms")} ms  p99 {show("tpot_p99_ms")} ms')
print(f'  ITL  mean {show("itl_mean_ms")} ms')
print(f'  E2E  mean {show("e2e_mean_ms")} ms  p99 {show("e2e_p99_ms")} ms')
print(f'  completed {show("requests_completed")} requests over {show("bench_duration_s")}s')
print(f'  output tok/s {show("output_throughput_toks")}   total tok/s {show("total_throughput_toks")}')

with open(out_csv, 'w') as f:
    f.write('metric,mean,peak\n')
    if cpu:
        f.write(f'cpu_pct,{sum(cpu)/len(cpu):.4f},{max(cpu):.4f}\n')
    if rss:
        f.write(f'rss_mb,{sum(rss)/len(rss)/1024:.4f},{max(rss)/1024:.4f}\n')
    if kbwr:
        f.write(f'disk_write_mb_s,{sum(kbwr)/len(kbwr)/1024:.4f},{max(kbwr)/1024:.4f}\n')
    f.write(f'output_dir_growth_mb_per_min,{growth_mb_min},{growth_mb_min}\n')
    for k, v in bench.items():
        val = '' if v is None else v
        f.write(f'{k},{val},{val}\n')

print(f'\nfull summary written to {out_csv}')
PY
PY

echo
echo "=== overhead measurement complete. dir: $OUTDIR ==="
