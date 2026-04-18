from typing import Generator

import pytest
from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base, relationship
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse
from starlette.testclient import TestClient

from sqladmin import Admin, BaseView, action, expose
from sqladmin.authentication import AuthenticationBackend
from sqladmin.models import ModelView
from tests.common import sync_engine as engine

Base = declarative_base()
session_maker = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)


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

    assert len(client.cookies) == 1
    assert response.status_code == 200


def test_logout(client: TestClient) -> None:
    response = client.get("/admin/logout")

    assert len(client.cookies) == 0
    assert response.status_code == 200
    assert response.url == "http://testserver/admin/login"


def test_expose_access_login_required_views(client: TestClient) -> None:
    response = client.get("/admin/custom")
    assert response.url == "http://testserver/admin/login"

    response = client.post("/admin/login", data={"username": "a", "password": "b"})

    response = client.get("/admin/custom")
    assert {"status": "ok"} == response.json()


def test_action_access_login_required_views(client: TestClient) -> None:
    response = client.get("/admin/movie/action/test")
    assert response.url == "http://testserver/admin/login"

    response = client.post("/admin/login", data={"username": "a", "password": "b"})

    response = client.get("/admin/movie/action/test")
    assert {"status": "ok"} == response.json()


class Artist(Base):
    __tablename__ = "artists_auth"

    id = Column(Integer, primary_key=True)
    name = Column(String(50))

    songs = relationship("SongAuth", back_populates="artist")

    def __str__(self) -> str:
        return f"Artist {self.id}"


class SongAuth(Base):
    __tablename__ = "songs_auth"

    id = Column(Integer, primary_key=True)
    artist_id = Column(Integer, ForeignKey("artists_auth.id"))

    artist = relationship("Artist", back_populates="songs")


class ArtistAdmin(ModelView, model=Artist):
    pass


class SongAuthAdmin(ModelView, model=SongAuth):
    form_ajax_refs = {
        "artist": {
            "fields": ("name",),
            "order_by": "name",
        }
    }


admin.add_view(ArtistAdmin)
admin.add_view(SongAuthAdmin)


@pytest.fixture(autouse=False)
def prepare_ajax_tables() -> Generator[None, None, None]:
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


def test_ajax_lookup_unauthenticated_redirects_to_login(
    client: TestClient,
) -> None:
    response = client.get("/admin/song-auth/ajax/lookup?name=artist&term=test")
    assert response.url == "http://testserver/admin/login"


def test_ajax_lookup_authenticated_returns_200(
    client: TestClient,
    prepare_ajax_tables: None,
) -> None:
    client.post(
        "/admin/login",
        data={"username": "a", "password": "b"},
    )

    response = client.get("/admin/song-auth/ajax/lookup?name=artist&term=test")
    assert response.status_code == 200
    assert "results" in response.json()


def test_ajax_lookup_after_logout_redirects_to_login(
    client: TestClient,
) -> None:
    client.post(
        "/admin/login",
        data={"username": "a", "password": "b"},
    )
    client.get("/admin/logout")

    response = client.get("/admin/song-auth/ajax/lookup?name=artist&term=test")
    assert response.url == "http://testserver/admin/login"
