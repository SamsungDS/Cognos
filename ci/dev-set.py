#!/usr/bin/env python3
"""Assembles a complete dev set: the packages of every component for ubuntu24 and ol10, plus set.json.

Usage: ci/dev-set.py --version <version> --pipeline <id> [--previous <dir>] --out <dir>

- A component built in this pipeline: its packages from <component dir>/build/artifacts/<os>/
  (the artifacts of this pipeline's build jobs).
- Every other component: its packages from the previous set (--previous: a directory holding a set.json
  and the files it lists), unchanged.

The result is <out>/set.json and <out>/<os>/<package files>. set.json lists, for each package file, its
component, OS, version, sha256 and the pipeline that built it.

Run from the repository root. Needs only the Python standard library.
"""

import argparse
import datetime
import hashlib
import json
import pathlib
import shutil
import sys

COMPONENT_DIRS = {
    "core": "components/core",
    "mgmt-fw": "components/mgmt-fw",
    "node": "components/node",
    "ras": "components/ras",
    "slat": "components/slat",
    "me": "components/me",
    "cxl": "components/cxl",
    "sapp": "apps/sapp",
}
OSES = ("ubuntu24", "ol10")
PACKAGE_SUFFIX = {"ubuntu24": ".deb", "ol10": ".rpm"}


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--version", required=True, help="the version of the packages built in this pipeline")
    parser.add_argument("--pipeline", required=True, type=int, help="this pipeline's id")
    parser.add_argument("--previous", type=pathlib.Path, help="directory of the previous set (may not exist)")
    parser.add_argument("--out", required=True, type=pathlib.Path)
    args = parser.parse_args()

    previous = []
    previous_json = args.previous / "set.json" if args.previous else None
    if previous_json and previous_json.is_file():
        previous_set = json.loads(previous_json.read_text())
        # Sets must be created in pipeline order, or an older pipeline would replace a newer set.
        if previous_set["pipeline"] > args.pipeline:
            sys.exit(f"dev-set: the newest set is from pipeline {previous_set['pipeline']}, "
                     f"newer than this pipeline ({args.pipeline}); not replacing it.")
        previous = previous_set["packages"]
        print(f"Previous set: {previous_set['version']} (pipeline {previous_set['pipeline']})")
    else:
        print("No previous set: this set holds only the packages built in this pipeline.")

    packages = []
    for os_name in OSES:
        (args.out / os_name).mkdir(parents=True, exist_ok=True)
        for component, component_dir in COMPONENT_DIRS.items():
            built = sorted(pathlib.Path(component_dir, "build", "artifacts", os_name).glob("*" + PACKAGE_SUFFIX[os_name]))
            if built:
                for path in built:
                    shutil.copy2(path, args.out / os_name / path.name)
                    packages.append({"component": component, "os": os_name, "file": f"{os_name}/{path.name}",
                                     "version": args.version, "pipeline": args.pipeline})
                source = "built in this pipeline"
            else:
                kept = [p for p in previous if p["component"] == component and p["os"] == os_name]
                for package in kept:
                    shutil.copy2(args.previous / package["file"], args.out / package["file"])
                    packages.append({k: package[k] for k in ("component", "os", "file", "version", "pipeline")})
                source = f"kept from pipeline {kept[0]['pipeline']}" if kept else "MISSING"
            print(f"  {component:8} {os_name:9} {source}")

    for package in packages:
        package["sha256"] = sha256(args.out / package["file"])

    missing = sorted({(c, o) for c in COMPONENT_DIRS for o in OSES}
                     - {(p["component"], p["os"]) for p in packages})
    if missing:
        print("WARNING: no packages for " + ", ".join(f"{c} ({o})" for c, o in missing))

    (args.out / "set.json").write_text(json.dumps({
        "version": args.version,
        "pipeline": args.pipeline,
        "created": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "packages": packages,
    }, indent=2) + "\n")
    print(f"Dev set {args.version}: {len(packages)} package files in {args.out}")


if __name__ == "__main__":
    main()
