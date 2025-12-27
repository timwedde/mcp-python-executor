from server import _create_env, _execute_python, _read_file, _delete_env
import base64
from mcp.types import ImageContent


def test_binary_and_image():
    env_id = "test-binary-env"
    _create_env(env_id)

    try:
        # 1. Test Image
        print("\nTesting Image Detection...")
        # Create a tiny 1x1 transparent PNG
        png_data = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
        )
        with open(
            f"/Users/cobaltcore/.mcp-python-executor/envs/{env_id}/test.png", "wb"
        ) as f:
            f.write(png_data)

        res = _read_file(env_id, "test.png")
        if isinstance(res, ImageContent):
            print(f"Success: Detected as ImageContent ({res.mimeType})")
        else:
            print(f"Failure: Expected ImageContent, got {type(res)}")

        # 2. Test Binary (Non-Image)
        print("\nTesting Binary Detection...")
        with open(
            f"/Users/cobaltcore/.mcp-python-executor/envs/{env_id}/test.bin", "wb"
        ) as f:
            f.write(b"\x00\x01\x02\x03")

        res = _read_file(env_id, "test.bin")
        if isinstance(res, str) and "Binary file" in res:
            print(f"Success: Detected as Binary string")
        else:
            print(f"Failure: Expected binary string, got {type(res)}")

        # 3. Test Text
        print("\nTesting Text Detection...")
        res = _read_file(env_id, "pyproject.toml")
        if isinstance(res, str) and "[project]" in res:
            print("Success: Detected as Text string")
        else:
            print(f"Failure: Expected text string, got {type(res)}")

    finally:
        _delete_env(env_id)


if __name__ == "__main__":
    test_binary_and_image()
