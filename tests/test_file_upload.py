from pathlib import Path
from typing import Any, Generator

import pytest
from fastapi_storages import FileSystemStorage, StorageFile
from fastapi_storages.integrations.sqlalchemy import FileType
from sqlalchemy import Column, Integer, select
from sqlalchemy.orm import declarative_base, sessionmaker
from starlette.applications import Starlette
from starlette.testclient import TestClient

from sqladmin import Admin, ModelView
from tests.common import sync_engine as engine

Base = declarative_base()  # type: Any
session_maker = sessionmaker(bind=engine)

app = Starlette()
admin = Admin(app=app, engine=engine)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    file = Column(FileType(FileSystemStorage(".uploads")), nullable=False)
    optional_file = Column(FileType(FileSystemStorage(".uploads")), nullable=True)


@pytest.fixture
def prepare_database() -> Generator[None, None, None]:
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def client(prepare_database: Any) -> Generator[TestClient, None, None]:
    with TestClient(app=app, base_url="http://testserver") as c:
        yield c


class UserAdmin(ModelView, model=User): ...


admin.add_view(UserAdmin)


def _query_user() -> User:
    stmt = select(User).limit(1)
    with session_maker() as s:
        return s.scalar(stmt)


def test_create_form_fields(client: TestClient) -> None:
    response = client.get("/admin/user/create")

    assert response.status_code == 200
    assert (
        '<input class="form-control" id="file" name="file" required type="file">'
        in response.text
    )
    assert (
        '<input class="form-control" id="optional_file" name="optional_file" type="file">'  # noqa: E501
        in response.text
    )


def test_create_form_post(client: TestClient) -> None:
    files = {
        "file": ("file.txt", b"abc"),
        "optional_file": ("optional_file.txt", b"cdb"),
    }
    client.post("/admin/user/create", files=files)

    user = _query_user()

    assert isinstance(user.file, StorageFile) is True
    assert user.file.name == "file.txt"
    assert Path(user.file.path).as_posix() == ".uploads/file.txt"
    assert user.file.open().read() == b"abc"
    assert user.optional_file.name == "optional_file.txt"
    assert Path(user.optional_file.path).as_posix() == ".uploads/optional_file.txt"
    assert user.optional_file.open().read() == b"cdb"


def test_create_form_update(client: TestClient) -> None:
    files = {
        "file": ("file.txt", b"abc"),
        "optional_file": ("optional_file.txt", b"cdb"),
    }
    client.post("/admin/user/create", files=files)

    files = {
        "file": ("new_file.txt", b"xyz"),
        "optional_file": ("new_optional_file.txt", b"zyx"),
    }
    client.post("/admin/user/edit/1", files=files)

    user = _query_user()
    assert user.file.name == "new_file.txt"
    assert Path(user.file.path).as_posix() == ".uploads/new_file.txt"
    assert user.file.open().read() == b"xyz"
    assert user.optional_file.name == "new_optional_file.txt"
    assert Path(user.optional_file.path).as_posix() == ".uploads/new_optional_file.txt"
    assert user.optional_file.open().read() == b"zyx"

    files = {"file": ("file.txt", b"abc")}
    client.post(
        "/admin/user/edit/1", files=files, data={"optional_file_checkbox": "true"}
    )

    user = _query_user()
    assert user.file.name == "file.txt"
    assert Path(user.file.path).as_posix() == ".uploads/file.txt"
    assert user.file.open().read() == b"abc"
    assert user.optional_file is None


def test_get_form_update(client: TestClient) -> None:
    files = {
        "file": ("file.txt", b"abc"),
        "optional_file": ("optional_file.txt", b"cdb"),
    }
    client.post("/admin/user/create", files=files)
    response = client.get("/admin/user/edit/1")

    assert response.text.count("Currently:") == 2
    assert '<input class="form-check-input" type="checkbox"' in response.text
    assert (
        '<label class="form-check-label" for="optional_file_checkbox">Clear</label>'
        in response.text
    )

    files = {"file": ("file.txt", b"abc")}
    client.post("/admin/user/edit/1", files=files)
    response = client.get("/admin/user/edit/1")

    assert response.text.count("Currently:") == 1
    assert response.text.count("checkbox") == 0
