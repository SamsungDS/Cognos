"""gitlab/scripts/api.py against a fake GitLab API, in throwaway repositories."""

import io
import json
import shutil
import unittest
import urllib.parse
import zipfile

from helpers import FakeGitLab, TempDirTestCase, git, sh

COMPONENT_TAGS = ("cxl/v1.6.2", "mgmt-fw/v1.6.2", "core/v1.6.0")
FILES = ["gitlab/scripts/api.py", "ci/version.sh"]


class ApiTestCase(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.gitlab = FakeGitLab()
        self.addCleanup(self.gitlab.close)
        self.p = self.gitlab.project

    def api(self, work, *args, check=False, **env):
        base = dict(CI_API_V4_URL=self.gitlab.api, CI_PROJECT_ID="dfs%2Fsvk%2Fcognos", RELEASE_BOT_TOKEN="bot-token",
                    CI_JOB_TOKEN="job-token", CI_SERVER_HOST="gitlab.example", CI_SERVER_URL=f"file://{self.tmp}",
                    CI_PROJECT_PATH="work-origin", CI_COMMIT_SHA=git(work, "rev-parse", "HEAD"))
        base.update(env)
        return sh("python3", str(work / "gitlab/scripts/api.py"), *args, cwd=work, env=self.env(**base), check=check)


class JobResultsTest(ApiTestCase):
    def test_passed_only_when_build_and_test_passed(self):
        jobs = [("build core: [ubuntu24]", "success"), ("test core: [ubuntu24]", "success"),
                ("build core: [ol10]", "success"), ("test core: [ol10]", "failed"),
                ("build cxl: [ubuntu24, release]", "success"), ("build cxl: [ubuntu24, mock]", "failed"),
                ("test cxl: [ubuntu24]", "success"), ("build sapp: [ol10]", "success")]
        self.gitlab.route("GET", rf"{self.p}/pipelines/77/jobs\?per_page=100&page=1",
                          [{"name": n, "status": s} for n, s in jobs])
        work = self.repo(FILES)
        result = self.api(work, "job-results", "--pipeline", "77", check=True)
        self.assertEqual(json.loads(result.stdout), {
            "core/ubuntu24": "passed", "core/ol10": "failed", "cxl/ubuntu24": "passed",
            "cxl-mock/ubuntu24": "failed", "sapp/ol10": "failed"})  # sapp's test job did not run: failed


class NewestDevSetTest(ApiTestCase):
    def test_skips_pipelines_without_set_and_expired_sets(self):
        p = self.p
        self.gitlab.route("GET", rf"{p}/pipelines\?ref=main&per_page=50",
                          [{"id": 3, "status": "running"}, {"id": 2, "status": "failed"}, {"id": 1, "status": "failed"}])
        self.gitlab.route("GET", rf"{p}/pipelines/3/jobs\?per_page=100&scope\[\]=success", [])
        self.gitlab.route("GET", rf"{p}/pipelines/2/jobs\?per_page=100&scope\[\]=success",
                          [{"id": 22, "name": "publish dev set"}])
        self.gitlab.route("GET", rf"{p}/pipelines/1/jobs\?per_page=100&scope\[\]=success",
                          [{"id": 11, "name": "publish dev set"}])
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("dev-set/set.json", json.dumps({"pipeline": 1}))
        self.gitlab.route("GET", rf"{p}/jobs/22/artifacts", (404, {}))
        self.gitlab.route("GET", rf"{p}/jobs/11/artifacts", archive.getvalue())
        work = self.repo(FILES)
        result = self.api(work, "newest-dev-set", "--out", str(self.tmp / "prev"), check=True)
        self.assertIn("pipeline 1", result.stdout)
        self.assertEqual(json.loads((self.tmp / "prev/dev-set/set.json").read_text()), {"pipeline": 1})
        self.assertEqual(self.gitlab.sent("GET", rf"{p}/jobs/11/artifacts")[0]["headers"].get("job-token"), "job-token")


class CreateReleaseTest(ApiTestCase):
    def routes(self):
        p = self.p
        self.gitlab.route("GET", rf"{p}/repository/branches/release%2F1\.6", (404, {}))
        self.gitlab.route("GET", rf"{p}/repository/tags/v1\.6\.3", (404, {}))
        self.gitlab.route("POST", rf"{p}/repository/branches\?.*", (201, {}))
        self.gitlab.route("POST", rf"{p}/repository/tags", (201, {}))
        self.gitlab.route("GET", rf"{p}/labels\?search=backport-1\.6", [])
        self.gitlab.route("POST", rf"{p}/labels", (201, {}))

    def test_creates_branch_tag_and_label(self):
        self.routes()
        work = self.repo(FILES, tags=COMPONENT_TAGS)
        sha = git(work, "rev-parse", "HEAD")
        self.api(work, "create-release", check=True)
        branch = self.gitlab.sent("POST", rf"{self.p}/repository/branches\?.*")
        self.assertEqual(len(branch), 1)
        self.assertEqual(urllib.parse.parse_qs(branch[0]["path"].split("?")[1]),
                         {"branch": ["release/1.6"], "ref": [sha]})
        tag = json.loads(self.gitlab.sent("POST", rf"{self.p}/repository/tags")[0]["body"])
        self.assertEqual((tag["tag_name"], tag["ref"]), ("v1.6.3", sha))
        self.assertEqual(json.loads(self.gitlab.sent("POST", rf"{self.p}/labels")[0]["body"])["name"], "backport-1.6")
        self.assertEqual(branch[0]["headers"]["private-token"], "bot-token")

    def test_refuses_existing_branch(self):
        self.routes()
        self.gitlab.route("GET", rf"{self.p}/repository/branches/release%2F1\.6",
                          {"commit": {"id": "0" * 40, "short_id": "00000000"}})
        self.gitlab.route("GET", rf"{self.p}/repository/tags\?search=.*", [])
        work = self.repo(FILES, tags=COMPONENT_TAGS)
        result = self.api(work, "create-release")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("release/1.6 already exists", result.stderr)
        self.assertEqual(self.gitlab.sent("POST", r".*"), [])

    def test_fails_without_guessing_when_tags_unreadable(self):
        # The v1.6.0 mistake: origin unreachable must stop the job before anything is created.
        self.routes()
        work = self.repo(FILES, tags=COMPONENT_TAGS)
        git(work, "remote", "set-url", "origin", str(self.tmp / "missing.git"))
        result = self.api(work, "create-release")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cannot read the release tags", result.stderr)
        self.assertEqual(self.gitlab.sent("POST", r".*"), [])

    def test_refuses_existing_tag(self):
        self.routes()
        self.gitlab.route("GET", rf"{self.p}/repository/tags/v1\.6\.3", {"name": "v1.6.3"})
        work = self.repo(FILES, tags=COMPONENT_TAGS)
        result = self.api(work, "create-release")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.gitlab.sent("POST", r".*"), [])

    def test_needs_token(self):
        self.routes()
        work = self.repo(FILES, tags=COMPONENT_TAGS)
        result = self.api(work, "create-release", RELEASE_BOT_TOKEN="")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("RELEASE_BOT_TOKEN is not set", result.stderr)

    def test_api_error_fails(self):
        self.routes()
        self.gitlab.route("POST", rf"{self.p}/repository/tags", (403, {"message": "forbidden"}))
        work = self.repo(FILES, tags=COMPONENT_TAGS)
        result = self.api(work, "create-release")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("HTTP 403", result.stderr)


class TagPatchTest(ApiTestCase):
    def test_tags_next_patch(self):
        self.gitlab.route("GET", rf"{self.p}/repository/tags\?search=.*", [{"name": "v1.6.3", "commit": {"id": "x"}}])
        self.gitlab.route("POST", rf"{self.p}/repository/tags", (201, {}))
        work = self.repo(FILES, tags=COMPONENT_TAGS + ("v1.6.3",))
        self.api(work, "tag-patch", check=True, CI_COMMIT_BRANCH="release/1.6")
        self.assertEqual(json.loads(self.gitlab.sent("POST", rf"{self.p}/repository/tags")[0]["body"])["tag_name"],
                         "v1.6.4")

    def test_already_tagged_does_nothing(self):
        work = self.repo(FILES, tags=COMPONENT_TAGS)
        sha = git(work, "rev-parse", "HEAD")
        self.gitlab.route("GET", rf"{self.p}/repository/tags\?search=.*", [{"name": "v1.6.3", "commit": {"id": sha}}])
        self.api(work, "tag-patch", check=True, CI_COMMIT_BRANCH="release/1.6")
        self.assertEqual(self.gitlab.sent("POST", r".*"), [])

    def test_branch_must_match_version(self):
        work = self.repo(FILES, tags=COMPONENT_TAGS)
        result = self.api(work, "tag-patch", CI_COMMIT_BRANCH="release/1.5")
        self.assertNotEqual(result.returncode, 0)


class ProposeTest(ApiTestCase):
    def test_writes_version_and_opens_merge_request(self):
        p = self.p
        self.gitlab.route("POST", rf"{p}/repository/commits", (201, {}))
        self.gitlab.route("GET", rf"{p}/merge_requests\?state=opened&source_branch=release-bot%2Fnext", [])
        self.gitlab.route("POST", rf"{p}/merge_requests", (201, {"web_url": "https://mr/1"}))
        work = self.repo(FILES)
        (self.tmp / "report.md").write_text("No breaking changes.")
        self.api(work, "propose", "--version", "1.7", "--report", str(self.tmp / "report.md"), check=True)
        commit = json.loads(self.gitlab.sent("POST", rf"{p}/repository/commits")[0]["body"])
        self.assertEqual((commit["branch"], commit["start_branch"], commit["force"]), ("release-bot/next", "main", True))
        self.assertEqual(commit["actions"], [{"action": "update", "file_path": "VERSION", "content": "1.7\n"}])
        mr = json.loads(self.gitlab.sent("POST", rf"{p}/merge_requests")[0]["body"])
        self.assertEqual((mr["title"], mr["target_branch"]), ("Release 1.7", "main"))
        self.assertIn("No breaking changes.", mr["description"])

    def test_updates_open_merge_request(self):
        p = self.p
        self.gitlab.route("POST", rf"{p}/repository/commits", (201, {}))
        self.gitlab.route("GET", rf"{p}/merge_requests\?state=opened&source_branch=release-bot%2Fnext", [{"iid": 4}])
        self.gitlab.route("PUT", rf"{p}/merge_requests/4", {"web_url": "https://mr/4"})
        work = self.repo(FILES)
        (self.tmp / "report.md").write_text("r")
        self.api(work, "propose", "--version", "2.0", "--report", str(self.tmp / "report.md"), check=True)
        self.assertEqual(len(self.gitlab.sent("PUT", rf"{p}/merge_requests/4")), 1)
        self.assertEqual(self.gitlab.sent("POST", rf"{p}/merge_requests"), [])


class BackportTest(ApiTestCase):
    def history(self, conflict):
        """main with a merged change to b.txt; release/1.6 from before it (with its own b.txt if conflict)."""
        work = self.repo(FILES)
        (work / "b.txt").write_text("base\n")
        git(work, "add", "b.txt")
        git(work, "commit", "--quiet", "-m", "b")
        git(work, "checkout", "--quiet", "-b", "release/1.6")
        if conflict:
            (work / "b.txt").write_text("release line\n")
            git(work, "commit", "--quiet", "-am", "release-only change")
        git(work, "push", "--quiet", "origin", "release/1.6")
        git(work, "checkout", "--quiet", "main")
        git(work, "checkout", "--quiet", "-b", "fix")
        (work / "b.txt").write_text("fixed\n")
        git(work, "commit", "--quiet", "-am", "Fix b")
        git(work, "checkout", "--quiet", "main")
        git(work, "merge", "--quiet", "--no-ff", "fix", "-m", "Merge branch 'fix' into 'main'")
        git(work, "push", "--quiet", "origin", "main")
        sha = git(work, "rev-parse", "HEAD")
        p = self.p
        self.gitlab.route("GET", rf"{p}/repository/commits/{sha}/merge_requests",
                          [{"iid": 5, "state": "merged", "merge_commit_sha": sha, "labels": ["backport-1.6", "bug"],
                            "title": "Fix b"}])
        self.gitlab.route("GET", r"/api/v4/user", {"name": "Bot", "username": "bot", "email": "bot@example.com"})
        self.gitlab.route("GET", rf"{p}/repository/branches/release%2F1\.6", {"name": "release/1.6"})
        self.gitlab.route("GET", rf"{p}/repository/branches/backport%2F5-1\.6", (404, {}))
        self.gitlab.route("POST", rf"{p}/merge_requests", (201, {"iid": 9, "web_url": "https://mr/9"}))
        self.gitlab.route("POST", rf"{p}/merge_requests/5/notes", (201, {}))
        return work

    def test_clean_backport_opens_merge_request(self):
        work = self.history(conflict=False)
        self.api(work, "backport", check=True)
        origin = self.tmp / "work-origin.git"
        self.assertEqual(git(origin, "show", "backport/5-1.6:b.txt"), "fixed")
        mr = json.loads(self.gitlab.sent("POST", rf"{self.p}/merge_requests")[0]["body"])
        self.assertEqual((mr["source_branch"], mr["target_branch"]), ("backport/5-1.6", "release/1.6"))
        note = json.loads(self.gitlab.sent("POST", rf"{self.p}/merge_requests/5/notes")[0]["body"])
        self.assertIn("!9", note["body"])

    def test_conflict_comments_and_fails(self):
        work = self.history(conflict=True)
        result = self.api(work, "backport")
        self.assertNotEqual(result.returncode, 0)
        note = json.loads(self.gitlab.sent("POST", rf"{self.p}/merge_requests/5/notes")[0]["body"])
        self.assertIn("does not apply cleanly", note["body"])
        self.assertIn("`b.txt`", note["body"])
        self.assertEqual(self.gitlab.sent("POST", rf"{self.p}/merge_requests"), [])
        self.assertEqual(git(self.tmp / "work-origin.git", "branch", "--list", "backport/*"), "")

    def test_no_label_does_nothing(self):
        work = self.repo(FILES)
        sha = git(work, "rev-parse", "HEAD")
        self.gitlab.route("GET", rf"{self.p}/repository/commits/{sha}/merge_requests",
                          [{"iid": 5, "state": "merged", "merge_commit_sha": sha, "labels": ["bug"], "title": "x"}])
        result = self.api(work, "backport", check=True)
        self.assertIn("No merged merge request with a backport-X.Y label", result.stdout)


class PublishReleaseTest(ApiTestCase):
    def test_uploads_packages_and_creates_release(self):
        p = self.p
        d = self.tmp / "release"
        (d / "ubuntu24").mkdir(parents=True)
        (d / "ubuntu24/cognos-core_1.6.3-ubuntu24.04_amd64.deb").write_bytes(b"deb")
        (d / "set.json").write_text(json.dumps({"packages": [
            {"file": "ubuntu24/cognos-core_1.6.3-ubuntu24.04_amd64.deb", "os": "ubuntu24"}]}))
        self.gitlab.route("PUT", rf"{p}/packages/generic/cognos/1\.6\.3/.*", (201, {}))
        self.gitlab.route("GET", rf"{p}/releases/v1\.6\.3", (404, {}))
        self.gitlab.route("POST", rf"{p}/releases", (201, {}))
        work = self.repo(FILES)
        self.api(work, "publish-release", "--dir", str(d), check=True, CI_COMMIT_TAG="v1.6.3")
        uploads = self.gitlab.sent("PUT", rf"{p}/packages/generic/cognos/1\.6\.3/.*")
        self.assertEqual(sorted(u["path"].rsplit("/", 1)[1] for u in uploads),
                         ["cognos-core_1.6.3-ubuntu24.04_amd64.deb", "set.json"])
        self.assertTrue(all(u["headers"].get("job-token") == "job-token" for u in uploads))
        release = json.loads(self.gitlab.sent("POST", rf"{p}/releases")[0]["body"])
        self.assertEqual(release["tag_name"], "v1.6.3")
        self.assertEqual(len(release["assets"]["links"]), 2)


if __name__ == "__main__":
    unittest.main()
