"""Minimal GitHub client on urllib (no extra dependencies)."""
from __future__ import annotations

import base64
import json
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.github.com"
TIMEOUT = 60


class GitHubError(Exception):
    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status


def parse_repo(text: str) -> str:
    """Accept "owner/name", a github.com URL or a git URL and return "owner/name" ("" if invalid)."""
    text = (text or "").strip()
    m = re.match(r"^(?:https?://)?(?:www\.)?github\.com[/:]([\w.-]+)/([\w.-]+?)(?:\.git)?(?:/.*)?$", text) \
        or re.match(r"^git@github\.com:([\w.-]+)/([\w.-]+?)(?:\.git)?$", text) \
        or re.match(r"^([\w.-]+)/([\w.-]+)$", text)
    return f"{m.group(1)}/{m.group(2)}" if m else ""


def _ssl_context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


class _StripAuthOnRedirect(urllib.request.HTTPRedirectHandler):
    """Tarball downloads redirect to codeload.github.com: never forward the token to another host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and urllib.parse.urlparse(newurl).hostname != urllib.parse.urlparse(req.full_url).hostname:
            new.remove_header("Authorization")
        return new


class GitHub:
    def __init__(self, token: str = ""):
        self.token = (token or "").strip()
        self._ctx = _ssl_context()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=self._ctx), _StripAuthOnRedirect())

    def _open(self, url: str, method: str = "GET", body: bytes | None = None, accept: str = "application/vnd.github+json"):
        headers = {"User-Agent": "RepoBrain", "Accept": accept, "X-GitHub-Api-Version": "2022-11-28"}
        if self.token and urllib.parse.urlparse(url).hostname in ("api.github.com",):
            headers["Authorization"] = f"Bearer {self.token}"
        if body is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            return self._opener.open(req, timeout=TIMEOUT)
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = json.loads(e.read().decode("utf-8", "replace")).get("message", "")
            except Exception:
                pass
            if e.code == 403 and "rate limit" in detail.lower():
                raise GitHubError("GitHub rate limit reached - add a GitHub token in Settings", e.code) from None
            if e.code in (401, 403):
                raise GitHubError(f"GitHub refused access ({e.code}) - check the token: {detail}", e.code) from None
            if e.code == 404:
                raise GitHubError(f"Not found on GitHub (or private without a token): {url}", e.code) from None
            raise GitHubError(f"GitHub error {e.code}: {detail or e.reason}", e.code) from None
        except urllib.error.URLError as e:
            raise GitHubError(f"Cannot reach GitHub: {e.reason}") from None

    def _json(self, path: str, method: str = "GET", payload: dict | None = None):
        body = json.dumps(payload).encode() if payload is not None else None
        with self._open(API + path, method, body) as resp:
            return json.loads(resp.read().decode("utf-8"))

    # ---- reading ----
    def repo_info(self, repo: str) -> dict:
        return self._json(f"/repos/{repo}")

    def default_branch(self, repo: str) -> str:
        return self.repo_info(repo).get("default_branch", "main")

    def head_sha(self, repo: str, branch: str) -> str:
        ref = urllib.parse.quote(branch, safe="")
        with self._open(f"{API}/repos/{repo}/commits/{ref}", accept="application/vnd.github.sha") as resp:
            return resp.read().decode().strip()

    def compare(self, repo: str, base: str, head: str) -> dict:
        """Changed files between two commits: {"status": ..., "files": [{"filename", "status", "previous_filename"}]}."""
        return self._json(f"/repos/{repo}/compare/{base}...{head}?per_page=300")

    def open_tarball(self, repo: str, ref: str):
        """A streaming response with the repository as .tar.gz at `ref`."""
        if self.token:
            return self._open(f"{API}/repos/{repo}/tarball/{ref}", accept="application/vnd.github+json")
        return self._open(f"https://codeload.github.com/{repo}/tar.gz/{ref}", accept="*/*")

    def raw_file(self, repo: str, ref: str, path: str) -> bytes:
        quoted = urllib.parse.quote(path)
        if self.token:  # private repos need the API; it also avoids caching delays on raw.githubusercontent.com
            url = f"{API}/repos/{repo}/contents/{quoted}?ref={ref}"
            with self._open(url, accept="application/vnd.github.raw") as resp:
                return resp.read()
        with self._open(f"https://raw.githubusercontent.com/{repo}/{ref}/{quoted}", accept="*/*") as resp:
            return resp.read()

    def current_user(self) -> str:
        return self._json("/user").get("login", "")

    # ---- writing ----
    def file_sha(self, repo: str, branch: str, path: str) -> str:
        ref = f"?ref={urllib.parse.quote(branch)}" if branch else ""
        return self._json(f"/repos/{repo}/contents/{urllib.parse.quote(path)}{ref}").get("sha", "")

    def put_file(self, repo: str, branch: str, path: str, content: bytes, message: str, sha: str = "") -> dict:
        if not self.token:
            raise GitHubError("A GitHub token is needed to add shared knowledge")
        payload = {"message": message, "content": base64.b64encode(content).decode()}
        if branch:
            payload["branch"] = branch
        if sha:
            payload["sha"] = sha  # required when replacing an existing file
        return self._json(f"/repos/{repo}/contents/{urllib.parse.quote(path)}", "PUT", payload)
