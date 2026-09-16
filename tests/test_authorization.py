from collections.abc import Generator
from typing import Any

import pytest
from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.testclient import TestClient

from sqladmin import Admin, BaseView, action, expose
from sqladmin.authentication import AuthenticationBackend
from sqladmin.authorization import (
    ACTIONS,
    Action,
    AllowAllAuthorizationBackend,
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


class SaveAsUser(Base):
    __tablename__ = "authz_save_as_users"

    id = Column(Integer, primary_key=True)
    name = Column(String)


class AuthzPost(Base):
    __tablename__ = "authz_posts"

    id = Column(Integer, primary_key=True)
    author_id = Column(Integer, ForeignKey("authz_users.id"))
    author = relationship("AuthzUser")


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
        if request.headers.get("x-superuser") == "1":
            return {("*", "*")}
        raw = request.headers.get("x-grants", "")
        grants = set()
        for item in filter(None, raw.split(",")):
            identity, _, action_name = item.partition(":")
            grants.add((identity, action_name))
        return grants


class UserAdmin(ModelView, model=AuthzUser):
    @action(name="ping")
    async def ping(self, request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})


class CustomPage(BaseView):
    name = "Custom Page"

    @expose("/custom-page", methods=["GET"])
    async def page(self, request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})


class PostAdmin(ModelView, model=AuthzPost):
    form_ajax_refs = {"author": {"fields": ("name",)}}


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
    admin.add_view(PostAdmin)
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
        session.add(SaveAsUser(name="Bob"))
        session.commit()
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with build_client(HeaderAuthorization()) as c:
        yield c


def grants(*items: str) -> dict[str, str]:
    return {"x-grants": ",".join(items)}


def make_request() -> Request:
    return Request({"type": "http", "headers": []})


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


def test_default_backend_allows_everything() -> None:
    backend = AllowAllAuthorizationBackend()
    request: Any = None
    assert backend.has_permission(request, "user", "delete") is True

    admin = Admin(app=Starlette(), engine=engine)
    assert isinstance(admin.authorization_backend, AllowAllAuthorizationBackend)


def test_incomplete_backends_cannot_be_instantiated() -> None:
    class NoHasPermission(AuthorizationBackend):
        pass

    class NoGetGrants(GrantsAuthorizationBackend):
        pass

    with pytest.raises(TypeError, match="has_permission"):
        NoHasPermission()  # type: ignore[abstract]
    with pytest.raises(TypeError, match="get_grants"):
        NoGetGrants()  # type: ignore[abstract]


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


def test_menu_links_to_list_when_listing_is_granted(client: TestClient) -> None:
    response = client.get("/admin/", headers=grants("authz-user:list"))
    assert "/admin/authz-user/list" in response.text


@pytest.mark.parametrize("granted", ["create", "import", "export"])
def test_menu_links_to_list_for_page_level_actions(
    client: TestClient, granted: str
) -> None:
    class ImportableUserAdmin(UserAdmin):
        can_import = True

    with build_client(HeaderAuthorization(), view=ImportableUserAdmin) as c:
        response = c.get("/admin/", headers=grants(f"authz-user:{granted}"))
    assert "/admin/authz-user/list" in response.text


def test_menu_follows_is_accessible_only(client: TestClient) -> None:
    # Any grant makes the view accessible; hiding it is up to ``is_accessible``.
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


@pytest.mark.parametrize(
    "granted, expected",
    [
        ((), 403),
        (("page:edit",), 403),
        (("page:details", "page:create"), 403),
        (("page:list",), 200),
        (("*:list",), 200),
        (("page:*",), 200),
    ],
)
def test_base_view_requires_list_grant(
    client: TestClient, granted: tuple[str, ...], expected: int
) -> None:
    response = client.get("/admin/custom-page", headers=grants(*granted))
    assert response.status_code == expected


# Interaction with can_* flags and view overrides --------------------------


@pytest.mark.parametrize(
    "granted",
    [("*:import",), ("authz-user:import",), ("closed-user:export",)],
)
def test_grants_for_disabled_actions_do_not_open_a_view(
    granted: tuple[str, ...],
) -> None:
    class NoExportUserAdmin(ModelView, model=ClosedUser):
        can_export = False

    app = Starlette()
    admin = Admin(
        app=app,
        engine=engine,
        authentication_backend=SessionBackend(secret_key="secret"),
        authorization_backend=HeaderAuthorization(),
    )
    admin.add_view(UserAdmin)  # can_import is False by default
    admin.add_view(NoExportUserAdmin)

    with TestClient(app=app) as client:
        index = client.get("/admin/", headers=grants(*granted))
        assert "/admin/authz-user/list" not in index.text
        assert "/admin/closed-user/list" not in index.text
        for path in ("/admin/authz-user/list", "/admin/closed-user/list"):
            assert client.get(path, headers=grants(*granted)).status_code == 403


def test_every_action_has_a_flag_entry() -> None:
    from sqladmin.models import _ACTION_FLAGS

    assert list(_ACTION_FLAGS) == list(ACTIONS)


def test_can_flag_overrules_grant() -> None:
    class ReadOnlyUserAdmin(ModelView, model=ReadonlyUser):
        can_edit = False

    with build_client(HeaderAuthorization(), view=ReadOnlyUserAdmin) as client:
        response = client.get("/admin/readonly-user/edit/1", headers=grants("*:*"))
        assert response.status_code == 403


class SaveAsUserAdmin(ModelView, model=SaveAsUser):
    save_as = True


def _save_as_new(client: TestClient, *granted: str) -> int:
    return client.post(
        "/admin/save-as-user/edit/1",
        data={"name": "Copy", "save": "Save as new"},
        headers=grants(*granted),
        follow_redirects=False,
    ).status_code


def test_save_as_new_requires_create_grant() -> None:
    with build_client(HeaderAuthorization(), view=SaveAsUserAdmin) as client:
        response = client.get(
            "/admin/save-as-user/edit/1", headers=grants("save-as-user:edit")
        )
        assert "Save as new" not in response.text
        assert _save_as_new(client, "save-as-user:edit") == 403

        response = client.get(
            "/admin/save-as-user/edit/1",
            headers=grants("save-as-user:edit", "save-as-user:create"),
        )
        assert "Save as new" in response.text
        assert _save_as_new(client, "save-as-user:edit", "save-as-user:create") == 302


def test_save_as_new_respects_can_create() -> None:
    class NoCreateAdmin(SaveAsUserAdmin):
        can_create = False

    with session_maker() as session:
        before = session.query(SaveAsUser).count()

    with build_client(view=NoCreateAdmin) as client:
        assert "Save as new" not in client.get("/admin/save-as-user/edit/1").text
        assert _save_as_new(client) == 403

    with session_maker() as session:
        assert session.query(SaveAsUser).count() == before


def test_can_import_flag_overrules_check_override() -> None:
    class NoImportAdmin(ModelView, model=OpenUser):
        can_import = False

        async def check_can_import(self, request: Request) -> bool:
            return True

    with build_client(view=NoImportAdmin) as client:
        response = client.post(
            "/admin/open-user/import",
            files={"file": ("users.csv", b"name\nAlice\n", "text/csv")},
        )
        assert response.status_code == 403


def test_login_required_without_authorization_backend_attribute() -> None:
    from sqladmin.authentication import login_required

    class PlainAdmin:
        authentication_backend = None

        @login_required
        async def page(self, request: Request) -> str:
            return "ok"

    import anyio

    assert anyio.run(PlainAdmin().page, make_request()) == "ok"


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
        # The menu cannot await the override, so it keeps the link.
        assert "/admin/open-user/list" in client.get("/admin/", headers=grants()).text


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


def test_is_accessible_asks_about_every_enabled_action() -> None:
    seen = []

    class RecordingBackend(AuthorizationBackend):
        def has_permission(
            self,
            request: Request,
            identity: str,
            action: str,
            obj: Any | None = None,
        ) -> bool:
            seen.append((identity, action))
            return False

    class RecordingUserAdmin(UserAdmin):
        pass

    app = Starlette()
    admin = Admin(app=app, engine=engine, authorization_backend=RecordingBackend())
    admin.add_view(RecordingUserAdmin)
    view = admin.views[0]

    assert view.is_accessible(make_request()) is False
    # ``import`` is off (``can_import = False``), so it is not asked about.
    assert seen == [
        ("authz-user", action) for action in [*ACTIONS[:-1], custom_action("ping")]
    ]


def test_is_accessible_stops_at_first_allowed_action() -> None:
    seen = []

    class FirstOnly(AuthorizationBackend):
        def has_permission(
            self,
            request: Request,
            identity: str,
            action: str,
            obj: Any | None = None,
        ) -> bool:
            seen.append(action)
            return True

    app = Starlette()
    admin = Admin(app=app, engine=engine, authorization_backend=FirstOnly())
    admin.add_view(UserAdmin)

    assert admin.views[0].is_accessible(make_request()) is True
    assert seen == [ACTIONS[0]]


def test_is_accessible_is_answered_once_per_request() -> None:
    calls = []

    class Counting(AuthorizationBackend):
        def has_permission(
            self,
            request: Request,
            identity: str,
            action: str,
            obj: Any | None = None,
        ) -> bool:
            calls.append(action)
            return action == "export"

    app = Starlette()
    admin = Admin(app=app, engine=engine, authorization_backend=Counting())
    admin.add_view(UserAdmin)
    view = admin.views[0]
    request = make_request()

    assert view.is_accessible(request) is True
    asked = len(calls)
    assert view.is_accessible(request) is True
    assert len(calls) == asked

    # A new request asks again.
    view.is_accessible(make_request())
    assert len(calls) == 2 * asked


# Action names ---------------------------------------------------------------


def test_action_members_are_their_string_values() -> None:
    assert Action.EDIT == "edit"
    assert f"user:{Action.EDIT}" == "user:edit"
    assert str(Action.IMPORT) == "import"
    assert ("user", Action.EDIT) in {("user", "edit")}
    assert ("user", "edit") in {("user", Action.EDIT)}
    assert "edit" in ACTIONS
    assert matches_grant({("user", Action.EDIT)}, "user", "edit")


def test_grants_may_use_action_members() -> None:
    class EnumGrants(GrantsAuthorizationBackend):
        async def get_grants(self, request: Request) -> set:
            return {("authz-user", Action.LIST)}

    with build_client(EnumGrants()) as client:
        assert client.get("/admin/authz-user/list").status_code == 200
        assert client.get("/admin/authz-user/create").status_code == 403


def test_grants_are_loaded_once_per_request() -> None:
    calls = []

    class Counting(GrantsAuthorizationBackend):
        async def get_grants(self, request: Request) -> set:
            calls.append(request.url.path)
            return {("*", "*")}

    with build_client(Counting()) as client:
        assert client.get("/admin/authz-user/list").status_code == 200
    assert calls == ["/admin/authz-user/list"]


def test_views_outside_an_admin_allow_everything() -> None:
    class UnregisteredPage(BaseView):
        identity = "unregistered"

    view = UnregisteredPage()
    assert not hasattr(view, "_admin_ref")
    assert view.has_permission(make_request(), "delete")
    assert view.is_accessible(make_request())


# List page for users who may not list -----------------------------------------


def test_list_page_without_list_grant_shows_toolbar_only(client: TestClient) -> None:
    response = client.get("/admin/authz-user/list", headers=grants("authz-user:create"))
    assert response.status_code == 200
    assert "You are not authorized to view these records." in response.text
    assert "/admin/authz-user/create" in response.text
    # No rows, no table, no bulk actions, no search.
    assert "<td" not in response.text
    assert "<table" not in response.text
    assert 'id="select-all"' not in response.text
    assert 'id="search-input"' not in response.text
    assert "Showing" not in response.text


def test_list_page_without_list_grant_does_not_query(client: TestClient) -> None:
    class NoQueryUserAdmin(UserAdmin):
        async def list(self, request: Request):  # type: ignore[override]
            raise AssertionError("rows must not be loaded")

    with build_client(HeaderAuthorization(), view=NoQueryUserAdmin) as c:
        response = c.get("/admin/authz-user/list", headers=grants("authz-user:create"))
    assert response.status_code == 200


def test_list_page_without_list_grant_offers_import_and_export() -> None:
    class ImportableUserAdmin(UserAdmin):
        can_import = True

    with build_client(HeaderAuthorization(), view=ImportableUserAdmin) as client:
        response = client.get(
            "/admin/authz-user/list", headers=grants("authz-user:import")
        )
        assert response.status_code == 200
        assert 'id="action-import"' in response.text
        assert "/admin/authz-user/create" not in response.text
        assert "/admin/authz-user/export/" not in response.text

        response = client.get(
            "/admin/authz-user/list", headers=grants("authz-user:export")
        )
        assert response.status_code == 200
        assert "/admin/authz-user/export/csv" in response.text
        assert 'id="action-import"' not in response.text


def test_list_page_without_any_page_level_grant_is_empty(
    client: TestClient,
) -> None:
    for granted in ("authz-user:details", "authz-user:edit", "authz-user:delete"):
        response = client.get("/admin/authz-user/list", headers=grants(granted))
        assert response.status_code == 200, granted
        assert "You are not authorized to view these records." in response.text
        assert "<table" not in response.text
        assert "/admin/authz-user/create" not in response.text
        assert "/admin/authz-user/export/" not in response.text
        assert 'id="action-import"' not in response.text
        assert 'id="dropdownMenuButton"' not in response.text


def test_list_page_is_forbidden_when_view_is_inaccessible(
    client: TestClient,
) -> None:
    assert client.get("/admin/authz-user/list", headers=grants()).status_code == 403


def test_list_template_rendered_without_can_list_shows_rows() -> None:
    """Custom routes rendering ``list.html`` without ``can_list`` still work."""

    class LegacyListPage(BaseView):
        name = "Legacy"

        @expose("/legacy-list", methods=["GET"], identity="legacy-list")
        async def legacy(self, request: Request) -> Any:
            model_view = next(
                v for v in self._admin_ref.views if v.identity == "authz-user"
            )
            return await self.templates.TemplateResponse(
                request,
                "sqladmin/list.html",
                {
                    "model_view": model_view,
                    "pagination": await model_view.list(request),
                },
            )

    app = Starlette()
    admin = Admin(app=app, engine=engine)
    admin.add_view(UserAdmin)
    admin.add_view(LegacyListPage)
    with TestClient(app=app) as client:
        response = client.get("/admin/legacy-list")
    assert response.status_code == 200
    assert "<td>1</td>" in response.text
    assert "not authorized" not in response.text


def test_save_without_list_grant_returns_to_list_page(client: TestClient) -> None:
    response = client.post(
        "/admin/authz-user/create",
        data={"name": "Carol", "save": "Save"},
        headers=grants("authz-user:create"),
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["location"] == "http://testserver/admin/authz-user/list"


def test_cancel_and_continue_editing_follow_grants(client: TestClient) -> None:
    response = client.get(
        "/admin/authz-user/create", headers=grants("authz-user:create")
    )
    assert "Save and continue editing" not in response.text
    assert "/admin/authz-user/list" in response.text

    response = client.get(
        "/admin/authz-user/create",
        headers=grants("authz-user:create", "authz-user:edit"),
    )
    assert "Save and continue editing" in response.text


def test_back_link_and_delete_redirect_go_to_list(client: TestClient) -> None:
    response = client.get(
        "/admin/authz-user/details/1", headers=grants("authz-user:details")
    )
    assert response.status_code == 200
    assert 'href="http://testserver/admin/authz-user/list" class="btn"' in response.text

    with session_maker() as session:
        user = AuthzUser(name="Temp")
        session.add(user)
        session.commit()
        pk = user.id

    response = client.delete(
        f"/admin/authz-user/delete?pks={pk}", headers=grants("authz-user:delete")
    )
    assert response.status_code == 200
    assert response.text == "http://testserver/admin/authz-user/list"


# Ajax lookup ----------------------------------------------------------------


@pytest.mark.parametrize(
    "granted, expected",
    [
        (("authz-post:list",), 403),
        (("authz-post:details",), 403),
        (("authz-post:create",), 200),
        (("authz-post:edit",), 200),
    ],
)
def test_ajax_lookup_needs_a_form_permission(
    client: TestClient, granted: tuple[str, ...], expected: int
) -> None:
    response = client.get(
        "/admin/authz-post/ajax/lookup?name=author&term=Bob",
        headers=grants(*granted),
    )
    assert response.status_code == expected
