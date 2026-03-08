# Set env vars BEFORE importing any app modules so pydantic-settings picks them up
# (must precede all app.* imports)
import os
import tempfile

_TEST_DB_FILE = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TEST_DB_FILE.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB_FILE.name}"
os.environ.setdefault("VLLM_BASE_URL", "http://localhost:8001")
os.environ.setdefault("VLLM_MODEL_ID", "test-model")
os.environ.setdefault("SYSTEM_PROMPT", "You are a test assistant.")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import init_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    init_db()
    yield
    os.unlink(_TEST_DB_FILE.name)


@pytest.fixture
def client(setup_test_db):
    with TestClient(app) as c:
        yield c
