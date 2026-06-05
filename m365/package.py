"""Build the Microsoft 365 app package from the manifest templates.

Resolves the ``${{PLACEHOLDER}}`` tokens in the manifests from environment variables, then zips the
resolved manifest, the declarative agent, the plugin manifest, and the icons into
``m365/build/appPackage.zip`` — the file uploaded to a tenant (custom-app upload / Agents Toolkit).

Usage (from the repo root)::

    TEAMS_APP_ID=<guid> MCP_HOST_DOMAIN=change-court.example.com \
    MCP_SERVER_URL=https://change-court.example.com/mcp \
    OAUTH_CONNECTION_ID=<connection-ref> \
    python m365/package.py

Secrets are never read here; only public packaging values. No third-party dependencies.
"""

from __future__ import annotations

import os
import re
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).parent
BUILD = HERE / "build"

# Files copied into the package. Manifests are placeholder-substituted; icons are copied verbatim.
MANIFESTS = ["manifest.json", "declarative-agent.json", "ai-plugin.json"]
ICONS = ["color.png", "outline.png"]

# Every ${{TOKEN}} that may appear across the manifests, mapped to its source environment variable.
PLACEHOLDERS = {
    "TEAMS_APP_ID": "TEAMS_APP_ID",
    "MCP_HOST_DOMAIN": "MCP_HOST_DOMAIN",
    "MCP_SERVER_URL": "MCP_SERVER_URL",
    "OAUTH_CONNECTION_ID": "OAUTH_CONNECTION_ID",
    # Entra app that sends Graph activity-feed notifications (manifest webApplicationInfo).
    "GRAPH_CLIENT_ID": "GRAPH_CLIENT_ID",
    # The Azure Bot's app registration (manifest bots[].botId) — the approval-card surface.
    "BOT_APP_ID": "BOT_APP_ID",
}
_TOKEN = re.compile(r"\$\{\{\s*(\w+)\s*\}\}")


def _resolve(text: str, values: dict[str, str], missing: set[str]) -> str:
    """Replace each ``${{TOKEN}}`` from ``values``; record any token left without a value."""

    def sub(match: re.Match[str]) -> str:
        token = match.group(1)
        value = values.get(token)
        if not value:
            missing.add(token)
            return match.group(0)
        return value

    return _TOKEN.sub(sub, text)


def main() -> int:
    values = {token: os.environ.get(env, "") for token, env in PLACEHOLDERS.items()}
    missing: set[str] = set()

    missing_icons = [name for name in ICONS if not (HERE / name).exists()]
    if missing_icons:
        print(
            f"error: missing icon(s) {missing_icons} in m365/ — add color.png (192x192) and "
            "outline.png (32x32) before packaging.",
            file=sys.stderr,
        )
        return 1

    BUILD.mkdir(exist_ok=True)
    package = BUILD / "appPackage.zip"
    with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in MANIFESTS:
            resolved = _resolve((HERE / name).read_text(encoding="utf-8"), values, missing)
            zf.writestr(name, resolved)
        for name in ICONS:
            zf.write(HERE / name, name)

    if missing:
        package.unlink(missing_ok=True)
        envs = ", ".join(sorted(PLACEHOLDERS[t] for t in missing if t in PLACEHOLDERS))
        print(
            f"error: unresolved placeholder(s): {sorted(missing)}. Set the env var(s): {envs}.",
            file=sys.stderr,
        )
        return 1

    print(f"wrote {package.relative_to(HERE.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
