from typing import Generator

import pytest
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import declarative_base, sessionmaker
from starlette.applications import Starlette
from starlette.datastructures import MutableHeaders
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.testclient import TestClient
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from sqladmin import Admin, ModelView
from tests.common import sync_engine as engine

Base = declarative_base()  # type: ignore
session_maker = sessionmaker(bind=engine)


class DataModel(Base):
    __tablename__ = "datamodel"
    id = Column(Integer, primary_key=True)
    data = Column(String)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(String(32), default="SQLAdmin")


class PinnedObject(Base):
    __tablename__ = "pinned_objects"

    id = Column(Integer, primary_key=True)
    pinnedable_type = Column(String)

    __mapper_args__ = {
        "polymorphic_identity": "pinned_object",
        "polymorphic_on": pinnedable_type,
    }


class NewsPinned(PinnedObject):
    __mapper_args__ = {"polymorphic_identity": "news_pinned"}


@pytest.fixture(autouse=True)
def prepare_database() -> Generator[None, None, None]:
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


def test_application_title() -> None:
    app = Starlette()
    Admin(app=app, engine=engine)

    with TestClient(app) as client:
        response = client.get("/admin")

    assert response.status_code == 200
    assert "<h3>Admin</h3>" in response.text
    assert "<title>Admin</title>" in response.text


def test_application_logo() -> None:
    app = Starlette()
    Admin(
        app=app,
        engine=engine,
        logo_url="https://example.com/logo.svg",
        base_url="/dashboard",
    )

    with TestClient(app) as client:
        response = client.get("/dashboard")

    assert response.status_code == 200
    assert (
        '<img src="https://example.com/logo.svg" width="64" height="64"'
        in response.text
    )


def test_application_logo_custom_dimensions() -> None:
    app = Starlette()
    Admin(
        app=app,
        engine=engine,
        logo_url="https://example.com/logo.svg",
        logo_width=128,
        logo_height=96,
        base_url="/dashboard",
    )

    with TestClient(app) as client:
        response = client.get("/dashboard")

    assert response.status_code == 200
    assert (
        '<img src="https://example.com/logo.svg" width="128" height="96"'
        in response.text
    )


def test_middlewares() -> None:
    class CorrelationIdMiddleware:
        def __init__(self, app: ASGIApp) -> None:
            self.app = app

        async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
            async def send_wrapper(message: Message) -> None:
                if message["type"] == "http.response.start":
                    headers = MutableHeaders(scope=message)
                    headers.append("X-Correlation-ID", "UUID")
                await send(message)

            await self.app(scope, receive, send_wrapper)

    app = Starlette()
    Admin(
        app=app,
        engine=engine,
        middlewares=[Middleware(CorrelationIdMiddleware)],
    )

    with TestClient(app) as client:
        response = client.get("/admin")

    assert response.status_code == 200
    assert "x-correlation-id" in response.headers


def _get_statics_mount(admin: Admin) -> Mount:
    statics_mount = next(
        route
        for route in admin.admin.router.routes
        if isinstance(route, Mount) and route.name == "statics"
    )
    assert isinstance(statics_mount.app, StaticFiles)
    return statics_mount


def test_static_files_use_default_kwargs() -> None:
    app = Starlette()
    admin = Admin(app=app, engine=engine)

    statics_mount = _get_statics_mount(admin)

    assert statics_mount.app.follow_symlink is False
    assert statics_mount.app.packages == ["sqladmin"]


def test_static_files_accept_custom_kwargs() -> None:
    """Issue #863: package statics can opt into following symlinks."""
    app = Starlette()
    admin = Admin(
        app=app,
        engine=engine,
        static_files_kwargs={"follow_symlink": True},
    )

    statics_mount = _get_statics_mount(admin)

    assert statics_mount.app.follow_symlink is True
    assert statics_mount.app.packages == ["sqladmin"]


def test_static_files_kwargs_cannot_override_packages() -> None:
    app = Starlette()
    admin = Admin(
        app=app,
        engine=engine,
        static_files_kwargs={"packages": ["not_sqladmin"]},
    )

    statics_mount = _get_statics_mount(admin)

    assert statics_mount.app.packages == ["sqladmin"]


def test_get_save_redirect_url():
    async def index(request: Request):
        obj = User(id=1)
        form_data = await request.form()
        url = admin.get_save_redirect_url(request, form_data, admin.views[0], obj)
        return Response(str(url))

    app = Starlette(
        routes=[
            Route("/{identity}", index, methods=["POST"]),
        ]
    )
    admin = Admin(app=app, engine=engine)

    class UserAdmin(ModelView, model=User):
        save_as = True

    admin.add_view(UserAdmin)

    client = TestClient(app)

    response = client.post("/user", data={"save": "Save"})
    assert response.text == "http://testserver/admin/user/list"

    response = client.post("/user", data={"save": "Save and continue editing"})
    assert response.text == "http://testserver/admin/user/edit/1"

    response = client.post("/user", data={"save": "Save as new"})
    assert response.text == "http://testserver/admin/user/edit/1"

    response = client.post("/user", data={"save": "Save and add another"})
    assert response.text == "http://testserver/admin/user/create"

    # Issue #1055: the list query string (page, sorting, search) should be
    # preserved on "Save" so the user returns to the page they came from.
    response = client.post("/user?page=3", data={"save": "Save"})
    assert response.text == "http://testserver/admin/user/list?page=3"

    # The query string only matters for the list redirect; the other actions
    # go to fixed edit/create pages and should ignore it.
    response = client.post("/user?page=3", data={"save": "Save and continue editing"})
    assert response.text == "http://testserver/admin/user/edit/1"


def test_build_category_menu():
    app = Starlette()
    admin = Admin(app=app, engine=engine)

    class UserAdmin(ModelView, model=User):
        category = "Accounts"

    admin.add_view(UserAdmin)

    admin._menu.items.pop().name = "Accounts"


def test_normalize_wtform_fields() -> None:
    app = Starlette()
    admin = Admin(app=app, engine=engine)

    class DataModelAdmin(ModelView, model=DataModel): ...

    datamodel = DataModel(id=1, data="abcdef")
    admin.add_view(DataModelAdmin)
    assert admin._normalize_wtform_data(datamodel) == {"data_": "abcdef"}


def test_denormalize_wtform_fields() -> None:
    app = Starlette()
    admin = Admin(app=app, engine=engine)

    class DataModelAdmin(ModelView, model=DataModel): ...

    datamodel = DataModel(id=1, data="abcdef")
    admin.add_view(DataModelAdmin)
    assert admin._denormalize_wtform_data({"data_": "abcdef"}, datamodel) == {
        "data": "abcdef"
    }

    datamodel_empty = DataModel(id=1, data="")
    assert admin._denormalize_wtform_data({"data_": "abcdef"}, datamodel_empty) == {
        "data": "abcdef"
    }


def test_validate_page_and_page_size():
    app = Starlette()
    admin = Admin(app=app, engine=engine)

    class UserAdmin(ModelView, model=User): ...

    admin.add_view(UserAdmin)

    client = TestClient(app)

    response = client.get("/admin/user/list?page=10000")
    assert response.status_code == 200

    response = client.get("/admin/user/list?page=aaaa")
    assert response.status_code == 400


def test_polymorphic_model_pages_use_view_identity() -> None:
    app = Starlette()
    admin = Admin(app=app, engine=engine)

    class PinnedObjectAdmin(ModelView, model=PinnedObject):
        column_list = [PinnedObject.id]

    admin.add_view(PinnedObjectAdmin)

    with session_maker() as session:
        session.add(NewsPinned(id=1))
        session.commit()

    client = TestClient(app)

    response = client.get("/admin/pinned-object/list")
    assert response.status_code == 200
    assert 'href="http://testserver/admin/pinned-object/details/1"' in response.text
    assert 'href="http://testserver/admin/pinned-object/edit/1"' in response.text
    assert (
        'data-url="http://testserver/admin/pinned-object/delete?pks=1"' in response.text
    )
    assert "/admin/news-pinned/" not in response.text

    response = client.get("/admin/pinned-object/details/1")
    assert response.status_code == 200
    assert (
        'data-url="http://testserver/admin/pinned-object/delete?pks=1"' in response.text
    )
    assert 'href="http://testserver/admin/pinned-object/edit/1"' in response.text

    response = client.get("/admin/pinned-object/edit/1")
    assert response.status_code == 200
    assert 'action="http://testserver/admin/pinned-object/edit/1"' in response.text


def test_polymorphic_delete_helper_uses_view_identity() -> None:
    app = Starlette()
    admin = Admin(app=app, engine=engine)

    class PinnedObjectAdmin(ModelView, model=PinnedObject): ...

    admin.add_view(PinnedObjectAdmin)
    view = admin.views[0]

    async def index(request: Request) -> Response:
        return Response(view._url_for_delete(request, NewsPinned(id=1)))

    app.add_route("/delete-url", index)

    client = TestClient(app)
    response = client.get("/delete-url")

    assert response.text == "http://testserver/admin/pinned-object/delete?pks=1"


def test_is_list_template_global():
    """Test that is_list correctly identifies list and set types."""
    app = Starlette()
    admin = Admin(app=app, engine=engine)

    is_list = admin.templates.env.globals["is_list"]

    # Should return True for list and set
    assert is_list([1, 2, 3]) is True
    assert is_list({1, 2, 3}) is True
    assert is_list([]) is True
    assert is_list(set()) is True

    # Should return False for non-collection types
    assert is_list("string") is False
    assert is_list(123) is False
    assert is_list(None) is False
    assert is_list({"key": "value"}) is False
