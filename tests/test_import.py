import enum

import pytest
from sqlalchemy import Boolean, Column, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from starlette.datastructures import MultiDict

from sqladmin import ModelView
from sqladmin._import import validate_import_row
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
