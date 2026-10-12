#!/usr/bin/env python3
"""Flag package-absolute imports that break when a module is run as a script.

    python3 scripts/check_script_mode_imports.py [file ...]

amoprof/report/amoprof.py is both a module and a program: the pipeline runs
`python .../amoprof/report/amoprof.py`. In that mode sys.path[0] is
.../amoprof/report, so the name `amoprof` resolves to amoprof.py -- the file
itself -- and `from amoprof.report.metric_kernels import X` raises

    ModuleNotFoundError: No module named 'amoprof.report';
    'amoprof' is not a package

The file says so, at the top, next to the guard every such import is supposed
to go through: "Every import of the registry must therefore go through this
guard -- never inline at the call site." Two imports added in v1.71.0 and
v1.72.0 went inline anyway. One of them sat in build_html, so it did not fail
a chart -- it aborted the whole static report, and with it the combined one.

The rule checked here: in a module that can run as a script (it has an
`if __name__ == "__main__"` block), a `from amoprof...` or `import amoprof...`
statement must be inside a try with an except that catches ImportError or
Exception. Module-level guarded imports are fine; so are imports in files that
are never executed directly.
"""
import ast
import pathlib
import sys

_PKG = "amoprof"


def _is_guarded(node, ancestors) -> bool:
    """Is this import inside a try whose handler catches the import failing?"""
    for anc in ancestors:
        if not isinstance(anc, ast.Try):
            continue
        # The import has to be in the try body, not in a handler or else.
        in_body = any(_contains(stmt, node) for stmt in anc.body)
        if not in_body:
            continue
        for h in anc.handlers:
            if h.type is None:
                return True                      # bare except
            names = []
            if isinstance(h.type, ast.Name):
                names = [h.type.id]
            elif isinstance(h.type, ast.Tuple):
                names = [e.id for e in h.type.elts if isinstance(e, ast.Name)]
            if {"ImportError", "ModuleNotFoundError", "Exception",
                    "BaseException"} & set(names):
                return True
    return False


def _contains(stmt, node) -> bool:
    return any(n is node for n in ast.walk(stmt))


def scan(path: str):
    src = pathlib.Path(path).read_text(encoding="utf-8")
    tree = ast.parse(src)

    runs_as_script = any(
        isinstance(n, ast.If) and isinstance(n.test, ast.Compare)
        and isinstance(n.test.left, ast.Name) and n.test.left.id == "__name__"
        for n in tree.body)
    if not runs_as_script:
        return []

    # Map every node to its ancestor chain, so a nested import can be tested.
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node

    def chain(n):
        out = []
        while n in parents:
            n = parents[n]
            out.append(n)
        return out

    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if not (mod == _PKG or mod.startswith(_PKG + ".")):
                continue
        elif isinstance(node, ast.Import):
            if not any(a.name == _PKG or a.name.startswith(_PKG + ".")
                       for a in node.names):
                continue
        else:
            continue
        if not _is_guarded(node, chain(node)):
            mod = getattr(node, "module", None) or ",".join(
                a.name for a in getattr(node, "names", []))
            bad.append((node.lineno, mod))
    return bad


_targets = sys.argv[1:]
if not _targets:
    _pkg_dir = pathlib.Path(__file__).resolve().parent.parent / _PKG
    _targets = sorted(str(p) for p in _pkg_dir.rglob("*.py"))
if not _targets:
    print("  nothing to scan: no .py files found", file=sys.stderr)
    sys.exit(2)

rc = 0
for t in _targets:
    for ln, mod in sorted(scan(t)):
        print(f"  {t}:{ln}  'from {mod} import ...' is package-absolute and "
              f"unguarded, in a module that also runs as a script — wrap it "
              f"in try/except ImportError with a flat-layout fallback, or "
              f"move it to the module-level guard")
        rc = 1
print(f"  none found ({len(_targets)} file(s) scanned)" if rc == 0 else "")
sys.exit(rc)
