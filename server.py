import base64
import json
import mimetypes
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from fastmcp import FastMCP
from mcp.types import ImageContent

# Initialize FastMCP server
mcp = FastMCP(
    "PythonExecutor",
    instructions="""
    You are an expert Python environment manager and code executor.

    ENVIRONMENT PERSISTENCE:
    - You MUST use exactly ONE `env_id` for the entire conversation.
    - DO NOT create multiple environment IDs.
    - DO NOT create a new environment for each request.
    - The server handles environment creation automatically on your first call.
    - Reuse your chosen `env_id` in all subsequent tool calls (execute_python, write_file, etc).

    FILE RETRIEVAL & DISPLAY:
    - Whenever code execution or file operations create or identify a file
      (especially images like .png, .jpg), you MUST call `read_file` to retrieve
      and show it to the user.
    - NEVER just print the absolute path to the user; they cannot see local files on your host.
    - If a tool result contains a file path, immediately follow up with `read_file`
      for that specific file.
    """,
)

# Define base directory for environments
BASE_DIR = Path.home() / ".mcp-python-executor"
ENVS_DIR = BASE_DIR / "envs"

# Ensure directories exist
ENVS_DIR.mkdir(parents=True, exist_ok=True)


def get_env_path(env_id: str) -> Path:
    """Get the absolute path for a specific environment."""
    safe_id = "".join(c for c in env_id if c.isalnum() or c in ("-", "_")).strip()
    if not safe_id:
        raise ValueError(f"Invalid environment ID: {env_id}")
    return ENVS_DIR / safe_id


def get_safe_file_path(env_path: Path, filename: str) -> Path:
    """Get a safe absolute path for a file within an environment."""
    # Prevent path traversal
    requested_path = (env_path / filename).resolve()
    if not str(requested_path).startswith(str(env_path.resolve())):
        raise ValueError(f"Illegal filename: {filename}")
    return requested_path


def run_uv_command(args: List[str], cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
    """Run a uv command and return the result."""
    # Clean environment to avoid leakage from the server's own virtualenv
    env = os.environ.copy()
    env.pop("VIRTUAL_ENV", None)
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)

    try:
        # Ensure uv is in the path
        result = subprocess.run(
            ["uv"] + args,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
        )
        return result
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            args=args,
            returncode=1,
            stdout="",
            stderr="Error: Command timed out after 300 seconds.",
        )
    except Exception as e:
        return subprocess.CompletedProcess(
            args=args, returncode=1, stdout="", stderr=f"Error: {str(e)}"
        )


def _ensure_env(env_id: str) -> Path:
    """Ensure an environment exists, initializing it if necessary."""
    env_path = get_env_path(env_id)
    if not env_path.exists():
        env_path.mkdir(parents=True, exist_ok=True)
        init_res = run_uv_command(["init", "--lib"], cwd=env_path)
        if init_res.returncode != 0:
            # Cleanup on failure
            shutil.rmtree(env_path)
            raise RuntimeError(f"Failed to initialize environment {env_id}:\n{init_res.stderr}")
    return env_path


def _execute_python(
    env_id: str,
    code: Optional[str] = None,
    filename: str = "main.py",
    packages: Optional[List[str]] = None,
) -> Dict[str, Any]:
    env_path = _ensure_env(env_id)

    if packages:
        add_res = run_uv_command(["add"] + packages, cwd=env_path)
        if add_res.returncode != 0:
            raise RuntimeError(f"Failed to add packages to environment {env_id}:\n{add_res.stderr}")

    file_path = get_safe_file_path(env_path, filename)

    if code:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(code)

    if not file_path.exists():
        raise FileNotFoundError(f"File '{filename}' not found in environment '{env_id}'.")

    run_res = run_uv_command(["run", str(file_path)], cwd=env_path)

    output_data = {
        "stdout": run_res.stdout,
        "stderr": run_res.stderr,
        "exit_code": run_res.returncode,
        "hint": (
            "If images or data files were generated, call "
            "read_file(env_id='...', filename='...') to show them."
        ),
    }

    if run_res.returncode != 0:
        raise RuntimeError(
            f"Execution failed with exit code {run_res.returncode}:\n{run_res.stderr}"
        )

    return output_data


def _write_file(env_id: str, filename: str, content: str) -> Dict[str, Any]:
    env_path = _ensure_env(env_id)

    try:
        file_path = get_safe_file_path(env_path, filename)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)
        return {
            "status": "success",
            "filename": filename,
            "bytes_written": len(content),
            "hint": (
                f"To show this file to the user, call "
                f"read_file(env_id='{env_id}', filename='{filename}')"
            ),
        }
    except Exception as e:
        if isinstance(e, RuntimeError):
            raise e
        raise RuntimeError(f"Error writing file: {str(e)}")


def _read_file(env_id: str, filename: str) -> Union[Dict[str, Any], ImageContent]:
    env_path = _ensure_env(env_id)

    try:
        file_path = get_safe_file_path(env_path, filename)
        if not file_path.exists():
            raise FileNotFoundError(f"File '{filename}' not found.")

        # Check file size (limit to 10MB)
        file_size = file_path.stat().st_size
        if file_size > 10 * 1024 * 1024:
            raise RuntimeError(
                f"File '{filename}' is too large ({file_size} bytes). Max size is 10MB."
            )

        mime_type, _ = mimetypes.guess_type(file_path)
        data = file_path.read_bytes()

        # Detection logic
        is_image = mime_type and mime_type.startswith("image/")

        # Binary check: look for null byte in first 1024 bytes
        is_binary = False
        if not is_image:
            chunk = data[:1024]
            if b"\0" in chunk:
                is_binary = True

        if is_image:
            b64_data = base64.b64encode(data).decode("utf-8")
            return ImageContent(type="image", data=b64_data, mimeType=mime_type or "image/png")

        if is_binary:
            b64_data = base64.b64encode(data).decode("utf-8")
            m_type = mime_type or "application/octet-stream"
            return {
                "filename": filename,
                "type": "binary",
                "mime_type": m_type,
                "content": b64_data,
            }

        # Assume text
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError:
            content = data.decode("latin-1")

        return {
            "filename": filename,
            "type": "text",
            "mime_type": mime_type or "text/plain",
            "content": content,
        }

    except Exception as e:
        if isinstance(e, (ValueError, FileNotFoundError, RuntimeError)):
            raise e
        raise RuntimeError(f"Error reading file: {str(e)}")


def _list_files(env_id: str) -> Dict[str, Any]:
    env_path = _ensure_env(env_id)

    files = []
    for p in env_path.rglob("*"):
        if ".venv" in p.parts or ".git" in p.parts:
            continue
        if p.is_file():
            files.append(str(p.relative_to(env_path)))

    # Sort by number of path components, then by path string
    files.sort(key=lambda p: (len(Path(p).parts), p))
    return {"env_id": env_id, "files": files}


def _install_packages(env_id: str, packages: List[str]) -> Dict[str, Any]:
    env_path = _ensure_env(env_id)

    res = run_uv_command(["add"] + packages, cwd=env_path)
    if res.returncode == 0:
        return {"status": "success", "env_id": env_id, "installed": packages}
    else:
        raise RuntimeError(f"Error installing packages:\n{res.stderr}")


def _remove_packages(env_id: str, packages: List[str]) -> Dict[str, Any]:
    env_path = _ensure_env(env_id)

    res = run_uv_command(["remove"] + packages, cwd=env_path)
    if res.returncode == 0:
        return {"status": "success", "env_id": env_id, "removed": packages}
    else:
        raise RuntimeError(f"Error removing packages:\n{res.stderr}")


def _list_packages(env_id: str) -> Dict[str, Any]:
    env_path = _ensure_env(env_id)

    res = run_uv_command(["pip", "list", "--format", "json"], cwd=env_path)
    if res.returncode == 0:
        try:
            packages = json.loads(res.stdout)
            return {"env_id": env_id, "packages": packages}
        except json.JSONDecodeError:
            raise RuntimeError("Failed to parse package list from uv.")
    else:
        raise RuntimeError(f"Error listing packages:\n{res.stderr}")


def _list_envs() -> Dict[str, Any]:
    if not ENVS_DIR.exists():
        return {"environments": []}

    envs = [d.name for d in ENVS_DIR.iterdir() if d.is_dir()]
    return {"environments": sorted(envs)}


def _delete_env(env_id: str) -> Dict[str, Any]:
    env_path = get_env_path(env_id)
    if env_path.exists() and env_path.is_dir():
        shutil.rmtree(env_path)
        return {"status": "deleted", "env_id": env_id}
    else:
        raise ValueError(f"Environment '{env_id}' not found.")


@mcp.resource("envs://list")
def list_envs_resource() -> str:
    """List all available persistent environments."""
    envs = _list_envs()
    return json.dumps(envs, indent=2)


# Register tools
@mcp.tool()
def execute_python(
    env_id: str,
    code: Optional[str] = None,
    filename: str = "main.py",
    packages: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Execute Python code in a persistent environment.
    If code is provided, it will be written to filename (default main.py) before execution.
    If images/files are generated, you MUST follow up with read_file to display them.
    """
    return _execute_python(env_id, code, filename, packages)


@mcp.tool()
def write_file(env_id: str, filename: str, content: str) -> Dict[str, Any]:
    """
    Write a file to an environment.
    After writing, you MUST use read_file to show the content to the user if needed.
    """
    return _write_file(env_id, filename, content)


@mcp.tool()
def read_file(env_id: str, filename: str) -> Union[Dict[str, Any], ImageContent]:
    """
    Read a file from an environment.
    Use this to show images, data, or code contents to the user.
    Returns structured data for text/binary files and ImageContent for images.
    """
    return _read_file(env_id, filename)


@mcp.tool()
def list_files(env_id: str) -> Dict[str, Any]:
    """
    List all files in an environment (excluding virtualenv).
    Use this to discover files that might need to be read via read_file.
    """
    return _list_files(env_id)


@mcp.tool()
def install_packages(env_id: str, packages: List[str]) -> Dict[str, Any]:
    """Install packages into a persistent environment."""
    return _install_packages(env_id, packages)


@mcp.tool()
def remove_packages(env_id: str, packages: List[str]) -> Dict[str, Any]:
    """Remove packages from a persistent environment."""
    return _remove_packages(env_id, packages)


@mcp.tool()
def list_packages(env_id: str) -> Dict[str, Any]:
    """List all installed packages in a persistent environment."""
    return _list_packages(env_id)


@mcp.tool()
def list_envs() -> Dict[str, Any]:
    """List all persistent environments."""
    return _list_envs()


@mcp.tool()
def delete_env(env_id: str) -> Dict[str, Any]:
    """Delete a persistent environment."""
    return _delete_env(env_id)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
