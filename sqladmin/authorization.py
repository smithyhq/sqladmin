from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import TYPE_CHECKING, Any

from starlette.requests import Request

if TYPE_CHECKING:
    from sqladmin.application import BaseAdmin

__all__ = [
    "ACTIONS",
    "Action",
    "WILDCARD",
    "AllowAllAuthorizationBackend",
    "AuthorizationBackend",
    "GrantsAuthorizationBackend",
    "custom_action",
    "matches_grant",
]

WILDCARD = "*"
"""Matches any identity or any action in a grant pair."""

_GRANTS_STATE_ATTR = "sqladmin_grants"


class Action(str, Enum):
    """The built-in actions SQLAdmin asks about.

    Members are plain strings as well, so ``Action.EDIT == "edit"`` and a grant
    stored as ``("user", "edit")`` matches ``("user", Action.EDIT)`` -- use
    whichever reads better.

    ???+ usage
        ```python
        from sqladmin.authorization import Action

        grants = {("user", Action.LIST), ("user", Action.EDIT)}
        ```

    Custom actions declared with [`@action`][sqladmin.application.action] are
    asked about as ``"action:<slug>"`` -- see
    [`custom_action`][sqladmin.authorization.custom_action].
    """

    LIST = "list"
    DETAILS = "details"
    CREATE = "create"
    EDIT = "edit"
    DELETE = "delete"
    EXPORT = "export"
    IMPORT = "import"

    # ``enum.StrEnum`` needs Python 3.11. Without this, Python 3.12+ formats a
    # ``(str, Enum)`` member as ``"Action.EDIT"`` in f-strings.
    __str__ = str.__str__


ACTIONS: tuple[Action, ...] = tuple(Action)
"""Every [`Action`][sqladmin.authorization.Action], in display order."""


def custom_action(slug: str) -> str:
    """Return the action name used for a custom `@action` endpoint."""

    return f"action:{slug}"


def matches_grant(
    grants: set[tuple[str, str]],
    identity: str,
    action: str,
) -> bool:
    """Check ``(identity, action)`` against a set of grants, honouring wildcards.

    A grant of ``("*", "edit")`` allows editing every view, ``("user", "*")``
    allows every action on the ``user`` view, and ``("*", "*")`` allows
    everything.
    """

    return (
        (identity, action) in grants
        or (WILDCARD, action) in grants
        or (identity, WILDCARD) in grants
        or (WILDCARD, WILDCARD) in grants
    )


class AuthorizationBackend(ABC):
    """Base class for deciding *what* the current user may do.

    Where [`AuthenticationBackend`][sqladmin.authentication.AuthenticationBackend]
    answers "who is this request", this answers "may they do this". Subclass
    it and implement
    [`has_permission`][sqladmin.authorization.AuthorizationBackend.has_permission],
    then pass an instance as ``Admin(authorization_backend=...)``.

    ???+ usage
        ```python
        class RoleAuthorization(AuthorizationBackend):
            def has_permission(self, request, identity, action, obj=None):
                role = request.session.get("role")
                return role == "admin" or action in ("list", "details")


        admin = Admin(app, engine, authorization_backend=RoleAuthorization())
        ```

    Without one, `Admin` uses
    [`AllowAllAuthorizationBackend`][sqladmin.authorization.AllowAllAuthorizationBackend].
    """

    def setup(self, admin: BaseAdmin) -> None:
        """Check that ``admin`` is configured the way this backend needs.

        Called once, when the `Admin` is created. Raise
        [`ImproperlyConfigured`][sqladmin.exceptions.ImproperlyConfigured] to
        report a mistake at startup rather than on the first request.

        Does nothing by default.
        """

    async def load(self, request: Request) -> None:
        """Prepare per-request authorization state.

        Called once per request, right after authentication succeeds and before
        any permission is checked. This is where I/O belongs -- query the
        database, call an external service -- storing the result on
        ``request.state`` for `has_permission` to read.

        Does nothing by default.
        """

    @abstractmethod
    def has_permission(
        self,
        request: Request,
        identity: str,
        action: str,
        obj: Any | None = None,
    ) -> bool:
        """Return whether the current user may perform ``action`` on ``identity``.

        Args:
            request: The current request.
            identity: The `ModelView.identity` (or `BaseView.identity`) being
                acted on.
            action: One of [`Action`][sqladmin.authorization.Action], or
                ``"action:<slug>"`` for a custom `@action` endpoint.
            obj: The specific object being acted on, when there is one. Passed
                for ``details``, ``edit`` and ``delete``; ``None`` everywhere
                else, including the row-less buttons that lead to those pages.

        This method is called many times while rendering a single page -- once
        per row on the list page -- so it must be cheap and must not perform
        I/O. Do the lookups in
        [`load`][sqladmin.authorization.AuthorizationBackend.load].
        """


class AllowAllAuthorizationBackend(AuthorizationBackend):
    """The backend `Admin` uses when none is configured: it allows everything.

    With it, only the ``can_*`` flags and your own ``is_accessible`` /
    ``check_can_*`` overrides decide what users may do.
    """

    def has_permission(
        self,
        request: Request,
        identity: str,
        action: str,
        obj: Any | None = None,
    ) -> bool:
        return True


class GrantsAuthorizationBackend(AuthorizationBackend):
    """An `AuthorizationBackend` backed by a set of ``(identity, action)`` grants.

    Subclasses implement
    [`get_grants`][sqladmin.authorization.GrantsAuthorizationBackend.get_grants];
    this class loads them once per request and matches them, wildcards
    included. A superuser is simply granted ``("*", "*")``.

    ???+ usage
        ```python
        class SessionAuthorization(GrantsAuthorizationBackend):
            async def get_grants(self, request):
                if request.session.get("is_admin"):
                    return {("*", "*")}
                # "user:action:deactivate" -> ("user", "action:deactivate")
                return {tuple(g.split(":", 1)) for g in request.session["grants"]}
        ```
    """

    @abstractmethod
    async def get_grants(self, request: Request) -> set[tuple[str, str]]:
        """Return the ``(identity, action)`` pairs granted to the current user.

        Called once per request from `load`. Either element of a pair may be
        [`WILDCARD`][sqladmin.authorization.WILDCARD]; return
        ``{("*", "*")}`` for a user who may do everything.
        """

    async def load(self, request: Request) -> None:
        setattr(request.state, _GRANTS_STATE_ATTR, await self.get_grants(request))

    def has_permission(
        self,
        request: Request,
        identity: str,
        action: str,
        obj: Any | None = None,
    ) -> bool:
        # ``None`` means ``load()`` never ran -- deny rather than fall open.
        grants = getattr(request.state, _GRANTS_STATE_ATTR, None)
        return grants is not None and matches_grant(grants, identity, action)
