"""Tests for sandboxer.core.mount_allowlist."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from sandboxer.core.mount_allowlist import (
    add_to_allowlist,
    is_path_blocked,
    load_allowlist,
    remove_from_allowlist,
    save_allowlist,
    validate_mount,
)


class TestBlockedPatterns:
    def test_ssh_blocked(self) -> None:
        assert is_path_blocked("/home/user/.ssh") == ".ssh"

    def test_aws_blocked(self) -> None:
        assert is_path_blocked("/home/user/.aws") == ".aws"

    def test_docker_blocked(self) -> None:
        assert is_path_blocked("/home/user/.docker") == ".docker"

    def test_gnupg_blocked(self) -> None:
        assert is_path_blocked("/home/user/.gnupg") == ".gnupg"

    def test_gcloud_blocked(self) -> None:
        assert is_path_blocked("/home/user/.config/gcloud") == ".config/gcloud"

    def test_kube_blocked(self) -> None:
        assert is_path_blocked("/home/user/.kube") == ".kube"

    def test_nested_ssh_blocked(self) -> None:
        assert is_path_blocked("/home/user/.ssh/id_rsa") == ".ssh"

    def test_safe_path_not_blocked(self) -> None:
        assert is_path_blocked("/home/user/projects/myapp") is None

    def test_credential_file_blocked(self) -> None:
        assert is_path_blocked("/some/path/credentials.json") == "credentials.json"


class TestAllowlist:
    def test_save_and_load(self, tmp_path: Path) -> None:
        allowlist_file = tmp_path / "mount-allowlist.json"
        with patch("sandboxer.core.mount_allowlist._allowlist_path", return_value=allowlist_file):
            save_allowlist(["/home/user/projects", "/tmp/work"])
            result = load_allowlist()
            assert result == ["/home/user/projects", "/tmp/work"]

    def test_load_missing(self, tmp_path: Path) -> None:
        allowlist_file = tmp_path / "nonexistent.json"
        with patch("sandboxer.core.mount_allowlist._allowlist_path", return_value=allowlist_file):
            result = load_allowlist()
            assert result == []

    def test_add_to_allowlist(self, tmp_path: Path) -> None:
        allowlist_file = tmp_path / "mount-allowlist.json"
        with patch("sandboxer.core.mount_allowlist._allowlist_path", return_value=allowlist_file):
            # Use tmp_path itself as the path to add (it exists and resolves cleanly).
            result = add_to_allowlist(str(tmp_path))
            assert str(tmp_path) in result

            # Adding again should not duplicate.
            result2 = add_to_allowlist(str(tmp_path))
            assert result2.count(str(tmp_path)) == 1

    def test_remove_from_allowlist(self, tmp_path: Path) -> None:
        allowlist_file = tmp_path / "mount-allowlist.json"
        with patch("sandboxer.core.mount_allowlist._allowlist_path", return_value=allowlist_file):
            save_allowlist([str(tmp_path), "/other/path"])
            result = remove_from_allowlist(str(tmp_path))
            assert str(tmp_path) not in result
            assert "/other/path" in result


class TestValidateMount:
    def test_blocked_path(self) -> None:
        ok, reason = validate_mount("/home/user/.ssh")
        assert ok is False
        assert "blocked" in reason

    def test_nonexistent_path(self) -> None:
        ok, reason = validate_mount("/nonexistent/path/that/does/not/exist/12345")
        assert ok is False
        assert "does not exist" in reason

    def test_existing_path_no_allowlist(self, tmp_path: Path) -> None:
        allowlist_file = tmp_path / "mount-allowlist.json"
        with patch("sandboxer.core.mount_allowlist._allowlist_path", return_value=allowlist_file):
            ok, reason = validate_mount(str(tmp_path))
            assert ok is True

    def test_existing_path_in_allowlist(self, tmp_path: Path) -> None:
        allowlist_file = tmp_path / "mount-allowlist.json"
        with patch("sandboxer.core.mount_allowlist._allowlist_path", return_value=allowlist_file):
            save_allowlist([str(tmp_path)])
            ok, reason = validate_mount(str(tmp_path))
            assert ok is True

    def test_existing_path_not_in_allowlist(self, tmp_path: Path) -> None:
        allowlist_file = tmp_path / "mount-allowlist.json"
        with patch("sandboxer.core.mount_allowlist._allowlist_path", return_value=allowlist_file):
            save_allowlist(["/some/other/path"])
            ok, reason = validate_mount(str(tmp_path))
            assert ok is False
            assert "not in allowlist" in reason

    def test_subdirectory_of_allowed_path(self, tmp_path: Path) -> None:
        allowlist_file = tmp_path / "mount-allowlist.json"
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        with patch("sandboxer.core.mount_allowlist._allowlist_path", return_value=allowlist_file):
            save_allowlist([str(tmp_path)])
            ok, reason = validate_mount(str(subdir))
            assert ok is True
