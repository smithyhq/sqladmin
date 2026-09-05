from collections.abc import Generator
from typing import Any

import pytest
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.testclient import TestClient

from sqladmin import Admin, BaseView, action, expose
from sqladmin.authentication import AuthenticationBackend
from sqladmin.authorization import (
    ACTIONS,
    AuthorizationBackend,
    GrantsAuthorizationBackend,
    custom_action,
    matches_grant,
)
from sqladmin.models import ModelView
from tests.common import sync_engine as engine

Base = declarative_base()
session_maker = sessionmaker(bind=engine, class_=Session)


class AuthzUser(Base):
    __tablename__ = "authz_users"

    id = Column(Integer, primary_key=True)
    name = Column(String)


class ReadonlyUser(Base):
    __tablename__ = "authz_readonly_users"

    id = Column(Integer, primary_key=True)
    name = Column(String)


class ClosedUser(Base):
    __tablename__ = "authz_closed_users"

    id = Column(Integer, primary_key=True)
    name = Column(String)


class OpenUser(Base):
    __tablename__ = "authz_open_users"

    id = Column(Integer, primary_key=True)
    name = Column(String)


class RowUser(Base):
    __tablename__ = "authz_row_users"

    id = Column(Integer, primary_key=True)
    name = Column(String)


class SessionBackend(AuthenticationBackend):
    async def login(self, request: Request) -> bool:  # pragma: no cover
        return True

    async def logout(self, request: Request) -> bool:  # pragma: no cover
        return True

    async def authenticate(self, request: Request) -> bool:
        return True


class HeaderAuthorization(GrantsAuthorizationBackend):
    """Grants come from a request header so tests can vary them per request."""

    async def get_grants(self, request: Request) -> set:
        raw = request.headers.get("x-grants", "")
        grants = set()
        for item in filter(None, raw.split(",")):
            identity, _, action_name = item.partition(":")
            grants.add((identity, action_name))
        return grants

    async def is_superuser(self, request: Request) -> bool:
        return request.headers.get("x-superuser") == "1"


class UserAdmin(ModelView, model=AuthzUser):
    @action(name="ping")
    async def ping(self, request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})


class CustomPage(BaseView):
    name = "Custom Page"

    @expose("/custom-page", methods=["GET"])
    async def page(self, request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})


def build_client(
    authorization_backend: AuthorizationBackend | None = None,
    view: type[ModelView] = UserAdmin,
) -> TestClient:
    app = Starlette()
    admin = Admin(
        app=app,
        engine=engine,
        authentication_backend=SessionBackend(secret_key="secret"),
        authorization_backend=authorization_backend,
    )
    admin.add_view(view)
    admin.add_view(CustomPage)
    return TestClient(app=app, base_url="http://testserver")


@pytest.fixture(autouse=True, scope="module")
def prepare_database() -> Generator[None, None, None]:
    Base.metadata.create_all(engine)
    with session_maker() as session:
        session.add(AuthzUser(name="Bob"))
        session.add(ReadonlyUser(name="Bob"))
        session.add(ClosedUser(name="Bob"))
        session.add(OpenUser(name="Bob"))
        session.add(RowUser(name="Bob"))
        session.commit()
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with build_client(HeaderAuthorization()) as c:
        yield c


def grants(*items: str) -> dict[str, str]:
    return {"x-grants": ",".join(items)}


# Matcher ------------------------------------------------------------------


@pytest.mark.parametrize(
    "grant_set, identity, action_name, expected",
    [
        ({("user", "edit")}, "user", "edit", True),
        ({("user", "edit")}, "user", "delete", False),
        ({("user", "edit")}, "movie", "edit", False),
        ({("*", "edit")}, "movie", "edit", True),
        ({("user", "*")}, "user", "delete", True),
        ({("*", "*")}, "anything", "whatever", True),
        (set(), "user", "edit", False),
    ],
)
def test_matches_grant(
    grant_set: set, identity: str, action_name: str, expected: bool
) -> None:
    assert matches_grant(grant_set, identity, action_name) is expected


def test_custom_action_name() -> None:
    assert custom_action("deactivate") == "action:deactivate"


def test_default_backend_allows_everything() -> None:
    backend = AuthorizationBackend()
    request: Any = None
    assert backend.has_permission(request, "user", "delete") is True
    assert backend.has_any_permission(request, "user") is True


def test_grants_backend_denies_when_load_never_ran() -> None:
    """A backend whose state is missing must fail closed, not open."""

    class Req:
        class state:  # noqa: N801
            pass

    backend = HeaderAuthorization()
    assert backend.has_permission(Req(), "user", "list") is False  # type: ignore[arg-type]


# Route guards -------------------------------------------------------------


def test_no_backend_configured_changes_nothing() -> None:
    with build_client() as client:
        assert client.get("/admin/authz-user/list").status_code == 200
        assert client.get("/admin/authz-user/create").status_code == 200


def test_list_requires_list_grant(client: TestClient) -> None:
    assert client.get("/admin/authz-user/list", headers=grants()).status_code == 403
    assert (
        client.get(
            "/admin/authz-user/list", headers=grants("authz-user:list")
        ).status_code
        == 200
    )


def test_create_requires_create_grant(client: TestClient) -> None:
    assert (
        client.get(
            "/admin/authz-user/create", headers=grants("authz-user:list")
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/admin/authz-user/create", headers=grants("authz-user:create")
        ).status_code
        == 200
    )


def test_details_and_edit_require_their_own_grants(client: TestClient) -> None:
    assert (
        client.get(
            "/admin/authz-user/details/1", headers=grants("authz-user:edit")
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/admin/authz-user/details/1", headers=grants("authz-user:details")
        ).status_code
        == 200
    )
    assert (
        client.get(
            "/admin/authz-user/edit/1", headers=grants("authz-user:details")
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/admin/authz-user/edit/1", headers=grants("authz-user:edit")
        ).status_code
        == 200
    )


def test_export_requires_export_grant(client: TestClient) -> None:
    assert (
        client.get(
            "/admin/authz-user/export/csv", headers=grants("authz-user:list")
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/admin/authz-user/export/csv", headers=grants("authz-user:export")
        ).status_code
        == 200
    )


def test_delete_requires_delete_grant(client: TestClient) -> None:
    assert (
        client.delete(
            "/admin/authz-user/delete?pks=1", headers=grants("authz-user:list")
        ).status_code
        == 403
    )


def test_wildcards_apply_to_routes(client: TestClient) -> None:
    assert (
        client.get("/admin/authz-user/list", headers=grants("*:*")).status_code == 200
    )
    assert (
        client.get(
            "/admin/authz-user/create", headers=grants("authz-user:*")
        ).status_code
        == 200
    )


def test_superuser_bypasses_grants(client: TestClient) -> None:
    response = client.get("/admin/authz-user/create", headers={"x-superuser": "1"})
    assert response.status_code == 200


def test_index_is_reachable_without_any_grant(client: TestClient) -> None:
    """The dashboard itself is not gated -- it just renders an empty menu."""

    response = client.get("/admin/", headers=grants())
    assert response.status_code == 200
    assert "/admin/authz-user/list" not in response.text


def test_menu_shows_view_with_any_grant(client: TestClient) -> None:
    response = client.get("/admin/", headers=grants("authz-user:details"))
    assert "/admin/authz-user/list" in response.text


# Custom actions and custom views -----------------------------------------


def test_custom_action_requires_its_own_grant(client: TestClient) -> None:
    assert (
        client.get(
            "/admin/authz-user/action/ping", headers=grants("authz-user:edit")
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/admin/authz-user/action/ping",
            headers=grants("authz-user:action:ping"),
        ).status_code
        == 200
    )


def test_unauthorized_action_button_is_not_rendered(client: TestClient) -> None:
    response = client.get("/admin/authz-user/list", headers=grants("authz-user:list"))
    assert "action/ping" not in response.text

    response = client.get(
        "/admin/authz-user/list",
        headers=grants("authz-user:list", "authz-user:action:ping"),
    )
    assert "action/ping" in response.text


def test_base_view_requires_grant(client: TestClient) -> None:
    assert client.get("/admin/custom-page", headers=grants()).status_code == 403
    assert client.get("/admin/custom-page", headers=grants("page:*")).status_code == 200


# Interaction with can_* flags and view overrides --------------------------


def test_can_flag_overrules_grant() -> None:
    class ReadOnlyUserAdmin(ModelView, model=ReadonlyUser):
        can_edit = False

    with build_client(HeaderAuthorization(), view=ReadOnlyUserAdmin) as client:
        response = client.get("/admin/readonly-user/edit/1", headers=grants("*:*"))
        assert response.status_code == 403


def test_view_override_wins_over_backend() -> None:
    class ClosedUserAdmin(ModelView, model=ClosedUser):
        def is_accessible(self, request: Request) -> bool:
            return False

    with build_client(HeaderAuthorization(), view=ClosedUserAdmin) as client:
        assert (
            client.get("/admin/closed-user/list", headers=grants("*:*")).status_code
            == 403
        )


def test_view_override_can_grant_more_than_backend() -> None:
    class OpenUserAdmin(ModelView, model=OpenUser):
        def is_accessible(self, request: Request) -> bool:
            return True

        async def check_can_list(self, request: Request) -> bool:
            return True

    with build_client(HeaderAuthorization(), view=OpenUserAdmin) as client:
        assert client.get("/admin/open-user/list", headers=grants()).status_code == 200


def test_row_level_permission_uses_obj() -> None:
    class OwnerAuthorization(AuthorizationBackend):
        def has_permission(
            self,
            request: Request,
            identity: str,
            action: str,
            obj: Any | None = None,
        ) -> bool:
            if obj is not None:
                return obj.name == "Alice"
            return True

    class RowUserAdmin(ModelView, model=RowUser):
        pass

    with build_client(OwnerAuthorization(), view=RowUserAdmin) as client:
        # The seeded row is named Bob, so per-row checks deny it.
        assert client.get("/admin/row-user/edit/1").status_code == 403
        # Row-less pages are unaffected.
        assert client.get("/admin/row-user/list").status_code == 200


def test_has_any_permission_covers_every_action() -> None:
    seen = []

    class RecordingBackend(AuthorizationBackend):
        def has_permission(
            self,
            request: Request,
            identity: str,
            action: str,
            obj: Any | None = None,
        ) -> bool:
            seen.append(action)
            return False

    RecordingBackend().has_any_permission(None, "user")  # type: ignore[arg-type]
    assert seen == list(ACTIONS)
