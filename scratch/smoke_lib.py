"""
ReliefOS Production Smoke Test — shared harness library.

Design:
- All smoke data is synthetic and tagged with a run tag (e.g. "s09a1b2c").
- Stage scripts communicate via scratch/smoke_manifest.json.
- Responses are appended to scratch/smoke_responses.log for the stage-7
  log/response security sweep (the sweep scans what actually came back).
- Fail-fast: any failed check raises SmokeFailure with a clear label.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import uuid

import requests

_TOKEN_RE = re.compile(r'("token"\s*:\s*")[^"]+(")')

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

MANIFEST_PATH = os.path.join(HERE, "smoke_manifest.json")
RESPONSE_LOG = os.path.join(HERE, "smoke_responses.log")
BASE_URL = "http://127.0.0.1:5001"
ORG_COOKIE = "reliefos_org_id"


class SmokeFailure(AssertionError):
    pass


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

def load_manifest() -> dict:
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_manifest(m: dict) -> None:
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(m, f, indent=2)


def update_manifest(**kwargs) -> dict:
    m = load_manifest()
    m.update(kwargs)
    save_manifest(m)
    return m


def new_tag() -> str:
    return uuid.uuid4().hex[:8]


def record_ids(**kwargs) -> None:
    """Append synthetic entity ids to the manifest for precise cleanup.

    record_ids(needs=[id1], agent_events=[id2], ...) appends to
    manifest["ids"][key] lists.
    """
    m = load_manifest()
    ids = m.setdefault("ids", {})
    for key, val in kwargs.items():
        vals = val if isinstance(val, list) else [val]
        ids.setdefault(key, []).extend(v for v in vals if v)
    save_manifest(m)


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

CHECKS = {"pass": 0, "fail": 0}


def check(cond: bool, label: str, detail: str = "") -> None:
    if cond:
        CHECKS["pass"] += 1
        print(f"[PASS] {label}")
    else:
        CHECKS["fail"] += 1
        msg = f"[FAIL] {label}" + (f" — {detail}" if detail else "")
        print(msg)
        raise SmokeFailure(msg)


def finish_stage(name: str) -> None:
    print(f"=== {name}: {CHECKS['pass']} passed, {CHECKS['fail']} failed ===")
    if CHECKS["fail"]:
        raise SystemExit(1)


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------

def _log_response(path: str, r: requests.Response) -> None:
    """Record response for the stage-7 sweep.

    - /api/my-org/* responses are BY-DESIGN private (authorized org reading
      its own workspace) and are not persisted to the sweep log.
    - Session tokens are redacted: the sweep log must not become a
      credential store.
    """
    if path.startswith("/api/my-org"):
        return
    try:
        body = _TOKEN_RE.sub(r"\1[REDACTED]\2", r.text[:1500]).replace("\n", " ")
    except Exception:
        body = "<unprintable>"
    with open(RESPONSE_LOG, "a", encoding="utf-8") as f:
        f.write(f"{r.status_code} {path} :: {body}\n")


class Http:
    """Thin requests wrapper: bearer token + explicit org cookie per call."""

    def __init__(self, token: str | None = None, org: str | None = None):
        self.token = token
        self.org = org

    def request(self, method: str, path: str, **kw) -> requests.Response:
        headers = dict(kw.pop("headers", {}) or {})
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        cookies = dict(kw.pop("cookies", {}) or {})
        if self.org:
            cookies.setdefault(ORG_COOKIE, self.org)
        r = requests.request(method, BASE_URL + path, headers=headers,
                             cookies=cookies, timeout=90, **kw)
        _log_response(path, r)
        return r

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, **kw):
        return self.request("POST", path, **kw)

    def patch(self, path, **kw):
        return self.request("PATCH", path, **kw)

    def delete(self, path, **kw):
        return self.request("DELETE", path, **kw)


def anon() -> Http:
    return Http()


def login(username: str, password: str) -> dict:
    """Login over the real HTTP path; returns {token, user, memberships}."""
    r = anon().post("/api/auth/login", json={"username": username, "password": password})
    if r.status_code != 200:
        raise SmokeFailure(f"login failed for {username}: {r.status_code} {r.text[:200]}")
    return r.json()


# ---------------------------------------------------------------------------
# Server spawn / stop
# ---------------------------------------------------------------------------

def child_env(overrides: dict | None = None) -> dict:
    """Environment for the production server process.

    Loads .env for DATABASE_URL etc., then hardens the values the smoke run
    requires. Explicit os.environ values always win over dotenv defaults
    (python-dotenv does not override pre-set variables).
    """
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
    env = dict(os.environ)
    env.pop("RELIEFOS_MEMORY", None)  # durable PostgreSQL only
    env.setdefault("DATABASE_URL", "postgresql://reliefos:reliefos@localhost:5433/reliefos")
    env.update(overrides or {})
    return env


def spawn_server(log_path: str, overrides: dict | None = None) -> subprocess.Popen:
    logf = open(log_path, "ab")
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    proc = subprocess.Popen(
        [sys.executable, "-m", "agent.prod_startup"],
        cwd=ROOT, env=child_env(overrides),
        stdout=logf, stderr=subprocess.STDOUT,
        creationflags=flags,
    )
    return proc


def wait_ready(timeout: float = 90.0) -> bool:
    """Poll the liveness/readiness probes until the server answers, or False."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(BASE_URL + "/api/health/liveness", timeout=3)
            if r.status_code == 200:
                r2 = requests.get(BASE_URL + "/api/health/readiness", timeout=5)
                if r2.status_code == 200:
                    return True
        except requests.RequestException:
            pass
        time.sleep(1.0)
    return False


def kill_server(pid: int) -> None:
    """Terminate the server process (hard kill = crash-restart scenario)."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                       capture_output=True, timeout=30)
    else:
        import signal
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    # Wait until the port actually stops answering.
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            requests.get(BASE_URL + "/api/health/liveness", timeout=2)
            time.sleep(0.5)
        except requests.RequestException:
            return


# ---------------------------------------------------------------------------
# Security scanning
# ---------------------------------------------------------------------------

FORBIDDEN_IN_RESPONSES = [
    "postgresql://",
    "reliefos-default-secret-key",
    "password_hash",
    "Traceback (most recent call last)",
    "private_factors",
]


def scan_text_for_leaks(text: str, extra_patterns: list[str] | None = None) -> list[str]:
    patterns = list(FORBIDDEN_IN_RESPONSES) + list(extra_patterns or [])
    hits = []
    for p in patterns:
        if p and p in text:
            hits.append(p)
    return hits


def scan_response(r: requests.Response, label: str, extra: list[str] | None = None) -> None:
    """Assert a single response carries no secrets / private data / stack traces."""
    hits = scan_text_for_leaks(r.text, extra)
    check(not hits, f"no leaks in {label}", f"found patterns: {hits}")
