# Integrating your own scenario — the extension guide

AI Change Court is built to be extended without touching its core. The two sentences that matter:

> **A new integration = one adapter + one registration.**
> **A new scenario = one rule pack + one gatherer + one planner.**

Everything else — the LangGraph court, the services, MCP, REST, the Adaptive Card — stays
unchanged. This directory explains exactly what to add (and what not to touch) for each kind of
extension.

## Which doc for which goal

| You want to… | Read |
| --- | --- |
| Connect a third-party system (your ticketing tool, your CRM, …) | [third-party-adapter.md](third-party-adapter.md) |
| Turn a Microsoft 365 service real (GitHub / Outlook / SharePoint) | [deploy/github.md](../deploy/github.md) · [deploy/outlook.md](../deploy/outlook.md) · [deploy/sharepoint.md](../deploy/sharepoint.md) |
| Put a new kind of decision on trial (your own scenario) | [new-scenario.md](new-scenario.md) |
| Ground the court's reasoning in your own knowledge base (Foundry IQ) | [foundry-iq.md](foundry-iq.md) |
| Expose a new MCP tool / update the M365 agent manifests | [mcp-tools-and-agent-manifest.md](mcp-tools-and-agent-manifest.md) |
| Swap or configure the LLM provider | [llm-provider.md](llm-provider.md) |
| Look up an environment variable | [config-reference.md](config-reference.md) |

## Where these extensions sit in the architecture

The diagrams make the seams visible:

- [View ① — Layered architecture](../architecture/01-layered-architecture.html): the dashed
  `ports/` band is the boundary every extension plugs into.
- [View ⑥ — Microsoft platform integration](../architecture/06-platform-integration.html): the
  bottom row is exactly the set of adapters; your system becomes one more box there.
- [View ② — Court pipeline](../architecture/02-court-pipeline.html): a new scenario flows through
  the same seven nodes — you supply the data they consume, not new nodes.

## Ground rules (the boundaries that keep extension cheap)

1. **Depend on ports, never on SDKs, from the core.** Your SDK calls live inside your adapter
   module only. `agent/` and `services/` must keep importing nothing but `ports/` and `domain/`.
2. **Real vs mock is configuration.** Ship a mock alongside any real adapter and register both;
   `INTEGRATION_MODE` picks per system, and `FORCE_ALL_MOCK=true` must always produce a working,
   credential-free run.
3. **Rules are data, not code.** Risk weights, unsafe markers, approver roles, and verdict options
   live in a rule pack — adding a scenario should not add `if` statements to the policy node.
4. **Declare capabilities honestly.** The intake hallucination guard only allows actions whose
   capability (name + parameter schema) your adapter registered. What you don't declare cannot be
   planned or executed — that is the safety model working, not an obstacle.
5. **Keep PRs single-responsibility.** One adapter per PR, one scenario per PR — see
   [.claude/rules/git-workflow.md](../../.claude/rules/git-workflow.md).

## The composition root

All wiring converges in `backend/app/container.py`: adapters, the knowledge provider, the LLM
provider, persistence. If you find yourself editing any other core file to "make your integration
visible", stop — the design intends one registration in the container and nothing else.
