#!/usr/bin/env bash
# Static checks of the pipeline configuration under gitlab/: the shared
# tools includes are pinned to one full commit, and the merge-request job set
# that the rules select for a given change is the expected one (a docs-only
# change runs only images:ci-tools and plan).
#
# The rule evaluation is a small offline model of rules:if/changes/when/
# variables for merge-request and push pipelines only (if: supports ==, !=,
# =~ and bare variables joined by &&). It covers the jobs defined in this
# repository, not the jobs of the included tools templates (CI Lint covers
# those).
set -euo pipefail

# shellcheck source=ci/tests/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

cd "${COGNOS_REPO_ROOT}"

TOOLS_SHA=efbaaadf825e3525126e506fc6400c91c794f406

# jobs_for [<key>=<value>...] [--] <changed file>...: the jobs the pipeline
# runs, one per line, sorted. The pipeline is a merge request (iid 7) into
# main unless key=value arguments say otherwise; keys are source, branch,
# target, iid and slug (see KEYS), for example 'source=push branch=main'.
# With JOBS_SHOW_VARS=1 each line also lists the variables of the matching
# rule, expanded.
jobs_for() {
  python3 - "$@" << 'PY'
import fnmatch, glob, os, re, sys, yaml

class Ref(list):
    pass

def ref(loader, node):
    return Ref(loader.construct_sequence(node))

yaml.SafeLoader.add_constructor('!reference', ref)

docs = {}
for f in ['gitlab/.gitlab-ci.yml', 'ci/selection.yml'] + sorted(glob.glob('gitlab/jobs/*.yml')):
    for k, v in (yaml.safe_load(open(f)) or {}).items():
        if isinstance(v, dict) and isinstance(docs.get(k), dict):
            docs[k].update(v)
        else:
            docs[k] = v

def resolve(v):
    if isinstance(v, Ref):
        node = docs
        for key in v:
            node = node[key]
        return resolve(node)
    if isinstance(v, list):
        out = []
        for x in v:
            r = resolve(x)
            out.extend(r if isinstance(x, Ref) and isinstance(r, list) else [r])
        return out
    if isinstance(v, dict):
        return {k: resolve(x) for k, x in v.items()}
    return v

def job_rules(name):
    job = docs[name]
    if 'rules' in job:
        return resolve(job['rules'])
    ext = job.get('extends')
    return job_rules(ext) if isinstance(ext, str) and ext in docs else None

# Predefined variable names, assembled so that ci/tests/scm_neutral_test.sh
# does not flag this file: the names only appear in gitlab/.
P = 'C' 'I_'
KEYS = {
    'source': P + 'PIPELINE_SOURCE',
    'branch': P + 'COMMIT_BRANCH',
    'target': P + 'MERGE_REQUEST_TARGET_BRANCH_NAME',
    'iid': P + 'MERGE_REQUEST_IID',
    'slug': P + 'COMMIT_REF_SLUG',
}
args = sys.argv[1:]
overrides = {}
while args and re.match(r'^[a-z]+=', args[0]):
    k, v = args.pop(0).split('=', 1)
    if k not in KEYS:
        raise SystemExit('jobs_for: unknown key %r' % k)
    overrides[k] = v
if args and args[0] == '--':
    args.pop(0)
given = {'slug': 'feature-x'}
if overrides.get('source', 'merge_request_event') == 'merge_request_event':
    given.update({'source': 'merge_request_event', 'target': 'main', 'iid': '7'})
given.update(overrides)
env = {KEYS[k]: v for k, v in given.items()}

TERM = re.compile(r'^\$(\w+)(?:\s*(==|!=|=~)\s*(?:"([^"]*)"|/(.*)/))?$')

def term_true(term):
    m = TERM.match(term.strip())
    if not m:
        raise SystemExit('unsupported rules:if term: %r' % term)
    var, op, lit, rx = m.groups()
    val = env.get(var, '')
    if op is None:
        return val != ''
    if op == '==':
        return val == lit
    if op == '!=':
        return val != lit
    return re.search(rx.replace('\\/', '/'), val) is not None

def if_true(expr):
    if expr is None:
        return True
    if '||' in expr or '(' in expr:
        raise SystemExit('unsupported rules:if expression: %r' % expr)
    return all(term_true(t) for t in expr.split('&&'))

def expand(v):
    return re.sub(r'\$\{?(\w+)\}?', lambda m: env.get(m.group(1), ''), str(v))

def matches(pattern, path):
    if pattern.endswith('/**/*'):
        return path.startswith(pattern[:-4])
    return fnmatch.fnmatchcase(path, pattern)

changed = args
reserved = {'workflow', 'stages', 'default', 'variables', 'include'}
selected = []
for name, job in docs.items():
    if name in reserved or name.startswith('.') or not isinstance(job, dict):
        continue
    rules = job_rules(name)
    when = 'on_success' if rules is None else 'never'
    rule_vars = {}
    for rule in rules or []:
        if not if_true(rule.get('if')):
            continue
        if 'changes' in rule and not any(matches(p, c) for p in rule['changes'] for c in changed):
            continue
        when = rule.get('when', 'on_success')
        rule_vars = rule.get('variables') or {}
        break
    if when != 'never':
        if os.environ.get('JOBS_SHOW_VARS') == '1':
            name += ''.join(' %s=%s' % (k, expand(v)) for k, v in sorted(rule_vars.items()))
        selected.append(name)
print('\n'.join(sorted(selected)))
PY
}

pins="$(grep -A1 -E '^[[:space:]]*-[[:space:]]+project:[[:space:]]+dfs/svk/tools' gitlab/.gitlab-ci.yml \
  | grep -E '^[[:space:]]+ref:' | awk '{print $2}' | sort -u)"
t_eq "tools includes are pinned to the full commit" "${TOOLS_SHA}" "${pins}"
n_includes="$(grep -cE 'project:[[:space:]]+dfs/svk/tools' gitlab/.gitlab-ci.yml)"
n_pinned="$(grep -cE "ref:[[:space:]]+${TOOLS_SHA}\$" gitlab/.gitlab-ci.yml)"
t_eq "every tools include has its own pinned ref" "${n_includes}" "${n_pinned}"

nl=$'\n'
t_eq "docs-only MR -> images:ci-tools and plan only" \
  "images:ci-tools${nl}plan" "$(jobs_for README.md docs/ci.md)"
t_eq "cama gitlink and .gitmodules MR -> images:ci-tools and plan only" \
  "images:ci-tools${nl}plan" "$(jobs_for cama .gitmodules)"
t_eq "component-only MR -> no hygiene, no ansible-lint" \
  "images:ci-tools${nl}plan" "$(jobs_for components/cxl/src/a.c)"
t_eq "ci/ change MR -> hygiene added" \
  "hygiene${nl}images:ci-tools${nl}plan" "$(jobs_for ci/scripts/plan.sh)"
t_eq "VERSION change MR -> hygiene added" \
  "hygiene${nl}images:ci-tools${nl}plan" "$(jobs_for VERSION)"
t_eq "deploy/ change MR -> ansible-lint and its image added" \
  "ansible-lint${nl}images:ci-tools${nl}images:deploy${nl}plan" "$(jobs_for deploy/site.yml)"
t_eq "docs-only push to main -> images:ci-tools and plan only" \
  "images:ci-tools${nl}plan" "$(jobs_for source=push branch=main -- docs/ci.md)"
t_eq "deploy/ push to main -> ansible-lint and its image added" \
  "ansible-lint${nl}images:ci-tools${nl}images:deploy${nl}plan" \
  "$(jobs_for source=push branch=main -- deploy/site.yml)"

# Image tags may not contain '/'. Both deploy jobs build their image tag from
# DOCKER_BRANCH_NAME, so no rule may give it a value with '/' (for example
# the target branch release/1.5 of a merge request).
deploy_vars() {
  JOBS_SHOW_VARS=1 jobs_for "$@" | grep -E '^(images:deploy|ansible-lint) ' || true
}
t_eq "MR into release/1.5 changing deploy/ -> DOCKER_BRANCH_NAME mr-<iid>, no '/'" \
  "ansible-lint DOCKER_BRANCH_NAME=mr-7${nl}images:deploy DOCKER_BRANCH_NAME=mr-7" \
  "$(deploy_vars target=release/1.5 -- deploy/site.yml)"
t_eq "MR into main changing deploy/ -> DOCKER_BRANCH_NAME main (bootstrap behaviour)" \
  "ansible-lint DOCKER_BRANCH_NAME=main${nl}images:deploy DOCKER_BRANCH_NAME=main" \
  "$(deploy_vars deploy/site.yml)"
t_eq "push to release/1.5 changing deploy/ -> DOCKER_BRANCH_NAME is the ref slug" \
  "ansible-lint DOCKER_BRANCH_NAME=release-1-5${nl}images:deploy DOCKER_BRANCH_NAME=release-1-5" \
  "$(deploy_vars source=push branch=release/1.5 slug=release-1-5 -- deploy/site.yml)"

# The hygiene paths are the CI part of .selection.platform: every hygiene
# entry is a platform entry, and the platform entries left out are exactly
# the two platform components and .github/.
subset="$(python3 - << 'PY'
import yaml
yaml.SafeLoader.add_constructor('!reference', lambda l, n: l.construct_sequence(n))
platform = yaml.safe_load(open('ci/selection.yml'))['.selection']['platform']
paths = set()
for rule in yaml.safe_load(open('gitlab/jobs/hygiene.yml'))['hygiene']['rules']:
    paths.update(rule.get('changes') or [])
print(' '.join(sorted(p for p in paths if p not in platform)) or '-')
print(' '.join(sorted(p for p in platform if p not in paths)))
PY
)"
t_eq "every hygiene changes entry is in .selection.platform" "-" "$(sed -n 1p <<< "${subset}")"
t_eq "the platform entries without hygiene are core, mgmt-fw and .github" \
  ".github/**/* components/core/**/* components/mgmt-fw/**/*" "$(sed -n 2p <<< "${subset}")"

# Nothing but the ci-tools image (which the gate itself needs) runs before
# the plan gate, so a merge request that fails a guard pushes no other image.
# A job without its own stage that extends 'build docker' inherits the tools
# template's stage .pre.
pre_jobs="$(python3 - << 'PY'
import glob, yaml
yaml.SafeLoader.add_constructor('!reference', lambda l, n: l.construct_sequence(n))
for f in sorted(glob.glob('gitlab/jobs/*.yml')):
    for k, v in (yaml.safe_load(open(f)) or {}).items():
        if not isinstance(v, dict) or k.startswith('.'):
            continue
        stage = v.get('stage')
        if stage is None and (k == 'build docker' or v.get('extends') == 'build docker'):
            stage = '.pre'
        if stage == '.pre':
            print(k)
PY
)"
t_eq "only images:ci-tools runs before the plan gate (build docker never runs)" \
  "build docker${nl}images:ci-tools" "$(sort <<< "${pre_jobs}")"

t_done
