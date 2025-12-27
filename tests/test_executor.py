import base64

from mcp.types import ImageContent

from server import (
    ENVS_DIR,
    _create_env,
    _delete_env,
    _execute_python,
    _get_file_path,
    _install_packages,
    _list_envs,
    _list_files,
    _list_packages,
    _read_file,
    _remove_packages,
    _write_file,
)


def test_create_and_delete_env():
    env_id = "temp-test-env"
    res = _create_env(env_id)
    assert res["status"] == "created"
    assert env_id in _list_envs()["environments"]

    res = _delete_env(env_id)
    assert res["status"] == "deleted"
    assert env_id not in _list_envs()["environments"]


def test_write_and_read_file(test_env):
    filename = "test.txt"
    content = "hello pytest"
    res = _write_file(test_env, filename, content)
    assert res["status"] == "success"

    read_res = _read_file(test_env, filename)
    assert isinstance(read_res, dict)
    assert read_res["content"] == content


def test_list_packages(test_env):
    # Should have no external packages initially (besides stdlib and boilerplate)
    res = _list_packages(test_env)
    assert isinstance(res, dict)
    assert "packages" in res
    assert isinstance(res["packages"], list)


def test_list_files(test_env):
    _write_file(test_env, "a.txt", "a")
    _write_file(test_env, "sub/b.txt", "b")

    res = _list_files(test_env)
    files = res["files"]
    assert "a.txt" in files
    assert "sub/b.txt" in files
    # Check sorting (root first)
    assert files.index("a.txt") < files.index("sub/b.txt")


def test_execute_python(test_env):
    code = "print('hello from python')"
    res = _execute_python(test_env, code=code)
    assert "hello from python" in res["stdout"]


def test_execute_with_packages(test_env):
    # This might be slow as it installs a package
    code = "import requests; print(requests.__version__)"
    res = _execute_python(test_env, code=code, packages=["requests"])
    assert "2." in res["stdout"]  # Assuming a 2.x version of requests


def test_get_file_path(test_env):
    _write_file(test_env, "path_test.txt", "data")
    res = _get_file_path(test_env, "path_test.txt")
    path = res["absolute_path"]
    assert str(ENVS_DIR) in path
    assert "path_test.txt" in path


def test_install_and_remove_packages(test_env):
    res = _install_packages(test_env, ["beartype"])
    assert res["status"] == "success"
    assert "beartype" in res["installed"]

    res = _remove_packages(test_env, ["beartype"])
    assert res["status"] == "success"
    assert "beartype" in res["removed"]


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
    assert isinstance(res, dict)
    assert res["type"] == "binary"
    assert "content" in res


def test_lazy_initialization():
    env_id = "lazy-env"
    # Ensure it's clean
    if (ENVS_DIR / env_id).exists():
        _delete_env(env_id)

    res = _execute_python(env_id, code="print('lazy')")
    assert "lazy" in res["stdout"]
    assert (ENVS_DIR / env_id).exists()

    # Cleanup
    _delete_env(env_id)
