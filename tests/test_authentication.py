from typing import Generator

import pytest
from sqlalchemy import Column, Integer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse
from starlette.testclient import TestClient

from sqladmin import Admin, BaseView, action, expose
from sqladmin.authentication import AuthenticationBackend
from sqladmin.models import ModelView
from tests.common import sync_engine as engine

Base = declarative_base()  # type: Any
session_maker = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


class Movie(Base):
    __tablename__ = "movies"

    id = Column(Integer, primary_key=True)


class CustomBackend(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        if form["username"] != "a":
            return False

        request.session.update({"token": "amin"})
        return True

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        if "token" not in request.session:
            return RedirectResponse(request.url_for("admin:login"), status_code=302)
        return True


class CustomAdmin(BaseView):
    @expose("/custom", methods=["GET"])
    async def custom(self, request: Request):
        return JSONResponse({"status": "ok"})


class MovieAdmin(ModelView, model=Movie):
    @action(name="test")
    async def test_page(self, request: Request):
        return JSONResponse({"status": "ok"})


app = Starlette()
authentication_backend = CustomBackend(secret_key="sqladmin")
admin = Admin(app=app, engine=engine, authentication_backend=authentication_backend)
admin.add_base_view(CustomAdmin)
admin.add_model_view(MovieAdmin)


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app=app, base_url="http://testserver") as c:
        yield c


def test_access_login_required_views(client: TestClient) -> None:
    response = client.get("/admin/")
    assert response.url == "http://testserver/admin/login"

    response = client.get("/admin/users/list")
    assert response.url == "http://testserver/admin/login"


def test_login_failure(client: TestClient) -> None:
    response = client.post("/admin/login", data={"username": "x", "password": "b"})

    assert response.status_code == 400
    assert response.url == "http://testserver/admin/login"


def test_login(client: TestClient) -> None:
    response = client.post("/admin/login", data={"username": "a", "password": "b"})

    assert len(response.cookies) == 1
    assert response.status_code == 200


def test_logout(client: TestClient) -> None:
    response = client.get("/admin/logout")

    assert len(response.cookies) == 0
    assert response.status_code == 200
    assert response.url == "http://testserver/admin/login"


def test_expose_access_login_required_views(client: TestClient) -> None:
    response = client.get("/admin/custom")
    assert response.url == "http://testserver/admin/login"

    response = client.post("/admin/login", data={"username": "a", "password": "b"})
    client.cookies = response.cookies

    response = client.get("/admin/custom")
    assert {"status": "ok"} == response.json()


def test_action_access_login_required_views(client: TestClient) -> None:
    response = client.get("/admin/movie/action/test")
    assert response.url == "http://testserver/admin/login"

    response = client.post("/admin/login", data={"username": "a", "password": "b"})
    client.cookies = response.cookies

    response = client.get("/admin/movie/action/test")
    assert {"status": "ok"} == response.json()
