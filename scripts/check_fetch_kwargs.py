#!/usr/bin/env python3
"""Check that every keyword passed across the Prometheus fetch chain exists.

The chain is three hops, each with its own explicit signature:

    cli._analyze  --prom_kwargs-->  prometheus_source.fetch_from_prometheus
                  --------------->  report.amoprof.collect_from_prometheus_api

A keyword added at one hop and not the next raises TypeError at RUN time, on
the first real invocation, after the run directory and the model config have
already been written -- which is exactly how --l35-nvme-device shipped broken
in v1.58.0.
"""
import ast
import sys
from pathlib import Path

FAILS = []


def _params(fn: ast.FunctionDef) -> set[str]:
    a = fn.args
    names = {p.arg for p in (a.posonlyargs + a.args + a.kwonlyargs)}
    if a.kwarg:                      # **kwargs accepts anything
        names.add("**")
    return names


def _func_def(tree, name):
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            return n
    return None


def _calls(tree, name):
    """Every call to `name`, as (lineno, {keyword names}, has_double_star)."""
    out = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        fname = (f.id if isinstance(f, ast.Name)
                 else f.attr if isinstance(f, ast.Attribute) else "")
        if fname != name:
            continue
        kw = {k.arg for k in n.keywords if k.arg is not None}
        star = any(k.arg is None for k in n.keywords)
        out.append((n.lineno, kw, star))
    return out


def _dict_kwargs(tree, var):
    """Keys of every `var = dict(...)` / `var.update(...)` in the tree."""
    keys = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name) and t.id == var and isinstance(n.value, ast.Call):
                    f = n.value.func
                    if isinstance(f, ast.Name) and f.id == "dict":
                        keys |= {k.arg for k in n.value.keywords if k.arg}
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == "update"
                and isinstance(n.func.value, ast.Name) and n.func.value.id == var):
            for a in n.args:
                if isinstance(a, ast.Dict):
                    keys |= {k.value for k in a.keys
                             if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    return keys


def check(what, got, want):
    if got != want:
        FAILS.append(what)
        print(f"  FAIL {what}\n       got  {got!r}\n       want {want!r}")


def main(repo: Path) -> int:
    cli = ast.parse((repo / "amoprof" / "cli.py").read_text())
    psrc = ast.parse((repo / "amoprof" / "prometheus_source.py").read_text())
    amo = ast.parse((repo / "amoprof" / "report" / "amoprof.py").read_text())

    fetch = _func_def(psrc, "fetch_from_prometheus")
    collect = _func_def(amo, "collect_from_prometheus_api")
    if fetch is None or collect is None:
        print("  FAIL one of the two fetch functions is missing")
        return 1
    fetch_p, collect_p = _params(fetch), _params(collect)

    # Hop 2: the wrapper's forwarding call.
    for ln, kw, _star in _calls(psrc, "collect_from_prometheus_api"):
        unknown = sorted(k for k in kw if k not in collect_p and "**" not in collect_p)
        check(f"prometheus_source.py:{ln} forwards only known keywords",
              unknown, [])

    # Hop 1: the CLI builds prom_kwargs as a dict and splats it.
    prom_keys = _dict_kwargs(cli, "prom_kwargs")
    # `start`/`end` are the wrapper's own names; prom_url/output_dir are
    # passed positionally at the call site.
    unknown = sorted(k for k in prom_keys if k not in fetch_p and "**" not in fetch_p)
    check("cli.py prom_kwargs are all accepted by fetch_from_prometheus",
          unknown, [])
    for ln, kw, _star in _calls(cli, "fetch_from_prometheus"):
        unknown = sorted(k for k in kw if k not in fetch_p and "**" not in fetch_p)
        check(f"cli.py:{ln} passes only known keywords", unknown, [])

    # And the wrapper must not swallow a keyword it accepts but never uses.
    _fsrc = ast.dump(fetch)
    dropped = sorted(
        p for p in (fetch_p - {"**"})
        if p not in {"prom_url", "output_dir"}
        and f"arg='{p}'" not in _fsrc.split("body=", 1)[1]
        and f"id='{p}'" not in _fsrc.split("body=", 1)[1]
    )
    check("fetch_from_prometheus uses every keyword it accepts", dropped, [])

    print(f"  {len(FAILS)} failure(s)" if FAILS else "  none found")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1] if len(sys.argv) > 1 else ".")))
