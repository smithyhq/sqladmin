from typing import Generator

import pytest
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import declarative_base
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Route
from starlette.testclient import TestClient

from sqladmin import Admin, ModelView
from tests.common import sync_engine as engine

Base = declarative_base()  # type: ignore


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
