# ADR-0017: Severity classification over additive risk scoring

- **Status:** Accepted (amends [ADR-0016](0016-llm-deterministic-allocation-contract.md), which
  described governance as "risk scoring, banding")
- **Date:** 2026-06-14

## Context

The policy node assessed risk by **summing per-factor integer weights** and **banding** the total
into a level: each fired evidence tag added a weight (5–50), and thresholds (`low<30`,
`medium≥30`, `high≥60`) mapped the sum to `low`/`medium`/`high`.

The mechanism was deterministic and auditable, but the *numbers* had no basis. The weights and
the band thresholds were hand-chosen design literals — not derived from any risk-quantification
framework (NIST 800-30, ISO 31000, FAIR, CVSS) and not calibrated against any dataset. The only
repository "eval" near policy, `backend/scripts/eval_retrieval.py`, scores knowledge **retrieval**
ranking, not risk. So the resulting score implied a quantitative precision the system did not have:
a "70" reads as a measurement, but no one could defend "70 and not 55" to an auditor, and a level
that flips because two weights happened to cross a threshold is an artifact of the chosen numbers,
not a fact about the change.

The clearest symptom: across the shipped rule packs and golden trials, the **only** non-unsafe
`high` outcome — the clean `launch_slip` reschedule — reached `high` purely by *summing*
(40+20+10+10). Every other `high` was an unsafe factor in its own right. The additive machinery
existed to manufacture one band transition that nothing substantive justified.

## Decision

Replace additive scoring with a **qualitative severity classification**.

- Each risk factor **declares a severity** (`RiskLevel` — `low`/`medium`/`high`) instead of an
  integer weight. `RiskFactorRule.weight` and the `RiskBands` model are removed.
- A trial's level is the **most severe fired factor** — `max` by severity rank — with no summing
  and no thresholds. `RiskLevel.rank` provides the ordering (the string values are not ordinally
  comparable).
- The downstream contract is unchanged: `requires_approval = (level is not low)`; a factor that
  `marks_unsafe` still flags the change and pins the deterministic refusal. Unsafe factors are
  declared `high` — being unsafe is the gravest qualitative outcome.
- Domain models drop the number: `RiskFactor.weight` → `RiskFactor.severity`; `RiskResult.score`
  is removed (it keeps `level`, `factors`, `requires_approval`, `matched_rule_ids`).

Each factor is now individually accountable for a claim a human can defend — "a contractual breach
is *high* severity" — rather than an unexplainable "+50". Determinism and the additive-only
monotonicity of the agentic bridge (ADR-0016) are preserved: a flagged tag can still only raise the
level or convene an approver, never lower or remove one.

## Consequences

- **More defensible, not less rigorous.** The governance output is the same shape (a deterministic
  level + quorum from tag data) but every input is a qualitative assessment that stands on its own,
  with no false-precision number to justify.
- **Compounding is gone.** Several `medium` factors no longer sum to `high`. This is accepted: the
  old compounding was a product of arbitrary weights, and `medium` already convenes the quorum, so
  the approval gate still fires — only the badge differs. Where a combination genuinely *is* grave,
  a factor should declare `high` directly.
- **One classification change.** The clean `launch_slip` reschedule is now `medium` (the milestone
  move), not `high` — it is feasible, approval is still required, and the same eng-lead + comms
  quorum convenes. The golden trials and the headline scenario assert this; `high` is now reserved
  for unsafe outcomes (a date conflict, a latent breach).
- **External surfaces changed.** The evidence-webhook packet no longer carries `risk.score`, and
  each factor carries `severity` instead of `weight`; the read-only run page renders per-factor
  severity and a level-keyed fill instead of a summed score and a percentage meter. Pre-tenant, so
  no compatibility shim is needed.
- **Extension is simpler.** A rule-pack entry declares `severity:` per factor and drops the
  `risk_bands` block entirely (see [extending.md](../extending.md) and
  [approval-policy.md](../approval-policy.md)).
