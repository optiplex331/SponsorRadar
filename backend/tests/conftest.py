from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from sponsor_radar import db

FIXTURES = Path(__file__).with_name("fixtures")


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def conn():
    url = os.environ.get("SPONSOR_RADAR_TEST_DATABASE_URL")
    if not url:
        pytest.skip("SPONSOR_RADAR_TEST_DATABASE_URL not set")
    with db.connect(url) as connection:
        connection.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
        connection.commit()
        db.migrate(connection)
        yield connection
