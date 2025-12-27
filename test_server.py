from server import (
    _create_env,
    _delete_env,
    _execute_python,
    _get_file_path,
    _list_envs,
    _list_files,
    _read_file,
    _write_file,
)


def test_new_flow():
    env_id = "test-env-flow"
    print(f"--- Testing New Flow for environment '{env_id}' ---")

    # 1. Create environment
    print("\n1. Creating environment...")
    res = _create_env(env_id, packages=["requests"])
    print(res)

    # 2. List Envs
    print("\n2. Listing envs...")
    print(_list_envs())

    # 3. Write a file
    print("\n3. Writing data.txt...")
    res = _write_file(env_id, "data.txt", "some sample data")
    print(res)

    # 3.5 Get file path
    print("\n3.5 Getting file path for data.txt...")
    res = _get_file_path(env_id, "data.txt")
    print(f"Absolute path: {res}")

    # 4. Write and execute code that reads that file
    print("\n4. Executing code to read data.txt...")
    code = """
import requests
with open('data.txt', 'r') as f:
    data = f.read()
print(f"Data from file: {data}")
print(f"Requests version: {requests.__version__}")
"""
    res = _execute_python(env_id, code=code, filename="read_test.py")
    print(f"Result:\n{res}")

    # 5. List files
    print("\n5. Listing files...")
    files = _list_files(env_id)
    print(f"Type: {type(files)}")
    print(files)

    # 6. Read file back
    print("\n6. Reading read_test.py content...")
    print(_read_file(env_id, "read_test.py"))

    # 7. Test failure without env_id
    print("\n7. Testing execution without existing environment (should fail)...")
    try:
        res = _execute_python("non-existent-env", code="print('fail')")
        print(res)
    except Exception as e:
        print(f"Caught expected error: {e}")

    # 8. Cleanup
    print("\n8. Deleting environment...")
    print(_delete_env(env_id))


if __name__ == "__main__":
    test_new_flow()
