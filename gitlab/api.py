#!/usr/bin/env python3
"""The GitLab API calls of the pipeline. Everything here is GitLab-specific; see docs/ci.md, "Releases".

Usage: gitlab/api.py <command> [options]

  job-results --pipeline <id>         print {"<component>/<os>": "passed"|"failed"} for ci/dev-set.py
  newest-dev-set --out <dir>          extract the newest dev set (the newest successful "publish dev set" job on
                                      main whose artifacts still exist, whatever its pipeline's status) into <dir>
  create-release                      create release/<VERSION>, its first tag and the backport-<VERSION> label
  propose --version <X.Y> --report <file>
                                      put VERSION=<X.Y> on release-bot/next and open or update the release MR
  tag-patch                           tag the next patch release on this release/X.Y commit
  backport                            backport this main commit's merge request to every release/X.Y it is
                                      labelled backport-X.Y for, as a merge request into that branch
  publish-release --dir <dir>         upload a release set (ci/dev-set.py --complete) to the package registry
                                      and create the GitLab release for $CI_COMMIT_TAG

Uses the CI variables CI_API_V4_URL, CI_PROJECT_ID, CI_PROJECT_PATH, CI_SERVER_HOST, CI_COMMIT_SHA, and
RELEASE_BOT_TOKEN (create-release, propose, tag-patch, backport) or CI_JOB_TOKEN (newest-dev-set, publish-release).
job-results and newest-dev-set read the public pipeline API without a token.
Never prints a token.
"""

import argparse
import base64
import io
import json
import os
import pathlib
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile

API = os.environ.get("CI_API_V4_URL", "")
PROJECT = os.environ.get("CI_PROJECT_ID", "")
ROOT = pathlib.Path(__file__).resolve().parent.parent

# job-results: which jobs make up a component on one OS ({os}: ubuntu24 or ol10).
COMPONENT_JOBS = {
    "core": ["build core: [{os}]", "test core: [{os}]"],
    "mgmt-fw": ["build mgmt-fw: [{os}]", "test mgmt-fw: [{os}]"],
    "node": ["build node: [{os}]", "test node: [{os}]"],
    "ras": ["build ras: [{os}]", "test ras: [{os}]"],
    "slat": ["build slat: [{os}]", "test slat: [{os}]"],
    "me": ["build me: [{os}]", "test me: [{os}]"],
    "cxl": ["build cxl: [{os}, release]", "test cxl: [{os}]"],
    "cxl-mock": ["build cxl: [{os}, mock]", "test cxl: [{os}]"],
    "sapp": ["build sapp: [{os}]", "test sapp: [{os}]"],
}


def die(message):
    sys.exit(f"gitlab/api.py: {message}")


def request(method, path, data=None, token=None, job_token=False, raw=None, ok_missing=False):
    """One API call; returns the decoded JSON (or None for 404 when ok_missing)."""
    url = path if path.startswith("http") else f"{API}/projects/{PROJECT}{path}"
    headers = {}
    if job_token:
        headers["JOB-TOKEN"] = os.environ["CI_JOB_TOKEN"]
    elif token:
        headers["PRIVATE-TOKEN"] = token
    body = raw
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=300) as response:
            content = response.read()
            return json.loads(content) if content else None
    except urllib.error.HTTPError as e:
        if e.code == 404 and ok_missing:
            return None
        die(f"{method} {url.split('?')[0]}: HTTP {e.code} {e.read().decode(errors='replace')[:300]}")


def bot_token():
    token = os.environ.get("RELEASE_BOT_TOKEN")
    if not token:
        die("RELEASE_BOT_TOKEN is not set (a protected CI/CD variable; see docs/ci.md, \"Releases\")")
    return token


def quote(name):
    return urllib.parse.quote(name, safe="")


def run(*command, check=True):
    return subprocess.run(command, check=check, cwd=ROOT, text=True, capture_output=True)


def version_line():
    x_y = (ROOT / "VERSION").read_text().strip()
    if not re.fullmatch(r"[0-9]+\.[0-9]+", x_y):
        die(f"VERSION must be MAJOR.MINOR, not {x_y!r}")
    return x_y


def next_patch_tag():
    """v<X.Y.P+1>: the next release tag of the VERSION line (ci/version.sh --next-patch)."""
    return "v" + run(str(ROOT / "ci" / "version.sh"), "--next-patch").stdout.strip()


def ensure_label(token, x_y):
    name = f"backport-{x_y}"
    labels = request("GET", f"/labels?search={quote(name)}", token=token) or []
    if not any(label["name"] == name for label in labels):
        request("POST", "/labels", {"name": name, "color": "#6699cc",
                                    "description": f"Backport this merge request to release/{x_y} after it merges"},
                token=token)
        print(f"Created label {name}")


def job_results(args):
    jobs, page = [], 1
    while True:
        batch = request("GET", f"/pipelines/{args.pipeline}/jobs?per_page=100&page={page}", job_token=False)
        jobs += batch
        if len(batch) < 100:
            break
        page += 1
    status = {job["name"]: job["status"] for job in jobs}
    results = {}
    for component, names in COMPONENT_JOBS.items():
        for os_name in ("ubuntu24", "ol10"):
            names_os = [n.format(os=os_name) for n in names]
            if names_os[0] not in status:
                continue  # not built in this pipeline
            ok = all(status.get(n) == "success" for n in names_os)
            results[f"{component}/{os_name}"] = "passed" if ok else "failed"
    print(json.dumps(results, indent=2, sort_keys=True))


def newest_dev_set(args):
    """Searched pipeline by pipeline, newest first: GitLab's own "latest artifacts" lookup only considers pipelines
    that passed, so it would skip a set published by a pipeline that failed elsewhere (for example a Sonar scan)."""
    for pipeline in request("GET", "/pipelines?ref=main&per_page=50"):
        jobs = request("GET", f"/pipelines/{pipeline['id']}/jobs?per_page=100&scope[]=success")
        job = next((j for j in jobs if j["name"] == "publish dev set"), None)
        if not job:
            continue
        token = os.environ.get("CI_JOB_TOKEN")
        req = urllib.request.Request(f"{API}/projects/{PROJECT}/jobs/{job['id']}/artifacts",
                                     headers={"JOB-TOKEN": token} if token else {})
        try:
            with urllib.request.urlopen(req, timeout=600) as response:
                data = response.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:  # expired
                continue
            die(f"artifacts of job {job['id']}: HTTP {e.code}")
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            z.extractall(args.out)
        print(f"Newest dev set: pipeline {pipeline['id']} (job {job['id']}, pipeline status {pipeline['status']})")
        return
    print("No dev set found.")


def create_release(_args):
    token = bot_token()
    x_y = version_line()
    sha = os.environ["CI_COMMIT_SHA"]
    branch = f"release/{x_y}"
    existing = request("GET", f"/repository/branches/{quote(branch)}", token=token, ok_missing=True)
    tag = next_patch_tag()
    if existing:
        tags = request("GET", f"/repository/tags?search=^v{x_y}.", token=token) or []
        if existing["commit"]["id"] == sha and any(t["commit"]["id"] == sha for t in tags):
            print(f"{branch} and its release tag already exist at this commit; nothing to do.")
            ensure_label(token, x_y)
            return
        die(f"{branch} already exists (at {existing['commit']['short_id']}). Patch releases are tagged from "
            f"{branch} itself; a new release line needs a new VERSION.")
    request("POST", f"/repository/branches?branch={quote(branch)}&ref={sha}", token=token)
    print(f"Created branch {branch} at {sha[:8]}")
    request("POST", "/repository/tags", {"tag_name": tag, "ref": sha, "message": f"Release {tag[1:]}"}, token=token)
    print(f"Created tag {tag}; its pipeline builds, tests and publishes the release.")
    ensure_label(token, x_y)


def propose(args):
    token = bot_token()
    branch = "release-bot/next"
    report = pathlib.Path(args.report).read_text()
    content = args.version + "\n"
    action = {"action": "update", "file_path": "VERSION", "content": content}
    request("POST", "/repository/commits", {
        "branch": branch, "start_branch": "main", "force": True,
        "commit_message": f"Release {args.version}", "actions": [action]}, token=token)
    print(f"{branch}: VERSION = {args.version} (on top of main)")
    title = f"Release {args.version}"
    description = (f"Merging this sets `VERSION` to `{args.version}`. That creates `release/{args.version}` and its "
                   f"first release tag (\"create release\").\n\nTo release a different version, edit `VERSION` in "
                   f"this merge request before merging.\n\n## Compatibility check\n\n{report}")
    open_mrs = request("GET", f"/merge_requests?state=opened&source_branch={quote(branch)}", token=token) or []
    if open_mrs:
        mr = request("PUT", f"/merge_requests/{open_mrs[0]['iid']}", {"title": title, "description": description},
                     token=token)
    else:
        mr = request("POST", "/merge_requests", {"source_branch": branch, "target_branch": "main", "title": title,
                                                 "description": description, "remove_source_branch": True},
                     token=token)
    print(f"Release merge request: {mr['web_url']}")


def tag_patch(_args):
    token = bot_token()
    sha = os.environ["CI_COMMIT_SHA"]
    x_y = os.environ["CI_COMMIT_BRANCH"].removeprefix("release/")
    if x_y != version_line():
        die(f"branch release/{x_y}, but VERSION is {version_line()}")
    tags = request("GET", f"/repository/tags?search=^v{x_y}.", token=token) or []
    if any(t["commit"]["id"] == sha for t in tags):
        print("This commit is already tagged; nothing to do.")
        return
    tag = next_patch_tag()
    request("POST", "/repository/tags", {"tag_name": tag, "ref": sha, "message": f"Release {tag[1:]}"}, token=token)
    print(f"Created tag {tag}")


def backport(_args):
    token = bot_token()
    sha = os.environ["CI_COMMIT_SHA"]
    mrs = request("GET", f"/repository/commits/{sha}/merge_requests", token=token) or []
    mrs = [mr for mr in mrs if mr["state"] == "merged" and sha in (mr.get("merge_commit_sha"),
                                                                     mr.get("squash_commit_sha"))]
    targets = [(mr, label.removeprefix("backport-")) for mr in mrs for label in mr["labels"]
               if re.fullmatch(r"backport-[0-9]+\.[0-9]+", label)]
    if not targets:
        print("No merged merge request with a backport-X.Y label for this commit.")
        return
    user = request("GET", f"{API}/user", token=token)
    env = dict(os.environ, GIT_COMMITTER_NAME=user["name"], GIT_COMMITTER_EMAIL=user.get("email") or user.get(
        "commit_email") or f"{user['username']}@noreply.{os.environ['CI_SERVER_HOST']}")
    auth = "Authorization: Basic " + base64.b64encode(f"oauth2:{token}".encode()).decode()
    url = f"https://{os.environ['CI_SERVER_HOST']}/{os.environ['CI_PROJECT_PATH']}.git"
    parents = run("git", "rev-list", "--parents", "-n", "1", sha).stdout.split()[1:]
    failed = []
    for mr, x_y in targets:
        target, branch = f"release/{x_y}", f"backport/{mr['iid']}-{x_y}"
        if not request("GET", f"/repository/branches/{quote(target)}", token=token, ok_missing=True):
            failed.append(f"!{mr['iid']} to {x_y}: {target} does not exist")
            continue
        if request("GET", f"/repository/branches/{quote(branch)}", token=token, ok_missing=True):
            print(f"!{mr['iid']} to {x_y}: {branch} already exists; nothing to do.")
            continue
        run("git", "fetch", "--quiet", "--depth", "1", "origin", target)
        run("git", "checkout", "--quiet", "-B", branch, "FETCH_HEAD")
        pick = ["git", "cherry-pick", "-x"] + (["-m", "1"] if len(parents) > 1 else []) + [sha]
        picked = subprocess.run(pick, cwd=ROOT, env=env, text=True, capture_output=True)
        if picked.returncode != 0:
            conflicts = run("git", "diff", "--name-only", "--diff-filter=U", check=False).stdout.split()
            run("git", "cherry-pick", "--abort", check=False)
            note = (f"Automatic backport to `{target}` failed: the change does not apply cleanly"
                    + (f" (conflicts in {', '.join(f'`{c}`' for c in conflicts)})" if conflicts else "")
                    + f". Please backport it by hand: a merge request into `{target}`.")
            request("POST", f"/merge_requests/{mr['iid']}/notes", {"body": note}, token=token)
            failed.append(f"!{mr['iid']} to {x_y}: conflicts")
            continue
        subprocess.run(["git", "-c", f"http.extraHeader={auth}", "push", "--quiet", url, f"HEAD:refs/heads/{branch}"],
                       cwd=ROOT, check=True)
        new = request("POST", "/merge_requests", {
            "source_branch": branch, "target_branch": target, "remove_source_branch": True,
            "title": f"Backport !{mr['iid']} to {x_y}: {mr['title']}",
            "description": f"Backport of !{mr['iid']} to `{target}`. Merging it tags the next {x_y} patch release."},
            token=token)
        request("POST", f"/merge_requests/{mr['iid']}/notes",
                {"body": f"Backport to `{target}`: !{new['iid']}"}, token=token)
        print(f"!{mr['iid']} to {x_y}: {new['web_url']}")
    if failed:
        die("backports that need to be done by hand: " + "; ".join(failed))


def publish_release(args):
    tag = os.environ["CI_COMMIT_TAG"]
    version = tag.removeprefix("v")
    directory = pathlib.Path(args.dir)
    release_set = json.loads((directory / "set.json").read_text())
    base = f"/packages/generic/cognos/{version}"
    links = []
    for file in ["set.json"] + [p["file"] for p in release_set["packages"]]:
        name = pathlib.PurePath(file).name
        request("PUT", f"{base}/{quote(name)}", raw=(directory / file).read_bytes(), job_token=True)
        links.append({"name": name, "url": f"{API}/projects/{PROJECT}{base}/{quote(name)}", "link_type": "package"})
    print(f"Uploaded {len(links)} files to the package registry: cognos/{version}")
    if request("GET", f"/releases/{quote(tag)}", job_token=True, ok_missing=True):
        print(f"Release {tag} already exists; packages re-uploaded.")
        return
    request("POST", "/releases", {
        "tag_name": tag, "name": f"Cognos {version}",
        "description": f"Cognos {version}: packages for ubuntu24 and ol10. `set.json` lists every file with its "
                       f"sha256. Deploy with `deploy/scripts/fetch-packages.py --release {tag}`.",
        "assets": {"links": links}}, job_token=True)
    print(f"Created release {tag}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("job-results").add_argument("--pipeline", required=True)
    commands.add_parser("newest-dev-set").add_argument("--out", required=True)
    commands.add_parser("create-release")
    p = commands.add_parser("propose")
    p.add_argument("--version", required=True)
    p.add_argument("--report", required=True)
    commands.add_parser("tag-patch")
    commands.add_parser("backport")
    commands.add_parser("publish-release").add_argument("--dir", required=True)
    args = parser.parse_args()
    {"job-results": job_results, "newest-dev-set": newest_dev_set, "create-release": create_release, "propose": propose, "tag-patch": tag_patch,
     "backport": backport, "publish-release": publish_release}[args.command](args)


if __name__ == "__main__":
    main()
