# Foundry IQ — knowledge grounding

> This page covers **provisioning** the backing Azure environment. For the integration side —
> the port, provider selection, and pointing the court at your own knowledge base — see
> [integrate/foundry-iq.md](../integrate/foundry-iq.md).

The court grounds its reasoning in cited facts via the `KnowledgePort`
(`backend/app/ports/knowledge.py`), consumed by the impact gatherers and the impact node. Two
providers satisfy the same port:

- **`FakeKnowledgeProvider`** (`adapters/knowledge/fake_knowledge.py`) — the default offline
  stand-in: a small, public-safe governance corpus matched by keyword. Backs the three trials with no
  external credentials.
- **`FoundryIqKnowledgeProvider`** (`adapters/knowledge/foundry_iq.py`) — the real provider: agentic
  retrieval against a managed **Azure AI Foundry knowledge base (Foundry IQ over Azure AI Search)**,
  returning cited facts. Authentication is keyless (`DefaultAzureCredential`).

## Selection
The composition root (`backend/app/container.py`) picks the real provider when a knowledge endpoint is
configured and `FORCE_ALL_MOCK` is false; otherwise it uses the fake. Nothing else changes — the
impact node and gatherers depend only on `KnowledgePort`.

## Configuration (`.env`)
Keyless auth — run `az login` locally (or use a managed identity when hosted); no key is stored.

```
KNOWLEDGE_SEARCH_ENDPOINT=https://<your-search-service>.search.windows.net
KNOWLEDGE_BASE_NAME=<knowledge base name>
KNOWLEDGE_SOURCE_NAME=<knowledge source name>
```
Leave `KNOWLEDGE_SEARCH_ENDPOINT` empty to use the offline fake.

## Provision the backing Azure environment
The knowledge base is provisioned with Bicep from Microsoft's
[`iq-series` Episode 1 cookbook](https://github.com/microsoft/iq-series) (Azure AI Search Standard +
Azure OpenAI `text-embedding-3-large`/`gpt-4o-mini` + an AI Foundry project + the Search↔Foundry
connection). Reproduce (~10 min):

```bash
# Prereqs: Azure CLI + `az login`; on Windows Git Bash:
#   export PATH="/c/Program Files/Microsoft SDKs/Azure/CLI2/wbin:$PATH"
git clone https://github.com/microsoft/iq-series.git iq-series      # add /iq-series/ to .gitignore
cd iq-series
OBJ=$(az ad signed-in-user show --query id -o tsv)
az group create -n iq-series-rg -l japaneast
az deployment group what-if -g iq-series-rg --template-file infra/main.bicep \
  --parameters userObjectId=$OBJ resourcePrefix=iqs location=japaneast searchServiceSku=standard
az deployment group create -g iq-series-rg --name foundry-iq-setup --template-file infra/main.bicep \
  --parameters userObjectId=$OBJ resourcePrefix=iqs location=japaneast searchServiceSku=standard
```
Region `japaneast` is the closest agentic-retrieval region to Taiwan that also offers the OpenAI
models (`eastus2` was out of AI Search capacity). Map the deployment outputs (`searchEndpoint`,
knowledge-base / knowledge-source names) onto the `.env` keys above. Teardown to stop charges (AI
Search Standard ≈ $8/day): `az group delete --name iq-series-rg --yes --no-wait`.

> The infrastructure-as-code choice is **Bicep** (Azure-native, `what-if` preview, no state store);
> the cookbook's `main.bicep` is reused as-is rather than forked.

## Testing
`backend/tests/test_foundry_iq.py` injects a stub retrieval client (no network) and asserts the
reference → `GroundedFact` mapping, `top_k`, and skip-empty behavior. The fake provider remains the
default in `conftest.py`, so the three trials stay credential-free.

## Follow-up
The currently-seeded knowledge base holds the cookbook's NASA sample corpus, not the governance
policies the trials reason about. Seeding a governance corpus (so the **real** provider grounds the
trials as the fake's corpus does) is a separate task; the fake remains the default until then.
