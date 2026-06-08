"""Seed the Foundry IQ knowledge base with the contextual-retrieval corpus.

Adapts Anthropic's *Contextual Retrieval* onto Azure AI Search / Foundry IQ. For each `##` section
of every corpus markdown file it:

1. generates a 1-2 sentence **context prefix** with a small chat model (situating the chunk in its
   document — Anthropic's contextualizer), then
2. embeds ``context + chunk`` with text-embedding-3-large, and
3. pushes ``{id, title, context, page_chunk, page_embedding}`` to the index.

The ``context`` field is **searchable**, so BM25 matches context + chunk (contextual BM25) while the
displayed claim stays the clean ``page_chunk``. Retrieval at query time is hybrid (BM25 + vector) +
semantic rerank — configured on the index — so this script rebuilds only the *content*; it reuses
the existing index's vectorizer and semantic configuration (only adding the ``context`` field).

Idempotent: re-running replaces the corpus (stale documents are deleted). Auth is keyless
(``DefaultAzureCredential`` — ``az login`` locally, or a managed identity), needing *Search Index
Data Contributor* + *Search Service Contributor* on the search service and *Cognitive Services
OpenAI User* on the OpenAI account.

Run:  ``uv run python -m scripts.seed_knowledge``  (``--dry-run`` skips writes)
"""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from typing import Any

import httpx
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import AzureOpenAI

# --- config (env-driven, with the live defaults) ---
SEARCH_ENDPOINT = os.environ.get(
    "KNOWLEDGE_SEARCH_ENDPOINT", "https://iqs-search-mm65ytt5g64nw.search.windows.net"
).rstrip("/")
INDEX_NAME = os.environ.get("KNOWLEDGE_INDEX_NAME", "change-court-governance")
OPENAI_ENDPOINT = os.environ.get(
    "KNOWLEDGE_OPENAI_ENDPOINT", "https://iqs-openai-mm65ytt5g64nw.openai.azure.com"
).rstrip("/")
EMBED_DEPLOYMENT = os.environ.get("KNOWLEDGE_EMBED_DEPLOYMENT", "text-embedding-3-large")
CONTEXT_DEPLOYMENT = os.environ.get("KNOWLEDGE_CONTEXT_DEPLOYMENT", "gpt-4o-mini")
OPENAI_API_VERSION = os.environ.get("KNOWLEDGE_OPENAI_API_VERSION", "2024-10-21")
SEARCH_API_VERSION = "2024-07-01"
_DEFAULT_CORPUS = Path(__file__).resolve().parents[2] / "knowledge" / "corpus"
CORPUS_DIR = Path(os.environ.get("KNOWLEDGE_CORPUS_DIR", _DEFAULT_CORPUS))

_SEARCH_SCOPE = "https://search.azure.com/.default"
_OPENAI_SCOPE = "https://cognitiveservices.azure.com/.default"

_CONTEXT_PROMPT = (
    "<document>\n{doc}\n</document>\n\n"
    "Here is a chunk we want to situate within the whole document:\n"
    "<chunk>\n{chunk}\n</chunk>\n\n"
    "Give a short, succinct context (1-2 sentences) that situates this chunk within the overall "
    "document to improve search retrieval. Answer only with the context, nothing else."
)


# --- pure helpers (unit-tested) -------------------------------------------------------------------

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


def build_index_definition(existing: dict[str, Any]) -> dict[str, Any]:
    """Take the live index definition and add a searchable ``context`` field (+ semantic priority).

    Read-only ``@odata.*`` keys are stripped so the result is a valid PUT body. Idempotent: a
    pre-existing ``context`` field is left as-is.
    """
    definition = {k: v for k, v in existing.items() if not k.startswith("@odata")}
    fields = definition["fields"]
    names = {f["name"] for f in fields}
    if "context" not in names:
        page_chunk = next(f for f in fields if f["name"] == "page_chunk")
        context_field = {k: v for k, v in page_chunk.items() if not k.startswith("@odata")}
        context_field["name"] = "context"
        fields.append(context_field)
    # Let the semantic reranker see the context prefix too.
    try:
        prioritized = definition["semantic"]["configurations"][0]["prioritizedFields"]
        content = prioritized.setdefault("prioritizedContentFields", [])
        if not any(f.get("fieldName") == "context" for f in content):
            content.append({"fieldName": "context"})
    except (KeyError, IndexError, TypeError):
        pass
    return definition


# --- network helpers ------------------------------------------------------------------------------

def _search(client: httpx.Client, method: str, path: str, **kw: Any) -> httpx.Response:
    url = f"{SEARCH_ENDPOINT}/{path}"
    params = {"api-version": SEARCH_API_VERSION, **kw.pop("params", {})}
    resp = client.request(method, url, params=params, **kw)
    resp.raise_for_status()
    return resp


def contextualize(oai: AzureOpenAI, doc: str, chunk: str) -> str:
    resp = oai.chat.completions.create(
        model=CONTEXT_DEPLOYMENT,
        messages=[{"role": "user", "content": _CONTEXT_PROMPT.format(doc=doc, chunk=chunk)}],
        temperature=0,
        max_tokens=120,
    )
    return (resp.choices[0].message.content or "").strip()


def embed(oai: AzureOpenAI, text: str) -> list[float]:
    return oai.embeddings.create(model=EMBED_DEPLOYMENT, input=text).data[0].embedding


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the contextual-retrieval knowledge base.")
    parser.add_argument("--dry-run", action="store_true", help="chunk + contextualize, no writes")
    args = parser.parse_args()

    files = sorted(CORPUS_DIR.rglob("*.md"))
    files = [f for f in files if f.name != "README.md"]
    if not files:
        raise SystemExit(f"no corpus markdown under {CORPUS_DIR}")
    print(f"corpus: {len(files)} document(s) under {CORPUS_DIR}")

    credential = DefaultAzureCredential()
    oai = AzureOpenAI(
        azure_endpoint=OPENAI_ENDPOINT,
        azure_ad_token_provider=get_bearer_token_provider(credential, _OPENAI_SCOPE),
        api_version=OPENAI_API_VERSION,
    )

    documents: list[dict[str, Any]] = []
    for path in files:
        doc_title, chunks = chunk_markdown(path.read_text(encoding="utf-8"))
        for i, (heading, chunk_md) in enumerate(chunks, start=1):
            context = contextualize(oai, path.read_text(encoding="utf-8"), chunk_md)
            embedding = [] if args.dry_run else embed(oai, f"{context}\n\n{chunk_md}")
            documents.append(
                {
                    "id": doc_id(path.stem, i),
                    "title": f"{doc_title} — {heading}" if doc_title else heading,
                    "context": context,
                    "page_chunk": chunk_md,
                    "page_embedding": embedding,
                }
            )
        print(f"  {path.name}: {len(chunks)} chunk(s) contextualized")
    print(f"total chunks: {len(documents)}")

    if args.dry_run:
        s = documents[0]
        print(f"\n[dry-run] sample id={s['id']}\n  title: {s['title']}\n  context: {s['context']}")
        return

    token = get_bearer_token_provider(credential, _SEARCH_SCOPE)()
    with httpx.Client(timeout=60, headers={"Authorization": f"Bearer {token}"}) as client:
        existing = _search(client, "GET", f"indexes/{INDEX_NAME}").json()
        definition = build_index_definition(existing)
        _search(client, "PUT", f"indexes/{INDEX_NAME}", json=definition)
        print(f"index '{INDEX_NAME}': ensured `context` field")

        stale = _search(
            client, "GET", f"indexes/{INDEX_NAME}/docs",
            params={"search": "*", "$select": "id", "$top": "1000"},
        ).json()["value"]
        if stale:
            _search(
                client, "POST", f"indexes/{INDEX_NAME}/docs/index",
                json={"value": [{"@search.action": "delete", "id": d["id"]} for d in stale]},
            )
            print(f"deleted {len(stale)} stale document(s)")

        for start in range(0, len(documents), 50):
            batch = documents[start : start + 50]
            _search(
                client, "POST", f"indexes/{INDEX_NAME}/docs/index",
                json={"value": [{"@search.action": "mergeOrUpload", **d} for d in batch]},
            )
            print(f"uploaded {start + len(batch)}/{len(documents)}")

    print("done — knowledge base reseeded with the contextual-retrieval corpus")


if __name__ == "__main__":
    main()
