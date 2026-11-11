"""ci/dev-set.py: which packages a dev set or a release takes, per component and OS."""

import json
import pathlib
import unittest

from helpers import REPO, TempDirTestCase, sh

DEV_SET = str(REPO / "ci/dev-set.py")
COMPONENTS = ["extras", "core", "mgmt-fw", "node", "ras", "slat", "me", "cxl", "cxl-mock", "sapp"]
DIRS = {"extras": "utils/extras", "core": "features/core", "mgmt-fw": "features/mgmt-fw", "node": "features/node",
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
                if c == "extras":  # gRPC and the Go modules, at their own versions
                    files = (["cognos-grpc_1.59.2_amd64.deb", "cognos-go-modules_0.0.25_amd64.deb"] if os_name == "ubuntu24"
                             else ["cognos-grpc-1.59.2-1.el10.x86_64.rpm", "cognos-go-modules-0.0.25-1.el10.x86_64.rpm"])
                elif os_name == "ubuntu24":
                    files = [f"{name}_1.7.0~dev.{run}-ubuntu24.04_amd64.deb", f"{name}-dev_1.7.0~dev.{run}-ubuntu24.04_amd64.deb"]
                else:
                    files = [f"{name}-1.7.0~dev.{run}-1.el10.ol10.2.x86_64.rpm"]
                for f in files:
                    (d / f).write_text(f"{f}\n")

    def clean(self):
        for top in ("features", "apps", "utils"):
            sh("rm", "-rf", str(self.tmp / top))

    def results(self, failed=(), only=COMPONENTS):
        path = self.tmp / "results.json"
        path.write_text(json.dumps({f"{c}/{o}": ("failed" if f"{c}/{o}" in failed else "passed")
                                    for c in only for o in ("ubuntu24", "ol10")}))
        return path

    def dev_set(self, pipeline, results=None, previous=None, out="set", complete=False, check=True):
        args = [DEV_SET, "--version", f"1.7.0~dev.{pipeline}", "--pipeline", str(pipeline), "--out", out]
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
        self.assertEqual(len(self.by(s)), 20)  # 10 components x 2 OSes, cxl and cxl-mock separate
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
        self.assertEqual(len(by), 20)

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

    def test_release_complete(self):
        self.build(1)
        self.dev_set(300, out="r", complete=True)
        the_set = self.packages("r")
        self.assertEqual(len(self.by(the_set)), 20)
        extras = sorted((p["os"], p["file"], p["version"]) for p in the_set["packages"] if p["component"] == "extras")
        self.assertEqual(extras, [
            ("ol10", "ol10/cognos-go-modules-0.0.25-1.el10.x86_64.rpm", "0.0.25"),
            ("ol10", "ol10/cognos-grpc-1.59.2-1.el10.x86_64.rpm", "1.59.2"),
            ("ubuntu24", "ubuntu24/cognos-go-modules_0.0.25_amd64.deb", "0.0.25"),
            ("ubuntu24", "ubuntu24/cognos-grpc_1.59.2_amd64.deb", "1.59.2"),
        ])
        core = [p for p in the_set["packages"] if p["component"] == "core"][0]
        self.assertEqual(core["version"], "1.7.0~dev.300")

    def test_release_needs_extras(self):
        self.build(1, components=[c for c in COMPONENTS if c != "extras"])
        result = self.dev_set(300, out="r", complete=True, check=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("missing: extras/ubuntu24", result.stderr)

    def test_extras_not_built_keeps_the_previous_with_its_versions(self):
        # extras is built only when utils/extras changes; other pipelines keep the previous set's.
        self.build(1)
        self.dev_set(100, self.results(), out="s1")
        self.clean()
        self.build(2, components=["cxl", "cxl-mock"])
        self.dev_set(101, self.results(only=["cxl", "cxl-mock"]), previous="s1", out="s2")
        s2 = self.packages("s2")
        self.assertEqual(self.by(s2)[("extras", "ol10")], 100)
        self.assertIn("not built in this pipeline; kept from pipeline 100", s2["outcomes"]["extras/ubuntu24"])
        self.assertEqual(sorted({p["version"] for p in s2["packages"] if p["component"] == "extras"}), ["0.0.25", "1.59.2"])

if __name__ == "__main__":
    unittest.main()
