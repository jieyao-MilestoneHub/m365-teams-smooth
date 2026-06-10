"""The knowledge seed script's pure helpers: markdown chunking and index-definition shaping.

The network steps (contextualize, embed, push) are not unit-tested here; these cover the
deterministic transforms the seeding depends on.
"""

from __future__ import annotations

from app.adapters.knowledge.markdown import chunk_markdown, doc_id, slugify
from scripts.seed_knowledge import build_index_definition

_DOC = """# Release & Change Management Policy

> reviewer note: this blockquote must be excluded from the indexed chunk text.

## Purpose and scope
This policy governs changes to committed launch dates.

## Coordinated downstream updates
An approved slip must propagate to every dependent system.
"""


def test_chunk_markdown_splits_by_section_and_drops_blockquotes() -> None:
    title, chunks = chunk_markdown(_DOC)
    assert title == "Release & Change Management Policy"
    assert [h for h, _ in chunks] == ["Purpose and scope", "Coordinated downstream updates"]
    # The chunk keeps its `## heading` line (matching the index's page_chunk shape)...
    assert chunks[0][1].startswith("## Purpose and scope")
    assert "This policy governs changes" in chunks[0][1]
    # ...and the reviewer blockquote never reaches the indexed text.
    assert "reviewer note" not in chunks[0][1]
    assert all("reviewer note" not in body for _, body in chunks)


def test_chunk_markdown_ignores_sectionless_and_empty() -> None:
    assert chunk_markdown("# Title only, no sections") == ("Title only, no sections", [])
    _, chunks = chunk_markdown("# T\n\n## Empty\n\n## Real\nbody")
    assert [h for h, _ in chunks] == ["Real"]  # the empty section is dropped


def test_doc_id_and_slugify_are_stable() -> None:
    assert slugify("Release & Change Management!") == "release-change-management"
    assert doc_id("release-change-management", 2) == "release-change-management-2"


def test_build_index_definition_adds_context_field_idempotently() -> None:
    existing = {
        "@odata.etag": "x",
        "name": "idx",
        "fields": [
            {"name": "id", "type": "Edm.String", "key": True},
            {"name": "page_chunk", "type": "Edm.String", "searchable": True, "retrievable": True},
        ],
        "semantic": {
            "configurations": [
                {"prioritizedFields": {"prioritizedContentFields": [{"fieldName": "page_chunk"}]}}
            ]
        },
    }
    out = build_index_definition(existing)
    assert not any(k.startswith("@odata") for k in out)  # read-only props stripped for PUT
    names = [f["name"] for f in out["fields"]]
    assert "context" in names
    context = next(f for f in out["fields"] if f["name"] == "context")
    assert context["searchable"] is True  # contextual BM25 needs the field searchable
    content = out["semantic"]["configurations"][0]["prioritizedFields"]["prioritizedContentFields"]
    assert {"fieldName": "context"} in content

    # Idempotent: running again does not duplicate the field or the semantic entry.
    again = build_index_definition(out)
    assert [f["name"] for f in again["fields"]].count("context") == 1
    sem = again["semantic"]["configurations"][0]["prioritizedFields"]
    assert sem["prioritizedContentFields"].count({"fieldName": "context"}) == 1
