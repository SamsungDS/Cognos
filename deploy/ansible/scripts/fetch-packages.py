#!/usr/bin/env python3
"""Puts the Cognos packages for one OS into deploy/ansible/artifacts/SVK/, where playbooks/deploy_cognos.yml installs them from.

Usage: deploy/ansible/scripts/fetch-packages.py --os ubuntu24|ol10 [--mock] [--only <components>] [--with-dev] <source>

<source> is one of:
  --release vX.Y.Z       a release (kept permanently)
  --set latest           the newest dev set (built on main)
  --set <pipeline id>    the dev set of that main pipeline (kept for 10 days)
  --pipeline <id>        the packages built by that pipeline, for example a merge request's; components it did
                         not build come from the newest dev set
  --local                the packages of your own ./build.sh, from build/artifacts/<os>/
  --grpc                 only cognos-grpc for ol10, from Nexus at GRPC_VERSION (needs the lab network; the
                         pipeline uses it to put cognos-grpc into dev sets and releases)

  --mock                 cognos-cxl-mock instead of cognos-cxl
  --only <components>    only these, comma-separated: core,mgmt-fw,node,ras,slat,me,cxl,sapp
  --with-dev             also the -dev/-devel packages (for building against them)

Existing cognos-* packages in the destination are removed first, so the playbooks install exactly this set.
Everything comes from GitLab: for ol10, dev sets and releases include cognos-grpc (not built in this repository; the
pipeline adds the pinned version). If the packages have none, this says so; --grpc downloads it separately.

Environment (defaults in brackets):
  COGNOS_GITLAB_URL   the GitLab that builds Cognos [in CI: CI_SERVER_URL]
  COGNOS_PROJECT      its project path [in CI: CI_PROJECT_PATH]
  GITLAB_TOKEN        only needed if the project or its pipelines are not public
  NEXUS_URL           the package server, for --grpc only
  ARTIFACTS_DIR       [deploy/ansible/artifacts/SVK]

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

ROOT = pathlib.Path(__file__).resolve().parents[3]   # deploy/ansible/scripts/ -> the repository root
# No built-in addresses: in CI they come from GitLab's own variables, elsewhere they must be set.
GITLAB = os.environ.get("COGNOS_GITLAB_URL") or os.environ.get("CI_SERVER_URL", "")
PROJECT = os.environ.get("COGNOS_PROJECT") or os.environ.get("CI_PROJECT_PATH", "")
API = f"{GITLAB}/api/v4/projects/{urllib.parse.quote(PROJECT, safe='')}"
NEXUS = os.environ.get("NEXUS_URL", "").rstrip("/").removesuffix("/repository")
DEST = pathlib.Path(os.environ.get("ARTIFACTS_DIR", ROOT / "deploy" / "ansible" / "artifacts" / "SVK"))
SUFFIX = {"ubuntu24": ".deb", "ol10": ".rpm"}
DEV_SET_JOB = "publish dev set"
PACKAGE_COMPONENT = {
    "cognos-core": "core", "cognos-mgmt-fw": "mgmt-fw", "cognos-node": "node", "cognos-ras": "ras",
    "cognos-slat": "slat", "cognos-me": "me", "cognos-cxl": "cxl", "cognos-cxl-mock": "cxl", "cognos-app": "sapp",
    "cognos-grpc": "grpc",
}


def die(message):
    sys.exit(f"fetch-packages: {message}")


def get(url, missing_ok=False, timeout=600):
    """GET url; bytes, or None for 404 when missing_ok."""
    headers = {"PRIVATE-TOKEN": os.environ["GITLAB_TOKEN"]} if os.environ.get("GITLAB_TOKEN") and url.startswith(
        GITLAB) else {}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as response:
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


def grpc():
    """cognos-grpc for ol10 from Nexus, at GRPC_VERSION. A short timeout: Nexus is only reachable from the lab.

    Found with Nexus' search by name, never from a fixed URL: Nexus records a yum version with its release
    (1.59.2-1.el10), so the matching rpm is the one whose file name has GRPC_VERSION right after the name."""
    base = f"{NEXUS}/service/rest/v1/search/assets?repository=svk_yum_ol10&name=cognos-grpc"
    token, urls = None, []
    while True:
        page = json.loads(get(base + (f"&continuationToken={urllib.parse.quote(token)}" if token else ""), timeout=60))
        urls += [a["downloadUrl"] for a in page.get("items", [])]
        token = page.get("continuationToken")
        if not token:
            break
    rpm = next((u for u in urls if u.rsplit("/", 1)[1].startswith(f"cognos-grpc-{GRPC_VERSION}-")
                and u.endswith(".rpm")), None)
    if not rpm:
        found = ", ".join(u.rsplit("/", 1)[1] for u in urls) or "none"
        die(f"cognos-grpc {GRPC_VERSION} not found in Nexus (svk_yum_ol10; found: {found})")
    print(f"cognos-grpc {GRPC_VERSION} from Nexus: {rpm.rsplit('/', 1)[1]}")
    return {rpm.rsplit("/", 1)[1]: get(rpm, timeout=120)}


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
    source.add_argument("--grpc", action="store_true")
    args = parser.parse_args()
    unknown = args.only - set(PACKAGE_COMPONENT.values())
    if unknown:
        die(f"unknown components: {', '.join(sorted(unknown))}")

    if args.grpc and not NEXUS:
        die("--grpc needs NEXUS_URL, the package server to download cognos-grpc from")
    if (args.release or args.dev_set or args.pipeline) and not (GITLAB and PROJECT):
        die("set COGNOS_GITLAB_URL (the GitLab that builds Cognos) and COGNOS_PROJECT (its project path); "
            "in a GitLab pipeline CI_SERVER_URL and CI_PROJECT_PATH are used")

    if args.grpc:
        if args.os != "ol10":
            die("--grpc is for ol10 only (ubuntu24 does not need cognos-grpc)")
        files = grpc()
    elif args.release:
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
    expected = args.only or set(PACKAGE_COMPONENT.values()) - {"grpc"}
    if not args.grpc and expected - found - {"grpc"}:
        print("WARNING: no packages for " + ", ".join(sorted(expected - found - {"grpc"})))
    if args.os == "ol10" and not args.only and not args.grpc and "grpc" not in found:
        print("WARNING: no cognos-grpc in these packages (sets published before it was added, or a local build); "
              "the playbooks need it on ol10. Add it with: fetch-packages.py --os ol10 --grpc (needs the lab network)")

    DEST.mkdir(parents=True, exist_ok=True)
    # --grpc adds to what is there: it replaces only an older cognos-grpc.
    for old in sorted(DEST.glob(("cognos-grpc*" if args.grpc else "cognos-*") + SUFFIX[args.os])):
        print(f"  removed old {old.name}")
        old.unlink()
    for name, data in sorted(files.items()):
        (DEST / name).write_bytes(data)
    print(f"Packages in {DEST}:")
    for name in sorted(files):
        print(f"  {name}")


if __name__ == "__main__":
    main()
