"""ci/compat-check.sh: proposes major only when a public interface broke; a check that cannot run is reported."""

import shutil
import unittest

from helpers import TempDirTestCase, git, sh

# Stand-ins: buf and abidiff exit with $BUF_RC / $ABIDIFF_RC.
BUF = 'echo "buf $*" >&2\necho "framework.proto: field changed type"\nexit ${BUF_RC:-0}\n'
ABIDIFF = 'echo "abidiff $1 $2"\nexit ${ABIDIFF_RC:-0}\n'


@unittest.skipUnless(shutil.which("dpkg-deb"), "needs dpkg-deb")
class CompatTest(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.stub("buf", BUF)
        self.stub("abidiff", ABIDIFF)
        self.work = self.repo(["ci/compat-check.sh", "components/mgmt-fw/proto/framework/framework.proto"])
        git(self.work, "tag", "v1.6.3")
        self.old = self.package("old", "libsvkcore.so.1.6.3")
        self.new = self.package("new", "libsvkcore.so.1.7.0")

    def package(self, name, lib):
        """A real .deb holding one shared library file."""
        root = self.tmp / f"{name}-root"
        (root / "DEBIAN").mkdir(parents=True)
        (root / "DEBIAN/control").write_text(f"Package: cognos-core\nVersion: 1.0\nArchitecture: amd64\n"
                                             f"Maintainer: test\nDescription: test\n")
        (root / "usr/lib").mkdir(parents=True)
        (root / "usr/lib" / lib).write_text("not really ELF\n")
        out = self.tmp / name
        out.mkdir()
        sh("dpkg-deb", "--build", "--root-owner-group", str(root), str(out / "cognos-core.deb"))
        return out

    def check(self, buf_rc=0, abidiff_rc=0, new=None):
        report = self.tmp / "report.md"
        result = sh(str(self.work / "ci/compat-check.sh"), "--base", "v1.6.3", "--old", str(self.old),
                    "--new", str(new or self.new), "--report", str(report), cwd=self.work,
                    env=self.env(BUF_RC=buf_rc, ABIDIFF_RC=abidiff_rc))
        return result.stdout.strip().splitlines()[-1], report.read_text()

    def test_nothing_broke(self):
        kind, report = self.check()
        self.assertEqual(kind, "minor")
        self.assertIn("No breaking changes.", report)
        self.assertIn("`libsvkcore.so`: unchanged", report)

    def test_proto_break_is_major(self):
        kind, report = self.check(buf_rc=100)
        self.assertEqual(kind, "major")
        self.assertIn("**Breaking changes:**", report)

    def test_abi_break_is_major(self):
        kind, report = self.check(abidiff_rc=12)
        self.assertEqual(kind, "major")
        self.assertIn("`libsvkcore.so`: **incompatible change**", report)

    def test_compatible_abi_change_is_minor(self):
        kind, report = self.check(abidiff_rc=4)
        self.assertEqual(kind, "minor")
        self.assertIn("compatible changes", report)

    def test_removed_library_is_major(self):
        empty = self.tmp / "empty"
        empty.mkdir()
        kind, report = self.check(new=empty)
        self.assertEqual(kind, "major")
        self.assertIn("**removed**", report)

    def test_check_that_cannot_run_is_reported_not_major(self):
        kind, report = self.check(buf_rc=1, abidiff_rc=1)
        self.assertEqual(kind, "minor")
        self.assertIn("Could not check (buf exit 1)", report)
        self.assertIn("could not compare", report)


if __name__ == "__main__":
    unittest.main()
