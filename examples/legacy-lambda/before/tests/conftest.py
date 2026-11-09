import os
import tempfile

import pytest

_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DATABASE_DSN"] = f"sqlite:///{_db.name}"

from chalicelib import db  # noqa: E402


@pytest.fixture(autouse=True)
def database():
    db.metadata.drop_all(db.engine)
    db.metadata.create_all(db.engine)
    with db.engine.connect() as connection:
        connection.execute(db.orders.insert(), [
            {"sku": "A100", "quantity": 1, "status": "new"},
            {"sku": "B200", "quantity": 5, "status": "paid"},
            {"sku": "C300", "quantity": 2, "status": "paid"},
        ])
    yield
