"""
ReliefOS Smoke Runner — orchestrates the full production smoke test.

Sequence:
  1. stage0  bootstrap synthetic orgs/users (service layer, pre-server)
  2. start production server via agent.prod_startup (ENVIRONMENT=production,
     AUTH_ENFORCED=true, waitress) — captures boot log
  3. stage1  security smoke (auth + org isolation)
  4. stage2  consequential workflow smoke (HITL lifecycle)
  5. stage3  event runtime smoke (outbox)
  6. stage4  proactive runtime smoke
  7. stage5a create persistence state, then KILL server
  8. restart production server (second boot; boot log captures stale recovery)
  9. stage5b verify persistence after restart
 10. stage7  log/response security sweep
 11. cleanup synthetic smoke data (orgs, users, memberships, DB rows,
     file-backed private workspace entries)
"""

import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from smoke_lib import (  # noqa: E402
    HERE, ROOT, spawn_server, wait_ready, kill_server, load_manifest,
    save_manifest, child_env, RESPONSE_LOG,
)

BOOT_LOG = os.path.join(HERE, "smoke_server_boot.log")   # boot-1, boot-2 + runtime
RUNTIME_LOG = BOOT_LOG

STAGES = [
    ("stage1_security", "smoke_stage1_security.py"),
    ("stage2_workflow", "smoke_stage2_workflow.py"),
    ("stage3_events", "smoke_stage3_events.py"),
    ("stage4_proactive", "smoke_stage4_proactive.py"),
    ("stage5a_persist", "smoke_stage5a_persist.py"),
]


def run_stage(script: str) -> None:
    print(f"\n########## RUN {script} ##########")
    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, script)],
        cwd=ROOT, capture_output=True, text=True, timeout=1200,
    )
    out = (proc.stdout or "") + (("\n[stderr] " + proc.stderr) if proc.stderr.strip() else "")
    print(out[-6000:])
    if proc.returncode != 0:
        print(f"!!! STAGE FAILED: {script} (exit {proc.returncode})")
        raise SystemExit(f"smoke stage failed: {script}")


# Production-mode overrides for BOTH boots — the smoke test verifies the
# hardened startup path (fail-fast config validation, fail-closed auth).
PROD_OVERRIDES = {
    "ENVIRONMENT": "production",
    "AUTH_ENFORCED": "true",
}


def start_production_server(log_path: str) -> int:
    """Start the hardened production server and wait for readiness."""
    with open(log_path, "ab") as lf:
        lf.write(f"\n===== BOOT {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n".encode())
    proc = spawn_server(log_path, overrides=PROD_OVERRIDES)
    if not wait_ready(timeout=120):
        # Dump the tail of the boot log to expose the failure, then abort.
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            tail = f.read()[-3000:]
        print("SERVER FAILED TO BECOME READY. Boot log tail:\n", tail)
        try:
            kill_server(proc.pid)
        except Exception:
            pass
        raise SystemExit("production server did not become ready")
    m = load_manifest()
    m["server_pid"] = proc.pid
    save_manifest(m)
    print(f"production server ready (pid={proc.pid})")
    return proc.pid


def main() -> int:
    # Fresh manifest + response log for this run (boot log holds both boots)
    for p in (os.path.join(HERE, "smoke_manifest.json"), RESPONSE_LOG, BOOT_LOG):
        if os.path.exists(p):
            os.remove(p)
    open(BOOT_LOG, "wb").close()

    # --- Stage 0: bootstrap (no server needed) -----------------------------
    print("########## RUN stage0_bootstrap ##########")
    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, "smoke_stage0_bootstrap.py")],
        cwd=ROOT, capture_output=True, text=True, timeout=300,
    )
    print((proc.stdout or "")[-3000:])
    if proc.stderr.strip():
        print("[stderr]", proc.stderr[-2000:])
    if proc.returncode != 0:
        return fail("stage0_bootstrap")

    # --- Boot 1 -------------------------------------------------------------
    pid = start_production_server(BOOT_LOG)
    failures = []
    try:
        for name, script in STAGES:
            try:
                run_stage(script)
            except SystemExit as e:
                failures.append(f"{name}: {e}")
                break
    finally:
        if failures:
            # Leave a trace of server logs before tearing down
            print("Stage failure — server log tail follows in stage output.")

    # --- Kill (stage5a already killed if it ran; kill again is safe) --------
    m = load_manifest()
    if m.get("server_pid"):
        try:
            kill_server(m["server_pid"])
        except Exception:
            pass

    if failures:
        print("\nSMOKE RUN FAILED:", failures)
        return 1

    # --- Boot 2 (restart) ----------------------------------------------------
    print("\n########## RESTART production server ##########")
    pid2 = start_production_server(BOOT_LOG)  # append to same boot log
    try:
        run_stage("smoke_stage5b_restart.py")
        run_stage("smoke_stage7_security_sweep.py")
    finally:
        m = load_manifest()
        if m.get("server_pid"):
            try:
                kill_server(m["server_pid"])
            except Exception:
                pass

    # --- Cleanup synthetic data ----------------------------------------------
    print("\n########## CLEANUP synthetic smoke data ##########")
    cleanup = subprocess.run(
        [sys.executable, os.path.join(HERE, "smoke_cleanup.py")],
        cwd=ROOT, capture_output=True, text=True, timeout=300,
    )
    print((cleanup.stdout or "")[-2000:])
    if cleanup.returncode != 0:
        print("[cleanup stderr]", (cleanup.stderr or "")[-1500:])

    print("\n=== PRODUCTION SMOKE RUN COMPLETE: ALL STAGES PASSED ===")
    return 0


def fail(stage: str) -> int:
    print(f"!!! STAGE FAILED: {stage}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
