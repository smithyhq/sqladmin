from typing import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base, relationship
from starlette.applications import Starlette

from sqladmin import Admin, ModelView
from tests.common import async_engine as engine

pytestmark = pytest.mark.anyio

Base = declarative_base()
session_maker = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)

app = Starlette()
admin = Admin(app=app, engine=engine)


class Tag(Base):
    __tablename__ = "tags"
    id = Column(Integer, primary_key=True)
    name = Column(String(length=32))

    def __str__(self) -> str:
        return f"Tag {self.id}"


class Post(Base):
    __tablename__ = "posts"
    id = Column(Integer, primary_key=True)
    tag_id = Column(Integer, ForeignKey("tags.id"))
    tag = relationship("Tag")

    def __str__(self) -> str:
        return f"Post {self.id}"


class PostAdmin(ModelView, model=Post):
    form_ajax_refs = {
        "tag": {
            "fields": ("name",),
        }
    }


admin.add_view(PostAdmin)


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
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


async def test_edit_page_loads_without_selectinload(client: AsyncClient) -> None:
    async with session_maker() as s:
        for i in range(3):
            s.add(Tag(name=f"tag-{i}"))
        await s.commit()

    async with session_maker() as s:
        post = Post(tag_id=1)
        s.add(post)
        await s.commit()

    response = await client.get("/admin/post/edit/1")
    assert response.status_code == 200
    assert 'data-role="select2-ajax"' in response.text
    assert response.text.count("<option") < 10
