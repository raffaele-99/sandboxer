"""Agent adapter registry — install snippets for AI agent CLIs."""
from __future__ import annotations

import textwrap
from dataclasses import dataclass, field


@dataclass(frozen=True)
class AgentAdapter:
    """Describes how to install an AI agent CLI inside a sandbox."""

    name: str
    agent_type: str
    required_packages: list[str] = field(default_factory=list)
    install_snippet: list[str] = field(default_factory=list)
    auto_args: list[str] = field(default_factory=list)
    cli_binary: str = ""


ADAPTERS: dict[str, AgentAdapter] = {
    "claude": AgentAdapter(
        name="claude",
        agent_type="claude",
        required_packages=["nodejs", "npm", "ca-certificates"],
        install_snippet=["RUN npm install -g @anthropic-ai/claude-code"],
        auto_args=["--dangerously-skip-permissions"],
        cli_binary="claude",
    ),
    "codex": AgentAdapter(
        name="codex",
        agent_type="codex",
        required_packages=["ca-certificates", "curl", "tar", "gzip"],
        install_snippet=[
            textwrap.dedent("""\
                ARG CODEX_VERSION=0.107.0
                RUN set -eux; \\
                  arch="$(uname -m)"; \\
                  case "${arch}" in \\
                    x86_64) codex_target="x86_64-unknown-linux-musl" ;; \\
                    aarch64|arm64) codex_target="aarch64-unknown-linux-musl" ;; \\
                    *) echo "unsupported architecture: ${arch}" >&2; exit 1 ;; \\
                  esac; \\
                  codex_url="https://github.com/openai/codex/releases/download/rust-v${CODEX_VERSION}/codex-${codex_target}.tar.gz"; \\
                  tmpdir="$(mktemp -d)"; \\
                  curl -fsSL "${codex_url}" -o "${tmpdir}/codex.tgz"; \\
                  tar -xzf "${tmpdir}/codex.tgz" -C "${tmpdir}"; \\
                  cp "${tmpdir}/codex-${codex_target}" /usr/local/bin/codex; \\
                  chmod 0755 /usr/local/bin/codex; \\
                  rm -rf "${tmpdir}\"""").strip(),
        ],
        auto_args=["--full-auto"],
        cli_binary="codex",
    ),
    "gemini": AgentAdapter(
        name="gemini",
        agent_type="gemini",
        required_packages=["nodejs", "npm", "ca-certificates"],
        install_snippet=["RUN npm install -g @anthropic-ai/gemini-cli"],
        auto_args=[],
        cli_binary="gemini",
    ),
}


def get_adapter(agent_type: str) -> AgentAdapter | None:
    """Look up an adapter by agent type. Returns None if unknown."""
    return ADAPTERS.get(agent_type)


def adapter_dockerfile_lines(agent_type: str) -> list[str]:
    """Return Dockerfile lines to install the given agent type."""
    adapter = get_adapter(agent_type)
    if adapter is None:
        return []
    lines: list[str] = []
    if adapter.required_packages:
        pkg_str = " ".join(adapter.required_packages)
        lines.append(
            f"RUN apt-get update && DEBIAN_FRONTEND=noninteractive "
            f"apt-get install -y --no-install-recommends {pkg_str} "
            f"&& rm -rf /var/lib/apt/lists/*"
        )
    lines.extend(adapter.install_snippet)
    return lines
