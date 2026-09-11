"""
ReliefOS Proactive Scheduler — Phase 2B

Provides a stoppable, bounded in-process background thread scheduler
that executes periodic proactive scans without external dependencies (no Celery, Redis, Cron).
"""

from __future__ import annotations

import logging
import os
import time
import threading
from datetime import datetime, timezone
from typing import Any, Optional

from agent.proactive.runtime import ProactiveRuntime

logger = logging.getLogger("reliefos.scheduler")


class ProactiveScheduler:
    """
    In-process scheduler for periodic proactive disaster state inspections.
    """
    def __init__(self, runtime: Optional[ProactiveRuntime] = None):
        self.runtime = runtime or ProactiveRuntime()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        # Single-flight guard: run_once also holds ProactiveRuntime._lock, but
        # an explicit condition here keeps the scheduler thread from even
        # STARTING a scan while a manual/API trigger is mid-flight, and lets a
        # triggered scan wait for a scheduled one to finish.
        self._scan_lock = threading.Condition()
        self._scan_in_progress = False
        self._interval_seconds = float(
            os.environ.get("RELIEFOS_PROACTIVE_INTERVAL_SECONDS", "")
            or __import__("agent.config", fromlist=["get_settings"]).get_settings().proactive_scan_interval_seconds
        )
        self._last_run_at: Optional[datetime] = None
        self._total_runs = 0
        self._last_scan_id: Optional[str] = None
        self._last_error: Optional[str] = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, interval_seconds: Optional[float] = None) -> None:
        """
        Start the background periodic scan loop.
        """
        if self.is_running:
            return

        if interval_seconds is not None:
            self._interval_seconds = max(5.0, float(interval_seconds))

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="reliefos-proactive-scheduler",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """
        Stop the background scheduler cleanly.
        """
        if not self.is_running:
            return

        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=timeout)
            self._thread = None

    def trigger_now(self, scope: Optional[dict[str, Any]] = None) -> Any:
        """
        Trigger an immediate proactive scan cycle synchronously.
        Waits for any in-flight scheduled scan to finish first.
        """
        with self._scan_lock:
            while self._scan_in_progress:
                self._scan_lock.wait(timeout=30)
                if self._stop_event.is_set():
                    raise RuntimeError("Scheduler stopped while waiting for in-flight scan")
            self._scan_in_progress = True
        try:
            scan = self.runtime.run_once(scope=scope, trigger="manual_api")
            self._last_run_at = datetime.now(timezone.utc)
            self._total_runs += 1
            self._last_scan_id = scan.id
            return scan
        finally:
            with self._scan_lock:
                self._scan_in_progress = False
                self._scan_lock.notify_all()

    def get_status(self) -> dict[str, Any]:
        """
        Return current scheduler telemetry.
        """
        return {
            "is_running": self.is_running,
            "interval_seconds": self._interval_seconds,
            "total_runs": self._total_runs,
            "last_run_at": self._last_run_at.isoformat() if self._last_run_at else None,
            "last_scan_id": self._last_scan_id,
            "last_error": self._last_error,
        }

    def _run_loop(self) -> None:
        """Background thread loop."""
        while not self._stop_event.is_set():
            # Single-flight: skip this tick if a manual trigger holds the slot.
            with self._scan_lock:
                if self._scan_in_progress:
                    logger.debug("Scheduled scan skipped — manual scan in progress")
                    self._stop_event.wait(timeout=self._interval_seconds)
                    continue
                self._scan_in_progress = True
            try:
                scan = self.runtime.run_once(trigger="scheduled")
                self._last_run_at = datetime.now(timezone.utc)
                self._total_runs += 1
                self._last_scan_id = scan.id
                self._last_error = None
            except Exception as e:
                # A failed scan must not kill the scheduler thread.
                self._last_error = str(e)
                logger.exception("Scheduled proactive scan failed: %s", e)
            finally:
                with self._scan_lock:
                    self._scan_in_progress = False
                    self._scan_lock.notify_all()

            # Wait for interval or stop event
            self._stop_event.wait(timeout=self._interval_seconds)


# Global singleton scheduler instance
_global_scheduler: Optional[ProactiveScheduler] = None


def get_proactive_scheduler() -> ProactiveScheduler:
    global _global_scheduler
    if _global_scheduler is None:
        _global_scheduler = ProactiveScheduler()
    return _global_scheduler


def start_proactive_scheduler(interval_seconds: Optional[float] = None) -> ProactiveScheduler:
    """Start the global singleton proactive scheduler and return it.

    Used by prod_startup; the scheduler thread is a daemon so process exit
    reclaims it. Raises nothing on repeated calls — an already-running
    scheduler is returned as-is.
    """
    scheduler = get_proactive_scheduler()
    scheduler.start(interval_seconds=interval_seconds)
    logger.info(
        "Proactive scheduler start requested (running=%s, interval=%ss)",
        scheduler.is_running,
        scheduler._interval_seconds,
    )
    return scheduler


def stop_proactive_scheduler(timeout: float = 5.0) -> None:
    """Stop the global singleton proactive scheduler cleanly."""
    scheduler = get_proactive_scheduler()
    scheduler.stop(timeout=timeout)
