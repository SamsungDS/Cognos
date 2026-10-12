#!/usr/bin/env python3
"""amoprof/report/amoprof.py is a module AND a program. Both must import.

Run: python3 tests/test_script_mode_imports.py

The pipeline runs `python .../amoprof/report/amoprof.py`. In that mode
sys.path[0] is .../amoprof/report, so the name `amoprof` resolves to
amoprof.py -- the file itself -- and a package-absolute import of a sibling
raises:

    ModuleNotFoundError: No module named 'amoprof.report';
    'amoprof' is not a package

Two imports added in v1.71.0 and v1.72.0 did exactly that. The file's own
header says not to, right above the guard they were supposed to use: "Every
import of the registry must therefore go through this guard -- never inline
at the call site." One of the two sat in build_html rather than in a chart
function, so it did not degrade a chart; it aborted the static report, and
the combined report with it:

    ⚠ chart ssd_req_summary failed: ModuleNotFoundError: No module named
      'amoprof.report'; 'amoprof' is not a package
    WARNING amoprof report generation returned 1
    WARNING combined report skipped — static or interactive generation failed

Nothing in the suite caught it. Every test here imports the package normally,
which is the one mode where those imports work. This file tests the other
mode two ways, and they cover different things:

  * the simulation execs the module's LEADING import block with sys.path[0]
    set as the interpreter sets it for a script. It catches an unguarded
    import at module level, and it cannot catch one inside a function,
    because that body never runs here.
  * the static checker catches both, including the two that caused this --
    one of which was inside build_html and so invisible to any import-time
    test.

Neither alone is sufficient. The regression that prompted the file fails the
checker and passes the simulation.
"""
import ast
import pathlib
import subprocess
import sys
import tempfile
import textwrap

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_AMO = _ROOT / "amoprof" / "report" / "amoprof.py"
_RESULTS = []


def _check(name, got, want):
    ok = got == want
    _RESULTS.append((ok, name))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        print(f"        got  {got!r}\n        want {want!r}")


def main() -> int:
    print("\nScript mode is what the pipeline actually uses")
    # Reproduce it without needing matplotlib: run the module's own
    # module-level import statements with sys.path[0] set the way the
    # interpreter sets it for a script, and with the heavy third-party
    # modules stubbed. If a package-absolute import of a sibling is
    # reachable at import time, this raises exactly as the pipeline did.
    _tree = ast.parse(_AMO.read_text(encoding="utf-8"))
    _imports = [n for n in _tree.body
                if isinstance(n, (ast.Import, ast.ImportFrom, ast.Try))]
    # Keep only the leading import section: statements up to the first
    # def/class, which is where the module's imports live.
    _stop = min((i for i, n in enumerate(_tree.body)
                 if isinstance(n, (ast.FunctionDef, ast.ClassDef))),
                default=len(_tree.body))
    _head = ast.Module(body=[n for n in _tree.body[:_stop]
                             if isinstance(n, (ast.Import, ast.ImportFrom,
                                               ast.Try, ast.Assign,
                                               ast.AnnAssign, ast.Expr,
                                               ast.If))],
                       type_ignores=[])
    _check("the module has a leading import section to test", _stop > 0, True)

    _tmp = pathlib.Path(tempfile.mkdtemp(prefix="amoprof_scriptmode_"))
    try:
        # A stub for every third-party module the header pulls in, so the
        # test measures IMPORT RESOLUTION and not what is pip-installed.
        _stub_dir = _tmp / "stubs"
        _stub_dir.mkdir()
        for _m in ("matplotlib", "numpy", "pandas", "scipy", "seaborn",
                   "plotly", "requests", "yaml"):
            # A finder that fabricates any submodule of the named
            # third-party packages. A flat stub module cannot satisfy
            # `import matplotlib.pyplot` -- that needs a package -- and
            # hand-writing a package per import is a list that goes stale.
            (_stub_dir / "_stubpkgs.py").write_text(textwrap.dedent("""
                import sys, types, importlib.abc, importlib.machinery

                ROOTS = ("matplotlib", "numpy", "pandas", "scipy", "seaborn",
                         "plotly", "requests", "yaml")


                class _Any:
                    def __init__(self, name=""):
                        self._name = name

                    def __getattr__(self, k):
                        if k.startswith("__") and k.endswith("__"):
                            raise AttributeError(k)
                        return _Any(f"{self._name}.{k}")

                    def __call__(self, *a, **k):
                        return _Any(self._name + "()")

                    def __getitem__(self, k):
                        return _Any(f"{self._name}[]")

                    def __setitem__(self, k, v):
                        return None

                    def __iter__(self):
                        return iter(())

                    def __bool__(self):
                        return True

                    def __hash__(self):
                        return id(self)

                    def __eq__(self, other):
                        return False


                class _Mod(types.ModuleType):
                    __path__ = []          # makes it a package

                    def __getattr__(self, k):
                        if k.startswith("__") and k.endswith("__"):
                            raise AttributeError(k)
                        return _Any(f"{self.__name__}.{k}")


                class _Finder(importlib.abc.MetaPathFinder,
                              importlib.abc.Loader):
                    def find_spec(self, name, path=None, target=None):
                        root = name.split(".")[0]
                        if root not in ROOTS:
                            return None
                        return importlib.machinery.ModuleSpec(
                            name, self, is_package=True)

                    def create_module(self, spec):
                        return _Mod(spec.name)

                    def exec_module(self, module):
                        return None


                sys.meta_path.insert(0, _Finder())
                """).strip() + "\n")
        _runner = _tmp / "runner.py"
        _runner.write_text(textwrap.dedent(f"""
            import sys
            # Exactly what the interpreter does for a script: the script's
            # own directory first.  `amoprof` then resolves to amoprof.py.
            sys.path.insert(0, {str(_AMO.parent)!r})
            sys.path.insert(0, {str(_stub_dir)!r})
            import _stubpkgs  # installs the third-party import hook
            src = open({str(_AMO)!r}, encoding="utf-8").read()
            import ast
            tree = ast.parse(src)
            stop = min((i for i, n in enumerate(tree.body)
                        if isinstance(n, (ast.FunctionDef, ast.ClassDef))),
                       default=len(tree.body))
            head = ast.Module(body=tree.body[:stop], type_ignores=[])
            ast.fix_missing_locations(head)
            g = {{"__name__": "__main__", "__file__": {str(_AMO)!r}}}
            exec(compile(head, {str(_AMO)!r}, "exec"), g)
            print("HEAD_OK")
        """).strip() + "\n")
        _r = subprocess.run([sys.executable, str(_runner)],
                            capture_output=True, text=True)
        _check("the module-level imports resolve in script mode",
               "HEAD_OK" in _r.stdout, True)
        if "HEAD_OK" not in _r.stdout:
            print("        " + (_r.stderr or "")[-700:].replace("\n",
                                                                "\n        "))
        # Specifically amoprof: a generic "is not a package" check also
        # matched the stub's own failures and hid the real signal.
        _check("and no \"'amoprof' is not a package\" error",
               "'amoprof' is not a package" in (_r.stderr or ""), False)

        print("\nThe guard carries every kernel symbol the module uses")
        _src = _AMO.read_text(encoding="utf-8")
        _guard_start = _src.index("try:\n    from amoprof.report.metric_kernels")
        _guard_end = _src.index("\n\n", _src.index("from metric_kernels import",
                                                   _guard_start))
        _guard = _src[_guard_start:_guard_end]
        for _sym in ("resolve_latency_percentile as _k_resolve_pct",
                     "vet_device_bw_peak as _k_vet_bw",
                     "vet_queue_depth as _k_vet_qd"):
            _check(f"{_sym.split(' as ')[0]} is in the guard",
                   _guard.count(_sym), 2)      # absolute AND flat fallback
        _check("the flat fallback mirrors the absolute import",
               _guard.count("from metric_kernels import"), 1)

        print("\nThe checker that would have caught it")
        _chk = _ROOT / "scripts" / "check_script_mode_imports.py"
        _check("it ships", _chk.is_file(), True)
        _r2 = subprocess.run([sys.executable, str(_chk)],
                             capture_output=True, text=True, cwd=str(_ROOT))
        _check("and the package passes it now", _r2.returncode, 0)
        _check("having actually scanned files",
               "0 file(s) scanned" in _r2.stdout, False)

        # Put the regression back, in a copy, and require a non-zero exit.
        _bad_dir = _tmp / "bad" / "amoprof" / "report"
        _bad_dir.mkdir(parents=True)
        (_bad_dir / "amoprof.py").write_text(
            "import sys\n"
            "from amoprof.report.metric_kernels import x\n"
            "def f():\n"
            "    from amoprof.report.metric_kernels import y\n"
            "if __name__ == '__main__':\n"
            "    pass\n")
        _r3 = subprocess.run(
            [sys.executable, str(_chk), str(_bad_dir / "amoprof.py")],
            capture_output=True, text=True)
        _check("an unguarded import is reported", _r3.returncode, 1)
        _check("both the module-level and the inline one",
               _r3.stdout.count("package-absolute and unguarded"), 2)

        # A guarded import, and a file that never runs as a script, must pass.
        (_bad_dir / "ok.py").write_text(
            "try:\n"
            "    from amoprof.report.metric_kernels import x\n"
            "except ImportError:\n"
            "    from metric_kernels import x\n"
            "def f():\n"
            "    try:\n"
            "        from amoprof.report.metric_kernels import y\n"
            "    except Exception:\n"
            "        y = None\n"
            "if __name__ == '__main__':\n"
            "    pass\n")
        _r4 = subprocess.run([sys.executable, str(_chk),
                              str(_bad_dir / "ok.py")],
                             capture_output=True, text=True)
        _check("a guarded import passes", _r4.returncode, 0)
        (_bad_dir / "lib.py").write_text(
            "from amoprof.report.metric_kernels import x\n")
        _r5 = subprocess.run([sys.executable, str(_chk),
                              str(_bad_dir / "lib.py")],
                             capture_output=True, text=True)
        _check("a module that never runs as a script is not flagged",
               _r5.returncode, 0)
    finally:
        import shutil
        shutil.rmtree(_tmp, ignore_errors=True)

    bad = [n for ok, n in _RESULTS if not ok]
    print(f"\n{len(_RESULTS) - len(bad)}/{len(_RESULTS)} passed"
          + (f" — FAILED: {', '.join(bad)}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
