#!/usr/bin/env python3
"""Show exactly what each report path reads for the token counters.

Run from the amoprof source root:
    python3 diagnose_tokrate.py results/prom_run_XXXX/raw
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))

raw = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
from amoprof.report.combined import (            # noqa: E402
    _amoprof_read_columns_raw, _amoprof_read_columns_substr, _first_existing)

p = _first_existing(raw, ["sglang_timeseries.csv"])
print(f"file: {p}\n")

import csv
with open(p, newline="") as f:
    hdr = next(csv.reader(f))

for base in ("prompt_tokens_total", "generation_tokens_total"):
    print(f"=== {base} ===")
    cols = [c for c in hdr if base in c]
    print(f"  matching columns ({len(cols)}):")
    for c in cols:
        print(f"    {c[:110]}")

    exact = _amoprof_read_columns_raw(p, [f"sglang_{base}"]).get(f"sglang_{base}", [])
    ex = [v for v in exact if v == v]
    print(f"  EXACT  lookup 'sglang_{base}': n={len(ex)} "
          f"first={ex[0] if ex else None} last={ex[-1] if ex else None} "
          f"max={max(ex) if ex else None}")

    sub = _amoprof_read_columns_substr(p, {"v": [base]}).get("v", [])
    sb = [v for v in sub if v == v]
    print(f"  SUBSTR lookup '{base}':        n={len(sb)} "
          f"first={sb[0] if sb else None} last={sb[-1] if sb else None} "
          f"max={max(sb) if sb else None}")

    # what each surface would compute
    t = _amoprof_read_columns_raw(p, ["time_sec"]).get("time_sec", [])
    if sb and len(t) >= 2:
        dt = t[-1] - t[0]
        print(f"  run average (End Report style): "
              f"{(sb[-1] - sb[0]) / dt if dt else 0:.2f} tok/s over {dt:.0f}s")
    print()
print("If EXACT returns zeros/None while SUBSTR returns rising values, the")
print("Executive is reading the wrong column and the fix is in _counter_series.")
