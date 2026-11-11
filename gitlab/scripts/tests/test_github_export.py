"""gitlab/scripts/github-export.sh: the history for GitHub, without large files and without e-mail addresses in the
commit messages, and the same every time."""

import os
import shutil
import unittest

from helpers import REPO, TempDirTestCase, sh

FILTER_REPO = os.environ.get("FILTER_REPO") or shutil.which("git-filter-repo")
EXPORT = str(REPO / "gitlab/scripts/github-export.sh")


@unittest.skipUnless(FILTER_REPO, "git-filter-repo is not installed (CI installs it; locally set FILTER_REPO)")
class GitHubExportTest(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.src = self.tmp / "src"
        self.git("init", "--quiet", "--initial-branch=main", str(self.src), cwd=self.tmp)
        self.commit({"a.txt": "a\n"}, "First\n\nSigned-off-by: Jane Doe <jane.doe@samsung.com>")
        # A commit with a large file and a small one: it stays, without the large file.
        self.commit({"big.gif": "x" * 3000, "b.txt": "b\n"}, "Add assets\n\nCo-authored-by: Bot <noreply@example.com>")
        # A commit that only adds a large file: nothing is left of it.
        self.commit({"only-big.bin": "y" * 3000}, "Add a binary")
        self.commit({"a.txt": "a2\n"}, "Fix, reported by root@lab-host.example.lab\n\n"
                                       "Signed-off-by: John Roe <john.roe@partner.samsung.com>")

    def git(self, *args, cwd=None):
        env = {"GIT_AUTHOR_NAME": "Author", "GIT_AUTHOR_EMAIL": "author@samsung.com", "GIT_COMMITTER_NAME": "Author",
               "GIT_COMMITTER_EMAIL": "author@samsung.com", "GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z",
               "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z"}
        return sh("git", *args, cwd=cwd or self.src, env=self.env(**env)).stdout.strip()

    def commit(self, files, message):
        for name, content in files.items():
            (self.src / name).write_text(content)
        self.git("add", "-A")
        self.git("commit", "--quiet", "-m", message)

    def export(self, out="out", check=True):
        return sh(EXPORT, str(self.src), "main", str(self.tmp / out), check=check,
                  env=self.env(FILTER_REPO=FILTER_REPO, MAX_FILE_SIZE="2K"))

    def log(self, out="out", fmt="%B"):
        return sh("git", "log", "main", f"--format={fmt}", cwd=self.tmp / out).stdout

    def test_large_files_and_addresses_go_the_rest_stays(self):
        result = self.export()
        self.assertIn("main: 4 commits, 3 exported (1 left with no change)", result.stdout)
        self.assertIn("checked: no file larger than 2K, no e-mail address", result.stdout)
        files = sh("git", "ls-tree", "-r", "--name-only", "main", cwd=self.tmp / "out").stdout.split()
        self.assertEqual(files, ["a.txt", "b.txt"])
        self.assertEqual(sh("git", "show", "main:a.txt", cwd=self.tmp / "out").stdout, "a2\n")
        messages = self.log()
        self.assertNotIn("@", messages)
        self.assertIn("Signed-off-by: Jane Doe\n", messages)
        self.assertIn("Signed-off-by: John Roe\n", messages)
        self.assertIn("Co-authored-by: Bot\n", messages)
        self.assertIn("Fix, reported by [e-mail removed]", messages)
        self.assertEqual(self.log(fmt="%s").split("\n")[:3], ["Fix, reported by [e-mail removed]", "Add assets", "First"])
        # Authors and dates as they were.
        self.assertEqual(set(self.log(fmt="%an <%ae> %ad").splitlines()), {"Author <author@samsung.com> Thu Jan 1 00:00:00 2026 +0000"})

    def test_the_same_every_time(self):
        self.export("one")
        self.export("two")
        head = lambda out: sh("git", "rev-parse", "main", cwd=self.tmp / out).stdout.strip()
        self.assertEqual(head("one"), head("two"))

    def test_a_newer_branch_continues_the_last_export(self):
        self.export("one")
        self.commit({"c.txt": "c\n"}, "Later")
        self.export("two")
        old = sh("git", "rev-parse", "main", cwd=self.tmp / "one").stdout.strip()
        self.assertEqual(sh("git", "rev-parse", "main~1", cwd=self.tmp / "two").stdout.strip(), old)

    def test_existing_out_is_refused(self):
        (self.tmp / "out").mkdir()
        result = self.export(check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("exists already", result.stderr)


if __name__ == "__main__":
    unittest.main()
