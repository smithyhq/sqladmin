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


def multipart(*parts: tuple[str, str | None, bytes]) -> dict[str, Any]:
    """
    Request kwargs for a multipart body built by hand, since httpx drops the
    empty filename a browser sends for a file input left untouched.
    A part whose filename is None is a plain field.
    """

    boundary = "sqladmin-boundary"
    body = b""
    for name, filename, content in parts:
        headers = f'Content-Disposition: form-data; name="{name}"'
        if filename is not None:
            headers += f'; filename="{filename}"\r\n'
            headers += "Content-Type: application/octet-stream"
        body += f"--{boundary}\r\n{headers}\r\n\r\n".encode() + content + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return {
        "content": body,
        "headers": {"Content-Type": f"multipart/form-data; boundary={boundary}"},
    }
