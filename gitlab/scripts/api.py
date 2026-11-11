#!/usr/bin/env python3
"""The GitLab API calls of the pipeline. Everything here is GitLab-specific; see docs/ci.md, "Releases".

Usage: gitlab/scripts/api.py <command> [options]

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
  sync [--only <components>]          bring each component repository's main into its folder here (git subtree
                                      merge, history kept), as one merge request per component

Uses the CI variables CI_API_V4_URL, CI_PROJECT_ID, CI_PROJECT_PATH, CI_SERVER_URL, CI_SERVER_HOST, CI_COMMIT_SHA, and
RELEASE_BOT_TOKEN (create-release, propose, tag-patch, backport, sync) or CI_JOB_TOKEN (newest-dev-set, publish-release).
job-results and newest-dev-set read the public pipeline API without a token. sync reads the component
repositories from SYNC_SOURCE_URL (default CI_SERVER_URL) without a token: they are public.
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
ROOT = pathlib.Path(__file__).resolve().parents[2]

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
    sys.exit(f"gitlab/scripts/api.py: {message}")


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
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    if check and result.returncode != 0:
        die(f"{' '.join(command)} failed (exit {result.returncode}): {result.stderr.strip()[-500:]}")
    return result


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
    if request("GET", f"/repository/tags/{quote(tag)}", token=token, ok_missing=True):
        die(f"tag {tag} already exists")
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
    url = f"{os.environ['CI_SERVER_URL']}/{os.environ['CI_PROJECT_PATH']}.git"
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

    def upload(name, data):
        request("PUT", f"{base}/{quote(name)}", raw=data, job_token=True)
        links.append({"name": name, "url": f"{API}/projects/{PROJECT}{base}/{quote(name)}", "link_type": "package"})

    # One download per OS: cognos-<version>-<os>.zip with that OS's packages (ol10 with cognos-grpc) and set.json.
    for os_name in sorted({p["os"] for p in release_set["packages"]}):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(directory / "set.json", "set.json")
            for package in release_set["packages"]:
                if package["os"] == os_name:
                    z.write(directory / package["file"], package["file"])
        upload(f"cognos-{version}-{os_name}.zip", archive.getvalue())
    for file in ["set.json"] + [p["file"] for p in release_set["packages"]]:
        upload(pathlib.PurePath(file).name, (directory / file).read_bytes())
    print(f"Uploaded {len(links)} files to the package registry: cognos/{version}")
    if request("GET", f"/releases/{quote(tag)}", job_token=True, ok_missing=True):
        print(f"Release {tag} already exists; packages re-uploaded.")
        return
    request("POST", "/releases", {
        "tag_name": tag, "name": f"Cognos {version}",
        "description": f"Cognos {version}: packages for ubuntu24 and ol10. `cognos-{version}-<os>.zip` holds all of "
                       f"one OS's packages (ol10 with cognos-grpc) and `set.json`, which lists every file with its "
                       f"sha256. Or deploy with `deploy/ansible/scripts/fetch-packages.py --os <os> --release {tag}`.",
        "assets": {"links": links}}, job_token=True)
    print(f"Created release {tag}")


# sync: monorepo folder -> component repository (on this GitLab). deploy/ansible/ is owned by this repository; cama holds
# only a README for now.
COMPONENT_REPOS = {
    "core": ("features/core", "dfs/svk/core"),
    "mgmt-fw": ("features/mgmt-fw", "dfs/svk/mgmt-fw"),
    "cxl": ("features/cxl", "dfs/svk/cxl"),
    "slat": ("features/slat", "dfs/svk/slat"),
    "ras": ("features/ras", "dfs/svk/ras"),
    "me": ("features/me", "dfs/svk/svk-me"),
    "node": ("features/node", "dfs/svk/svk-node"),
    "sapp": ("apps/sapp", "dfs/svk/sapp"),
    "amo-prof": ("profilers/amo-prof", "dfs/svk/amo_prof"),
}


def unmerged_paths():
    return run("git", "diff", "--name-only", "--diff-filter=U", check=False).stdout.split()


def merge_preferring_repository(upstream, prefix, message, env):
    """Merges upstream into prefix on the current branch. Returns (files that conflicted, error or None).

    A clean merge keeps both sides. On conflicts, the merge is redone with the repository's side winning
    (-Xtheirs); a file deleted on one side and changed on the other takes the repository's side too."""
    def merge(*options):
        return subprocess.run(["git", "merge", "--quiet", "--no-ff", f"-Xsubtree={prefix}", *options, "-m", message,
                               upstream], cwd=ROOT, env=env, text=True, capture_output=True)

    result = merge()
    if result.returncode == 0:
        return [], None
    conflicts = unmerged_paths()
    run("git", "merge", "--abort", check=False)
    if not conflicts:
        return [], f"cannot be merged: {result.stderr.strip()[-200:]}"
    result = merge("-Xtheirs")
    if result.returncode != 0:
        for path in unmerged_paths():
            # Stage 3 is the repository's side; without it, the repository deleted the file.
            if run("git", "cat-file", "-e", f":3:{path}", check=False).returncode == 0:
                run("git", "checkout", "--theirs", "--", path)
                run("git", "add", "--", path)
            else:
                run("git", "rm", "--quiet", "--", path)
        left = unmerged_paths()
        committed = None if left else subprocess.run(["git", "commit", "--quiet", "--no-edit"], cwd=ROOT, env=env,
                                                     text=True, capture_output=True)
        if left or committed.returncode != 0:
            run("git", "merge", "--abort", check=False)
            return conflicts, f"cannot be merged even with its side winning: {', '.join(left) or committed.stderr[-200:]}"
    return conflicts, None


def sync(args):
    """For each component: if its repository's main is not yet in this main, merge it into the component's folder
    (git merge -Xsubtree, what `git subtree pull` does, history kept) on sync/<component>, and open or update that
    merge request.

    The component repository is the source of truth until it is retired: where both sides changed the same lines,
    or one side deleted a file the other changed, the repository's side wins. The merge request lists those files.
    A component that cannot be merged for any other reason is reported and the others continue."""
    token = bot_token()
    only = set(args.only.split(",")) if args.only else set(COMPONENT_REPOS)
    unknown = only - set(COMPONENT_REPOS)
    if unknown:
        die(f"unknown components: {', '.join(sorted(unknown))}")
    base = os.environ["CI_COMMIT_SHA"]
    source = os.environ.get("SYNC_SOURCE_URL") or os.environ["CI_SERVER_URL"]
    user = request("GET", f"{API}/user", token=token)
    email = user.get("email") or user.get("commit_email") or f"{user['username']}@noreply.{os.environ['CI_SERVER_HOST']}"
    env = dict(os.environ, GIT_AUTHOR_NAME=user["name"], GIT_AUTHOR_EMAIL=email,
               GIT_COMMITTER_NAME=user["name"], GIT_COMMITTER_EMAIL=email)
    auth = "Authorization: Basic " + base64.b64encode(f"oauth2:{token}".encode()).decode()
    url = f"{os.environ['CI_SERVER_URL']}/{os.environ['CI_PROJECT_PATH']}.git"
    failed = []
    for component, (prefix, repo) in COMPONENT_REPOS.items():
        if component not in only:
            continue
        fetched = run("git", "fetch", "--quiet", f"{source}/{repo}.git", "main", check=False)
        if fetched.returncode != 0:
            failed.append(f"{component}: cannot fetch {repo} ({fetched.stderr.strip()[-200:]})")
            continue
        upstream = run("git", "rev-parse", "FETCH_HEAD").stdout.strip()
        if run("git", "merge-base", "--is-ancestor", upstream, base, check=False).returncode == 0:
            print(f"{component}: up to date ({repo} main {upstream[:8]})")
            continue
        branch = f"sync/{component}"
        new_commits = run("git", "log", "--no-merges", "--format=- `%h` %s", f"{base}..{upstream}").stdout.strip()
        run("git", "checkout", "--quiet", "--force", "-B", branch, base)
        # The trailers git subtree writes, so a later sync (or a person) can see what was merged.
        message = f"Sync {component} from {repo} main\n\ngit-subtree-dir: {prefix}\ngit-subtree-split: {upstream}\n"
        conflicts, error = merge_preferring_repository(upstream, prefix, message, env)
        if error:
            failed.append(f"{component}: {error}")
            continue
        if conflicts:
            print(f"{component}: conflicts resolved in favour of {repo}: {', '.join(conflicts)}")
        pushed = subprocess.run(["git", "-c", f"http.extraHeader={auth}", "push", "--quiet", "--force", url,
                                 f"HEAD:refs/heads/{branch}"], cwd=ROOT, text=True, capture_output=True)
        if pushed.returncode != 0:
            failed.append(f"{component}: push of {branch} failed ({pushed.stderr.strip()[-300:]})")
            continue
        title = f"Sync {component} from {repo} main"
        description = (f"`{repo}` main (`{upstream[:8]}`) merged into `{prefix}` (git subtree merge, history kept). "
                       f"Made by the nightly sync; it is updated, not duplicated, by the next sync.\n\n"
                       f"New commits:\n{new_commits or '- (merge commits only)'}")
        if conflicts:
            description += (f"\n\n**Conflicts resolved in favour of `{repo}`** (the component repository is the "
                            f"source of truth): in these files its version replaced this repository's changes where "
                            f"both changed the same lines:\n" + "\n".join(f"- `{c}`" for c in conflicts))
        open_mrs = request("GET", f"/merge_requests?state=opened&source_branch={quote(branch)}", token=token) or []
        if open_mrs:
            mr = request("PUT", f"/merge_requests/{open_mrs[0]['iid']}", {"title": title, "description": description},
                         token=token)
        else:
            mr = request("POST", "/merge_requests", {
                "source_branch": branch, "target_branch": "main", "title": title, "description": description,
                "remove_source_branch": True, "squash": False}, token=token)
        print(f"{component}: {mr['web_url']}")
    run("git", "checkout", "--quiet", "--force", base, check=False)
    if failed:
        die("components that did not sync (each needs a merge request by hand):\n  " + "\n  ".join(failed))


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
    commands.add_parser("sync").add_argument("--only")
    args = parser.parse_args()
    {"job-results": job_results, "newest-dev-set": newest_dev_set, "create-release": create_release, "propose": propose, "tag-patch": tag_patch,
     "backport": backport, "publish-release": publish_release, "sync": sync}[args.command](args)


if __name__ == "__main__":
    main()
