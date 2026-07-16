import pytest


@pytest.fixture(scope="module")
def anyio_backend() -> tuple[str, dict]:
    return ("asyncio", {"debug": True})
