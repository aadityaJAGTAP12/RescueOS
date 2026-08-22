"""
kobo_webhook_receiver.py
 
Receives KoboToolbox REST Service webhook POSTs and maps them into
ReliefOS's existing submit_report() function. Reuses the already-tested
community_reports.py backend — does not duplicate its logic.
 
Run locally with: python kobo_webhook_receiver.py
Then test with:   python test_kobo_webhook_locally.py  (separate file below)
"""
 
from flask import Flask, request, jsonify
from agent.community_reports import submit_report
 
app = Flask(__name__)
 
# ---------------------------------------------------------------------------
# Field mapping — adjust the LEFT side (Kobo field names) once you know your
# form's actual XML/question names. Get these from Data > Downloads or by
# submitting a test entry and checking the API response JSON, as discussed.
# ---------------------------------------------------------------------------
 
KOBO_FIELD_MAP = {
    # Confirmed real Kobo field names (from actual submission JSON, Aug 22 2026)
    "Your_location": "geopoint",
    "How_many_people_are_uck_at_this_location": "people_count",
    "How_many_are_adults": "adults",
    "How_many_are_children_under_12": "children",
    "How_many_are_elderly_60": "elderly",
    "What_help_is_needed_most_urgently": "needs",
    "Anything_else_we_should_know": "note",
    "Your_relationship_to_the_people_affected": "relationship",
    "Your_contact_number_optional": "contact",
    # Not in original map, but present in real data — optional context field
    "If_GPS_isn_t_working_escribe_the_location": "location_description",
}
 
 
def parse_kobo_geopoint(geopoint_str: str):
    """
    Kobo geopoint fields come as a space-separated string:
    "latitude longitude altitude accuracy"
    Returns (lat, lon) as floats, or (None, None) if missing/invalid.
    """
    if not geopoint_str:
        return None, None
    try:
        parts = geopoint_str.strip().split()
        lat = float(parts[0])
        lon = float(parts[1])
        return lat, lon
    except (IndexError, ValueError):
        return None, None
 
 
def parse_kobo_submission(payload: dict) -> dict:
    """
    Maps a raw Kobo submission JSON payload into the arguments expected by
    submit_report(). Field names below match the ACTUAL confirmed names
    from real form submissions (not the question labels — Kobo
    auto-generates shortened field names from labels, with quirks like
    dropped letters, e.g. "stuck" became "uck").
    """
    def get_field(kobo_name):
        if kobo_name in payload:
            return payload[kobo_name]
        # Fall back to matching grouped fields (group_name/field_name)
        for key in payload:
            if key.endswith(f"/{kobo_name}"):
                return payload[key]
        return None
 
    geopoint_raw = get_field("Your_location")
    lat, lon = parse_kobo_geopoint(geopoint_raw)
 
    needs_raw = get_field("What_help_is_needed_most_urgently") or ""
    needs_list = needs_raw.split() if needs_raw else []
 
    def safe_int(value, default=0):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
 
    return {
        "lat": lat,
        "lon": lon,
        "people_count": safe_int(get_field("How_many_people_are_uck_at_this_location")),
        "adults": safe_int(get_field("How_many_are_adults")),
        "children": safe_int(get_field("How_many_are_children_under_12")),
        "elderly": safe_int(get_field("How_many_are_elderly_60")),
        "needs": needs_list,
        "note": get_field("Anything_else_we_should_know") or "",
        "contact": get_field("Your_contact_number_optional") or None,
        "relationship": get_field("Your_relationship_to_the_people_affected") or "",
        "location_description": get_field("If_GPS_isn_t_working_escribe_the_location") or "",
    }
 
 
@app.route("/kobo-webhook", methods=["POST"])
def kobo_webhook():
    payload = request.get_json(force=True, silent=True)
 
    if payload is None:
        return jsonify({"status": "error", "message": "No valid JSON payload received"}), 400
 
    print(f"[KOBO WEBHOOK] Received submission. Raw keys: {list(payload.keys())}")
 
    parsed = parse_kobo_submission(payload)
 
    if parsed["lat"] is None or parsed["lon"] is None:
        print("[KOBO WEBHOOK] Missing/invalid location — rejecting")
        return jsonify({
            "status": "error",
            "message": "Submission missing valid GPS location, cannot process"
        }), 400
 
    try:
        result = submit_report(
            lat=parsed["lat"],
            lon=parsed["lon"],
            people_count=parsed["people_count"],
            adults=parsed["adults"],
            children=parsed["children"],
            elderly=parsed["elderly"],
            needs=parsed["needs"],
            note=parsed["note"],
            contact=parsed["contact"],
            # NOTE: parsed["relationship"] and parsed["location_description"]
            # are captured but NOT currently passed to submit_report(), since
            # that function's signature doesn't accept them yet. They're
            # logged below for visibility. If you want them stored, submit_report()
            # needs a small signature update — flag this to your coding agent
            # as a separate, explicit task rather than silently dropping data.
        )
        print(f"[KOBO WEBHOOK] Additional context not yet stored: "
              f"relationship='{parsed['relationship']}', "
              f"location_description='{parsed['location_description']}'")
        print(f"[KOBO WEBHOOK] Report submitted successfully: {result}")
        return jsonify({"status": "success", "report": result}), 200
 
    except Exception as e:
        print(f"[KOBO WEBHOOK] ERROR calling submit_report: {type(e).__name__}: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
 
 
if __name__ == "__main__":
    print("Starting Kobo webhook receiver on http://localhost:5000/kobo-webhook")
    app.run(host="0.0.0.0", port=5000, debug=True)
 