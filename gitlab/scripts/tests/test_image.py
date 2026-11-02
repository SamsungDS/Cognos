"""ci/image.sh: an image is rebuilt only when its Dockerfile or scripts/dependencies change."""

import unittest

from helpers import TempDirTestCase, git, sh

# A stand-in docker: logs its arguments; "imagetools inspect" succeeds only for tags listed in $EXISTING.
DOCKER = """echo "$*" >> "$DOCKER_LOG"
case "$1 $2 $3" in
  "buildx imagetools inspect") case " $EXISTING " in *" $4 "*) exit 0 ;; *) exit 1 ;; esac ;;
esac
exit 0
"""


class ImageTest(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.stub("docker", DOCKER)
        self.work = self.repo(["ci/image.sh"])
        deps = self.work / "components/x/scripts/dependencies"
        deps.mkdir(parents=True)
        (deps / "install.sh").write_text("echo install\n")
        (self.work / "components/x/scripts/docker").mkdir(parents=True)
        (self.work / "components/x/scripts/docker/ubuntu24.DOCKERFILE").write_text("FROM ubuntu:24.04\n")
        git(self.work, "add", "-A")
        git(self.work, "commit", "--quiet", "-m", "component x")
        self.log = self.tmp / "docker.log"

    def image(self, existing=""):
        self.log.write_text("")
        result = sh(str(self.work / "ci/image.sh"), "components/x", "ubuntu24", "reg/x", "abc123", cwd=self.work,
                    env=self.env(DOCKER_LOG=self.log, EXISTING=existing))
        return result.stdout, self.log.read_text()

    def content_tag(self):
        out, _ = self.image()
        return out.split("Building ")[1].split(":")[0] + ":" + out.split("Building ")[1].split(":")[1]

    def test_builds_when_missing(self):
        out, log = self.image()
        self.assertIn("Building reg/x:ubuntu24-deps-", out)
        self.assertIn("buildx build --file components/x/scripts/docker/ubuntu24.DOCKERFILE", log)
        self.assertIn("--tag reg/x:ubuntu24-abc123", log)
        self.assertIn("--push", log)

    def test_reuses_when_present(self):
        tag = self.content_tag()
        out, log = self.image(existing=tag)
        self.assertIn("Reusing " + tag, out)
        self.assertIn(f"buildx imagetools create --tag reg/x:ubuntu24-abc123 {tag}", log)
        self.assertNotIn("buildx build", log)

    def test_dependency_change_changes_tag(self):
        before = self.content_tag()
        (self.work / "components/x/scripts/dependencies/install.sh").write_text("echo install v2\n")
        git(self.work, "commit", "--quiet", "-am", "deps")
        self.assertNotEqual(self.content_tag(), before)

    def test_dockerfile_change_changes_tag(self):
        before = self.content_tag()
        (self.work / "components/x/scripts/docker/ubuntu24.DOCKERFILE").write_text("FROM ubuntu:24.04\nRUN true\n")
        git(self.work, "commit", "--quiet", "-am", "dockerfile")
        self.assertNotEqual(self.content_tag(), before)

    def test_other_change_keeps_tag(self):
        before = self.content_tag()
        (self.work / "components/x/README").write_text("docs\n")
        git(self.work, "add", "-A")
        git(self.work, "commit", "--quiet", "-m", "docs")
        self.assertEqual(self.content_tag(), before)

    def test_usage(self):
        result = sh(str(self.work / "ci/image.sh"), "components/x", cwd=self.work, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("usage", result.stderr)


if __name__ == "__main__":
    unittest.main()
