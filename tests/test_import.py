import enum
import json

import pytest
from sqlalchemy import Boolean, Column, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from starlette.applications import Starlette
from starlette.datastructures import MultiDict
from starlette.testclient import TestClient

from sqladmin import ModelView
from sqladmin._import import (
    validate_foreign_key_values,
    validate_import_row,
)
from sqladmin.application import Admin
from tests.common import sync_engine as engine

Base = declarative_base()
session_maker = sessionmaker(bind=engine)


class ImportStatus(enum.Enum):
    ACTIVE = "ACTIVE"
    DEACTIVE = "DEACTIVE"


class ImportUser(Base):
    __tablename__ = "import_user"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    status = Column(Enum(ImportStatus), default=ImportStatus.ACTIVE)


class ImportWidget(Base):
    __tablename__ = "import_widget_validate"

    id = Column(Integer, primary_key=True)
    profile_id = Column(Integer, ForeignKey("import_profile_validate.id"))
    active = Column(Boolean, nullable=False)

    profile = relationship("ImportProfile")


class ImportProfile(Base):
    __tablename__ = "import_profile_validate"

    id = Column(Integer, primary_key=True)


class ImportRequiredWidget(Base):
    __tablename__ = "import_required_widget_validate"

    id = Column(Integer, primary_key=True)
    profile_id = Column(
        Integer, ForeignKey("import_profile_validate.id"), nullable=False
    )

    profile = relationship("ImportProfile")


class ImportTag(Base):
    __tablename__ = "import_tag_validate"

    id = Column(Integer, primary_key=True)
    label = Column(String)
    post_id = Column(Integer, ForeignKey("import_post_validate.id"))


class ImportPost(Base):
    __tablename__ = "import_post_validate"

    id = Column(Integer, primary_key=True)
    title = Column(String)

    tags = relationship("ImportTag")


class ImportPrice(Base):
    __tablename__ = "import_price"

    id = Column(Integer, primary_key=True)
    price = Column(Numeric(10, 2))


class ImportNumericParent(Base):
    __tablename__ = "import_numeric_parent"

    id = Column(Numeric(10, 2), primary_key=True, autoincrement=False)


class ImportNumericChild(Base):
    __tablename__ = "import_numeric_child"

    id = Column(Integer, primary_key=True)
    parent_id = Column(Numeric(10, 2), ForeignKey("import_numeric_parent.id"))


class ImportPriceAdmin(ModelView, model=ImportPrice):
    can_import = True
    column_import_list = [ImportPrice.price]


class ImportNumericChildAdmin(ModelView, model=ImportNumericChild):
    can_import = True
    column_import_list = [ImportNumericChild.parent_id]


class ImportUserAdmin(ModelView, model=ImportUser):
    column_import_list = [ImportUser.name, ImportUser.status]


class ImportWidgetAdmin(ModelView, model=ImportWidget):
    column_import_list = [ImportWidget.profile_id, ImportWidget.active]


@pytest.fixture(autouse=True)
def prepare_database():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


def _model_view(admin_class: type[ModelView]) -> ModelView:
    model_view = admin_class()
    model_view.session_maker = session_maker
    return model_view


@pytest.mark.anyio
async def test_validate_import_row_coerces_boolean_despite_wtforms_semantics() -> None:
    model_view = _model_view(ImportWidgetAdmin)
    form_class = await model_view.scaffold_form(model_view._form_create_rules)
    row = MultiDict([("profile_id", "5"), ("active", "False")])

    merged, errors, row_data = validate_import_row(
        row,
        model_view.get_import_columns(),
        ImportWidget,
        form_class,
        Admin._denormalize_wtform_data,
    )

    assert errors == {}
    assert row_data == {"profile_id": "5", "active": "False"}
    assert merged["active"] is False
    assert merged["profile_id"] == 5
    assert isinstance(merged["profile_id"], int)


@pytest.mark.anyio
async def test_validate_import_row_reports_form_validation_errors() -> None:
    model_view = _model_view(ImportUserAdmin)
    form_class = await model_view.scaffold_form(model_view._form_create_rules)
    row = MultiDict([("name", ""), ("status", "NOT_A_STATUS")])

    merged, errors, _row_data = validate_import_row(
        row,
        model_view.get_import_columns(),
        ImportUser,
        form_class,
        Admin._denormalize_wtform_data,
    )

    assert "name" in errors
    assert "status" in errors


@pytest.mark.anyio
async def test_validate_import_row_reports_coercion_errors() -> None:
    model_view = _model_view(ImportWidgetAdmin)
    form_class = await model_view.scaffold_form(model_view._form_create_rules)
    row = MultiDict([("profile_id", "not-an-integer"), ("active", "true")])

    merged, errors, _row_data = validate_import_row(
        row,
        model_view.get_import_columns(),
        ImportWidget,
        form_class,
        Admin._denormalize_wtform_data,
    )

    assert merged == {"active": True}
    assert "profile_id" in errors
    assert "Invalid value" in errors["profile_id"][0]


@pytest.mark.anyio
async def test_import_value_error_coerce_column_value() -> None:
    # row_data is built by hand, so the value reaches foreign_key_error_message
    # uncoerced and fails when coerced against the Integer target column.
    model_view = _model_view(ImportWidgetAdmin)
    result = await validate_foreign_key_values(
        model_view,
        {
            ImportWidget.id.key: 1,
            ImportWidget.profile_id.key: "not-an-int",
        },
        {},
    )
    assert result == {
        "profile_id": ["Invalid value 'not-an-int' for column profile_id."]
    }


@pytest.mark.anyio
async def test_import_type_error_coerce_column_value(monkeypatch) -> None:
    def mock_coerce_column_value(column: Column, value):
        raise TypeError("error!")

    monkeypatch.setattr(
        "sqladmin._import.coerce_column_value", mock_coerce_column_value
    )

    model_view = _model_view(ImportWidgetAdmin)
    result = await validate_foreign_key_values(
        model_view,
        {
            ImportWidget.id.key: 1,
            ImportWidget.active.key: True,
            ImportWidget.profile_id.key: 1,
        },
        {},
    )
    assert result == {"profile_id": ["Invalid value 1 for column profile_id."]}


class ImportWidgetRelationshipAdmin(ModelView, model=ImportWidget):
    column_import_list = [ImportWidget.active, ImportWidget.profile]


@pytest.mark.anyio
async def test_validate_import_row_reports_invalid_relationship_value() -> None:
    model_view = _model_view(ImportWidgetRelationshipAdmin)
    form_class = await model_view.scaffold_form(model_view._form_create_rules)
    row = MultiDict([("active", "true"), ("profile", "adg34gfb13")])

    merged, errors, _row_data = validate_import_row(
        row,
        model_view.get_import_columns(),
        ImportWidget,
        form_class,
        Admin._denormalize_wtform_data,
    )

    assert merged["profile"] is None
    assert errors["profile"] == ["Not a valid choice"]


@pytest.mark.anyio
async def test_validate_import_row_accepts_valid_relationship_value() -> None:
    with session_maker() as session:
        session.add(ImportProfile(id=1))
        session.commit()

    model_view = _model_view(ImportWidgetRelationshipAdmin)
    form_class = await model_view.scaffold_form(model_view._form_create_rules)
    row = MultiDict([("active", "true"), ("profile", "1")])

    merged, errors, _row_data = validate_import_row(
        row,
        model_view.get_import_columns(),
        ImportWidget,
        form_class,
        Admin._denormalize_wtform_data,
    )

    assert errors == {}
    assert merged["active"] is True
    assert merged["profile"] == "1"


class ImportRequiredWidgetRelationshipAdmin(ModelView, model=ImportRequiredWidget):
    column_import_list = [ImportRequiredWidget.profile]


@pytest.mark.anyio
@pytest.mark.parametrize("value", ["adg34gfb13", ""])
async def test_validate_import_row_does_not_duplicate_relationship_errors(
    value: str,
) -> None:
    model_view = _model_view(ImportRequiredWidgetRelationshipAdmin)
    form_class = await model_view.scaffold_form(model_view._form_create_rules)
    row = MultiDict([("profile", value)])

    _merged, errors, _row_data = validate_import_row(
        row,
        model_view.get_import_columns(),
        ImportRequiredWidget,
        form_class,
        Admin._denormalize_wtform_data,
    )

    assert errors["profile"] == ["Not a valid choice"]


class ImportPostTagsAdmin(ModelView, model=ImportPost):
    column_import_list = [ImportPost.title, ImportPost.tags]


@pytest.mark.anyio
async def test_validate_import_row_round_trips_valid_multi_select_value() -> None:
    with session_maker() as session:
        session.add(ImportTag(id=1, label="t1"))
        session.commit()

    model_view = _model_view(ImportPostTagsAdmin)
    form_class = await model_view.scaffold_form(model_view._form_create_rules)
    row = MultiDict([("title", "good"), ("tags", "1")])

    merged, errors, _row_data = validate_import_row(
        row,
        model_view.get_import_columns(),
        ImportPost,
        form_class,
        Admin._denormalize_wtform_data,
    )

    assert errors == {}
    assert merged["title"] == "good"
    assert merged["tags"] == ["1"]


@pytest.mark.anyio
async def test_validate_import_row_defaults_non_nullable_column_from_form():
    model_view = _model_view(ImportWidgetAdmin)
    form_class = await model_view.scaffold_form(model_view._form_create_rules)
    row = MultiDict([("profile_id", "1"), ("active", "")])
    merged, errors, _row_data = validate_import_row(
        row,
        model_view.get_import_columns(),
        ImportWidget,
        form_class,
        Admin._denormalize_wtform_data,
    )
    assert errors == {}
    assert merged == {"profile_id": 1, "active": False}


@pytest.mark.parametrize("continue_on_error", ["0", "1"])
@pytest.mark.parametrize(
    ("admin_class", "column"),
    [
        (ImportPriceAdmin, "price"),
        (ImportNumericChildAdmin, "parent_id"),
    ],
)
def test_import_csv_reports_invalid_numeric_value(
    admin_class: type[ModelView], column: str, continue_on_error: str
) -> None:
    app = Starlette()
    admin = Admin(app=app, engine=engine)
    admin.add_view(admin_class)

    with TestClient(app=app, base_url="http://testserver") as client:
        response = client.post(
            f"/admin/{admin_class.identity}/import",
            data={"continue_on_error": continue_on_error},
            files={"csvfile": ("data.csv", f"{column}\r\nabc\r\n".encode())},
        )

    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines() if line]
    result = events[-1]
    assert result["type"] == "result"
    assert result["ok"] is (continue_on_error == "1")
    assert result["imported"] == 0
    assert result["skipped"] == 1
    assert result["missed_rows"][0]["errors"][column]
