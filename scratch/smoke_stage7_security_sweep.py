"""
ReliefOS Smoke Stage 7 — Task 7: Log / response security check.

Scans:
- every captured HTTP response body (scratch/smoke_responses.log)
- the production server startup log (two boots) and runtime log
for: stack traces, DB URLs, passwords/secret keys, env secrets, private NGO
inventories, private staff info, internal agent state, raw exception payloads.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from smoke_lib import (  # noqa: E402
    load_manifest, check, finish_stage, HERE, ROOT,
)

m = load_manifest()
tag = m["tag"]
restart = m.get("restart", {})

LOG_PATHS = [
    os.path.join(HERE, "smoke_server_boot.log"),   # both boots + runtime
    os.path.join(HERE, "smoke_responses.log"),      # captured HTTP responses
]

# Patterns that must NEVER appear in logs or responses
SECRET_PATTERNS = [
    # stack traces / raw exceptions
    "Traceback (most recent call last)",
    # infrastructure secrets
    "postgresql://",
    "psycopg2",
    "SECRET",          # catches RELIEFOS_SECRET_KEY=..., "SECRET_KEY", etc.
    "PASSWORD",
    "password=",
    "reliefos-default-secret-key",
    "BEGIN PRIVATE KEY",
    "AWS_ACCESS_KEY",
    "AWS_SECRET",
]

# Private data markers used in this smoke run (must never cross public/log surfaces)
PRIVATE_MARKERS = [
    restart.get("private_marker", ""),
    "Alpha private warehouse",
]

# User password used during the smoke run (never log it)
PASSWORD = m["password"]


def scan_file(path: str, patterns: list[str], allow_map: dict[str, list[str]] | None = None):
    """Return list of (pattern, line_no, line) hits for a file.

    allow_map lets a pattern be legitimately present on specific lines
    (e.g. the sweep tool's own marker strings in the harness log).
    """
    hits = []
    if not os.path.exists(path):
        return hits, False
    allow_map = allow_map or {}
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f, 1):
            for p in patterns:
                if p and p in line:
                    allowed = any(a in line for a in allow_map.get(p, []))
                    if not allowed:
                        hits.append((p, i, line.rstrip()[:200]))
    return hits, True


all_clean = True

for path in LOG_PATHS:
    name = os.path.basename(path)
    exists = os.path.exists(path)
    check(exists, f"{name} exists for sweep")
    if not exists:
        all_clean = False
        continue

    patterns = list(SECRET_PATTERNS) + [p for p in PRIVATE_MARKERS if p] + [PASSWORD]
    allow = {"SECRET": ["SECRETS PRESENT", "secret patterns"],
             "PASSWORD": ["PASSWORD PRESENT"]}
    hits, _ = scan_file(path, patterns, allow)

    # Whitelisted harness echo lines (stage prints of its own labels) are
    # already excluded via allow_map; anything else is a failure.
    for p, lineno, line in hits[:10]:
        print(f"  LEAK {name}:{lineno} pattern={p!r} line={line!r}")
    check(not hits, f"{name} free of secrets/stack-traces/private-data",
          f"{len(hits)} hits: {[h[0] for h in hits[:5]]}")

# Additional targeted checks on the startup log
boot_log = os.path.join(HERE, "smoke_server_boot.log")
if os.path.exists(boot_log):
    with open(boot_log, "r", encoding="utf-8", errors="replace") as f:
        boot_text = f.read()
    # Useful startup logs present
    for needle in ("Initializing ReliefOS", "Active Repository",
                   "Durable PostgreSQL schema initialized", "Event worker started",
                   "Stale event recovery loop started"):
        check(needle in boot_text, f"startup log contains '{needle}'")
    # Explicit optional-component messaging
    check("Proactive scheduler" in boot_text,
          "startup log states proactive scheduler status explicitly")

# Private marker must not appear in ANY server log (double-check with the
# org file store path contents as source of truth)
for path in LOG_PATHS:
    if os.path.exists(path) and restart.get("private_marker"):
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            txt = f.read()
        check(restart["private_marker"] not in txt,
              f"{os.path.basename(path)} carries no private inventory marker")

finish_stage("stage7_security_sweep")
