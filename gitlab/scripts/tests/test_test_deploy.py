"""deploy/scripts/test-deploy.sh with stand-in ssh and ansible-playbook: the order of the steps, that the cleanup
always runs, and that anything the deployment leaves behind fails the run."""

import shutil
import unittest

from helpers import REPO, TempDirTestCase, sh

# Stand-in ssh: the host is the root@ argument; the remote command decides the answer. A host's state is
# $FAKE/<host>.before until remove_cognos.yml ran, then $FAKE/<host>.removed, then $FAKE/<host>.purged after a purge.
SSH = r"""#!/bin/sh
host=; cmd=
for a in "$@"; do [ -n "$host" ] && cmd="$cmd $a"; case $a in root@*) host=${a#root@} ;; esac; done
echo "ssh $host $cmd" | head -c 200 >> "$FAKE/calls"; echo >> "$FAKE/calls"
case $cmd in
  *dpkg-query*)
    if [ -e "$FAKE/$host.purged-done" ]; then cat "$FAKE/$host.purged"
    elif [ -e "$FAKE/removed" ]; then cat "$FAKE/$host.removed"
    else cat "$FAKE/$host.before"; fi ;;
  *apt-get\ purge*) touch "$FAKE/$host.purged-done"; echo "$cmd" > "$FAKE/$host.purge-command" ;;
  *is-active*)
    unit=${cmd##* }
    case " $FAKE_INACTIVE " in *" $host:$unit "*) exit 3 ;; esac
    # FAKE_SLOW: inactive on the first two checks, active from the third on.
    case " $FAKE_SLOW " in *" $host:$unit "*)
      n=$(cat "$FAKE/slow-$unit" 2>/dev/null || echo 0); echo $((n + 1)) > "$FAKE/slow-$unit"
      [ "$n" -ge 2 ] || exit 3 ;; esac ;;
  *journalctl*) echo "journal of ${cmd##*-u }" ;;
  *ip\ -4\ route\ get*) echo "1.1.1.1 via 10.0.0.1 dev eth0 src 10.0.0.5 uid 0" ;;
  */dev/tcp/*) case " $FAKE_UNREACHABLE " in *" 9999 "*) exit 1 ;; esac ;;
  *curl*) case " $FAKE_UNREACHABLE " in *" 8001 "*) echo 000; exit 7 ;; esac; echo 200 ;;
esac
exit 0
"""
PLAYBOOK = r"""#!/bin/sh
for a in "$@"; do case $a in playbooks/*) p=${a#playbooks/} ;; esac; done
echo "playbook $p" >> "$FAKE/calls"
[ -f hosts.test-deploy ] || { echo "no inventory" >&2; exit 9; }
# ansible ignores ansible.cfg in a world-writable directory (a CI checkout): it must be given explicitly.
[ "$ANSIBLE_CONFIG" = "$PWD/ansible.cfg" ] || { echo "ANSIBLE_CONFIG is not deploy/ansible.cfg" >&2; exit 8; }
case $p in
  deploy_cognos.yml) exit ${FAKE_DEPLOY_RC:-0} ;;
  remove_cognos.yml) touch "$FAKE/removed" ;;
esac
"""

# Stand-in ansible-galaxy: fails the first $FAKE_GALAXY_FAILS times (default 0), as a flaky network would.
GALAXY = r"""#!/bin/sh
n=$(cat "$FAKE/galaxy-attempts" 2>/dev/null || echo 0); n=$((n + 1)); echo "$n" > "$FAKE/galaxy-attempts"
echo "galaxy $*" >> "$FAKE/calls"
[ "$n" -gt "${FAKE_GALAXY_FAILS:-0}" ] || { echo "Network is unreachable" >&2; exit 1; }
"""

M, A = "mgmt.lab", "app.lab"


class TestDeployTest(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.stub("ssh", SSH.split("\n", 1)[1])
        self.stub("ansible-playbook", PLAYBOOK.split("\n", 1)[1])
        self.stub("ansible-galaxy", GALAXY.split("\n", 1)[1])
        self.root = self.tmp / "root"
        (self.root / "deploy/scripts").mkdir(parents=True)
        (self.root / "deploy/artifacts/SVK").mkdir(parents=True)
        (self.root / "deploy/artifacts/SVK/cognos-core_1.7.0~dev.1-ubuntu24.04_amd64.deb").write_text("deb")
        shutil.copy2(REPO / "deploy/scripts/test-deploy.sh", self.root / "deploy/scripts/")
        self.fake = self.tmp / "fake"
        self.fake.mkdir()
        self.key = self.tmp / "key"
        self.key.write_text("key")
        before = "pkg base\nuser root\n"
        for host in (M, A):
            self.state(host, "before", before)
            # After remove_cognos.yml: a dependency the deployment pulled in is still installed.
            self.state(host, "removed", before + "pkg python3-venv\n")
            self.state(host, "purged", before)

    def state(self, host, phase, text):
        (self.fake / f"{host}.{phase}").write_text(text)

    def run_test(self, *extra, **env):
        result = sh(str(self.root / "deploy/scripts/test-deploy.sh"), "--management", M, "--application", A,
                    "--key", str(self.key), *extra, check=False,
                    env=self.env(**{"FAKE": self.fake, "COLLECTION_RETRY_DELAY": 0, "CHECK_WAIT": 0,
                                    "CHECK_TIMEOUT": 0, "CHECK_INTERVAL": 0, **env}))
        calls = (self.fake / "calls").read_text().splitlines() if (self.fake / "calls").exists() else []
        return result, calls

    def playbooks(self, calls):
        return [c.split()[1] for c in calls if c.startswith("playbook ")]

    def test_success_deploys_checks_and_cleans_up(self):
        result, calls = self.run_test()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.playbooks(calls), ["deploy_cognos.yml", "remove_cognos.yml"])
        self.assertIn("deployed, checked and removed cleanly", result.stdout)
        for host in (M, A):
            self.assertIn("purge -y -q python3-venv", (self.fake / f"{host}.purge-command").read_text())
            self.assertIn(f"{host}: nothing of the deployment is left", result.stdout)
        self.assertTrue(any(c.split()[:2] == ["ssh", A] and "is-active --quiet cmmh_driver" in c for c in calls))
        self.assertFalse((self.root / "deploy/hosts.test-deploy").exists())

    def test_failed_deploy_still_cleans_up(self):
        result, calls = self.run_test(FAKE_DEPLOY_RC="2")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.playbooks(calls), ["deploy_cognos.yml", "remove_cognos.yml"])
        self.assertIn("deploy_cognos.yml failed", result.stdout)
        self.assertTrue((self.fake / f"{A}.purge-command").exists())

    def test_service_not_running_fails_but_cleans_up(self):
        result, calls = self.run_test(FAKE_INACTIVE=f"{A}:cognos-svc-mgr")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(f"{A}: cognos-svc-mgr NOT active", result.stdout)
        self.assertIn("journal of cognos-svc-mgr", result.stdout)
        self.assertEqual(self.playbooks(calls)[-1], "remove_cognos.yml")

    def test_services_checked_where_they_run(self):
        # Controller and REST server on the management server; the node only on the application server.
        result, calls = self.run_test()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        checked = {(c.split()[1], c.split()[-1]) for c in calls if "is-active" in c}
        self.assertEqual(checked, {(M, "cognos-controller"), (M, "cognos-restserver"), (A, "cmmh_driver"),
                                   (A, "cognos-node"), (A, "cognos-svc-mgr")})

    def test_application_server_reaches_the_management_server(self):
        result, calls = self.run_test()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        # From the application server, to the address the management server's services listen on.
        from_app = [c for c in calls if c.startswith(f"ssh {A} ")]
        self.assertTrue(any("/dev/tcp/10.0.0.5/9999" in c for c in from_app), calls)
        self.assertTrue(any("http://10.0.0.5:8001/" in c for c in from_app), calls)
        self.assertIn(f"{A} -> {M} (10.0.0.5): controller port 9999 reachable", result.stdout)
        self.assertIn(f"{A} -> {M} (10.0.0.5): REST API answers on port 8001 (HTTP 200)", result.stdout)

    def test_unreachable_controller_or_rest_fails_but_cleans_up(self):
        for port in ("9999", "8001"):
            with self.subTest(port=port):
                (self.fake / "removed").unlink(missing_ok=True)
                for f in self.fake.glob("*.purged-done"):
                    f.unlink()
                result, calls = self.run_test(FAKE_UNREACHABLE=port)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(f"port {port}", result.stdout)
                self.assertIn("NOT", result.stdout.split("== removing")[0])
                self.assertEqual(self.playbooks(calls)[-1], "remove_cognos.yml")

    def test_a_service_slow_to_come_up_passes(self):
        result, _ = self.run_test(FAKE_SLOW=f"{A}:cognos-node", CHECK_TIMEOUT="30")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.fake / "slow-cognos-node").read_text().strip(), "3")
        self.assertIn(f"{A}: cognos-node active", result.stdout)

    def test_waits_before_checking(self):
        result, calls = self.run_test(CHECK_WAIT="1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("== waiting 1 s for the services to come up", result.stdout)
        self.assertLess(result.stdout.index("== waiting"), result.stdout.index("== checking the deployment"))

    def test_anything_left_behind_fails(self):
        self.state(A, "purged", "pkg base\npath /etc/svk\nuser root\n")
        result, _ = self.run_test()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(f"{A}: LEFT BEHIND by the deployment:", result.stdout)
        self.assertIn("path /etc/svk", result.stdout)

    def test_something_gone_that_was_there_is_only_reported(self):
        # The first run on a host with an older Cognos removes it: reported, not an error.
        self.state(A, "before", "pkg base\npkg cognos-core\nuser root\n")
        self.state(A, "removed", "pkg base\nuser root\n")
        self.state(A, "purged", "pkg base\nuser root\n")
        result, _ = self.run_test()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("there before, gone now (not an error)", result.stdout)
        self.assertIn("pkg cognos-core", result.stdout)

    def test_ssh_login_sessions_are_not_leftovers(self):
        # Every ssh connection gets a transient session-N.scope; they differ between before and after.
        self.state(A, "before", "pkg base\nunit session-11.scope\nunit ssh.service\nuser root\n")
        self.state(A, "removed", "pkg base\npkg python3-venv\nunit session-12.scope\nunit ssh.service\nuser root\n")
        self.state(A, "purged", "pkg base\nunit run-r42.scope\nunit session-13.scope\nunit ssh.service\nuser root\n")
        result, _ = self.run_test()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"{A}: nothing of the deployment is left", result.stdout)
        self.assertNotIn("session-", result.stdout)

    def test_a_real_unit_left_behind_still_fails(self):
        self.state(A, "purged", "pkg base\nunit cognos-node.service\nuser root\n")
        result, _ = self.run_test()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unit cognos-node.service", result.stdout)

    def test_collections_are_installed_first(self):
        result, calls = self.run_test()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(calls[0].startswith("galaxy collection install -r collections/requirements.yml"), calls[0])

    def test_collection_install_is_retried(self):
        result, calls = self.run_test(FAKE_GALAXY_FAILS="2")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(sum(c.startswith("galaxy ") for c in calls), 3)
        self.assertIn("attempt 2 failed; retrying", result.stdout)
        self.assertEqual(self.playbooks(calls), ["deploy_cognos.yml", "remove_cognos.yml"])

    def test_collection_install_gives_up_without_touching_the_hosts(self):
        result, calls = self.run_test(FAKE_GALAXY_FAILS="3")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("after 3 attempts; the hosts were not touched", result.stderr)
        self.assertEqual([c for c in calls if not c.startswith("galaxy ")], [])  # no ssh, no playbook
        self.assertFalse((self.root / "deploy/hosts.test-deploy").exists())

    def test_mock_skips_the_cmmh_driver(self):
        result, calls = self.run_test("--mock")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(any("cmmh_driver" in c for c in calls))

    def test_needs_packages_and_arguments(self):
        (self.root / "deploy/artifacts/SVK/cognos-core_1.7.0~dev.1-ubuntu24.04_amd64.deb").unlink()
        result, calls = self.run_test()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no packages in deploy/artifacts/SVK", result.stderr)
        self.assertEqual(calls, [])
        result = sh(str(self.root / "deploy/scripts/test-deploy.sh"), "--management", M, check=False)
        self.assertIn("are required", result.stderr)


if __name__ == "__main__":
    unittest.main()
