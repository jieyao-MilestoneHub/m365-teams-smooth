# Extending the court — new scenarios and integrations, without touching the pipeline

The pipeline is generic: any request flows through the same
`intake → impact → options → policy → [verdict] → execute → verify → audit` graph, the LLM owns
perception and plan content on every path, and deterministic rules own governance
([ADR-0016](adr/0016-llm-deterministic-allocation-contract.md)). Adapting a clone to your own
change domains therefore means **adding data and adapters at the edges** — never editing the
graph, the services, REST, or MCP.

## A new scenario is a rule-pack entry

Point `POLICY_PACKS_PATH` at a YAML file; file packs **append** to the built-in defaults (which
keep first-match precedence) unless the file sets `include_defaults: false`. The checked-in,
load-tested example — [`assets/policy-packs/example.yaml`](../assets/policy-packs/example.yaml):

```yaml
include_defaults: true
packs:
  - id: dns_change
    match:                                   # when this pack governs a change
      any_action_capability: ["dns.update_record"]
      any_tag: ["dns.production_zone"]
    subjects: ["dns-change"]                 # the parser subjects this pack specializes
    grounding_query: "DNS change production zone rollback window"
    risk_factors:                            # tag-keyed severities (the level is the highest fired)
      - id: production_zone
        when_tag: dns.production_zone
        severity: high
        marks_unsafe: true                   # fired -> deterministic refusal authority
      - id: long_ttl
        when_tag: dns.long_ttl
        severity: low
    quorum:                                  # evidence-named approvers
      approvers:
        - { role: eng_lead, when_tag: dns.production_zone }
      policy: all                            # or "any"
    verdict_options:
      default: [approve, request_revision, reject]
      when_unsafe: [accept_alternative, request_revision, reject]
```

One pack entry extends the whole pipeline, because every policy-adjacent derivation reads the
loaded packs (`backend/app/agent/policy_rules/vocabulary.py`):

- the **tag vocabulary** the agentic gatherer may flag from (`dns.production_zone`,
  `dns.long_ttl` become legal severity-carrying signals);
- the **unsafe-tag set** that pins the generic planner's refusal stance;
- the **grounding mapping** the impact node uses for knowledge retrieval on your subject.

Notes that matter in production:

- **Quorum roles must resolve to people**: map every role you use in `APPROVER_DIRECTORY`,
  or a quorum-bearing trial can be sent but never decided.
- **Unknown stays governed**: a change that matches *no* pack lands on the ungoverned floor
  (MEDIUM, manager approval) — your file narrows that floor, it never widens it.
- **Validation is fail-fast**: a broken file stops composition with an error naming the file,
  the entry index, and the pack id.

## A new integration is one adapter + one registration

Implement `IntegrationAdapter` (read + write capabilities — see
`backend/app/adapters/integrations/base.py` and any `real_*.py`/`mock_*.py` pair) and register it
in `backend/app/container.py`. That is the entire integration surface:

- its **read capabilities** appear in the Prosecutor's catalog (the LLM can select them as
  evidence reads, validated per read);
- its **write capabilities** appear in the Defender's catalog (the LLM can plan them, validated
  per step) and in the parser's action catalog;
- the **MCP capabilities resource** and the intake hallucination guard pick it up automatically.

Real-vs-mock is chosen per system from `INTEGRATION_MODE`; ship a mock alongside the real adapter
so the verification mode covers your system too.

## Optional: a specialized gatherer/planner

The generic agentic path covers any subject. Registering a deterministic gatherer/planner for
your subject (the `Gatherer`/`Planner` protocols in `backend/app/agent/nodes/impact.py` /
`options.py`, wired in `container.py`) buys two things: a scripted evidence/plan baseline for the
offline verification mode (offline, the generic path contributes no tags by design), and a richer
deterministic fallback when the LLM is unavailable. It is an optimization, never a requirement.

## What you never touch

The graph (`backend/app/agent/graph.py`), the services, REST, and MCP are closed to extension by
design — composition happens only in `container.py` (and `asgi.py` for the deployment surfaces).
If adapting the court to your domain seems to require editing any of those, the extension point
you are looking for is one of the three above.
