"""
ReliefOS Observability & Request Tracing Middleware

Injects unique request correlation IDs (X-Request-ID), measures execution latency,
and produces structured request access logs.
"""

from __future__ import annotations

import logging
import time
import uuid
from flask import Flask, Response, g, request

logger = logging.getLogger("reliefos.http")


def register_observability_middleware(app: Flask) -> None:
    """
    Attach correlation ID extraction and latency tracking to the Flask application.
    """
    @app.before_request
    def trace_before_request():
        incoming_id = request.headers.get("X-Request-ID")
        if incoming_id and len(incoming_id) <= 64:
            g.request_id = incoming_id.strip()
        else:
            g.request_id = f"req_{uuid.uuid4().hex[:12]}"

        g.start_time = time.perf_counter()

    @app.after_request
    def trace_after_request(response: Response) -> Response:
        # Exclude static assets from noisy request logging
        if request.path.startswith(("/static", "/favicon")):
            return response

        start = getattr(g, "start_time", None)
        latency_ms = round((time.perf_counter() - start) * 1000, 2) if start else 0.0

        principal = getattr(g, "principal", None)
        actor = principal.username if principal else "anonymous"

        log_level = logging.INFO
        if response.status_code >= 500:
            log_level = logging.ERROR
        elif response.status_code >= 400:
            log_level = logging.WARNING

        logger.log(
            log_level,
            f"[{g.request_id}] {request.method} {request.path} -> {response.status_code} "
            f"({latency_ms}ms) [actor={actor}]",
        )
        return response
