import json
from collections.abc import AsyncGenerator, Generator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Column, ForeignKey, Integer, String, create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.testclient import TestClient

from sqladmin import Admin, ModelView
from sqladmin.palette import PaletteResult
from tests.common import async_engine, sync_engine

pytestmark = pytest.mark.anyio

Base = declarative_base()


class User(Base):
    __tablename__ = "palette_users"

    id = Column(Integer, primary_key=True)
    name = Column(String(length=64))
    email = Column(String(length=64))

    def __str__(self) -> str:
        return f"User {self.name}"


class Vacancy(Base):
    __tablename__ = "palette_vacancies"

    id = Column(Integer, primary_key=True)
    title = Column(String(length=64))

    def __str__(self) -> str:
        return self.title or ""


class Secret(Base):
    __tablename__ = "palette_secrets"

    id = Column(Integer, primary_key=True)
    name = Column(String(length=64))

    def __str__(self) -> str:
        return self.name or ""


class Locked(Base):
    __tablename__ = "palette_locked"

    id = Column(Integer, primary_key=True)
    name = Column(String(length=64))

    def __str__(self) -> str:
        return self.name or ""


class Command(Base):
    __tablename__ = "palette_commands"

    id = Column(Integer, primary_key=True)
    name = Column(String(length=64))

    def __str__(self) -> str:
        return self.name or ""


class Restricted(Base):
    __tablename__ = "palette_restricted"

    id = Column(Integer, primary_key=True)
    name = Column(String(length=64))

    def __str__(self) -> str:
        return self.name or ""


# --------------------------------------------------------------------------- #
# Views
# --------------------------------------------------------------------------- #
class UserAdmin(ModelView, model=User):
    column_searchable_list = [User.name, User.email]
    palette_search = True
    palette_search_limit = 3


class VacancyAdmin(ModelView, model=Vacancy):
    column_searchable_list = [Vacancy.title]
    palette_search = True


class SecretNotOptInAdmin(ModelView, model=Secret):
    # Searchable, but NOT opted into unscoped palette search.
    column_searchable_list = [Secret.name]
    palette_search = False


class HiddenAdmin(ModelView, model=Locked):
    # Opted in, but never visible/accessible -> must never surface.
    column_searchable_list = [Locked.name]
    palette_search = True

    def is_visible(self, request: Request) -> bool:
        return False

    def is_accessible(self, request: Request) -> bool:
        return False


class RowRestrictedAdmin(ModelView, model=Restricted):
    # Opted in and visible, but row-level check rejects "private" rows.
    column_searchable_list = [Restricted.name]
    palette_search = True

    async def check_can_view_details(self, request: Request, model: Any) -> bool:
        return not str(model.name).startswith("private")


def _register(admin: Admin) -> None:
    admin.add_view(UserAdmin)
    admin.add_view(VacancyAdmin)
    admin.add_view(SecretNotOptInAdmin)
    admin.add_view(HiddenAdmin)
    admin.add_view(RowRestrictedAdmin)


def _seed() -> list:
    return [
        User(name="John Smith", email="john@acme.com"),
        User(name="Johnny Berg", email="johnny@mail.io"),
        User(name="Alice", email="alice@acme.com"),
        Vacancy(title="Senior Backend Developer"),
        Vacancy(title="Junior Python Engineer"),
        Secret(name="johnson secret"),
        Locked(name="john locked"),
        Restricted(name="public johnfile"),
        Restricted(name="private johnfile"),
    ]


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
async_session_maker = async_sessionmaker(
    bind=async_engine, class_=AsyncSession, expire_on_commit=False
)
sync_session_maker = sessionmaker(bind=sync_engine, class_=Session)


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_maker() as session:
        session.add_all(_seed())
        await session.commit()

    app = Starlette()
    admin = Admin(app=app, engine=async_engine)
    _register(admin)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    # Drop pooled connections: asyncpg binds them to the event loop that
    # created them, and the next test gets a new loop.
    await async_engine.dispose()


@pytest.fixture
def sync_client() -> Generator[TestClient, None, None]:
    Base.metadata.create_all(sync_engine)

    with sync_session_maker() as session:
        session.add_all(_seed())
        session.commit()

    app = Starlette()
    admin = Admin(app=app, engine=sync_engine)
    _register(admin)

    with TestClient(app) as client:
        yield client

    Base.metadata.drop_all(sync_engine)
    sync_engine.dispose()


def _labels(records: list) -> set:
    return {r["label"] for r in records}


# --------------------------------------------------------------------------- #
# Model matching (registry only, no DB)
# --------------------------------------------------------------------------- #
async def test_empty_query_returns_visible_models(async_client: AsyncClient) -> None:
    resp = await async_client.get("/admin/palette")
    assert resp.status_code == 200
    body = resp.json()

    identities = {m["identity"] for m in body["models"]}
    assert {"user", "vacancy", "secret", "restricted"} <= identities
    assert "locked" not in identities  # hidden view filtered out
    assert body["records"] == []
    assert body["scope"] is None


async def test_model_match_is_case_insensitive(async_client: AsyncClient) -> None:
    resp = await async_client.get("/admin/palette", params={"q": "vac"})
    assert {m["identity"] for m in resp.json()["models"]} == {"vacancy"}


async def test_model_payload_urls_and_flags(async_client: AsyncClient) -> None:
    resp = await async_client.get("/admin/palette", params={"q": "user"})
    user = next(m for m in resp.json()["models"] if m["identity"] == "user")

    assert user["url"].endswith("/admin/user/list")
    assert user["create_url"].endswith("/admin/user/create")
    assert user["searchable"] is True
    assert set(user) == {
        "identity",
        "name",
        "name_plural",
        "category",
        "url",
        "create_url",
        "searchable",
    }


async def test_non_optin_model_not_searchable(async_client: AsyncClient) -> None:
    resp = await async_client.get("/admin/palette", params={"q": "secret"})
    secret = next(m for m in resp.json()["models"] if m["identity"] == "secret")
    assert secret["searchable"] is False


# --------------------------------------------------------------------------- #
# Unscoped fan-out
# --------------------------------------------------------------------------- #
async def test_unscoped_search_only_optin_models(async_client: AsyncClient) -> None:
    resp = await async_client.get("/admin/palette", params={"q": "john"})
    labels = _labels(resp.json()["records"])

    assert "User John Smith" in labels
    assert "User Johnny Berg" in labels
    assert "johnson secret" not in labels  # not opted in
    assert "john locked" not in labels  # hidden view


async def test_unscoped_below_min_chars_skips_records(
    async_client: AsyncClient,
) -> None:
    resp = await async_client.get("/admin/palette", params={"q": "j"})
    assert resp.json()["records"] == []


async def test_unscoped_record_shape(async_client: AsyncClient) -> None:
    resp = await async_client.get("/admin/palette", params={"q": "john"})
    rec = next(r for r in resp.json()["records"] if r["label"] == "User John Smith")

    assert rec["identity"] == "user"
    assert "/admin/user/details/" in rec["url"]
    assert set(rec) == set(PaletteResult._fields)


# --------------------------------------------------------------------------- #
# Row-level permissions (sqladmin >= 0.29 check_can_view_details)
# --------------------------------------------------------------------------- #
async def test_row_level_permission_filters_records(
    async_client: AsyncClient,
) -> None:
    resp = await async_client.get("/admin/palette", params={"q": "johnfile"})
    labels = _labels(resp.json()["records"])

    assert "public johnfile" in labels
    assert "private johnfile" not in labels


async def test_row_level_permission_applies_when_scoped(
    async_client: AsyncClient,
) -> None:
    resp = await async_client.get(
        "/admin/palette", params={"q": "johnfile", "scope": "restricted"}
    )
    assert _labels(resp.json()["records"]) == {"public johnfile"}


# --------------------------------------------------------------------------- #
# Scoped search
# --------------------------------------------------------------------------- #
async def test_scoped_search_single_model(async_client: AsyncClient) -> None:
    resp = await async_client.get(
        "/admin/palette", params={"q": "john", "scope": "user"}
    )
    body = resp.json()

    assert body["scope"] == "user"
    assert body["models"] == []
    assert _labels(body["records"]) == {"User John Smith", "User Johnny Berg"}


async def test_scoped_search_respects_limit(async_client: AsyncClient) -> None:
    resp = await async_client.get("/admin/palette", params={"q": "@", "scope": "user"})
    assert len(resp.json()["records"]) == 3  # palette_search_limit = 3


async def test_scoped_search_works_on_non_optin_model(
    async_client: AsyncClient,
) -> None:
    resp = await async_client.get(
        "/admin/palette", params={"q": "johnson", "scope": "secret"}
    )
    assert _labels(resp.json()["records"]) == {"johnson secret"}


async def test_scoped_empty_term_returns_no_records(async_client: AsyncClient) -> None:
    resp = await async_client.get("/admin/palette", params={"scope": "user"})
    assert resp.json()["records"] == []


async def test_scope_unknown_identity_404(async_client: AsyncClient) -> None:
    resp = await async_client.get("/admin/palette", params={"q": "x", "scope": "nope"})
    assert resp.status_code == 404


async def test_scope_hidden_model_404(async_client: AsyncClient) -> None:
    resp = await async_client.get(
        "/admin/palette", params={"q": "x", "scope": "locked"}
    )
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# Fan-out cap
# --------------------------------------------------------------------------- #
async def test_max_models_caps_fanout() -> None:
    app = Starlette()
    admin = Admin(app=app, engine=async_engine, palette_search_max_models=1)
    _register(admin)

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_session_maker() as session:
        session.add_all([User(name="John", email="j@x.io"), Vacancy(title="John role")])
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/admin/palette", params={"q": "john"})

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await async_engine.dispose()

    assert {r["identity"] for r in resp.json()["records"]} <= {"user"}


# --------------------------------------------------------------------------- #
# Sync engine parity
# --------------------------------------------------------------------------- #
def test_sync_unscoped_search(sync_client: TestClient) -> None:
    resp = sync_client.get("/admin/palette", params={"q": "john"})
    assert resp.status_code == 200
    assert "User John Smith" in _labels(resp.json()["records"])


def test_sync_scoped_search(sync_client: TestClient) -> None:
    resp = sync_client.get("/admin/palette", params={"q": "senior", "scope": "vacancy"})
    assert _labels(resp.json()["records"]) == {"Senior Backend Developer"}


def test_sync_model_matching(sync_client: TestClient) -> None:
    resp = sync_client.get("/admin/palette", params={"q": "user"})
    assert {m["identity"] for m in resp.json()["models"]} == {"user"}


def test_sync_row_level_permission(sync_client: TestClient) -> None:
    resp = sync_client.get("/admin/palette", params={"q": "johnfile"})
    assert "private johnfile" not in _labels(resp.json()["records"])


# --------------------------------------------------------------------------- #
# UI wiring
# --------------------------------------------------------------------------- #
def test_layout_renders_trigger_and_modal(sync_client: TestClient) -> None:
    page = sync_client.get("/admin/user/list").text

    assert "data-sa-palette-open" in page
    assert 'id="sa-palette"' in page
    assert "css/palette.css" in page
    assert "js/palette.js" in page
    assert "SA_PALETTE_URL" in page
    assert "SA_PALETTE_I18N" in page


# --------------------------------------------------------------------------- #
# Authentication
# --------------------------------------------------------------------------- #
def test_palette_requires_authentication() -> None:
    from sqladmin.authentication import AuthenticationBackend

    class DenyBackend(AuthenticationBackend):
        async def login(self, request: Request) -> bool:
            return False

        async def logout(self, request: Request) -> bool:
            return True

        async def authenticate(self, request: Request) -> bool:
            return False

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    app = Starlette()
    admin = Admin(
        app=app, engine=engine, authentication_backend=DenyBackend(secret_key="x")
    )
    admin.add_view(UserAdmin)

    with TestClient(app) as client:
        resp = client.get("/admin/palette", follow_redirects=False)

    Base.metadata.drop_all(engine)

    # Unlike other admin routes, the palette endpoint answers unauthenticated
    # requests with JSON rather than an HTML redirect: see
    # test_palette_returns_json_401_when_unauthenticated for why.
    assert resp.status_code == 401


# --------------------------------------------------------------------------- #
# i18n
# --------------------------------------------------------------------------- #
def _palette_i18n(html: str) -> dict:
    """Pull the window.SA_PALETTE_I18N object out of a rendered page."""
    import re

    blob = re.search(r"window\.SA_PALETTE_I18N = \{(.*?)\n  \};", html, re.S)
    assert blob is not None, "palette i18n block missing"
    return dict(re.findall(r'(\w+):\s*"([^"]*)"', blob.group(1)))


def _i18n_app() -> Starlette:
    from sqladmin import I18nConfig

    app = Starlette()
    admin = Admin(
        app=app,
        engine=sync_engine,
        i18n_config=I18nConfig(
            default_locale="en", language_switcher=["en", "az", "tr", "de", "ru"]
        ),
    )
    admin.add_view(UserAdmin)
    return app


def test_palette_strings_are_translated() -> None:
    Base.metadata.create_all(sync_engine)
    with TestClient(_i18n_app()) as client:
        english = _palette_i18n(client.get("/admin/", params={"lang": "en"}).text)
        azerbaijani = _palette_i18n(client.get("/admin/", params={"lang": "az"}).text)
    Base.metadata.drop_all(sync_engine)

    assert english["models"] == "Models"
    assert azerbaijani["models"] == "Modell\u0259r"
    # every key must differ from English, i.e. no untranslated leftovers
    untranslated = [k for k, v in azerbaijani.items() if v == english[k]]
    assert untranslated == [], f"untranslated palette keys: {untranslated}"


def test_palette_placeholders_survive_translation() -> None:
    Base.metadata.create_all(sync_engine)
    with TestClient(_i18n_app()) as client:
        pages = {
            lang: _palette_i18n(client.get("/admin/", params={"lang": lang}).text)
            for lang in ("en", "az", "tr", "de", "ru")
        }
    Base.metadata.drop_all(sync_engine)

    for lang, strings in pages.items():
        assert "{name}" in strings["goTo"], lang
        assert "{name}" in strings["create"], lang
        assert "{name}" in strings["recordsIn"], lang
        assert "{name}" in strings["searchInsidePlaceholder"], lang
        assert "{count}" in strings["more"], lang


def test_all_locales_cover_every_palette_string() -> None:
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    mappings = json.loads(
        (root / "scripts" / "translations.json").read_text(encoding="utf-8")
    )

    palette_strings = {
        "Models",
        "Commands",
        "Records",
        "Records in {name}",
        "Search inside",
        "Search inside {name}",
        "Go to {name}",
        "Create {name}",
        "page",
        "new",
        "open",
        "single model",
        "registry, no database query",
        "{count} more, keep typing to narrow",
        "Searched {searched} of {total} models, keep typing to narrow",
        "No matches",
        "Nothing found",
        "Search failed",
        "Search models, records, commands",
        "Click a model to scope, click a record to open",
    }

    for locale, entries in mappings.items():
        if locale == "en":  # source language, intentionally empty
            continue
        missing = sorted(palette_strings - set(entries))
        assert missing == [], f"{locale} is missing: {missing}"


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
class CommandAdmin(ModelView, model=Command):
    column_searchable_list = [Command.name]

    def palette_commands(self, request: Request) -> list:
        commands = super().palette_commands(request)
        commands.append(
            {
                "label": "Export as CSV",
                "url": str(
                    request.url_for(
                        "admin:export", identity=self.identity, export_type="csv"
                    )
                ),
                "icon": "\u2193",
                "badge": "csv",
            }
        )
        return commands


async def test_no_commands_without_a_term(async_client: AsyncClient) -> None:
    # With nothing typed there is no best match, so offering "Go to <first
    # registered model>" would be arbitrary noise.
    resp = await async_client.get("/admin/palette")
    assert resp.json()["commands"] == []


async def test_commands_follow_the_matched_model(async_client: AsyncClient) -> None:
    resp = await async_client.get("/admin/palette", params={"q": "vac"})
    commands = resp.json()["commands"]

    assert [c["label"] for c in commands] == ["goTo", "create"]
    assert all(c["name"] == "Vacancy" for c in commands)
    assert commands[0]["url"].endswith("/admin/vacancy/list")
    assert commands[1]["url"].endswith("/admin/vacancy/create")


async def test_create_command_hidden_when_cannot_create() -> None:
    app = Starlette()
    admin = Admin(app=app, engine=async_engine)

    class NoCreateAdmin(ModelView, model=Vacancy):
        can_create = False
        column_searchable_list = [Vacancy.title]

    admin.add_view(NoCreateAdmin)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/admin/palette", params={"q": "vacancy"})

    assert [c["label"] for c in resp.json()["commands"]] == ["goTo"]


async def test_scoped_response_has_no_commands(async_client: AsyncClient) -> None:
    resp = await async_client.get(
        "/admin/palette", params={"q": "john", "scope": "user"}
    )
    assert resp.json()["commands"] == []


async def test_palette_commands_can_be_overridden() -> None:
    app = Starlette()
    admin = Admin(app=app, engine=async_engine)
    admin.add_view(CommandAdmin)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/admin/palette", params={"q": "command"})

    commands = resp.json()["commands"]
    assert [c["label"] for c in commands] == ["goTo", "create", "Export as CSV"]
    assert commands[-1]["badge"] == "csv"


# --------------------------------------------------------------------------- #
# Review follow-ups: scoped search against models the fan-out never reaches
# --------------------------------------------------------------------------- #
class NoDetailsAdmin(ModelView, model=Secret):
    can_view_details = False
    column_searchable_list = [Secret.name]
    palette_search = True


class NoSearchableAdmin(ModelView, model=Locked):
    # No column_searchable_list at all: _search_fields is empty.
    palette_search = True


async def test_scoped_search_against_can_view_details_false() -> None:
    app = Starlette()
    admin = Admin(app=app, engine=async_engine)
    admin.add_view(NoDetailsAdmin)

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_session_maker() as session:
        session.add(Secret(name="johnson secret"))
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/admin/palette", params={"q": "johnson", "scope": "secret"}
        )

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await async_engine.dispose()

    # The view is visible/accessible so the scope itself resolves (no 404),
    # but can_view_details = False means there is nothing to link to.
    assert resp.status_code == 200
    assert resp.json()["records"] == []


async def test_scoped_search_against_model_with_no_searchable_columns() -> None:
    app = Starlette()
    admin = Admin(app=app, engine=async_engine)
    admin.add_view(NoSearchableAdmin)

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_session_maker() as session:
        session.add(Locked(name="john locked"))
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/admin/palette", params={"q": "john", "scope": "locked"}
        )

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await async_engine.dispose()

    assert resp.status_code == 200
    assert resp.json()["records"] == []


# --------------------------------------------------------------------------- #
# Review follow-ups: relationships touched by __str__, tenant-style scoping
# --------------------------------------------------------------------------- #
class Team(Base):
    __tablename__ = "palette_teams"

    id = Column(Integer, primary_key=True)
    name = Column(String(length=64))


class Player(Base):
    __tablename__ = "palette_players"

    id = Column(Integer, primary_key=True)
    name = Column(String(length=64))
    team_id = Column(Integer, ForeignKey("palette_teams.id"))
    team = relationship("Team")

    def __str__(self) -> str:
        return f"{self.name} ({self.team.name if self.team else '-'})"


class PlayerAdmin(ModelView, model=Player):
    # The relation __str__ touches must be listed here: sqladmin eager-loads
    # exactly the relations named in column_list wherever it later calls
    # str(obj), and the palette follows the same convention.
    column_list = [Player.id, Player.name, Player.team]
    column_searchable_list = [Player.name]
    palette_search = True


class TenantArticle(Base):
    __tablename__ = "palette_tenant_articles"

    id = Column(Integer, primary_key=True)
    title = Column(String(length=64))
    tenant = Column(String(length=64))

    def __str__(self) -> str:
        return self.title or ""


class TenantArticleAdmin(ModelView, model=TenantArticle):
    column_searchable_list = [TenantArticle.title]
    palette_search = True

    def list_query(self, request: Request):  # type: ignore[no-untyped-def]
        from sqlalchemy import select

        tenant = request.query_params.get("tenant")
        stmt = select(TenantArticle)
        if tenant:
            stmt = stmt.where(TenantArticle.tenant == tenant)
        return stmt


async def test_relationship_in_str_does_not_crash_when_listed() -> None:
    app = Starlette()
    admin = Admin(app=app, engine=async_engine)
    admin.add_view(PlayerAdmin)

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_session_maker() as session:
        team = Team(name="Backend")
        session.add(team)
        await session.flush()
        session.add(Player(name="John", team_id=team.id))
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/admin/palette", params={"q": "john"})

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await async_engine.dispose()

    assert resp.status_code == 200
    assert _labels(resp.json()["records"]) == {"John (Backend)"}


async def test_palette_respects_list_query_scoping() -> None:
    # A view overriding list_query for request-based scoping (e.g. a tenant
    # filter) should see that scoping applied by the palette too, not just
    # the list page.
    app = Starlette()
    admin = Admin(app=app, engine=async_engine)
    admin.add_view(TenantArticleAdmin)

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_session_maker() as session:
        session.add_all(
            [
                TenantArticle(title="Acme roadmap", tenant="acme"),
                TenantArticle(title="Acme onboarding", tenant="acme"),
                TenantArticle(title="Beta roadmap", tenant="beta"),
            ]
        )
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/admin/palette",
            params={"q": "roadmap", "scope": "tenant-article", "tenant": "acme"},
        )

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await async_engine.dispose()

    assert _labels(resp.json()["records"]) == {"Acme roadmap"}


# --------------------------------------------------------------------------- #
# Review follow-ups: authentication returns JSON, not an HTML redirect
# --------------------------------------------------------------------------- #
def test_palette_returns_json_401_when_unauthenticated() -> None:
    from sqladmin.authentication import AuthenticationBackend

    class DenyBackend(AuthenticationBackend):
        async def login(self, request: Request) -> bool:
            return False

        async def logout(self, request: Request) -> bool:
            return True

        async def authenticate(self, request: Request) -> bool:
            return False

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    app = Starlette()
    admin = Admin(
        app=app,
        engine=engine,
        authentication_backend=DenyBackend(secret_key="x"),
    )
    admin.add_view(UserAdmin)

    with TestClient(app) as client:
        resp = client.get(
            "/admin/palette", headers={"X-Requested-With": "XMLHttpRequest"}
        )

    Base.metadata.drop_all(engine)

    # A JSON 401 (not an HTML redirect) lets the frontend recognise the
    # session expired and send the user to the login page itself, instead of
    # rendering a login page's markup inside the results list.
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Authentication required"}


def test_login_url_exposed_for_client_side_redirect(sync_client: TestClient) -> None:
    page = sync_client.get("/admin/user/list").text
    assert "SA_PALETTE_LOGIN_URL" in page


# --------------------------------------------------------------------------- #
# Review follow-ups: bounds on the constructor parameters
# --------------------------------------------------------------------------- #
def test_negative_palette_settings_are_clamped_to_zero() -> None:
    app = Starlette()
    admin = Admin(
        app=app,
        engine=sync_engine,
        palette_search_min_chars=-5,
        palette_search_max_models=-5,
    )
    assert admin.palette_search_min_chars == 0
    assert admin.palette_search_max_models == 0


# --------------------------------------------------------------------------- #
# Second review round: gather failure isolation, tojson escaping, capped
# fan-out visibility
# --------------------------------------------------------------------------- #
class FlakyAdmin(ModelView, model=Locked):
    # Simulates one model's query failing outright — a bad custom
    # palette_search_query, a transient connection error, anything.
    column_searchable_list = [Locked.name]
    palette_search = True

    def palette_search_query(self, request: Request, term: str):  # type: ignore[no-untyped-def]
        raise RuntimeError("simulated failure in one model's query")


async def test_one_model_failing_does_not_fail_the_whole_search() -> None:
    app = Starlette()
    admin = Admin(app=app, engine=async_engine)
    admin.add_view(UserAdmin)
    admin.add_view(FlakyAdmin)

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_session_maker() as session:
        session.add_all(
            [
                User(name="John Smith", email="john@acme.com"),
                Locked(name="john locked"),
            ]
        )
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/admin/palette", params={"q": "john"})

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await async_engine.dispose()

    # The working model's result must still come back with a 200, not a 500
    # from the broken model taking the whole gather() down with it.
    assert resp.status_code == 200
    assert _labels(resp.json()["records"]) == {"User John Smith"}


def test_translation_containing_a_quote_is_not_a_syntax_break(
    sync_client: TestClient,
) -> None:
    # A translation is developer/translator content, not sandboxed by Jinja's
    # HTML autoescaping (jinja2.ext.i18n deliberately exempts gettext output
    # so translators can include intentional HTML). Embedding it with
    # `| tojson` rather than manual quoting must keep it a single, valid,
    # fully round-trippable JS string no matter what it contains.
    from sqladmin.templating import _tojson_filter

    payload = '"; alert(document.cookie); var x = "'
    embedded = _tojson_filter(payload)

    # Every quote from the source must be backslash-escaped, not bare — a
    # bare `"` is what would close the JS string literal early.
    assert '\\"' in str(embedded)
    restored = json.loads(
        str(embedded)
        .replace("\\u003c", "<")
        .replace("\\u003e", ">")
        .replace("\\u0026", "&")
        .replace("\\u0027", "'")
    )
    assert restored == payload


def test_tojson_filter_blocks_script_tag_breakout() -> None:
    from sqladmin.templating import _tojson_filter

    payload = "</script><script>alert(1)</script>"
    embedded = str(_tojson_filter(payload))
    assert "</script>" not in embedded
    assert "\\u003c/script\\u003e" in embedded


def test_palette_html_uses_tojson_for_every_interpolation(
    sync_client: TestClient,
) -> None:
    page = sync_client.get("/admin/user/list").text
    start = page.index("window.SA_PALETTE_I18N")
    end = page.index("};", start)
    block = page[start:end]
    # Every value in the object must be produced by tojson (always opens with
    # a double quote from json.dumps), never by the old bare `"{{ _(...) }}"`
    # pattern this fixes.
    assert "{{" not in block


async def test_capped_fanout_reports_searched_and_total() -> None:
    app = Starlette()
    admin = Admin(app=app, engine=async_engine, palette_search_max_models=2)

    models = []
    for i in range(5):
        model = type(
            f"CapModel{i}",
            (Base,),
            {
                "__tablename__": f"cap_model_{i}",
                "id": Column(Integer, primary_key=True),
                "name": Column(String(length=64)),
                "__str__": lambda self: str(self.name or ""),
            },
        )
        models.append(model)
        view = type(
            f"CapModel{i}Admin",
            (ModelView,),
            {"column_searchable_list": [model.name], "palette_search": True},
            model=model,
        )
        admin.add_view(view)

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_session_maker() as session:
        # Only the last (unsearched, given the cap of 2) model has a match.
        session.add(models[4](name="onlylast"))
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/admin/palette", params={"q": "onlylast"})

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await async_engine.dispose()

    body = resp.json()
    assert body["searched_models"] == 2
    assert body["total_optin_models"] == 5
    # The match is real but outside the searched prefix: the response must
    # still say so via the counts, rather than an indistinguishable "nothing
    # found" that looks identical to a genuine no-match.
    assert body["records"] == []


async def test_uncapped_search_reports_equal_searched_and_total(
    async_client: AsyncClient,
) -> None:
    resp = await async_client.get("/admin/palette", params={"q": "john"})
    body = resp.json()
    assert body["searched_models"] == body["total_optin_models"]


async def test_scoped_response_reports_single_model(
    async_client: AsyncClient,
) -> None:
    resp = await async_client.get(
        "/admin/palette", params={"q": "john", "scope": "user"}
    )
    body = resp.json()
    assert body["searched_models"] == 1
    assert body["total_optin_models"] == 1
