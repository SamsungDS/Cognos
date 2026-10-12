#!/usr/bin/env python3
"""--model-path must never produce "model architecture unavailable".

Run: python3 tests/test_model_config_warning.py

Reported symptom, with --model-path passed globally to analyze:

    Tier chart data — L2 (DRAM BW): yes | L3 (NVMe): yes
    [warn] model architecture unavailable — KV bytes/token will be ESTIMATED
           from the model name (approximate).
           amoprof_model_config_* was not found in this Prometheus window.

Two things were wrong with that.

The CHECK read raw/model_config.json and nothing else, so it depended on the
caller having written that file before the fetch ran. The prom-only path does
write it first, and a comment there says the ordering was already got wrong
once for exactly this reason. An ordering dependency that keeps breaking is
worth removing rather than fixing again, so the fetch now takes the
already-read config and writes the file itself when it is missing.

The MESSAGE was wrong for the person most likely to read it. It blamed absent
Prometheus metrics and advised passing --model-path, to someone who had just
passed --model-path. It now names the path it checked and distinguishes "no
config was offered" from "a config was offered and the write did not land".

The warning block is executed here against the real source text, so the test
cannot drift from the code it is asserting about.
"""
import json
import pathlib
import sys
import tempfile
import textwrap
import shutil

_SRC = (pathlib.Path(__file__).resolve().parent.parent
        / "amoprof" / "report" / "amoprof.py").read_text()
_START = '        _mc = output_dir / "model_config.json"'
_END = '        print(f"  Raw CSVs saved'
BLOCK = textwrap.dedent(_SRC[_SRC.index(_START):_SRC.index(_END)])

MC = {"num_hidden_layers": 60, "num_key_value_heads": 16, "head_dim": 256,
      "torch_dtype": "bfloat16", "_name_or_path": "google/gemma-4-31b-it"}

_RESULTS = []


def _check(name, got, want):
    ok = got == want
    _RESULTS.append((ok, name))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        print(f"        got  {got!r}\n        want {want!r}")


def _run(output_dir, model_config):
    out = []
    ns = {"output_dir": output_dir, "model_config": model_config,
          "json": json, "print": lambda *a, **k: out.append(" ".join(map(str, a)))}
    exec(BLOCK, ns)
    return out


class _FailingPath(type(pathlib.Path())):
    """A real path whose write_text always fails.

    Needed because this suite may run as root, where a read-only directory
    does not stop a write and the except branch would never execute.
    """

    def write_text(self, *a, **k):
        raise PermissionError("Read-only file system")


def main() -> int:
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="amoprof_mc_"))
    try:
        print("\nThe reported symptom: config supplied, file not yet written")
        d = tmp / "a"
        d.mkdir()
        out = _run(d, MC)
        f = d / "model_config.json"
        _check("the fetch writes the file itself", f.is_file(), True)
        _check("with the geometry it was given",
               json.loads(f.read_text())["num_hidden_layers"], 60)
        _check("and does NOT warn that the architecture is unavailable",
               any("ESTIMATED" in o for o in out), False)
        _check("it says where it wrote it",
               any(str(f) in o for o in out), True)
        _check("and reports the geometry, so the value is checkable",
               any("layers=60" in o and "kv_heads=16" in o
                   and "head_dim=256" in o for o in out), True)

        print("\nA file already there is not touched, and nothing is said")
        d = tmp / "b"
        d.mkdir()
        (d / "model_config.json").write_text(json.dumps({"num_hidden_layers": 80}))
        out = _run(d, MC)
        _check("the existing config survives",
               json.loads((d / "model_config.json").read_text())["num_hidden_layers"],
               80)
        _check("and the block is silent", out, [])

        print("\nNothing available: warn, and name the path checked")
        d = tmp / "c"
        d.mkdir()
        out = _run(d, None)
        _check("it warns", any("ESTIMATED" in o for o in out), True)
        _check("it names the exact path it looked at",
               any(f"Checked: {d / 'model_config.json'}" in o for o in out), True)
        _check("it explains the Prometheus route as well",
               any("amoprof_model_config_*" in o for o in out), True)
        _check("and suggests the flag, which was genuinely not passed",
               any("pass --model-path" in o for o in out), True)

        print("\nConfig supplied but the write fails: blame the write")
        d = tmp / "d"
        d.mkdir()
        out = _run(_FailingPath(d), MC)
        _check("the write failure is reported with its exception",
               any("could not write" in o and "PermissionError" in o
                   for o in out), True)
        _check("it still falls back to the estimate warning",
               any("ESTIMATED" in o for o in out), True)
        _check("it says the flag WAS honoured",
               any("the flag was honoured" in o for o in out), True)
        # The whole point: never tell someone to pass a flag they passed.
        _check("and does not advise passing the flag again",
               any("Fix for this run: pass --model-path" in o for o in out),
               False)

        print("\nThe fetch chain carries the config to where it is needed")
        import ast
        _repo = pathlib.Path(__file__).resolve().parent.parent
        for _mod, _fn in (("amoprof/report/amoprof.py",
                           "collect_from_prometheus_api"),
                          ("amoprof/prometheus_source.py",
                           "fetch_from_prometheus")):
            _t = ast.parse((_repo / _mod).read_text())
            _f = [n for n in ast.walk(_t) if isinstance(n, ast.FunctionDef)
                  and n.name == _fn][0]
            _names = {a.arg for a in _f.args.args + _f.args.kwonlyargs}
            _check(f"{_fn} accepts model_config", "model_config" in _names, True)
        _cli = (_repo / "amoprof" / "cli.py").read_text()
        _check("analyze reads the config and hands it down",
               "model_config=(_read_model_config(" in _cli, True)
        _check("compare does too", "model_config         = _mc_run" in _cli, True)
        # And compare resolves it at the TOP of the loop body: the fetch call
        # sits above the later write, so a binding further down would have
        # raised UnboundLocalError on the first run.
        _t = ast.parse(_cli)
        _cf = [n for n in ast.walk(_t) if isinstance(n, ast.FunctionDef)
               and n.name == "_compare"][0]
        _b = [n.lineno for n in ast.walk(_cf)
              if isinstance(n, ast.Name) and n.id == "_mc_run"
              and isinstance(n.ctx, ast.Store)]
        _l = [n.lineno for n in ast.walk(_cf)
              if isinstance(n, ast.Name) and n.id == "_mc_run"
              and isinstance(n.ctx, ast.Load)]
        _check("compare binds the config before its first use",
               bool(_b) and bool(_l) and min(_b) < min(_l), True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    bad = [n for ok, n in _RESULTS if not ok]
    print(f"\n{len(_RESULTS) - len(bad)}/{len(_RESULTS)} passed"
          + (f" — FAILED: {', '.join(bad)}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
