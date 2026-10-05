"""Isolate each test database; never remove a shared /tmp database."""

from pathlib import Path

import pytest
from src.database import db


@pytest.fixture(autouse=True)
def isolated_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(db, "db_path", str(tmp_path / "payments.sqlite"))
    db._init_db()
