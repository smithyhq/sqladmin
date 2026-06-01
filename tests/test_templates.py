# tests/test_templates.py
from typing import Callable, Generator

import pytest
from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.orm import Session, declarative_base
from sqlalchemy.pool import StaticPool
from starlette.applications import Starlette
from starlette.testclient import TestClient

from sqladmin import Admin, ModelView

Base = declarative_base()
engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


_ClientFixtureType = Callable[[str, str], TestClient]


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String)


class UserAdmin(ModelView, model=User):
    pass


@pytest.fixture(autouse=True, scope="function")
def prepare_database() -> Generator[None, None, None]:
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture()
def make_client(tmp_path) -> Generator[_ClientFixtureType, None, None]:
    def _make(template_name: str, template_content: str) -> TestClient:
        template_dir = tmp_path / "sqladmin"
        template_dir.mkdir(parents=True, exist_ok=True)
        (template_dir / template_name).write_text(template_content)

        app = Starlette()
        admin = Admin(app, engine, templates_dir=str(tmp_path))
        admin.add_view(UserAdmin)
        return TestClient(app)

    yield _make


######################################################
################## BASE.HTML BLOCKS ##################
######################################################
def test_head_meta_block_can_be_overridden(make_client: _ClientFixtureType) -> None:
    client = make_client(
        "base.html",
        """
        {% extends "sqladmin_original/base.html" %}
        {% block head_meta %}
        <meta name="custom-meta" content="test-value">
        {% endblock %}
    """,
    )
    response = client.get("/admin/")
    assert response.status_code == 200
    assert 'name="custom-meta"' in response.text
    assert 'content="test-value"' in response.text


def test_head_meta_block_super_preserves_defaults(
    make_client: _ClientFixtureType,
) -> None:
    client = make_client(
        "base.html",
        """
        {% extends "sqladmin_original/base.html" %}
        {% block head_meta %}
        {{ super() }}
        <meta name="extra" content="extra-value">
        {% endblock %}
    """,
    )
    response = client.get("/admin/")
    assert response.status_code == 200
    assert 'charset="UTF-8"' in response.text
    assert 'name="extra"' in response.text


def test_head_css_block_can_inject_stylesheet(make_client: _ClientFixtureType) -> None:
    client = make_client(
        "base.html",
        """
        {% extends "sqladmin_original/base.html" %}
        {% block head_css %}
        {{ super() }}
        <link rel="stylesheet" href="/static/custom.css">
        {% endblock %}
    """,
    )
    response = client.get("/admin/")
    assert response.status_code == 200
    assert "/static/custom.css" in response.text
    assert "tabler.min.css" in response.text


def test_head_css_block_can_replace_stylesheets(
    make_client: _ClientFixtureType,
) -> None:
    client = make_client(
        "base.html",
        """
        {% extends "sqladmin_original/base.html" %}
        {% block head_css %}
        <link rel="stylesheet" href="/static/my-only.css">
        {% endblock %}
    """,
    )
    response = client.get("/admin/")
    assert response.status_code == 200
    assert "/static/my-only.css" in response.text
    assert "tabler.min.css" not in response.text


def test_head_tail_block_injects_before_end_of_head(
    make_client: _ClientFixtureType,
) -> None:
    client = make_client(
        "base.html",
        """
        {% extends "sqladmin_original/base.html" %}
        {% block head_tail %}
        <script>window.__CUSTOM__ = true;</script>
        {% endblock %}
    """,
    )
    response = client.get("/admin/")
    assert response.status_code == 200
    text = response.text
    assert "window.__CUSTOM__" in text
    assert text.index("window.__CUSTOM__") < text.index("</head>")


def test_tail_js_block_can_inject_scripts(make_client: _ClientFixtureType) -> None:
    client = make_client(
        "base.html",
        """
        {% extends "sqladmin_original/base.html" %}
        {% block tail_js %}
        {{ super() }}
        <script src="/static/custom.js"></script>
        {% endblock %}
    """,
    )
    response = client.get("/admin/")
    assert response.status_code == 200
    assert "/static/custom.js" in response.text
    assert "jquery.min.js" in response.text


def test_head_js_block_can_replace_stylesheets(make_client: _ClientFixtureType) -> None:
    client = make_client(
        "base.html",
        """
        {% extends "sqladmin_original/base.html" %}
        {% block tail_js %}
        <script src="/static/custom.js"></script>
        {% endblock %}
    """,
    )
    response = client.get("/admin/")
    assert response.status_code == 200
    assert "/static/custom.js" in response.text
    assert "jquery.min.js" not in response.text


def test_tail_js_block_appears_before_closing_body(
    make_client: _ClientFixtureType,
) -> None:
    client = make_client(
        "base.html",
        """
        {% extends "sqladmin_original/base.html" %}
        {% block tail_js %}
        {{ super() }}
        <script>window.__TAIL__ = true;</script>
        {% endblock %}
    """,
    )
    response = client.get("/admin/")
    assert response.status_code == 200
    text = response.text
    assert "window.__TAIL__" in text
    assert text.index("window.__TAIL__") < text.index("</body>")


######################################################


######################################################
################ CREATE.HTML BLOCKS #################
######################################################
def test_create_form_block_can_be_overridden(make_client: _ClientFixtureType) -> None:
    client = make_client(
        "create.html",
        """
        {% extends "sqladmin_original/create.html" %}
        {% block create_form %}
        <div id="custom-create-form">CUSTOM_CREATE_FORM</div>
        {% endblock %}
    """,
    )
    response = client.get("/admin/user/create")
    assert response.status_code == 200
    assert "CUSTOM_CREATE_FORM" in response.text
    assert "<form action=" not in response.text


def test_create_form_block_coexists_using_super(
    make_client: _ClientFixtureType,
) -> None:
    client = make_client(
        "create.html",
        """
        {% extends "sqladmin_original/create.html" %}
        {% block create_form %}
        {{ super() }}
        <div id="custom-create-form">CUSTOM_CREATE_FORM</div>
        {% endblock %}
    """,
    )
    response = client.get("/admin/user/create")
    assert response.status_code == 200
    assert "CUSTOM_CREATE_FORM" in response.text
    assert "<form action=" in response.text


def test_submit_buttons_bottom_can_be_overridden_in_create(
    make_client: _ClientFixtureType,
) -> None:
    client = make_client(
        "create.html",
        """
        {% extends "sqladmin_original/create.html" %}
        {% block submit_buttons_bottom %}
        <button id="custom-submit-btn">CUSTOM_BTN</button>
        {% endblock %}
    """,
    )
    response = client.get("/admin/user/create")
    assert response.status_code == 200
    assert "CUSTOM_BTN" in response.text
    assert 'value="Save"' not in response.text


def test_submit_buttons_bottom_coexists_using_super_in_create(
    make_client: _ClientFixtureType,
) -> None:
    client = make_client(
        "create.html",
        """
        {% extends "sqladmin_original/create.html" %}
        {% block submit_buttons_bottom %}
        {{ super() }}
        <button id="custom-submit-btn">CUSTOM_BTN</button>
        {% endblock %}
    """,
    )
    response = client.get("/admin/user/create")
    assert response.status_code == 200
    assert "CUSTOM_BTN" in response.text
    assert 'value="Save"' in response.text


######################################################
################# EDIT.HTML BLOCKS ##################
######################################################
def test_edit_form_block_can_be_overridden(make_client: _ClientFixtureType) -> None:
    client = make_client(
        "edit.html",
        """
        {% extends "sqladmin_original/edit.html" %}
        {% block edit_form %}
        <div id="custom-edit-form">CUSTOM_EDIT_FORM</div>
        {% endblock %}
    """,
    )
    with Session(engine) as session:
        session.add(User(name="test"))
        session.commit()

    response = client.get("/admin/user/edit/1")
    assert response.status_code == 200
    assert "CUSTOM_EDIT_FORM" in response.text
    assert "<form action=" not in response.text


def test_edit_form_block_coexists_using_super(make_client: _ClientFixtureType) -> None:
    client = make_client(
        "edit.html",
        """
        {% extends "sqladmin_original/edit.html" %}
        {% block edit_form %}
        {{ super() }}
        <div id="custom-edit-form">CUSTOM_EDIT_FORM</div>
        {% endblock %}
    """,
    )
    with Session(engine) as session:
        session.add(User(name="test"))
        session.commit()

    response = client.get("/admin/user/edit/1")
    assert response.status_code == 200
    assert "CUSTOM_EDIT_FORM" in response.text
    assert "<form action=" in response.text


def test_submit_buttons_bottom_can_be_overridden_in_edit(
    make_client: _ClientFixtureType,
) -> None:
    client = make_client(
        "edit.html",
        """
        {% extends "sqladmin_original/edit.html" %}
        {% block submit_buttons_bottom %}
        <button id="custom-submit-btn">CUSTOM_BTN</button>
        {% endblock %}
    """,
    )
    with Session(engine) as session:
        session.add(User(name="test"))
        session.commit()

    response = client.get("/admin/user/edit/1")
    assert response.status_code == 200
    assert "CUSTOM_BTN" in response.text
    assert 'value="Save"' not in response.text


def test_submit_buttons_bottom_coexists_using_super_in_edit(
    make_client: _ClientFixtureType,
) -> None:
    client = make_client(
        "edit.html",
        """
        {% extends "sqladmin_original/edit.html" %}
        {% block submit_buttons_bottom %}
        {{ super() }}
        <button id="custom-submit-btn">CUSTOM_BTN</button>
        {% endblock %}
    """,
    )
    with Session(engine) as session:
        session.add(User(name="test"))
        session.commit()

    response = client.get("/admin/user/edit/1")
    assert response.status_code == 200
    assert "CUSTOM_BTN" in response.text
    assert 'value="Save"' in response.text


######################################################
################ DETAILS.HTML BLOCKS ################
######################################################
def test_details_table_block_can_be_overridden(make_client: _ClientFixtureType) -> None:
    client = make_client(
        "details.html",
        """
        {% extends "sqladmin_original/details.html" %}
        {% block details_table %}
        <div id="custom-details-table">CUSTOM_DETAILS_TABLE</div>
        {% endblock %}
    """,
    )
    with Session(engine) as session:
        session.add(User(name="test"))
        session.commit()

    response = client.get("/admin/user/details/1")
    assert response.status_code == 200
    assert "CUSTOM_DETAILS_TABLE" in response.text
    assert "<table" not in response.text


def test_details_table_block_coexists_using_super(
    make_client: _ClientFixtureType,
) -> None:
    client = make_client(
        "details.html",
        """
        {% extends "sqladmin_original/details.html" %}
        {% block details_table %}
        {{ super() }}
        <div id="custom-details-table">CUSTOM_DETAILS_TABLE</div>
        {% endblock %}
    """,
    )
    with Session(engine) as session:
        session.add(User(name="test"))
        session.commit()

    response = client.get("/admin/user/details/1")
    assert response.status_code == 200
    assert "CUSTOM_DETAILS_TABLE" in response.text
    assert "<table" in response.text


def test_action_buttons_bottom_can_be_overridden_in_details(
    make_client: _ClientFixtureType,
) -> None:
    client = make_client(
        "details.html",
        """
        {% extends "sqladmin_original/details.html" %}
        {% block action_buttons_bottom %}
        <button id="custom-action-btn">CUSTOM_ACTION</button>
        {% endblock %}
    """,
    )
    with Session(engine) as session:
        session.add(User(name="test"))
        session.commit()

    response = client.get("/admin/user/details/1")
    assert response.status_code == 200
    assert "CUSTOM_ACTION" in response.text
    assert "Please confirm" not in response.text


def test_action_buttons_bottom_coexists_using_super_in_details(
    make_client: _ClientFixtureType,
) -> None:
    client = make_client(
        "details.html",
        """
        {% extends "sqladmin_original/details.html" %}
        {% block action_buttons_bottom %}
        {{ super() }}
        <button id="custom-action-btn">CUSTOM_ACTION</button>
        {% endblock %}
    """,
    )
    with Session(engine) as session:
        session.add(User(name="test"))
        session.commit()

    response = client.get("/admin/user/details/1")
    assert response.status_code == 200
    assert "CUSTOM_ACTION" in response.text
    assert "Please confirm" in response.text


######################################################
################## LIST.HTML BLOCKS ##################
######################################################
def test_model_menu_bar_block_can_be_overridden(
    make_client: _ClientFixtureType,
) -> None:
    client = make_client(
        "list.html",
        """
        {% extends "sqladmin_original/list.html" %}
        {% block model_menu_bar %}
        <div id="custom-menu-bar">CUSTOM_MENU_BAR</div>
        {% endblock %}
    """,
    )
    response = client.get("/admin/user/list")
    assert response.status_code == 200
    assert "CUSTOM_MENU_BAR" in response.text
    assert "New User" not in response.text


def test_model_menu_bar_block_coexists_using_super(
    make_client: _ClientFixtureType,
) -> None:
    client = make_client(
        "list.html",
        """
        {% extends "sqladmin_original/list.html" %}
        {% block model_menu_bar %}
        {{ super() }}
        <div id="custom-menu-bar">CUSTOM_MENU_BAR</div>
        {% endblock %}
    """,
    )
    response = client.get("/admin/user/list")
    assert response.status_code == 200
    assert "CUSTOM_MENU_BAR" in response.text
    assert "New User" in response.text


def test_model_list_table_block_can_be_overridden(
    make_client: _ClientFixtureType,
) -> None:
    client = make_client(
        "list.html",
        """
        {% extends "sqladmin_original/list.html" %}
        {% block model_list_table %}
        <div id="custom-list-table">CUSTOM_LIST_TABLE</div>
        {% endblock %}
    """,
    )
    response = client.get("/admin/user/list")
    assert response.status_code == 200
    assert "CUSTOM_LIST_TABLE" in response.text
    assert "<table" not in response.text


def test_model_list_table_block_coexists_using_super(
    make_client: _ClientFixtureType,
) -> None:
    client = make_client(
        "list.html",
        """
        {% extends "sqladmin_original/list.html" %}
        {% block model_list_table %}
        {{ super() }}
        <div id="custom-list-table">CUSTOM_LIST_TABLE</div>
        {% endblock %}
    """,
    )
    response = client.get("/admin/user/list")
    assert response.status_code == 200
    assert "CUSTOM_LIST_TABLE" in response.text
    assert "<table" in response.text
