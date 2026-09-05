from collections.abc import AsyncGenerator, Generator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Boolean, Column, Integer, String
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.testclient import TestClient

from sqladmin import Admin, BaseView, action, expose
from sqladmin.authentication import AuthenticationBackend
from sqladmin.contrib.rbac import (
    DBAuthorizationBackend,
    GroupAccessMixin,
    GroupAdmin,
    GroupMixin,
    build_permission_rows,
    user_group_table,
)
from sqladmin.models import ModelView
from tests.common import async_engine
from tests.common import sync_engine as engine

Base = declarative_base()
session_maker = sessionmaker(bind=engine, class_=Session)


class Group(GroupMixin, Base):
    __tablename__ = "admin_groups"


class GroupAccess(GroupAccessMixin, Base):
    __tablename__ = "admin_group_accesses"


UserGroup = user_group_table(Base, user_table="rbac_users")


class RbacUser(Base):
    __tablename__ = "rbac_users"

    id = Column(Integer, primary_key=True)
    name = Column(String)
    is_superuser = Column(Boolean, default=False)

    groups = relationship("Group", secondary=UserGroup)


class Article(Base):
    __tablename__ = "rbac_articles"

    id = Column(Integer, primary_key=True)
    title = Column(String)


class HeaderUserBackend(AuthenticationBackend):
    """Identifies the user from a header rather than a session."""

    async def login(self, request: Request) -> bool:  # pragma: no cover
        return True

    async def logout(self, request: Request) -> bool:  # pragma: no cover
        return True

    async def authenticate(self, request: Request) -> bool:
        return True

    async def get_user_id(self, request: Request) -> Any:
        raw = request.headers.get("x-user-id")
        return int(raw) if raw else None


class ArticleAdmin(ModelView, model=Article):
    can_import = True

    @action(name="publish", label="Publish")
    async def publish(self, request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})


class ReportsPage(BaseView):
    name = "Reports"

    @expose("/reports", methods=["GET"])
    async def reports(self, request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})


class MyGroupAdmin(GroupAdmin, model=Group):
    access_model = GroupAccess


@pytest.fixture(autouse=True, scope="module")
def prepare_database() -> Generator[None, None, None]:
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def clean_tables() -> Generator[None, None, None]:
    yield
    with session_maker() as session:
        session.execute(UserGroup.delete())
        session.query(GroupAccess).delete()
        session.query(Group).delete()
        session.query(RbacUser).delete()
        session.query(Article).delete()
        session.commit()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    app = Starlette()
    admin = Admin(
        app=app,
        engine=engine,
        authentication_backend=HeaderUserBackend(secret_key="secret"),
        authorization_backend=DBAuthorizationBackend(
            session_maker, user_model=RbacUser
        ),
    )
    admin.add_view(ArticleAdmin)
    admin.add_view(ReportsPage)
    admin.add_view(MyGroupAdmin)
    with TestClient(app=app, base_url="http://testserver") as c:
        yield c


def make_user(
    *grants: str,
    is_superuser: bool = False,
    user_id: int = 1,
) -> int:
    """Create a user in one group holding ``grants``."""

    with session_maker() as session:
        user = RbacUser(id=user_id, name="Test", is_superuser=is_superuser)
        group = Group(name=f"group-{user_id}")
        for grant in grants:
            identity, _, action_name = grant.partition(":")
            group.accesses.append(GroupAccess(identity=identity, action=action_name))
        user.groups.append(group)
        session.add(user)
        session.commit()
    return user_id


def as_user(user_id: int) -> dict[str, str]:
    return {"x-user-id": str(user_id)}


# Grant resolution ---------------------------------------------------------


def test_anonymous_user_has_no_grants(client: TestClient) -> None:
    assert client.get("/admin/article/list").status_code == 403


def test_user_without_groups_has_no_grants(client: TestClient) -> None:
    with session_maker() as session:
        session.add(RbacUser(id=1, name="Test"))
        session.commit()

    assert client.get("/admin/article/list", headers=as_user(1)).status_code == 403


def test_grant_from_group_allows_route(client: TestClient) -> None:
    make_user("article:list")

    assert client.get("/admin/article/list", headers=as_user(1)).status_code == 200
    assert client.get("/admin/article/create", headers=as_user(1)).status_code == 403


def test_grants_from_multiple_groups_are_merged(client: TestClient) -> None:
    with session_maker() as session:
        user = RbacUser(id=1, name="Test")
        readers = Group(
            name="readers", accesses=[GroupAccess(identity="article", action="list")]
        )
        writers = Group(
            name="writers", accesses=[GroupAccess(identity="article", action="create")]
        )
        user.groups.extend([readers, writers])
        session.add(user)
        session.commit()

    assert client.get("/admin/article/list", headers=as_user(1)).status_code == 200
    assert client.get("/admin/article/create", headers=as_user(1)).status_code == 200


def test_superuser_bypasses_grants(client: TestClient) -> None:
    make_user(is_superuser=True)

    assert client.get("/admin/article/list", headers=as_user(1)).status_code == 200
    assert client.get("/admin/article/create", headers=as_user(1)).status_code == 200


def test_wildcard_grant(client: TestClient) -> None:
    make_user("*:*")

    assert client.get("/admin/article/list", headers=as_user(1)).status_code == 200
    assert client.get("/admin/reports", headers=as_user(1)).status_code == 200


def test_grants_are_reread_each_request(client: TestClient) -> None:
    """Changing the database changes what the next request may do."""

    make_user("article:list")
    assert client.get("/admin/article/create", headers=as_user(1)).status_code == 403

    with session_maker() as session:
        group = session.query(Group).one()
        group.accesses.append(GroupAccess(identity="article", action="create"))
        session.commit()

    assert client.get("/admin/article/create", headers=as_user(1)).status_code == 200


def test_custom_action_grant(client: TestClient) -> None:
    make_user("article:action:publish")

    assert (
        client.get("/admin/article/action/publish", headers=as_user(1)).status_code
        == 200
    )


def test_backend_requires_user_model() -> None:
    with pytest.raises(ValueError, match="requires a user_model"):
        DBAuthorizationBackend(session_maker)


def test_backend_validates_relationship_names() -> None:
    with pytest.raises(ValueError, match="no relationship named 'teams'"):
        DBAuthorizationBackend(session_maker, user_model=RbacUser, groups_attr="teams")


def test_audit_actor_defaults_to_authentication_user_id(client: TestClient) -> None:
    """`get_user_id` feeds the audit trail as well as authorization."""

    from sqladmin.audit import AuditEntry, DBAuditBackend

    captured = {}

    class Backend(DBAuditBackend):
        def build_row(self, entry: AuditEntry, actor: Any, request: Request) -> Any:
            captured["actor"] = actor
            return None

        async def log(self, entry: AuditEntry, request: Request) -> None:
            self.build_row(entry, await self.get_actor(request), request)

    make_user("article:create")

    app = Starlette()
    admin = Admin(
        app=app,
        engine=engine,
        authentication_backend=HeaderUserBackend(secret_key="secret"),
        authorization_backend=DBAuthorizationBackend(
            session_maker, user_model=RbacUser
        ),
        audit_backend=Backend(session_maker),
    )
    admin.add_view(ArticleAdmin)

    with TestClient(app=app, base_url="http://testserver") as c:
        c.post("/admin/article/create", data={"title": "x"}, headers=as_user(1))

    assert captured["actor"] == 1


# Permission matrix --------------------------------------------------------


def test_permission_rows_are_built_from_registered_views(client: TestClient) -> None:
    rows = build_permission_rows(MyGroupAdmin._admin_ref)
    by_identity = {row.identity: row for row in rows}

    assert set(by_identity) == {"article", "reports", "group"}

    article = by_identity["article"]
    values = [choice.value for choice in article.choices]
    assert "article:list" in values
    assert "article:import" in values  # can_import = True on this view
    assert "article:action:publish" in values

    # Custom pages get a single grant that opens them.
    assert [c.value for c in by_identity["reports"].choices] == ["reports:*"]


def test_permission_rows_skip_disabled_actions(client: TestClient) -> None:
    rows = build_permission_rows(MyGroupAdmin._admin_ref)
    group_row = next(row for row in rows if row.identity == "group")

    # can_import defaults to False, so no import checkbox is offered.
    assert "group:import" not in [choice.value for choice in group_row.choices]


def test_group_admin_creates_permissions(client: TestClient) -> None:
    make_user(is_superuser=True)

    response = client.post(
        "/admin/group/create",
        data={"name": "editors", "permissions": ["article:list", "article:edit"]},
        headers=as_user(1),
        follow_redirects=False,
    )
    assert response.status_code == 302

    with session_maker() as session:
        group = session.query(Group).filter(Group.name == "editors").one()
        assert {(a.identity, a.action) for a in group.accesses} == {
            ("article", "list"),
            ("article", "edit"),
        }


def test_group_admin_edits_permissions(client: TestClient) -> None:
    make_user(is_superuser=True)

    with session_maker() as session:
        group = Group(
            name="editors",
            accesses=[
                GroupAccess(identity="article", action="list"),
                GroupAccess(identity="article", action="delete"),
            ],
        )
        session.add(group)
        session.commit()
        group_id = group.id

    # The edit form arrives with the current grants ticked.
    response = client.get(f"/admin/group/edit/{group_id}", headers=as_user(1))
    assert (
        'value="article:list" id="permissions-article:list" checked>' in response.text
    )
    assert 'value="article:create" id="permissions-article:create">' in response.text

    response = client.post(
        f"/admin/group/edit/{group_id}",
        data={"name": "editors", "permissions": ["article:list", "article:create"]},
        headers=as_user(1),
        follow_redirects=False,
    )
    assert response.status_code == 302

    with session_maker() as session:
        group = session.query(Group).filter(Group.id == group_id).one()
        assert {(a.identity, a.action) for a in group.accesses} == {
            ("article", "list"),
            ("article", "create"),
        }


def test_group_admin_rejects_unknown_permission(client: TestClient) -> None:
    """A forged permission string is not a valid choice, so validation fails."""

    make_user(is_superuser=True)

    response = client.post(
        "/admin/group/create",
        data={"name": "sneaky", "permissions": ["article:sudo"]},
        headers=as_user(1),
        follow_redirects=False,
    )
    assert response.status_code == 400

    with session_maker() as session:
        assert session.query(Group).filter(Group.name == "sneaky").count() == 0


def test_group_admin_clears_permissions(client: TestClient) -> None:
    make_user(is_superuser=True)

    with session_maker() as session:
        group = Group(
            name="editors",
            accesses=[GroupAccess(identity="article", action="list")],
        )
        session.add(group)
        session.commit()
        group_id = group.id

    client.post(
        f"/admin/group/edit/{group_id}",
        data={"name": "editors"},
        headers=as_user(1),
        follow_redirects=False,
    )

    with session_maker() as session:
        group = session.query(Group).filter(Group.id == group_id).one()
        assert group.accesses == []


def test_group_admin_requires_access_model() -> None:
    class Broken(GroupAdmin, model=Group):
        pass

    with pytest.raises(ValueError, match="access_model must be set"):
        Broken()._require_access_model()


# Async engine -------------------------------------------------------------


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    async_session_maker = async_sessionmaker(
        bind=async_engine, class_=AsyncSession, expire_on_commit=False
    )

    app = Starlette()
    admin = Admin(
        app=app,
        engine=async_engine,
        authentication_backend=HeaderUserBackend(secret_key="secret"),
        authorization_backend=DBAuthorizationBackend(
            async_session_maker, user_model=RbacUser
        ),
    )
    admin.add_view(ArticleAdmin)
    admin.add_view(MyGroupAdmin)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c

    # Each test runs in its own event loop; pooled connections must not outlive
    # it, or the next one fails with "another operation is in progress".
    await async_engine.dispose()


@pytest.mark.anyio
async def test_async_engine_resolves_grants(async_client: AsyncClient) -> None:
    make_user("article:list")

    response = await async_client.get("/admin/article/list", headers=as_user(1))
    assert response.status_code == 200

    response = await async_client.get("/admin/article/create", headers=as_user(1))
    assert response.status_code == 403


@pytest.mark.anyio
async def test_async_engine_superuser(async_client: AsyncClient) -> None:
    make_user(is_superuser=True)

    response = await async_client.get("/admin/article/create", headers=as_user(1))
    assert response.status_code == 200


@pytest.mark.anyio
async def test_async_engine_stores_permissions(async_client: AsyncClient) -> None:
    make_user(is_superuser=True)

    response = await async_client.post(
        "/admin/group/create",
        data={"name": "editors", "permissions": ["article:list"]},
        headers=as_user(1),
        follow_redirects=False,
    )
    assert response.status_code == 302

    with session_maker() as session:
        group = session.query(Group).filter(Group.name == "editors").one()
        assert {(a.identity, a.action) for a in group.accesses} == {("article", "list")}


def test_permission_matrix_renders_real_markup(client: TestClient) -> None:
    """The widget emits markup, not an escaped string of it.

    ``Markup`` is built only from string literals here and every value goes
    through ``Markup.format``; escaping the assembled table instead would show
    the raw tags to the user.
    """

    make_user(is_superuser=True)

    response = client.get("/admin/group/create", headers=as_user(1))

    assert '<table class="table table-sm table-vcenter permission-matrix">' in (
        response.text
    )
    assert "&lt;input" not in response.text
    assert "&lt;table" not in response.text


def test_permission_matrix_escapes_view_names() -> None:
    """A view whose name contains markup is escaped, not rendered."""

    from wtforms import Form as WTForm

    from sqladmin.contrib.rbac import PermissionMatrixField, _ActionChoice, _ViewRow

    rows = [
        _ViewRow(
            identity="x",
            label="<script>alert(1)</script>",
            standard=[_ActionChoice("x:list", "list")],
        )
    ]

    class MatrixForm(WTForm):
        permissions = PermissionMatrixField(rows=rows)

    rendered = str(MatrixForm().permissions())

    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered
    # The surrounding table is still real markup.
    assert '<input type="checkbox"' in rendered
