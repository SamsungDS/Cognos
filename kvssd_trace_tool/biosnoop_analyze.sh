#!/bin/bash

python3 kvssd_trace_tool.py analyze --biosnoop-file results/kvssd_both_run2/biosnoop.txt --actions '' --out results/kvssd_both_run2_biosnoop_analysis --kv-block-size 4096 --page-size 4096 --window-sec 1 --write-events-csv
