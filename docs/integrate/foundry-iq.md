# Grounding with Foundry IQ — wiring your own knowledge base

The court grounds impact evidence in **cited facts** retrieved from a knowledge base. This page
covers the integration side — the port, the provider selection, and pointing the court at *your*
knowledge base. Provisioning the backing Azure environment is covered separately in
[deploy/foundry-iq.md](../deploy/foundry-iq.md).

## The port

`backend/app/ports/knowledge.py` defines `KnowledgePort` with a single method:

```
ground(query, top_k=3) -> list[GroundedFact]
```

Each `GroundedFact` carries the fact text plus its citation (title + reference). The impact node
and the gatherers depend on this port only — they neither know nor care which provider answers.

## The two providers

| Provider | When | Auth |
| --- | --- | --- |
| `FakeKnowledgeProvider` (`adapters/knowledge/fake_knowledge.py`) | Default. Offline keyword-matched governance corpus; backs the trials with zero credentials. | none |
| `FoundryIqKnowledgeProvider` (`adapters/knowledge/foundry_iq.py`) | When a knowledge endpoint is configured. Agentic retrieval against a **Foundry IQ knowledge base over Azure AI Search**. | keyless — `DefaultAzureCredential` (`az login` locally, managed identity when hosted) |

Selection happens in the composition root (`backend/app/container.py`): the real provider is used
when `KNOWLEDGE_SEARCH_ENDPOINT` and `KNOWLEDGE_BASE_NAME` are set **and** `FORCE_ALL_MOCK` is
false. Nothing else changes either way.

## Point the court at your knowledge base

```
KNOWLEDGE_SEARCH_ENDPOINT=https://<your-search-service>.search.windows.net
KNOWLEDGE_BASE_NAME=<knowledge base name>
KNOWLEDGE_SOURCE_NAME=<knowledge source name>
KNOWLEDGE_REASONING_EFFORT=medium   # query-planning depth: minimal | low | medium
```

No key goes in the configuration — grant your identity (or the hosting platform's managed
identity) access to the Search service instead.

**What to put in the KB — and how retrieval works.** The corpus is version-controlled under
[`knowledge/corpus/`](../../knowledge/corpus/): a *realistic* company knowledge base (everyday
meeting notes + policies), deliberately mixed with **adversarial near-misses and off-topic noise** so
retrieval quality is demonstrable, not assumed. Retrieval is **professional-grade RAG**, adapting
Anthropic's *Contextual Retrieval* onto Azure / Foundry IQ:

- **Contextual chunking** — `backend/scripts/seed_knowledge.py` generates a short LLM context prefix
  per `##` section (situating it in its document) and stores it in a searchable `context` field, so
  both keyword and vector matching see the situated chunk (contextual BM25 + contextual embeddings).
- **Hybrid + rerank** — the index carries BM25, a `text-embedding-3-large` vector field, and a
  semantic ranker; Foundry IQ plans the query (reasoning effort above) then retrieves hybrid +
  semantic-reranked. Grounded facts surface on the card as citations (the displayed claim stays the
  clean `page_chunk`; the context prefix is search-only).

Re-seed after editing the corpus: `cd backend && uv run python -m scripts.seed_knowledge`
(keyless; `--dry-run` to preview chunking without writing). See
[deploy/foundry-iq.md](../deploy/foundry-iq.md) for provisioning + roles.

## Swapping in something else entirely

`KnowledgePort` is deliberately small. A different retrieval stack (your own RAG service, a vector
store, an internal wiki search) is one more adapter implementing `ground()` plus a selection
branch in the container — the pipeline, gatherers, and card never change.

## Verifying the wiring

- With the endpoint unset, trials run on the offline corpus — the baseline behavior.
- With the endpoint set, watch the impact evidence citations change to your KB's titles.
- **Retrieval-quality eval:** `cd backend && uv run python -m scripts.eval_retrieval` runs the
  production retrieval for each trial query and asserts the intended target policy ranks #1 above its
  adversarial near-miss (e.g. the current Release & Change Management Policy above the deprecated v1
  and the room-booking "scheduling" doc) — the concrete proof retrieval discriminates.
- The provider/seed tests (`backend/tests/test_foundry_iq.py`, `test_seed_knowledge.py`) stub the
  network, so the suite stays green offline either way.

## See also

- [deploy/foundry-iq.md](../deploy/foundry-iq.md) — provisioning the Azure environment (Bicep,
  region notes, teardown).
- [View ⑥ — Microsoft platform integration](../architecture/06-platform-integration.html) — where
  Foundry IQ sits in the platform map.
- [new-scenario.md](new-scenario.md) — how gatherers consume grounded facts.
