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
```

No key goes in the configuration — grant your identity (or the hosting platform's managed
identity) access to the Search service instead.

**What to put in the KB:** the corpus the court cites should be your *governance* knowledge — the
policies, commitments, and review rules your scenarios reason about (e.g. "milestone moves require
the comms team when an announcement is pending"). Grounded facts surface on the card as citations
attached to the impact evidence, so write entries as short, citable statements.

## Swapping in something else entirely

`KnowledgePort` is deliberately small. A different retrieval stack (your own RAG service, a vector
store, an internal wiki search) is one more adapter implementing `ground()` plus a selection
branch in the container — the pipeline, gatherers, and card never change.

## Verifying the wiring

- With the endpoint unset, trials run on the offline corpus — the baseline behavior.
- With the endpoint set, watch the impact evidence citations change to your KB's titles.
- The provider tests (`backend/tests/test_foundry_iq.py`) stub the retrieval client, so the suite
  stays green with no network either way.

## See also

- [deploy/foundry-iq.md](../deploy/foundry-iq.md) — provisioning the Azure environment (Bicep,
  region notes, teardown).
- [View ⑥ — Microsoft platform integration](../architecture/06-platform-integration.html) — where
  Foundry IQ sits in the platform map.
- [new-scenario.md](new-scenario.md) — how gatherers consume grounded facts.
