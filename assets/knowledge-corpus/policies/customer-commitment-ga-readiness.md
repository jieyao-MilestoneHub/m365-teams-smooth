# Customer Commitment & GA Readiness Policy

## Purpose and scope
This policy governs external commitments made to customers about feature availability — in particular
general availability (GA) dates and enterprise capabilities such as Single Sign-On (SSO/SAML). It
exists to prevent the company from promising a date or capability that engineering and security cannot
safely deliver. It applies to Sales, Customer Success, and Product when communicating timelines to a
customer.

## No commitment before security review sign-off
A customer-facing commitment to make a capability generally available — especially an authentication
or identity feature such as SSO/SAML — must not be given until the security review for that capability
has passed and been signed off. A pending or scheduled security review is a hard blocker: until it
clears, the only permitted external answer is a conditional one (for example "targeted, pending
security sign-off"), never a firm GA date.

## GA readiness gate
Before any GA promise, the capability must satisfy the GA readiness checklist: security review passed,
SSO/SAML flows validated against the common identity providers, certificate lifecycle handling in
place, error and incident runbooks ready, and support/onboarding documentation complete. If material
checklist items are unmet, the launch or promise is paused and the gaps are closed first.

## SSO / SAML specific requirements
SSO readiness specifically requires: validated SAML assertion handling (signature verification on
canonicalized XML to prevent signature-wrapping), tested certificate rotation, and scenario testing
for expired certificates, misconfigured attributes, and partial domain verification. A customer SSO
promise is only safe once these are demonstrably complete.

## Safe alternative when a promise is unsafe
When a requested commitment cannot be made safely, the governed outcome is a safe alternative rather
than a blunt refusal: offer a private preview or pilot instead of GA, or a conditional date framed as
"target, subject to security sign-off". The customer relationship is preserved without the company
taking on an unsafe obligation.

## Approval and quorum
A firm GA or SSO commitment to a customer requires sign-off from Product and Security; commitments
tied to a renewal or contract value additionally require Sales leadership review. The evidence behind
the decision (security-review status, blocking issues, renewal value) is recorded with the verdict.

## Audit and traceability
Every external commitment decision is recorded in an append-only trail: the request, the impact
evidence (security-review date, open blocking issues), the approvers, and the final verdict. The trail
is never edited after the fact.
