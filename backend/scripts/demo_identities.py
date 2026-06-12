"""The two seed identities the demo drivers run the identity-bound flow with.

The court requires an authenticated requester on submit and an authorized approver on every
decision, so the credential-free drivers (demo, card export) carry explicit principals: a requester
who submits and confirms, and an approver who holds every quorum role. In a deployment these come
from Entra ID and ``APPROVER_DIRECTORY``; here they are fixed so runs stay reproducible.
"""

from __future__ import annotations

from app.domain.principal import Principal

REQUESTER = Principal(
    oid="demo-requester", upn="requester@change-court.local", display_name="Robin Requester"
)
APPROVER = Principal(
    oid="demo-approver", upn="approver@change-court.local", display_name="Alex Approver"
)

_ROLES = ("eng_lead", "comms", "account_owner", "security_lead", "manager")
DIRECTORY = ",".join(f"{role}:{APPROVER.upn}" for role in _ROLES)
