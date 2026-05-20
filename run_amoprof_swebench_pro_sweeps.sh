#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-all}"

MODEL="${MODEL:-deepseek-r1-70b}"
MODEL_HF_ID="${MODEL_HF_ID:-deepseek-ai/DeepSeek-R1-Distill-Llama-70B}"
HBM_CAP="${HBM_CAP:-320GB}"
DRAM_CAP="${DRAM_CAP:-512GB}"
NVME_CAP="${NVME_CAP:-1TB}"
MODEL_PORT="${MODEL_PORT:-30000}"

MAX_AGENT_STEPS="${MAX_AGENT_STEPS:-30}"
# Agent backend: none | amoprof | sweagent | mini
# Override with:  AGENT_BACKEND=sweagent ./run_aiwasp_swebench_pro_sweeps.sh concurrency
AGENT_BACKEND="${AGENT_BACKEND:-amoprof}"
MAX_TOKENS="${MAX_TOKENS:-8192}"
TIMEOUT="${TIMEOUT:-900}"
EVAL_WORKERS="${EVAL_WORKERS:-4}"
INFERENCE_CONCURRENCY="${INFERENCE_CONCURRENCY:-32}"
MAX_INSTANCES="${MAX_INSTANCES:-20}"
INSTANCES_PER_LEVEL="${INSTANCES_PER_LEVEL:-10}"

SWEBENCH_INSTANCES_PATH="${SWEBENCH_INSTANCES_PATH:-}"
SWEAGENT_DEFAULT_CONFIG="${SWEAGENT_DEFAULT_CONFIG:-}"
SWEAGENT_CONFIG_PATH="${SWEAGENT_CONFIG_PATH:-}"
SWEAGENT_MODEL_NAME="${SWEAGENT_MODEL_NAME:-$MODEL_HF_ID}"
SWEAGENT_MODEL_API_BASE="${SWEAGENT_MODEL_API_BASE:-http://127.0.0.1:${MODEL_PORT}/v1}"
SWEAGENT_MODEL_API_KEY="${SWEAGENT_MODEL_API_KEY:-EMPTY}"
SWEAGENT_MAX_INPUT_TOKENS="${SWEAGENT_MAX_INPUT_TOKENS:-50000}"
SWEAGENT_NUM_WORKERS="${SWEAGENT_NUM_WORKERS:-1}"
SWEAGENT_INSTANCES_TYPE="${SWEAGENT_INSTANCES_TYPE:-file}"
SWEAGENT_REDO_EXISTING="${SWEAGENT_REDO_EXISTING:-1}"
SWEAGENT_SHUFFLE="${SWEAGENT_SHUFFLE:-0}"

CONCURRENCY_LEVELS="${CONCURRENCY_LEVELS:-1,2,4,8,16,32}"
TURN_LEVELS="${TURN_LEVELS:-5,10,15,20}"
BATCH_SIZES="${BATCH_SIZES:-1,2,4,8,16}"
CONTEXT_LENGTHS="${CONTEXT_LENGTHS:-8192,32768,65536}"

OUTPUT_BASE="${AIWASP_OUTPUT_DIR:-$PWD/aiwasp_results_pro}"

build_base_cmd() {
  local -a cmd=(
    amoprof
    --model "$MODEL"
    --model-hf-id "$MODEL_HF_ID"
    --hbm-cap "$HBM_CAP"
    --dram-cap "$DRAM_CAP"
    --nvme-cap "$NVME_CAP"
    --benchmark swebench
    --swebench-server-port "$MODEL_PORT"
    --swebench-split pro
    --swebench-docker
    --swebench-agent-backend "$AGENT_BACKEND"
    --swebench-max-agent-steps "$MAX_AGENT_STEPS"
    --swebench-max-tokens "$MAX_TOKENS"
    --swebench-timeout "$TIMEOUT"
    --swebench-workers "$EVAL_WORKERS"
    --swebench-inference-concurrency "$INFERENCE_CONCURRENCY"
  )

  if [[ -n "$SWEBENCH_INSTANCES_PATH" ]]; then
    cmd+=(--swebench-instances-path "$SWEBENCH_INSTANCES_PATH")
  fi

  if [[ "$AGENT_BACKEND" == "sweagent" ]]; then
    if [[ -n "$SWEAGENT_DEFAULT_CONFIG" ]]; then
      cmd+=(--sweagent-default-config "$SWEAGENT_DEFAULT_CONFIG")
    fi
    if [[ -n "$SWEAGENT_CONFIG_PATH" ]]; then
      cmd+=(--sweagent-config-path "$SWEAGENT_CONFIG_PATH")
    fi
    if [[ -n "$SWEAGENT_MODEL_NAME" ]]; then
      cmd+=(--sweagent-model-name "$SWEAGENT_MODEL_NAME")
    fi
    if [[ -n "$SWEAGENT_MODEL_API_BASE" ]]; then
      cmd+=(--sweagent-model-api-base "$SWEAGENT_MODEL_API_BASE")
    fi
    if [[ -n "$SWEAGENT_MODEL_API_KEY" ]]; then
      cmd+=(--sweagent-model-api-key "$SWEAGENT_MODEL_API_KEY")
    fi
    cmd+=(
      --sweagent-max-input-tokens "$SWEAGENT_MAX_INPUT_TOKENS"
      --sweagent-num-workers "$SWEAGENT_NUM_WORKERS"
      --sweagent-instances-type "$SWEAGENT_INSTANCES_TYPE"
    )
    case "${SWEAGENT_REDO_EXISTING,,}" in
      1|true|yes|y) cmd+=(--sweagent-redo-existing) ;;
    esac
    case "${SWEAGENT_SHUFFLE,,}" in
      1|true|yes|y) cmd+=(--sweagent-shuffle) ;;
    esac
  fi

  printf '%q ' "${cmd[@]}"
}

run_case() {
  local name="$1"; shift
  local ts out_dir
  ts="$(date +%Y%m%d_%H%M%S)"
  out_dir="${OUTPUT_BASE}/${name}_${ts}"
  mkdir -p "$out_dir"
  local cmd
  cmd="$(build_base_cmd)"
  cmd+=" $* --output-dir $(printf '%q' "$out_dir")"
  echo
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting ${name}_${ts}"
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Output dir: $out_dir"
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Command: $cmd"
  eval "$cmd"
}

case "$MODE" in
  benchmark)
    run_case benchmark --swebench-max-instances "$MAX_INSTANCES"
    ;;
  concurrency)
    run_case concurrency_sweep \
      --swebench-concurrency-sweep \
      --swebench-concurrency-levels "$CONCURRENCY_LEVELS" \
      --swebench-instances-per-level "$INSTANCES_PER_LEVEL"
    ;;
  turns)
    run_case turns_sweep \
      --swebench-turns-sweep \
      --swebench-turns-levels "$TURN_LEVELS" \
      --swebench-instances-per-level "$INSTANCES_PER_LEVEL"
    ;;
  batch)
    run_case batch_sweep \
      --swebench-batch-sweep \
      --swebench-batch-sizes "$BATCH_SIZES" \
      --swebench-max-instances "$MAX_INSTANCES"
    ;;
  context)
    run_case context_sweep \
      --swebench-context-sweep \
      --swebench-context-lengths "$CONTEXT_LENGTHS" \
      --swebench-instances-per-level "$INSTANCES_PER_LEVEL"
    ;;
  all)
    "$0" benchmark
    "$0" concurrency
    "$0" turns
    "$0" batch
    "$0" context
    ;;
  *)
    echo "Usage: $0 {benchmark|concurrency|turns|batch|context|all}"
    exit 2
    ;;
esac
