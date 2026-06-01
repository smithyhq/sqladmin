# SQLAlchemy Admin for Litestar

SQLAdmin is a flexible admin interface for SQLAlchemy models, adapted for [Litestar](https://litestar.dev).

Main features:

- SQLAlchemy sync/async engines
- Litestar ASGI framework integration
- WTForms form scaffolding
- SQLModel support
- Tabler-based UI
- Export to CSV/JSON
- Authentication via session cookies
- AJAX lookups for relationships
- Column filters and search
- Custom views and actions

## Installation

```bash
pip install sqladmin-litestar

# With full optional dependencies
pip install "sqladmin-litestar[full]"
```

## Quickstart

Define your SQLAlchemy model:

```python
from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase

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
```

Create the Litestar app and register the admin:

```python
from litestar import Litestar
from sqladmin import Admin, ModelView

app = Litestar()
admin = Admin(app, engine)

class UserAdmin(ModelView, model=User):
    column_list = [User.id, User.name]

admin.add_view(UserAdmin)
```

Visit `/admin` in your browser to see the admin interface.

## Using async engine

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

async_engine = create_async_engine("sqlite+aiosqlite:///example.db")
admin = Admin(app, async_engine)
```

## Authentication

```python
from litestar import Request
from litestar.response import Redirect
from sqladmin import Admin
from sqladmin.authentication import AuthenticationBackend

class MyAuthBackend(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        username = form.get("username")
        password = form.get("password")
        # validate credentials
        return True

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool | Redirect:
        if "user_id" not in request.session:
            return Redirect(request.url_for("admin:login"), status_code=302)
        return True

auth_backend = MyAuthBackend(secret_key="your-secret-key")
admin = Admin(app, engine, authentication_backend=auth_backend)
```

## Custom Views

```python
from sqladmin import BaseView, expose

class MyView(BaseView):
    name = "Dashboard"
    icon = "fa-solid fa-chart-line"

    @expose("/dashboard", methods=["GET"])
    async def dashboard(self, request: Request):
        return await self.templates.TemplateResponse(
            request, "custom_dashboard.html"
        )

admin.add_base_view(MyView)
```

## Model Configuration

```python
class UserAdmin(ModelView, model=User):
    # Permissions
    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True
    can_export = True

    # List columns
    column_list = [User.id, User.name, User.email]

    # Form columns
    form_excluded_columns = [User.id]

    # Search
    column_searchable_list = [User.name, User.email]

    # Sorting
    column_sortable_list = [User.id, User.name]

    # Filters
    column_filters = [User.is_active]

    # Labels
    column_labels = {User.email: "Email Address"}

    # Page size
    page_size = 25
```

## Key differences from the original Starlette/FastAPI version

1. **Framework**: Built for Litestar — uses `Litestar()` instead of `FastAPI()` or `Starlette()`
2. **Session middleware**: Uses Litestar's `CookieBackendConfig` (client-side sessions) instead of Starlette's `SessionMiddleware`
3. **Routing**: Registers `HTTPRouteHandler` directly on the main Litestar app, no sub-mounting
4. **Static files**: Served via a dedicated route handler, not `StaticFiles` mount
5. **Imports**: `from litestar import Request`, `from litestar.response import Redirect, Response` — no Starlette imports
6. **Templates**: Uses `jinja2.Environment(enable_async=True)` with `await template.render_async()` — template methods must be async
7. **Model methods**: `get_prop_value`, `get_list_value`, `get_detail_value`, `check_can_view_details`, `check_can_edit`, `check_can_delete` are `async def` — must be `await`ed
8. **Dependencies**: Depends on `litestar` instead of `starlette` or `fastapi`

## License

BSD-3-Clause
