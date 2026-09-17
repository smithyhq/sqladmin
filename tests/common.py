import os
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine

test_database_uri_sync = os.environ.get(
    "TEST_DATABASE_URI_SYNC", "sqlite:///test.db?check_same_thread=False"
)
test_database_uri_async = os.environ.get(
    "TEST_DATABASE_URI_ASYNC",
    "sqlite+aiosqlite:///test.db",
)

sync_engine = create_engine(test_database_uri_sync)
async_engine = create_async_engine(test_database_uri_async)


class DummyData(dict):  # pragma: no cover
    def getlist(self, key: str) -> list[Any]:
        v = self[key]
        if not isinstance(v, (list, tuple)):
            v = [v]
        return v
