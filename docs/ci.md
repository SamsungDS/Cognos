# Cognos CI

This page describes the repository-wide CI of the Cognos monorepo: which jobs a change gets, the guards that every merge request passes, and how to run the same selection locally.

All selection and guard logic is plain bash under `ci/`, with no dependency on a particular SCM. GitLab-specific configuration lives only in `gitlab/` and in the adapter `ci/scm/gitlab.sh`, which maps the GitLab variables to neutral `SCM_*` variables. Moving to another SCM means adding its wiring and an adapter, not rewriting the logic.

## Layout

| Path | Contents |
|---|---|
| `ci/selection.yml` | The single source of change-based selection. |
| `ci/lib/` | Shared helpers (`common.sh`) and the selection parser and change range (`selection.sh`). |
| `ci/scm/` | SCM adapters: `gitlab.sh`, and `fake.sh` for tests. |
| `ci/scripts/plan.sh` | Prints what a change selects (text, JSON or a GitHub matrix). |
| `ci/scripts/guards.sh` | The repository guards. |
| `ci/scripts/generate-gitlab.sh` | Renders the generated files under `gitlab/jobs/` from `gitlab/templates/`. |
| `ci/docker/ci-tools.DOCKERFILE` | The image of the plan and hygiene jobs. |
| `ci/tests/` | Offline tests of all of the above (`bash ci/tests/run_all.sh`). |
| `gitlab/.gitlab-ci.yml` | Pipeline entry point: workflow rules, stages, defaults and includes. |
| `gitlab/jobs/` | The jobs. `components.yml` and `ci-tools-image.yml` are generated; do not edit them. |
| `build.sh` | Repository-wide build entry point. Only `--plan` works yet. |

## Pipeline map

There is one pipeline per event and no child pipelines. Pipelines run for merge requests, pushes to `main` and `release/X.Y`, tags `vX.Y.Z`, schedules on `main` and runs from the web UI. Feature-branch pushes, other tags (such as the imported `core/v*` tags), branch creation, triggers and API pipelines do not run.

Stages: `.pre`, `plan`, `images`, `build`, `test`, `analysis`, `publish`, `release`. In this phase, the jobs are:

| Job | Stage | Runs |
|---|---|---|
| `images:ci-tools` | `.pre` | Every pipeline. Builds and pushes `$CI_REGISTRY_IMAGE/ci-tools:<hash>` only if that tag does not exist yet. The hash is the first 12 hex digits of the sha256 of `ci/docker/ci-tools.DOCKERFILE`, so an unchanged Dockerfile costs one manifest lookup. The job fails if the tag in `gitlab/jobs/ci-tools-image.yml` is not the hash of the Dockerfile, and it rebuilds only when the registry reports the manifest or the repository as unknown (the first run); any other registry error fails the job rather than overwriting a tag. It is the only job before the gate, because the gate runs in its image. |
| `plan` | `plan` | Every pipeline. The gate: runs `scm_env`, `plan.sh` and `guards.sh`, and keeps `plan.json`, `plan.txt` and `guards.txt` (the guard output, including why the gate failed) as artifacts for 30 days. |
| `images:deploy` | `images` | With `ansible-lint`. Builds the ansible-lint image from `deploy/scripts/docker/ubuntu22.DOCKERFILE` with `deploy/` as context. It runs after the gate, so a merge request that fails a guard pushes nothing. A merge request into `main` that passes the gate still pushes `ubuntu22-main` (and its cache tag), as the bootstrap pipeline did; see the known limitations under 'Project settings this CI relies on'. Merge requests into `release/X.Y` use the tag suffix `mr-<iid>`, because an image tag cannot contain `/`; pushes, schedules and web pipelines use the ref slug. |
| `ansible-lint` | `test` | When `deploy/` changes (merge requests, pushes to `main` and `release/X.Y`), nightly and from the web UI. Runs `ansible-lint` in `deploy/`. |
| `hygiene` | `test` | When `ci/`, `gitlab/`, `build.sh` or `VERSION` changes, and nightly. Runs `ci/tests/run_all.sh`, shellcheck over `ci/**` and `build.sh`, `generate-gitlab.sh --check`, and a CI Lint check of the commit's configuration if the job token may call the lint API (otherwise the log says `CI Lint NOT performed (HTTP <code>)`). The check is not a dry run: a simulated push has an all-zero previous commit, which the workflow rule for branch creation always rejects. |

A docs-only merge request therefore gets `images:ci-tools` and `plan` only.

Only merge-request jobs are interruptible. Jobs of `main`, `release/X.Y` and tag pipelines always run to the end.

The `ci-tools` image tag is written to `gitlab/jobs/ci-tools-image.yml` by `generate-gitlab.sh`. After changing the Dockerfile, run `bash ci/scripts/generate-gitlab.sh` and commit the result; the `hygiene` job fails if the file is stale, and `images:ci-tools` refuses to push under a tag that is not the Dockerfile's hash. The hash covers only the Dockerfile text: `FROM ubuntu:24.04` and the apt packages are not pinned, so the same tag can stand for different contents depending on when it was first built. Pinning the base image by digest (bump the digest, regenerate, commit) is a planned follow-up.

Schedules are told apart by the variable `SCHEDULE_KIND`; `nightly` is the only kind used in this phase. `plan.sh` does not read `SCHEDULE_KIND`: for every schedule it reports everything as selected, including amo-prof and ansible-lint, while the `ansible-lint` and `hygiene` jobs run only for `SCHEDULE_KIND=nightly`. For a schedule of another kind, `plan.json` therefore lists more than the pipeline runs.

## Selection

`ci/selection.yml` holds one hidden key, `.selection`, with a block list of path patterns per key. An entry is either an exact path or `<dir>/**/*` (everything under `<dir>/`). GitLab jobs use the lists through `rules:changes: !reference [.selection, <key>]`; `plan.sh` parses the same file, so both agree.

| Change | Selects |
|---|---|
| `components/core/**`, `components/mgmt-fw/**`, `VERSION`, `build.sh`, `ci/**`, `gitlab/**`, `.github/**` (platform) | All 8 package components: core, mgmt-fw, cxl, slat, ras, me, node, sapp. Not amo-prof. |
| `components/<x>/**` | Component `<x>`. |
| `apps/sapp/**` | sapp. |
| `profilers/amo-prof/**` | The amo-prof jobs only. |
| `deploy/**` | ansible-lint. |
| Anything else (`cama`, `.gitmodules`, `docs/`, `README.md`, `CHANGELOG.md`) | Nothing; only the plan runs. |

`plan.sh` compares `git diff --name-only <merge-base>..<head>`, without rename collapsing, so moving a file out of a component still selects that component. The base is `--base`, else the merge-request diff base, else the commit before a push. In merged-results and merge-train pipelines the commit under test is a temporary merge of the merge request onto the target branch, so the adapter uses the target branch head as the base instead of the fork point; otherwise everything merged into the target since the fork would count as part of the merge request. If there is no base, the base is all zeros or not reachable, or the pipeline is a schedule, tag or web pipeline, everything is selected (the 8 components, amo-prof and ansible-lint), as GitLab does for `rules:changes` in those cases. A tag pipeline (whatever started it: push, API or trigger) is the exception: it selects the 8 components but not amo-prof or ansible-lint, because those jobs do not run on tags; the JSON output gives the reason under `not_selected`.

Run the selection locally:

```bash
./build.sh --plan                         # changes since the merge base with origin/main
./build.sh --plan --base <ref> --format json
bash ci/scripts/plan.sh --base <ref> --head <ref> --format github-matrix
```

With no component selected, `--format github-matrix` prints `{"include":[]}`. GitHub Actions rejects an empty matrix, so a workflow must check for an empty selection before it uses the matrix.

Conventions for using the lists: `changes: !reference [.selection, <key>]` sits directly in a job's own `rules`, and a `!reference` is not combined with other paths in one `changes` list. A job that needs two lists (for example platform or `<x>`) uses one rule per list. Jobs share such rules through YAML anchors within one file; anchors are used for simplicity.

The JSON output lists the selected components, the `amo_prof` and `ansible_lint` flags, the reason for each selection and the changed files.

## Guards

`guards.sh` runs in the plan job. Each failing guard prints its reason and the offending paths, and the plan job fails.

| Guard | Applies to | Fails when |
|---|---|---|
| (a) Transition | Merge requests | The change touches `components/**`, `apps/sapp/**` or `profilers/amo-prof/**`. Source branches `sync/*` and `backport/*` of this project are exempt; the same branch names in a fork are not. |
| (b) VERSION and CHANGELOG.md | Merge requests | A merge request into `main` changes `VERSION` or `CHANGELOG.md` and its source branch is not `release-bot/next` of this project; or any merge request into `release/*` changes `VERSION`. No branch is exempt. |
| (c) Release bot content | Merge requests from `release-bot/next` | Anything other than `VERSION` and `CHANGELOG.md` changes, or the new `VERSION` (X.Y) is not greater than the latest release line (the highest `vX.Y.Z` tag, else `VERSION` at the merge base). The log says which source the release line came from. |
| (d) Conflict markers | Every pipeline with a diff | An added line starts with `<<<<<<<` or `>>>>>>>` followed by a space, a carriage return (files with CRLF endings) or the end of the line. Conflicted backports are committed with their markers, and this guard keeps them red until they are resolved. The diff is read with fixed `a/` and `b/` prefixes, so the user's git diff settings cannot hide a file, and a marker whose file name cannot be read is reported as `<unknown file>`. |

### Lifting the transition guard

Until cut-over, the components are owned by their own repositories and reach this repository only through `sync/*` merge requests. The transition guard enforces that. To lift it at cut-over, set the CI/CD variable `MONOREPO_OWNS_COMPONENTS` to `true` in the project settings (not protected, so merge-request pipelines can read it). Unset, or any other value, keeps the guard active.

## Project settings this CI relies on

The code cannot enforce the following; they are project settings that a maintainer must apply in GitLab. Until they are applied, the guards can be bypassed.

1. **Protect the branches `sync/*`, `backport/*` and `release-bot/next`** (Settings > Repository > Protected branches) so that only maintainers or the bot accounts can push to them. The guard exemptions trust the source branch name, so anyone who can create such a branch in this project gets the exemption.
2. **Turn on "Pipelines must succeed"** (Settings > Merge requests > Merge checks). Without it, the plan job is only advisory and a merge request that fails a guard can still be merged.
3. **Require maintainer or code-owner approval for changes to `ci/**`, `gitlab/**`, `build.sh` and `VERSION`.** A merge request runs its own copy of the gate (`guards.sh`, the job rules, the `MONOREPO_OWNS_COMPONENTS` default), so a change to these files can weaken the gate for that same merge request. Only a review stops that. (No CODEOWNERS file is added in this phase.)
4. **Known limitation, to resolve before any phase gives a ci-tools job a secret:** a merge-request pipeline can push, and so overwrite, a `ci-tools:<hash>` tag that other pipelines use. The planned mitigation is a protected container tag rule for `ci-tools:*`, or merge-request-scoped tags.
   **Known limitation, inherited from the bootstrap pipeline:** a merge request into `main` that changes `deploy/` and passes the gate pushes `ubuntu22-main` and `ubuntu22-main-cache`, the image that `main`'s `ansible-lint` pulls, before the merge request is merged. The planned fix is merge-request-scoped tags, as merge requests into `release/X.Y` already use.
5. **Merge a merge request from a fork only after its pipeline has run in this project.** This project is public. A fork merge request runs its pipeline in the fork, with the fork's CI configuration path and the fork's CI/CD variables (for example `MONOREPO_OWNS_COMPONENTS=true`), so a green fork pipeline can satisfy "Pipelines must succeed" without this project's gate ever running. A maintainer must run the pipeline in this project ('Run pipeline' on the merge request) before merging, or the project must restrict forking or the merging of fork merge requests. Parent-project pipelines for fork merge requests run with this project's variables, so they will see any secrets that later phases add; review the change before running one.

`MONOREPO_OWNS_COMPONENTS` (see above) is the only CI/CD variable this phase reads. This phase uses no secrets.

## Local verification

```bash
bash ci/tests/run_all.sh
find ci -type f -name '*.sh' -print0 | xargs -0 shellcheck -x build.sh
bash ci/scripts/generate-gitlab.sh --check
./build.sh --plan --base origin/main
```

The tests build their fixture repositories in a temporary directory, need no network and finish in seconds. They need bash, git, jq and python3 with the yaml module.

`ci/tests/pipeline_rules_test.sh` models the job rules of merge-request and push pipelines only; schedule, web and tag pipelines are covered by CI Lint and the pipelines themselves.

The suite also checks the CI files themselves: LF line endings, mode 100755 in the git index for every script (a script that is not added to git fails), `set -euo pipefail` in every executed script, and no `set -x`. The modes are read from the index, not the disk, so stage new scripts with `git add --chmod=+x <file>`.

## Registry probe results

Verified on 2026-10-27 against this project (GitLab EE 18.6.2). These results decide how later phases store packages.

- Generic package versions reject `~` (HTTP 400). Registry versions therefore use the form `1.7.0-dev.N.g<sha8>`, while the packages themselves keep `~` in their own version.
- Generic package file names may contain `~`: upload and download were verified, with an identical checksum. Packages keep their real file names.
- Package protection rules are supported for generic packages (`POST /projects/:id/packages/protection/rules` with `package_type: generic` returned 201). The fallback of a separate store project is therefore not needed.

## Roadmap

Later phases add per-component builds with a content-addressed package cache and per-commit stack manifests, unit tests, Sonar, compatibility checks, the release bot and the sync from the individual repositories. The integration stage (deploying the latest stack to a dedicated VM and running integration tests) is deferred.
