from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from typing import Any

from starlette import status
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response


class AuthenticationBackend:
    """Base class for implementing the Authentication into SQLAdmin.
    You need to inherit this class and override the methods:
    `login`, `logout` and `authenticate`.
    """

    def __init__(self, secret_key: str, **session_kwargs: Any) -> None:
        from starlette.middleware.sessions import SessionMiddleware

        self.middlewares = [
            Middleware(SessionMiddleware, secret_key=secret_key, **session_kwargs),
        ]

    async def login(self, request: Request) -> Response | bool:
        """Implement login logic here.
        You can access the login form data `await request.form()`
        and validate the credentials.
        """
        raise NotImplementedError()

    async def logout(self, request: Request) -> Response | bool:
        """Implement logout logic here.
        This will usually clear the session with `request.session.clear()`.

        If a `Response` or `RedirectResponse` is returned,
        that response is returned to the user,
        otherwise the user will be redirected to the index page.
        """
        raise NotImplementedError()

    async def authenticate(self, request: Request) -> Response | bool:
        """Implement authenticate logic here.
        This method will be called for each incoming request
        to validate the authentication.

        If a `Response` or `RedirectResponse` is returned,
        that response is returned to the user,
        otherwise a True/False is expected.
        """
        raise NotImplementedError()

    async def get_user_id(self, request: Request) -> Any:
        """Return an identifier for the authenticated user, or `None`.

        Called once per request after `authenticate` succeeds. The result is
        stored on the request and read back by
        [`get_current_user_id`][sqladmin.authentication.get_current_user_id],
        so everything that needs to know *who* is acting -- the audit backend
        and the authorization backend among them -- shares one answer instead
        of each re-deriving it.

        The default reads ``user_id`` from the session, which suits the
        session-based login flow in the docs. Override it for anything else.
        """

        if "session" in request.scope:
            return request.session.get("user_id")
        return None


USER_ID_STATE_ATTR = "sqladmin_user_id"
_AUTHORIZATION_LOADED_ATTR = "sqladmin_authorization_loaded"


def get_current_user_id(request: Request) -> Any:
    """Return the user id resolved for this request, or `None`.

    Populated from
    [`AuthenticationBackend.get_user_id`][sqladmin.authentication.AuthenticationBackend.get_user_id]
    when the request enters an Admin route.
    """

    return getattr(request.state, USER_ID_STATE_ATTR, None)


def login_required(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator to check authentication of Admin routes.
    If no authentication backend is setup, this will do nothing.

    Once authentication passes, the authorization backend's
    [`load`][sqladmin.authorization.AuthorizationBackend.load] hook runs, so
    every permission check further down the request sees prepared state.
    """

    @functools.wraps(func)
    async def wrapper_decorator(*args: Any, **kwargs: Any) -> Any:
        view, request = args[0], args[1]
        admin = getattr(view, "_admin_ref", view)
        auth_backend = getattr(admin, "authentication_backend", None)
        if auth_backend is not None:
            response = await auth_backend.authenticate(request)
            if isinstance(response, Response):
                return response
            if not bool(response):
                return RedirectResponse(
                    request.url_for("admin:login"), status_code=status.HTTP_302_FOUND
                )

            if not hasattr(request.state, USER_ID_STATE_ATTR):
                setattr(
                    request.state,
                    USER_ID_STATE_ATTR,
                    await auth_backend.get_user_id(request),
                )

        authz_backend = getattr(admin, "authorization_backend", None)
        if authz_backend is not None and not getattr(
            request.state, _AUTHORIZATION_LOADED_ATTR, False
        ):
            setattr(request.state, _AUTHORIZATION_LOADED_ATTR, True)
            await authz_backend.load(request)

        if inspect.iscoroutinefunction(func):
            return await func(*args, **kwargs)
        return func(*args, **kwargs)

    return wrapper_decorator
