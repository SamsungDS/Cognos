"""build.sh: its options, and where upstream packages come from (pipeline, then dev set, then image)."""

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


class UpstreamTest(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.root = self.tmp / "root"
        (self.root / "deploy/scripts").mkdir(parents=True)
        shutil.copy2(REPO / "build.sh", self.root / "build.sh")
        fetch = self.root / "deploy/scripts/fetch-packages.py"
        fetch.write_text(FETCH)
        fetch.chmod(0o755)
        self.log = self.tmp / "apt.log"
        self.stub("apt-get", f'echo "apt-get $*" >> "{self.log}"\n')
        self.stub("dpkg-deb", 'case "$3" in Package) echo cognos-core ;; Version) basename "$2" | cut -d_ -f2 ;; esac\n')
        self.stub("dpkg-query", "echo 1.6.2\n")

    def install_upstream(self, **env):
        script = (f'source "{self.root}/build.sh"; shopt -s nullglob; OS=ubuntu24 PKG_EXT=deb SUDO=; '
                  'install_upstream core')
        result = sh("bash", "-c", script, env=self.env(**env))
        return result.stdout, self.log.read_text() if self.log.exists() else ""

    def test_pipeline_packages_first(self):
        d = self.root / "components/core/build/artifacts/ubuntu24"
        d.mkdir(parents=True)
        (d / "cognos-core_1.7.0~dev.0.mr3.9-ubuntu24.04_amd64.deb").write_text("pkg")
        out, apt = self.install_upstream()
        self.assertIn("upstream core: pipeline 1.7.0~dev.0.mr3.9", out)
        self.assertIn("cognos-core_1.7.0~dev.0.mr3.9", apt)

    def test_dev_set_second(self):
        out, apt = self.install_upstream()
        self.assertIn("upstream core: dev set 1.7.0~dev.9", out)
        self.assertIn("cognos-core-dev_1.7.0~dev.9", apt)

    def test_image_last(self):
        out, apt = self.install_upstream(FAKE_DEV_SET="fail")
        self.assertIn("no dev set packages (fetch-packages: no dev set available)", out)
        self.assertIn("upstream core: image 1.6.2", out)
        self.assertEqual(apt, "")

    def test_dev_set_can_be_skipped(self):
        out, _ = self.install_upstream(UPSTREAM_DEV_SET="0")
        self.assertIn("upstream core: image", out)


if __name__ == "__main__":
    unittest.main()
