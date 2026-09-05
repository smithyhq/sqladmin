from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from starlette.requests import Request

__all__ = [
    "ACTIONS",
    "WILDCARD",
    "AuthorizationBackend",
    "GrantsAuthorizationBackend",
    "custom_action",
    "matches_grant",
]

WILDCARD = "*"
"""Matches any identity or any action in a grant pair."""

ACTIONS = (
    "list",
    "details",
    "create",
    "edit",
    "delete",
    "export",
    "import",
)
"""The built-in actions SQLAdmin asks about.

Custom actions declared with [`@action`][sqladmin.application.action] are asked
about as ``"action:<slug>"`` -- see
[`custom_action`][sqladmin.authorization.custom_action].
"""


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


class AuthorizationBackend:
    """Base class for deciding *what* the current user may do.

    Where [`AuthenticationBackend`][sqladmin.authentication.AuthenticationBackend]
    answers "who is this request", this answers "may they do this". Subclass
    it and override
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

    The default implementation allows everything, so adding a backend without
    overriding anything changes no behaviour.
    """

    async def load(self, request: Request) -> None:
        """Prepare per-request authorization state.

        Called once per request, right after authentication succeeds and before
        any permission is checked. This is where I/O belongs -- query the
        database, call an external service -- storing the result on
        ``request.state`` for `has_permission` to read.

        Does nothing by default.
        """

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
            action: One of [`ACTIONS`][sqladmin.authorization.ACTIONS], or
                ``"action:<slug>"`` for a custom `@action` endpoint.
            obj: The specific object being acted on, when there is one. Passed
                for ``details``, ``edit`` and ``delete``; ``None`` everywhere
                else, including the row-less buttons that lead to those pages.

        This method is called many times while rendering a single page -- once
        per row on the list page -- so it must be cheap and must not perform
        I/O. Do the lookups in
        [`load`][sqladmin.authorization.AuthorizationBackend.load].
        """

        return True

    def has_any_permission(
        self,
        request: Request,
        identity: str,
        actions: Sequence[str] | None = None,
    ) -> bool:
        """Return whether the user may do *anything* with ``identity``.

        Drives `ModelView.is_accessible`, which gates the menu entry and every
        route of a view. The default asks
        [`has_permission`][sqladmin.authorization.AuthorizationBackend.has_permission]
        about each action in turn; override it if your backend can answer that
        more directly.

        Args:
            actions: The actions to consider. Defaults to
                [`ACTIONS`][sqladmin.authorization.ACTIONS]; views pass their
                own custom actions in as well, so a user granted only
                ``action:deactivate`` can still reach the view.
        """

        return any(
            self.has_permission(request, identity, action)
            for action in (ACTIONS if actions is None else actions)
        )


class GrantsAuthorizationBackend(AuthorizationBackend):
    """An `AuthorizationBackend` backed by a set of ``(identity, action)`` grants.

    Subclasses implement
    [`get_grants`][sqladmin.authorization.GrantsAuthorizationBackend.get_grants]
    (and optionally
    [`is_superuser`][sqladmin.authorization.GrantsAuthorizationBackend.is_superuser]);
    this class handles caching them on the request and matching them, wildcards
    included.

    ???+ usage
        ```python
        class SessionAuthorization(GrantsAuthorizationBackend):
            async def get_grants(self, request):
                return {tuple(g.split(":")) for g in request.session["grants"]}
        ```
    """

    grants_state_attr = "sqladmin_grants"
    superuser_state_attr = "sqladmin_superuser"

    async def get_grants(self, request: Request) -> set[tuple[str, str]]:
        """Return the ``(identity, action)`` pairs granted to the current user.

        Called once per request from `load`. Either element of a pair may be
        [`WILDCARD`][sqladmin.authorization.WILDCARD].
        """

        raise NotImplementedError(
            "Subclasses of GrantsAuthorizationBackend must implement get_grants()."
        )

    async def is_superuser(self, request: Request) -> bool:
        """Return whether the current user bypasses grant checks entirely.

        ``False`` by default.
        """

        return False

    async def load(self, request: Request) -> None:
        setattr(
            request.state, self.superuser_state_attr, await self.is_superuser(request)
        )
        setattr(request.state, self.grants_state_attr, await self.get_grants(request))

    def has_permission(
        self,
        request: Request,
        identity: str,
        action: str,
        obj: Any | None = None,
    ) -> bool:
        if getattr(request.state, self.superuser_state_attr, False):
            return True

        grants = getattr(request.state, self.grants_state_attr, None)
        if grants is None:
            # ``load()`` never ran -- deny rather than fall open.
            return False

        return matches_grant(grants, identity, action)
