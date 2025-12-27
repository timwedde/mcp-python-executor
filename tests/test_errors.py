import shutil
import subprocess
from pathlib import Path

import pytest

from server import (
    ENVS_DIR,
    _create_env,
    _execute_python,
    _get_file_path,
    _install_packages,
    _list_packages,
    _read_file,
    _remove_packages,
    _write_file,
    get_env_path,
    get_safe_file_path,
    run_uv_command,
)


def test_get_env_path_invalid():
    with pytest.raises(ValueError, match="Invalid environment ID"):
        get_env_path("")
    with pytest.raises(ValueError, match="Invalid environment ID"):
        get_env_path("   ")


def test_get_safe_file_path_traversal():
    env_path = Path("/tmp/env")
    with pytest.raises(ValueError, match="Illegal filename"):
        get_safe_file_path(env_path, "../outside.txt")
    with pytest.raises(ValueError, match="Illegal filename"):
        get_safe_file_path(env_path, "/etc/passwd")


def test_create_env_already_exists():
    env_id = "already-exists"
    _create_env(env_id)
    try:
        res = _create_env(env_id)
        assert res["status"] == "already_exists"
    finally:
        shutil.rmtree(ENVS_DIR / env_id)


def test_read_file_not_found():
    env_id = "err-env"
    _create_env(env_id)
    try:
        with pytest.raises(FileNotFoundError, match="not found"):
            _read_file(env_id, "ghost.txt")
    finally:
        shutil.rmtree(ENVS_DIR / env_id)


def test_read_file_too_large():
    env_id = "large-env"
    _create_env(env_id)
    try:
        env_path = ENVS_DIR / env_id
        file_path = env_path / "large.bin"
        with open(file_path, "wb") as f:
            f.seek(11 * 1024 * 1024 - 1)
            f.write(b"\0")

        with pytest.raises(RuntimeError, match="too large"):
            _read_file(env_id, "large.bin")
    finally:
        shutil.rmtree(ENVS_DIR / env_id)


def test_get_file_path_not_found():
    env_id = "path-err-env"
    _create_env(env_id)
    try:
        with pytest.raises(RuntimeError, match="not found"):
            _get_file_path(env_id, "ghost.txt")
    finally:
        shutil.rmtree(ENVS_DIR / env_id)


def test_execute_python_no_file():
    env_id = "exec-err-env"
    _create_env(env_id)
    try:
        with pytest.raises(FileNotFoundError, match="not found"):
            _execute_python(env_id, filename="non-existent.py")
    finally:
        shutil.rmtree(ENVS_DIR / env_id)


def test_execute_python_failure():
    env_id = "fail-exec-env"
    _create_env(env_id)
    try:
        with pytest.raises(RuntimeError, match="Execution failed"):
            _execute_python(env_id, code="import sys; sys.exit(1)")
    finally:
        shutil.rmtree(ENVS_DIR / env_id)


def test_execute_python_add_package_failure():
    env_id = "pkg-fail-env"
    _create_env(env_id)
    try:
        with pytest.raises(RuntimeError, match="Failed to add packages"):
            _execute_python(env_id, code="print(1)", packages=["non-existent-package-name-12345"])
    finally:
        shutil.rmtree(ENVS_DIR / env_id)


def test_install_packages_failure():
    env_id = "inst-fail-env"
    _create_env(env_id)
    try:
        with pytest.raises(RuntimeError, match="Error installing packages"):
            _install_packages(env_id, ["non-existent-package-name-12345"])
    finally:
        shutil.rmtree(ENVS_DIR / env_id)


def test_remove_packages_failure():
    env_id = "rem-fail-env"
    _create_env(env_id)
    try:
        with pytest.raises(RuntimeError, match="Error removing packages"):
            _remove_packages(env_id, ["non-existent-package-name-12345"])
    finally:
        shutil.rmtree(ENVS_DIR / env_id)


def test_run_uv_command_timeout(monkeypatch):
    import subprocess

    from server import run_uv_command

    def mock_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 300)

    monkeypatch.setattr(subprocess, "run", mock_run)
    res = run_uv_command(["version"])
    assert res.returncode == 1
    assert "Error: Command timed out" in res.stderr


def test_create_env_init_failure_mocked(monkeypatch):
    import server
    from server import _create_env

    def mock_uv_command(args, cwd=None):
        if args[0] == "init":
            return subprocess.CompletedProcess(args, 1, "", "Mock init failure")
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(server, "run_uv_command", mock_uv_command)

    with pytest.raises(RuntimeError, match="Failed to initialize"):
        _create_env("mock-fail-env")


def test_create_env_add_failure(monkeypatch):
    import server
    from server import _create_env

    def mock_uv_command(args, cwd=None):
        if args[0] == "add":
            return subprocess.CompletedProcess(args, 1, "", "Mock add failure")
        return subprocess.CompletedProcess(args, 0, "mock stdout", "")

    monkeypatch.setattr(server, "run_uv_command", mock_uv_command)

    res = _create_env("mock-add-fail-env", packages=["reqs"])
    assert res["status"] == "created_with_warning"
    assert "Mock add failure" in res["warning"]
    shutil.rmtree(ENVS_DIR / "mock-add-fail-env")


def test_read_file_unicode_error_fallback(test_env):
    from server import _read_file

    env_path = ENVS_DIR / test_env
    file_path = env_path / "latin1.txt"
    # Create a file with non-utf8 content (latin-1)
    with open(file_path, "wb") as f:
        f.write(b"\xe9")  # 'é' in latin-1

    res = _read_file(test_env, "latin1.txt")
    assert isinstance(res, dict)
    assert res["content"] == "\xe9"


def test_list_packages_parse_error(monkeypatch):
    import server
    from server import _create_env

    env_id = "parse-fail-env"
    _create_env(env_id)
    try:

        def mock_uv_command(args, cwd=None):
            return subprocess.CompletedProcess(args, 0, "not a json", "")

        monkeypatch.setattr(server, "run_uv_command", mock_uv_command)
        with pytest.raises(RuntimeError, match="Failed to parse"):
            _list_packages(env_id)
    finally:
        shutil.rmtree(ENVS_DIR / env_id)


def test_list_packages_failure(monkeypatch):
    import server
    from server import _create_env

    env_id = "list-fail-env"
    _create_env(env_id)
    try:

        def mock_uv_command(args, cwd=None):
            return subprocess.CompletedProcess(args, 1, "", "pip list failed")

        monkeypatch.setattr(server, "run_uv_command", mock_uv_command)
        with pytest.raises(RuntimeError, match="Error listing packages"):
            _list_packages(env_id)
    finally:
        shutil.rmtree(ENVS_DIR / env_id)


def test_write_file_exception(monkeypatch):
    _create_env("write-fail-env")
    try:
        monkeypatch.setattr("server.get_safe_file_path", lambda x, y: 1 / 0)
        with pytest.raises(RuntimeError, match="Error writing file"):
            _write_file("write-fail-env", "test.txt", "data")
    finally:
        shutil.rmtree(ENVS_DIR / "write-fail-env")


def test_read_file_exception(monkeypatch):
    from server import _read_file

    _create_env("read-fail-env")
    try:
        monkeypatch.setattr("server.get_safe_file_path", lambda x, y: 1 / 0)
        with pytest.raises(RuntimeError, match="Error reading file"):
            _read_file("read-fail-env", "test.txt")
    finally:
        shutil.rmtree(ENVS_DIR / "read-fail-env")


def test_run_uv_command_exception(monkeypatch):
    def mock_run(*args, **kwargs):
        raise Exception("Mock error")

    monkeypatch.setattr(subprocess, "run", mock_run)
    res = run_uv_command(["version"])
    assert res.returncode == 1
    assert "Error: Mock error" in res.stderr


def test_list_envs_empty(monkeypatch):
    monkeypatch.setattr("server.ENVS_DIR", Path("/tmp/non-existent-mcp-envs"))
    from server import _list_envs

    res = _list_envs()
    assert res["environments"] == []


def test_delete_env_not_found():
    with pytest.raises(ValueError, match="not found"):
        from server import _delete_env

        _delete_env("non-existent-env")
