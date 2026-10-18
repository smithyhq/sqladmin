import io
import logging
import os
import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import Any, BinaryIO

import pytest
from fastapi_storages import FileSystemStorage, StorageFile
from fastapi_storages.integrations.sqlalchemy import FileType, ImageType
from PIL import Image, UnidentifiedImageError
from sqlalchemy import Column, Integer, select
from sqlalchemy.orm import declarative_base, sessionmaker
from starlette.applications import Starlette
from starlette.testclient import TestClient
from wtforms.validators import ValidationError

from sqladmin import Admin, ModelView
from sqladmin.fields import FileField
from tests.common import multipart
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


class OpenlessStorage(FileSystemStorage):
    """Has no `open()`, like `S3Storage` in fastapi-storages."""

    def open(self, name: str) -> BinaryIO:
        raise NotImplementedError()


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True)
    image = Column(ImageType(FileSystemStorage(".uploads")), nullable=False)
    remote_file = Column(FileType(OpenlessStorage(".uploads")), nullable=False)


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True)
    file = Column(
        FileType(FileSystemStorage(".uploads"), upload_to="docs"), nullable=False
    )


@pytest.fixture(autouse=True)
def prepare_database() -> Generator[None, None, None]:
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app=app, base_url="http://testserver") as c:
        yield c


@pytest.fixture
def opened_files(monkeypatch: pytest.MonkeyPatch) -> list[BinaryIO]:
    """The handles `FileSystemStorage.open` returns during the test."""

    handles: list[BinaryIO] = []
    storage_open = FileSystemStorage.open

    def record_open(self: FileSystemStorage, name: str) -> BinaryIO:
        handles.append(storage_open(self, name))
        return handles[-1]

    monkeypatch.setattr(FileSystemStorage, "open", record_open)
    return handles


class UserAdmin(ModelView, model=User):
    form_overrides = {User.file: FileField, User.optional_file: FileField}


class DocumentAdmin(ModelView, model=Document):
    pass


class ReportAdmin(ModelView, model=Report):
    form_overrides = {Report.file: FileField}
    save_as = True


admin.add_view(UserAdmin)
admin.add_view(DocumentAdmin)
admin.add_view(ReportAdmin)


# Larger than one read buffer, so a rewrite of a file onto itself shows.
CONTENT = b"a" * 100_000


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


def _create_user(client: TestClient) -> None:
    files = {
        "file": ("file.txt", CONTENT),
        "optional_file": ("optional_file.txt", CONTENT),
    }
    client.post("/admin/user/create", files=files)


def test_update_without_new_file_keeps_existing_content(client: TestClient) -> None:
    _create_user(client)

    response = client.post(
        "/admin/user/edit/1",
        **multipart(("file", "", b""), ("optional_file", "", b"")),
        follow_redirects=False,
    )
    assert response.status_code == 302

    user = _query_user()
    assert user.file.name == "file.txt"
    assert user.file.open().read() == CONTENT
    assert user.optional_file.name == "optional_file.txt"
    assert user.optional_file.open().read() == CONTENT


@pytest.mark.parametrize(
    ("expected", "status_code"),
    [(CONTENT, 302), (b"other", 400)],
    ids=["valid", "invalid"],
)
def test_update_without_new_file_validates_stored_content(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    opened_files: list[BinaryIO],
    expected: bytes,
    status_code: int,
) -> None:
    _create_user(client)

    def validate_content(form: Any, field: Any) -> None:
        assert field.data.filename == "file.txt"
        file = field.data.file
        # What a validator could use on the handle the storage opens.
        assert file.readable() and file.seekable()
        assert Path(file.name).name == "file.txt"
        assert os.fstat(file.fileno()).st_size == len(CONTENT)
        if file.read() != expected:
            raise ValidationError("Unexpected content.")

    monkeypatch.setattr(
        UserAdmin, "form_args", {"file": {"validators": [validate_content]}}
    )
    response = client.post(
        "/admin/user/edit/1",
        **multipart(("file", "", b""), ("optional_file", "", b"")),
        follow_redirects=False,
    )
    assert response.status_code == status_code
    # Only the file the validator read was opened, and it is closed.
    assert len(opened_files) == 1
    assert opened_files[0].closed

    user = _query_user()
    assert user.file.open().read() == CONTENT
    assert user.optional_file.open().read() == CONTENT


def test_update_clear_with_empty_input(client: TestClient) -> None:
    _create_user(client)

    response = client.post(
        "/admin/user/edit/1",
        **multipart(
            ("file", "", b""),
            ("optional_file", "", b""),
            ("optional_file_checkbox", None, b"on"),
        ),
        follow_redirects=False,
    )
    assert response.status_code == 302

    user = _query_user()
    assert user.file.open().read() == CONTENT
    assert user.optional_file is None


def test_update_with_new_file_keeps_untouched_one(client: TestClient) -> None:
    _create_user(client)

    response = client.post(
        "/admin/user/edit/1",
        **multipart(("file", "new_file.txt", b"xyz"), ("optional_file", "", b"")),
        follow_redirects=False,
    )
    assert response.status_code == 302

    user = _query_user()
    assert user.file.name == "new_file.txt"
    assert user.file.open().read() == b"xyz"
    assert user.optional_file.name == "optional_file.txt"
    assert user.optional_file.open().read() == CONTENT


def test_save_as_new_without_new_file_keeps_existing_content(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(UserAdmin, "save_as", True)
    _create_user(client)

    response = client.post(
        "/admin/user/edit/1",
        **multipart(
            ("file", "", b""),
            ("optional_file", "", b""),
            ("save", None, b"Save as new"),
        ),
        follow_redirects=False,
    )
    assert response.status_code == 302

    with session_maker() as s:
        original, new = s.scalars(select(User).order_by(User.id)).all()
    assert original.file.name == "file.txt"
    assert original.optional_file.name == "optional_file.txt"
    assert new.file.name != original.file.name
    assert new.optional_file.name != original.optional_file.name
    for user in (original, new):
        assert user.file.open().read() == CONTENT
        assert user.optional_file.open().read() == CONTENT

    # Each row has its own file: replacing one, under its own name, leaves the
    # other as is.
    client.post(
        "/admin/user/edit/1",
        **multipart(("file", "file.txt", b"xyz"), ("optional_file", "", b"")),
    )
    assert Path(original.file.path).read_bytes() == b"xyz"
    assert Path(new.file.path).read_bytes() == CONTENT

    client.post(
        "/admin/user/edit/2",
        **multipart(("file", new.file.name, b"zyx"), ("optional_file", "", b"")),
    )
    assert Path(new.file.path).read_bytes() == b"zyx"
    assert Path(original.file.path).read_bytes() == b"xyz"


def test_save_as_new_copy_stays_in_the_upload_to_directory(
    client: TestClient,
) -> None:
    client.post("/admin/report/create", files={"file": ("file.txt", CONTENT)})
    names_before = set(os.listdir(".uploads/docs"))

    response = client.post(
        "/admin/report/edit/1",
        **multipart(("file", "", b""), ("save", None, b"Save as new")),
        follow_redirects=False,
    )
    assert response.status_code == 302

    with session_maker() as s:
        original, new = s.scalars(select(Report).order_by(Report.id)).all()
    assert original.file.name == "docs/file.txt"
    # The column adds `docs/` again on write: the copy is not under docs/docs/,
    # and takes a name no file had before.
    assert Path(new.file.name).parent == Path("docs")
    assert Path(new.file.name).name not in names_before
    assert Path(new.file.path).read_bytes() == CONTENT
    assert Path(original.file.path).read_bytes() == CONTENT


def test_save_as_new_asks_for_a_new_upload_when_the_copy_cannot_be_named(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    opened_files: list[BinaryIO],
) -> None:
    monkeypatch.setattr(UserAdmin, "save_as", True)
    _create_user(client)

    def generate_new_filename(self: FileSystemStorage, filename: str) -> str:
        raise NotImplementedError()

    monkeypatch.setattr(
        FileSystemStorage, "generate_new_filename", generate_new_filename
    )
    response = client.post(
        "/admin/user/edit/1",
        **multipart(
            ("file", "", b""),
            ("optional_file", "", b""),
            ("save", None, b"Save as new"),
        ),
    )
    assert response.status_code == 400
    assert "Save as new needs a new upload for file" in response.text
    assert opened_files
    assert all(handle.closed for handle in opened_files)
    with session_maker() as s:
        assert [user.id for user in s.scalars(select(User))] == [1]


def test_save_as_new_closes_the_copy_when_insert_fails(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(UserAdmin, "save_as", True)
    _create_user(client)

    received: dict[str, Any] = {}

    async def insert_model(self: UserAdmin, request: Any, data: dict) -> Any:
        received.update(data)
        raise ValueError("insert failed")

    monkeypatch.setattr(UserAdmin, "insert_model", insert_model)
    response = client.post(
        "/admin/user/edit/1",
        **multipart(
            ("file", "", b""),
            ("optional_file", "", b""),
            ("save", None, b"Save as new"),
        ),
    )
    assert response.status_code == 400
    assert received["file"].file.closed
    assert received["optional_file"].file.closed


def test_save_as_new_closes_the_copy_when_copying_fails(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(UserAdmin, "save_as", True)
    _create_user(client)

    copies: list[Any] = []
    spooled = tempfile.SpooledTemporaryFile

    def spooled_temporary_file(*args: Any, **kwargs: Any) -> Any:
        copies.append(spooled(*args, **kwargs))
        return copies[-1]

    def copyfileobj(*args: Any) -> None:
        raise OSError("read failed")

    monkeypatch.setattr(
        "sqladmin.application.tempfile.SpooledTemporaryFile", spooled_temporary_file
    )
    monkeypatch.setattr("sqladmin.application.shutil.copyfileobj", copyfileobj)
    response = client.post(
        "/admin/user/edit/1",
        **multipart(
            ("file", "", b""),
            ("optional_file", "", b""),
            ("save", None, b"Save as new"),
        ),
    )
    assert response.status_code == 400
    assert copies
    assert all(copy.closed for copy in copies)


def _create_document(client: TestClient) -> bytes:
    image = io.BytesIO()
    Image.frombytes("L", (256, 256), os.urandom(256 * 256)).save(image, "PNG")
    files = {
        "image": ("image.png", image.getvalue()),
        "remote_file": ("remote_file.txt", CONTENT),
    }
    client.post("/admin/document/create", files=files)
    return image.getvalue()


def test_update_document_without_new_files(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    image = _create_document(client)

    def validate_image(form: Any, field: Any) -> None:
        try:
            with Image.open(field.data.file) as stored:
                stored.verify()
        except UnidentifiedImageError:
            raise ValidationError("Not an image.")

    # Only a stored file a validator reads is opened, so a storage without
    # `open()` works when no validator reads its file.
    monkeypatch.setattr(
        DocumentAdmin, "form_args", {"image": {"validators": [validate_image]}}
    )
    response = client.post(
        "/admin/document/edit/1",
        **multipart(("image", "", b""), ("remote_file", "", b"")),
        follow_redirects=False,
    )
    assert response.status_code == 302

    with session_maker() as s:
        document = s.scalar(select(Document))
    assert Path(document.image.path).read_bytes() == image
    assert Path(document.remote_file.path).read_bytes() == CONTENT


def test_update_document_asks_for_a_new_upload_when_a_validator_reads_it(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create_document(client)

    def validate_content(form: Any, field: Any) -> None:
        field.data.file.read()

    monkeypatch.setattr(
        DocumentAdmin,
        "form_args",
        {"remote_file": {"validators": [validate_content]}},
    )
    response = client.post(
        "/admin/document/edit/1",
        **multipart(("image", "", b""), ("remote_file", "", b"")),
    )
    assert response.status_code == 400
    assert "its storage cannot read the stored file" in response.text

    with session_maker() as s:
        document = s.scalar(select(Document))
    assert Path(document.remote_file.path).read_bytes() == CONTENT


def test_save_as_new_document_asks_for_a_new_upload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(DocumentAdmin, "save_as", True)
    _create_document(client)

    caplog.set_level(logging.INFO, logger="sqladmin.application")
    response = client.post(
        "/admin/document/edit/1",
        **multipart(
            ("image", "", b""),
            ("remote_file", "", b""),
            ("save", None, b"Save as new"),
        ),
    )
    assert response.status_code == 400
    assert "Save as new needs a new upload for remote_file" in response.text
    # An expected answer to the user: logged without a stack trace.
    [record] = [r for r in caplog.records if r.name == "sqladmin.application"]
    assert record.levelno == logging.INFO
    assert record.exc_info is None
    with session_maker() as s:
        assert [document.id for document in s.scalars(select(Document))] == [1]
