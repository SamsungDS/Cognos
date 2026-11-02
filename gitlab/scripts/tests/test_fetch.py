"""deploy/scripts/fetch-packages.py against a fake GitLab and Nexus."""

import hashlib
import io
import json
import re
import shutil
import unittest
import zipfile

from helpers import REPO, FakeGitLab, TempDirTestCase, sh

UBUNTU = ["cognos-core_1.7.0~dev.5-ubuntu24.04_amd64.deb", "cognos-core-dev_1.7.0~dev.5-ubuntu24.04_amd64.deb",
          "cognos-cxl_1.7.0~dev.5-ubuntu24.04_amd64.deb", "cognos-cxl-mock_1.7.0~dev.5-ubuntu24.04_amd64.deb",
          "cognos-app_1.7.0~dev.5-ubuntu24.04_amd64.deb"]
OL10 = ["cognos-core-1.7.0~dev.5-1.el10.ol10.2.x86_64.rpm"]
COMPONENT = {"cognos-core": "core", "cognos-core-dev": "core", "cognos-cxl": "cxl", "cognos-cxl-mock": "cxl-mock",
             "cognos-app": "sapp"}


def component(file):
    return COMPONENT[re.match(r"^([a-z0-9-]+?)(_|-[0-9])", file).group(1)]


class FetchTest(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.gitlab = FakeGitLab()
        self.addCleanup(self.gitlab.close)
        self.p = self.gitlab.project
        # The script, as in a checkout, so that --local reads this root's build/artifacts.
        self.root = self.tmp / "root"
        (self.root / "deploy/scripts").mkdir(parents=True)
        shutil.copy2(REPO / "deploy/scripts/fetch-packages.py", self.root / "deploy/scripts/")
        self.dest = self.tmp / "dest"

    def publish_set(self, job, pipeline, files=None, corrupt=None):
        """Serve a dev set as the artifacts of `job`."""
        files = files or [("ubuntu24", f) for f in UBUNTU] + [("ol10", f) for f in OL10]
        packages = []
        for os_name, f in files:
            data = f"{f} from pipeline {pipeline}".encode()
            packages.append({"component": component(f), "os": os_name, "file": f"{os_name}/{f}",
                             "version": "1.7.0~dev.5", "pipeline": pipeline, "sha256": hashlib.sha256(data).hexdigest()})
            served = b"tampered" if f == corrupt else data
            self.gitlab.route("GET", rf"{self.p}/jobs/{job}/artifacts/dev-set/{os_name}/{f.replace('~', '.')}", served)
        the_set = {"version": "1.7.0~dev.5", "pipeline": pipeline, "created": "now", "packages": packages,
                   "outcomes": {"ras/ubuntu24": "failed in this pipeline; kept from pipeline 1"}}
        self.gitlab.route("GET", rf"{self.p}/jobs/{job}/artifacts/dev-set/set\.json", the_set)

    def pipelines(self, *pipeline_jobs):
        """main's pipelines, newest first: (pipeline id, publish job id or None)."""
        self.gitlab.route("GET", rf"{self.p}/pipelines\?ref=main&per_page=50", [{"id": p} for p, _ in pipeline_jobs])
        for p, job in pipeline_jobs:
            jobs = [{"id": job, "name": "publish dev set"}] if job else []
            self.gitlab.route("GET", rf"{self.p}/pipelines/{p}/jobs\?per_page=100&scope\[\]=success", jobs)

    def fetch(self, *args, check=True):
        env = self.env(COGNOS_GITLAB_URL=self.gitlab.url, COGNOS_PROJECT="dfs/svk/cognos", NEXUS_URL=self.gitlab.url,
                       ARTIFACTS_DIR=self.dest)
        return sh("python3", str(self.root / "deploy/scripts/fetch-packages.py"), *args, env=env, check=check)

    def files(self):
        return sorted(p.name for p in self.dest.iterdir())

    def test_latest_set_runtime_packages_release_cxl(self):
        self.pipelines((3, None), (2, 20))
        self.publish_set(20, 2)
        result = self.fetch("--os", "ubuntu24", "--set", "latest")
        self.assertEqual(self.files(), ["cognos-app_1.7.0~dev.5-ubuntu24.04_amd64.deb",
                                        "cognos-core_1.7.0~dev.5-ubuntu24.04_amd64.deb",
                                        "cognos-cxl_1.7.0~dev.5-ubuntu24.04_amd64.deb"])
        self.assertIn("ras/ubuntu24: failed in this pipeline", result.stdout)
        self.assertIn("WARNING: no packages for", result.stdout)

    def test_mock_and_dev_and_only(self):
        self.pipelines((2, 20))
        self.publish_set(20, 2)
        self.fetch("--os", "ubuntu24", "--set", "latest", "--mock", "--only", "cxl")
        self.assertEqual(self.files(), ["cognos-cxl-mock_1.7.0~dev.5-ubuntu24.04_amd64.deb"])
        self.fetch("--os", "ubuntu24", "--set", "latest", "--with-dev", "--only", "core")
        self.assertEqual(self.files(), ["cognos-core-dev_1.7.0~dev.5-ubuntu24.04_amd64.deb",
                                        "cognos-core_1.7.0~dev.5-ubuntu24.04_amd64.deb"])

    def test_old_packages_removed(self):
        self.pipelines((2, 20))
        self.publish_set(20, 2)
        self.dest.mkdir()
        (self.dest / "cognos-core_1.6.2-ubuntu24.04_amd64.deb").write_text("old")
        (self.dest / "keep.txt").write_text("not a package")
        self.fetch("--os", "ubuntu24", "--set", "latest", "--only", "core")
        self.assertEqual(self.files(), ["cognos-core_1.7.0~dev.5-ubuntu24.04_amd64.deb", "keep.txt"])

    def test_expired_newest_falls_back(self):
        self.pipelines((3, 30), (2, 20))
        self.publish_set(20, 2)  # job 30's set.json is not served: expired
        result = self.fetch("--os", "ubuntu24", "--set", "latest", "--only", "core")
        self.assertIn("pipeline 2", result.stdout)

    def test_checksum_mismatch_fails(self):
        self.pipelines((2, 20))
        self.publish_set(20, 2, corrupt=UBUNTU[0])
        result = self.fetch("--os", "ubuntu24", "--set", "latest", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("checksum mismatch", result.stderr)

    def test_set_of_one_pipeline(self):
        self.gitlab.route("GET", rf"{self.p}/pipelines/7/jobs\?per_page=100&scope\[\]=success",
                          [{"id": 70, "name": "publish dev set"}])
        self.publish_set(70, 7)
        self.fetch("--os", "ubuntu24", "--set", "7", "--only", "core")
        self.assertEqual(self.files(), ["cognos-core_1.7.0~dev.5-ubuntu24.04_amd64.deb"])

    def test_pipeline_overrides_dev_set(self):
        self.pipelines((2, 20))
        self.publish_set(20, 2)
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("components/core/build/artifacts/ubuntu24/cognos-core_1.7.0~dev.0.mr3.9-ubuntu24.04_amd64.deb", b"mr")
        self.gitlab.route("GET", rf"{self.p}/pipelines/9/jobs\?per_page=100&scope\[\]=success",
                          [{"id": 91, "name": "build core: [ubuntu24]"}, {"id": 92, "name": "build core image: [ubuntu24]"},
                           {"id": 93, "name": "build core: [ol10]"}])
        self.gitlab.route("GET", rf"{self.p}/jobs/91/artifacts", archive.getvalue())
        self.fetch("--os", "ubuntu24", "--pipeline", "9")
        self.assertIn("cognos-core_1.7.0~dev.0.mr3.9-ubuntu24.04_amd64.deb", self.files())
        self.assertNotIn("cognos-core_1.7.0~dev.5-ubuntu24.04_amd64.deb", self.files())
        self.assertIn("cognos-cxl_1.7.0~dev.5-ubuntu24.04_amd64.deb", self.files())  # from the dev set
        self.assertEqual(self.gitlab.sent("GET", rf"{self.p}/jobs/93/artifacts"), [])  # other OS not downloaded

    def test_release(self):
        base = rf"{self.p}/packages/generic/cognos/1\.6\.3"
        data = b"release core"
        self.gitlab.route("GET", rf"{base}/set\.json", {
            "version": "1.6.3", "pipeline": 5, "created": "now", "packages": [
                {"component": "core", "os": "ubuntu24", "file": "ubuntu24/cognos-core_1.6.3-ubuntu24.04_amd64.deb",
                 "version": "1.6.3", "pipeline": 5, "sha256": hashlib.sha256(data).hexdigest()}]})
        self.gitlab.route("GET", rf"{base}/cognos-core_1\.6\.3-ubuntu24\.04_amd64\.deb", data)
        self.fetch("--os", "ubuntu24", "--release", "v1.6.3")
        self.assertEqual(self.files(), ["cognos-core_1.6.3-ubuntu24.04_amd64.deb"])

    def test_missing_release_fails(self):
        result = self.fetch("--os", "ubuntu24", "--release", "v9.9.9", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not found", result.stderr)

    def test_ol10_gets_pinned_grpc_from_nexus(self):
        self.pipelines((2, 20))
        self.publish_set(20, 2)
        rpm = f"{self.gitlab.url}/repository/svk_yum_ol10/cognos-grpc-1.59.2-1.el10.x86_64.rpm"
        self.gitlab.route("GET", r"/service/rest/v1/search/assets\?repository=svk_yum_ol10&name=cognos-grpc&version=1\.59\.2",
                          {"items": [{"downloadUrl": rpm}]})
        self.gitlab.route("GET", r"/repository/svk_yum_ol10/cognos-grpc-1\.59\.2-1\.el10\.x86_64\.rpm", b"grpc")
        self.fetch("--os", "ol10", "--set", "latest")
        self.assertEqual(self.files(), ["cognos-core-1.7.0~dev.5-1.el10.ol10.2.x86_64.rpm",
                                        "cognos-grpc-1.59.2-1.el10.x86_64.rpm"])

    def test_local(self):
        local = self.root / "build/artifacts/ubuntu24"
        local.mkdir(parents=True)
        for f in UBUNTU:
            (local / f).write_text(f)
        self.fetch("--os", "ubuntu24", "--local")
        self.assertEqual(len(self.files()), 3)

    def test_local_without_build_fails(self):
        result = self.fetch("--os", "ubuntu24", "--local", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("run ./build.sh", result.stderr)

    def test_unknown_component(self):
        result = self.fetch("--os", "ubuntu24", "--set", "latest", "--only", "nope", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown components", result.stderr)


if __name__ == "__main__":
    unittest.main()
