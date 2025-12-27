import base64
import mimetypes
import os
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional, Union

from fastmcp import FastMCP
from mcp.types import ImageContent, TextContent

# Initialize FastMCP server
mcp = FastMCP("PythonExecutor")

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


def run_uv_command(
    args: List[str], cwd: Optional[Path] = None
) -> subprocess.CompletedProcess:
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


def _create_env(env_id: str, packages: Optional[List[str]] = None) -> str:
    env_path = get_env_path(env_id)
    if env_path.exists():
        return f"Environment '{env_id}' already exists at {env_path}."

    env_path.mkdir(parents=True, exist_ok=True)
    init_res = run_uv_command(["init", "--lib"], cwd=env_path)
    if init_res.returncode != 0:
        # Cleanup on failure
        shutil.rmtree(env_path)
        raise RuntimeError(
            f"Failed to initialize environment {env_id}:\n{init_res.stderr}"
        )

    if packages:
        add_res = run_uv_command(["add"] + packages, cwd=env_path)
        if add_res.returncode != 0:
            return f"Environment created, but failed to add packages:\n{add_res.stderr}"

    return f"Environment '{env_id}' created successfully."


def _execute_python(
    env_id: str,
    code: Optional[str] = None,
    filename: str = "main.py",
    packages: Optional[List[str]] = None,
) -> str:
    env_path = get_env_path(env_id)
    if not env_path.exists():
        raise ValueError(
            f"Environment '{env_id}' does not exist. Please create it first using create_env."
        )

    if packages:
        add_res = run_uv_command(["add"] + packages, cwd=env_path)
        if add_res.returncode != 0:
            raise RuntimeError(
                f"Failed to add packages to environment {env_id}:\n{add_res.stderr}"
            )

    file_path = get_safe_file_path(env_path, filename)

    if code:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(code)

    if not file_path.exists():
        raise FileNotFoundError(
            f"File '{filename}' not found in environment '{env_id}'."
        )

    run_res = run_uv_command(["run", str(file_path)], cwd=env_path)

    combined_output = []
    if run_res.stdout:
        combined_output.append(run_res.stdout)
    if run_res.stderr:
        combined_output.append(run_res.stderr)

    output_text = (
        "\n".join(combined_output)
        if combined_output
        else "Code executed successfully with no output."
    )

    if run_res.returncode != 0:
        raise RuntimeError(
            f"Execution failed with exit code {run_res.returncode}:\n{output_text}"
        )

    return output_text


def _write_file(env_id: str, filename: str, content: str) -> str:
    env_path = get_env_path(env_id)
    if not env_path.exists():
        raise ValueError(f"Environment '{env_id}' does not exist.")

    try:
        file_path = get_safe_file_path(env_path, filename)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)
        return f"Successfully wrote to '{filename}' in environment '{env_id}'."
    except Exception as e:
        raise RuntimeError(f"Error writing file: {str(e)}")


def _read_file(env_id: str, filename: str) -> Union[str, ImageContent]:
    env_path = get_env_path(env_id)
    if not env_path.exists():
        raise ValueError(f"Environment '{env_id}' does not exist.")

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
            return ImageContent(
                type="image", data=b64_data, mimeType=mime_type or "image/png"
            )

        if is_binary:
            b64_data = base64.b64encode(data).decode("utf-8")
            return f"Binary file ({mime_type or 'application/octet-stream'}). Base64 content:\n{b64_data}"

        # Assume text
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            # Fallback to latin-1
            return data.decode("latin-1")

    except Exception as e:
        if isinstance(e, (ValueError, FileNotFoundError, RuntimeError)):
            raise e
        raise RuntimeError(f"Error reading file: {str(e)}")


def _list_files(env_id: str) -> List[str]:
    env_path = get_env_path(env_id)
    if not env_path.exists():
        raise ValueError(f"Environment '{env_id}' does not exist.")

    files = []
    for p in env_path.rglob("*"):
        if ".venv" in p.parts or ".git" in p.parts:
            continue
        if p.is_file():
            files.append(str(p.relative_to(env_path)))

    if not files:
        return []

    # Sort by number of path components, then by path string
    files.sort(key=lambda p: (len(Path(p).parts), p))
    return files


def _get_file_path(env_id: str, filename: str) -> str:
    env_path = get_env_path(env_id)
    if not env_path.exists():
        raise ValueError(f"Environment '{env_id}' does not exist.")

    try:
        file_path = get_safe_file_path(env_path, filename)
        if not file_path.exists():
            raise FileNotFoundError(f"File '{filename}' not found.")
        return str(file_path.absolute())
    except Exception as e:
        raise RuntimeError(f"Error getting file path: {str(e)}")


def _install_packages(env_id: str, packages: List[str]) -> str:
    env_path = get_env_path(env_id)
    if not env_path.exists():
        raise ValueError(f"Environment '{env_id}' does not exist.")

    res = run_uv_command(["add"] + packages, cwd=env_path)
    if res.returncode == 0:
        return (
            f"Successfully installed {', '.join(packages)} in environment '{env_id}'."
        )
    else:
        raise RuntimeError(f"Error installing packages:\n{res.stderr}")


def _remove_packages(env_id: str, packages: List[str]) -> str:
    env_path = get_env_path(env_id)
    if not env_path.exists():
        raise ValueError(f"Environment '{env_id}' does not exist.")

    res = run_uv_command(["remove"] + packages, cwd=env_path)
    if res.returncode == 0:
        return (
            f"Successfully removed {', '.join(packages)} from environment '{env_id}'."
        )
    else:
        raise RuntimeError(f"Error removing packages:\n{res.stderr}")


def _list_packages(env_id: str) -> str:
    env_path = get_env_path(env_id)
    if not env_path.exists():
        return f"Environment '{env_id}' does not exist."

    res = run_uv_command(["pip", "list"], cwd=env_path)
    if res.returncode == 0:
        return f"Packages in '{env_id}':\n{res.stdout}"
    else:
        return f"Error listing packages:\n{res.stderr}"


def _list_envs() -> str:
    if not ENVS_DIR.exists():
        return "No environments found."

    envs = [d.name for d in ENVS_DIR.iterdir() if d.is_dir()]
    if not envs:
        return "No environments found."

    return "Persistent environments:\n" + "\n".join(f"- {e}" for e in envs)


def _delete_env(env_id: str) -> str:
    env_path = get_env_path(env_id)
    if env_path.exists() and env_path.is_dir():
        shutil.rmtree(env_path)
        return f"Environment '{env_id}' has been deleted."
    else:
        return f"Environment '{env_id}' not found."


# Register tools
@mcp.tool()
def create_env(env_id: str, packages: Optional[List[str]] = None) -> str:
    """Create a new persistent Python environment."""
    return _create_env(env_id, packages)


@mcp.tool()
def execute_python(
    env_id: str,
    code: Optional[str] = None,
    filename: str = "main.py",
    packages: Optional[List[str]] = None,
) -> str:
    """
    Execute Python code in a persistent environment.
    If code is provided, it will be written to filename (default main.py) before execution.
    Environment must be created first.
    """
    return _execute_python(env_id, code, filename, packages)


@mcp.tool()
def write_file(env_id: str, filename: str, content: str) -> str:
    """Write a file to an environment."""
    return _write_file(env_id, filename, content)


@mcp.tool()
def read_file(env_id: str, filename: str) -> Union[str, ImageContent]:
    """
    Read a file from an environment.
    Returns text content for text files and ImageContent for images.
    Binary files are returned as a Base64 string.
    """
    return _read_file(env_id, filename)


@mcp.tool()
def list_files(env_id: str) -> List[str]:
    """
    List all files in an environment (excluding virtualenv).
    Returns a JSON array of relative paths sorted by depth and name.
    """
    return _list_files(env_id)


@mcp.tool()
def get_file_path(env_id: str, filename: str) -> str:
    """Get the absolute path to a requested file in an environment."""
    return _get_file_path(env_id, filename)


@mcp.tool()
def install_packages(env_id: str, packages: List[str]) -> str:
    """Install packages into a persistent environment."""
    return _install_packages(env_id, packages)


@mcp.tool()
def remove_packages(env_id: str, packages: List[str]) -> str:
    """Remove packages from a persistent environment."""
    return _remove_packages(env_id, packages)


@mcp.tool()
def list_packages(env_id: str) -> str:
    """List all installed packages in a persistent environment."""
    return _list_packages(env_id)


@mcp.tool()
def list_envs() -> str:
    """List all persistent environments."""
    return _list_envs()


@mcp.tool()
def delete_env(env_id: str) -> str:
    """Delete a persistent environment."""
    return _delete_env(env_id)


if __name__ == "__main__":
    mcp.run()
