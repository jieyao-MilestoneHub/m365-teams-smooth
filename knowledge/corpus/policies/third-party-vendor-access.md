# Third-Party Vendor & Contractor Access Policy

## Purpose and scope
This policy governs how external vendors, agencies, and contractors are granted access to company
systems, data, and collaboration spaces (SharePoint, Teams, source repositories, and SaaS admin
consoles). It applies to every engagement in which a non-employee needs temporary access to complete
scoped work. It aligns with NIST Cybersecurity Framework control PR.AA-05 (access permissions and
authorizations are defined, managed, enforced, reviewed, and incorporate least privilege).

## Principle of least privilege
Vendors receive the minimum access required for the specific task, and nothing more. Broad,
role-wide, or tenant-wide grants to external identities are prohibited. Where a vendor needs to review
material, grant read-only access scoped to a single folder, site, or repository rather than a parent
container. Write, delete, share, or administrative permissions are granted only with explicit
justification and named approver sign-off.

## Time-bound, just-in-time access
All external access is time-bound. Access is provisioned just-in-time for the engagement and carries
an explicit expiry date; standing or open-ended vendor access is not permitted. When a request states
an ambiguous duration (for example "until the campaign is done"), it must be converted to a concrete
expiry date, and access must auto-revoke on that date. The default maximum for a single grant is 30
days, renewable only by re-approval.

## Auto-revocation and offboarding
Every vendor grant must have an automatic revocation schedule tied to its expiry. Access is also
revoked immediately when the engagement ends, the statement of work closes, or a policy violation is
detected. A scheduled auto-revoke task is mandatory for any access to customer data or production
systems.

## Data classification and customer data
Access to folders or sites containing customer data or personally identifiable information requires a
documented security review and is restricted to read-only unless a data processing agreement is in
place. Customer-data locations are treated as sensitive and are never shared with an external party
by default.

## Approval and quorum
Granting external access to sensitive scopes requires approval from the resource owner and the
security or IT administrator. Requests touching customer data additionally require compliance review.
Separation of duties applies: the requester cannot be the sole approver.

## Periodic access review
All active external grants are reviewed on a recurring basis (at minimum quarterly, consistent with
ISO/IEC 27001 access-review guidance) to confirm the access is still required and still least-privilege.
Grants that are no longer justified are revoked at review.

## Safe alternative pattern
When a broad or ambiguous access request is unsafe, the governed outcome is a safer equivalent:
read-only instead of write, a single scoped folder instead of a site, and a fixed expiry with a
scheduled auto-revoke instead of indefinite access.
