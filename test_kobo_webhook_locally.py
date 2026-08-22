"""
test_kobo_webhook_locally.py
 
Simulates a Kobo REST Service webhook POST, without needing ngrok or any
public exposure. Run kobo_webhook_receiver.py first (in a separate
terminal), then run this script to send it a fake-but-realistic payload.
 
This tests the parsing/mapping logic end-to-end against your real
submit_report() function and real flood-polygon validation.
"""
 
import requests
 
# This mimics the JSON shape Kobo actually sends on submission.
# Adjust field names here once you confirm your form's real question names
# (see KOBO_FIELD_MAP in kobo_webhook_receiver.py — keep both in sync).
FAKE_KOBO_PAYLOAD = {
    "Your_location": "26.9894 94.6698 0 5",  # lat lon altitude accuracy — matches
                                               # our known sivasagar_flood_zone point
    "How_many_people_are_uck_at_this_location": "5",
    "How_many_are_adults": "2",
    "How_many_are_children_under_12": "2",
    "How_many_are_elderly_60": "1",
    "What_help_is_needed_most_urgently": "medical water sanitary_supply",
    "Anything_else_we_should_know": "Test submission — simulating a real flooded location report",
    "Your_contact_number_optional": "9999999999",
    "Your_relationship_to_the_people_affected": "i_am_there_myself",
}
 
FAKE_KOBO_PAYLOAD_MISSING_LOCATION = {
    "How_many_people_are_uck_at_this_location": "3",
    "What_help_is_needed_most_urgently": "food",
}
 
FAKE_KOBO_PAYLOAD_SAFE_LOCATION = {
    "Your_location": "26.9701 94.6393 0 5",  # sivasagar town center — near_flood_zone,
                                               # correctly accepted per the fixed validation
    "How_many_people_are_uck_at_this_location": "2",
    "How_many_are_adults": "2",
    "How_many_are_children_under_12": "0",
    "How_many_are_elderly_60": "0",
    "What_help_is_needed_most_urgently": "food",
    "Anything_else_we_should_know": "Test submission for a near-but-not-contained location",
}
 
WEBHOOK_URL = "http://localhost:5000/kobo-webhook"
 
 
def run_test(name, payload):
    print(f"\n{'='*60}")
    print(f"TEST: {name}")
    print(f"{'='*60}")
    try:
        response = requests.post(WEBHOOK_URL, json=payload, timeout=10)
        print(f"Status code: {response.status_code}")
        print(f"Response body: {response.json()}")
    except requests.exceptions.ConnectionError:
        print("ERROR: Could not connect to the webhook receiver.")
        print("Make sure kobo_webhook_receiver.py is running in another terminal first.")
 
 
if __name__ == "__main__":
    run_test(
        "Valid submission at a known flooded location (should succeed)",
        FAKE_KOBO_PAYLOAD,
    )
    run_test(
        "Missing location field (should fail gracefully with 400)",
        FAKE_KOBO_PAYLOAD_MISSING_LOCATION,
    )
    run_test(
        "Sivasagar town center — near_flood_zone (0.39km), correctly ACCEPTED per fixed validation",
        FAKE_KOBO_PAYLOAD_SAFE_LOCATION,
    )