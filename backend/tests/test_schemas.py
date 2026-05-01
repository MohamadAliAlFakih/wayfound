"""Pydantic schema tests (TST-02).

These tests don't need a database, network, or LLM — they just verify our
request/response shapes accept good input and reject bad input. Fast and
deterministic.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.auth import LoginRequest, RegisterRequest
from app.schemas.trips import PlanTripRequest


def test_register_accepts_valid_input():
    """Happy path — username, email, and password all valid."""
    payload = RegisterRequest(
        username="alice_42",
        email="alice@example.com",
        password="secret123",
    )
    assert payload.username == "alice_42"
    assert payload.email == "alice@example.com"


def test_register_rejects_username_with_space():
    """Spaces are not allowed in usernames (D-04 — alphanumeric + _ + -)."""
    with pytest.raises(ValidationError):
        RegisterRequest(
            username="alice smith",
            email="alice@example.com",
            password="secret123",
        )


def test_register_rejects_short_password():
    """Passwords must be at least 8 chars (D-05)."""
    with pytest.raises(ValidationError):
        RegisterRequest(
            username="alice",
            email="alice@example.com",
            password="short",
        )


def test_register_rejects_invalid_email():
    """Pydantic EmailStr catches obviously bad email shapes."""
    with pytest.raises(ValidationError):
        RegisterRequest(
            username="alice",
            email="not-an-email",
            password="secret123",
        )


def test_login_accepts_valid_input():
    payload = LoginRequest(email="alice@example.com", password="secret123")
    assert payload.email == "alice@example.com"


def test_plan_trip_rejects_short_query():
    """Query has min_length=10 — short queries should fail validation."""
    with pytest.raises(ValidationError):
        PlanTripRequest(query="hi")


def test_plan_trip_accepts_realistic_query():
    payload = PlanTripRequest(
        query="Two weeks in Japan in March, mid budget, love food and history."
    )
    assert "Japan" in payload.query