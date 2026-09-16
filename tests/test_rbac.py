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

from sqladmin import Admin, AuditBackend, AuditEntry, BaseView, action, expose
from sqladmin.authentication import AuthenticationBackend
from sqladmin.contrib.rbac import (
    DBAuthorizationBackend,
    GroupAccessMixin,
    GroupAdmin,
    GroupMixin,
    build_permission_rows,
    user_group_table,
)
from sqladmin.exceptions import InvalidRelationshipError
from sqladmin.models import ModelView
from tests.common import async_engine
from tests.common import sync_engine as engine

Base = declarative_base()
session_maker = sessionmaker(bind=engine, class_=Session)
async_session_maker = async_sessionmaker(
    bind=async_engine, class_=AsyncSession, expire_on_commit=False
)


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


PlainUserGroup = user_group_table(
    Base, user_table="rbac_plain_users", table_name="rbac_plain_user_groups"
)


class PlainUser(Base):
    """A user model without a superuser column."""

    __tablename__ = "rbac_plain_users"

    id = Column(Integer, primary_key=True)
    groups = relationship("Group", secondary=PlainUserGroup)


class CompositeUser(Base):
    __tablename__ = "rbac_composite_users"

    tenant = Column(Integer, primary_key=True)
    id = Column(Integer, primary_key=True)


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
    pass


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
        session.execute(PlainUserGroup.delete())
        session.query(PlainUser).delete()
        session.query(GroupAccess).delete()
        session.query(Group).delete()
        session.query(RbacUser).delete()
        session.query(Article).delete()
        session.commit()


def build_app(
    *views: type,
    is_async: bool = False,
    authenticated: bool = True,
    audit: AuditBackend | None = None,
) -> Starlette:
    """An admin wired to ``DBAuthorizationBackend``; all test views by default."""

    app = Starlette()
    admin = Admin(
        app=app,
        engine=async_engine if is_async else engine,
        authentication_backend=(
            HeaderUserBackend(secret_key="secret") if authenticated else None
        ),
        authorization_backend=DBAuthorizationBackend(
            async_session_maker if is_async else session_maker, user_model=RbacUser
        ),
        audit_backend=audit,
    )
    for view in views or (ArticleAdmin, ReportsPage, MyGroupAdmin):
        admin.add_view(view)
    return app


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app=build_app(), base_url="http://testserver") as c:
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


def test_backend_validates_relationship_names() -> None:
    with pytest.raises(InvalidRelationshipError, match="no relationship named 'teams'"):
        DBAuthorizationBackend(session_maker, user_model=RbacUser, groups_attr="teams")


def test_backend_rejects_composite_primary_keys() -> None:
    from sqladmin.exceptions import ImproperlyConfigured

    with pytest.raises(ImproperlyConfigured, match="single-column primary key"):
        DBAuthorizationBackend(session_maker, user_model=CompositeUser)


def _statements_during(func: Any) -> list[str]:
    from sqlalchemy import event

    statements: list[str] = []

    def record(conn, cursor, statement, *args):  # type: ignore[no-untyped-def]
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        func()
    finally:
        event.remove(engine, "before_cursor_execute", record)
    return statements


def test_grants_are_loaded_with_one_query(client: TestClient) -> None:
    make_user("article:list", "group:*")

    # The index page itself touches no tables, so every query is the lookup.
    statements = _statements_during(
        lambda: client.get("/admin/", headers=as_user(1)).raise_for_status()
    )
    assert len(statements) == 1


def test_user_model_without_superuser_column() -> None:
    with session_maker() as session:
        user = PlainUser(id=7)
        user.groups.append(
            Group(
                name="plain", accesses=[GroupAccess(identity="article", action="list")]
            )
        )
        session.add(user)
        session.commit()

    backend = DBAuthorizationBackend(session_maker, user_model=PlainUser)
    assert backend._load_grants_sync(7) == {("article", "list")}
    assert backend._load_grants_sync(8) == set()


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

    app = build_app(ArticleAdmin, audit=Backend(session_maker))
    with TestClient(app=app, base_url="http://testserver") as c:
        c.post("/admin/article/create", data={"title": "x"}, headers=as_user(1))

    assert captured["actor"] == 1


def test_db_backend_requires_an_authentication_backend() -> None:
    from sqladmin.exceptions import ImproperlyConfigured

    with pytest.raises(ImproperlyConfigured, match="authentication_backend="):
        build_app(ArticleAdmin, authenticated=False)


def test_grants_shared_by_several_groups_are_read_once() -> None:
    make_user("article:list")
    with session_maker() as session:
        user = session.get(RbacUser, 1)
        assert user is not None
        other = Group(name="other")
        other.accesses.append(GroupAccess(identity="article", action="list"))
        user.groups.append(other)
        session.commit()

    backend = DBAuthorizationBackend(session_maker, user_model=RbacUser)
    with session_maker() as session:
        rows = session.execute(backend._query_for(1)).all()
    assert rows == [(False, "article", "list")]


def test_db_backend_treats_anonymous_user_as_no_grants(client: TestClient) -> None:
    """A configured backend that finds no user is not a setup error."""

    assert client.get("/admin/article/list").status_code == 403


class RecordingAudit(AuditBackend):
    def __init__(self) -> None:
        self.entries: list[AuditEntry] = []

    async def log(self, entry: AuditEntry, request: Request) -> None:
        self.entries.append(entry)


def test_group_permission_changes_are_audited() -> None:
    make_user(is_superuser=True)
    group_id = _group_with(("*", "*"), ("article", "list"))
    audit = RecordingAudit()

    with TestClient(app=build_app(audit=audit)) as c:
        c.post(
            "/admin/group/create",
            data={"name": "new", "permissions": ["article:list"]},
            headers=as_user(1),
            follow_redirects=False,
        )
        c.post(
            f"/admin/group/edit/{group_id}",
            data={"name": "editors", "permissions": ["article:create"]},
            headers=as_user(1),
            follow_redirects=False,
        )
        c.post(
            f"/admin/group/edit/{group_id}",
            data={"name": "renamed"},
            headers=as_user(1),
            follow_redirects=False,
        )

    created, updated, renamed = audit.entries
    assert created.action == "create"
    assert created.changes == {"name": "new", "permissions": ["article:list"]}
    assert updated.action == "update"
    # The resulting grants, including ones the matrix does not show.
    assert updated.changes == {
        "name": "editors",
        "permissions": ["*:*", "article:create"],
    }
    assert renamed.changes == {"name": "renamed", "permissions": ["*:*"]}


def test_rejected_group_change_is_not_audited() -> None:
    make_user("group:*", user_id=2)
    audit = RecordingAudit()

    with TestClient(app=build_app(audit=audit)) as c:
        response = c.post(
            "/admin/group/create",
            data={"name": "sneaky", "permissions": ["article:delete"]},
            headers=as_user(2),
            follow_redirects=False,
        )
    assert response.status_code == 400
    assert audit.entries == []


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

    # Custom pages get a single grant that opens them: ``list``.
    assert [c.value for c in by_identity["reports"].choices] == ["reports:list"]


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


def test_group_admin_validates_accesses_attr() -> None:
    class Broken(GroupAdmin, model=Group):
        accesses_attr = "grants"

    # Fails when the view is added, not on the first edit.
    with pytest.raises(InvalidRelationshipError, match="relationship named 'grants'"):
        build_app(Broken)


def test_group_admin_derives_access_model() -> None:
    assert MyGroupAdmin()._access_model is GroupAccess


def _group_with(*grants: tuple[str, str], name: str = "editors") -> int:
    with session_maker() as session:
        group = Group(
            name=name,
            accesses=[GroupAccess(identity=i, action=a) for i, a in grants],
        )
        session.add(group)
        session.commit()
        return group.id


def _grants_of(group_id: int) -> set[tuple[str, str]]:
    with session_maker() as session:
        group = session.query(Group).filter(Group.id == group_id).one()
        return {(a.identity, a.action) for a in group.accesses}


def test_group_admin_keeps_grants_the_matrix_does_not_offer(
    client: TestClient,
) -> None:
    """Wildcards and grants for disabled actions survive an edit."""

    make_user(is_superuser=True)
    # ``article:sudo`` stands in for a grant whose action was since disabled.
    group_id = _group_with(
        ("*", "*"), ("article", "*"), ("article", "sudo"), ("article", "list")
    )

    response = client.post(
        f"/admin/group/edit/{group_id}",
        data={"name": "renamed", "permissions": ["article:create"]},
        headers=as_user(1),
        follow_redirects=False,
    )
    assert response.status_code == 302

    assert _grants_of(group_id) == {
        ("*", "*"),
        ("article", "*"),
        ("article", "sudo"),
        ("article", "create"),
    }


def test_group_editor_cannot_grant_what_they_lack(client: TestClient) -> None:
    make_user("group:*", "article:list")
    group_id = _group_with(("article", "list"))

    response = client.post(
        f"/admin/group/edit/{group_id}",
        data={"name": "editors", "permissions": ["article:list", "article:delete"]},
        headers=as_user(1),
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "You are not allowed to grant: Articles: Delete" in response.text
    assert _grants_of(group_id) == {("article", "list")}


def test_group_editor_may_revoke_what_they_lack(client: TestClient) -> None:
    """Removing grants cannot escalate, so it is not restricted."""

    make_user("group:*", "article:list")
    group_id = _group_with(("article", "list"), ("article", "delete"))

    response = client.post(
        f"/admin/group/edit/{group_id}",
        data={"name": "editors", "permissions": ["article:list"]},
        headers=as_user(1),
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert _grants_of(group_id) == {("article", "list")}


def test_group_editor_may_delete_group_with_grants_they_lack(
    client: TestClient,
) -> None:
    make_user("group:*")
    group_id = _group_with(("*", "*"), name="admins")

    response = client.delete(f"/admin/group/delete?pks={group_id}", headers=as_user(1))
    assert response.status_code == 200
    assert "error" not in response.text
    with session_maker() as session:
        assert session.query(Group).filter(Group.id == group_id).count() == 0


def test_can_grant_override_allows_delegation() -> None:
    class DelegatingGroupAdmin(MyGroupAdmin):
        def can_grant(self, request: Request, identity: str, action: str) -> bool:
            if identity == "article":
                return self.has_permission(request, "edit")
            return super().can_grant(request, identity, action)

    make_user("group:*")
    group_id = _group_with()

    with TestClient(build_app(ArticleAdmin, ReportsPage, DelegatingGroupAdmin)) as c:
        response = c.post(
            f"/admin/group/edit/{group_id}",
            data={"name": "editors", "permissions": ["article:delete"]},
            headers=as_user(1),
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert _grants_of(group_id) == {("article", "delete")}

        # Anything else still follows the default rule.
        response = c.post(
            f"/admin/group/edit/{group_id}",
            data={"name": "editors", "permissions": ["reports:list"]},
            headers=as_user(1),
            follow_redirects=False,
        )
        assert response.status_code == 400
        assert "Reports: Access" in response.text


def test_can_grant_is_asked_only_about_new_grants() -> None:
    asked: list[tuple[str, str]] = []

    class RecordingGroupAdmin(MyGroupAdmin):
        def can_grant(self, request: Request, identity: str, action: str) -> bool:
            asked.append((identity, action))
            return True

    make_user("group:*")
    group_id = _group_with(("article", "list"), ("article", "edit"))

    with TestClient(build_app(ArticleAdmin, ReportsPage, RecordingGroupAdmin)) as c:
        c.post(
            f"/admin/group/edit/{group_id}",
            data={"name": "editors", "permissions": ["article:list", "article:create"]},
            headers=as_user(1),
            follow_redirects=False,
        )

    assert asked == [("article", "create")]
    assert _grants_of(group_id) == {("article", "list"), ("article", "create")}


def test_group_editor_may_change_what_they_hold(client: TestClient) -> None:
    """Untouched grants the editor lacks are resubmitted as-is and allowed."""

    make_user("group:*", "article:list", "article:create")
    group_id = _group_with(("article", "list"), ("article", "delete"))

    response = client.post(
        f"/admin/group/edit/{group_id}",
        data={
            "name": "editors",
            "permissions": ["article:create", "article:delete"],
        },
        headers=as_user(1),
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert _grants_of(group_id) == {("article", "create"), ("article", "delete")}


def test_rejected_group_create_saves_nothing(client: TestClient) -> None:
    """The group and its grants share one transaction."""

    make_user("group:*")

    response = client.post(
        "/admin/group/create",
        data={"name": "sneaky", "permissions": ["article:delete"]},
        headers=as_user(1),
        follow_redirects=False,
    )
    assert response.status_code == 400

    with session_maker() as session:
        assert session.query(Group).filter(Group.name == "sneaky").count() == 0


def test_group_edit_form_does_not_set_permissions_attribute(
    client: TestClient,
) -> None:
    make_user(is_superuser=True)

    captured = {}

    class Recording(MyGroupAdmin):
        async def after_model_change(self, data, model, is_created, request):
            captured["has_attr"] = hasattr(model, "permissions")

    with TestClient(app=build_app(Recording)) as c:
        c.post(
            "/admin/group/create",
            data={"name": "g", "permissions": ["group:list"]},
            headers=as_user(1),
            follow_redirects=False,
        )
    assert captured == {"has_attr": False}


# Async engine -------------------------------------------------------------


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    app = build_app(ArticleAdmin, MyGroupAdmin, is_async=True)
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


@pytest.mark.anyio
async def test_async_engine_audits_group_permissions() -> None:
    make_user(is_superuser=True)
    group_id = _group_with(("article", "list"))
    audit = RecordingAudit()
    app = build_app(ArticleAdmin, MyGroupAdmin, is_async=True, audit=audit)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        await c.post(
            f"/admin/group/edit/{group_id}",
            data={"name": "editors", "permissions": ["article:edit"]},
            headers=as_user(1),
            follow_redirects=False,
        )
    await async_engine.dispose()

    assert [e.changes for e in audit.entries] == [
        {"name": "editors", "permissions": ["article:edit"]}
    ]


@pytest.mark.anyio
async def test_async_engine_edit_keeps_unoffered_grants(
    async_client: AsyncClient,
) -> None:
    make_user(is_superuser=True)
    group_id = _group_with(("*", "*"), ("article", "list"))

    response = await async_client.post(
        f"/admin/group/edit/{group_id}",
        data={"name": "editors", "permissions": ["article:edit"]},
        headers=as_user(1),
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert _grants_of(group_id) == {("*", "*"), ("article", "edit")}


@pytest.mark.anyio
async def test_async_engine_rejects_escalation(async_client: AsyncClient) -> None:
    make_user("group:*", "article:list")
    group_id = _group_with(("article", "list"))

    response = await async_client.post(
        f"/admin/group/edit/{group_id}",
        data={"name": "editors", "permissions": ["article:list", "article:delete"]},
        headers=as_user(1),
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "You are not allowed to grant: Articles: Delete" in response.text
    assert _grants_of(group_id) == {("article", "list")}


def test_group_list_does_not_load_grants(client: TestClient) -> None:
    make_user(is_superuser=True)
    _group_with(("article", "list"))

    statements = _statements_during(
        lambda: client.get("/admin/group/list", headers=as_user(1)).raise_for_status()
    )
    # Only the authorization lookup reads the grants table.
    assert sum("admin_group_accesses" in q for q in statements) == 1, statements


def test_group_delete_does_not_preload_grants(client: TestClient) -> None:
    make_user(is_superuser=True)
    group_id = _group_with(("article", "list"))

    statements = _statements_during(
        lambda: client.delete(
            f"/admin/group/delete?pks={group_id}", headers=as_user(1)
        ).raise_for_status()
    )
    # The authorization lookup, the details page's grants (the delete check
    # loads the object as for details), and the cascade.
    reads = [
        q for q in statements if q.startswith("SELECT") and "admin_group_accesses" in q
    ]
    assert len(reads) == 3, statements


@pytest.mark.anyio
async def test_async_engine_group_details_edit_and_delete(
    async_client: AsyncClient,
) -> None:
    make_user(is_superuser=True)
    group_id = _group_with(("article", "list"), ("article", "edit"))

    response = await async_client.get(
        f"/admin/group/details/{group_id}", headers=as_user(1)
    )
    assert response.status_code == 200

    response = await async_client.get(
        f"/admin/group/edit/{group_id}", headers=as_user(1)
    )
    assert 'value="article:edit" id="permissions-article:edit" checked>' in (
        response.text
    )

    response = await async_client.delete(
        f"/admin/group/delete?pks={group_id}", headers=as_user(1)
    )
    assert "error" not in response.text
    with session_maker() as session:
        assert session.query(Group).filter(Group.id == group_id).count() == 0
        assert (
            session.query(GroupAccess).filter(GroupAccess.group_id == group_id).count()
            == 0
        )


def test_permission_rows_are_cached_until_a_view_is_added() -> None:
    app = Starlette()
    admin = Admin(app=app, engine=engine)
    admin.add_view(ArticleAdmin)

    first = build_permission_rows(admin)
    assert build_permission_rows(admin) is first

    admin.add_view(ReportsPage)
    assert [row.identity for row in build_permission_rows(admin)] == [
        "article",
        "reports",
    ]


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
    assert "<th>Page</th><th>Permissions</th>" in response.text
    assert '<span class="form-check-label">List</span>' in response.text
    assert "&lt;input" not in response.text
    assert "&lt;table" not in response.text


def test_permission_matrix_labels_are_translated() -> None:
    pytest.importorskip("babel")
    from sqladmin.i18n import I18nConfig

    make_user(is_superuser=True)
    app = Starlette()
    admin = Admin(
        app=app,
        engine=engine,
        authentication_backend=HeaderUserBackend(secret_key="secret"),
        authorization_backend=DBAuthorizationBackend(
            session_maker, user_model=RbacUser
        ),
        i18n_config=I18nConfig(default_locale="de"),
    )
    admin.add_view(ArticleAdmin)
    admin.add_view(MyGroupAdmin)

    with TestClient(app=app) as c:
        response = c.get("/admin/group/create", headers=as_user(1))

    assert "<th>Seite</th><th>Berechtigungen</th>" in response.text
    assert '<span class="form-check-label">Liste</span>' in response.text


def test_escalation_error_is_translated() -> None:
    pytest.importorskip("babel")
    from sqladmin.i18n import I18nConfig

    make_user("group:*")
    group_id = _group_with()
    app = Starlette()
    admin = Admin(
        app=app,
        engine=engine,
        authentication_backend=HeaderUserBackend(secret_key="secret"),
        authorization_backend=DBAuthorizationBackend(
            session_maker, user_model=RbacUser
        ),
        i18n_config=I18nConfig(default_locale="de"),
    )
    admin.add_view(ArticleAdmin)
    admin.add_view(MyGroupAdmin)

    with TestClient(app=app) as c:
        response = c.post(
            f"/admin/group/edit/{group_id}",
            data={"name": "editors", "permissions": ["article:delete"]},
            headers=as_user(1),
        )

    assert response.status_code == 400
    assert (
        "Sie dürfen folgende Berechtigungen nicht vergeben: Articles: Löschen"
        in response.text
    )


@pytest.mark.parametrize("is_async", [False, True])
@pytest.mark.anyio
async def test_edit_form_loads_grants_without_form_edit_query(is_async: bool) -> None:
    class PlainQueryGroupAdmin(MyGroupAdmin):
        def form_edit_query(self, request: Request) -> Any:
            return self._stmt_by_identifier(request.path_params["pk"])

    make_user(is_superuser=True)
    group_id = _group_with(("article", "edit"))
    app = build_app(ArticleAdmin, PlainQueryGroupAdmin, is_async=is_async)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        response = await c.get(f"/admin/group/edit/{group_id}", headers=as_user(1))
    await async_engine.dispose()

    assert response.status_code == 200
    assert 'value="article:edit" id="permissions-article:edit" checked>' in (
        response.text
    )


def test_permission_matrix_escapes_view_names() -> None:
    """A view whose name contains markup is escaped, not rendered."""

    from wtforms import Form as WTForm

    from sqladmin.contrib.rbac import PermissionMatrixField, _ActionChoice, _ViewRow

    rows = [
        _ViewRow(
            identity="x",
            label="<script>alert(1)</script>",
            choices=[_ActionChoice("x:list", "list")],
        )
    ]

    class MatrixForm(WTForm):
        permissions = PermissionMatrixField(rows=rows)

    rendered = str(MatrixForm().permissions())

    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered
    # The surrounding table is still real markup.
    assert '<input type="checkbox"' in rendered
