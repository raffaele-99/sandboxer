"""Docker container management — uses regular ``docker run`` with optional gVisor runtime."""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass

# Labels used to identify and query sandboxer-managed containers.
LABEL_MANAGED = "sandboxer.managed"
LABEL_AGENT = "sandboxer.agent"
LABEL_TEMPLATE = "sandboxer.template"
LABEL_WORKSPACE = "sandboxer.workspace"

# Default paths inside the container (matches docker/sandbox-templates images).
CONTAINER_HOME = "/home/agent"
CONTAINER_WORKSPACE = f"{CONTAINER_HOME}/workspace"


@dataclass(frozen=True)
class SandboxRow:
    """One row from container listing."""

    name: str
    status: str
    image: str
    agent: str = ""
    workspace: str = ""


class DockerError(Exception):
    """Raised when a docker command fails."""

    def __init__(self, returncode: int, stderr: str) -> None:
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(f"docker failed (rc={returncode}): {stderr}")


# Keep old name as alias for compatibility.
DockerSandboxError = DockerError


def _run_docker(
    args: list[str],
    *,
    check: bool = True,
    capture: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a ``docker`` command."""
    cmd = ["docker", *args]
    result = subprocess.run(cmd, text=True, capture_output=capture)
    if check and result.returncode != 0:
        raise DockerError(result.returncode, result.stderr or "")
    return result


# -- Template / image operations ---------------------------------------------

def build_template(dockerfile: str, tag: str, context_dir: str = ".") -> None:
    """Build a Docker image from a Dockerfile string."""
    _run_docker(["build", "-t", tag, "-f", dockerfile, context_dir])


def tag_image(source: str, target: str) -> None:
    _run_docker(["tag", source, target])


def push_image(tag: str) -> None:
    _run_docker(["image", "push", tag])


def pull_image(tag: str) -> None:
    _run_docker(["image", "pull", tag])


# -- Container lifecycle -----------------------------------------------------

def create(
    image: str,
    *,
    name: str | None = None,
    volumes: dict[str, str] | None = None,
    env: dict[str, str] | None = None,
    labels: dict[str, str] | None = None,
    runtime: str | None = None,
    network: str | None = None,
) -> str:
    """Create and start a container in detached mode.  Returns the container name.

    Uses ``docker run -d`` with an idle ``sleep infinity`` process so that
    the container stays alive for ``docker exec`` calls.

    *volumes* maps host paths to container paths.
    *runtime* can be ``"runsc"`` for gVisor isolation.
    """
    args = ["run", "-d"]
    if runtime:
        args.extend(["--runtime", runtime])
    if name:
        args.extend(["--name", name])
    if network:
        args.extend(["--network", network])

    # Always mark as sandboxer-managed.
    all_labels = {LABEL_MANAGED: "true"}
    if labels:
        all_labels.update(labels)
    for k, v in all_labels.items():
        args.extend(["--label", f"{k}={v}"])

    if volumes:
        for host_path, container_path in volumes.items():
            args.extend(["-v", f"{host_path}:{container_path}"])

    if env:
        for k, v in env.items():
            args.extend(["-e", f"{k}={v}"])

    # Keep the container running without starting an agent.
    args.extend(["--entrypoint", "sleep"])
    args.append(image)
    args.append("infinity")

    result = _run_docker(args)
    return name or (result.stdout or "").strip()[:12]


def list_sandboxes() -> list[SandboxRow]:
    """List sandboxer-managed containers."""
    result = _run_docker(
        [
            "ps", "-a",
            "--filter", f"label={LABEL_MANAGED}=true",
            "--format", "{{json .}}",
        ],
        check=False,
    )
    if result.returncode != 0:
        return []

    rows: list[SandboxRow] = []
    for line in (result.stdout or "").strip().splitlines():
        if not line.strip():
            continue
        data = json.loads(line)

        # Parse labels from the comma-separated string.
        label_map: dict[str, str] = {}
        for part in (data.get("Labels") or "").split(","):
            if "=" in part:
                k, v = part.split("=", 1)
                label_map[k] = v

        rows.append(SandboxRow(
            name=data.get("Names", ""),
            status=data.get("State", data.get("Status", "")),
            image=data.get("Image", ""),
            agent=label_map.get(LABEL_AGENT, ""),
            workspace=label_map.get(LABEL_WORKSPACE, ""),
        ))

    return rows


def exec_shell(
    name: str,
    command: str = "bash",
    *,
    env: dict[str, str] | None = None,
    workdir: str | None = None,
) -> None:
    """Exec an interactive shell inside a running container (foreground)."""
    cmd = ["docker", "exec", "-it"]
    if workdir:
        cmd.extend(["-w", workdir])
    if env:
        for key, value in env.items():
            cmd.extend(["-e", f"{key}={value}"])
    cmd.extend([name, command])
    subprocess.run(cmd)


def exec_command(
    name: str,
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    workdir: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Exec a non-interactive command inside a container."""
    args = ["exec"]
    if workdir:
        args.extend(["-w", workdir])
    if env:
        for k, v in env.items():
            args.extend(["-e", f"{k}={v}"])
    args.append(name)
    args.extend(command)
    return _run_docker(args)


def stop(name: str) -> None:
    _run_docker(["stop", name])


def remove(name: str) -> None:
    _run_docker(["rm", "-f", name])


def save_as_template(name: str, tag: str) -> None:
    _run_docker(["commit", name, tag])


def sandbox_stats(name: str) -> dict[str, str]:
    """Return resource usage for a container via ``docker stats``."""
    result = _run_docker(
        ["stats", "--no-stream", "--format", "{{json .}}", name],
    )
    raw = json.loads((result.stdout or "").strip())
    return {
        "name": raw.get("Name", name),
        "cpu_percent": raw.get("CPUPerc", ""),
        "mem_usage": raw.get("MemUsage", ""),
        "mem_percent": raw.get("MemPerc", ""),
        "net_io": raw.get("NetIO", ""),
        "block_io": raw.get("BlockIO", ""),
        "pids": raw.get("PIDs", ""),
    }


# -- Utility -----------------------------------------------------------------

def sandbox_exists(name: str) -> bool:
    """Check whether a container with the given name exists."""
    for row in list_sandboxes():
        if row.name == name:
            return True
    return False


def is_docker_available() -> bool:
    """Return True if the docker CLI is reachable."""
    try:
        result = subprocess.run(
            ["docker", "info"], text=True, capture_output=True,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def is_gvisor_available() -> bool:
    """Return True if the ``runsc`` (gVisor) runtime is available."""
    try:
        result = subprocess.run(
            ["docker", "info", "--format", "{{json .Runtimes}}"],
            text=True, capture_output=True,
        )
        if result.returncode != 0:
            return False
        return "runsc" in (result.stdout or "")
    except FileNotFoundError:
        return False


# Backward compat alias.
is_sandbox_feature_available = is_gvisor_available
