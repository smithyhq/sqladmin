# Profiling and debugging

SQLAdmin does not ship a profiler or a debug toolbar, and does not wire one in for you.
The tools below already work with it, and each one attaches to *your* application rather
than to the admin. That is usually where you want it: SQLAdmin builds its own queries, and
the requests you need to understand are your application's, not the admin's.

None of this requires changes to SQLAdmin. If you want the results inside the admin,
[asgi-profiler](#asgi-profiler) has a built-in [SQLAdmin integration](#sqladmin-integration)
that adds its viewer as an admin page, behind your admin login.

## Choosing a tool

| Tool | Answers | Runs in |
| --- | --- | --- |
| [asgi-profiler](#asgi-profiler) | Which request, which SQL, which N+1 — viewable in the admin | Development/Production |
| [fastapi-debug-toolbar](#fastapi-debug-toolbar) | Same, rendered into the page | Development |
| [debug-toolbar](#debug-toolbar) | Same, plus N+1 flags, `EXPLAIN`, profiling | Development |
| [pyinstrument](#pyinstrument) | Where the time goes *outside* SQL | Development |
| [SQLAlchemy echo](#sqlalchemy-echo) | What SQL ran, in order | Anywhere |
| [py-spy](#py-spy) | Why a live process is slow or stuck | Production |

The first four are development tools. Do not leave any of them enabled on a public
deployment — see [Security](#security).

## When the admin itself is slow

SQLAdmin eager-loads (`selectinload`) every relationship you list directly in
`column_list` or `column_details_list`, so adding `Post.user` to a list page costs one
extra query, not one per row. A few things are not covered by that:

- **Dotted paths and properties.** `column_list = ["user.name"]`, or a `@property` that
  walks relationships, lazy-loads per row. On a ten-row page these took 12 and 22 queries
  respectively. Override `list_query` (or `details_query`) to load what they touch:

    ```python
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload


    class PostAdmin(ModelView, model=Post):
        column_list = [Post.id, "user.name", "author_company"]

        def list_query(self, request):
            return select(Post).options(
                selectinload(Post.user).selectinload(User.company)
            )
    ```

    With that override, both columns together cost 4 queries.

- **To-many relationships in `column_list`.** They are eager-loaded in full. A user with
  500 posts renders all 500 into the list cell.
- **Relationship fields on the edit page.** The select loads every row of the related
  table. `form_ajax_refs` fixes that; see
  [Optimize relationship loading](optimize_relationship_loading.md).
- **Relationships inside `__str__`.** Related objects are rendered after the session has
  closed, so a `__str__` that reaches through another relationship raises
  `DetachedInstanceError` rather than running slowly. Keep `__str__` to columns on the
  model itself.

Use a profiler when you do not yet know *which* page or *which* query is at fault.

## asgi-profiler

[asgi-profiler](https://github.com/mmzeynalli/asgi-profiler) records every request with the
SQL it issued and serves a browsable viewer. Repeated statements collapse into one row with
an `xN` badge, so a 500-row N+1 reads as a single line rather than 500 you have to scroll.

!!! tip "SQLAdmin integration"
    asgi-profiler ships `asgi_profiler.contrib.sqladmin`, which shows the profiler as a page
    inside SQLAdmin, behind your authentication backend. See
    [SQLAdmin integration](#sqladmin-integration) below.

```console
pip install asgi-profiler
```

```python
from asgi_profiler import install
from fastapi import FastAPI
from sqladmin import Admin

app = FastAPI()
admin = Admin(app, engine)

install(app)  # viewer at /profiler
```

Install it on the **parent** application, not on the admin. `Admin` mounts itself onto your
app, so middleware on the parent sees every request, and your own routes are profiled
alongside it.

You do not need to hand it an engine. asgi-profiler hooks SQLAlchemy at the `Engine` class
level, so it captures queries from every engine in the process. The flip side is that it
cannot be scoped to a single engine.

### SQLAdmin integration

asgi-profiler has a built-in SQLAdmin integration, `asgi_profiler.contrib.sqladmin`. Its
`register` function adds the viewer to your admin as a regular page, instead of serving it
on its own route:

```python
from asgi_profiler import install
from asgi_profiler.contrib.sqladmin import register

admin = Admin(app, engine, authentication_backend=auth_backend)

profiler = install(app, mount_path=None)  # record only, no standalone viewer
register(admin, profiler)                 # "Profiler" entry in the admin sidebar
```

This is the recommended setup when you already run the admin:

- The viewer goes through SQLAdmin's `expose`, so it sits behind your
  `authentication_backend`. The standalone viewer has no authentication of its own.
- With an [authorization backend](../authorization.md) configured, the page also needs a
  `list` grant on its identity -- for custom pages, `list` means "may open this page".
  Without it the entry is hidden and the page returns `403`.
- Requests to the admin are **not** recorded by default, so the history shows your
  application's traffic rather than admin page views. Pass `profile_admin=True` when the
  admin itself is what you are debugging.
- `mount_path=None` skips the standalone viewer, so nothing is served outside the admin.

`register` also accepts `name`, `icon` and `category` to place the entry in the sidebar.

### Options and storage

```python
install(
    app,
    mount_path="/_perf",        # default "/profiler"; None to skip the viewer
    exclude_paths=["/healthz"],
    slow_request_ms=500,
    slow_query_ms=50,
    capture_stacks=True,        # which line issued the query
    stack_depth=8,
    authorize=lambda request: request.user.is_staff,
)
```

By default, captures live in a per-process ring buffer and vanish on restart. For captures
that survive a reload, or that are shared across uvicorn workers:

```python
from asgi_profiler import SQLiteStorage, install

install(app, storage=SQLiteStorage("profiler.db", max_requests=5000))
```

The file can then be read without running the app at all:

```console
python -m asgi_profiler profiler.db   # viewer on :8080
```

The standalone viewer has JSON twins — `requests.json`, `summary.json`,
`statements.json` — so a query-count regression can be asserted in CI rather than
noticed six months later.

Two caveats:

- **Overhead is real.** Roughly 20 µs per query, which on a 20-query endpoint is about a
  70% increase in wall time. Use it to find the *shape* of a problem, not to measure
  absolute latency.
- **Admin pages share route groups.** With `profile_admin=True`, SQLAdmin's routes are
  grouped by their pattern, such as `/admin/{identity}/edit/{pk:path}`, so edit pages for
  every model land in one group. Use the per-request view to tell them apart.

It is marked alpha. Treat it as a development tool.

## Debug toolbars

A toolbar renders panels — SQL, timings, headers, templates — directly into the page you
are looking at. Adding one to `Admin` was proposed in
[#1125](https://github.com/smithyhq/sqladmin/pull/1125). SQLAdmin documents them instead,
because a toolbar belongs on your application, which is what it would have been installed
on anyway.

There are two that work with SQLAdmin. Both install into a module named `debug_toolbar`, so
pick one — they cannot be installed side by side.

A toolbar needs an HTML response to inject itself into. It shows on SQLAdmin's list and
edit pages but tells you nothing about JSON endpoints such as
`/admin/{identity}/ajax/lookup`, or about your own API routes. asgi-profiler covers those.

### fastapi-debug-toolbar

[fastapi-debug-toolbar](https://github.com/mongkok/fastapi-debug-toolbar) is the
established FastAPI option:

```console
pip install fastapi-debug-toolbar
```

```python
from debug_toolbar.middleware import DebugToolbarMiddleware
from fastapi import FastAPI

app = FastAPI(debug=True)
app.add_middleware(
    DebugToolbarMiddleware,
    panels=["debug_toolbar.panels.sqlalchemy.SQLAlchemyPanel"],
)
```

The app **must** be constructed with `debug=True` or the toolbar does not render.

### debug-toolbar

[debug-toolbar](https://github.com/JacobCoffee/debug-toolbar)
([docs](https://jacobcoffee.github.io/debug-toolbar)) is an async-native toolbar with a
framework-agnostic core and adapters for Starlette, FastAPI and Litestar. Its SQLAlchemy
panel flags N+1 patterns and duplicate queries and can show `EXPLAIN` plans, and it adds
profiling (with flame graphs), memory and alerts panels on top of the usual set.

The repository is called `debug-toolbar`, but on PyPI it is published as
**`litestar-debug-toolbar`**; `pip install debug-toolbar` finds nothing. Install it with
the `litestar` extra even on FastAPI (see the caveats below):

```console
pip install "litestar-debug-toolbar[fastapi,litestar]" sqlalchemy
```

```python
from debug_toolbar.fastapi import FastAPIDebugToolbarConfig, setup_debug_toolbar
from fastapi import FastAPI
from sqladmin import Admin

app = FastAPI()
admin = Admin(app, engine)

setup_debug_toolbar(
    app,
    FastAPIDebugToolbarConfig(
        enabled=settings.DEBUG,
        extra_panels=["debug_toolbar.extras.advanced_alchemy.SQLAlchemyPanel"],
    ),
)
```

For a plain Starlette app, use `debug_toolbar.starlette` and `StarletteDebugToolbarConfig`
with the `[starlette]` extra instead. Past requests are browsable at `/_debug_toolbar/`.

Call it on the parent application, as above. Despite its module path, the SQLAlchemy panel
does not need Advanced Alchemy: it listens on SQLAlchemy's `Engine` class, so it picks up
any engine, sync or async, with only `sqlalchemy` installed.

Things to know before relying on it (checked against 0.4.2):

- **It needs Litestar installed**, even on FastAPI or Starlette. Without it, the toolbar is
  injected into the page but its stylesheet and script return 500, because the Starlette
  routes import from the Litestar adapter. Adding the `litestar` extra is the workaround.
- **It does not require `debug=True`**, and `enabled` defaults to `True`. There is no
  built-in interlock, so drive `enabled` from a setting yourself.
- **`show_toolbar_callback` does not protect `/_debug_toolbar/`.** It decides which requests
  are recorded and get the toolbar, but the history routes are open to anyone: a request
  the callback rejects can still read the headers and cookies of one it accepted, via
  `/_debug_toolbar/api/requests`.
- It is marked alpha.

## pyinstrument

[pyinstrument](https://github.com/joerick/pyinstrument) answers a different question: not
*what SQL ran*, but *where the Python time went*. Reach for it when a page is slow and the
query count already looks reasonable — form scaffolding, `column_formatters`, or template
rendering over a large `column_list` can all cost more than the database does.

```console
pip install pyinstrument
```

```python
from fastapi import Request
from fastapi.responses import HTMLResponse
from pyinstrument import Profiler

PROFILING = True  # drive this from settings

if PROFILING:

    @app.middleware("http")
    async def profile_request(request: Request, call_next):
        if not request.query_params.get("profile"):
            return await call_next(request)

        profiler = Profiler(interval=0.001)
        profiler.start()
        await call_next(request)
        profiler.stop()
        return HTMLResponse(profiler.output_html())
```

Append `?profile=1` to any URL, in your app or the admin, to get a flame report instead of
the page.

The response is *replaced* by the report, so this works for reading a page's cost but not
for profiling a form submission you also want to succeed.

## SQLAlchemy echo

Before adding any dependency, you can see every statement that runs:

```python
engine = create_engine(DATABASE_URL, echo=True)
```

Or, without touching the engine, through logging, which lets you keep it out of the way
until you want it:

```python
import logging

logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)
```

Crude, but it costs nothing and answers "how many queries does this page run" immediately.
Counting identical `SELECT` lines in the output is usually enough to confirm an N+1 before
you go looking for a nicer tool.

## py-spy

Everything above needs a code change and is unsafe to leave enabled. When a deployed app
is slow or wedged, [py-spy](https://github.com/benfred/py-spy) attaches to a running process
from the outside:

```console
py-spy dump --pid 1234          # what is it doing right now
py-spy top --pid 1234           # live function-level view
py-spy record --pid 1234 -o profile.svg
```

No import, no middleware, no restart. This is the only option on this page that is
reasonable to point at production, and `dump` in particular is the fastest way to tell a
deadlock apart from a slow query.

For ongoing production visibility rather than one-off investigation, instrument with
OpenTelemetry and its SQLAlchemy integration instead — that is telemetry, not profiling.

## Scoping to the admin only

If you want a middleware on the admin and nowhere else, `Admin` accepts middleware for its
sub-application:

```python
from starlette.middleware import Middleware

admin = Admin(
    app,
    engine,
    middlewares=[Middleware(SomeProfilingMiddleware)],
)
```

These run for admin routes only. This is the wrong seam for asgi-profiler and the toolbars,
which expect the application they are installed on; for asgi-profiler, use `register` with
`profile_admin=True` instead.

## Security

Profilers and toolbars expose SQL, bound parameters, request headers and sometimes session
cookies. Next to an admin interface that is a particularly bad combination, since the data
in those queries is usually the data you were protecting with authentication in the first
place.

- Gate them on a setting and leave that setting off by default.
- asgi-profiler's standalone viewer has **no authentication of its own**. Either show it
  inside the admin with `register` and `mount_path=None`, or pass `authorize`:

    ```python
    install(app, authorize=lambda request: request.user.is_staff)
    ```

    `authorize` may be async, so it can hit the database if your staff check needs to.
    asgi-profiler also redacts `Cookie`, `Authorization` and similar headers by default.

- `fastapi-debug-toolbar` requires `debug=True`, which you should not be running in
  production for unrelated reasons. Treat that requirement as a safety interlock.
- `debug-toolbar` has no such interlock, and its `/_debug_toolbar/` history is readable by
  anyone who can reach the app, whatever `show_toolbar_callback` returns. Set `enabled`
  from a setting, and keep that path off any network you do not control.
