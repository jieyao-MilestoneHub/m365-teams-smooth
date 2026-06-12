"""Load rule packs from a data file — the policy layer's extension point.

A deployment points ``POLICY_PACKS_PATH`` at a YAML file (see ``assets/policy-packs/example.yaml``
and ``docs/extending.md``); each entry validates as a :class:`RulePack`, so the tag vocabulary,
the unsafe-tag set, and the grounding mapping all derive from it automatically. File packs
**append** to the built-in defaults unless the file sets ``include_defaults: false`` — and because
the policy node selects the first governing pack, the built-ins keep precedence in append mode;
replace mode is the override path.

Failures raise :class:`PolicyPackError` at composition time, naming the file and the offending
entry — a deployment with a broken policy file must not start.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import yaml
from pydantic import ValidationError

from app.agent.policy_rules.models import RulePack
from app.agent.policy_rules.packs import default_packs


class PolicyPackError(ValueError):
    """A rule-pack file failed to load or validate (raised at composition time)."""


def load_packs(
    path: str | Path,
    *,
    defaults: Callable[[], list[RulePack]] = default_packs,
) -> list[RulePack]:
    """The packs from ``path`` (appended to ``defaults()`` unless the file opts out)."""
    file = Path(path)
    if not file.is_file():
        raise PolicyPackError(f"rule-pack file not found: {file}")
    try:
        loaded = yaml.safe_load(file.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise PolicyPackError(f"rule-pack file {file} is not valid YAML: {exc}") from exc

    if not isinstance(loaded, dict):
        raise PolicyPackError(f"rule-pack file {file} must be a mapping with a 'packs' list")
    entries = loaded.get("packs")
    if not isinstance(entries, list):
        raise PolicyPackError(f"rule-pack file {file} must define 'packs' as a list")
    include_defaults = bool(loaded.get("include_defaults", True))

    packs: list[RulePack] = []
    for index, entry in enumerate(entries):
        try:
            packs.append(RulePack.model_validate(entry))
        except ValidationError as exc:
            pack_id = entry.get("id", "<missing>") if isinstance(entry, dict) else "<not a map>"
            raise PolicyPackError(
                f"invalid rule pack at index {index} (id={pack_id}) in {file}: {exc}"
            ) from exc

    return [*defaults(), *packs] if include_defaults else packs
