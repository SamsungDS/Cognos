"""Checks of gitlab/.gitlab-ci.yml that its jobs depend on but that GitLab's CI Lint does not catch."""

import re
import unittest

from helpers import REPO

CONFIG = (REPO / "gitlab/.gitlab-ci.yml").read_text()


def before_scripts():
    """(job name, its before_script lines) for every before_script written in the file."""
    found, job = [], None
    lines = CONFIG.splitlines()
    for i, line in enumerate(lines):
        if re.match(r"^[.A-Za-z][^:#]*:\s*$", line):
            job = line[:-1].strip()
        if line == "  before_script:":
            block = []
            for nxt in lines[i + 1:]:
                if not nxt.startswith("    "):
                    break
                block.append(nxt.strip())
            found.append((job, block))
    return found


class CiConfigTest(unittest.TestCase):
    def test_every_job_computing_the_version_trusts_the_internal_ca(self):
        # ci/version.sh reads origin's release tags with git on release branches (X.Y.Z~rc): without the CA setup
        # git cannot reach this GitLab (the release/1.6 "test sapp" failure).
        jobs = [(job, block) for job, block in before_scripts() if "- !reference [.version, before_script]" in block]
        self.assertGreater(len(jobs), 3)
        for job, block in jobs:
            with self.subTest(job=job):
                self.assertIn("- !reference [.internal-ca, before_script]", block)
                self.assertLess(block.index("- !reference [.internal-ca, before_script]"),
                                block.index("- !reference [.version, before_script]"))

    def test_the_ca_setup_covers_git_python_and_curl(self):
        ca = CONFIG[CONFIG.index(".internal-ca:"):CONFIG.index(".version:")]
        for variable in ("SSL_CERT_FILE", "GIT_SSL_CAINFO"):
            self.assertIn(variable, ca)

    def test_jobs_outside_a_release_skip_tag_pipelines(self):
        for job in ("test amo-prof:", ".deploy:"):
            block = CONFIG[CONFIG.index("\n" + job):][:900]
            rules = block[block.index("  rules:"):]
            with self.subTest(job=job):
                self.assertRegex(rules, r"- if: \$CI_COMMIT_TAG\n\s+when: never")

    def test_deploy_is_manual_and_stops_without_the_key(self):
        block = CONFIG[CONFIG.index("\ndeploy cognos:"):]
        block = block[:block.index("\n  script:")]
        rules = block[block.index("  rules:"):block.index("  variables:")]
        for source in (r'\$CI_COMMIT_BRANCH == "main"', r'\$CI_PIPELINE_SOURCE == "merge_request_event"'):
            with self.subTest(rule=source):
                self.assertRegex(rules, source + r".*\n\s+when: manual\n\s+allow_failure: true")
        self.assertEqual(rules.count("when: manual"), rules.count("- if:"))
        # A pipeline without the protected key fails at once, before any host is touched.
        self.assertLess(block.index('if [ -z "${DEPLOY_SSH_KEY:-}" ]'), block.index("base64 -d"))

    def test_unit_tests_retry_once(self):
        block = CONFIG[CONFIG.index("\n.test:"):][:600]
        self.assertRegex(block, r"retry:\n\s+max: 1\n\s+when: \[script_failure\]")


if __name__ == "__main__":
    unittest.main()
