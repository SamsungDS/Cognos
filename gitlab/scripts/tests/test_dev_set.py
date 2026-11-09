"""ci/dev-set.py: which packages a dev set or a release takes, per component and OS."""

import json
import pathlib
import unittest

from helpers import REPO, TempDirTestCase, sh

DEV_SET = str(REPO / "ci/dev-set.py")
COMPONENTS = ["core", "mgmt-fw", "node", "ras", "slat", "me", "cxl", "cxl-mock", "sapp"]
DIRS = {"core": "features/core", "mgmt-fw": "features/mgmt-fw", "node": "features/node",
        "ras": "features/ras", "slat": "features/slat", "me": "features/me", "cxl": "features/cxl",
        "cxl-mock": "features/cxl", "sapp": "apps/sapp"}
NAMES = {"cxl-mock": "cognos-cxl-mock", "sapp": "cognos-app"}


class DevSetTest(TempDirTestCase):
    def build(self, run, components=COMPONENTS, oses=("ubuntu24", "ol10")):
        """Fake packages of a pipeline's builds (runtime and -dev), as the build jobs leave them."""
        for c in components:
            name = NAMES.get(c, f"cognos-{c}")
            for os_name in oses:
                d = self.tmp / DIRS[c] / "build" / "artifacts" / os_name
                d.mkdir(parents=True, exist_ok=True)
                if os_name == "ubuntu24":
                    files = [f"{name}_1.7.0~dev.{run}-ubuntu24.04_amd64.deb", f"{name}-dev_1.7.0~dev.{run}-ubuntu24.04_amd64.deb"]
                else:
                    files = [f"{name}-1.7.0~dev.{run}-1.el10.ol10.2.x86_64.rpm"]
                for f in files:
                    (d / f).write_text(f"{f}\n")

    def clean(self):
        for top in ("features", "apps"):
            sh("rm", "-rf", str(self.tmp / top))

    def results(self, failed=(), only=COMPONENTS):
        path = self.tmp / "results.json"
        path.write_text(json.dumps({f"{c}/{o}": ("failed" if f"{c}/{o}" in failed else "passed")
                                    for c in only for o in ("ubuntu24", "ol10")}))
        return path

    def dev_set(self, pipeline, results=None, previous=None, out="set", complete=False, check=True, extra=()):
        args = [DEV_SET, "--version", f"1.7.0~dev.{pipeline}", "--pipeline", str(pipeline), "--out", out]
        args += [f"--extra={e}" for e in extra]
        if results:
            args += ["--results", str(results)]
        if previous:
            args += ["--previous", previous]
        if complete:
            args.append("--complete")
        return sh(*args, cwd=self.tmp, check=check)

    def packages(self, out):
        return json.loads((self.tmp / out / "set.json").read_text())

    def by(self, the_set):
        """{(component, os): pipeline} of a set."""
        return {(p["component"], p["os"]): p["pipeline"] for p in the_set["packages"]}

    def test_first_set(self):
        self.build(1)
        self.dev_set(100, self.results(), out="s1")
        s = self.packages("s1")
        self.assertEqual(len(self.by(s)), 18)  # 9 components x 2 OSes, cxl and cxl-mock separate
        for p in s["packages"]:
            self.assertTrue((self.tmp / "s1" / p["file"]).is_file())
            self.assertEqual(len(p["sha256"]), 64)

    def test_failed_component_keeps_previous(self):
        self.build(1)
        self.dev_set(100, self.results(), out="s1")
        self.clean()
        self.build(2)
        self.dev_set(101, self.results(failed=("ras/ol10", "cxl-mock/ubuntu24")), previous="s1", out="s2")
        by = self.by(self.packages("s2"))
        self.assertEqual(by[("ras", "ol10")], 100)
        self.assertEqual(by[("cxl-mock", "ubuntu24")], 100)
        self.assertEqual(by[("ras", "ubuntu24")], 101)
        self.assertEqual(by[("cxl", "ubuntu24")], 101)
        self.assertIn("failed in this pipeline", self.packages("s2")["outcomes"]["ras/ol10"])

    def test_not_built_keeps_previous(self):
        self.build(1)
        self.dev_set(100, self.results(), out="s1")
        self.clean()
        self.build(2, components=["cxl", "cxl-mock"])
        self.dev_set(101, self.results(only=["cxl", "cxl-mock"]), previous="s1", out="s2")
        by = self.by(self.packages("s2"))
        self.assertEqual(by[("core", "ubuntu24")], 100)
        self.assertEqual(by[("cxl", "ol10")], 101)
        self.assertEqual(len(by), 18)

    def test_upstream_failure_publishes_no_set(self):
        self.build(1)
        for failed in ("core/ol10", "mgmt-fw/ubuntu24"):
            result = self.dev_set(100, self.results(failed=(failed,)), out="s", check=False)
            self.assertEqual(result.returncode, 2, failed)
            self.assertFalse((self.tmp / "s" / "set.json").exists(), failed)

    def test_never_passed_is_missing(self):
        self.build(1)
        result = self.dev_set(100, self.results(failed=("node/ubuntu24",)), out="s1")
        self.assertIn("WARNING: no packages for node/ubuntu24", result.stdout)
        self.assertNotIn(("node", "ubuntu24"), self.by(self.packages("s1")))

    def test_older_pipeline_does_not_replace_newer_set(self):
        self.build(1)
        self.dev_set(200, self.results(), out="s1")
        result = self.dev_set(199, self.results(), previous="s1", out="s2", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("newer than this pipeline", result.stderr)

    def test_rerun_in_same_pipeline(self):
        self.build(1)
        self.dev_set(200, self.results(failed=("ras/ol10",)), out="s1")
        self.dev_set(200, self.results(), previous="s1", out="s2")
        self.assertEqual(self.by(self.packages("s2"))[("ras", "ol10")], 200)

    def test_release_needs_everything(self):
        self.build(1, components=[c for c in COMPONENTS if c != "sapp"])
        result = self.dev_set(300, out="r", complete=True, check=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("missing: sapp/ubuntu24, sapp/ol10", result.stderr)

    def grpc(self, name="cognos-grpc-1.59.2-1.el10.x86_64.rpm"):
        path = self.tmp / "grpc" / name
        path.parent.mkdir(exist_ok=True)
        path.write_text("grpc")
        return f"ol10={path}"

    def test_release_complete(self):
        self.build(1)
        self.dev_set(300, out="r", complete=True, extra=[self.grpc()])
        by = self.by(self.packages("r"))
        self.assertEqual(len(by), 19)  # 18 + cognos-grpc for ol10
        grpc = [p for p in self.packages("r")["packages"] if p["component"] == "grpc"][0]
        self.assertEqual((grpc["os"], grpc["version"], grpc["file"]),
                         ("ol10", "1.59.2", "ol10/cognos-grpc-1.59.2-1.el10.x86_64.rpm"))
        self.assertTrue((self.tmp / "r/ol10/cognos-grpc-1.59.2-1.el10.x86_64.rpm").is_file())

    def test_release_needs_grpc(self):
        self.build(1)
        result = self.dev_set(300, out="r", complete=True, check=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("grpc/ol10", result.stderr)

    def test_dev_set_keeps_previous_grpc_when_not_added(self):
        self.build(1)
        self.dev_set(100, self.results(), out="s1", extra=[self.grpc()])
        self.clean()
        self.build(2, components=["cxl", "cxl-mock"])
        self.dev_set(101, self.results(only=["cxl", "cxl-mock"]), previous="s1", out="s2")
        self.assertEqual(self.by(self.packages("s2"))[("grpc", "ol10")], 100)
        self.assertIn("not added in this pipeline", self.packages("s2")["outcomes"]["grpc/ol10"])

    def test_extra_must_be_grpc_for_ol10(self):
        self.build(1)
        for bad in ("ubuntu24=" + self.grpc().split("=", 1)[1], "ol10=" + str(self.tmp / "missing.rpm"),
                    self.grpc("cognos-core-1.0.0-1.el10.x86_64.rpm")):
            result = self.dev_set(100, self.results(), out="s", check=False, extra=[bad])
            self.assertNotEqual(result.returncode, 0, bad)


if __name__ == "__main__":
    unittest.main()
