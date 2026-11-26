# Its presence makes pytest add the project root to sys.path, so tests can import
# `services`, `ui` and `app`.
import pytest


@pytest.fixture(autouse=True)
def _ignore_the_real_env_file(monkeypatch, tmp_path):
    """Tests must never read the developer's real .env file (it may hold a real API key)."""
    from services import env_file

    monkeypatch.setattr(env_file, "DEFAULT_ENV_PATH", tmp_path / "no-such.env")
