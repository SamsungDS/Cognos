#!/usr/bin/env python3
"""`compare` can pass a model config, globally and per run.

Run: python3 tests/test_compare_model_config.py

`analyze` has had --model-path since early on: it writes raw/model_config.json
so KV bytes per token is computed from num_hidden_layers /
num_key_value_heads / head_dim rather than estimated from the model name.
`compare` had no equivalent, so every figure derived from KV bytes per token
-- L2 and L3 residency, bytes per token, the capacity reconciliation -- fell
back to a name-based estimate on a fetched run, with nothing in the report
saying it had.

Per-run as well as global, because two runs serving DIFFERENT models is a
comparison someone will want, and one global config would then be wrong for
at least one of them. The arithmetic below shows why it matters: the two
models in this test differ by 3x in KV bytes per token.

Needs no pandas and no Prometheus.
"""
import argparse
import json
import logging
import pathlib
import shutil
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
logging.basicConfig(level=logging.CRITICAL)
import amoprof.cli as cli  # noqa: E402

GEMMA = {"_name_or_path": "google/gemma-4-31b-it", "num_hidden_layers": 60,
         "num_key_value_heads": 16, "head_dim": 256, "torch_dtype": "bfloat16"}
LLAMA = {"_name_or_path": "meta-llama/Llama-3-70B", "num_hidden_layers": 80,
         "num_key_value_heads": 8, "head_dim": 128, "torch_dtype": "bfloat16"}

_RESULTS = []


def _check(name, got, want):
    ok = got == want
    _RESULTS.append((ok, name))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        print(f"        got  {got!r}\n        want {want!r}")


def _kv_bytes(cfg):
    """2 (K and V) x layers x kv_heads x head_dim x bytes-per-element."""
    _dt = str(cfg.get("torch_dtype", "")).lower()
    _w = 1 if "fp8" in _dt or "int8" in _dt else 4 if "float32" in _dt else 2
    return (2 * int(cfg["num_hidden_layers"]) * int(cfg["num_key_value_heads"])
            * int(cfg["head_dim"]) * _w)


def main() -> int:
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="amoprof_cmp_"))
    try:
        for name, body in (("gemma4", GEMMA), ("llama", LLAMA)):
            d = tmp / "models" / name
            d.mkdir(parents=True)
            (d / "config.json").write_text(json.dumps(body))
        for r in ("runA", "runB"):
            (tmp / r / "raw").mkdir(parents=True)

        print("\nThe flag exists on compare, and model_path is overridable")
        p = cli._build_parser()
        a = p.parse_args([
            "compare", "--prometheus", "http://p:9090",
            "--run", "A::100:200", "--run", "B::300:400",
            "--model-path", str(tmp / "models/gemma4/config.json"),
            "--run-opt", f"B=model_path={tmp}/models/llama/config.json"])
        _check("compare accepts --model-path", bool(a.model_path), True)
        _check("model_path is a per-run override key",
               "model_path" in cli._COMPARE_RUN_OPT_KEYS, True)
        ovr, errs = cli._parse_run_keyed_args(a.run_opt, ["A", "B"],
                                              flag="--run-opt")
        # The second return value is an error STRING, empty on success.
        _check("the per-run override parses with no error", errs, "")
        _check("and lands on the right run",
               ovr, {"B": {"model_path": f"{tmp}/models/llama/config.json"}})
        _check("the global flag covers the run with no override",
               ovr.get("A", {}).get("model_path", a.model_path),
               str(tmp / "models/gemma4/config.json"))

        print("\nEach run gets its own raw/model_config.json")
        ca = cli._write_model_config(
            tmp / "runA/raw",
            argparse.Namespace(model_path=str(tmp / "models/gemma4/config.json")))
        cb = cli._write_model_config(
            tmp / "runB/raw",
            argparse.Namespace(model_path=str(tmp / "models/llama/config.json")))
        _check("run A's file is written",
               (tmp / "runA/raw/model_config.json").is_file(), True)
        _check("run B's file is written",
               (tmp / "runB/raw/model_config.json").is_file(), True)
        ja = json.loads((tmp / "runA/raw/model_config.json").read_text())
        jb = json.loads((tmp / "runB/raw/model_config.json").read_text())
        _check("they are not the same config",
               (ja["num_hidden_layers"], jb["num_hidden_layers"]), (60, 80))
        _check("and the geometry each one needs survives the read",
               all(k in ja for k in ("num_hidden_layers",
                                     "num_key_value_heads", "head_dim")), True)

        print("\nWhy one global config would be wrong for one of them")
        _check("gemma-4-31b-it is 960 KB of KV per token",
               _kv_bytes(ja) // 1024, 960)
        _check("Llama-3-70B is 320 KB", _kv_bytes(jb) // 1024, 320)
        _check("so one config for both misstates a tier by 3x",
               round(_kv_bytes(ja) / _kv_bytes(jb), 1), 3.0)

        print("\nThe model's own identity is recorded, not a directory name")
        # _write_model_config reads cfg["_name_or_path"] first, but that key
        # was not in _MODEL_CONFIG_KEYS, so it never survived the read: the
        # branch was dead and the name fell through to the parent directory.
        _check("a plain model path records the config's _name_or_path",
               ca.get("_amoprof_model_name"), "google/gemma-4-31b-it")
        _check("not the directory it happened to sit in",
               ca.get("_amoprof_model_name") == "gemma4", False)
        _check("and it says where the name came from",
               ca.get("_amoprof_model_name_source"), "--model-path (explicit)")
        # A HuggingFace cache path with no _name_or_path still resolves, via
        # the models--owner--name path segment.
        hf = tmp / "hf/models--google--gemma-4-31b-it/snapshots/abc123"
        hf.mkdir(parents=True)
        (hf / "config.json").write_text(json.dumps(
            {k: v for k, v in GEMMA.items() if k != "_name_or_path"}))
        chf = cli._write_model_config(
            tmp / "runA/raw", argparse.Namespace(model_path=str(hf / "config.json")))
        _check("an HF cache path with no _name_or_path still resolves",
               chf.get("_amoprof_model_name"), "google/gemma-4-31b-it")

        print("\nA path that reads nothing is a typo, not a preference")
        cli._write_model_config(
            tmp / "runB/raw", argparse.Namespace(model_path=str(hf / "config.json")))
        before = json.loads((tmp / "runA/raw/model_config.json").read_text())
        bad = cli._write_model_config(
            tmp / "runA/raw", argparse.Namespace(model_path="/nonexistent/x.json"))
        _check("it returns nothing, so compare can exit 2", bad, {})
        after = json.loads((tmp / "runA/raw/model_config.json").read_text())
        _check("and it does not clobber the config already there",
               after, before)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    bad_names = [n for ok, n in _RESULTS if not ok]
    print(f"\n{len(_RESULTS) - len(bad_names)}/{len(_RESULTS)} passed"
          + (f" — FAILED: {', '.join(bad_names)}" if bad_names else ""))
    return 1 if bad_names else 0


if __name__ == "__main__":
    sys.exit(main())
