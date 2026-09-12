import pytest
from fastapi.testclient import TestClient

from failurelab.api import create_app
from failurelab.config import Settings
from failurelab.store import Store


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path, seed_demo=False, worker_enabled=False, _env_file=None)


@pytest.fixture
def store(settings):
    instance = Store(settings)
    yield instance
    instance.close()


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as instance:
        yield instance
