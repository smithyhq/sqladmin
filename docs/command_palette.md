The command palette is a modal search available from every page in the admin.
It searches three things at once: your registered models, records inside them,
and commands like "go to" and "create".

Clicking **Search** in the top bar opens it. Everything in the palette is
click-driven; there are no keyboard shortcuts to learn or to collide with your
browser's own.

## How searching works

The palette answers three different questions, and each has a different cost.

**Model names** are matched against the in-memory view registry. No database
query runs, so this stays instant no matter how many models you register.

**Records inside one model** are searched when you pick a model first: click
**Search inside** on any row and it becomes the scope. From then on every
search hits exactly one model, regardless of how many exist — though a model
whose `__str__` touches a relationship listed in `column_list` costs one query
per eager-loaded relation on top of that, the same as anywhere else in
SQLAdmin.

**Records across models** are searched when you type without picking a model.
This is the only mode that fans out, so it is opt-in per model and capped.

## Enabling record search

Set `palette_search` on the views you want included in the global, unscoped
search. It defaults to `False`, so adding the palette to an existing admin never
silently starts querying every table you have.

!!! example

    ```python title="admin.py"
    from sqladmin import Admin, ModelView

    class UserAdmin(ModelView, model=User):
        column_searchable_list = [User.name, User.email]
        palette_search = True
        palette_search_limit = 5
    ```

`column_searchable_list` is required: the palette reuses the same `ilike`
expression as the list page, so a model with no searchable columns is skipped.

- `palette_search`: include this model in unscoped search. Defaults to `False`.
- `palette_search_limit`: rows returned per model. Defaults to `5`.

A model that is not opted in is still reachable through **Search inside**.
Scoping is an explicit choice by the user and always touches one model, so the
opt-in does not apply there.

## Limiting the fan-out

Two settings on `Admin` bound the unscoped search:

!!! example

    ```python title="admin.py"
    admin = Admin(
        app,
        engine,
        palette_search_min_chars=2,
        palette_search_max_models=8,
    )
    ```

- `palette_search_min_chars`: minimum term length before any record query runs.
  Defaults to `2`, which stops a single keystroke from fanning out.
- `palette_search_max_models`: how many opted-in models a single unscoped search
  may touch. Defaults to `8`.

Queries run concurrently on async engines, and sync engines are off-loaded to a
worker thread, the same as everywhere else in SQLAdmin.

## Permissions

The palette never exposes anything the rest of the admin would not.

Views hidden by `is_visible` or rejected by `is_accessible` are not listed, not
searched, and return `404` if named directly as a scope. Individual rows go
through `check_can_view_details`, so a record you are not allowed to open never
appears in the results. Models with `can_view_details = False` are skipped
entirely, since there would be nothing to navigate to.

The endpoint itself is behind the same `login_required` as every other admin
route.

## Commands

Below the matches, the palette offers commands for the model that best fits what
you typed: "Go to *model*", and "Create *model*" when `can_create` allows it.
With an empty search box no commands are shown, since there is no match to act
on.

Override `palette_commands` to add your own:

!!! example

    ```python title="admin.py"
    from starlette.requests import Request

    class UserAdmin(ModelView, model=User):
        column_searchable_list = [User.name, User.email]
        palette_search = True

        def palette_commands(self, request: Request) -> list[dict]:
            commands = super().palette_commands(request)
            commands.append(
                {
                    "label": "Export users as CSV",
                    "url": str(
                        request.url_for(
                            "admin:export",
                            identity=self.identity,
                            export_type="csv",
                        )
                    ),
                    "icon": "↓",
                    "badge": "csv",
                }
            )
            return commands
    ```

Each command is a dictionary:

- `label`: the text to show. `goTo` and `create` are reserved keys resolved
  against the active locale using `name`; any other value is rendered as given.
- `name`: substituted into the `goTo` and `create` labels.
- `url`: where clicking navigates.
- `icon`: optional single character. Defaults to `›`.
- `badge`: optional short tag rendered on the right.

Skip the `super()` call to replace the defaults entirely. Custom labels are not
translated automatically, since the text comes from your own code — wrap it in
`gettext` yourself if you need that.

## Customising the query

`palette_search_query` builds the statement for a single model. Override it for
full-text search, trigram matching, or anything else your database supports:

!!! example

    ```python title="admin.py"
    from sqlalchemy import Select, select
    from starlette.requests import Request

    class ArticleAdmin(ModelView, model=Article):
        column_searchable_list = [Article.title]
        palette_search = True

        def palette_search_query(self, request: Request, term: str) -> Select:
            return (
                select(Article)
                .where(Article.search_vector.match(term))
                .limit(self.palette_search_limit)
            )
    ```

## Relationships and `__str__`

The palette calls `str(obj)` to build each result's label, after the query has
returned. If `__str__` accesses a relationship that was not eager-loaded, the
session is already closed and SQLAlchemy raises `DetachedInstanceError`.

The palette follows the same convention as the rest of SQLAdmin here: it
eager-loads exactly the relations named in `column_list`, the same set already
eager-loaded for the list page. List a relationship there if `__str__` touches
it, even if you do not want it rendered as its own column:

!!! example

    ```python title="admin.py"
    class PlayerAdmin(ModelView, model=Player):
        column_list = [Player.id, Player.name, Player.team]
        column_searchable_list = [Player.name]
        palette_search = True
    ```

A relationship touched by `__str__` but absent from `column_list` will still
crash. For a label built from a relationship you would rather not display,
override `palette_search_query` to eager-load it explicitly instead:

```python
def palette_search_query(self, request: Request, term: str) -> Select:
    from sqlalchemy.orm import selectinload

    stmt = super().palette_search_query(request, term)
    return stmt.options(selectinload(Player.team))
```

## Request-based scoping

`palette_search_query` builds on `list_query(request)` by default, so a view
that restricts `list_query` per request — filtering by tenant from the session,
for example — gets the same restriction applied to palette results
automatically. There is nothing extra to opt into for this to take effect.

## Translations

Every string in the palette is translated, including the ones rendered by
JavaScript as you type. Catalogs ship for the same locales as the rest of the
interface. See [Internationalization](./internationalization.md).