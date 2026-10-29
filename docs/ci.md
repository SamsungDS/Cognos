# CI

| File | What it does | Depends on GitLab |
|---|---|---|
| `gitlab/.gitlab-ci.yml` | when jobs run, and which CI variables are passed to the scripts | yes |
| `build.sh` | builds or tests components, locally (Docker) or in CI (`--native`) | no |
| `ci/version.sh` | prints the one version of a build | no |
| `ci/image.sh` | builds a component image, or reuses it when its inputs are unchanged | no |

One pipeline per event, no child pipelines. `gitlab/.gitlab-ci.yml` has five sections: includes and workflow, what a
change rebuilds, job templates, one block per component with all of its jobs, and other jobs.

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
- Anything else (docs, the `cama` submodule bump) builds nothing; only "check version" runs.
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
When "build core" or "build mgmt-fw" ran in the same pipeline, the job installs its packages from the artifacts and
logs `upstream core: pipeline <version>`. Otherwise it uses the Nexus packages in the image and logs
`upstream core: image <version>`.

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

## Planned: dev sets

- Every merge to `main`, and every nightly, produces a set. Its version is `X.(Y+1).0~dev.<pipeline iid>` in package
  file names and deb/rpm versions, and `X.(Y+1).0-dev.<pipeline iid>` as the registry version.
- Packages built in that pipeline carry the set version. Unchanged components are not rebuilt and keep the version of
  their last build.
- `cognos-dev-set/X.(Y+1).0-dev.<iid>/set.json` pins the exact package file, version and sha256 of every component
  and OS. `latest.json` points to the newest set.
- Deploying a set installs exactly the pinned versions, so hosts upgrade and restart only the changed components.
- A release rebuilds every component at `X.Y.Z`.

Package registry facts (GitLab 18.6):

- Generic package versions reject `~`, so registry versions use `-dev.N` (for example `1.7.0-dev.12`).
- File names may contain `~`.
- Generic package protection rules are available.

## Later

Dev sets and deploy, releases, and the sync from the component repositories.
