#!/usr/bin/env python3
"""Puts the Cognos packages for one OS into deploy/artifacts/SVK/, where playbooks/deploy_cognos.yml installs them from.

Usage: deploy/scripts/fetch-packages.py --os ubuntu24|ol10 [--mock] [--only <components>] [--with-dev] <source>

<source> is one of:
  --release vX.Y.Z       a release (kept permanently)
  --set latest           the newest dev set (built on main)
  --set <pipeline id>    the dev set of that main pipeline (kept for 10 days)
  --pipeline <id>        the packages built by that pipeline, for example a merge request's; components it did
                         not build come from the newest dev set
  --local                the packages of your own ./build.sh, from build/artifacts/<os>/

  --mock                 cognos-cxl-mock instead of cognos-cxl
  --only <components>    only these, comma-separated: core,mgmt-fw,node,ras,slat,me,cxl,sapp
  --with-dev             also the -dev/-devel packages (for building against them)

Existing cognos-* packages in the destination are removed first, so the playbooks install exactly this set. Without
--only, ol10 also gets cognos-grpc, which is not built in this repository: it comes from Nexus at GRPC_VERSION.

Environment (defaults in brackets):
  COGNOS_GITLAB_URL   [https://cxl-gitlab.ssi.samsung.com]
  COGNOS_PROJECT      [dfs/svk/cognos]
  GITLAB_TOKEN        only needed if the project or its pipelines are not public
  NEXUS_URL           [http://ssg-nexus.msl.lab:8081]
  ARTIFACTS_DIR       [deploy/artifacts/SVK]

Needs only Python 3 and its standard library.
"""

import argparse
import hashlib
import io
import json
import os
import pathlib
import re
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile

GRPC_VERSION = "1.59.2"

ROOT = pathlib.Path(__file__).resolve().parents[2]
GITLAB = os.environ.get("COGNOS_GITLAB_URL", "https://cxl-gitlab.ssi.samsung.com")
API = f"{GITLAB}/api/v4/projects/{urllib.parse.quote(os.environ.get('COGNOS_PROJECT', 'dfs/svk/cognos'), safe='')}"
NEXUS = os.environ.get("NEXUS_URL", "http://ssg-nexus.msl.lab:8081")
DEST = pathlib.Path(os.environ.get("ARTIFACTS_DIR", ROOT / "deploy" / "artifacts" / "SVK"))
SUFFIX = {"ubuntu24": ".deb", "ol10": ".rpm"}
DEV_SET_JOB = "publish dev set"
PACKAGE_COMPONENT = {
    "cognos-core": "core", "cognos-mgmt-fw": "mgmt-fw", "cognos-node": "node", "cognos-ras": "ras",
    "cognos-slat": "slat", "cognos-me": "me", "cognos-cxl": "cxl", "cognos-cxl-mock": "cxl", "cognos-app": "sapp",
}


def die(message):
    sys.exit(f"fetch-packages: {message}")


def get(url, missing_ok=False):
    """GET url; bytes, or None for 404 when missing_ok."""
    headers = {"PRIVATE-TOKEN": os.environ["GITLAB_TOKEN"]} if os.environ.get("GITLAB_TOKEN") and url.startswith(
        GITLAB) else {}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=600) as response:
            return response.read()
    except urllib.error.HTTPError as e:
        if e.code == 404 and missing_ok:
            return None
        die(f"{url.split('?')[0]}: HTTP {e.code}")
    except urllib.error.URLError as e:
        die(f"{url.split('?')[0]}: {e.reason}")


def get_json(url, missing_ok=False):
    data = get(url, missing_ok)
    return json.loads(data) if data is not None else None


def parse(file_name):
    """(package name, component) of a package file name, e.g. cognos-core-dev_1.7.0~dev.3-ubuntu24.04_amd64.deb."""
    m = re.match(r"^([a-z0-9-]+?)(_|-[0-9])", file_name)
    name = m.group(1) if m else ""
    return name, PACKAGE_COMPONENT.get(re.sub(r"-(dev|devel)$", "", name))


def wanted(file_name, args):
    name, component = parse(file_name)
    if not component or not file_name.endswith(SUFFIX[args.os]):
        return False
    if name.endswith(("-dev", "-devel")) and not args.with_dev:
        return False
    if component == "cxl" and name.startswith("cognos-cxl-mock") != args.mock:
        return False
    return not args.only or component in args.only


def job_id(pipeline, name):
    jobs = get_json(f"{API}/pipelines/{pipeline}/jobs?per_page=100&scope[]=success")
    return next((j["id"] for j in jobs if j["name"] == name), None)


def newest_dev_set_job():
    """The job id of the newest dev set: the newest successful "publish dev set" on main whose artifacts still exist.

    Searched pipeline by pipeline, newest first, whatever the pipeline's own status: a set published by a pipeline
    that failed elsewhere (for example a Sonar scan) is still the newest set.
    """
    for pipeline in get_json(f"{API}/pipelines?ref=main&per_page=50"):
        job = job_id(pipeline["id"], DEV_SET_JOB)
        if job and get(f"{API}/jobs/{job}/artifacts/dev-set/set.json", missing_ok=True) is not None:
            return job
    return None


def from_set(set_url, file_url, args):
    """Packages of a set (dev set or release): {file name: bytes}, checked against set.json."""
    the_set = json.loads(get(set_url))
    print(f"Set {the_set['version']} (pipeline {the_set['pipeline']}, {the_set['created']})")
    for key, outcome in sorted(the_set.get("outcomes", {}).items()):
        if key.endswith("/" + args.os) and outcome != "built in this pipeline":
            print(f"  note: {key}: {outcome}")
    files = {}
    for package in the_set["packages"]:
        name = pathlib.PurePath(package["file"]).name
        if package["os"] == args.os and wanted(name, args):
            data = get(file_url(package["file"]))
            if hashlib.sha256(data).hexdigest() != package["sha256"]:
                die(f"checksum mismatch: {name}")
            files[name] = data
    print(f"  {len(files)} files, checksums OK")
    return files


def from_dev_set(which, args):
    job = newest_dev_set_job() if which == "latest" else job_id(which, DEV_SET_JOB)
    if not job:
        return None
    base = f"{API}/jobs/{job}/artifacts/dev-set"
    return from_set(f"{base}/set.json", lambda f: f"{base}/{urllib.parse.quote(f)}", args)


def from_release(tag, args):
    if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", tag):
        die("--release needs a tag vX.Y.Z")
    base = f"{API}/packages/generic/cognos/{tag[1:]}"
    if get(f"{base}/set.json", missing_ok=True) is None:
        die(f"release {tag} not found in the package registry")
    return from_set(f"{base}/set.json", lambda f: f"{base}/{urllib.parse.quote(pathlib.PurePath(f).name)}", args)


def from_pipeline(pipeline, args):
    """Packages of a pipeline's build jobs: {file name: bytes}."""
    variant = "mock" if args.mock else "release"
    jobs = get_json(f"{API}/pipelines/{pipeline}/jobs?per_page=100&scope[]=success")
    files = {}
    for job in jobs:
        name = job["name"]
        if name.startswith("build ") and " image" not in name and (
                name.endswith(f"[{args.os}]") or name.endswith(f"[{args.os}, {variant}]")):
            print(f"  pipeline {pipeline}: {name}")
            with zipfile.ZipFile(io.BytesIO(get(f"{API}/jobs/{job['id']}/artifacts"))) as z:
                for member in z.namelist():
                    file_name = pathlib.PurePath(member).name
                    if wanted(file_name, args):
                        files[file_name] = z.read(member)
    if not files:
        die(f"pipeline {pipeline} has no successful build jobs for {args.os}")
    return files


def merge(base, overlay):
    """base, with every package of overlay replacing the base package of the same name."""
    names = {parse(f)[0] for f in overlay}
    merged = {f: d for f, d in base.items() if parse(f)[0] not in names}
    merged.update(overlay)
    return merged


def grpc(args):
    url = (f"{NEXUS}/service/rest/v1/search/assets?repository=svk_yum_ol10&name=cognos-grpc&version={GRPC_VERSION}")
    items = get_json(url)["items"]
    rpm = next((a["downloadUrl"] for a in items if a["downloadUrl"].endswith(".rpm")), None)
    if not rpm:
        die(f"cognos-grpc {GRPC_VERSION} not found in Nexus (svk_yum_ol10)")
    print(f"cognos-grpc {GRPC_VERSION} from Nexus")
    return {rpm.rsplit("/", 1)[1]: get(rpm)}


def main():
    parser = argparse.ArgumentParser(usage=argparse.SUPPRESS, description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--os", required=True, choices=SUFFIX)
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--only", type=lambda s: set(s.split(",")), default=set())
    parser.add_argument("--with-dev", action="store_true")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--release")
    source.add_argument("--set", dest="dev_set")
    source.add_argument("--pipeline")
    source.add_argument("--local", action="store_true")
    args = parser.parse_args()
    unknown = args.only - set(PACKAGE_COMPONENT.values())
    if unknown:
        die(f"unknown components: {', '.join(sorted(unknown))}")

    if args.release:
        files = from_release(args.release, args)
    elif args.dev_set:
        files = from_dev_set(args.dev_set, args)
        if files is None:
            die(f"no dev set {'available' if args.dev_set == 'latest' else 'for pipeline ' + args.dev_set}"
                " (dev sets are kept for 10 days)")
    elif args.pipeline:
        print(f"Components not built in pipeline {args.pipeline} come from the newest dev set.")
        base = from_dev_set("latest", args)
        if base is None:
            print("WARNING: no dev set available; only the pipeline's packages are used.")
        files = merge(base or {}, from_pipeline(args.pipeline, args))
    else:
        local = ROOT / "build" / "artifacts" / args.os
        files = {p.name: p.read_bytes() for p in sorted(local.glob("*" + SUFFIX[args.os])) if wanted(p.name, args)}
        if not files:
            die(f"no packages in build/artifacts/{args.os}; run ./build.sh --os {args.os} first")

    found = {parse(f)[1] for f in files}
    expected = args.only or set(PACKAGE_COMPONENT.values())
    if expected - found:
        print("WARNING: no packages for " + ", ".join(sorted(expected - found)))
    if args.os == "ol10" and not args.only:
        files.update(grpc(args))

    DEST.mkdir(parents=True, exist_ok=True)
    for old in sorted(DEST.glob("cognos-*" + SUFFIX[args.os])):
        print(f"  removed old {old.name}")
        old.unlink()
    for name, data in sorted(files.items()):
        (DEST / name).write_bytes(data)
    print(f"Packages in {DEST}:")
    for name in sorted(files):
        print(f"  {name}")


if __name__ == "__main__":
    main()
