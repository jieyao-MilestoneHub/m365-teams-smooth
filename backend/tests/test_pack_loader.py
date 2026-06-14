"""Rule packs load from a data file and propagate through every pack derivation."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.agent.policy_rules.loader import PolicyPackError, load_packs
from app.agent.policy_rules.packs import default_packs
from app.agent.policy_rules.vocabulary import (
    grounding_queries,
    marks_unsafe_tags,
    tag_vocabulary,
)
from app.config import Settings
from app.container import build_court_service

_EXAMPLE = Path(__file__).resolve().parents[2] / "assets" / "policy-packs" / "example.yaml"

_PACK_YAML = """
packs:
  - id: dns_change
    match:
      any_action_capability: ["dns.update_record"]
    subjects: ["dns-change"]
    grounding_query: "DNS change production zone rollback window"
    risk_factors:
      - id: production_zone
        when_tag: dns.production_zone
        severity: high
        marks_unsafe: true
    quorum:
      approvers:
        - { role: eng_lead, when_tag: dns.production_zone }
"""


def test_file_packs_append_to_the_defaults(tmp_path: Path) -> None:
    file = tmp_path / "packs.yaml"
    file.write_text(_PACK_YAML)
    packs = load_packs(file)
    assert [p.id for p in packs] == [*(p.id for p in default_packs()), "dns_change"]
    # The derivations are downstream of the loader, so the file propagates everywhere.
    assert "dns.production_zone" in tag_vocabulary(packs)
    assert "dns.production_zone" in marks_unsafe_tags(packs)
    assert grounding_queries(packs)["dns-change"] == "DNS change production zone rollback window"


def test_include_defaults_false_replaces_the_builtins(tmp_path: Path) -> None:
    file = tmp_path / "packs.yaml"
    file.write_text("include_defaults: false\n" + _PACK_YAML)
    assert [p.id for p in load_packs(file)] == ["dns_change"]


def test_missing_file_fails_fast(tmp_path: Path) -> None:
    with pytest.raises(PolicyPackError, match="not found"):
        load_packs(tmp_path / "nope.yaml")


def test_invalid_yaml_names_the_file(tmp_path: Path) -> None:
    file = tmp_path / "packs.yaml"
    file.write_text("packs: [unclosed")
    with pytest.raises(PolicyPackError, match="not valid YAML"):
        load_packs(file)


def test_wrong_shape_is_a_clear_error(tmp_path: Path) -> None:
    file = tmp_path / "packs.yaml"
    file.write_text("- just\n- a list\n")
    with pytest.raises(PolicyPackError, match="must be a mapping"):
        load_packs(file)
    file.write_text("packs: not-a-list\n")
    with pytest.raises(PolicyPackError, match="'packs' as a list"):
        load_packs(file)


def test_invalid_entry_names_its_index_and_id(tmp_path: Path) -> None:
    file = tmp_path / "packs.yaml"
    # An invalid severity enum fails RulePack validation, naming the entry's index and id.
    file.write_text(
        "packs:\n  - id: broken\n    risk_factors:\n"
        "      - id: f\n        when_tag: x\n        severity: not-a-level\n"
    )
    with pytest.raises(PolicyPackError, match=r"index 0 \(id=broken\)"):
        load_packs(file)


def test_the_checked_in_example_loads() -> None:
    # The file the docs walk through must stay loadable.
    packs = load_packs(_EXAMPLE)
    assert "dns_change" in [p.id for p in packs]


def test_settings_path_drives_composition(tmp_path: Path) -> None:
    file = tmp_path / "packs.yaml"
    file.write_text(_PACK_YAML)
    settings = Settings(
        force_all_mock=True,
        db_url=f"sqlite:///{tmp_path / 'court.db'}",
        dry_run_default=True,
        policy_packs_path=str(file),
    )
    service = build_court_service(settings)  # composition succeeds with the file applied
    assert service is not None

    settings_broken = Settings(
        force_all_mock=True,
        db_url=f"sqlite:///{tmp_path / 'court2.db'}",
        dry_run_default=True,
        policy_packs_path=str(tmp_path / "missing.yaml"),
    )
    with pytest.raises(PolicyPackError):
        build_court_service(settings_broken)


def test_policy_packs_path_defaults_empty() -> None:
    assert Settings(force_all_mock=True, db_url="sqlite:///:memory:").policy_packs_path == ""
