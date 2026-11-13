"""HTTP mapping tests: each asserts the status code AND the error envelope code.

Every rejection also asserts the stored bookings are unchanged (project rule).
"""
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api import create_app
from app.models import AppointmentStatus
from app.service import BookingService
from helpers import at, make_service, snapshot

JSON = {"Content-Type": "application/json"}


@pytest.fixture
def service():
    return make_service()


@pytest.fixture
def client(service):
    # Fresh app + service per test, with the fixed clock: no shared state, no real time.
    # raise_server_exceptions=False: a server crash shows up as a 500 response, like a real client sees.
    return TestClient(create_app(service), raise_server_exceptions=False)


def book(client, provider_id="provider-a", start=at(10), end=at(11)):
    return client.post("/appointments", json={"provider_id": provider_id, "start": start, "end": end})


def assert_rejected(service, send, status, code):
    """Send a request, assert the error envelope, and assert the store did not change."""
    before = snapshot(service)
    response = send()
    assert response.status_code == status
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == code
    assert body["error"]["message"]
    assert snapshot(service) == before
    return body["error"]


def test_api_book_201(client):
    response = client.post(
        "/appointments",
        json={"provider_id": "provider-a", "start": "2030-01-01T15:30:00+05:30", "end": at(11)},
    )
    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "provider_id", "start", "end", "status"}
    assert body["provider_id"] == "provider-a"
    assert body["start"] == "2030-01-01T10:00:00Z"  # converted to UTC, Z suffix
    assert body["end"] == "2030-01-01T11:00:00Z"
    assert body["status"] == "ACTIVE"


def test_api_microseconds_kept_when_non_zero(client):
    response = book(client, start="2030-01-01T08:00:00.000001Z", end=at(9))
    assert response.status_code == 201
    assert response.json()["start"] == "2030-01-01T08:00:00.000001Z"


def test_api_conflict_409(client, service):
    assert book(client).status_code == 201
    assert_rejected(service, lambda: book(client, start=at(10, 30), end=at(11, 30)), 409, "CONFLICT")


@pytest.mark.parametrize(
    "payload",
    [
        {"provider_id": "provider-a", "start": at(12), "end": at(12)},            # zero duration
        {"provider_id": "provider-a", "start": "not-a-date", "end": at(12)},      # unparseable
        {"provider_id": "provider-a", "start": "2030-01-01T12:00:00", "end": at(13)},  # naive
        {"provider_id": "   ", "start": at(12), "end": at(13)},                   # blank provider
        {"provider_id": "provider-a", "start": at(7), "end": at(9)},              # in the past
        {},                                                                       # missing fields
    ],
    ids=["zero-duration", "unparseable", "naive", "blank-provider", "past", "empty-object"],
)
def test_api_invalid_input_422(client, service, payload):
    book(client)  # existing booking, so "unchanged" is meaningful
    assert_rejected(service, lambda: client.post("/appointments", json=payload), 422, "INVALID_INPUT")


def test_api_past_start_message(client, service):
    error = assert_rejected(service, lambda: book(client, start=at(7), end=at(9)), 422, "INVALID_INPUT")
    assert error["message"] == "start must be in the future (UTC)"


@pytest.mark.parametrize("missing", ["provider_id", "start", "end"])
def test_api_missing_single_field_422(client, service, missing):
    book(client)
    payload = {"provider_id": "provider-a", "start": at(12), "end": at(13)}
    del payload[missing]
    error = assert_rejected(service, lambda: client.post("/appointments", json=payload), 422, "INVALID_INPUT")
    assert error["message"] == f"{missing} is required"


def test_api_wrong_type_422(client, service):
    # Pydantic rejects int for str before the service runs; must still use our envelope.
    book(client)
    assert_rejected(service, lambda: book(client, provider_id=123), 422, "INVALID_INPUT")


@pytest.mark.parametrize(
    "content", ["{not json", "[1, 2, 3]", ""], ids=["malformed", "array-body", "no-body"]
)
def test_api_malformed_json_422(client, service, content):
    book(client)
    assert_rejected(
        service, lambda: client.post("/appointments", content=content, headers=JSON), 422, "INVALID_INPUT"
    )


def test_api_malformed_json_message(client, service):
    book(client)
    error = assert_rejected(
        service,
        lambda: client.post("/appointments", content='{"provider_id": "a",', headers=JSON),
        422,
        "INVALID_INPUT",
    )
    assert error["message"] == "request body is not valid JSON"


def test_api_invalid_utf8_body_422(client, service):
    # A raw 0xFF byte is not UTF-8: must use our envelope, not FastAPI's 400 {"detail": ...}.
    book(client)
    error = assert_rejected(
        service,
        lambda: client.post("/appointments", content=b'{"provider_id": "\xff"}', headers=JSON),
        422,
        "INVALID_INPUT",
    )
    assert error["message"] == "request body is not valid JSON"


def test_api_unencodable_provider_id_rejected_nothing_saved(client, service):
    # JSON escape \ud800 is a lone surrogate: valid JSON, but the string can't be encoded as UTF-8.
    body = rb'{"provider_id": "\ud800", "start": "2030-01-01T12:00:00Z", "end": "2030-01-01T13:00:00Z"}'
    before = len(service._appointments)
    response = client.post("/appointments", content=body, headers=JSON)
    saved = len(service._appointments) - before
    assert (response.status_code, saved) == (422, 0)
    assert response.json()["error"]["code"] == "INVALID_INPUT"


def test_api_cancel_200(client):
    created = book(client).json()
    response = client.post(f"/appointments/{created['id']}/cancel")
    assert response.status_code == 200
    assert response.json() == {**created, "status": "CANCELLED"}  # same id, UTC 'Z' timestamps
    assert book(client).status_code == 201  # slot freed


def test_api_cancel_missing_404(client, service):
    book(client)
    assert_rejected(service, lambda: client.post("/appointments/does-not-exist/cancel"), 404, "NOT_FOUND")


def test_api_cancel_twice_409(client, service):
    appointment_id = book(client).json()["id"]
    assert client.post(f"/appointments/{appointment_id}/cancel").status_code == 200
    assert_rejected(
        service, lambda: client.post(f"/appointments/{appointment_id}/cancel"), 409, "ALREADY_CANCELLED"
    )


def test_api_cancel_id_with_spaces_404_original_stays_active(client, service):
    appointment_id = book(client).json()["id"]
    assert_rejected(
        service, lambda: client.post(f"/appointments/%20{appointment_id}%20/cancel"), 404, "NOT_FOUND"
    )
    assert service._appointments[appointment_id].status is AppointmentStatus.ACTIVE


@pytest.mark.parametrize(
    "payload, field",
    [
        ({"provider_id": "provider-a", "start": at(12), "end": at(12)}, "end"),
        ({"provider_id": "provider-a", "start": "nope", "end": at(12)}, "start"),
        ({"provider_id": 123, "start": at(12), "end": at(13)}, "provider_id"),
    ],
    ids=["zero-duration", "unparseable", "wrong-type"],
)
def test_api_error_names_the_field(client, service, payload, field):
    error = assert_rejected(service, lambda: client.post("/appointments", json=payload), 422, "INVALID_INPUT")
    assert error["field"] == field


def test_api_malformed_json_field_is_body(client, service):
    error = assert_rejected(
        service, lambda: client.post("/appointments", content="{oops", headers=JSON), 422, "INVALID_INPUT"
    )
    assert error["field"] == "body"


def test_api_unknown_field_rejected(client, service):
    # A client trying to set "status" (or mistyping a field) must fail loudly, not be ignored.
    payload = {"provider_id": "provider-a", "start": at(12), "end": at(13), "status": "CANCELLED"}
    error = assert_rejected(service, lambda: client.post("/appointments", json=payload), 422, "INVALID_INPUT")
    assert error["field"] == "status"


def test_api_long_unknown_field_name_is_truncated(client, service):
    # The field name comes from the client, so it must not be echoed back in full.
    payload = {"provider_id": "provider-a", "start": at(12), "end": at(13), "x" * 5000: 1}
    response = client.post("/appointments", json=payload)
    assert response.status_code == 422
    assert len(response.text) < 300


def test_api_other_400_keeps_its_detail(service):
    # Only FastAPI's body-parse 400 is relabelled "not valid JSON"; any other 400 keeps its detail.
    app = create_app(service)

    @app.get("/boom")
    def boom():
        raise HTTPException(status_code=400, detail="something else went wrong")

    response = TestClient(app, raise_server_exceptions=False).get("/boom")
    assert response.status_code == 400
    assert response.json() == {"error": {"code": "BAD_REQUEST", "message": "something else went wrong"}}


def test_api_unknown_route_uses_envelope(client):
    response = client.get("/no-such-route")
    assert response.status_code == 404
    assert response.json() == {"error": {"code": "NOT_FOUND", "message": "Not Found"}}


def test_api_wrong_method_uses_envelope_and_keeps_allow_header(client):
    response = client.get("/appointments")  # only POST exists
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "METHOD_NOT_ALLOWED"
    assert response.headers["allow"] == "POST"


def test_api_unexpected_error_is_generic_500():
    class FailingService(BookingService):
        def book(self, *args):
            raise RuntimeError("internal secret: db password is hunter2")

    client = TestClient(create_app(FailingService()), raise_server_exceptions=False)
    response = client.post("/appointments", json={"provider_id": "p", "start": at(10), "end": at(11)})
    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "INTERNAL_ERROR", "message": "An unexpected server error occurred."}
    }
    assert "secret" not in response.text


def test_api_conflict_includes_conflicting_appointment_id(client, service):
    existing = book(client).json()
    error = assert_rejected(service, lambda: book(client, start=at(10, 30), end=at(11, 30)), 409, "CONFLICT")
    assert error["conflicting_appointment_id"] == existing["id"]


# --- Read-only verification aids ------------------------------------------------------------

def test_api_get_appointment_200(client):
    created = book(client).json()
    assert client.get(f"/appointments/{created['id']}").json() == created
    client.post(f"/appointments/{created['id']}/cancel")
    assert client.get(f"/appointments/{created['id']}").json()["status"] == "CANCELLED"


def test_api_get_appointment_404_and_blank_422(client, service):
    appointment_id = book(client).json()["id"]
    assert_rejected(service, lambda: client.get("/appointments/does-not-exist"), 404, "NOT_FOUND")
    assert_rejected(service, lambda: client.get(f"/appointments/%20{appointment_id}%20"), 404, "NOT_FOUND")
    assert_rejected(service, lambda: client.get("/appointments/%20"), 422, "INVALID_INPUT")


def test_api_list_provider_appointments(client):
    late = book(client, start=at(14), end=at(15)).json()
    early = book(client, start=at(9), end=at(10)).json()
    book(client, provider_id="provider-b").json()
    client.post(f"/appointments/{late['id']}/cancel")

    response = client.get("/providers/provider-a/appointments")

    assert response.status_code == 200
    assert [a["id"] for a in response.json()] == [early["id"], late["id"]]
    assert [a["status"] for a in response.json()] == ["ACTIVE", "CANCELLED"]


def test_api_list_unknown_provider_empty_and_blank_422(client, service):
    assert client.get("/providers/nobody/appointments").json() == []
    assert_rejected(service, lambda: client.get("/providers/%20/appointments"), 422, "INVALID_INPUT")


def test_api_cancel_blank_id_422(client, service):
    book(client)
    assert_rejected(service, lambda: client.post("/appointments/%20/cancel"), 422, "INVALID_INPUT")
