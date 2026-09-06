"""TEMPORARY diagnostic wrapper around agent.api (NOT production code).

Adds:
- werkzeug before/after_request timing logs for every /api request
- /api/_timed/<name> endpoints that call each internal hop in isolation
  (handler+judge, judge-only, static response) so we can see exactly where
  wall-clock time goes when requests run through Flask.

Run: DATABASE_URL=... python -m tools.timed_api_diag  (port 5002)
"""
import time as _time
import logging

from flask import jsonify

import agent.api as api

_app = api.app

logging.basicConfig(level=logging.INFO)
_diaglog = logging.getLogger("timing-diag")


@_app.before_request
def _diag_before():
    from flask import request, g
    g._t0 = _time.perf_counter()
    _diaglog.info("REQ-START %s %s", request.method, request.path)


@_app.after_request
def _diag_after(response):
    from flask import request, g
    t0 = getattr(g, "_t0", None)
    if t0 is not None:
        _diaglog.info(
            "REQ-END %s %s -> %s in %.1f ms",
            request.method, request.path, response.status_code,
            (_time.perf_counter() - t0) * 1000,
        )
    return response


def _make_need():
    return {
        "id": "need_diag",
        "need_type": "boat",
        "title": "diag boat",
        "urgency": "critical",
        "requested_resources": [{"resource_type": "boat", "quantity": 1, "unit": "units"}],
    }


@_app.route("/api/_timed/handler", methods=["POST"])
def _timed_handler():
    """Full analyze-need pipeline incl. LLM judge with its 2s timeout."""
    t0 = _time.perf_counter()
    from agent.agents.ngo_main_agent import analyze_need_for_org
    from agent.org_workspace import list_resources, list_teams, list_missions
    from agent.data.repository import get_repository

    repo = get_repository()
    resources = list_resources("org_demo")
    teams = list_teams("org_demo")
    missions = list_missions("org_demo")
    t_ctx = _time.perf_counter()

    result = analyze_need_for_org(
        org_id="org_demo",
        need=_make_need(),
        private_resources=resources,
        private_teams=teams,
        private_missions=missions,
        network_needs=[n.to_dict() for n in repo.list_needs(status="OPEN")],
        network_operations=[o.to_dict() for o in repo.list_operations()],
        network_overrides=[],
    )
    t1 = _time.perf_counter()
    return jsonify({
        "hop": "handler+judge",
        "ctx_ms": round((t_ctx - t0) * 1000, 1),
        "total_ms": round((t1 - t0) * 1000, 1),
        "recommendation": result.get("recommendation"),
        "interpretation": result.get("interpretation"),
    })


@_app.route("/api/_timed/judge", methods=["POST"])
def _timed_judge():
    """Only the LLM judgment step (2s timeout, thread-abandoned on timeout)."""
    t0 = _time.perf_counter()
    from agent.reasoning.need_offer_judgment import judge_need_offer
    out = judge_need_offer({"available_quantity": 10, "requested_quantity": 1}, "diag", "diag")
    t1 = _time.perf_counter()
    return jsonify({
        "hop": "judge-only",
        "total_ms": round((t1 - t0) * 1000, 1),
        "interpretation": out.get("interpretation"),
    })


@_app.route("/api/_timed/agent", methods=["POST"])
def _timed_agent():
    """Raw Strands agent invocation, no timeout wrapper at all."""
    t0 = _time.perf_counter()
    from agent.agents.coordinator_agent import _coordinator_agent
    try:
        resp = _coordinator_agent("Return JSON {\"note\":\"ok\",\"confidence\":\"unclear\"} and nothing else.")
        text = str(resp)
        err = None
    except Exception as e:  # noqa: BLE001
        text = None
        err = repr(e)
    t1 = _time.perf_counter()
    return jsonify({"hop": "raw-agent", "total_ms": round((t1 - t0) * 1000, 1), "error": err, "text": (text or "")[:200]})


@_app.route("/api/_timed/static", methods=["GET"])
def _timed_static():
    return jsonify({"hop": "static", "ok": True})


if __name__ == "__main__":
    print("Starting TIMED DIAG API on http://localhost:5002")
    _app.run(host="0.0.0.0", port=5002, threaded=True)
