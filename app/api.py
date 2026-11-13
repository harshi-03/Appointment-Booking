"""Thin FastAPI adapter: forwards raw input to BookingService and maps errors to HTTP.

No business rules live here (see DESIGN.md §2, §4). Every failure, whether from the service,
request parsing, routing or an unexpected fault, uses one envelope:
    {"error": {"code": "...", "message": "...", "field": "..."}}   (field only when known)
"""
from datetime import datetime
from typing import Annotated, Optional

from fastapi import Body, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.models import (
    AlreadyCancelledError,
    Appointment,
    BookingError,
    ConflictError,
    InvalidInputError,
    NotFoundError,
)
from app.service import BookingService, _preview

_HTTP_STATUS = {
    InvalidInputError: 422,
    ConflictError: 409,
    NotFoundError: 404,
    AlreadyCancelledError: 409,
}
_FRAMEWORK_CODES = {400: "BAD_REQUEST", 404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}
_BODY_PARSE_ERROR = "There was an error parsing the body"  # FastAPI's detail for an undecodable body


# --- Schemas (also drive the Swagger docs) ---------------------------------------------

class BookingRequest(BaseModel):
    # Optional strings on purpose: the service performs all semantic validation.
    # Unknown fields are rejected, so a typo or a client sending e.g. "status" fails loudly.
    model_config = ConfigDict(extra="forbid")

    provider_id: Optional[str] = None
    start: Optional[str] = Field(None, description="ISO-8601 with an explicit offset; converted to UTC.")
    end: Optional[str] = Field(None, description="ISO-8601 with an explicit offset; must be after start.")


class AppointmentOut(BaseModel):
    id: str
    provider_id: str
    start: str = Field(description="UTC, e.g. 2099-01-01T10:00:00Z")
    end: str = Field(description="UTC, e.g. 2099-01-01T11:00:00Z")
    status: str = Field(description="ACTIVE or CANCELLED")


class ErrorDetail(BaseModel):
    code: str = Field(description="Stable, machine-readable, e.g. CONFLICT")
    message: str
    field: Optional[str] = Field(None, description="The input that was wrong, when known")
    conflicting_appointment_id: Optional[str] = Field(None, description="On CONFLICT: the appointment in the way")


class ErrorBody(BaseModel):
    error: ErrorDetail


def _documented(*statuses: int) -> dict:
    descriptions = {
        404: "Appointment not found (NOT_FOUND)",
        409: "CONFLICT or ALREADY_CANCELLED",
        422: "Invalid input (INVALID_INPUT)",
    }
    return {s: {"model": ErrorBody, "description": descriptions[s]} for s in statuses}


def _example(summary: str, start: str, end: str, provider: str = "provider-a") -> dict:
    return {"summary": summary, "value": {"provider_id": provider, "start": start, "end": end}}


# Ready-made bodies in Swagger's "Examples" dropdown, in the order of a manual test run.
_BOOKING_EXAMPLES = {
    "valid": _example("Valid booking (201)", "2099-01-01T10:00:00Z", "2099-01-01T11:00:00Z"),
    "overlap": _example("Overlaps the valid booking (409)", "2099-01-01T10:30:00Z", "2099-01-01T11:30:00Z"),
    "adjacent": _example("Starts when the valid one ends (201)", "2099-01-01T11:00:00Z", "2099-01-01T12:00:00Z"),
    "other_provider": _example(
        "Same slot, different provider (201)", "2099-01-01T10:00:00Z", "2099-01-01T11:00:00Z", "provider-b"
    ),
    "offset": _example(
        "+05:30 offset, returned as 10:00Z (201)", "2099-01-01T15:30:00+05:30", "2099-01-01T16:30:00+05:30",
        "provider-c",
    ),
    "naive": _example("No UTC offset (422)", "2099-01-01T10:00:00", "2099-01-01T11:00:00Z"),
    "zero_duration": _example("end == start (422)", "2099-01-01T10:00:00Z", "2099-01-01T10:00:00Z"),
    "past": _example("Start in the past (422)", "2020-01-01T10:00:00Z", "2020-01-01T11:00:00Z"),
}


# --- Serialisation -----------------------------------------------------------------------

def _iso_utc(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _to_json(appointment: Appointment) -> dict:
    return {
        "id": appointment.id,
        "provider_id": appointment.provider_id,
        "start": _iso_utc(appointment.start),
        "end": _iso_utc(appointment.end),
        "status": appointment.status.value,
    }


def _error(
    status: int,
    code: str,
    message: str,
    field: Optional[str] = None,
    headers: Optional[dict] = None,
    conflicting_appointment_id: Optional[str] = None,
) -> JSONResponse:
    detail = {"code": code, "message": message}
    if field is not None:
        detail["field"] = field
    if conflicting_appointment_id is not None:
        detail["conflicting_appointment_id"] = conflicting_appointment_id
    return JSONResponse(status_code=status, content={"error": detail}, headers=headers)


# --- App -----------------------------------------------------------------------------------

def create_app(service: Optional[BookingService] = None) -> FastAPI:
    app = FastAPI(
        title="Appointment Booking",
        description="Conflict-safe booking and cancellation. All times are UTC. "
        "Every error uses {\"error\": {\"code\", \"message\", \"field\"}}.",
    )
    booking = service or BookingService()

    @app.exception_handler(BookingError)
    def handle_booking_error(_: Request, exc: BookingError) -> JSONResponse:
        return _error(
            _HTTP_STATUS.get(type(exc), 400),
            exc.code,
            exc.message,
            getattr(exc, "field", None),
            conflicting_appointment_id=getattr(exc, "conflicting_id", None),
        )

    @app.exception_handler(RequestValidationError)
    def handle_request_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Wrong JSON types, unknown fields, malformed JSON, missing/non-object body.
        first = exc.errors()[0] if exc.errors() else {}
        if first.get("type") == "json_invalid":
            return _error(422, InvalidInputError.code, "request body is not valid JSON", "body")
        location = [str(part) for part in first.get("loc", ()) if part != "body"]
        # The field name can come from the client (an unknown key), so shorten it before echoing.
        field = _preview(location[-1]) if location else "body"
        message = first.get("msg", "invalid request")
        return _error(422, InvalidInputError.code, f"{field}: {message}" if location else message, field)

    @app.exception_handler(StarletteHTTPException)
    def handle_http_exception(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        # FastAPI raises a bare 400 with this exact detail when the body can't be decoded
        # (e.g. invalid UTF-8 bytes). Only that case is relabelled; any other 400 keeps its detail.
        if exc.status_code == 400 and exc.detail == _BODY_PARSE_ERROR:
            return _error(422, InvalidInputError.code, "request body is not valid JSON", "body")
        # Unknown route (404), wrong method (405): same envelope; keep headers such as Allow.
        code = _FRAMEWORK_CODES.get(exc.status_code, f"HTTP_{exc.status_code}")
        return _error(exc.status_code, code, str(exc.detail), headers=getattr(exc, "headers", None))

    @app.exception_handler(Exception)
    def handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        # Server faults: generic message only. Details stay in the server log, never in the response.
        return _error(500, "INTERNAL_ERROR", "An unexpected server error occurred.")

    @app.post("/appointments", status_code=201, response_model=AppointmentOut, responses=_documented(409, 422))
    def book_appointment(request: Annotated[BookingRequest, Body(openapi_examples=_BOOKING_EXAMPLES)]) -> dict:
        return _to_json(booking.book(request.provider_id, request.start, request.end))

    @app.post(
        "/appointments/{appointment_id}/cancel",
        response_model=AppointmentOut,
        responses=_documented(404, 409, 422),
    )
    def cancel_appointment(appointment_id: str) -> dict:
        return _to_json(booking.cancel(appointment_id))

    # Read-only verification aids: they add no rules and change nothing (see README).
    @app.get(
        "/appointments/{appointment_id}",
        response_model=AppointmentOut,
        responses=_documented(404, 422),
        summary="Get one appointment (read-only verification aid)",
    )
    def get_appointment(appointment_id: str) -> dict:
        return _to_json(booking.get(appointment_id))

    @app.get(
        "/providers/{provider_id}/appointments",
        response_model=list[AppointmentOut],
        responses=_documented(422),
        summary="List a provider's appointments, ACTIVE and CANCELLED, by start (read-only verification aid)",
    )
    def list_provider_appointments(provider_id: str) -> list[dict]:
        return [_to_json(a) for a in booking.list_for_provider(provider_id)]

    return app


app = create_app()
