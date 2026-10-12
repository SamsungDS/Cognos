#!/usr/bin/env python3
"""Reversion testing: revert each fix in turn and require the suite to fail.

    python3 scripts/mutate.py mutations.json

A mutation that the suite still passes is either an untested fix or an
assertion satisfied by something other than the behaviour it names -- a
comment, a cross-reference in prose, a string that survives the change.
Both have happened repeatedly in this repo, which is why this exists.

SAFETY.  Earlier runs of this as an ad-hoc script edited sources in place and
restored them in a `finally`.  A SIGKILL (or an interrupted tool call) skips
that, and the tree was left holding a mutation -- which then showed up as
four unrelated test failures an hour later, in a file nobody had touched.

So: every target is committed-clean-checked and backed up to a marker
directory before anything is edited, the marker is removed only after every
file is restored, and a run that finds a leftover marker refuses to start and
tells you how to recover.  Restoration also runs on SIGINT and SIGTERM.
"""
import json
import pathlib
import shutil
import signal
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
MARKER = ROOT / ".mutate-in-progress"


def _restore(files):
    for rel, src in files.items():
        shutil.copy2(src, ROOT / rel)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    spec = json.loads(pathlib.Path(sys.argv[1]).read_text())
    tests = spec["tests"]
    muts = spec["mutations"]

    if MARKER.exists():
        print(f"refusing to start: {MARKER} exists, so a previous run was "
              f"interrupted and may have left a mutation in the tree.\n"
              f"Restore from the backups in that directory, or "
              f"`git checkout --` the affected files, then delete it.",
              file=sys.stderr)
        return 2

    targets = sorted({m["file"] for m in muts})
    MARKER.mkdir()
    backups = {}
    try:
        for rel in targets:
            dst = MARKER / rel.replace("/", "__")
            shutil.copy2(ROOT / rel, dst)
            backups[rel] = dst

        def _bail(signum, _frame):
            _restore(backups)
            shutil.rmtree(MARKER, ignore_errors=True)
            print(f"\ninterrupted ({signum}); sources restored",
                  file=sys.stderr)
            sys.exit(130)

        for _s in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            try:
                signal.signal(_s, _bail)
            except (OSError, ValueError):
                pass

        def run():
            for t in tests:
                r = subprocess.run([sys.executable, t], cwd=ROOT,
                                   capture_output=True, text=True)
                if r.returncode != 0:
                    return r.returncode
            return 0

        if run() != 0:
            print("baseline FAILS -- fix that before reversion testing",
                  file=sys.stderr)
            return 2
        print(f"baseline passes ({len(tests)} suite(s))")

        caught = escaped = 0
        for m in muts:
            rel, old, new = m["file"], m["old"], m["new"]
            want = m.get("count", 1)
            label = m["label"]
            orig = (ROOT / rel).read_text()
            if orig.count(old) != want:
                print(f"  SKIP     {label}  "
                      f"(matched {orig.count(old)}x, expected {want}x)")
                escaped += 1
                continue
            (ROOT / rel).write_text(orig.replace(old, new))
            try:
                rc = run()
            finally:
                (ROOT / rel).write_text(orig)
            if rc != 0:
                print(f"  caught   {label}")
                caught += 1
            else:
                print(f"  ESCAPED  {label}")
                escaped += 1
        print(f"\n{caught}/{len(muts)} reversions caught"
              + (f", {escaped} NOT" if escaped else ""))
        return 1 if escaped else 0
    finally:
        _restore(backups)
        shutil.rmtree(MARKER, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
