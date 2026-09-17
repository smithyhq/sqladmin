import datetime
import enum
import uuid
from collections.abc import Generator

import pytest
from markupsafe import Markup
from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from starlette.applications import Starlette
from starlette.testclient import TestClient

from sqladmin import Admin, ModelView
from sqladmin._types import StrEnum
from sqladmin.formatters import (
    BASE_FORMATTERS,
    copy_to_clipboard_formatter,
    datetime_formatter,
    str_enum_formatter,
)
from tests.common import sync_engine as engine

# Try to import UUID type for SQLAlchemy 2.0+
try:
    from sqlalchemy import Uuid

    HAS_UUID_SUPPORT = True
except ImportError:
    HAS_UUID_SUPPORT = False
    Uuid = None

pytestmark = pytest.mark.anyio

Base = declarative_base()  # type: ignore
session_maker = sessionmaker(bind=engine)

app = Starlette()
admin = Admin(app=app, session_maker=session_maker)


@pytest.fixture(autouse=True)
def prepare_database() -> Generator[None, None, None]:
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app=app, base_url="http://testserver") as c:
        yield c


class Status(enum.Enum):
    ACTIVE = "ACTIVE"
    DEACTIVE = "DEACTIVE"


class Role(StrEnum):
    ADMIN = "ADMIN"
    USER = "USER"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(String)
    role = Column(Enum(Role))
    registered_at = Column(DateTime)

    profile = relationship("Profile", back_populates="user", uselist=False)

    if HAS_UUID_SUPPORT:
        user_uuid = Column(Uuid, nullable=True)


class Profile(Base):
    __tablename__ = "profiles"

    id = Column(Integer, primary_key=True)
    is_active = Column(Boolean)
    role = Column(Enum(Role))
    status = Column(Enum(Status))
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)

    user = relationship("User", back_populates="profile")


NOW = datetime.datetime.now()
VALID_DATETIME_HTML = (
    f"<span "
    f'class="my-1 py-1 px-2 badge bg-secondary text-light '
    f'lead d-inline-block text-truncate" '
    f'data-bs-toggle="tooltip" '
    f'data-bs-html="true" '
    f'data-bs-placement="bottom" '
    f'title="{NOW}"'
    f">"
    f'<i class="fa-solid fa-calendar-days"></i> '
    f"{NOW.strftime('%d %B %Y %H:%M:%S')}"
    f"</span>"
)

VALID_STR_ENUM_HTML = Markup(
    "<span "
    'class="my-1 py-1 px-2 badge bg-secondary text-light '
    'lead d-inline-block text-truncate" '
    'data-bs-toggle="tooltip" '
    'data-bs-html="true" '
    'data-bs-placement="bottom" '
    'title="Available values: ADMIN, USER">ADMIN</span>'
)


async def test_column_formatters_different_details_and_list() -> None:
    custom_column_type_formatters = BASE_FORMATTERS.copy()
    custom_column_type_formatters.update(
        {str: lambda x: Markup(x[:16] + "...") if len(x) > 16 else Markup(x)}
    )

    custom_column_type_formatters_detail = BASE_FORMATTERS.copy()
    custom_column_type_formatters_detail.update({str: lambda x: Markup(x)})

    class UserAdmin(ModelView, model=User):
        column_type_formatters = custom_column_type_formatters
        column_type_formatters_detail = custom_column_type_formatters_detail

    user = User(name="very " * 10 + "long string")

    assert await UserAdmin().get_detail_value(user, "name") == (
        user.name,
        Markup(user.name),
    )

    assert await UserAdmin().get_list_value(user, "name") == (
        user.name,
        Markup("very very very v..."),
    )

    if HAS_UUID_SUPPORT:
        user_uuid = uuid.uuid4()
        user.user_uuid = user_uuid
        assert await UserAdmin().get_list_value(user, "user_uuid") == (
            user.user_uuid,
            user_uuid,
        )


async def test_column_formatters_list_with_inheritance_type() -> None:
    class CustomStr(str): ...

    custom_column_type_formatters = BASE_FORMATTERS.copy()
    custom_column_type_formatters.update(
        {CustomStr: lambda x: Markup(x[:16] + "...") if len(x) > 16 else Markup(x)}
    )

    class UserAdmin(ModelView, model=User):
        column_type_formatters = custom_column_type_formatters

    user = User(name="very " * 10 + "long string")

    assert await UserAdmin().get_detail_value(user, "name") == (
        user.name,
        Markup(user.name),
    )


async def test_column_formatters_list_with_inheritance_type_and_parent() -> None:
    class CustomStr(str): ...

    custom_column_type_formatters = BASE_FORMATTERS.copy()
    custom_column_type_formatters.update(
        {
            str: lambda x: Markup(x + " str class"),
            CustomStr: lambda x: Markup(x + " CustomStr class"),
        }
    )

    class UserAdmin(ModelView, model=User):
        column_type_formatters = custom_column_type_formatters

    user = User(name="Max")
    user_1 = User(name=CustomStr("Max"))

    assert await UserAdmin().get_list_value(user, "name") == (
        user.name,
        Markup("Max str class"),
    )

    assert await UserAdmin().get_list_value(user_1, "name") == (
        user_1.name,
        Markup("Max CustomStr class"),
    )


async def test_column_formatters_str_enum() -> None:
    custom_column_type_formatters = BASE_FORMATTERS.copy()
    custom_column_type_formatters.update({StrEnum: str_enum_formatter})

    class ProfileAdmin(ModelView, model=Profile):
        column_type_formatters = custom_column_type_formatters

    user = User()
    profile = Profile(user=user, role=Role.ADMIN, status=None, is_active=True)

    assert await ProfileAdmin().get_detail_value(profile, "role") == (
        Role.ADMIN,
        VALID_STR_ENUM_HTML,
    )

    assert await ProfileAdmin().get_detail_value(profile, "status") == (
        None,
        Markup(""),
    )


async def test_column_formatters_list_page_str_enum(client: TestClient) -> None:
    custom_column_type_formatters = BASE_FORMATTERS.copy()
    custom_column_type_formatters.update({StrEnum: str_enum_formatter})

    class ProfileAdmin(ModelView, model=Profile):
        column_list = [Profile.id, Profile.role]

        column_type_formatters = custom_column_type_formatters

    user = User()
    profile = Profile(user=user, role=Role.ADMIN, is_active=True)

    session = session_maker()
    session.add_all([user, profile])
    session.commit()

    admin.add_model_view(ProfileAdmin)
    response = client.get("/admin/profile/list")

    assert VALID_STR_ENUM_HTML in response.text


async def test_column_formatters_details_page_str_enum(client: TestClient) -> None:
    custom_column_type_formatters = BASE_FORMATTERS.copy()
    custom_column_type_formatters.update({StrEnum: str_enum_formatter})

    class ProfileAdmin(ModelView, model=Profile):
        column_details_list = [Profile.id, Profile.role]

        column_type_formatters = custom_column_type_formatters

    user = User()
    profile = Profile(user=user, role=Role.ADMIN, is_active=True)

    session = session_maker()
    session.add_all([user, profile])
    session.commit()

    admin.add_model_view(ProfileAdmin)
    response = client.get("/admin/profile/details/1")

    assert VALID_STR_ENUM_HTML in response.text


async def test_column_formatters_details_datetime(client: TestClient) -> None:
    custom_column_type_formatters = ModelView.column_type_formatters_detail.copy()
    custom_column_type_formatters.update(
        {
            datetime.datetime: datetime_formatter,
            str: copy_to_clipboard_formatter,
        }
    )

    class UserAdmin(ModelView, model=User):
        column_details_list = [User.id, User.registered_at]

        column_type_formatters_detail = custom_column_type_formatters

    user = User(registered_at=NOW)

    session = session_maker()
    session.add(user)
    session.commit()

    admin.add_model_view(UserAdmin)
    response = client.get("/admin/user/details/1")

    assert VALID_DATETIME_HTML in response.text


async def test_copy_to_clipboard_formatter_escapes_value() -> None:
    formatted = copy_to_clipboard_formatter('"<script>alert(1)</script>')

    assert 'data-copy-value="&#34;&lt;script&gt;alert(1)&lt;/script&gt;"' in formatted
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in formatted
