#!/usr/bin/env bash
# Deploys the whole Cognos stack to a management server and an application server with the playbooks, checks that
# it runs, then removes it and checks that nothing of it is left on either machine.
#
# Usage: deploy/scripts/test-deploy.sh --management <host> --application <host> --key <ssh key file> [--mock]
#
#   --management   host for the management_server group (controller, REST server)
#   --application  host for the application_server group (node, svc-mgr, cmmh driver, feature modules)
#   --key          SSH private key that logs in as root on both hosts
#   --mock         the cxl mock (for an application server without CXL devices)
#
# The packages must already be in deploy/artifacts/SVK/ (deploy/scripts/fetch-packages.py). Steps:
#   1. record each host's state: packages, systemd units, Cognos folders, users, ld.so.conf.d, ufw
#   2. playbooks/deploy_cognos.yml (it first removes any existing Cognos, then installs and starts)
#   3. check the services and the REST API (the start roles do not fail when a service does not start)
#   4. always, also when 2 or 3 failed: playbooks/remove_cognos.yml, purge every package the deploy added,
#      remove what ansible left behind
#   5. compare with 1: anything added and still there fails the run. Anything that was there before and is gone is
#      only reported (on the first run, for example, an older Cognos installation).
# Exit 0 only if the deploy, the checks and the cleanup all succeeded.
#
# Needs ansible (deploy/collections/requirements.yml installed) and ssh.
set -euo pipefail

DEPLOY=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
MANAGEMENT='' APPLICATION='' KEY='' MOCK=false

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
compgen -G "$DEPLOY/artifacts/SVK/cognos-*.deb" > /dev/null || die "no packages in deploy/artifacts/SVK (fetch-packages.py first)"

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
systemctl list-unit-files --no-legend 2> /dev/null | awk "{print \"unit \" \$1}"
for p in /etc/svk /usr/local/svk /var/log/svk /var/lib/svk /var/lib/influxdb /opt/installed /root/.ansible /root/logs; do
    [ -e "$p" ] && echo "path $p"
done
getent passwd | cut -d: -f1 | sed "s/^/user /"
ls /etc/ld.so.conf.d | sed "s/^/ldconf /"
command -v ufw > /dev/null && ufw status | sed "s/^/ufw /"
true'

state() {
    remote "$1" "$STATE_COMMAND" | sort -u
}

playbook() {
    (cd "$DEPLOY" && ansible-playbook -i "$INVENTORY" "playbooks/$1" \
        -e "{\"scmc_cxl_mock_enable\": $MOCK, \"cognos_install_gui_enabled\": false, \"cognos_rbac_enabled\": false}")
}

check_services() {
    local host=$1 unit ok=0
    shift
    for unit in "$@"; do
        if remote "$host" systemctl is-active --quiet "$unit"; then
            echo "  $host: $unit active"
        else
            echo "  $host: $unit NOT active"
            ok=1
        fi
    done
    return "$ok"
}

check() {
    local ok=0 code
    echo "== checking the deployment"
    check_services "$MANAGEMENT" cognos-controller cognos-restserver cognos-node || ok=1
    local app_units=(cognos-node cognos-svc-mgr)
    [[ $MOCK == true ]] || app_units=(cmmh_driver "${app_units[@]}")
    check_services "$APPLICATION" "${app_units[@]}" || ok=1
    code=$(remote "$MANAGEMENT" curl -s -o /dev/null -w '%{http_code}' --max-time 10 http://localhost:8001/ || true)
    if [[ -n $code && $code != 000 ]]; then
        echo "  $MANAGEMENT: REST API answers (HTTP $code)"
    else
        echo "  $MANAGEMENT: REST API does not answer on port 8001"
        ok=1
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
