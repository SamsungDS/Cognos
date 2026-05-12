#!/bin/bash

python3 kvssd_trace_tool.py analyze --trace-dir results/kvssd_both_run2 --actions '' --out results/kvssd_both_run2_blktrace_analysis --kv-block-size 131072 --page-size 4096 --window-sec 1 --write-events-csv
