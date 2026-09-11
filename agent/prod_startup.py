"""
ReliefOS Production Startup & Entrypoint

Performs fail-fast configuration validation, verifies durable PostgreSQL connectivity,
runs pending schema creations/migrations, starts the outbox worker and stale claim
recovery loops, starts background proactive scheduler threads, and exposes the
WSGI application.

Component policy (explicit, configuration-driven):
  - Database initialization is MANDATORY: a failure aborts startup in every
    environment — the application cannot operate without durable state.
  - The AgentEvent worker is MANDATORY when enabled (EVENT_WORKER_REQUIRED=true,
    the default): without it the outbox never drains and coordination stalls.
  - The proactive scheduler is OPTIONAL (PROACTIVE_SCHEDULER_REQUIRED=false, the
    default): it enriches coordination but the platform remains operable without
    it. Failures degrade loudly with a warning instead of aborting.
"""

from __future__ import annotations

import logging
import os
import sys
import threading

# Configure structured logging. Never log secrets: messages must not include
# connection strings, tokens, or request bodies.
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("reliefos.prod_startup")


def init_production_application():
    """
    Initialize, validate, and prepare ReliefOS backend for production traffic.
    """
    from agent.config import get_settings
    settings = get_settings()

    logger.info("Initializing ReliefOS in environment: %s", settings.environment)

    # 1. Validate Production Configuration (fail fast in production)
    errors = settings.validate_production_readiness()
    if errors:
        for err in errors:
            logger.critical("CONFIGURATION ERROR: %s", err)
        if settings.is_production:
            raise RuntimeError(f"Production readiness validation failed: {'; '.join(errors)}")

    startup_failures: list[str] = []

    # 2. Database Connection & Schema Verification (MANDATORY — including
    #    additive migrations). No database means no durable state at all.
    from agent.data.repository import get_repository
    repo = get_repository()
    logger.info("Active Repository: %s", type(repo).__name__)

    if hasattr(repo, "_engine") and repo._engine is not None:
        try:
            from agent.data.schema import create_all_tables, run_migrations
            create_all_tables(repo._engine)
            applied = run_migrations(repo._engine)
            logger.info("Durable PostgreSQL schema initialized (%d migration steps applied).", len(applied))
        except Exception as e:
            logger.critical("Database initialization failed: %s", e)
            # Mandatory in every environment: without schema init the app is
            # unsafe to operate, not merely degraded.
            raise
    else:
        msg = "Repository has no SQLAlchemy engine (in-memory fallback) — durable storage unavailable."
        if settings.is_production:
            logger.critical(msg)
            raise RuntimeError(msg)
        logger.warning(msg)

    # 3. Stale Agent Event Recovery (one-shot at boot: requeue events orphaned
    #    by a previous crash before the worker starts claiming fresh ones).
    #    Recoverable — the periodic loop retries; degrade loudly, do not abort.
    try:
        from agent.agents.event_router import get_event_dispatcher
        dispatcher = get_event_dispatcher()
        recovered = dispatcher.recover_stale_events(repo=repo, stale_threshold_seconds=settings.stale_event_threshold_seconds)
        if recovered > 0:
            logger.warning("Startup recovered %d stale outbox events.", recovered)
    except Exception as e:
        logger.error("Initial stale event recovery failed (periodic loop will retry): %s", e)

    # 4. Outbox worker + periodic stale-claim recovery loop (in-process).
    if settings.event_worker_enabled:
        started = False
        try:
            from agent.agents.event_router import start_event_worker, start_stale_recovery_loop
            worker_thread = start_event_worker(
                poll_seconds=settings.event_worker_poll_seconds,
                batch_size=settings.event_worker_batch_size,
            )
            started = bool(worker_thread and worker_thread.is_alive())
            start_stale_recovery_loop(
                interval_seconds=settings.stale_event_recovery_interval_seconds,
                stale_threshold_seconds=settings.stale_event_threshold_seconds,
            )
            logger.info(
                "Event worker started (poll=%ss, batch=%s).",
                settings.event_worker_poll_seconds,
                settings.event_worker_batch_size,
            )
        except Exception as e:
            logger.error("Event worker startup failed: %s", e)
        if not started:
            startup_failures.append(
                "event worker failed to start (EVENT_WORKER_REQUIRED=true means this is fatal)"
            )
    else:
        logger.info("Event worker disabled via EVENT_WORKER_ENABLED=false.")

    # 5. Proactive Intelligence Background Scheduler (OPTIONAL — enriches
    #    coordination; the platform operates without it).
    if settings.proactive_scheduler_enabled:
        try:
            from agent.proactive.scheduler import start_proactive_scheduler
            start_proactive_scheduler(interval_seconds=settings.proactive_scan_interval_seconds)
            logger.info("Background proactive scheduler started (interval=%ds).", settings.proactive_scan_interval_seconds)
        except Exception as e:
            if settings.proactive_scheduler_required:
                startup_failures.append(f"proactive scheduler failed to start: {e}")
            else:
                logger.warning("Proactive scheduler not started (optional component): %s", e)
    else:
        logger.info("Proactive scheduler disabled via PROACTIVE_SCHEDULER_ENABLED=false.")

    # 6. Abort on mandatory-component failures (production), warn otherwise.
    if startup_failures:
        if settings.is_production or settings.event_worker_required:
            for failure in startup_failures:
                logger.critical("STARTUP FAILURE: %s", failure)
            raise RuntimeError(f"Mandatory startup components failed: {'; '.join(startup_failures)}")
        for failure in startup_failures:
            logger.warning("STARTUP DEGRADED: %s", failure)

    # 7. Import and return Flask application
    from agent.api import app
    return app


def start_event_worker_loop(poll_seconds: int = 5, batch_size: int = 10) -> threading.Thread:
    """Compatibility shim retained for older tooling; see event_router.start_event_worker."""
    from agent.agents.event_router import start_event_worker
    return start_event_worker(poll_seconds=poll_seconds, batch_size=batch_size)


def _load_wsgi_app():
    """Load the WSGI app without aborting module import when initialization
    fails — the failure is logged and re-raised by the server instead, so
    misconfiguration surfaces as a crash of the serving process rather than
    an import-time side effect."""
    return init_production_application()


# WSGI entrypoint for Gunicorn/uWSGI/Waitress.
# Initialization failures MUST abort the process: a silently degraded
# application must never report itself as production-ready.
app = init_production_application()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    host = os.environ.get("HOST", "0.0.0.0")
    logger.info("Starting ReliefOS production server on %s:%d", host, port)
    try:
        import waitress
        waitress.serve(app, host=host, port=port, threads=8)
    except ImportError:
        logger.info("Waitress not found, using standard WSGI server")
        app.run(host=host, port=port, debug=False)
