# KVSSD Trace Tool v4 Correct

This version includes the corrected `--backend {blktrace,biosnoop,both}` option.

## Verify

```bash
python3 kvssd_trace_tool.py capture --help
```

You should see:

```text
--backend {blktrace,biosnoop,both}
```

## Install

```bash
chmod +x install_deps.sh
./install_deps.sh
```

## Run both blktrace and biosnoop

```bash
sudo ./kvssd_trace_tool.py capture \
  --backend both \
  --dev /dev/nvme1n1 \
  --seconds 600 \
  --interval-sec 5 \
  --capture-sec 1 \
  --max-trace-size-gb 10 \
  --biosnoop-queue-time \
  --out kvssd_both_run
```

## Analyze blktrace side

```bash
./kvssd_trace_tool.py analyze \
  --trace-dir kvssd_both_run \
  --out kvssd_both_blktrace_analysis
```

## Analyze biosnoop side

```bash
./kvssd_trace_tool.py analyze \
  --biosnoop-file kvssd_both_run/biosnoop.txt \
  --actions '' \
  --out kvssd_both_biosnoop_analysis
```

## Notes

- Use `--actions ''` for biosnoop analysis because biosnoop events are tagged as `BIO`, not blkparse `D` or `C`.
- If biosnoop does not support `-d`, rerun capture with `--biosnoop-no-disk-filter`.
- If biosnoop does not support `-Q`, remove `--biosnoop-queue-time`.
