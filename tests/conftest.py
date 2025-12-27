import pytest

from server import ENVS_DIR, _create_env, _delete_env


@pytest.fixture
def test_env():
    env_id = "pytest-env"
    # Ensure clean start
    env_path = ENVS_DIR / env_id
    if env_path.exists():
        _delete_env(env_id)
    _create_env(env_id)
    yield env_id
    if env_path.exists():
        _delete_env(env_id)
