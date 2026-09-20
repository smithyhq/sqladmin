import enum
from datetime import datetime, timedelta, timezone

import arrow
import pytest
from sqlalchemy import Column, Integer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy_utils import (
    ArrowType,
    ChoiceType,
    ColorType,
    CurrencyType,
    EmailType,
    IPAddressType,
    PhoneNumberType,
    TimezoneType,
    URLType,
    UUIDType,
)

from sqladmin.fields import TimezoneAwareDateTimeField
from sqladmin.forms import get_model_form
from tests.common import DummyData
from tests.common import async_engine as engine

pytestmark = pytest.mark.anyio

Base = declarative_base()
session_maker = async_sessionmaker(bind=engine, class_=AsyncSession)


class RoleEnum(enum.Enum):
    admin = "admin"
    user = "user"


ROLE_CHOICES = [("admin", "admin"), ("user", "user")]


@pytest.mark.parametrize("choices", [RoleEnum, ROLE_CHOICES])
async def test_model_form_sqlalchemy_utils(choices) -> None:
    class SQLAlchemyUtilsModel(Base):
        __tablename__ = f"sqlalchemy_utils_model_{choices}"

        id = Column(Integer, primary_key=True)
        arrow = Column(ArrowType)
        email = Column(EmailType)
        ip = Column(IPAddressType)
        uuid = Column(UUIDType)
        url = Column(URLType)
        currency = Column(CurrencyType)
        timezone = Column(TimezoneType)
        phone = Column(PhoneNumberType)
        color = Column(ColorType)
        role = Column(ChoiceType(choices))

    Form = await get_model_form(model=SQLAlchemyUtilsModel, session_maker=session_maker)
    data = DummyData(
        currency="IR",
        timezone=["Iran/Tehran"],
        color="bbb",
        phone="abc",
        arrow="wrong",
        role=None,
    )
    form = Form(data)
    assert form.validate() is False

    data = DummyData(
        currency="IRR",
        timezone="Asia/Tehran",
        color="red",
        phone="+9823456789",
        arrow="2023-02-06 12:00:0",
        role="admin",
    )
    form = Form(data)
    assert form.validate() is True


async def test_model_form_timezone_aware_arrow_type() -> None:
    class ArrowModel(Base):
        __tablename__ = "sqlalchemy_utils_arrow_tz"

        id = Column(Integer, primary_key=True)
        at = Column(ArrowType(timezone=True))

    Form = await get_model_form(model=ArrowModel, session_maker=session_maker)
    # e.g. psycopg returns values in the session timezone
    stored = arrow.get(
        datetime(2026, 7, 26, 11, 30, tzinfo=timezone(timedelta(hours=2)))
    )

    form = Form(data={"at": stored})
    assert isinstance(form.at, TimezoneAwareDateTimeField)
    assert form.at._value() == "2026-07-26 09:30:00"

    submitted = Form(DummyData(at=[form.at._value()])).at.data
    assert submitted == stored.datetime
    assert submitted.tzinfo is timezone.utc
