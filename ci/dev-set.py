#!/usr/bin/env python3
"""Assembles a set of Cognos packages, every component for ubuntu24 and ol10, plus set.json.

Usage: ci/dev-set.py --version <version> --pipeline <id> [--results <file>] [--previous <dir>] [--extra <os>=<file>]
                     --out <dir>
       ci/dev-set.py --version <version> --pipeline <id> --complete --extra ol10=<grpc rpm> --out <dir>   (a release)

Packages are taken from <component dir>/build/artifacts/<os>/ (the artifacts of the pipeline's build jobs) and
grouped by package name: cognos-cxl and cognos-cxl-mock are separate entries ("cxl", "cxl-mock").

Dev set (--results, --previous): --results is a JSON object {"<component>/<os>": "passed" | "failed"} for every
component and OS this pipeline built and tested. For each component and OS:
  - passed:              this pipeline's packages;
  - failed:              the previous set's packages (or none), noted as failed;
  - not in --results:    not built in this pipeline: the previous set's packages.
If core or mgmt-fw failed on any OS, no set is made (exit 2): every other component depends on them.

--extra <os>=<file>: a package not built in this repository, added for that OS: cognos-grpc for ol10 (the pinned
version from Nexus), so that a set needs nothing but GitLab to deploy. A dev set without --extra keeps the previous
set's cognos-grpc.

Release (--complete): every component and OS must have packages built in this pipeline, and ol10 its cognos-grpc
(--extra), else exit 1.

The result is <out>/set.json and <out>/<os>/<package files>. set.json lists every package file with its component,
OS, version, sha256 and the pipeline that built it, and per component and OS what happened in this pipeline.

Run from the repository root. Needs only the Python standard library.
"""

import argparse
import datetime
import hashlib
import json
import pathlib
import re
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
# Package name (without -dev/-devel) -> set component. cxl's two variants are separate components.
PACKAGE_COMPONENT = {
    "cognos-core": "core", "cognos-mgmt-fw": "mgmt-fw", "cognos-node": "node", "cognos-ras": "ras",
    "cognos-slat": "slat", "cognos-me": "me", "cognos-cxl": "cxl", "cognos-cxl-mock": "cxl-mock",
    "cognos-app": "sapp", "cognos-grpc": "grpc",
}
COMPONENTS = ["core", "mgmt-fw", "node", "ras", "slat", "me", "cxl", "cxl-mock", "sapp"]
# Packages not built in this repository (--extra), and the OSes that need them.
EXTRAS = {"grpc": ("ol10",)}
UPSTREAMS = ("core", "mgmt-fw")
OSES = ("ubuntu24", "ol10")
SUFFIX = {"ubuntu24": ".deb", "ol10": ".rpm"}


def package_component(file_name):
    """cognos-cxl-mock-dev_1.7.0~dev.3-ubuntu24.04_amd64.deb -> cxl-mock"""
    m = re.match(r"^([a-z0-9-]+?)(_|-[0-9])", file_name)
    name = re.sub(r"-(dev|devel)$", "", m.group(1)) if m else ""
    return PACKAGE_COMPONENT.get(name)


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def built_packages(os_name):
    """{component: [paths]} of the packages under every component's build/artifacts/<os>/."""
    found = {}
    for component_dir in COMPONENT_DIRS.values():
        for path in sorted(pathlib.Path(component_dir, "build", "artifacts", os_name).glob("*" + SUFFIX[os_name])):
            component = package_component(path.name)
            if component:
                found.setdefault(component, []).append(path)
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--version", required=True, help="the version of the packages built in this pipeline")
    parser.add_argument("--pipeline", required=True, type=int, help="this pipeline's id")
    parser.add_argument("--results", type=pathlib.Path, help="JSON: {\"<component>/<os>\": \"passed\"|\"failed\"}")
    parser.add_argument("--previous", type=pathlib.Path, help="directory of the previous set (may not exist)")
    parser.add_argument("--complete", action="store_true", help="a release: every component must be built here")
    parser.add_argument("--extra", action="append", default=[], metavar="OS=FILE",
                        help="a package not built here, e.g. ol10=cognos-grpc-1.59.2-1.el10.x86_64.rpm")
    parser.add_argument("--out", required=True, type=pathlib.Path)
    args = parser.parse_args()

    results = json.loads(args.results.read_text()) if args.results else {}
    extras = {}
    for item in args.extra:
        os_name, _, path = item.partition("=")
        path = pathlib.Path(path)
        component = package_component(path.name)
        if os_name not in OSES or component not in EXTRAS or os_name not in EXTRAS[component] or not path.is_file():
            sys.exit(f"dev-set: --extra {item}: not one of {EXTRAS}, or no such file")
        extras.setdefault((component, os_name), []).append(path)
    failed_upstreams = sorted(k for k, v in results.items() if v != "passed" and k.split("/")[0] in UPSTREAMS)
    if failed_upstreams:
        print(f"dev-set: {', '.join(failed_upstreams)} failed. Every other component depends on core and mgmt-fw, "
              "so no dev set is made; the previous set stays the newest.", file=sys.stderr)
        sys.exit(2)

    previous = []
    previous_json = args.previous / "set.json" if args.previous else None
    if not args.complete and previous_json and previous_json.is_file():
        previous_set = json.loads(previous_json.read_text())
        # Sets are made in pipeline order: an older pipeline must not replace a newer set.
        # The same pipeline may (a rerun after a retried job).
        if previous_set["pipeline"] > args.pipeline:
            sys.exit(f"dev-set: the newest set is from pipeline {previous_set['pipeline']}, "
                     f"newer than this pipeline ({args.pipeline}); not replacing it.")
        previous = previous_set["packages"]
        print(f"Previous set: {previous_set['version']} (pipeline {previous_set['pipeline']})")
    elif not args.complete:
        print("No previous set.")

    packages, outcomes, missing = [], {}, []
    for os_name in OSES:
        (args.out / os_name).mkdir(parents=True, exist_ok=True)
        built = built_packages(os_name)
        for component in COMPONENTS + [c for c, oses in EXTRAS.items() if os_name in oses]:
            key = f"{component}/{os_name}"
            if component in EXTRAS:
                paths = extras.get((component, os_name), [])
                result = "passed" if paths else None
            else:
                paths = built.get(component)
                result = "passed" if args.complete else results.get(key)
            if result == "passed" and paths:
                for path in paths:
                    shutil.copy2(path, args.out / os_name / path.name)
                    version = args.version
                    if component in EXTRAS:  # its own version, from the file name
                        version = re.search(r"-([0-9]+\.[0-9]+\.[0-9]+)", path.name).group(1)
                    packages.append({"component": component, "os": os_name, "file": f"{os_name}/{path.name}",
                                     "version": version, "pipeline": args.pipeline})
                outcome = "added in this pipeline" if component in EXTRAS else "built in this pipeline"
            else:
                kept = [p for p in previous if p["component"] == component and p["os"] == os_name]
                for package in kept:
                    shutil.copy2(args.previous / package["file"], args.out / package["file"])
                    packages.append({k: package[k] for k in ("component", "os", "file", "version", "pipeline")})
                since = f"kept from pipeline {kept[0]['pipeline']}" if kept else "missing"
                if result == "passed":
                    outcome = f"passed but produced no packages; {since}"
                elif result:
                    outcome = f"failed in this pipeline; {since}"
                elif component in EXTRAS:
                    outcome = f"not added in this pipeline; {since}"
                else:
                    outcome = f"not built in this pipeline; {since}"
                if not kept:
                    missing.append(key)
            outcomes[key] = outcome
            print(f"  {component:9} {os_name:9} {outcome}")

    if args.complete and missing:
        sys.exit("dev-set: a release needs every component built in this pipeline (and cognos-grpc for ol10, --extra); "
                 "missing: " + ", ".join(missing))
    if missing:
        print("WARNING: no packages for " + ", ".join(missing))

    for package in packages:
        package["sha256"] = sha256(args.out / package["file"])
    (args.out / "set.json").write_text(json.dumps({
        "version": args.version,
        "pipeline": args.pipeline,
        "created": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "outcomes": outcomes,
        "packages": packages,
    }, indent=2) + "\n")
    print(f"Set {args.version}: {len(packages)} package files in {args.out}")


if __name__ == "__main__":
    main()
