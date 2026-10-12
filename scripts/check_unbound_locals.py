"""Find locals read on a line before their first assignment, per function.

Approximate but targeted at the shape that just crashed: a module-level-of-
function temporary assigned once, far below a conditional that reads it.
Loads inside loops, comprehensions, nested functions and except handlers are
excluded, since those can legitimately run after a later assignment.
"""
import ast, sys

def scan(path):
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    out = []
    for fn in [n for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
        params = set()
        a = fn.args
        for grp in (a.posonlyargs, a.args, a.kwonlyargs):
            params |= {x.arg for x in grp}
        if a.vararg: params.add(a.vararg.arg)
        if a.kwarg: params.add(a.kwarg.arg)
        globals_ = set()
        first_store, loads = {}, {}
        # Statements directly in the function body, in order; skip anything
        # nested inside a loop / with / try-handler / inner def.
        def walk(node, in_loop=False, in_nested=False):
            for ch in ast.iter_child_nodes(node):
                nl = in_loop or isinstance(ch, (ast.For, ast.While,
                                                ast.AsyncFor, ast.comprehension))
                nn = in_nested or isinstance(ch, (ast.FunctionDef, ast.Lambda,
                                                  ast.AsyncFunctionDef,
                                                  ast.ExceptHandler,
                                                  ast.ListComp, ast.SetComp,
                                                  ast.DictComp, ast.GeneratorExp))
                if isinstance(ch, (ast.Global, ast.Nonlocal)):
                    globals_.update(ch.names)
                # import x as y, def f, class C all BIND the name.
                if in_nested:
                    walk(ch, nl, True)
                    continue
                if isinstance(ch, (ast.Import, ast.ImportFrom)):
                    for al in ch.names:
                        nm = al.asname or al.name.split(".")[0]
                        if nm not in first_store or ch.lineno < first_store[nm]:
                            first_store[nm] = ch.lineno
                if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef,
                                   ast.ClassDef)):
                    if ch.name not in first_store or ch.lineno < first_store[ch.name]:
                        first_store[ch.name] = ch.lineno
                if isinstance(ch, ast.Name):
                    if isinstance(ch.ctx, ast.Store):
                        if ch.id not in first_store or ch.lineno < first_store[ch.id]:
                            first_store[ch.id] = ch.lineno
                    elif isinstance(ch.ctx, ast.Load) and not nl and not nn:
                        loads.setdefault(ch.id, []).append(ch.lineno)
                walk(ch, nl, nn)
        walk(fn)
        for name, lns in loads.items():
            if name in params or name in globals_ or name not in first_store:
                continue
            st = first_store[name]
            bad = [l for l in lns if l < st]
            if bad:
                out.append((fn.name, name, min(bad), st))
    return out

# With no arguments this scanned sys.argv[1:] -- nothing at all -- and then
# printed "none found" and exited 0.  A clean run that inspected zero files is
# indistinguishable from a clean run that inspected the package, and it was
# trusted as the latter.  Default to every module in the package, and say how
# many files were read so an empty scan cannot pass for a pass.
import pathlib as _pl

_targets = sys.argv[1:]
if not _targets:
    _pkg = _pl.Path(__file__).resolve().parent.parent / "amoprof"
    _targets = sorted(str(p) for p in _pkg.rglob("*.py"))
if not _targets:
    print("  nothing to scan: no .py files found", file=sys.stderr)
    sys.exit(2)

rc = 0
for p in _targets:
    for fname, name, load_ln, store_ln in sorted(scan(p), key=lambda r: r[2]):
        print(f"  {p}:{load_ln}  {name}  read before its first assignment "
              f"at line {store_ln}  (in {fname})")
        rc = 1
print(f"  none found ({len(_targets)} file(s) scanned)" if rc == 0 else "")
# (exit moved to the end: a second scan follows)


# ---------------------------------------------------------------------------
# A second, different fault, found three times in one afternoon: a local or a
# parameter that shadows a module-level import, in a function that then uses
# the NAME as a module.
#
#   import html
#   def build_html(...):
#       _esc = html.escape          # UnboundLocalError: html is local here
#       ...
#       html = f"<!DOCTYPE html>"   # ...because of this, 600 lines below
#
#   import html as _html
#   def outer():
#       def _group(_html):          # parameter shadows the alias
#           _html.unescape(...)     # AttributeError: str has no unescape
#
# Neither shape is a read-before-assignment, so the scan above cannot see
# them, and the second is not even an error until that line runs.
def scan_shadowed_imports(path):
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    mods = set()
    for n in tree.body:
        if isinstance(n, ast.Import):
            for al in n.names:
                mods.add(al.asname or al.name.split(".")[0])
        elif isinstance(n, ast.ImportFrom) and n.module and not n.names[0].name == "*":
            pass  # `from x import y` binds y, not a module; attribute use is fine
    out = []
    for fn in [n for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
        shadow = {}
        a = fn.args
        for grp in (a.posonlyargs, a.args, a.kwonlyargs):
            for x in grp:
                if x.arg in mods:
                    shadow.setdefault(x.arg, ("parameter", fn.lineno))
        for n in ast.walk(fn):
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store) \
                    and n.id in mods:
                shadow.setdefault(n.id, ("assignment", n.lineno))
        if not shadow:
            continue
        # Report only where the shadowed name is then used as a module, which
        # is what actually breaks.  A local that merely reuses the name and
        # never dots into it is legal and common.
        for n in ast.walk(fn):
            if not (isinstance(n, ast.Attribute)
                    and isinstance(n.value, ast.Name)
                    and n.value.id in shadow):
                continue
            # Only flag an attribute a string cannot provide.  These shadows
            # are almost always by a built HTML string, so `html.find(...)` is
            # correct code -- str.find exists -- while `html.escape(...)` and
            # `_html.unescape(...)` cannot work and are the real faults.
            #
            # Limits worth knowing: a shadow by something other than a str is
            # not judged (there is no type information here), and an attribute
            # that exists on str but means something different on the module
            # is missed.  The check is deliberately narrow rather than noisy.
            if getattr(str, n.attr, None) is not None:
                continue
            kind, at = shadow[n.value.id]
            out.append((fn.name, n.value.id, n.lineno, kind, at, n.attr))
    return out


rc2 = 0
for p in _targets:
    for fname, name, use_ln, kind, at, attr in sorted(
            set(scan_shadowed_imports(p)), key=lambda r: r[2]):
        print(f"  {p}:{use_ln}  {name}.{attr}  uses an imported module whose "
              f"name is shadowed by a {kind} at line {at}  (in {fname})")
        rc2 = 1
if rc2 == 0:
    print(f"  no shadowed-import use found ({len(_targets)} file(s) scanned)")
sys.exit(rc or rc2)
