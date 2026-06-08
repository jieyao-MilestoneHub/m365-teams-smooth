# ADR-0012: Contextual-retrieval knowledge base over Foundry IQ

- **Status:** Accepted
- **Date:** 2026-06-08

## Context

The court grounds its impact evidence in cited facts from a Foundry IQ knowledge base (Azure AI
Search). Two weaknesses undermined that grounding as a credible capability:

1. **The corpus was thin and demo-shaped.** A handful of bare policy docs, chunked as plain section
   text, read as "written for the demo" rather than as a real organization's knowledge — and, with so
   little noise, retrieval was never actually tested.
2. **Retrieval was opaque "chunk grabbing."** The index *had* a vector field and a semantic ranker,
   but chunks carried no contextual augmentation, so a short section detached from its parent document
   retrieves poorly — exactly the failure mode Anthropic's *Contextual Retrieval* targets.
3. **The corpus and seed were not version-controlled** — they lived only in the index, so the KB
   could not be reproduced or reviewed.

A hard constraint applies: Foundry IQ is the required Microsoft IQ integration, so the fix must keep
Foundry IQ as the retrieval surface rather than replace it with a bespoke pipeline.

## Decision

1. **A realistic, version-controlled corpus** under `knowledge/corpus/`: everyday meeting notes +
   company policies written as a believable company KB, *not* demo-tailored. It deliberately includes
   **adversarial near-misses** (a deprecated policy version, a same-vocabulary room-booking doc, a
   different project's standup) and **off-topic noise**, so retrieval quality is demonstrable.
2. **Anthropic Contextual Retrieval, adapted to Azure** (`backend/scripts/seed_knowledge.py`): each
   `##` section gets a short LLM-generated context prefix situating it in its document, stored in a
   **searchable `context` field**. Both keyword and vector matching see the situated chunk
   (contextual BM25 + contextual embeddings); the displayed claim stays the clean `page_chunk`.
   Retrieval remains **hybrid (BM25 + vector) + semantic rerank**, performed by the Foundry IQ
   knowledge base — query planning depth is configurable (`KNOWLEDGE_REASONING_EFFORT`, default
   `medium`). The seed only *adds* the `context` field; it reuses the existing index's vectorizer and
   semantic configuration, so Foundry IQ needs no reconfiguration.
3. **A retrieval-quality eval** (`backend/scripts/eval_retrieval.py`) runs the production retrieval
   for each trial query and asserts the intended target ranks #1 above its near-miss — the measurable
   proof that retrieval discriminates.

## Consequences

- Grounding is now a credible, professional-grade RAG capability, not a plausible-looking lookup: the
  corpus is realistic and the eval proves the right policy wins over deliberate distractors.
- The KB is reproducible from source: re-seeding is one idempotent command, keyless.
- Foundry IQ stays the retrieval surface (requirement preserved); the professionalism lives in corpus
  construction + the contextual index, not in a replacement pipeline.
- The offline `FakeKnowledgeProvider` remains the default for local/credential-free runs, with its
  citations mirroring the live corpus so the two surfaces ground the same policies.
- Cost: seeding makes one small `gpt-4o-mini` call per chunk plus one embedding; trivial and one-off.
