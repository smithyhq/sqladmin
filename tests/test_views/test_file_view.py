import io
import re
from pathlib import Path
from typing import Any, AsyncGenerator

import pytest
from fastapi_storages import FileSystemStorage, StorageFile
from fastapi_storages.integrations.sqlalchemy import FileType
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Column, Integer, String, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from starlette.applications import Starlette
from starlette.datastructures import UploadFile

from sqladmin import Admin, ModelView
from sqladmin.fields import FileField, file_display_formatter
from sqladmin.helpers import validate_servable_file_path
from tests.common import async_engine as engine

pytestmark = pytest.mark.anyio

Base = declarative_base()  # type: Any
session_maker = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

app = Starlette()
admin = Admin(app=app, engine=engine)

storage = FileSystemStorage(path=".uploads")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    file = Column(FileType(FileSystemStorage(".uploads")))


class Asset(Base):
    __tablename__ = "assets"

    id = Column(Integer, primary_key=True)
    url = Column(String, nullable=False)


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
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


class UserAdmin(ModelView, model=User):
    column_list = [User.id, User.file]
    form_overrides = {User.file: FileField}
    column_formatters = {User.file: file_display_formatter}
    column_formatters_detail = {User.file: file_display_formatter}


class AssetAdmin(ModelView, model=Asset):
    column_list = [Asset.id, Asset.url]
    column_formatters = {Asset.url: file_display_formatter}


admin.add_view(UserAdmin)
admin.add_view(AssetAdmin)


async def _query_user() -> Any:
    stmt = select(User).limit(1)
    async with session_maker() as s:
        result = await s.execute(stmt)
    return result.scalar_one()


async def test_detail_view(client: AsyncClient) -> None:
    async with session_maker() as session:
        user = User(file=UploadFile(filename="upload.txt", file=io.BytesIO(b"abc")))
        session.add(user)
        await session.commit()

    response = await client.get("/admin/user/details/1")

    user = await _query_user()

    assert response.status_code == 200
    assert isinstance(user.file, StorageFile) is True
    assert user.file.name == "upload.txt"
    assert Path(user.file.path).as_posix() == ".uploads/upload.txt"
    assert user.file.open().read() == b"abc"

    assert (
        '<span class="me-1"><i class="fa-solid fa-download"></i></span>'
        in response.text
    )
    assert '<a href="http://testserver/admin/user/1/file/preview/">' in response.text
    assert '<a href="http://testserver/admin/user/1/file/download/">' in response.text


async def test_list_view(client: AsyncClient) -> None:
    async with session_maker() as session:
        for _ in range(10):
            user = User(file=UploadFile(filename="upload.txt", file=io.BytesIO(b"abc")))
            session.add(user)
        await session.commit()

    response = await client.get("/admin/user/list")

    user = await _query_user()

    assert response.status_code == 200
    assert isinstance(user.file, StorageFile) is True
    assert user.file.name == "upload.txt"
    assert Path(user.file.path).as_posix() == ".uploads/upload.txt"
    assert user.file.open().read() == b"abc"

    pattern_span = re.compile(
        r'<span class="me-1"><i class="fa-solid fa-download"></i></span>'
    )
    pattern_a_preview = re.compile(
        r'<a href="http://testserver/admin/user/\d+/file/preview/">'
    )
    pattern_a_download = re.compile(
        r'<a href="http://testserver/admin/user/\d+/file/download/">'
    )

    count_span = len(pattern_span.findall(response.text))
    count_a_preview = len(pattern_a_preview.findall(response.text))
    count_a_download = len(pattern_a_download.findall(response.text))

    assert count_span == count_a_preview == count_a_download == 10


async def test_file_download(client: AsyncClient) -> None:
    async with session_maker() as session:
        user = User(file=UploadFile(filename="upload.txt", file=io.BytesIO(b"abc")))
        session.add(user)
        await session.commit()

    response = await client.get("/admin/user/1/file/download/")

    assert response.status_code == 200
    assert response.content == b"abc"


async def test_file_preview(client: AsyncClient) -> None:
    async with session_maker() as session:
        user = User(file=UploadFile(filename="upload.txt", file=io.BytesIO(b"abc")))
        session.add(user)
        await session.commit()

    response = await client.get("/admin/user/1/file/preview/")
    assert response.status_code == 200
    assert response.text == "abc"


async def test_file_download_forbidden_when_details_disabled(
    client: AsyncClient,
) -> None:
    class RestrictedUserAdmin(ModelView, model=User):
        can_view_details = False
        column_list = [User.id, User.file]

    local_app = Starlette()
    local_admin = Admin(app=local_app, engine=engine)
    local_admin.add_view(RestrictedUserAdmin)

    async with session_maker() as session:
        user = User(file=UploadFile(filename="upload.txt", file=io.BytesIO(b"abc")))
        session.add(user)
        await session.commit()

    transport = ASGITransport(app=local_app)
    async with AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as local_client:
        response = await local_client.get("/admin/user/1/file/download/")

    assert response.status_code == 403


async def test_file_download_unknown_column(client: AsyncClient) -> None:
    async with session_maker() as session:
        user = User(file=UploadFile(filename="upload.txt", file=io.BytesIO(b"abc")))
        session.add(user)
        await session.commit()

    response = await client.get("/admin/user/1/missing/download/")
    assert response.status_code == 404


async def test_cdn_url_list(client: AsyncClient) -> None:
    async with session_maker() as session:
        asset = Asset(url="https://cdn.example.com/image.png")
        session.add(asset)
        await session.commit()

    response = await client.get("/admin/asset/list")

    assert response.status_code == 200
    assert 'href="https://cdn.example.com/image.png"' in response.text
    assert 'target="_blank"' in response.text
    assert "file/download" not in response.text


async def test_cdn_url_download_not_served(client: AsyncClient) -> None:
    async with session_maker() as session:
        asset = Asset(url="https://cdn.example.com/image.png")
        session.add(asset)
        await session.commit()

    response = await client.get("/admin/asset/1/url/download/")
    assert response.status_code == 400


def test_validate_servable_file_path_allows_files_under_storage_root(
    tmp_path: Path,
) -> None:
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    allowed = storage_root / "allowed.txt"
    allowed.write_text("ok", encoding="utf-8")

    resolved = validate_servable_file_path(str(allowed), [storage_root])
    assert resolved == allowed.resolve()


def test_validate_servable_file_path_rejects_outside_storage_root(
    tmp_path: Path,
) -> None:
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("nope", encoding="utf-8")

    with pytest.raises(ValueError, match="File path not allowed"):
        validate_servable_file_path(str(outside), [storage_root])
