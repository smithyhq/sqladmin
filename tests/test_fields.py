from datetime import date, datetime, timedelta
from typing import Generator
from uuid import UUID

import pytest
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import declarative_base
from wtforms import Form

from sqladmin.fields import (
    DateField,
    DateTimeField,
    IntervalField,
    JSONField,
    QuerySelectField,
    QuerySelectMultipleField,
    Select2TagsField,
    SelectField,
    UuidField,
)
from tests.common import DummyData
from tests.common import sync_engine as engine

Base = declarative_base()  # type: ignore


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(String)


@pytest.fixture(autouse=True, scope="function")
def prepare_database() -> Generator[None, None, None]:
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


def test_date_field() -> None:
    class F(Form):
        date = DateField()

    form = F()

    assert form.date.format == ["%Y-%m-%d"]
    assert 'data-role="datepicker"' in form.date()

    form = F(DummyData(date=["2021-12-22"]))
    assert form.date.data == date(2021, 12, 22)


def test_datetime_field() -> None:
    class F(Form):
        datetime = DateTimeField()

    form = F()

    assert form.datetime.format == ["%Y-%m-%d %H:%M:%S"]
    assert 'data-role="datetimepicker"' in form.datetime()

    form = F(DummyData(datetime=["2021-12-22 12:30:00"]))
    assert form.datetime.data == datetime(2021, 12, 22, 12, 30, 0, 0)


def test_json_field() -> None:
    class F(Form):
        json = JSONField()

    form = F()
    assert form.json() == """<textarea id="json" name="json">\r\n{}</textarea>"""

    form = F(DummyData(json=[""]))
    assert form.json.data is None

    form = F(DummyData(json=['{"a": 1}']))
    assert form.json.data == {"a": 1}
    assert (
        form.json()
        == """<textarea id="json" name="json">\r\n{&#34;a&#34;: 1}</textarea>"""
    )

    form = F(DummyData(json=["""'{"A": 10}'"""]))
    assert form.json.data is None


def test_select_field() -> None:
    class F(Form):
        select = SelectField(
            choices=[(1, "A"), (2, "B")],
            coerce=int,
        )

    form = F()
    assert '<option value="1">A</option><option value="2">B</option>' in form.select()

    form = F(DummyData(select=["1"]))
    assert form.validate() is True
    assert form.select.data == 1

    form = F(DummyData(select=["A"]))
    assert form.validate() is False
    assert form.select.data is None

    class F(Form):  # type: ignore
        select = SelectField(coerce=int, allow_blank=True)

    form = F()
    assert '<option selected value="__None">' in form.select()
    assert form.validate() is True

    form = F(DummyData(select=["__None"]))
    assert form.select.data is None


def test_query_select_field() -> None:
    select_data = [(str(i), str(User(id=i))) for i in range(5)]

    class F(Form):
        select = QuerySelectField(data=select_data, get_label="__doc__")

    form = F(DummyData(select=["1"]))
    form.select._select_data = []
    assert form.validate() is False

    class F(Form):  # type: ignore
        select = QuerySelectField(
            data=select_data,
            allow_blank=True,
        )

    form = F(DummyData(select=["__None"]))
    assert form.validate() is True

    class F(Form):  # type: ignore
        select = QuerySelectField()

    form = F(DummyData(select=["1"]))
    assert form.validate() is False


def test_query_select_multiple_field() -> None:
    data = [(str(i), str(User(id=i))) for i in range(5)]

    class F(Form):
        select = QuerySelectMultipleField(allow_blank=True, data=data)

    form = F()
    assert form.validate() is True

    form = F(DummyData(select=["1"]))
    form.select._select_data = data
    assert form.validate() is True

    form = F(DummyData(select=["100"]))
    form.select._select_data = data
    assert form.select.data == []
    assert form.validate() is False


def test_select2_tags_field() -> None:
    class F(Form):
        array = Select2TagsField()

    form = F()
    assert 'data-role="select2-tags"' in form.array()
    assert form.array.pre_validate(form) is None

    form = F(DummyData(array=["a", "b", "abc"]))
    assert form.array.data == ["a", "b", "abc"]

    form = F(DummyData(array=[]))
    assert form.array.data == []


def test_interval_field() -> None:
    class F(Form):
        interval = IntervalField()

    form = F()

    form = F(DummyData(interval=["1 day 22:30:00"]))
    assert form.interval.data == timedelta(days=1, seconds=81000)

    form = F(DummyData(interval=["1 1 1 1 1"]))
    assert form.validate() is False

    form = F(DummyData(interval=[]))
    assert form.validate() is True


def test_uuid_field() -> None:
    class F(Form):
        uuid = UuidField()

    form = F()
    assert 'type="text"' in form.uuid()

    form = F(DummyData(uuid=["00000000-0000-0000-0000-000000000001"]))
    assert form.uuid.data == UUID("00000000-0000-0000-0000-000000000001")

    form = F(DummyData(uuid=["00000000-0000-000000000001"]))
    assert form.validate() is False
