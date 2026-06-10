"""Mask personal data in log output.

Defense in depth for logs: even though secrets are never logged and the audit trail (not logs) is
the governance system of record, third-party content reaches log lines, so emails and phone numbers
are masked before a record is emitted. Deliberately high-precision — it masks the canonical PII
shapes without touching IDs, ISO dates, or timestamps that logs need for debugging.
"""

from __future__ import annotations

import re

_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
# A run of digits and phone separators; redacted only when it carries enough digits to be a phone
# number (>= 10), so 8-digit ISO dates like 2026-06-22 are left intact.
_PHONE = re.compile(r"\+?\d[\d ()./-]{8,}\d")


def _mask_phone(match: re.Match[str]) -> str:
    return "<phone>" if sum(c.isdigit() for c in match.group()) >= 10 else match.group()


def redact(text: str) -> str:
    """Return ``text`` with email addresses and phone numbers masked."""
    text = _EMAIL.sub("<email>", text)
    return _PHONE.sub(_mask_phone, text)
