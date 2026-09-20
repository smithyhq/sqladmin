import enum
from collections.abc import Generator
from datetime import date, datetime, timedelta, timezone, tzinfo
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from markupsafe import Markup
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import declarative_base
from wtforms import Form, validators
from wtforms.validators import DataRequired, Length

from sqladmin.fields import (
    BooleanField,
    DateField,
    DateTimeField,
    IntervalField,
    JSONField,
    QuerySelectField,
    QuerySelectMultipleField,
    Select2TagsField,
    SelectField,
    TextAreaField,
    TimezoneAwareDateTimeField,
    UuidField,
)
from tests.common import DummyData
from tests.common import sync_engine as engine

IST = timezone(timedelta(hours=5, minutes=30))

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


def test_timezone_aware_datetime_field_defaults_to_utc() -> None:
    class F(Form):
        dt = TimezoneAwareDateTimeField()

    stored = datetime(2026, 7, 26, 15, 0, tzinfo=IST)
    form = F(data={"dt": stored})

    assert form.dt.display_timezone is timezone.utc
    assert form.dt.description == "UTC"
    assert 'data-role="datetimepicker"' in form.dt()
    assert form.dt._value() == "2026-07-26 09:30:00"

    submitted = F(DummyData(dt=[form.dt._value()])).dt.data
    assert submitted == stored
    assert submitted.tzinfo is timezone.utc


def test_timezone_aware_datetime_field_new_value_is_utc() -> None:
    class F(Form):
        dt = TimezoneAwareDateTimeField()

    form = F(DummyData(dt=["2026-09-17 12:00:00"]))
    assert form.dt.data == datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)


def test_timezone_aware_datetime_field_display_timezone() -> None:
    berlin = ZoneInfo("Europe/Berlin")

    class F(Form):
        dt = TimezoneAwareDateTimeField(display_timezone=berlin)

    stored = datetime(2026, 7, 26, 15, 0, tzinfo=IST)
    form = F(data={"dt": stored})
    assert form.dt.description == "Europe/Berlin"
    assert form.dt._value() == "2026-07-26 11:30:00"
    assert F(DummyData(dt=[form.dt._value()])).dt.data == stored

    # DST is resolved per value
    summer = F(DummyData(dt=["2026-07-01 12:00:00"])).dt.data
    winter = F(DummyData(dt=["2026-01-01 12:00:00"])).dt.data
    assert summer.utcoffset() == timedelta(hours=2)
    assert winter.utcoffset() == timedelta(hours=1)


def test_timezone_aware_datetime_field_pytz_style_timezone() -> None:
    class LocalizingTZ(tzinfo):
        """Mimics pytz: attaching via replace() gives a wrong offset."""

        def utcoffset(self, dt: datetime | None) -> timedelta:  # pragma: no cover
            return timedelta(minutes=53)  # LMT-like offset

        def dst(self, dt: datetime | None) -> timedelta:  # pragma: no cover
            return timedelta(0)

        def localize(self, dt: datetime) -> datetime:
            return dt.replace(tzinfo=IST)

    class F(Form):
        dt = TimezoneAwareDateTimeField(display_timezone=LocalizingTZ())

    data = F(DummyData(dt=["2026-07-26 15:00:00"])).dt.data
    assert data.utcoffset() == timedelta(hours=5, minutes=30)


def test_timezone_aware_datetime_field_keeps_custom_description() -> None:
    class F(Form):
        dt = TimezoneAwareDateTimeField(description="Starts at (UTC)")

    assert F().dt.description == "Starts at (UTC)"


def test_timezone_aware_datetime_field_empty_description_hides_timezone() -> None:
    class F(Form):
        dt = TimezoneAwareDateTimeField(description="")

    assert F().dt.description == ""


def test_timezone_aware_datetime_field_naive_and_empty_values() -> None:
    class F(Form):
        dt = TimezoneAwareDateTimeField()

    # Naive values (e.g. from SQLite) are displayed as-is.
    naive = datetime(2026, 7, 26, 15, 0)
    form = F(data={"dt": naive})
    assert form.dt._value() == "2026-07-26 15:00:00"

    # Field missing from the submitted form keeps the object value, tz-aware.
    form = F(DummyData(), data={"dt": datetime(2026, 7, 26, 15, 0, tzinfo=IST)})
    assert form.dt.data == datetime(2026, 7, 26, 9, 30, tzinfo=timezone.utc)

    assert F(data={"dt": None}).dt.data is None

    form = F(DummyData(dt=["not a date"]))
    assert form.dt.data is None
    assert form.dt.process_errors


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

    # A callable get_label is applied to each label in iter_choices().
    class F(Form):
        select = QuerySelectField(
            data=[("1", "alpha"), ("2", "beta")],
            get_label=lambda label: label.upper(),
        )

    form = F()
    assert [choice[1] for choice in form.select.iter_choices()] == ["ALPHA", "BETA"]
    assert '<option value="1">ALPHA</option>' in form.select()

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


def test_boolean_field() -> None:
    class F(Form):
        boolean = BooleanField()

    form = F()
    html = form.boolean()
    assert '<div class="form-switch d-flex align-items-center h-100">' in html
    assert 'type="checkbox"' in html
    assert "checked" not in html

    form = F(DummyData(boolean=["y"]))
    html = form.boolean()
    assert "checked" in html

    class FRequired(Form):
        boolean = BooleanField(validators=[DataRequired()])

    form = FRequired()
    html = form.boolean()
    assert "required" in html


def test_textarea_field() -> None:
    class F(Form):
        text = TextAreaField()

    form = F()
    assert "autoresize-textarea" in form.text()
    assert "chars-count-label" in form.text()


def test_textarea_field_without_chars_count() -> None:
    class F(Form):
        text = TextAreaField(show_chars_count=False)

    form = F()
    assert "autoresize-textarea" in form.text()
    assert "chars-count-label" not in form.text()


def test_textarea_field_without_autoresize() -> None:
    class F(Form):
        text = TextAreaField(enable_autoresize=False)

    form = F()
    assert "autoresize-textarea" not in form.text()
    assert "chars-count-label" in form.text()


def test_textarea_field_all_bool_false() -> None:
    class F(Form):
        text = TextAreaField(enable_autoresize=False, show_chars_count=False)

    form = F()
    assert "autoresize-textarea" not in form.text()
    assert "chars-count-label" not in form.text()


def test_textarea_field_with_validators() -> None:
    class F(Form):
        text = TextAreaField(validators=[DataRequired(), Length(min=1, max=100)])

    form = F()
    html = form.text()

    assert len(form.text.validators) == 2
    assert type(form.text.validators[0]) is DataRequired
    assert type(form.text.validators[1]) is Length

    # Validator flags must reach the rendered widget, not just the field.
    assert "required" in html
    assert 'minlength="1"' in html
    assert 'maxlength="100"' in html


def test_enum_field() -> None:
    class MyEnum(enum.Enum):
        first = "first"
        second = "second"

    class F(Form):
        tuple_choices = SelectField(
            choices=[(e.value, e.value) for e in MyEnum],
            validators=[validators.AnyOf([(e.value, e.value) for e in MyEnum])],
            coerce=lambda v: v.name if isinstance(v, enum.Enum) else str(v),
        )
        enum_choices = SelectField(
            choices=[e for e in MyEnum],
            validators=[validators.AnyOf([e for e in MyEnum])],
            coerce=lambda v: v.name if isinstance(v, enum.Enum) else str(v),
        )
        else_choices = SelectField(
            choices=[e.value for e in MyEnum],
            validators=[validators.AnyOf([e.value for e in MyEnum])],
            coerce=lambda v: v.name if isinstance(v, enum.Enum) else str(v),
        )

    form = F()

    assert form.tuple_choices() == Markup(
        '<select id="tuple_choices" name="tuple_choices">'
        '<option value="first">first</option>'
        '<option value="second">second</option>'
        "</select>"
    )

    assert form.enum_choices() == Markup(
        '<select id="enum_choices" name="enum_choices">'
        '<option value="first">first</option>'
        '<option value="second">second</option>'
        "</select>"
    )

    assert form.else_choices() == Markup(
        '<select id="else_choices" name="else_choices">'
        '<option value="first">first</option>'
        '<option value="second">second</option>'
        "</select>"
    )


def test_enum_field_with_non_str_values() -> None:
    class MyIntEnum(enum.IntEnum):
        first = 1
        second = 2

    class F(Form):
        enum_choices = SelectField(
            choices=list(MyIntEnum),
            coerce=lambda v: v.name if isinstance(v, enum.Enum) else str(v),
        )

    form = F()

    # iter_choices() yields the raw Enum value; the widget stringifies it when
    # rendering, so assert on the tuples to pin the actual contract.
    assert [(c[0], c[1]) for c in form.enum_choices.iter_choices()] == [
        (1, "first"),
        (2, "second"),
    ]
    assert '<option value="1">first</option>' in form.enum_choices()


@pytest.mark.parametrize(
    "values, valid",
    [(["missing"], False), (["1", "missing"], False), (["1"], True), ([], True)],
)
def test_multiple_select_validates_unknown_choices_on_first_pass(values, valid):
    class F(Form):
        select = QuerySelectMultipleField(data=[("1", "One")])

    form = F(DummyData(select=values))
    assert form.validate() is valid
    assert form.errors == ({} if valid else {"select": ["Not a valid choice"]})
