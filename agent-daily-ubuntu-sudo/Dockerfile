FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ARG CODEX_VERSION=0.107.0
ARG USERNAME=agent
ARG UID=1000
ARG GID=1000

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    ca-certificates \
    curl \
    git \
    jq \
    less \
    nano \
    openssh-client \
    procps \
    python3 \
    ripgrep \
    sudo \
    tini \
    unzip \
    wget \
    && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    if getent group "${GID}" >/dev/null 2>&1; then \
      GROUP_NAME="$(getent group "${GID}" | cut -d: -f1)"; \
    else \
      GROUP_NAME="${USERNAME}"; \
      groupadd --gid "${GID}" "${GROUP_NAME}"; \
    fi; \
    if getent passwd "${UID}" >/dev/null 2>&1; then \
      USER_NAME="$(getent passwd "${UID}" | cut -d: -f1)"; \
    else \
      USER_NAME="${USERNAME}"; \
      useradd --uid "${UID}" --gid "${GID}" -m -s /bin/bash "${USER_NAME}"; \
    fi; \
    usermod -g "${GID}" "${USER_NAME}"; \
    echo "${USER_NAME} ALL=(ALL) NOPASSWD:ALL" > "/etc/sudoers.d/${USER_NAME}"; \
    chmod 0440 "/etc/sudoers.d/${USER_NAME}"; \
    mkdir -p "/home/${USER_NAME}/.codex" /workspace /tmp; \
    chown -R "${UID}:${GID}" "/home/${USER_NAME}" /workspace /tmp

RUN set -eux; \
    arch="$(uname -m)"; \
    case "${arch}" in \
      x86_64) codex_target="x86_64-unknown-linux-musl" ;; \
      aarch64|arm64) codex_target="aarch64-unknown-linux-musl" ;; \
      *) echo "unsupported architecture for Codex install: ${arch}" >&2; exit 1 ;; \
    esac; \
    codex_url="https://github.com/openai/codex/releases/download/rust-v${CODEX_VERSION}/codex-${codex_target}.tar.gz"; \
    tmpdir="$(mktemp -d)"; \
    curl -fsSL "${codex_url}" -o "${tmpdir}/codex.tgz"; \
    tar -xzf "${tmpdir}/codex.tgz" -C "${tmpdir}"; \
    install -m 0755 "${tmpdir}/codex-${codex_target}" /usr/local/bin/codex; \
    rm -rf "${tmpdir}"

ENV HOME=/home/${USERNAME}
ENV CODEX_HOME=${HOME}/.codex

WORKDIR /workspace
USER ${USERNAME}

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/bin/bash"]
