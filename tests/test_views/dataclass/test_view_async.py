from typing import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Integer, String, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    MappedAsDataclass,
    mapped_column,
)
from starlette.applications import Starlette

from sqladmin import Admin
from sqladmin.models import ModelView
from tests.common import async_engine as engine

pytestmark = pytest.mark.anyio
session_maker = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(MappedAsDataclass, DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False)
    name: Mapped[str] = mapped_column(String(length=16), init=True)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=True, init=False)


class UserAdmin(ModelView, model=User):
    column_list = ["name", "email"]
    column_labels = {"name": "Name", "email": "Email"}


app = Starlette()
admin = Admin(app=app, engine=engine)
admin.add_view(UserAdmin)


@pytest.fixture(autouse=True)
async def prepare_database() -> AsyncGenerator[None, None]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


async def test_async_create_dataclass(client: AsyncClient) -> None:
    await client.post("/admin/user/create", data={"name": "foo", "email": "bar"})
    stmt = select(func.count(User.id))
    async with session_maker() as s:
        result = await s.execute(stmt)
    assert result.scalar_one() == 1


async def test_update_dataclass(client: AsyncClient) -> None:
    async with session_maker() as session:
        user = User(name="John Doe")
        session.add(user)
        await session.commit()

    await client.post("/admin/user/edit/1", data={"name": "foo", "email": "bar"})

    stmt = select(User)
    async with session_maker() as s:
        result = await s.execute(stmt)
    user = result.scalar_one()
    assert user.name == "foo"
    assert user.email == "bar"
