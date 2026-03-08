import os

# Set env vars BEFORE importing any app modules so pydantic-settings picks them up
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_local_chat.db")
os.environ.setdefault("VLLM_BASE_URL", "http://localhost:8001")
os.environ.setdefault("VLLM_MODEL_ID", "test-model")
os.environ.setdefault("SYSTEM_PROMPT", "You are a test assistant.")

import pytest
from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    init_db()
    yield
    # Cleanup test DB file
    db_path = "./test_local_chat.db"
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture
def client(setup_test_db):
    with TestClient(app) as c:
        yield c
