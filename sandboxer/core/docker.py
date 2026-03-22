"""Container management — uses containerkit for runtime-agnostic operations."""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass

import containerkit
from containerkit import Mount, RunOptions, Runtime

# Labels used to identify and query sandboxer-managed containers.
LABEL_MANAGED = "sandboxer.managed"
LABEL_AGENT = "sandboxer.agent"
LABEL_TEMPLATE = "sandboxer.template"
LABEL_WORKSPACE = "sandboxer.workspace"

# Default paths inside the container (matches docker/sandbox-templates images).
CONTAINER_HOME = "/home/agent"
CONTAINER_WORKSPACE = f"{CONTAINER_HOME}/workspace"

# Module-level runtime instance (lazily initialized).
_runtime: Runtime | None = None


def get_runtime() -> Runtime:
    """Get or initialize the containerkit runtime."""
    global _runtime
    if _runtime is None:
        _runtime = containerkit.resolve()
    return _runtime


@dataclass(frozen=True)
class SandboxRow:
    """One row from container listing."""

    name: str
    status: str
    image: str
    agent: str = ""
    workspace: str = ""


class DockerError(Exception):
    """Raised when a container command fails."""

    def __init__(self, returncode: int, stderr: str) -> None:
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(f"container command failed (rc={returncode}): {stderr}")


# Keep old name as alias for compatibility.
DockerSandboxError = DockerError


def _run_cmd(
    args: list[str],
    *,
    check: bool = True,
    capture: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a container CLI command using the resolved runtime binary."""
    rt = get_runtime()
    cmd = [rt.binary, *args]
    result = subprocess.run(cmd, text=True, capture_output=capture)
    if check and result.returncode != 0:
        raise DockerError(result.returncode, result.stderr or "")
    return result


# -- Template / image operations ---------------------------------------------

def build_template(
    dockerfile: str, tag: str, context_dir: str = ".", dns: str | None = None,
) -> None:
    """Build a container image from a Dockerfile."""
    rt = get_runtime()
    cmd = rt.build_build_command(tag, context_dir, file=dockerfile)
    if dns:
        # Insert --dns before the context dir (last arg).
        cmd = cmd[:-1] + ["--dns", dns, cmd[-1]]
    result = subprocess.run(cmd, text=True, capture_output=True)
    if result.returncode != 0:
        raise DockerError(result.returncode, result.stderr or "")


def tag_image(source: str, target: str) -> None:
    _run_cmd(["tag", source, target])


def push_image(tag: str) -> None:
    _run_cmd(["image", "push", tag])


def pull_image(tag: str) -> None:
    rt = get_runtime()
    cmd = rt.build_pull_command(tag)
    result = subprocess.run(cmd, text=True, capture_output=True)
    if result.returncode != 0:
        raise DockerError(result.returncode, result.stderr or "")


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
    dns: str | None = None,
) -> str:
    """Create and start a container in detached mode.  Returns the container name.

    Uses ``<runtime> run -d`` with an idle ``sleep infinity`` process so that
    the container stays alive for exec calls.

    *volumes* maps host paths to container paths (append ``:ro`` for read-only).
    *runtime* can be ``"runsc"`` for gVisor isolation (Docker only).
    """
    rt = get_runtime()

    # Convert volume dict to containerkit Mount objects.
    mounts: list[Mount] = []
    if volumes:
        for host_path, container_path in volumes.items():
            readonly = False
            if container_path.endswith(":ro"):
                container_path = container_path[:-3]
                readonly = True
            mounts.append(Mount(host_path, container_path, readonly=readonly))

    # Build extra args for features not directly in RunOptions.
    extra: list[str] = ["-d"]
    if runtime:
        extra.extend(["--runtime", runtime])
    if dns:
        extra.extend(["--dns", dns])

    # Always mark as sandboxer-managed.
    all_labels = {LABEL_MANAGED: "true"}
    if labels:
        all_labels.update(labels)
    for k, v in all_labels.items():
        extra.extend(["--label", f"{k}={v}"])

    # Override entrypoint to keep container alive.
    extra.extend(["--entrypoint", "sleep"])

    opts = RunOptions(
        name=name,
        remove=False,
        env=env or {},
        mounts=mounts,
        network=network,
        extra_args=extra,
    )

    result = rt.run(image, command=["infinity"], options=opts, text=True, capture_output=True)
    if result.returncode != 0:
        raise DockerError(result.returncode, result.stderr or "")

    return name or (result.stdout or "").strip()[:12]


def list_sandboxes() -> list[SandboxRow]:
    """List sandboxer-managed containers."""
    rt = get_runtime()

    if rt.name == "docker":
        return _list_sandboxes_docker()
    return _list_sandboxes_apple()


def _list_sandboxes_docker() -> list[SandboxRow]:
    """List sandboxer containers via Docker CLI."""
    result = _run_cmd(
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


def _list_sandboxes_apple() -> list[SandboxRow]:
    """List sandboxer containers via Apple Containers CLI."""
    rt = get_runtime()
    cmd = rt.build_list_command(all=True, format="json")
    result = subprocess.run(cmd, text=True, capture_output=True)
    if result.returncode != 0:
        return []

    try:
        containers = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        return []

    rows: list[SandboxRow] = []
    for c in containers:
        config = c.get("configuration", {})
        labels = config.get("labels", {})
        if labels.get(LABEL_MANAGED) != "true":
            continue

        image_ref = ""
        image = config.get("image", {})
        if isinstance(image, dict):
            image_ref = image.get("reference", "")

        rows.append(SandboxRow(
            name=config.get("id", ""),
            status=c.get("status", ""),
            image=image_ref,
            agent=labels.get(LABEL_AGENT, ""),
            workspace=labels.get(LABEL_WORKSPACE, ""),
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
    rt = get_runtime()
    cmd = rt.build_exec_command(
        name,
        [command],
        interactive=True,
        tty=True,
        workdir=workdir,
        env=env,
    )
    subprocess.run(cmd)


def exec_command(
    name: str,
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    workdir: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Exec a non-interactive command inside a container."""
    rt = get_runtime()
    cmd = rt.build_exec_command(
        name,
        command,
        workdir=workdir,
        env=env,
    )
    result = subprocess.run(cmd, text=True, capture_output=True)
    if result.returncode != 0:
        raise DockerError(result.returncode, result.stderr or "")
    return result


def stop(name: str) -> None:
    rt = get_runtime()
    cmd = rt.build_stop_command(name)
    result = subprocess.run(cmd, text=True, capture_output=True)
    if result.returncode != 0:
        raise DockerError(result.returncode, result.stderr or "")


def remove(name: str) -> None:
    rt = get_runtime()
    cmd = rt.build_rm_command(name, force=True)
    result = subprocess.run(cmd, text=True, capture_output=True)
    if result.returncode != 0:
        raise DockerError(result.returncode, result.stderr or "")


def save_as_template(name: str, tag: str) -> None:
    _run_cmd(["commit", name, tag])


def sandbox_stats(name: str) -> dict[str, str]:
    """Return resource usage for a container."""
    result = _run_cmd(
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
    """Return True if a container runtime is available."""
    return containerkit.detect() is not None


def is_gvisor_available() -> bool:
    """Return True if the ``runsc`` (gVisor) runtime is available (Docker only)."""
    try:
        rt = get_runtime()
    except Exception:
        return False
    if rt.name != "docker":
        # gVisor is Docker-specific; Apple Container has its own isolation.
        return False
    try:
        result = subprocess.run(
            [rt.binary, "info", "--format", "{{json .Runtimes}}"],
            text=True, capture_output=True,
        )
        if result.returncode != 0:
            return False
        return "runsc" in (result.stdout or "")
    except FileNotFoundError:
        return False


# Backward compat alias.
is_sandbox_feature_available = is_gvisor_available
