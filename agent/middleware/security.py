"""
ReliefOS Security Middleware & Production Error Sanitization

Injects robust HTTP security headers and prevents internal stack trace leaks in production.
"""

from __future__ import annotations

import logging
import os
import uuid
from flask import Flask, Response, g, jsonify, request

logger = logging.getLogger("reliefos.security")


def is_production() -> bool:
    return os.environ.get("ENVIRONMENT", "development").lower() == "production"


def apply_security_headers(response: Response) -> Response:
    """
    Append standard defensive HTTP headers to every outgoing response.
    """
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    # CSP for ReliefOS dashboard
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob: https:; "
        "connect-src 'self' https: http: ws: wss:; "
        "font-src 'self' data: https:;"
    )

    # Attach request ID to response header if present
    request_id = getattr(g, "request_id", None)
    if request_id:
        response.headers["X-Request-ID"] = request_id

    return response


def register_security_middleware(app: Flask) -> None:
    """
    Register response header processors and production error handlers.
    """
    app.after_request(apply_security_headers)

    @app.errorhandler(400)
    def handle_bad_request(e):
        return jsonify({
            "error": "Bad Request",
            "message": str(e.description if hasattr(e, "description") else e),
            "request_id": getattr(g, "request_id", None),
        }), 400

    @app.errorhandler(404)
    def handle_not_found(e):
        return jsonify({
            "error": "Not Found",
            "message": str(e.description if hasattr(e, "description") else e),
            "request_id": getattr(g, "request_id", None),
        }), 404

    @app.errorhandler(Exception)
    def handle_unhandled_exception(e):
        request_id = getattr(g, "request_id", str(uuid.uuid4()))
        logger.exception(f"[RequestID: {request_id}] Unhandled error during {request.method} {request.path}: {e}")

        # Exception detail is sanitized by default in EVERY environment:
        # raw str(e) can carry connection strings, SQL, or filesystem paths.
        # Opt in explicitly (and consciously) via DEBUG_ERRORS=true for
        # local debugging only.
        debug_errors = os.environ.get("DEBUG_ERRORS", "").lower() in ("true", "1", "yes")
        if debug_errors and not is_production():
            return jsonify({
                "error": "Internal Server Error",
                "message": str(e),
                "type": type(e).__name__,
                "request_id": request_id,
            }), 500
        return jsonify({
            "error": "Internal Server Error",
            "message": "An unexpected error occurred. Please contact support with the request ID.",
            "request_id": request_id,
        }), 500
