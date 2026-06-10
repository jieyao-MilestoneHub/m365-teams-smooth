"""Pure markdown chunking for the governance corpus — no framework or SDK imports.

One responsibility: split a corpus document into the same ``(doc_title, [(heading, page_chunk)])``
shape the live Foundry IQ index is built from, so offline retrieval and the seed script agree on
chunk boundaries, titles, and ids. Both ``scripts/seed_knowledge.py`` (live index) and the offline
``corpus`` provider depend on these helpers; neither reimplements them.
"""

from __future__ import annotations

import re


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def chunk_markdown(text: str) -> tuple[str, list[tuple[str, str]]]:
    """Return ``(doc_title, [(section_heading, section_markdown), ...])``.

    The document title is the first ``# `` line; each ``## `` section is one chunk whose text keeps
    its ``## heading`` line (matching the index's existing ``page_chunk`` shape). Blockquote ``>``
    annotation lines (reviewer notes) are dropped from the indexed text.
    """
    lines = text.splitlines()
    doc_title = next((ln[2:].strip() for ln in lines if ln.startswith("# ")), "")
    chunks: list[tuple[str, str]] = []
    heading: str | None = None
    body: list[str] = []

    def flush() -> None:
        if heading is not None:
            content = "\n".join(body).strip()
            if content:
                chunks.append((heading, f"## {heading}\n{content}"))

    for ln in lines:
        if ln.startswith("## "):
            flush()
            heading = ln[3:].strip()
            body = []
        elif heading is not None and not ln.lstrip().startswith(">"):
            body.append(ln)
    flush()
    return doc_title, chunks


def doc_id(stem: str, index: int) -> str:
    return f"{slugify(stem)}-{index}"
