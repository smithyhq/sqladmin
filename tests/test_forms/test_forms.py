import enum
import inspect
import time
from collections.abc import AsyncGenerator, Generator
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Interval,
    Numeric,
    String,
    Text,
    Time,
    TypeDecorator,
    func,
    select,
)
from sqlalchemy.dialects.postgresql import ARRAY, INET, MACADDR, TIMESTAMP, UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import (
    ColumnProperty,
    column_property,
    composite,
    declarative_base,
    relationship,
)
from wtforms import BooleanField, Field, Form, IntegerField, StringField, TimeField
from wtforms.fields import DateTimeField as WTFormsDateTimeField
from wtforms.fields.core import UnboundField

from sqladmin import ModelView
from sqladmin.ajax import create_ajax_loader
from sqladmin.fields import (
    DateTimeField,
    Select2TagsField,
    SelectField,
    TimezoneAwareDateTimeField,
)
from sqladmin.forms import ModelConverter, converts, get_model_form
from tests.common import DummyData
from tests.common import async_engine as engine

pytestmark = pytest.mark.anyio

Base = declarative_base()
session_maker = async_sessionmaker(bind=engine, class_=AsyncSession)


class Status(enum.Enum):
    REGISTERED = 1
    ACTIVE = 2


class Point:  # pragma: no cover
    def __init__(self, x: int, y: int) -> None:
        self.x = x
        self.y = y

    def __composite_values__(self) -> tuple[int, int]:
        return self.x, self.y

    def __eq__(self, other: "Point") -> bool:
        return isinstance(other, Point) and other.x == self.x and other.y == self.y

    def __ne__(self, other: "Point") -> bool:
        return not self.__eq__(other)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(String(32), default="SQLAdmin")
    email = Column(String, nullable=False)
    bio = Column(Text)
    active = Column(Boolean, nullable=True)
    verified = Column(Boolean, nullable=False)
    registered_at = Column(DateTime)
    status = Column(Enum(Status))
    balance = Column(Numeric)
    number = Column(Integer)
    reminder = Column(Time)
    x = Column(Integer)
    y = Column(Integer)
    interval = Column(Interval)

    addresses = relationship("Address", back_populates="user")
    profile = relationship("Profile", back_populates="user", uselist=False)
    point = composite(Point, x, y)


class TZDateTime(TypeDecorator):
    impl = DateTime(timezone=True)
    cache_ok = True


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=True)
    naive_at = Column(DateTime, nullable=True)
    aware_at = Column(DateTime(timezone=True), nullable=True)
    pg_aware_at = Column(TIMESTAMP(timezone=True), nullable=True)
    decorated_at = Column(TZDateTime, nullable=True)


class Address(Base):
    __tablename__ = "addresses"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))

    user = relationship("User", back_populates="addresses")


class Profile(Base):
    __tablename__ = "profiles"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)

    user = relationship("User", back_populates="profile")


@pytest.fixture(autouse=True)
async def prepare_database() -> AsyncGenerator[None, None]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


async def test_model_form() -> None:
    Form = await get_model_form(model=User, session_maker=session_maker)
    form = Form()

    assert len(form._fields) == 15
    assert form._fields["active"].flags.required is None
    assert form._fields["name"].flags.required is None
    assert form._fields["email"].flags.required is True
    assert isinstance(form._fields["active"], SelectField)
    assert isinstance(form._fields["verified"], BooleanField)
    assert isinstance(form._fields["reminder"], TimeField)


async def test_model_form_converter_with_default() -> None:
    class Point(Base):
        __tablename__ = "points"

        id = Column(Integer, primary_key=True)
        user = User()

    await get_model_form(model=Point, session_maker=session_maker)


async def test_model_form_only() -> None:
    Form = await get_model_form(
        model=User, session_maker=session_maker, only=["status"]
    )
    assert len(Form()._fields) == 1


async def test_model_form_exclude() -> None:
    Form = await get_model_form(
        model=User, session_maker=session_maker, exclude=["status"]
    )
    assert len(Form()._fields) == 14


async def test_model_form_form_args() -> None:
    form_args = {"name": {"label": "User Name"}, "number": {"default": 100}}
    Form = await get_model_form(
        model=User, session_maker=session_maker, form_args=form_args
    )
    assert Form()._fields["name"].label.text == "User Name"
    assert Form()._fields["number"].default == 100


async def test_model_form_column_default() -> None:
    class Model(Base):
        __tablename__ = "model_column_default"

        id = Column(Integer, primary_key=True)
        name = Column(String, default="untitled")
        priority = Column(Integer, default=5)
        is_active = Column(Boolean, nullable=False, default=True)

    Form = await get_model_form(model=Model, session_maker=session_maker)
    assert Form()._fields["name"].default == "untitled"
    assert Form()._fields["priority"].default == 5
    assert Form()._fields["is_active"].default is True


async def test_model_form_form_args_default_overrides_column() -> None:
    class Model(Base):
        __tablename__ = "model_form_args_overrides_column_default"

        id = Column(Integer, primary_key=True)
        name = Column(String, default="from-column")

    Form = await get_model_form(
        model=Model,
        session_maker=session_maker,
        form_args={"name": {"default": "from-form-args"}},
    )
    assert Form()._fields["name"].default == "from-form-args"


async def test_model_form_column_label() -> None:
    labels = {"name": "User Name"}
    Form = await get_model_form(
        model=User, session_maker=session_maker, column_labels=labels
    )
    assert Form()._fields["name"].label.text == "User Name"


@pytest.mark.filterwarnings("ignore:^Dialect sqlite\\+aiosqlite.*$")
async def test_model_form_column_label_precedence() -> None:
    # Validator takes precedence over label.
    form_args_user = {"name": {"label": "User Name (Use Me)"}}
    labels_user = {"name": "User Name (Do Not Use Me)"}
    Form = await get_model_form(
        model=User,
        session_maker=session_maker,
        form_args=form_args_user,
        column_labels=labels_user,
    )
    assert Form()._fields["name"].label.text == "User Name (Use Me)"

    # If there are form args, but no "label", then read from labels mapping.
    form_args_user = {"user": {}}
    labels_user = {"user": "User (Use Me)"}
    Form = await get_model_form(
        model=Address,
        session_maker=session_maker,
        form_args=form_args_user,
        column_labels=labels_user,
    )
    assert Form()._fields["user"].label.text == "User (Use Me)"


async def test_model_form_override() -> None:
    class ExampleField(Field):
        pass

    Form = await get_model_form(
        model=User, session_maker=session_maker, form_overrides={"name": ExampleField}
    )
    assert isinstance(Form()._fields["name"], ExampleField)
    assert not isinstance(Form()._fields["email"], ExampleField)


async def test_model_form_override_receives_ajax_loader() -> None:
    class LoaderAwareField(Field):
        def __init__(self, *args: Any, loader=None, **kwargs: Any) -> None:
            self.loader = loader
            kwargs.pop("allow_blank", None)
            super().__init__(*args, **kwargs)

    class AddressAdmin(ModelView, model=Address):
        form_ajax_refs = {"user": {"fields": ("name",)}}

    loader = create_ajax_loader(
        model_admin=AddressAdmin(),
        name="user",
        options={"fields": ("name",)},
    )

    Form = await get_model_form(
        model=Address,
        session_maker=session_maker,
        form_overrides={"user": LoaderAwareField},
        form_ajax_refs={"user": loader},
    )

    assert Form()._fields["user"].loader is loader


@pytest.mark.skipif(engine.name != "postgresql", reason="PostgreSQL only")
async def test_model_form_postgresql() -> None:
    class PostgresModel(Base):
        __tablename__ = "postgres_model"

        id = Column(Integer, primary_key=True)
        uuid = Column(UUID)
        ip = Column(INET)
        mac = Column(MACADDR)
        array = Column(ARRAY(String))

    Form = await get_model_form(model=PostgresModel, session_maker=session_maker)

    assert len(Form()._fields) == 4
    assert isinstance(Form()._fields["array"], Select2TagsField)


async def test_form_override_scaffold() -> None:
    class MyForm(Form):
        foo = StringField("Foo")

    class UserAdmin(ModelView, model=User):
        form = MyForm

    form_type = await UserAdmin().scaffold_form()
    form = form_type()
    assert isinstance(form, MyForm)
    assert len(form._fields) == 1
    assert "foo" in form._fields


async def test_form_converter_when_impl_is_callable() -> None:
    class MyType(TypeDecorator):
        impl = String

    class CustomModel(Base):
        __tablename__ = "impl_callable"

        id = Column(Integer, primary_key=True)
        custom = Column(MyType)

    Form = await get_model_form(model=CustomModel, session_maker=session_maker)
    assert "custom" in Form()._fields


async def test_form_converter_when_impl_not_callable() -> None:
    class MyType(TypeDecorator):
        impl = String(length=100)

    class CustomModel(Base):
        __tablename__ = "impl_non_callable"

        id = Column(Integer, primary_key=True)
        custom = Column(MyType)

    Form = await get_model_form(model=CustomModel, session_maker=session_maker)
    assert "custom" in Form()._fields


async def test_model_form_include_pk() -> None:
    Form = await get_model_form(
        model=User, session_maker=session_maker, form_include_pk=True
    )
    assert "id" in Form()._fields


async def test_form_override_form_converter() -> None:
    class EmailField(Field):
        pass

    class EmailType(TypeDecorator):
        impl = String

    class MyModelConverter(ModelConverter):
        @converts("EmailType")
        def convert_phone_number(
            self,
            model: type,
            prop: ColumnProperty,
            kwargs: dict[str, Any],
        ) -> UnboundField:
            return EmailField(**kwargs)

    class MyModel(Base):
        __tablename__ = "model_form_converter"

        id = Column(Integer, primary_key=True)
        number = Column(Integer)
        email = Column(EmailType)

    Form = await get_model_form(
        model=MyModel,
        session_maker=session_maker,
        form_converter=MyModelConverter,
    )

    assert isinstance(Form()._fields["email"], EmailField)
    assert isinstance(Form()._fields["number"], IntegerField)


async def test_model_field_clashing_with_wtforms_reserved_attribute() -> None:
    class DataModel(Base):
        __tablename__ = "model_with_wtforms_reserved_attribute"
        id = Column(Integer, primary_key=True)
        data = Column(String, default="untitled")
        errors = Column(String)
        process = Column(String)
        validate = Column(Boolean)
        populate_obj = Column(String)

    Form = await get_model_form(model=DataModel, session_maker=session_maker)
    obj = DataModel(
        id=1,
        data="abcdef",
        errors="boom",
        process="pid1",
        validate=True,
        populate_obj="ohi",
    )
    form = Form(obj=obj)
    assert Form.data_.name == "data"
    assert Form.errors_.name == "errors"
    assert Form.process_.name == "process"
    assert Form.validate_.name == "validate"
    assert Form.populate_obj_.name == "populate_obj"
    assert Form()._fields["data_"].default == "untitled"
    assert isinstance(Form.data, property)
    assert isinstance(Form.errors, property)
    assert isinstance(form.data, dict)
    assert inspect.isfunction(Form.process)
    assert inspect.isfunction(Form.validate)
    assert inspect.isfunction(Form.populate_obj)


async def test_column_property_is_ignored_in_form() -> None:
    class Model(Base):
        __tablename__ = "model_column_property"

        id = Column(Integer, primary_key=True)
        number = Column(Integer)
        count = column_property(select(func.count("Model")).scalar_subquery())

    Form = await get_model_form(model=Model, session_maker=session_maker)

    assert "count" not in Form()._fields


async def test_model_form_timezone_aware_datetime() -> None:
    Form = await get_model_form(model=Event, session_maker=session_maker)
    form = Form()

    naive = form._fields["naive_at"]
    assert type(naive) is DateTimeField
    assert isinstance(naive, WTFormsDateTimeField)
    assert not naive.description

    for name in ("aware_at", "pg_aware_at", "decorated_at"):
        field = form._fields[name]
        assert isinstance(field, TimezoneAwareDateTimeField), name
        assert field.display_timezone is timezone.utc
        assert field.description == "UTC"


async def test_model_form_timezone_aware_datetime_form_args() -> None:
    Form = await get_model_form(
        model=Event,
        session_maker=session_maker,
        form_args={"aware_at": {"display_timezone": ZoneInfo("Asia/Kolkata")}},
    )
    stored = datetime(2026, 7, 26, 9, 30, tzinfo=timezone.utc)

    form = Form(data={"aware_at": stored})
    assert form.aware_at.description == "Asia/Kolkata"
    assert form.aware_at._value() == "2026-07-26 15:00:00"

    submitted = Form(DummyData(aware_at=[form.aware_at._value()]))
    assert submitted.aware_at.data == stored


async def test_model_form_timezone_aware_datetime_hidden_description() -> None:
    Form = await get_model_form(
        model=Event,
        session_maker=session_maker,
        form_args={"aware_at": {"description": ""}},
    )
    assert Form().aware_at.description == ""


@pytest.fixture
def non_utc_local_timezone() -> Generator[None, None, None]:
    if not hasattr(time, "tzset"):  # pragma: no cover
        pytest.skip("time.tzset() is not available on this platform")
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("TZ", "Europe/Berlin")
        time.tzset()
        yield
    time.tzset()


@pytest.mark.usefixtures("non_utc_local_timezone")
async def test_edit_does_not_shift_timezone_aware_datetime() -> None:
    """Regression test for https://github.com/smithyhq/sqladmin/issues/796"""
    ist = timezone(timedelta(hours=5, minutes=30))
    stored = datetime(2026, 7, 26, 15, 0, tzinfo=ist)
    columns = ("aware_at", "pg_aware_at", "decorated_at")

    async with session_maker() as session:
        session.add(Event(id=1, name="before", **{c: stored for c in columns}))
        await session.commit()

    async with session_maker() as session:
        event = await session.get(Event, 1)
        assert event is not None
        before = {c: getattr(event, c) for c in columns}

    Form = await get_model_form(model=Event, session_maker=session_maker)
    rendered = Form(data={"name": "before", **before})
    # Simulate the user changing an unrelated field and saving.
    formdata = DummyData(name=["after"], naive_at=[""])
    formdata.update({c: [rendered[c]._value()] for c in columns})
    submitted = Form(formdata)

    async with session_maker() as session:
        event = await session.get(Event, 1)
        assert event is not None
        for name, value in submitted.data.items():
            setattr(event, name, value)
        await session.commit()

    async with session_maker() as session:
        event = await session.get(Event, 1)
        assert event is not None
        assert event.name == "after"
        for column in columns:
            assert getattr(event, column) == before[column], column
