from __future__ import annotations

import datetime
import pathlib
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from starlette.datastructures import MutableHeaders
from starlette.requests import HTTPConnection
from starlette.types import ASGIApp, Message, Receive, Scope, Send

__all__ = [
    "BABEL_INSTALLED",
    "DEFAULT_LOCALE",
    "SUPPORTED_LOCALES",
    "I18nConfig",
    "LocaleMiddleware",
    "gettext",
    "ngettext",
    "lazy_gettext",
    "get_locale",
    "set_locale",
    "get_locale_display_name",
    "format_datetime",
    "format_date",
    "format_time",
]

DEFAULT_LOCALE = "en"
"""The fallback locale used when no translation catalog matches."""

LOCALE_QUERY_PARAM = "lang"
"""Query string key read by `LocaleMiddleware` to switch the active locale."""

LANGUAGE_COOKIE_MAX_AGE = 365 * 24 * 60 * 60
"""Lifetime in seconds of the persisted language cookie (one year)."""

SUPPORTED_LOCALES = [
    "en",  # English
    "de",  # German
    "az",  # Azerbaijani
    "ru",  # Russian
    "tr",  # Turkish
]
"""Locale codes for which a compiled catalog ships with the package."""


try:
    from babel import Locale, dates
    from babel.support import LazyProxy, NullTranslations, Translations

    BABEL_INSTALLED = True

    translations: Dict[str, NullTranslations] = {
        locale: Translations.load(
            dirname=pathlib.Path(__file__).parent.joinpath("translations"),
            locales=[locale],
            domain="admin",
        )
        for locale in SUPPORTED_LOCALES
    }

    _current_locale: ContextVar[str] = ContextVar(
        "sqladmin_current_locale", default=DEFAULT_LOCALE
    )
    _current_translation: ContextVar[NullTranslations] = ContextVar(
        "sqladmin_current_translation", default=translations[DEFAULT_LOCALE]
    )

    def set_locale(locale: str) -> None:
        """Activate `locale` for the current request context.

        Both the active locale code and its loaded catalog are stored in
        context variables, so `gettext` calls made anywhere downstream resolve
        against the right language. An unsupported locale falls back to
        `DEFAULT_LOCALE`.

        Args:
            locale: The locale code to activate.

        Example:
            ```python
            from sqladmin.i18n import set_locale, gettext

            set_locale("az")
            gettext("Logout")  # "Çıxış"
            ```
        """
        _current_locale.set(locale if locale in translations else DEFAULT_LOCALE)
        _current_translation.set(translations[get_locale()])

    def get_locale() -> str:
        """Return the locale active for the current request.

        Returns:
            The active locale code, or `DEFAULT_LOCALE` outside of a request.

        Example:
            ```python
            from sqladmin.i18n import get_locale

            get_locale()  # "en"
            ```
        """
        return _current_locale.get()

    def gettext(message: str) -> str:
        """Translate `message` using the active locale.

        Installed into the template environment as both ``gettext`` and ``_``,
        and safe to call directly from Python running inside a request, e.g.
        when building a flash message.

        Args:
            message: The source string to translate.

        Returns:
            The translated string, or `message` unchanged when untranslated.

        Example:
            ```python
            from sqladmin.i18n import gettext as _

            _("Logout")
            ```
        """
        return _current_translation.get().gettext(message)

    def ngettext(msgid1: str, msgid2: str, n: int) -> str:
        """Translate a pluralised message using the active locale.

        The plural form is selected by the ``Plural-Forms`` rule compiled into
        the locale's catalog, so languages with more than two forms (Russian,
        Polish, Arabic, ...) are handled correctly.

        Args:
            msgid1: The source string for the singular form.
            msgid2: The source string for the other forms.
            n: The count that selects the plural form.

        Returns:
            The translated form for `n` in the active locale.

        Example:
            ```python
            from sqladmin.i18n import ngettext

            ngettext("%(num)d item", "%(num)d items", 5)
            ```
        """
        return _current_translation.get().ngettext(msgid1, msgid2, n)

    def lazy_gettext(message: str) -> str:
        """Return a lazily evaluated translation of `message`.

        The string is only translated when it is rendered, which makes it safe
        to use at import time or module scope where no request locale exists
        yet.

        Args:
            message: The source string to translate.

        Returns:
            A proxy that resolves to the translated string on use.

        Example:
            ```python
            from sqladmin.i18n import lazy_gettext as _

            LABEL = _("Save")
            ```
        """
        return LazyProxy(gettext, message)  # type: ignore[return-value]

    def format_datetime(
        value: datetime.datetime,
        format: Optional[str] = None,
        tzinfo: Any = None,
    ) -> str:
        """Format a datetime for the active locale using Babel.

        Args:
            value: The datetime to format.
            format: A Babel format name or pattern. Defaults to ``"medium"``.
            tzinfo: Optional timezone to convert to before formatting.

        Returns:
            The localized datetime string.
        """
        return dates.format_datetime(value, format or "medium", tzinfo, get_locale())

    def format_date(value: datetime.date, format: Optional[str] = None) -> str:
        """Format a date for the active locale using Babel.

        Args:
            value: The date to format.
            format: A Babel format name or pattern. Defaults to ``"medium"``.

        Returns:
            The localized date string.
        """
        return dates.format_date(value, format or "medium", get_locale())

    def format_time(
        value: datetime.time,
        format: Optional[str] = None,
        tzinfo: Any = None,
    ) -> str:
        """Format a time for the active locale using Babel.

        Args:
            value: The time to format.
            format: A Babel format name or pattern. Defaults to ``"medium"``.
            tzinfo: Optional timezone to convert to before formatting.

        Returns:
            The localized time string.
        """
        return dates.format_time(value, format or "medium", tzinfo, get_locale())

    def get_locale_display_name(locale: str) -> str:
        """Return the native display name of a locale.

        Resolved through Babel's CLDR data, so the result is the language's own
        endonym (e.g. ``"Azərbaycan"`` for ``az``). Only the first character is
        upper-cased, which keeps multi-word names such as ``"português (Brasil)"``
        intact.

        Args:
            locale: The locale code.

        Returns:
            The native display name, or the locale code when unavailable.

        Example:
            ```python
            from sqladmin.i18n import get_locale_display_name

            get_locale_display_name("az")  # "Azərbaycan"
            ```
        """
        display_name = Locale.parse(locale).display_name
        if not display_name:
            return locale
        return display_name[0].upper() + display_name[1:]

except ImportError:
    # Provide a degraded but functional i18n surface when babel is absent:
    # every message is returned untranslated so the admin keeps rendering.
    BABEL_INSTALLED = False

    def set_locale(locale: str) -> None:
        pass

    def get_locale() -> str:
        return DEFAULT_LOCALE

    def gettext(message: str) -> str:
        return message

    def ngettext(msgid1: str, msgid2: str, n: int) -> str:
        return msgid1 if n == 1 else msgid2

    def lazy_gettext(message: str) -> str:
        return gettext(message)

    def format_datetime(
        value: datetime.datetime,
        format: Optional[str] = None,
        tzinfo: Any = None,
    ) -> str:
        if tzinfo is not None:
            value = value.astimezone(tzinfo)
        return value.strftime(format or "%B %d, %Y %H:%M:%S")

    def format_date(value: datetime.date, format: Optional[str] = None) -> str:
        return value.strftime(format or "%B %d, %Y")

    def format_time(
        value: datetime.time,
        format: Optional[str] = None,
        tzinfo: Any = None,
    ) -> str:
        return value.strftime(format or "%H:%M:%S")

    def get_locale_display_name(locale: str) -> str:
        return locale


@dataclass
class I18nConfig:
    """Internationalization configuration for the admin interface.

    Pass an instance to `Admin` to enable translation. Translation requires the
    optional ``babel`` dependency, installable with ``pip install sqladmin[i18n]``.

    Attributes:
        default_locale: Locale used when no preference is detected.
        language_cookie_name: Cookie that persists the visitor's choice. Set to
            `None` to disable cookie detection.
        language_header_name: Request header inspected for a preferred locale.
            Set to `None` to disable header detection.
        language_switcher: Locale codes offered in the navigation switcher. When
            `None` (the default) no switcher is shown.

    Example:
        ```python
        from sqladmin import Admin
        from sqladmin.i18n import I18nConfig

        admin = Admin(
            app,
            engine,
            i18n_config=I18nConfig(
                default_locale="az",
                language_switcher=["en", "az", "de", "ru", "tr"],
            ),
        )
        ```
    """

    default_locale: str = DEFAULT_LOCALE
    language_cookie_name: Optional[str] = "language"
    language_header_name: Optional[str] = "Accept-Language"
    language_switcher: Optional[List[str]] = None


def _negotiate_from_header(header: str, available: List[str]) -> Optional[str]:
    """Pick the best supported locale from an ``Accept-Language`` header."""
    try:
        from babel.core import negotiate_locale
    except ImportError:
        return header if header in available else None

    preferred: List[tuple[float, str]] = []
    for part in header.split(","):
        token = part.strip()
        if not token:
            continue
        value, _, params = token.partition(";")
        quality = 1.0
        if params.strip().startswith("q="):
            try:
                quality = float(params.strip()[2:])
            except ValueError:
                quality = 0.0
        preferred.append((quality, value.strip()))

    ordered = [v for _, v in sorted(preferred, key=lambda i: i[0], reverse=True)]
    return negotiate_locale(ordered, available, sep="-")


class LocaleMiddleware:
    """ASGI middleware that resolves the active locale for each request.

    Resolution order, highest priority first:

    1. The ``?lang=`` query parameter (also persisted to the language cookie).
    2. The language cookie named by `I18nConfig.language_cookie_name`.
    3. The header named by `I18nConfig.language_header_name`.
    4. `I18nConfig.default_locale`.

    Only locales in `SUPPORTED_LOCALES` are accepted. The middleware is added
    automatically by `Admin` when an `I18nConfig` is supplied.

    Args:
        app: The wrapped ASGI application.
        i18n_config: The active i18n configuration.
        cookie_path: Path scope for the persisted language cookie.
    """

    def __init__(
        self,
        app: ASGIApp,
        i18n_config: I18nConfig,
        cookie_path: str = "/",
    ) -> None:
        self.app = app
        self.i18n_config = i18n_config
        self.cookie_path = cookie_path

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        conn = HTTPConnection(scope)
        config = self.i18n_config
        locale = config.default_locale
        persist = False

        requested = conn.query_params.get(LOCALE_QUERY_PARAM)
        cookie = (
            conn.cookies.get(config.language_cookie_name)
            if config.language_cookie_name
            else None
        )
        header = (
            conn.headers.get(config.language_header_name)
            if config.language_header_name
            else None
        )

        if requested in SUPPORTED_LOCALES:
            locale, persist = requested, True  # type: ignore[assignment]
        elif cookie in SUPPORTED_LOCALES:
            locale = cookie  # type: ignore[assignment]
        elif header:
            matched = _negotiate_from_header(header, SUPPORTED_LOCALES)
            if matched is not None:
                locale = matched

        set_locale(locale)

        async def send_wrapper(message: Message) -> None:
            if (
                persist
                and config.language_cookie_name
                and message["type"] == "http.response.start"
            ):
                headers = MutableHeaders(scope=message)
                headers.append(
                    "set-cookie",
                    f"{config.language_cookie_name}={locale}; "
                    f"Path={self.cookie_path}; Max-Age={LANGUAGE_COOKIE_MAX_AGE}; "
                    "SameSite=lax",
                )
            await send(message)

        await self.app(scope, receive, send_wrapper)
