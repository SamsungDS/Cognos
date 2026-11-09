#!/usr/bin/env bash
# Deploys the whole Cognos stack to a management server and an application server with the playbooks, checks that
# it runs, then removes it and checks that nothing of it is left on either machine.
#
# Usage: deploy/ansible/scripts/test-deploy.sh --management <host> --application <host> --key <ssh key file> [--mock]
#
#   --management   host for the management_server group (controller, REST server)
#   --application  host for the application_server group (node, svc-mgr, cmmh driver, feature modules)
#   --key          SSH private key that logs in as root on both hosts
#   --mock         the cxl mock (for an application server without CXL devices)
#
# The packages must already be in deploy/ansible/artifacts/SVK/ (deploy/ansible/scripts/fetch-packages.py). Steps:
#   1. record each host's state: packages, systemd units, Cognos folders, users, ld.so.conf.d, ufw
#   2. playbooks/deploy_cognos.yml (it first removes any existing Cognos, then installs and starts)
#   3. wait CHECK_WAIT seconds (default 10), then check, retrying each check for up to CHECK_TIMEOUT seconds
#      (default 60): the controller and the REST server run on the management server, the node, svc-mgr and the
#      cmmh driver on the application server, and the application server reaches the management server's controller
#      (port 9999) and REST API (port 8001). The start roles do not fail when a service does not start.
#   4. always, also when 2 or 3 failed: playbooks/remove_cognos.yml, purge every package the deploy added,
#      remove what ansible left behind
#   5. compare with 1: anything added and still there fails the run. Anything that was there before and is gone is
#      only reported (on the first run, for example, an older Cognos installation).
# Exit 0 only if the deploy, the checks and the cleanup all succeeded.
#
# Before step 1 it installs the ansible collections (deploy/ansible/collections/requirements.yml) from Ansible Galaxy, with
# retries: the lab network drops connections now and then. If that fails, the hosts are not touched.
#
# Needs ansible and ssh. COLLECTION_RETRY_DELAY (seconds between attempts, default 30) and CHECK_INTERVAL (seconds
# between check attempts, default 5) are for the tests.
set -euo pipefail

DEPLOY=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
MANAGEMENT='' APPLICATION='' KEY='' MOCK=false
CHECK_WAIT=${CHECK_WAIT:-10} CHECK_TIMEOUT=${CHECK_TIMEOUT:-60} CHECK_INTERVAL=${CHECK_INTERVAL:-5}

die() {
    echo "test-deploy.sh: $*" >&2
    exit 1
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --management | --application | --key)
            [[ $# -ge 2 ]] || die "$1 needs a value"
            case $1 in
                --management) MANAGEMENT=$2 ;;
                --application) APPLICATION=$2 ;;
                --key) KEY=$2 ;;
            esac
            shift
            ;;
        --mock) MOCK=true ;;
        -h | --help)
            sed -n '2,/^set -euo/p' "${BASH_SOURCE[0]}" | sed '$d; s/^# \{0,1\}//'
            exit 0
            ;;
        *) die "unknown option $1" ;;
    esac
    shift
done
[[ -n $MANAGEMENT && -n $APPLICATION && -f $KEY ]] || die "--management, --application and --key are required (see -h)"
compgen -G "$DEPLOY/artifacts/SVK/cognos-*.deb" > /dev/null || die "no packages in deploy/ansible/artifacts/SVK (fetch-packages.py first)"

WORK=$(mktemp -d)
INVENTORY="$DEPLOY/hosts.test-deploy"   # next to group_vars/ and artifacts/, which the playbooks find from it
SSH_OPTIONS=(-o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=20 -o StrictHostKeyChecking=accept-new
    -o "UserKnownHostsFile=$WORK/known_hosts")
HOSTS=("$MANAGEMENT" "$APPLICATION")

remote() {
    local host=$1
    shift
    ssh -i "$KEY" "${SSH_OPTIONS[@]}" "root@$host" "$@"
}

# Runs on the host, so its $ are not expanded here. One line per trace: "pkg <name>" (any dpkg state but
# not-installed), "unit", "path", "user", "ldconf", "ufw".
# shellcheck disable=SC2016
STATE_COMMAND='dpkg-query -W -f "\${db:Status-Abbrev}|\${Package}\n" | awk -F"|" "\$1 !~ /^[up]n/ {print \"pkg \" \$2}"
systemctl list-unit-files --no-legend 2> /dev/null | awk "\$2 != \"transient\" {print \"unit \" \$1}"
for p in /etc/svk /usr/local/svk /var/log/svk /var/lib/svk /var/lib/influxdb /opt/installed /root/.ansible /root/logs; do
    [ -e "$p" ] && echo "path $p"
done
getent passwd | cut -d: -f1 | sed "s/^/user /"
ls /etc/ld.so.conf.d | sed "s/^/ldconf /"
command -v ufw > /dev/null && ufw status | sed "s/^/ufw /"
true'

# Login sessions (session-N.scope) and transient runs (run-*.scope) come and go with every ssh connection,
# including ours: not a trace of the deployment.
state() {
    remote "$1" "$STATE_COMMAND" | grep -vE '^unit (session-[0-9]+|run-[^ ]+)\.scope$' | sort -u
}

# ANSIBLE_CONFIG explicitly: ansible ignores an ansible.cfg in a world-writable directory, which a CI checkout
# can be, and without it does not find deploy/ansible/roles.
playbook() {
    (cd "$DEPLOY" && ANSIBLE_CONFIG="$DEPLOY/ansible.cfg" ansible-playbook -i "$INVENTORY" "playbooks/$1" \
        -e "{\"scmc_cxl_mock_enable\": $MOCK, \"cognos_install_gui_enabled\": false, \"cognos_rbac_enabled\": false}")
}

# Retries "$@" every CHECK_INTERVAL seconds until it succeeds or CHECK_TIMEOUT seconds have passed: services take
# a while to come up after the playbook started them.
eventually() {
    local deadline=$((SECONDS + CHECK_TIMEOUT))
    until "$@"; do
        [[ $SECONDS -lt $deadline ]] || return 1
        sleep "$CHECK_INTERVAL"
    done
}

check_services() {
    local host=$1 unit ok=0
    shift
    for unit in "$@"; do
        if eventually remote "$host" systemctl is-active --quiet "$unit"; then
            echo "  $host: $unit active"
        else
            echo "  $host: $unit NOT active after ${CHECK_TIMEOUT} s; its last journal lines:"
            remote "$host" journalctl -u "$unit" -n 20 --no-pager | indent || true
            ok=1
        fi
    done
    return "$ok"
}

# Any HTTP answer from the REST server at $1, as the application server sees it; sets code.
rest_answers() {
    code=$(remote "$APPLICATION" curl -s -o /dev/null -w '%{http_code}' --max-time 10 "http://$1:8001/" || true)
    [[ -n $code && $code != 000 ]]
}

# The application server connects to the management server's controller (gRPC) and REST server. Both listen on
# the management server's default IPv4 address (ansible_default_ipv4 in the start roles), not on localhost.
reach() {
    local address=$1 code
    if eventually remote "$APPLICATION" timeout 5 bash -c "'exec 3<> /dev/tcp/$address/9999'"; then
        echo "  $APPLICATION -> $MANAGEMENT ($address): controller port 9999 reachable"
    else
        echo "  $APPLICATION -> $MANAGEMENT ($address): controller port 9999 NOT reachable"
        return 1
    fi
    if eventually rest_answers "$address"; then
        echo "  $APPLICATION -> $MANAGEMENT ($address): REST API answers on port 8001 (HTTP $code)"
    else
        echo "  $APPLICATION -> $MANAGEMENT ($address): REST API does NOT answer on port 8001"
        return 1
    fi
}

check() {
    local ok=0 address
    echo "== waiting ${CHECK_WAIT} s for the services to come up"
    sleep "$CHECK_WAIT"
    echo "== checking the deployment"
    # The management server runs the controller and the REST server; the node runs on the application server.
    check_services "$MANAGEMENT" cognos-controller cognos-restserver || ok=1
    local app_units=(cognos-node cognos-svc-mgr)
    [[ $MOCK == true ]] || app_units=(cmmh_driver "${app_units[@]}")
    check_services "$APPLICATION" "${app_units[@]}" || ok=1
    address=$(remote "$MANAGEMENT" ip -4 route get 1.1.1.1 | sed -n 's/.* src \([0-9.]*\).*/\1/p')
    if [[ -z $address ]]; then
        echo "  $MANAGEMENT: could not find its default IPv4 address"
        ok=1
    else
        reach "$address" || ok=1
    fi
    return "$ok"
}

indent() {
    sed 's/^/    /'
}

RESULT=0
cleanup() {
    local host before after added removed status=0
    set +e
    trap - EXIT INT TERM
    echo "== removing the deployment"
    playbook remove_cognos.yml || status=1
    for host in "${HOSTS[@]}"; do
        before="$WORK/$host.before"
        [[ -s $before ]] || continue
        after=$(state "$host")
        added=$(comm -13 "$before" <(echo "$after") | sed -n 's/^pkg //p' | tr '\n' ' ')
        if [[ -n ${added// /} ]]; then
            echo "  $host: purging packages the deployment added: $added"
            # shellcheck disable=SC2086
            remote "$host" "DEBIAN_FRONTEND=noninteractive apt-get purge -y -q $added" > "$WORK/$host.purge" 2>&1 \
                || { cat "$WORK/$host.purge"; status=1; }
        fi
        # What ansible itself leaves: its temporary folder, unless it was there before.
        grep -qx 'path /root/.ansible' "$before" || remote "$host" rm -rf /root/.ansible
        after=$(state "$host")
        added=$(comm -13 "$before" <(echo "$after"))
        removed=$(comm -23 "$before" <(echo "$after"))
        if [[ -n $added ]]; then
            echo "  $host: LEFT BEHIND by the deployment:"
            indent <<< "$added"
            status=1
        else
            echo "  $host: nothing of the deployment is left"
        fi
        [[ -z $removed ]] || { echo "  $host: there before, gone now (not an error):"; indent <<< "$removed"; }
    done
    rm -f "$INVENTORY"
    rm -rf "$WORK"
    [[ $status -eq 0 ]] || RESULT=1
    echo "== result: $([[ $RESULT -eq 0 ]] && echo "deployed, checked and removed cleanly" || echo FAILED)"
    exit "$RESULT"
}

cat > "$INVENTORY" << EOF
[management_server]
$MANAGEMENT

[application_server]
$APPLICATION

[all:vars]
ansible_user=root
ansible_ssh_private_key_file=$KEY
ansible_ssh_common_args='-o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=$WORK/known_hosts'
EOF

echo "== installing the ansible collections"
attempt=1
until (cd "$DEPLOY" && ANSIBLE_CONFIG="$DEPLOY/ansible.cfg" ansible-galaxy collection install \
    -r collections/requirements.yml); do
    if [[ $attempt -ge 3 ]]; then
        rm -f "$INVENTORY"
        die "could not install the ansible collections from Ansible Galaxy after 3 attempts; the hosts were not touched"
    fi
    echo "attempt $attempt failed; retrying in ${COLLECTION_RETRY_DELAY:-30} s"
    sleep "${COLLECTION_RETRY_DELAY:-30}"
    attempt=$((attempt + 1))
done

echo "== recording the state of ${HOSTS[*]}"
for host in "${HOSTS[@]}"; do
    state "$host" > "$WORK/$host.before"
    echo "  $host: $(grep -c '^pkg ' "$WORK/$host.before") packages"
done
trap cleanup EXIT
trap 'RESULT=1; exit 1' INT TERM

echo "== deploying"
playbook deploy_cognos.yml || { echo "deploy_cognos.yml failed"; RESULT=1; exit 1; }
check || { echo "the deployment does not run"; RESULT=1; exit 1; }
