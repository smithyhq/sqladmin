SQLadmin does not enforce any authentication to your application,
but provides an optional `AuthenticationBackend` you can use.

## AuthenticationBackend

SQLAdmin has a session-based authentication that will allow you
to integrate any existing authentication to it.

The class `AuthenticationBackend` has three methods you need to override:

* `authenticate`: Will be called for validating each incoming request.
* `login`: Will be called only in the login page to validate username/password.
* `logout`: Will be called only for the logout, usually clearing the session.

```python
from sqladmin import Admin
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request
from starlette.responses import RedirectResponse


class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        username, password = form["username"], form["password"]

        # Validate username/password credentials
        # And update session
        request.session.update({"token": "..."})

        return True

    async def logout(self, request: Request) -> bool:
        # Usually you'd want to just clear the session
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        token = request.session.get("token")

        if not token:
            return False

        # Check the token in depth
        return True


authentication_backend = AdminAuth(secret_key="...")
admin = Admin(app=..., authentication_backend=authentication_backend، ...)
```

!!! note
    In order to use AuthenticationBackend you need to install the `itsdangerous` package.

??? example "Full Example"

    ```python
    from sqladmin import Admin, ModelView
    from sqladmin.authentication import AuthenticationBackend
    from sqlalchemy import Column, Integer, String, create_engine
    from sqlalchemy.orm import declarative_base
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import RedirectResponse


    Base = declarative_base()
    engine = create_engine(
        "sqlite:///example.db",
        connect_args={"check_same_thread": False},
    )


    class User(Base):
        __tablename__ = "users"

        id = Column(Integer, primary_key=True)
        name = Column(String)


    Base.metadata.create_all(engine)


    class AdminAuth(AuthenticationBackend):
        async def login(self, request: Request) -> bool:
            request.session.update({"token": "..."})
            return True

        async def logout(self, request: Request) -> bool:
            request.session.clear()
            return True

        async def authenticate(self, request: Request) -> bool:
            token = request.session.get("token")

            if not token:
                return False

            # Check the token in depth
            return True


    app = Starlette()
    authentication_backend = AdminAuth(secret_key="...")
    admin = Admin(app=app, engine=engine, authentication_backend=authentication_backend)


    class UserAdmin(ModelView, model=User):
        def is_visible(self, request: Request) -> bool:
            return True

        def is_accessible(self, request: Request) -> bool:
            return True


    admin.add_view(UserAdmin)
    ```

## Using OAuth

You can also integrate OAuth into SQLAdmin, for this example we will integrate Google OAuth using `Authlib`.
If you have followed the previous example, there are only two changes required to the authentication flow:

```python
from typing import Union

from authlib.integrations.starlette_client import OAuth
from sqladmin.authentication import AuthenticationBackend
from starlette.applications import Starlette
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse


app = Starlette()
app.add_middleware(SessionMiddleware, secret_key="test")

oauth = OAuth()
oauth.register(
    'google',
    client_id='...',
    client_secret='...',
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile',
        'prompt': 'select_account',
    },
)
google = oauth.create_client('google')


class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        return True

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> Union[bool, RedirectResponse]:
        user = request.session.get("user")
        if not user:
            redirect_uri = request.url_for('login_google')
            return await google.authorize_redirect(request, redirect_uri)

        return True


admin = Admin(app=app, engine=engine, authentication_backend=AdminAuth("test"))


async def login_google(request: Request) -> Response:
    token = await google.authorize_access_token(request)
    user = token.get('userinfo')
    if user:
        request.session['user'] = user
    return RedirectResponse(request.url_for("admin:index"))


admin.app.router.add_route("/auth/google", login_google)
```

## Permissions

The `ModelView` and `BaseView` classes in SQLAdmin implements two special methods you can override.
You can use these methods to have control over each Model/View in addition to the AuthenticationBackend.
So this is more like checking if the user has access to the specific Model or View.

* `is_visible`
* `is_accessible`

As you might guess the `is_visible` controls if this Model/View
should be displayed in the menu or not.

The `is_accessible` controls if this Model/View should be accessed.

Both methods implement the same signature and should return a boolean.

!!! note
    For Model/View to be displayed in the sidebar both `is_visible`
    and `is_accessible` should return `True`.

So in order to override these methods:

```python
from starlette.requests import Request


class UserAdmin(ModelView, model=User):
    def is_accessible(self, request: Request) -> bool:
        # Check incoming request
        # For example request.session if using AuthenticationBackend
        return True

    def is_visible(self, request: Request) -> bool:
        # Check incoming request
        # For example request.session if using AuthenticationBackend
        return True
```
