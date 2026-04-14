import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import Annotated, Any
from unittest.mock import MagicMock, PropertyMock

import pytest
from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String, Time, Uuid
from sqlalchemy.orm import declarative_base

from sqladmin.helpers import (
    get_column_python_type,
    get_object_identifier,
    is_falsy_value,
    object_identifier_values,
    parse_interval,
    secure_filename,
    slugify_action_name,
)

Base: Any = declarative_base()


def test_secure_filename(monkeypatch):
    assert secure_filename("My cool movie.mov") == "My_cool_movie.mov"
    assert secure_filename("../../../etc/passwd") == "etc_passwd"
    assert (
        secure_filename("i contain cool \xfcml\xe4uts.txt")
        == "i_contain_cool_umlauts.txt"
    )
    assert secure_filename("__filename__") == "filename"
    assert secure_filename("foo$&^*)bar") == "foobar"


def test_parse_interval():
    assert parse_interval("1 day") == timedelta(days=1)
    assert parse_interval("-1 day") == timedelta(days=-1)
    assert parse_interval("1.10000") == timedelta(seconds=1, microseconds=100000)
    assert parse_interval("P3DT01H00M00S") == timedelta(days=3, seconds=3600)


def test_is_falsy_values():
    assert is_falsy_value(None) is True
    assert is_falsy_value("") is True
    assert is_falsy_value(0) is False
    assert is_falsy_value("example") is False


def test_slugify_action_name():
    assert slugify_action_name("custom action") == "custom-action"

    with pytest.raises(ValueError):
        slugify_action_name("custom action !@#$%")


class Person(Base):
    __tablename__ = "users"

    family_id = Column(String, ForeignKey("family.id"), primary_key=True)
    member_id = Column(Integer, primary_key=True)
    version = Column(String, primary_key=True)


def person(family_id, member_id, version):
    return Person(family_id=family_id, member_id=member_id, version=version)


class Family(Base):
    __tablename__ = "family"
    id = Column(String, primary_key=True)


class Profile(Base):
    __tablename__ = "profile"
    id = Column(Integer, primary_key=True)


class Anniversary(Base):
    # Synthetic example of a composite PK with unusual key types
    __tablename__ = "anniversary"
    person_id = Column(Integer, ForeignKey("person.id"), primary_key=True)
    anniversary_date = Column(Date, primary_key=True)
    anniversary_time = Column(Time, primary_key=True)
    anniversary_timestamp = Column(DateTime, primary_key=True)


def test_single_pk_identifier():
    assert get_object_identifier(Family(id="test")) == "test"
    assert get_object_identifier(Family(id="C:\\Files\\")) == "C:\\Files\\"
    assert get_object_identifier(Family(id=r"1;2\;3")) == r"1;2\;3"

    assert get_object_identifier(Profile(id=0)) == 0
    assert get_object_identifier(Profile(id=3217)) == 3217


def test_single_pk_id_values():
    assert object_identifier_values("test", Family) == ("test",)
    assert object_identifier_values("C:\\Files\\", Family) == ("C:\\Files\\",)
    assert object_identifier_values(r"1;2\;3", Family) == (r"1;2\;3",)

    assert object_identifier_values(str(0), Profile) == (0,)
    assert object_identifier_values(str(3217), Profile) == (3217,)


def test_multi_pk_identifier():
    assert get_object_identifier(person("Johnson", 7, "A")) == "Johnson;7;A"
    assert (
        get_object_identifier(person("C:\\Files\\", 404, "F")) == r"C:\\Files\\;404;F"
    )
    assert get_object_identifier(person(r"1;2\;3", 201, "S")) == r"1\;2\\\;3;201;S"
    assert get_object_identifier(person("Doe", 3, "\\")) == "Doe;3;\\\\"
    assert get_object_identifier(person("", 1, "")) == ";1;"
    assert (
        get_object_identifier(
            Anniversary(
                person_id=1,
                anniversary_date=date(2025, 10, 29),
                anniversary_time=time(12, 30),
                anniversary_timestamp=datetime(
                    2025, 10, 29, 12, 30, tzinfo=timezone.utc
                ),
            )
        )
        == "1;2025-10-29;12:30:00;2025-10-29 12:30:00+00:00"
    )


def test_multi_pk_id_values():
    def id_values(ident):
        return object_identifier_values(ident, Person)

    assert id_values("Johnson;7;A") == ("Johnson", 7, "A")
    assert id_values(r"C:\\Files\\;404;F") == ("C:\\Files\\", 404, "F")
    assert id_values(r"1\;2\\\;3;201;S") == (r"1;2\;3", 201, "S")
    assert id_values("Doe;3;\\\\") == ("Doe", 3, "\\")
    assert id_values(";1;") == ("", 1, "")
    assert object_identifier_values(
        "1;2025-10-29;12:30:00;2025-10-29 12:30:00+00:00", Anniversary
    ) == (
        1,
        date(2025, 10, 29),
        time(12, 30),
        datetime(2025, 10, 29, 12, 30, tzinfo=timezone.utc),
    )


def test_catch_malformed_id():
    def test_case(ident):
        with pytest.raises(ValueError):
            object_identifier_values(ident, Person)

    test_case("Missing;1")
    test_case("Johnson;7;A;Extra")


class UUIDPKModel(Base):
    __tablename__ = "uuid_pk_model"
    id = Column(Uuid, primary_key=True)


def test_get_column_python_type_with_uuid_pk():
    """Regression #981: must not raise TypeError when python_type
    returns a type annotation instead of a plain class."""
    pk = UUIDPKModel.__table__.c["id"]
    result = get_column_python_type(pk)
    assert callable(result)


def test_get_column_python_type_annotated_type_no_typeerror():
    """When python_type returns Annotated[uuid.UUID, ...], issubclass
    must not be called on it — no TypeError should be raised."""
    mock_col = MagicMock()
    mock_col.type.python_type = Annotated[uuid.UUID, "meta"]
    # Before the fix: TypeError: issubclass() arg 1 must be a class
    result = get_column_python_type(mock_col)
    assert callable(result)


def test_get_column_python_type_annotated_returns_origin():
    """When python_type is Annotated[uuid.UUID, ...], the returned
    type should resolve to the origin class (uuid.UUID)."""
    mock_col = MagicMock()
    mock_col.type.python_type = Annotated[uuid.UUID, "meta"]
    result = get_column_python_type(mock_col)
    assert result is uuid.UUID


def test_get_column_python_type_not_implemented_no_impl():
    """Falls back to str when python_type raises NotImplementedError
    and there is no impl."""
    mock_col = MagicMock(spec=["type"])
    t = MagicMock(spec=["python_type"])
    type(t).python_type = PropertyMock(side_effect=NotImplementedError)
    mock_col.type = t
    assert get_column_python_type(mock_col) is str
