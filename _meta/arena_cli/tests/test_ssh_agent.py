"""Tests for the ssh-agent socket mapping in _meta/docker/lib."""

import os
import socket
import subprocess
from pathlib import Path

LIB = Path(__file__).resolve().parents[2] / "docker" / "lib"


def _listen(path: Path) -> socket.socket:
    path.parent.mkdir(parents=True, exist_ok=True)
    server = socket.socket(socket.AF_UNIX)
    server.bind(str(path))
    return server


def _arena_ssh_agent(tmp_path: Path, sock: str, agent_dir: str) -> subprocess.CompletedProcess[str]:
    env = {"PATH": os.environ["PATH"], "ARENA_WS_DIR": str(tmp_path), "HOST_UID": str(os.getuid()), "SSH_AUTH_SOCK": sock, "HOST_SSH_AGENT_DIR": agent_dir}
    return subprocess.run(["bash", "-c", 'source "$0" && arena_ssh_agent', str(LIB)], env=env, capture_output=True, text=True, check=False)


def test_socket_in_agent_dir_maps_to_container_mount(tmp_path: Path) -> None:
    with _listen(tmp_path / "agent" / "s.agent"):
        result = _arena_ssh_agent(tmp_path, str(tmp_path / "agent" / "s.agent"), str(tmp_path / "agent"))
    assert (result.returncode, result.stdout) == (0, "/run/ssh-agent/s.agent\n")


def test_symlinked_socket_maps_by_its_target(tmp_path: Path) -> None:
    with _listen(tmp_path / "agent" / "s.agent"):
        (tmp_path / "link.sock").symlink_to(tmp_path / "agent" / "s.agent")
        result = _arena_ssh_agent(tmp_path, str(tmp_path / "link.sock"), str(tmp_path / "agent"))
    assert (result.returncode, result.stdout) == (0, "/run/ssh-agent/s.agent\n")


def test_socket_outside_mounted_dirs_is_refused(tmp_path: Path) -> None:
    (tmp_path / "agent").mkdir()
    with _listen(tmp_path / "other" / "s.agent"):
        for agent_dir in (str(tmp_path / "agent"), ""):
            result = _arena_ssh_agent(tmp_path, str(tmp_path / "other" / "s.agent"), agent_dir)
            assert (result.returncode, result.stdout) == (1, "")


def test_missing_socket_and_regular_file_are_refused(tmp_path: Path) -> None:
    (tmp_path / "agent").mkdir()
    (tmp_path / "agent" / "config").write_text("")
    for sock in ("", str(tmp_path / "agent" / "gone"), str(tmp_path / "agent" / "config")):
        result = _arena_ssh_agent(tmp_path, sock, str(tmp_path / "agent"))
        assert (result.returncode, result.stdout) == (1, "")
