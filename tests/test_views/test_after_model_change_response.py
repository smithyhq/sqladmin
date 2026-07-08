"""Tests for after_model_change response control and secret modal."""

from __future__ import annotations

from typing import Any, AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Column, Integer, String, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse

from sqladmin import Admin, ModelView, Secret
from tests.common import async_engine as engine

pytestmark = pytest.mark.anyio

Base = declarative_base()  # type: Any
session_maker = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

app = Starlette()
admin = Admin(app=app, engine=engine, templates_dir="tests/templates")


class Token(Base):
    __tablename__ = "test_tokens"

    id = Column(Integer, primary_key=True)
    name = Column(String(length=50))


class TokenAdmin(ModelView, model=Token):
    """Behaviour driven by the token name prefix."""

    async def after_model_change(
        self, data: dict, model: Any, is_created: bool, request: Request
    ) -> PlainTextResponse | None:
        if model.name.startswith("resp-"):
            action = "created" if is_created else "updated"
            return PlainTextResponse(f"custom-{action}-{model.name}")
        if model.name.startswith("bad-"):
            return "not a response"  # type: ignore[return-value]
        if model.name.startswith("secret-"):
            Secret.reveal_once(
                request, value=f"raw-{model.name}", title="Token created"
            )
        return None


admin.add_view(TokenAdmin)


@pytest.fixture
async def prepare_database() -> AsyncGenerator[None, None]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def client(prepare_database: Any) -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


async def test_create_none_return_redirects(client: AsyncClient) -> None:
    response = await client.post(
        "/admin/token/create",
        data={"name": "plain-token"},
        follow_redirects=False,
    )
    assert response.status_code == 302

    stmt = select(func.count(Token.id))
    async with session_maker() as s:
        result = await s.execute(stmt)
    assert result.scalar_one() == 1


async def test_edit_none_return_redirects(client: AsyncClient) -> None:
    async with session_maker() as session:
        session.add(Token(name="old"))
        await session.commit()

    response = await client.post(
        "/admin/token/edit/1",
        data={"name": "new"},
        follow_redirects=False,
    )
    assert response.status_code == 302


async def test_create_response_return(client: AsyncClient) -> None:
    response = await client.post(
        "/admin/token/create",
        data={"name": "resp-my-key"},
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert response.text == "custom-created-resp-my-key"

    stmt = select(func.count(Token.id))
    async with session_maker() as s:
        result = await s.execute(stmt)
    assert result.scalar_one() == 1


async def test_edit_response_return(client: AsyncClient) -> None:
    async with session_maker() as session:
        session.add(Token(name="resp-orig"))
        await session.commit()

    response = await client.post(
        "/admin/token/edit/1",
        data={"name": "resp-changed"},
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert response.text == "custom-updated-resp-changed"


async def test_invalid_return_type_raises(client: AsyncClient) -> None:
    response = await client.post(
        "/admin/token/create",
        data={"name": "bad-token"},
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "after_model_change must return" in response.text


async def test_create_secret_rerenders_with_modal(client: AsyncClient) -> None:
    response = await client.post(
        "/admin/token/create",
        data={"name": "secret-api-key"},
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert "modal-secret" in response.text
    assert "raw-secret-api-key" in response.text
    assert "Token created" in response.text

    stmt = select(func.count(Token.id))
    async with session_maker() as s:
        result = await s.execute(stmt)
    assert result.scalar_one() == 1


async def test_edit_secret_rerenders_with_modal(client: AsyncClient) -> None:
    async with session_maker() as session:
        session.add(Token(name="orig"))
        await session.commit()

    response = await client.post(
        "/admin/token/edit/1",
        data={"name": "secret-rotated"},
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert "modal-secret" in response.text
    assert "raw-secret-rotated" in response.text
