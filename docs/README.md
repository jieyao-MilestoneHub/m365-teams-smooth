# Documentation map

These docs cover only what isn't already obvious from the code: the **architecture** (diagrams), the
**demo** (one scenario), the **extension guide**, and the **decisions** behind the design (ADRs).
Setup and deployment are derivable from the codebase plus the official Microsoft docs linked below.

## How to use these docs

| Your goal | Start here |
| --- | --- |
| **Understand the design** | [architecture/index.html](architecture/index.html) — four offline diagrams (layers · data flow · sequence · Azure/M365) |
| **See the demo & reproduce it** | [demo/README.md](demo/README.md) — the Informed Approval scenario, credential-free |
| **Extend it (new scenario or integration)** | [extending.md](extending.md) — pack files, adapters, what never changes |
| **Know who must approve, and when** | [approval-policy.md](approval-policy.md) — risk levels, rule packs as data, what auto-approves |
| **Know *why* a choice was made** | [adr/](adr/) — Architecture Decision Records, one file per decision |
| **Get the project running** | [../README.md](../README.md) — quick start, configuration, repo layout |
| **Contribute** | [../CONTRIBUTING.md](../CONTRIBUTING.md) |

New here? Read the [architecture diagrams](architecture/index.html), then
[the demo](demo/README.md), then skim the [ADRs](adr/) for the reasoning.

## Microsoft 365 / Azure service reference

The platform pieces this project builds on — go to the source for setup and API details:

- **Microsoft 365 Copilot — declarative agents:** https://learn.microsoft.com/microsoft-365-copilot/extensibility/overview-declarative-agent
- **Microsoft 365 Agents Toolkit:** https://learn.microsoft.com/microsoft-365/developer/agents-toolkit
- **Model Context Protocol (MCP):** https://modelcontextprotocol.io/
- **Teams Adaptive Cards:** https://learn.microsoft.com/adaptive-cards/
- **Microsoft Graph API:** https://learn.microsoft.com/graph/overview
- **Microsoft Entra ID — OAuth 2.0 / OpenID Connect:** https://learn.microsoft.com/entra/identity-platform/v2-protocols
- **Azure Container Apps:** https://learn.microsoft.com/azure/container-apps/overview
- **Azure AI Foundry:** https://learn.microsoft.com/azure/ai-foundry/
- **Foundry IQ / Azure AI Search:** https://learn.microsoft.com/azure/search/search-what-is-azure-search
- **Azure Key Vault:** https://learn.microsoft.com/azure/key-vault/general/overview
