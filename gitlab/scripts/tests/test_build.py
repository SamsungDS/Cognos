"""build.sh: its options, and where upstream packages come from (pipeline, then dev set, then installed)."""

import shutil
import unittest

from helpers import REPO, TempDirTestCase, sh

# A stand-in fetch-packages.py: puts a fake dev set package into $ARTIFACTS_DIR, or fails (FAKE_DEV_SET=fail).
FETCH = """#!/bin/sh
[ "$FAKE_DEV_SET" = fail ] && { echo "fetch-packages: no dev set available"; exit 1; }
mkdir -p "$ARTIFACTS_DIR"
echo pkg > "$ARTIFACTS_DIR/cognos-core_1.7.0~dev.9-ubuntu24.04_amd64.deb"
echo pkg > "$ARTIFACTS_DIR/cognos-core-dev_1.7.0~dev.9-ubuntu24.04_amd64.deb"
"""


class BuildOptionsTest(TempDirTestCase):
    def run_build(self, *args):
        return sh(str(REPO / "build.sh"), *args, check=False)

    def test_help(self):
        result = self.run_build("-h")
        self.assertEqual(result.returncode, 0)
        self.assertIn("Usage: ./build.sh", result.stdout)

    def test_unknown_option(self):
        result = self.run_build("--bogus")
        self.assertEqual(result.returncode, 1)
        self.assertIn("unknown option --bogus", result.stderr)

    def test_unsupported_os(self):
        result = self.run_build("--os", "ol9", "core")
        self.assertEqual(result.returncode, 1)
        self.assertIn("--os must be ubuntu24 or ol10", result.stderr)

    def test_unknown_component(self):
        result = self.run_build("--native", "nope")
        self.assertEqual(result.returncode, 1)
        self.assertIn("unknown component nope", result.stderr)

    def test_upstream_only_needs_native_and_not_test(self):
        result = self.run_build("--upstream-only", "cxl")
        self.assertEqual(result.returncode, 1)
        self.assertIn("use it with --native", result.stderr)
        result = self.run_build("--native", "--upstream-only", "--test", "cxl")
        self.assertEqual(result.returncode, 1)
        self.assertIn("do not go together", result.stderr)

    def test_extras_first(self):
        result = self.run_build("-h")
        self.assertIn("(extras core mgmt-fw node ras slat me cxl sapp)", result.stdout)
        self.assertNotIn("Nexus", result.stdout)


class UpstreamTest(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.root = self.tmp / "root"
        (self.root / "deploy/ansible/scripts").mkdir(parents=True)
        shutil.copy2(REPO / "build.sh", self.root / "build.sh")
        fetch = self.root / "deploy/ansible/scripts/fetch-packages.py"
        fetch.write_text(FETCH)
        fetch.chmod(0o755)
        self.log = self.tmp / "apt.log"
        self.stub("apt-get", f'echo "apt-get $*" >> "{self.log}"\n')
        self.stub("dpkg-deb", 'case "$3" in Package) echo cognos-core ;; Version) basename "$2" | cut -d_ -f2 ;; esac\n')
        # dpkg-query: the installed version, unless FAKE_NOT_INSTALLED; it logs which package was asked for.
        self.stub("dpkg-query", f'echo "dpkg-query $*" >> "{self.log}.query"\n'
                                '[ -n "$FAKE_NOT_INSTALLED" ] && exit 1\necho 1.6.2\n')

    def install_upstream(self, component="core", check=True, **env):
        script = (f'source "{self.root}/build.sh"; shopt -s nullglob; OS=ubuntu24 PKG_EXT=deb SUDO=; '
                  f'install_upstream {component}')
        result = sh("bash", "-c", script, env=self.env(**env), check=check)
        if not check:
            return result
        return result.stdout, self.log.read_text() if self.log.exists() else ""

    def test_pipeline_packages_first(self):
        d = self.root / "features/core/build/artifacts/ubuntu24"
        d.mkdir(parents=True)
        (d / "cognos-core_1.7.0~dev.0.mr3.9-ubuntu24.04_amd64.deb").write_text("pkg")
        out, apt = self.install_upstream()
        self.assertIn("upstream core: pipeline 1.7.0~dev.0.mr3.9", out)
        self.assertIn("cognos-core_1.7.0~dev.0.mr3.9", apt)

    def test_dev_set_second(self):
        out, apt = self.install_upstream()
        self.assertIn("upstream core: dev set 1.7.0~dev.9", out)
        self.assertIn("cognos-core-dev_1.7.0~dev.9", apt)

    def test_installed_last(self):
        out, apt = self.install_upstream(FAKE_DEV_SET="fail")
        self.assertIn("no dev set packages (fetch-packages: no dev set available)", out)
        self.assertIn("upstream core: installed 1.6.2", out)
        self.assertEqual(apt, "")

    def test_dev_set_can_be_skipped(self):
        out, _ = self.install_upstream(UPSTREAM_DEV_SET="0")
        self.assertIn("upstream core: installed", out)

    def test_nowhere_stops_the_build(self):
        # The build images no longer carry Cognos packages: without pipeline, dev set or installed packages, stop.
        result = self.install_upstream(check=False, FAKE_DEV_SET="fail", FAKE_NOT_INSTALLED="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("upstream core: not built here, not in a dev set and cognos-core is not installed", result.stderr)
        self.assertIn("./build.sh core", result.stderr)

    def test_extras_from_its_folder(self):
        d = self.root / "utils/extras/build/artifacts/ubuntu24"
        d.mkdir(parents=True)
        for f in ("cognos-grpc_1.59.2_amd64.deb", "cognos-go-modules_0.0.25_amd64.deb"):
            (d / f).write_text("pkg")
        out, apt = self.install_upstream("extras")
        self.assertIn("upstream extras: pipeline", out)
        self.assertIn("cognos-grpc_1.59.2_amd64.deb", apt)
        self.assertIn("cognos-go-modules_0.0.25_amd64.deb", apt)

    def test_extras_installed_is_cognos_grpc(self):
        out, _ = self.install_upstream("extras", UPSTREAM_DEV_SET="0")
        self.assertIn("upstream extras: installed 1.6.2", out)
        self.assertIn("cognos-grpc", (self.tmp / "apt.log.query").read_text())

    def test_upstream_only_installs_and_builds_nothing(self):
        # Sonar scans: the upstream packages of the component (their headers), and no build. build_native checks
        # that this machine runs --os, so the test uses this machine's OS name.
        host = sh("bash", "-c", '. /etc/os-release && echo "$ID${VERSION_ID%%.*}"').stdout.strip()
        d = self.root / f"features/core/build/artifacts/{host}"
        d.mkdir(parents=True)
        (d / "cognos-core-dev_1.7.0~dev.9-ubuntu24.04_amd64.deb").write_text("pkg")
        (self.root / "features/ras/scripts").mkdir(parents=True)
        build = self.root / "features/ras/scripts/build.sh"
        build.write_text(f'#!/bin/sh\necho built > "{self.tmp}/ras-built"\n')
        build.chmod(0o755)
        script = (f'source "{self.root}/build.sh"; shopt -s nullglob; OS={host} PKG_EXT=deb SUDO= TEST= '
                  'UPSTREAM_ONLY=1 COGNOS_VERSION=1 build_native ras')
        out = sh("bash", "-c", script, env=self.env()).stdout
        self.assertIn(f"== upstream packages of ras ({host})", out)
        self.assertIn("upstream core: pipeline", out)
        self.assertIn("cognos-core-dev_1.7.0~dev.9", self.log.read_text())
        self.assertFalse((self.tmp / "ras-built").exists())

    def test_upstreams(self):
        script = (f'source "{self.root}/build.sh"; for c in extras core mgmt-fw node cxl me sapp; do '
                  'echo "$c: $(upstreams $c)"; done')
        out = sh("bash", "-c", script).stdout.splitlines()
        self.assertEqual(out, ["extras: ", "core: ", "mgmt-fw: extras core", "node: core",
                               "cxl: extras core mgmt-fw", "me: extras core mgmt-fw", "sapp: "])


if __name__ == "__main__":
    unittest.main()
