# CI

The pipeline is defined in `gitlab/.gitlab-ci.yml`. It is plain GitLab YAML: one pipeline per event, no child
pipelines.

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

Path lists are hidden keys in `gitlab/.gitlab-ci.yml`, used by jobs through `rules:changes`.

- `.rebuild-all` (`components/core`, `components/mgmt-fw`, `gitlab/`, `VERSION`, `build.sh`): a change rebuilds every component.
- `.paths-<component>` (`cxl`, `slat`, `ras`, `me`, `node`, `sapp`, `amo-prof`, `deploy`, and `core`, `mgmt-fw`): a
  change rebuilds only that component.
- A `.rebuild-all` change does not run the amo-prof or deploy jobs; they run only when their own folder changes.
- Anything else (docs, the `cama` submodule bump) builds nothing; only "check version" runs.

## Stages and jobs

Stages: `build-images`, `build`, `test`, `scan`, `publish`, `release`.

| Job | Stage | Runs |
|---|---|---|
| check version | test | every pipeline; checks that `VERSION` is `MAJOR.MINOR` |
| build \<component\> image | build-images | see [Builds](#builds) |
| build \<component\> | build | as its image job, after it |
| build ansible image | build-images | `deploy/` changes, schedules and web runs |
| lint ansible | test | as "build ansible image", after it |

"check version" makes sure every merge request has a pipeline, which "Pipelines must succeed" requires.

## Operating systems

Components are built for ubuntu24 and ol10 only.

## Builds

Components: core, mgmt-fw, node, ras, slat, me, cxl and sapp (cama and amo-prof are not built here).

- "build \<component\> image" builds the component's own `scripts/docker/<os>.DOCKERFILE`, with the component
  directory as the context, and pushes `$CI_REGISTRY/$CI_PROJECT_PATH/<component>:<os>-<ref slug>` and
  `:<os>-<short sha>`.
- "build \<component\>" runs `./build.sh --native <component> --os <os>` in the image of its commit
  (`<os>-<short sha>`), so overlapping pipelines on one ref never use each other's image. Its packages are job
  artifacts under `<component dir>/build/artifacts/<os>/` for 14 days.
- Both run for every tag, schedule and web run, and in merge requests and pushes when `.rebuild-all` or the
  component's own path list changes. A change only under `components/cxl/` runs only "build cxl image" and
  "build cxl".
- Each job runs on ubuntu24 and ol10. "build cxl" also runs both variants, release (`cognos-cxl`) and mock
  (`cognos-cxl-mock`).

Every package built in a pipeline carries the same version, `COGNOS_VERSION`, which each build job prints. `X.Y` is
`VERSION`:

| Pipeline | Version |
|---|---|
| tag `vX.Y.Z` | `X.Y.Z` |
| `main`, and schedules or web runs on other branches | `X.(Y+1).0~dev.<pipeline iid>` |
| `release/X.Y` | `X.Y.(P+1)~rc.<pipeline iid>`, P is the highest `vX.Y.P` tag (none: `X.Y.0~rc.<iid>`); fails if `VERSION` is not `X.Y` |
| merge request | `X.(Y+1).0~dev.0.mr<mr iid>.<pipeline iid>` |
| local `./build.sh` | the `vX.Y.Z` tag on HEAD, else `X.(Y+1).0~dev.0.local` |

The components' `scripts/get_version.sh` print `v$COGNOS_VERSION` when it is set, and use `git describe` otherwise.
Inside this repository `git describe` finds the imported tags, so build a component through the root `build.sh`, or
export `COGNOS_VERSION` first.

Upstream packages: every component except core and sapp builds against core, and cxl and me also against mgmt-fw.
When "build core" or "build mgmt-fw" ran in the same pipeline, the build installs its packages from the artifacts and logs
`upstream core: pipeline <version>`. Otherwise it uses the Nexus packages in the image and logs
`upstream core: image <version>`.

To build locally:

```bash
./build.sh                          # all components, ubuntu24, each in a Docker container
./build.sh --os ol10 core mgmt-fw   # only these, in dependency order
./build.sh --mock cxl               # the cxl mock variant
./build.sh --native node            # on this machine; it must run that OS with node's dependencies installed
./build.sh -h
```

The packages end up in `build/artifacts/<os>/`. The component Dockerfiles install dependencies from the internal
Nexus, so a local Docker build needs the lab network.

## Versions

`VERSION` holds `MAJOR.MINOR` of the current release line. Release tags are `vX.Y.Z`.

Planned, from the dev-set phase on:

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

Later changes add unit tests, Sonar, dev sets, releases and the sync from the component
repositories.
