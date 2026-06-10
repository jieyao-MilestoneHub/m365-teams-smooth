"""PII redaction masks emails and phone numbers in logs, leaving IDs and dates intact."""

from __future__ import annotations

import json
import logging

from app.observability.logging import JsonFormatter
from app.observability.redact import redact


def test_email_is_masked() -> None:
    assert redact("contact vendor@example.com about access") == "contact <email> about access"


def test_phone_is_masked() -> None:
    assert "<phone>" in redact("call +1 (415) 555-0199 today")
    assert "<phone>" in redact("number 4155550199")


def test_iso_dates_and_ids_are_preserved() -> None:
    # 8-digit ISO dates and 32-char hex audit ids must survive — logs need them for debugging.
    text = "milestone due 2026-06-22, audit a1b2c3d4e5f60718293a4b5c6d7e8f90"
    assert redact(text) == text


def test_non_pii_text_is_untouched() -> None:
    assert redact("slip the launch from 2026-06-10 to 2026-06-17") == (
        "slip the launch from 2026-06-10 to 2026-06-17"
    )


def test_formatter_redacts_message_and_extras() -> None:
    formatter = JsonFormatter(redact_pii=True)
    record = logging.LogRecord(
        name="t", level=logging.INFO, pathname="", lineno=0,
        msg="request from %s", args=("vendor@example.com",), exc_info=None,
    )
    record.actor = "owner@example.com"  # an extra field
    payload = json.loads(formatter.format(record))
    assert payload["message"] == "request from <email>"
    assert payload["actor"] == "<email>"


def test_formatter_can_disable_redaction() -> None:
    formatter = JsonFormatter(redact_pii=False)
    record = logging.LogRecord(
        name="t", level=logging.INFO, pathname="", lineno=0,
        msg="reach me at a@b.com", args=(), exc_info=None,
    )
    assert "a@b.com" in json.loads(formatter.format(record))["message"]
