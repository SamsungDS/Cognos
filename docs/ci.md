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

- `.rebuild-all` (`components/core`, `components/mgmt-fw`, `gitlab/`, `VERSION`): a change rebuilds every component.
- `.paths-<component>` (`cxl`, `slat`, `ras`, `me`, `node`, `sapp`, `amo-prof`, `deploy`, and `core`, `mgmt-fw`): a
  change rebuilds only that component.
- A `.rebuild-all` change does not run the amo-prof or deploy jobs; they run only when their own folder changes.
- Anything else (docs, the `cama` submodule bump) builds nothing; only "check version" runs.

## Stages and jobs

Stages: `build-images`, `build`, `test`, `scan`, `publish`, `release`.

| Job | Stage | Runs |
|---|---|---|
| check version | test | every pipeline; checks that `VERSION` is `MAJOR.MINOR` |
| build ansible image | build-images | `deploy/` changes, schedules and web runs |
| lint ansible | test | as "build ansible image", after it |

"check version" makes sure every merge request has a pipeline, which "Pipelines must succeed" requires.

## Operating systems

Components are built for ubuntu24 and ol10 only.

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

Later changes add component builds and unit tests, Sonar, dev sets, releases and the sync from the component
repositories.
