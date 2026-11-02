"""ci/version.sh: the one version of every kind of pipeline, and the next release patch."""

import unittest

from helpers import TempDirTestCase, git, sh

COMPONENT_TAGS = ("core/v1.6.0", "cxl/v1.6.2", "mgmt-fw/v1.6.2", "sapp/v1.6.1", "core/v1.5.9")


class VersionTest(TempDirTestCase):
    def version(self, *args, repo=None, check=True):
        repo = repo or self.repo(["ci/version.sh"], tags=COMPONENT_TAGS)
        return sh(str(repo / "ci/version.sh"), *args, cwd=repo, check=check)

    def test_tag(self):
        self.assertEqual(self.version("--tag", "v1.6.3").stdout.strip(), "1.6.3")

    def test_tag_must_be_x_y_z(self):
        result = self.version("--tag", "core/v1.6.2", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("is not vX.Y.Z", result.stderr)

    def test_merge_request(self):
        self.assertEqual(self.version("--tag", "", "--mr", "7", "--branch", "", "--run", "41").stdout.strip(),
                         "1.7.0~dev.0.mr7.41")

    def test_merge_request_needs_run(self):
        self.assertNotEqual(self.version("--mr", "7", check=False).returncode, 0)

    def test_main(self):
        self.assertEqual(self.version("--branch", "main", "--run", "42").stdout.strip(), "1.7.0~dev.42")

    def test_local_without_tag(self):
        self.assertEqual(self.version().stdout.strip(), "1.7.0~dev.0.local")

    def test_local_on_release_tag(self):
        repo = self.repo(["ci/version.sh"])
        git(repo, "tag", "v1.6.3")
        self.assertEqual(self.version(repo=repo).stdout.strip(), "1.6.3")

    def test_next_patch_counts_component_tags(self):
        # The first monorepo release of 1.6 must not reuse 1.6.0-1.6.2 of the component repositories.
        self.assertEqual(self.version("--next-patch").stdout.strip(), "1.6.3")

    def test_next_patch_after_own_release(self):
        repo = self.repo(["ci/version.sh"], tags=COMPONENT_TAGS + ("v1.6.3",))
        self.assertEqual(self.version("--next-patch", repo=repo).stdout.strip(), "1.6.4")

    def test_next_patch_new_line(self):
        repo = self.repo(["ci/version.sh"], version="1.7", tags=COMPONENT_TAGS)
        self.assertEqual(self.version("--next-patch", repo=repo).stdout.strip(), "1.7.0")

    def test_release_candidate(self):
        self.assertEqual(self.version("--branch", "release/1.6", "--run", "5").stdout.strip(), "1.6.3~rc.5")

    def test_release_branch_must_match_version(self):
        result = self.version("--branch", "release/1.5", "--run", "5", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("VERSION is 1.6", result.stderr)

    def test_next_patch_fails_when_origin_unreachable(self):
        # The v1.6.0 mistake: an unreadable origin must fail, never count as "no release yet".
        repo = self.repo(["ci/version.sh"], tags=COMPONENT_TAGS)
        git(repo, "remote", "set-url", "origin", str(self.tmp / "missing.git"))
        for args in (["--next-patch"], ["--branch", "release/1.6", "--run", "5"]):
            result = self.version(*args, repo=repo, check=False)
            self.assertNotEqual(result.returncode, 0, args)
            self.assertEqual(result.stdout.strip(), "", args)
            self.assertIn("cannot read the release tags", result.stderr)


if __name__ == "__main__":
    unittest.main()
