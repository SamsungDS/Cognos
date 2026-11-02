"""Shared pieces of the CI script tests: a fake GitLab API, throwaway git repositories, stand-in commands.

Nothing here talks to the real GitLab, Docker or the network.
"""

import http.server
import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import threading
import unittest

REPO = pathlib.Path(__file__).resolve().parents[3]
PROJECT = "dfs%2Fsvk%2Fcognos"


def sh(*command, cwd=None, env=None, check=True):
    """Runs a command; returns the CompletedProcess (stdout and stderr as text)."""
    result = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True)
    if check and result.returncode != 0:
        raise AssertionError(f"{command} failed ({result.returncode}):\n{result.stdout}\n{result.stderr}")
    return result


def git(cwd, *args):
    return sh("git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "-c", "init.defaultBranch=main",
              *args, cwd=cwd).stdout.strip()


class FakeGitLab:
    """A local HTTP server answering like the GitLab API, from routes a test registers.

    route(method, pattern, response): pattern is a regex matched against the full request path including the query
    string; response is JSON-able data, bytes, a (status, data) tuple, or a function(request) returning one of those.
    Every request is recorded in .requests as dict(method, path, headers (names in lower case), body).
    """

    def __init__(self):
        self.routes, self.requests = [], []
        fake = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def handle_any(self):
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                request = {"method": self.command, "path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}, "body": body}
                fake.requests.append(request)
                for method, pattern, response in reversed(fake.routes):
                    if method == self.command and re.fullmatch(pattern, self.path):
                        if callable(response):
                            response = response(request)
                        status, data = response if isinstance(response, tuple) else (200, response)
                        payload = data if isinstance(data, bytes) else json.dumps(data).encode()
                        self.send_response(status)
                        self.send_header("Content-Length", str(len(payload)))
                        self.end_headers()
                        self.wfile.write(payload)
                        return
                self.send_response(404)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")

            do_GET = do_POST = do_PUT = do_DELETE = handle_any

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.api = f"{self.url}/api/v4"
        self.project = f"/api/v4/projects/{PROJECT}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def route(self, method, pattern, response):
        self.routes.append((method, pattern, response))

    def sent(self, method, pattern):
        """The recorded requests matching method and pattern (regex on the path)."""
        return [r for r in self.requests if r["method"] == method and re.fullmatch(pattern, r["path"])]

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class TempDirTestCase(unittest.TestCase):
    """A test case with a fresh temporary directory, self.tmp."""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="ci-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def stub(self, name, script):
        """A stand-in command `name` (a shell script) in self.tmp/bin; returns that bin directory."""
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir(exist_ok=True)
        path = bin_dir / name
        path.write_text("#!/bin/sh\n" + script)
        path.chmod(0o755)
        return bin_dir

    def env(self, **extra):
        """The environment with self.tmp/bin first on PATH (if it exists), plus extra."""
        env = dict(os.environ)
        if (self.tmp / "bin").is_dir():
            env["PATH"] = f"{self.tmp / 'bin'}:{env['PATH']}"
        env.update({k: str(v) for k, v in extra.items()})
        return env

    def repo(self, files=(), version="1.6", tags=(), name="work"):
        """A git repository with copies of the given repository files, VERSION, one commit, and an 'origin'
        (a bare repository) holding the given tags. Returns the work tree path."""
        origin = self.tmp / f"{name}-origin.git"
        work = self.tmp / name
        git(self.tmp, "init", "--quiet", "--bare", str(origin))
        git(self.tmp, "init", "--quiet", str(work))
        for rel in files:
            target = work / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / rel, target)
        (work / "VERSION").write_text(version + "\n")
        git(work, "add", "-A")
        git(work, "commit", "--quiet", "-m", "initial")
        git(work, "remote", "add", "origin", str(origin))
        for tag in tags:
            git(work, "tag", "-a", tag, "-m", tag)
        git(work, "push", "--quiet", "origin", "main", "--tags")
        return work
