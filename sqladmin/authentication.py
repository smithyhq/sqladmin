from __future__ import annotations

import functools
import hashlib
import inspect
from typing import Any, Callable

from litestar import Request
from litestar.response import Redirect, Response


class AuthenticationBackend:
    """Base class for implementing the Authentication into SQLAdmin.
    You need to inherit this class and override the methods:
    `login`, `logout` and `authenticate`.
    """

    def __init__(self, secret_key: str | bytes, **session_kwargs: Any) -> None:
        from litestar.middleware.session.client_side import CookieBackendConfig

        secret_bytes = (
            secret_key.encode("utf-8") if isinstance(secret_key, str) else secret_key
        )
        session_config = CookieBackendConfig(
            secret=hashlib.sha256(secret_bytes).digest(), **session_kwargs
        )
        self.middlewares = [
            session_config.middleware,
        ]

    async def login(self, request: Request) -> bool:
        """Implement login logic here.
        You can access the login form data `await request.form()`
        and validate the credentials.
        """
        raise NotImplementedError()

    async def logout(self, request: Request) -> Response | bool:
        """Implement logout logic here.
        This will usually clear the session with `request.session.clear()`.

        If a `Response` or `Redirect` is returned,
        that response is returned to the user,
        otherwise the user will be redirected to the index page.
        """
        raise NotImplementedError()

    async def authenticate(self, request: Request) -> Response | bool:
        """Implement authenticate logic here.
        This method will be called for each incoming request
        to validate the authentication.

        If a `Response` or `Redirect` is returned,
        that response is returned to the user,
        otherwise a True/False is expected.
        """
        raise NotImplementedError()


def login_required(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator to check authentication of Admin routes.
    If no authentication backend is setup, this will do nothing.
    """

    @functools.wraps(func)
    async def wrapper_decorator(*args: Any, **kwargs: Any) -> Any:
        view = args[0] if args else getattr(func, "__self__", None)
        request = kwargs.get("request") or (args[1] if len(args) > 1 else None)
        if request is None:
            raise RuntimeError("Request is required for sqladmin route handlers")

        admin = getattr(view, "_admin_ref", view)
        auth_backend = getattr(admin, "authentication_backend", None)
        if auth_backend is not None:
            response = await auth_backend.authenticate(request)
            if isinstance(response, Response):
                return response
            if not bool(response):
                return Redirect(request.url_for("admin:login"), status_code=302)

        if inspect.iscoroutinefunction(func):
            return await func(*args, **kwargs)
        return func(*args, **kwargs)

    return wrapper_decorator
