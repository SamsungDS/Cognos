# CI

| File | What it does | Depends on GitLab |
|---|---|---|
| `gitlab/.gitlab-ci.yml` | when jobs run, and which CI variables are passed to the scripts | yes |
| `build.sh` | builds or tests components, locally (Docker) or in CI (`--native`) | no |
| `ci/version.sh` | prints the one version of a build | no |
| `ci/image.sh` | builds a component image, or reuses it when its inputs are unchanged | no |
| `ci/dev-set.py` | assembles a dev set or a release, with its `set.json` | no |
| `ci/compat-check.sh` | proposes a major or minor release (buf, abidiff) | no |
| `gitlab/scripts/api.py` | the GitLab API calls: job results, release branches, tags, merge requests, backports, release upload | yes |
| `gitlab/scripts/tests/` | tests of all of the above: `run.sh` (file modes, shellcheck, unit tests) and `smoke.sh` | the smoke tests only |
| `deploy/scripts/fetch-packages.py` | puts the packages of a release, a dev set, a pipeline or a local build into `deploy/artifacts/SVK/` | uses the GitLab API to download |

One pipeline per event, no child pipelines. `gitlab/.gitlab-ci.yml` has seven sections: includes and workflow, what a
change rebuilds, job templates, one block per component with all of its jobs, the dev set, releases, and other
jobs.

## When a pipeline runs

| Event | Runs |
|---|---|
| Merge request | yes |
| Push to `main` | yes |
| Push to `release/X.Y` | yes, except the push that creates the branch |
| Tag `vX.Y.Z` | yes |
| Any other tag (the imported prefixed tags) | no |
| Schedule, or a run from the web UI | yes |
| Push to any other branch | no |

## What a change rebuilds

- A change under `components/core`, `components/mgmt-fw`, `gitlab/`, `ci/`, `VERSION` or `build.sh` (`.rebuild-all`)
  builds and tests every component.
- A change in one component's folder builds and tests only that component.
- amo-prof and `deploy/` run only when their own folder changes.
- Anything else (docs, the `cama` submodule bump) builds nothing; only "check version" runs, and on `main` also
  "publish dev set", which then republishes the previous set unchanged.
- Tag, schedule and web pipelines run every job. Images are still reused when their inputs are unchanged.

## Stages and jobs

Stages: `build-images`, `build`, `test`, `scan`, `publish`, `release`.

| Job | Stage | What it does |
|---|---|---|
| build \<component\> image | build-images | builds or reuses the component image ([Images](#images)) |
| build \<component\> | build | builds the release packages ([Builds](#builds)) |
| test \<component\> | test | runs the unit tests ([Tests](#tests)) |
| scan \<component\> | scan | Sonar analysis, `main` only ([Scans](#scans)) |
| test amo-prof | test | builds the amo-prof wheel and runs its tests |
| publish dev set | publish | every `main` push, schedule and web run ([Dev sets](#dev-sets)) |
| propose release, create release, tag patch, backport, publish release | release, publish | see [Releases](#releases) |
| sync components | release | nightly schedule or by hand, with `SYNC_COMPONENTS=true` ([Sync](#sync)) |
| test ci | test | the tests of the CI scripts ([Tests of the CI scripts](#tests-of-the-ci-scripts)) |
| check version | test | every pipeline; checks that `VERSION` is `MAJOR.MINOR` |
| build ansible image, lint ansible | build-images, test | lint `deploy/` |

Components: core, mgmt-fw, node, ras, slat, me, cxl and sapp. cama is not built here.

"check version" makes sure every merge request has a pipeline, which "Pipelines must succeed" requires.

## Operating systems

ubuntu24 and ol10 only. Merge requests run the unit tests on ubuntu24 only; every other pipeline runs them on both.

## Images

A component image depends only on its `scripts/docker/<os>.DOCKERFILE` and `scripts/dependencies/`, so
`ci/image.sh` tags it by those two inputs: `<component>:<os>-deps-<hash>` in this project's container registry.

- Tag already exists: nothing is built, also in tag, schedule and web pipelines. The image only gets the commit's tag.
- Tag does not exist (the Dockerfile or `scripts/dependencies/` changed): the image is built and pushed.
- Build and test jobs use `<component>:<os>-<short sha>`, so overlapping pipelines never use each other's image.

An image keeps the base OS and the Nexus packages (for example core and mgmt-fw) it was built with. Newer ones are
picked up only when one of its two inputs changes.

## Builds

"build \<component\>" runs `./build.sh --native <component> --os <os>`. Its packages are job artifacts under
`<component dir>/build/artifacts/<os>/` for 14 days. "build cxl" builds both variants, release (`cognos-cxl`) and mock
(`cognos-cxl-mock`).

Upstream packages: every component except core and sapp builds against core, and cxl and me also against mgmt-fw.
`build.sh` installs them from the first of: this pipeline's "build core" / "build mgmt-fw" artifacts (logged
`upstream core: pipeline <version>`), the newest dev set (`upstream core: dev set <version>`), or the Nexus packages
in the image (`upstream core: image <version>`). So a cxl-only change builds against the newest dev set's core and
mgmt-fw, not the older ones in the image.

## Versions

Every package built in a pipeline carries one version, printed by `ci/version.sh`. `X.Y` is `VERSION`:

| Pipeline | Version |
|---|---|
| tag `vX.Y.Z` | `X.Y.Z` |
| `main`, and schedules or web runs | `X.(Y+1).0~dev.<pipeline iid>` |
| `release/X.Y` | `X.Y.(P+1)~rc.<pipeline iid>`, P is the highest `vX.Y.P` tag (none: `X.Y.0~rc.<iid>`); fails if `VERSION` is not `X.Y` |
| merge request | `X.(Y+1).0~dev.0.mr<mr iid>.<pipeline iid>` |
| local `./build.sh` | the `vX.Y.Z` tag on HEAD, else `X.(Y+1).0~dev.0.local` |

The pipeline iid only makes dev and release-candidate builds unique and ordered; release versions do not contain it.

The components' `scripts/get_version.sh` print `v$COGNOS_VERSION` when it is set, and use `git describe` otherwise.
Inside this repository `git describe` finds the imported tags, so build a component through the root `build.sh`, or
export `COGNOS_VERSION` first.

## Tests

"test \<component\>" runs `./build.sh --native --test <component> --os <os>`, which installs the upstream packages as
a build does and then runs the component's own unit-test command:

| Component | Command |
|---|---|
| core, mgmt-fw, ras, slat | `scripts/build.sh --run-tests` |
| cxl | `scripts/build.sh --build-tests --with-coverage` |
| me | `scripts/build.sh --build-tests` |
| node | `scripts/build.sh --run-tests`, then `--run-python-tests` |
| sapp | `scripts/run-tests.sh --ut`, then `npm run test:coverage` for the UI and rbac |

The C/C++ tests run under Sonar's build-wrapper. The junit and coverage reports appear in the merge request. slat runs
on the `svk-slat` runner and me on the `svk-me` runner, as in their own repositories.

## Scans

"scan \<component\>" runs on `main` pushes only, after the ubuntu24 test. It analyses the component's existing Sonar
project as the branch `branch-cognos-monorepo`, so the component repository's own `main` analysis and its merge request
analyses are never touched. Merge requests in this repository are not scanned, because their numbers would collide with
the component repository's merge request analyses.

Sonar keeps the branch while it is inactive if its name matches "Branches to keep when inactive" (Housekeeping; the
default `(branch|release)-.*` matches).

## Build locally

```bash
./build.sh                          # all components, ubuntu24, each in a Docker container
./build.sh --os ol10 core mgmt-fw   # only these, in dependency order
./build.sh --mock cxl               # the cxl mock variant
./build.sh --test node              # node's unit tests
./build.sh --native node            # on this machine; it must run that OS with node's dependencies installed
./build.sh -h
```

The packages end up in `build/artifacts/<os>/`. The component Dockerfiles install dependencies from the internal
Nexus, so a local Docker build needs the lab network.

## Dev sets

A dev set is a complete set of Cognos packages, every component for ubuntu24 and ol10, built on `main`. It is what
`deploy/scripts/fetch-packages.py --set` deploys.

- "publish dev set" runs in every `main` push, scheduled and web pipeline, once all of its builds and tests finished,
  also when some failed (`ci/dev-set.py`). For each component and OS (cxl and cxl-mock separately):
  - its build and tests passed: this pipeline's packages;
  - its build or tests failed: the previous set's packages, noted as failed in `set.json`;
  - not built in this pipeline: the previous set's packages.
- If core or mgmt-fw failed on any OS, **no set is published** and the job fails: every other component depends on
  them. The previous set stays the newest.
- A failed Sonar scan does not hold a set back; scans report code quality, not whether the packages work.
- A component that has never passed is missing from the set; `fetch-packages.py` warns about it.
- Rerunning "publish dev set" (for example after retrying a failed job) republishes the set with the new results.
- The set is the job's artifact: `dev-set/set.json` and `dev-set/<os>/<packages>`. `set.json` lists every package
  file with its component, OS, version, sha256 and the pipeline that built it, and what happened to each component
  and OS in this pipeline. Packages built in this pipeline carry its version (`X.(Y+1).0~dev.<pipeline iid>`);
  others keep the version of the pipeline that built them.
- The newest set is the artifact of the newest successful "publish dev set" job on `main`, whatever the status of its
  pipeline: a pipeline can fail elsewhere (a component's tests, a Sonar scan) and still publish the newest set.
  "publish dev set" and `fetch-packages.py --set latest` both find it by searching `main`'s pipelines, newest first.
- Every set expires 10 days after it was created, except the one in the most recent pipeline that passed: GitLab keeps
  those artifacts ("Keep artifacts from most recent successful jobs"). So the newest set stays until a newer one exists
  if its pipeline passed. If its pipeline failed (for example a failing Sonar scan) and no newer set follows within 10
  days, it expires and `--set latest` uses the newest set still kept. A nightly schedule on `main` avoids that.
- Sets are created in pipeline order (`resource_group: dev-set`). If an older pipeline would still finish after a
  newer one, `ci/dev-set.py` refuses to replace the newer set and that job fails.
- Dev sets are stored only in GitLab, as job artifacts; nothing is published to Nexus or to the package registry.
- A merge request's packages are the artifacts of its build jobs (14 days): `fetch-packages.py --pipeline <id>`
  deploys them, with the newest dev set for the components the merge request did not build.

Deploying: see "Prepare the artifacts" in [deploy/README.md](../deploy/README.md). Every deployment starts from a clean
host: `deploy_cognos.yml` first runs `remove_cognos.yml`.

## Releases

`VERSION` holds the current release line `X.Y`; `main` builds `X.(Y+1).0~dev`. Releases are tagged `vX.Y.Z` and never
reuse a version: the first patch of a line follows the highest `X.Y.P` released so far, including the component
repositories' imported tags (so the first 1.6 release is `v1.6.3`).

| Step | Job | When | What it does |
|---|---|---|---|
| 1. Propose | propose release | by hand, on any `main` pipeline | compares the newest dev set with the last release of the line (`ci/compat-check.sh`) and opens or updates one merge request from `release-bot/next` setting `VERSION` to the next `X.Y`: major if a public interface broke, else minor |
| 2. Review | you | | merge it, or first edit `VERSION` in it to release a different version |
| 3. Create | create release | the `main` push that changed `VERSION`; or by hand for the current line (the first release) | creates `release/X.Y`, the tag `vX.Y.P` and the label `backport-X.Y` |
| 4. Publish | publish release | every `vX.Y.Z` tag pipeline, after every component built and tested on both OSes | uploads the packages and `set.json` to the package registry (`cognos/X.Y.Z`, kept permanently) and creates the GitLab release |
| 5. Backport | backport | every `main` push | for a merged merge request labelled `backport-X.Y`: cherry-picks it onto `release/X.Y` and opens a merge request into it; on a conflict it comments on the merge request and fails, and the backport is done by hand |
| 6. Patch | tag patch | every push to `release/X.Y` (e.g. a merged backport) | tags `vX.Y.(P+1)` unless the commit is tagged, which runs step 4 |

The compatibility check: `buf breaking` on mgmt-fw's gRPC API (`proto/framework`) against the last release's
protos, and `abidiff` on every shared library in the ubuntu24 packages against the last release's. A check that cannot
run is reported in the merge request and does not count as a break. All release jobs share `resource_group: release`.
They use `RELEASE_BOT_TOKEN`, except "publish release", which uses the job token. Releases are not published to Nexus
yet; that comes when the component repositories stop releasing.

Deploying a release: `deploy/scripts/fetch-packages.py --os ubuntu24 --release vX.Y.Z`.

## Sync

Until the component repositories stop, their `main` branches are brought into this repository every night. For each
of core, mgmt-fw, cxl, slat, ras, me (`svk-me`), node (`svk-node`), sapp and amo-prof (`amo_prof`) whose repository's
`main` is not in this `main` yet, "sync components" merges it into the component's folder (a git subtree merge, so the
history is kept) on `sync/<component>` and opens a merge request, or updates the open one. The merge request runs the
normal pipeline for that component; you merge it.

The component repositories are the source of truth until they are retired. Where both sides changed the same lines,
the repository's version wins; where one side deleted a file the other changed, the repository's side wins (the file
stays if the repository has it, and goes if the repository deleted it). This repository's changes elsewhere are kept.
The merge request lists every file where the repository's version replaced a change made here. A component that cannot
be merged for another reason fails the job and needs a merge request by hand; the others still sync.
`deploy/` is owned by this repository and is not synced; `cama` is a submodule.

It runs only when `SYNC_COMPONENTS` is `true`, on `main`:

| What | How |
|---|---|
| Nightly: full build and tests, dev set refresh, and the sync | a pipeline schedule on `main` with the variable `SYNC_COMPONENTS` = `true` (Build → Pipeline schedules) |
| Sync now | the schedule's ▶ Play, or Build → Pipelines → Run pipeline on `main` with `SYNC_COMPONENTS` = `true` |
| Stop the sync, keep the nightly build | set `SYNC_COMPONENTS` to `false` in the schedule |
| Stop the nightly pipeline | make the schedule inactive |

The sync uses `RELEASE_BOT_TOKEN`: its merge requests and merge commits are made by that token's user.

## Tests of the CI scripts

`gitlab/scripts/tests/run.sh` tests every script the pipeline runs: `build.sh`, `ci/version.sh`, `ci/image.sh`,
`ci/dev-set.py`, `ci/compat-check.sh`, `gitlab/scripts/api.py` and `deploy/scripts/fetch-packages.py`.

- **File modes:** each of those scripts is executable in git.
- **shellcheck** on the shell scripts.
- **Unit tests** (`test_*.py`, Python's `unittest`, nothing to install). They need no network: a fake GitLab API
  (`helpers.py`), throwaway git repositories with tags, and stand-in `docker`, `buf`, `abidiff` and `apt-get`.
- **Smoke tests** (`smoke.sh`, with `--smoke`, CI only): read-only checks that the pipeline's environment reaches this
  GitLab with git (release tags and the next release patch), Python (the API) and downloads (the newest dev set).

The "test ci" job runs `run.sh --smoke` whenever `ci/`, `gitlab/`, `build.sh` or `deploy/scripts/` change, and in tag
and scheduled pipelines. The release jobs and "publish dev set" wait for it, so a broken script never tags or publishes
anything. Run the unit tests locally with `gitlab/scripts/tests/run.sh` (needs `shellcheck` and `dpkg-deb`).

When changing a CI script, add or update its test in the same merge request.

## Required settings

| Setting | Where | Why |
|---|---|---|
| "Keep artifacts from most recent successful jobs" on (the default) | Settings → CI/CD → Artifacts | keeps the newest dev set until a newer one exists |
| Public pipelines on (the default for a public project) | Settings → CI/CD → General pipelines | `fetch-packages.py` downloads without a token; otherwise users export `GITLAB_TOKEN` |
| A nightly schedule on `main` with the variable `SYNC_COMPONENTS` = `true` | Build → Pipeline schedules | the full build and tests, a fresh dev set (a failed or stale component is retried, and the newest set does not expire), and the [sync](#sync) |
| `RELEASE_BOT_TOKEN`: Masked and hidden, Protected | Settings → CI/CD → Variables | the release jobs' GitLab API calls (an access token with the Maintainer role and the `api` and `write_repository` scopes) |
| Protected branches `main` and `release/*`: allowed to merge "Maintainers" and the token's user; push "No one" | Settings → Repository → Protected branches | the token's protected variable is only available there; the token's user creates `release/X.Y` |
| Protected tags `v*`: allowed to create "Maintainers" | Settings → Repository → Protected tags | only maintainers and the release jobs create release tags |
| Merge method "Merge commit" | Settings → Merge requests | "backport" cherry-picks the merge commit of a merged merge request |

## Later

Publishing releases to Nexus, and retiring the component repositories and the sync.
