import datetime
import importlib
import sys
from typing import Generator, Optional
from unittest import mock

import pytest
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import declarative_base
from starlette.applications import Starlette
from starlette.testclient import TestClient

from sqladmin import Admin, ModelView
from sqladmin.i18n import (
    DEFAULT_LOCALE,
    LANGUAGE_COOKIE_MAX_AGE,
    SUPPORTED_LOCALES,
    I18nConfig,
    LocaleMiddleware,
    format_date,
    format_datetime,
    format_time,
    get_locale,
    get_locale_display_name,
    gettext,
    lazy_gettext,
    ngettext,
    set_locale,
    translations,
)
from tests.common import sync_engine as engine

Base = declarative_base()  # type: ignore

SWITCHER = ["en", "az", "de", "ru", "tr"]


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(String(32), default="SQLAdmin")


class UserAdmin(ModelView, model=User):
    column_list = [User.id, User.name]
    column_searchable_list = [User.name]


@pytest.fixture(autouse=True)
def prepare_database() -> Generator[None, None, None]:
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def reset_locale() -> Generator[None, None, None]:
    set_locale(DEFAULT_LOCALE)
    yield
    set_locale(DEFAULT_LOCALE)


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    app = Starlette()
    admin = Admin(
        app=app,
        engine=engine,
        i18n_config=I18nConfig(language_switcher=SWITCHER),
    )
    admin.add_view(UserAdmin)
    with TestClient(app) as c:
        yield c


######################################################
################# CATALOG LOADING ####################
######################################################
def test_all_supported_locales_are_loaded() -> None:
    assert set(translations) == set(SUPPORTED_LOCALES)


def test_gettext_translates_for_active_locale() -> None:
    set_locale("az")
    assert gettext("Logout") == "Çıxış"

    set_locale("de")
    assert gettext("Logout") == "Abmelden"


def test_gettext_falls_back_to_source() -> None:
    set_locale("az")
    assert gettext("Untranslated string") == "Untranslated string"


def test_unsupported_locale_falls_back_to_default() -> None:
    set_locale("xx")
    assert get_locale() == DEFAULT_LOCALE
    assert gettext("Logout") == "Logout"


def test_lazy_gettext_defers_evaluation() -> None:
    # Created at the default locale, but resolved only on first use.
    label = lazy_gettext("Save")

    set_locale("az")
    assert str(label) == "Yadda saxla"


def test_lazy_gettext_per_locale() -> None:
    set_locale("de")
    assert str(lazy_gettext("Save")) == "Speichern"


######################################################
################### PLURAL FORMS #####################
######################################################
def test_ngettext_uses_locale_plural_rule() -> None:
    # Russian has three plural forms; the rule comes from the compiled catalog.
    set_locale("ru")
    assert ngettext("a", "b", 1) == "a"
    assert ngettext("a", "b", 2) == "b"
    assert ngettext("a", "b", 5) == "b"


def test_ngettext_english_default() -> None:
    set_locale("en")
    assert ngettext("a", "b", 1) == "a"
    assert ngettext("a", "b", 3) == "b"


######################################################
################ DISPLAY / FORMATTING ################
######################################################
def test_get_locale_display_name_preserves_multi_word_names() -> None:
    # Only the first character is upper-cased, so names like "português (Brasil)"
    # keep their inner casing instead of being flattened by ``str.capitalize()``.
    with mock.patch("sqladmin.i18n.Locale") as locale_cls:
        locale_cls.parse.return_value.display_name = "português (Brasil)"
        assert get_locale_display_name("pt-BR") == "Português (Brasil)"


def test_get_locale_display_name_falls_back_to_code() -> None:
    with mock.patch("sqladmin.i18n.Locale") as locale_cls:
        locale_cls.parse.return_value.display_name = ""
        assert get_locale_display_name("xx") == "xx"


def test_get_locale_display_name_uses_cldr() -> None:
    assert get_locale_display_name("az") == "Azərbaycan"
    assert get_locale_display_name("ru") == "Русский"


def test_format_datetime_is_locale_aware() -> None:
    value = datetime.datetime(2026, 6, 15, 9, 30)

    set_locale("en")
    english = format_datetime(value)
    set_locale("ru")
    russian = format_datetime(value)

    assert english != russian


def test_format_date_and_time_run() -> None:
    set_locale("de")
    assert format_date(datetime.date(2026, 6, 15))
    assert format_time(datetime.time(9, 30))


######################################################
################ LOCALE NEGOTIATION ##################
######################################################
@pytest.mark.parametrize(
    "header, expected",
    [
        ("de-DE,de;q=0.9,en;q=0.8", "de"),
        ("az-AZ,az;q=0.9", "az"),
        ("ru", "ru"),
        ("fr-FR,fr;q=0.9", None),
        ("", None),
    ],
)
def test_negotiate_from_header(header: str, expected: Optional[str]) -> None:
    from sqladmin.i18n import _negotiate_from_header

    assert _negotiate_from_header(header, SUPPORTED_LOCALES) == expected


def test_negotiate_respects_quality_order() -> None:
    from sqladmin.i18n import _negotiate_from_header

    assert _negotiate_from_header("en;q=0.3,de;q=0.9", ["en", "de"]) == "de"


def test_negotiate_handles_malformed_quality() -> None:
    from sqladmin.i18n import _negotiate_from_header

    assert _negotiate_from_header("de;q=bad,en;q=0.5", ["en", "de"]) == "en"


######################################################
#################### END TO END ######################
######################################################
def test_default_renders_english(client: TestClient) -> None:
    response = client.get("/admin/user/list")

    assert response.status_code == 200
    assert "Search" in response.text
    assert "Showing" in response.text


def test_query_param_switches_locale(client: TestClient) -> None:
    response = client.get("/admin/user/list?lang=az")

    assert response.status_code == 200
    assert "Axtarış" in response.text
    assert "göstərilir" in response.text  # pagination placeholder message


def test_query_param_sets_cookie(client: TestClient) -> None:
    response = client.get("/admin/user/list?lang=ru")

    assert response.cookies.get("language") == "ru"


def test_cookie_persists_locale(client: TestClient) -> None:
    client.cookies.set("language", "tr")
    response = client.get("/admin/user/list")

    assert "gösteriliyor" in response.text  # pagination placeholder message


def test_accept_language_header_negotiated(client: TestClient) -> None:
    response = client.get(
        "/admin/user/list",
        headers={"accept-language": "de-DE,de;q=0.9"},
    )

    assert "Zeige" in response.text  # pagination placeholder message


def test_default_locale_is_used_without_any_preference() -> None:
    app = Starlette()
    admin = Admin(
        app=app,
        engine=engine,
        i18n_config=I18nConfig(default_locale="de", language_switcher=SWITCHER),
    )
    admin.add_view(UserAdmin)

    with TestClient(app) as c:
        response = c.get("/admin/user/list")

    assert response.status_code == 200
    assert "Suche" in response.text


def test_default_locale_used_when_header_does_not_match() -> None:
    app = Starlette()
    admin = Admin(
        app=app,
        engine=engine,
        i18n_config=I18nConfig(default_locale="ru", language_switcher=SWITCHER),
    )
    admin.add_view(UserAdmin)

    with TestClient(app) as c:
        response = c.get(
            "/admin/user/list",
            headers={"accept-language": "fr-FR,fr;q=0.9"},
        )

    assert "Поиск" in response.text


def test_query_param_overrides_default_locale() -> None:
    app = Starlette()
    admin = Admin(
        app=app,
        engine=engine,
        i18n_config=I18nConfig(default_locale="de", language_switcher=SWITCHER),
    )
    admin.add_view(UserAdmin)

    with TestClient(app) as c:
        response = c.get("/admin/user/list?lang=az")

    assert "Axtarış" in response.text


def test_language_cookie_is_persisted_with_max_age(client: TestClient) -> None:
    response = client.get("/admin/user/list?lang=az")

    cookie_header = response.headers["set-cookie"]
    assert f"Max-Age={LANGUAGE_COOKIE_MAX_AGE}" in cookie_header


def test_unsupported_query_locale_ignored(client: TestClient) -> None:
    response = client.get("/admin/user/list?lang=fr")

    assert response.status_code == 200
    assert response.cookies.get("language") is None
    assert "Showing" in response.text


def test_switcher_rendered_with_config(client: TestClient) -> None:
    response = client.get("/admin/user/list")

    assert "Azərbaycan" in response.text
    assert "Русский" in response.text


def test_switcher_absent_without_i18n_config() -> None:
    app = Starlette()
    admin = Admin(app=app, engine=engine)
    admin.add_view(UserAdmin)

    with TestClient(app) as c:
        response = c.get("/admin/user/list")

    assert "Azərbaycan" not in response.text


######################################################
################ CATALOG COMPLETENESS ################
######################################################
@pytest.mark.parametrize(
    "locale, source, expected",
    [
        ("az", "Export", "İxrac et"),
        ("az", "Actions", "Əməliyyatlar"),
        ("az", "New %(name)s", "Yeni %(name)s"),
        ("az", "prev", "əvvəlki"),
        ("az", "Show", "Göstər"),
        ("de", "Export", "Exportieren"),
        ("de", "Actions", "Aktionen"),
        ("ru", "Export", "Экспорт"),
        ("tr", "Actions", "İşlemler"),
    ],
)
def test_expanded_ui_strings_translate(locale: str, source: str, expected: str) -> None:
    set_locale(locale)
    assert gettext(source) == expected


def test_every_locale_covers_the_full_catalog() -> None:
    # Azerbaijani is fully translated; use its message ids as the reference set
    # and assert the other shipped locales translate all of them too.
    reference = [msgid for msgid in translations["az"]._catalog if msgid]  # type: ignore[attr-defined]
    assert len(reference) >= 40

    for locale in ("de", "ru", "tr"):
        catalog = translations[locale]._catalog  # type: ignore[attr-defined]
        missing = [msgid for msgid in reference if not catalog.get(msgid)]
        assert not missing, f"{locale} is missing translations for: {missing}"


######################################################
############### LANGUAGE SWITCHER (UI) ###############
######################################################
def test_switcher_rendered_in_top_navbar(client: TestClient) -> None:
    import re

    response = client.get("/admin/user/list")
    header = re.search(r"<header[^>]*navbar.*?</header>", response.text, re.S)

    assert header is not None
    # The switcher and its locale options live inside the top navbar header.
    assert "Azərbaycan" in header.group(0)
    assert "Deutsch" in header.group(0)


def test_warns_when_i18n_config_passed_without_babel() -> None:
    app = Starlette()

    with mock.patch("sqladmin.application.BABEL_INSTALLED", False):
        with pytest.warns(UserWarning, match="babel"):
            Admin(app=app, engine=engine, i18n_config=I18nConfig())


def test_no_warning_without_i18n_config() -> None:
    import warnings as warnings_module

    app = Starlette()
    with warnings_module.catch_warnings():
        warnings_module.simplefilter("error")
        Admin(app=app, engine=engine)


@pytest.mark.anyio
async def test_middleware_passes_through_non_http_scope() -> None:
    seen = []

    async def app(scope, receive, send) -> None:
        seen.append(scope["type"])

    middleware = LocaleMiddleware(app, I18nConfig())
    await middleware({"type": "lifespan"}, None, None)  # type: ignore[arg-type]

    assert seen == ["lifespan"]


######################################################
################# NO-BABEL FALLBACK ##################
######################################################
def test_fallback_without_babel() -> None:
    import sqladmin.i18n as i18n_module

    with mock.patch.dict(sys.modules):
        for name in list(sys.modules):
            if name == "babel" or name.startswith("babel."):
                sys.modules[name] = None  # force ImportError on reload
        importlib.reload(i18n_module)

        assert i18n_module.gettext("Logout") == "Logout"
        assert i18n_module.ngettext("a", "b", 1) == "a"
        assert i18n_module.ngettext("a", "b", 2) == "b"
        assert i18n_module.lazy_gettext("Save") == "Save"
        assert i18n_module.get_locale() == DEFAULT_LOCALE
        i18n_module.set_locale("az")  # no-op, must not raise
        assert i18n_module.get_locale_display_name("az") == "az"
        assert i18n_module.format_date(datetime.date(2026, 6, 15))
        assert i18n_module.format_time(datetime.time(9, 30))
        tz = datetime.timezone(datetime.timedelta(hours=4))
        assert i18n_module.format_datetime(
            datetime.datetime(2026, 6, 15, 9, 30), tzinfo=tz
        )
        assert i18n_module._negotiate_from_header("de", ["en", "de"]) == "de"
        assert i18n_module._negotiate_from_header("zz", ["en", "de"]) is None

    # Restore the real, babel-backed module for the rest of the suite.
    importlib.reload(i18n_module)
