#!/usr/bin/env python3
"""A configured local L3 must appear in the capacity chart, or say why not.

Run: python3 tests/test_l3_capacity_series.py

Reported: "Memory hierarchy capacity used" shows no L3 capacity on a report
generated with a local L3 SSD configured.

It cannot, on a Prometheus-only analyze, for a reason that has nothing to do
with how the tier was configured. Three things had to line up and one of them
could not:

* The report reads the only measured L3 capacity figures --
  hicache_fs_total_gb, hicache_fs_used_gb, nvme_device_capacity_gb -- out of
  smart_summary.json.
* They are produced by the ssd_hardware collector, whose Prometheus prefix is
  amoprof_ssd_hw_*, which the fetch's prefix map routes to
  ssd_hw_summary.json. A different file.
* cli.py merges them across at COLLECT time, with a comment saying why: "the
  smart_summary.json that the report reads ... without the report needing to
  read two separate files". The Prometheus path had no such merge.

So the fields were fetched, written to a file the report does not consult for
them, and the L3 series was dropped from the chart with nothing said.
_refresh_smart_capacity could not cover for it: it returns early without
run_dir/summary.json, which a prom_run_* directory never has, and its own
docstring says it no-ops on a cross-host analyze.

Three fixes, each tested here: the fetch now mirrors the collect-time merge;
the report reads ssd_hw_summary.json as a fallback so it depends on neither
merge; and a configured L3 whose capacity is unknown is NAMED in the chart's
subtitle instead of vanishing from it.
"""
import json
import pathlib
import shutil
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_COMB = (_ROOT / "amoprof" / "report" / "combined.py").read_text()
_AMO = (_ROOT / "amoprof" / "report" / "amoprof.py").read_text()
_CLI = (_ROOT / "amoprof" / "cli.py").read_text()

_RESULTS = []


def _check(name, got, want):
    ok = got == want
    _RESULTS.append((ok, name))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        print(f"        got  {got!r}\n        want {want!r}")


def main() -> int:
    print("\nThe mismatch that caused it")
    _check("the report reads smart_summary.json for the L3 figures",
           'smart      = _read_json(raw_dir / "smart_summary.json")' in _COMB,
           True)
    _check("the fetch routes amoprof_ssd_hw_* to a DIFFERENT file",
           '"amoprof_ssd_hw_":             ("ssd_hw_summary.json",' in _AMO,
           True)
    _check("collect mode bridges the two deliberately",
           "ssd_hw → smart_summary merge failed" in _CLI, True)
    _check("and says why in a comment",
           "the smart_summary.json that the report reads" in _CLI, True)
    _check("_refresh_smart_capacity cannot help: it needs summary.json",
           "if not raw_dir.exists() or not sum_path.exists():" in _CLI, True)
    _check("and admits it no-ops cross-host",
           "Silently no-ops if the device or path isn't reachable" in _CLI,
           True)

    print("\nThe Prometheus path now mirrors the collect-time merge")
    _check("it reads the sidecar",
           '_ssdhw_p = output_dir / "ssd_hw_summary.json"' in _AMO, True)
    _check("it merges the same field set collect mode does",
           all(k in _AMO for k in ('str(k).startswith("hicache_fs_")',
                                   '"nvme_device_capacity_gb", "hicache_size_gb"')),
           True)
    _check("it never overwrites a value smart_summary already has",
           "_added = [k for k in _want if k not in _sm]" in _AMO, True)
    _check("and it says what it merged",
           "so the L3 capacity series" in _AMO, True)

    print("\nThe report no longer depends on either merge")
    _check("it reads ssd_hw_summary.json as a fallback",
           '_ssd_hw_sum = _read_json(raw_dir / "ssd_hw_summary.json")' in _COMB,
           True)
    _fb = _COMB[_COMB.index("_ssd_hw_sum = _read_json"):][:900]
    _check("for every field the chart needs",
           [k for k in ("hicache_fs_total_gb", "hicache_fs_used_gb",
                        "hicache_fs_avail_gb", "hicache_fs_used_pct",
                        "nvme_device_capacity_gb", "hicache_size_gb")
            if k not in _fb], [])
    _check("without overriding a value already present",
           "if not smart.get(_k_hw) and _ssd_hw_sum.get(_k_hw):" in _COMB, True)

    print("\nAnd a configured L3 with no capacity is named, not dropped")
    _check("the omission is recorded", "_l3_cap_missing" in _COMB, True)
    _check("only when the tier IS configured",
           "elif l3_explicit_config:" in _COMB, True)
    _check("it names which figure is missing",
           '_l3_miss.append("total capacity")' in _COMB
           and '_l3_miss.append("used capacity")' in _COMB, True)
    _check("it names where that figure comes from",
           "ssd_hardware collector" in _COMB and "df snapshot" in _COMB, True)
    _check("it names the setup-details alternative",
           "L3 (local storage) capacity GB" in _COMB, True)
    _check("it explains why a Prometheus-only analyze cannot have it",
           "has no df to run" in _COMB, True)
    _check("and it reaches the chart's own subtitle",
           "+ _l3_cap_missing," in _COMB, True)

    print("\nThe merge behaves on real files")
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="amoprof_l3cap_"))
    try:
        # Exactly the block the fetch runs, against real files.
        import textwrap
        _blk = textwrap.dedent(_AMO[
            _AMO.index('            _ssdhw_p = output_dir / "ssd_hw_summary.json"'):
            _AMO.index('        except Exception as _hwex:')])
        HW = {"hicache_fs_total_gb": 966.4, "hicache_fs_used_gb": 127.2,
              "nvme_device_capacity_gb": 1024.0, "unrelated_field": 1}

        def _run(seed_smart):
            d = tmp / f"case{len(list(tmp.iterdir()))}"
            d.mkdir()
            (d / "ssd_hw_summary.json").write_text(json.dumps(HW))
            if seed_smart is not None:
                (d / "smart_summary.json").write_text(json.dumps(seed_smart))
            out = []
            ns = {"output_dir": d, "json": json,
                  "print": lambda *a, **k: out.append(" ".join(map(str, a)))}
            exec(_blk, ns)
            return json.loads((d / "smart_summary.json").read_text()), out

        sm, out = _run(None)
        _check("capacity lands in smart_summary.json",
               (sm["hicache_fs_total_gb"], sm["hicache_fs_used_gb"]),
               (966.4, 127.2))
        _check("the device capacity too", sm["nvme_device_capacity_gb"], 1024.0)
        _check("unrelated fields are not copied",
               "unrelated_field" in sm, False)
        _check("and it reports what it merged",
               any("Merged 3 ssd_hw field(s)" in o for o in out), True)

        sm2, out2 = _run({"hicache_fs_total_gb": 500.0, "temperature_c": 41})
        _check("an existing value is preserved, not overwritten",
               sm2["hicache_fs_total_gb"], 500.0)
        _check("the missing ones are still filled",
               sm2["hicache_fs_used_gb"], 127.2)
        _check("and unrelated SMART fields survive", sm2["temperature_c"], 41)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    bad = [n for ok, n in _RESULTS if not ok]
    print(f"\n{len(_RESULTS) - len(bad)}/{len(_RESULTS)} passed"
          + (f" — FAILED: {', '.join(bad)}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
