from typing import Generator

import pytest
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import declarative_base, sessionmaker
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Route
from starlette.testclient import TestClient

from sqladmin import Admin, ModelView
from tests.common import sync_engine as engine

session_maker = sessionmaker(bind=engine)

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(String(32), default="SQLAdmin")


@pytest.fixture(autouse=True)
def prepare_database() -> Generator[None, None, None]:
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


def test_root_path_in_redirect_url() -> None:
    app = Starlette()
    Admin(app=app, engine=engine)

    with TestClient(app, root_path="/api/v1") as client:
        response = client.get("/admin")
        assert response.status_code == 200
        assert str(response.url) == "http://testserver/api/v1/admin/"


def test_root_path_admin_routes() -> None:
    app = Starlette()
    admin = Admin(app=app, engine=engine)

    class UserAdmin(ModelView, model=User):
        ...

    admin.add_view(UserAdmin)

    with TestClient(app, root_path="/api/v1") as client:
        response = client.get("/admin/")
        assert response.status_code == 200
        assert "<h3>Admin</h3>" in response.text

        response = client.get("/admin/user/list")
        assert response.status_code == 200


def test_root_path_static_files() -> None:
    app = Starlette()
    Admin(app=app, engine=engine)

    with TestClient(app, root_path="/api/v1") as client:
        response = client.get("/admin/statics/css/main.css")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/css")


def test_root_path_does_not_affect_other_routes() -> None:
    def hello(request: Request) -> Response:
        return PlainTextResponse("hello")

    app = Starlette(routes=[Route("/hello", endpoint=hello)])
    Admin(app=app, engine=engine)

    with TestClient(app, root_path="/api/v1") as client:
        response = client.get("/hello")
        assert response.status_code == 200
        assert response.text == "hello"

        response = client.get("/admin/")
        assert response.status_code == 200


def test_root_path_with_custom_base_url() -> None:
    app = Starlette()
    Admin(app=app, engine=engine, base_url="/dashboard")

    with TestClient(app, root_path="/api/v1") as client:
        response = client.get("/dashboard/")
        assert response.status_code == 200

        response = client.get("/dashboard/statics/css/main.css")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/css")


def test_root_path_already_in_path() -> None:
    app = Starlette()
    Admin(app=app, engine=engine)

    with TestClient(app, root_path="/api/v1") as client:
        response = client.get("/api/v1/admin/")
        assert response.status_code == 200

        response = client.get("/api/v1/admin/statics/css/main.css")
        assert response.status_code == 200


def test_root_path_matches_base_url() -> None:
    app = Starlette()
    Admin(app=app, engine=engine)

    with TestClient(app, root_path="/admin") as client:
        response = client.get("/admin/")
        assert response.status_code == 200

        response = client.get("/admin/statics/css/main.css")
        assert response.status_code == 200


def test_root_path_does_not_rewrite_similar_prefix() -> None:
    """Routes like /admin-panel should not be affected by the /admin middleware."""

    def admin_panel(request: Request) -> Response:
        return PlainTextResponse("admin-panel")

    app = Starlette(routes=[Route("/admin-panel", endpoint=admin_panel)])
    Admin(app=app, engine=engine)

    with TestClient(app, root_path="/api/v1") as client:
        response = client.get("/admin-panel")
        assert response.status_code == 200
        assert response.text == "admin-panel"


def test_root_path_html_urls_include_root_path() -> None:
    """Asset and navigation URLs rendered in templates must include root_path."""
    app = Starlette()
    admin = Admin(app=app, engine=engine)

    class UserAdmin(ModelView, model=User):
        ...

    admin.add_view(UserAdmin)

    with TestClient(app, root_path="/api/v1") as client:
        response = client.get("/admin/")
        assert response.status_code == 200

        # Static asset URLs should include root_path
        assert "/api/v1/admin/statics/css/main.css" in response.text
        assert "/api/v1/admin/statics/js/main.js" in response.text

        # Navigation link to model list should include root_path
        assert "/api/v1/admin/user/list" in response.text


def test_root_path_redirect_after_create() -> None:
    """Redirect URL after creating a model should include root_path."""
    app = Starlette()
    admin = Admin(app=app, engine=engine)

    class UserAdmin(ModelView, model=User):
        ...

    admin.add_view(UserAdmin)

    with TestClient(app, root_path="/api/v1") as client:
        response = client.post(
            "/admin/user/create",
            data={"name": "test", "save": "Save"},
        )
        assert response.status_code == 200
        assert "/api/v1/admin/user/list" in str(response.url)


def test_root_path_delete_returns_url_with_root_path() -> None:
    """Delete endpoint returns a list URL that should include root_path."""
    with session_maker() as session:
        session.add(User(id=1, name="delete-me"))
        session.commit()

    app = Starlette()
    admin = Admin(app=app, engine=engine)

    class UserAdmin(ModelView, model=User):
        ...

    admin.add_view(UserAdmin)

    with TestClient(app, root_path="/api/v1") as client:
        response = client.delete(
            "/admin/user/delete",
            params={"pks": "1"},
            headers={"Referer": "http://testserver/api/v1/admin/user/list"},
        )
        assert response.status_code == 200
        assert "/api/v1/admin/user/list" in response.text


def test_no_root_path_unchanged_behavior() -> None:
    app = Starlette()
    admin = Admin(app=app, engine=engine)

    class UserAdmin(ModelView, model=User):
        ...

    admin.add_view(UserAdmin)

    with TestClient(app) as client:
        response = client.get("/admin/")
        assert response.status_code == 200

        response = client.get("/admin/user/list")
        assert response.status_code == 200

        response = client.get("/admin/statics/css/main.css")
        assert response.status_code == 200
