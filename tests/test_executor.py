import base64

import pytest
from mcp.types import ImageContent

from server import (
    ENVS_DIR,
    _create_env,
    _delete_env,
    _execute_python,
    _get_file_path,
    _list_envs,
    _list_files,
    _read_file,
    _write_file,
)


@pytest.fixture
def test_env():
    env_id = "pytest-env"
    # Ensure clean start
    _delete_env(env_id)
    _create_env(env_id)
    yield env_id
    _delete_env(env_id)


def test_create_and_delete_env():
    env_id = "temp-test-env"
    res = _create_env(env_id)
    assert "created successfully" in res
    assert env_id in _list_envs()

    res = _delete_env(env_id)
    assert "has been deleted" in res
    assert env_id not in _list_envs()


def test_write_and_read_file(test_env):
    filename = "test.txt"
    content = "hello pytest"
    res = _write_file(test_env, filename, content)
    assert "Successfully wrote" in res

    read_content = _read_file(test_env, filename)
    assert read_content == content


def test_list_files(test_env):
    _write_file(test_env, "a.txt", "a")
    _write_file(test_env, "sub/b.txt", "b")

    files = _list_files(test_env)
    assert isinstance(files, list)
    assert "a.txt" in files
    assert "sub/b.txt" in files
    # Check sorting (root first)
    assert files.index("a.txt") < files.index("sub/b.txt")


def test_execute_python(test_env):
    code = "print('hello from python')"
    res = _execute_python(test_env, code=code)
    assert "hello from python" in res


def test_execute_with_packages(test_env):
    # This might be slow as it installs a package
    code = "import requests; print(requests.__version__)"
    res = _execute_python(test_env, code=code, packages=["requests"])
    assert "2." in res  # Assuming a 2.x version of requests


def test_get_file_path(test_env):
    _write_file(test_env, "path_test.txt", "data")
    path = _get_file_path(test_env, "path_test.txt")
    assert str(ENVS_DIR) in path
    assert "path_test.txt" in path


def test_image_detection(test_env):
    # Create a tiny 1x1 transparent PNG
    png_data = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
    )
    env_path = ENVS_DIR / test_env
    with open(env_path / "test.png", "wb") as f:
        f.write(png_data)

    res = _read_file(test_env, "test.png")
    assert isinstance(res, ImageContent)
    assert res.mimeType == "image/png"


def test_binary_detection(test_env):
    env_path = ENVS_DIR / test_env
    with open(env_path / "test.bin", "wb") as f:
        f.write(b"\x00\x01\x02\x03")

    res = _read_file(test_env, "test.bin")
    assert isinstance(res, str)
    assert "Binary file" in res
    assert "Base64 content" in res


def test_non_existent_env_failure():
    with pytest.raises(ValueError, match="does not exist"):
        _execute_python("non-existent", code="print(1)")
