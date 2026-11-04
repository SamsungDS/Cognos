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
  *is-active*) case " $FAKE_INACTIVE " in *" $host:${cmd##* } "*) exit 3 ;; esac ;;
  *curl*) echo 200 ;;
esac
exit 0
"""
PLAYBOOK = r"""#!/bin/sh
for a in "$@"; do case $a in playbooks/*) p=${a#playbooks/} ;; esac; done
echo "playbook $p" >> "$FAKE/calls"
[ -f hosts.test-deploy ] || { echo "no inventory" >&2; exit 9; }
case $p in
  deploy_cognos.yml) exit ${FAKE_DEPLOY_RC:-0} ;;
  remove_cognos.yml) touch "$FAKE/removed" ;;
esac
"""

M, A = "mgmt.lab", "app.lab"


class TestDeployTest(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.stub("ssh", SSH.split("\n", 1)[1])
        self.stub("ansible-playbook", PLAYBOOK.split("\n", 1)[1])
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
                    "--key", str(self.key), *extra, check=False, env=self.env(FAKE=self.fake, **env))
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
        self.assertEqual(self.playbooks(calls)[-1], "remove_cognos.yml")

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
