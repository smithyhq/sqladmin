Where [authentication](./authentication.md) answers *who is this request*,
authorization answers *what may they do*. SQLAdmin provides an optional
`AuthorizationBackend` for the second question, and an opt-in group-based
implementation of it in `sqladmin.contrib.rbac`.

Without an authorization backend, the `can_*` class variables and any
`is_accessible` / `check_can_*` overrides you have written keep working as
before. Two internals did change; see [Upgrading](#upgrading) if you subclass
`Admin` or `DBAuditBackend`.

## AuthorizationBackend

The class has three methods:

* `has_permission` (required): called for every permission decision, many
  times per page. It must be cheap and must not perform I/O.
* `load` (optional): called once per request, right after authentication
  succeeds. This is where I/O belongs -- query your database, call your IAM
  service -- storing the result on `request.state`.
* `setup` (optional): called once with the `Admin` when it is created. Raise
  `ImproperlyConfigured` here to report a configuration the backend cannot
  work with at startup.

`load` runs on every admin request that passes authentication -- pages, form
posts, related-object lookups, file downloads, even requests that end in a
`403` or `404`. If it is expensive, cache its result, for example in the session
or in a short-lived cache keyed by user id, and accept that permission changes
then take effect when the cache expires.

`AuthorizationBackend` is abstract, so a subclass that forgets
`has_permission` fails as soon as it is instantiated rather than silently
allowing everything. When you pass no backend, `Admin` uses
`AllowAllAuthorizationBackend`.

```python
from sqladmin import Admin
from sqladmin.authorization import Action, AuthorizationBackend

ROLES = {
    "viewer": {Action.LIST, Action.DETAILS},
    "editor": {Action.LIST, Action.DETAILS, Action.CREATE, Action.EDIT},
}


class RoleAuthorization(AuthorizationBackend):
    def has_permission(self, request, identity, action, obj=None) -> bool:
        if request.session.get("is_admin"):
            return True
        return action in ROLES.get(request.session.get("role"), set())


admin = Admin(
    app,
    engine,
    authentication_backend=AdminAuth(secret_key="..."),
    authorization_backend=RoleAuthorization(),
)
```

That is the whole integration. Every `ModelView` you have already written now
hides its menu entry, its Create button and its per-row Edit/Delete links, and
returns `403` on the matching routes.

### Actions

`action` is one of the `Action` members -- `Action.LIST`, `DETAILS`, `CREATE`,
`EDIT`, `DELETE`, `EXPORT`, `IMPORT` -- or `action:<slug>` for an endpoint
declared with `@action`.

`Action` is a string enum, so each member *is* its string value:
`Action.EDIT == "edit"`, and `("user", Action.EDIT)` and `("user", "edit")` are
the same grant. Use the members for autocompletion and typo safety, or plain
strings where they read better (for example in a database column). To test
whether a string names a built-in action, use `value in ACTIONS`; `value in
Action` raises before Python 3.12.

```python
class UserAdmin(ModelView, model=User):
    @action(name="deactivate", label="Deactivate")
    async def deactivate(self, request):
        ...
```

is asked about as `("user", "action:deactivate")`, which
`custom_action("deactivate")` builds for you. Buttons for actions the user
may not invoke are not rendered, and the endpoint rejects them either way.

The `obj` argument is the specific row being acted on. It is passed for
`details`, `edit` and `delete`, and is `None` everywhere else -- including the
row-less buttons that lead to those pages, so a row-level rule should allow
`obj is None` unless you want to hide the button for everyone:

```python
class OwnerAuthorization(AuthorizationBackend):
    def has_permission(self, request, identity, action, obj=None) -> bool:
        if obj is not None and hasattr(obj, "owner_id"):
            return obj.owner_id == request.session["user_id"]
        return True
```

Row-level rules gate the buttons and the routes, not the query behind the list
page. To hide rows from the listing itself, override `ModelView.list_query`.

### Navigation

By default a `ModelView` is accessible -- listed in the menu and reachable at
all -- when the backend allows at least one action on it: a built-in action the
view has not switched off with a `can_*` flag, or one of the view's own
`@action` endpoints. A grant for a switched-off action, such as `import` on a
view with `can_import = False`, opens nothing. Any view the user can access opens
its list page. Without `list`, the page shows a "You are not authorized to view these
records." notice instead of the rows: no table, search, filters, bulk actions
or pagination, and the rows are never queried. The *Create*, *Import* and
*Export* buttons still appear for users allowed to use them; a user with none
of those sees an empty page. Override the `model_list_not_authorized` block in
your list template to change the notice. If you render `sqladmin/list.html`
from your own route, pass `can_list` -- when it is missing, the rows are shown
as before.

To hide a view from some users entirely -- no menu entry, `403` on every
route -- override `is_accessible`.

!!! warning "`export` and `import` are independent of `list` and `create`"
    Each action is checked on its own; none implies another.

    * `export` is a read permission in its own right: a user granted `export`
      but not `list` can still download the rows.
    * `import` is a write permission in its own right: a user granted `import`
      but not `create` can still add rows by uploading a CSV.

    Grant them as carefully as `list` and `create`, or tie them together in
    `check_can_export` / `check_can_import` if your rules need that.

The related-object search behind `form_ajax_refs` serves the create and edit
forms, so it requires `create` or `edit` on the view. *Save as new* on the edit
page creates a row, so it requires `create` as well as `edit`.

Endpoints you add to a `ModelView` with `@expose` are checked only against
`is_accessible`: anyone who can open the view can call them. Use `@action` for
an endpoint that should have its own grant, or check
`self.has_permission(request, ...)` inside the endpoint.

!!! note "For custom pages, `list` means *view*"
    A custom page (`BaseView`) has no rows, so the only action asked about is
    `list`, and it means "may open this page". `("reports", "list")`,
    `("reports", "*")` and `("*", "list")` all open a `reports` page; any other
    action on it does not. Remember that `("*", "list")` therefore opens every
    custom page as well as every list page.

Each view's `identity` is the key its grants are stored under, so two views
with the same identity share their grants. Custom pages take their identity
from the `@expose`d method's name unless you pass `identity=`, so give each
page an explicit one.

### Grants and wildcards

For the common case of a set of `(identity, action)` pairs, subclass
`GrantsAuthorizationBackend` instead and implement its one method,
`get_grants`. It is called once per request; the grants are kept on the request
and matched with `*` allowed on either side of the pair:

```python
from sqladmin.authorization import Action, GrantsAuthorizationBackend


class SessionAuthorization(GrantsAuthorizationBackend):
    async def get_grants(self, request) -> set[tuple[str, str]]:
        if request.session.get("is_admin"):
            return {("*", "*")}  # a superuser may do everything
        return {("user", Action.LIST), ("movie", "*")}
```

| Grant | Allows |
| --- | --- |
| `("user", "edit")` | editing on the `user` view |
| `("user", "*")` | every action on the `user` view |
| `("*", "edit")` | editing on every view |
| `("*", "*")` | everything |

A `GrantsAuthorizationBackend` whose `load` never ran denies everything rather
than falling open.

If you keep grants as `"identity:action"` strings, split on the *first* colon
only -- custom action names contain one themselves:

```python
identity, action = "user:action:deactivate".split(":", 1)
```

### Third-party engines

An external policy engine is an adapter of `has_permission`:

```python
class CasbinAuthorization(AuthorizationBackend):
    def __init__(self, enforcer):
        self.enforcer = enforcer

    def has_permission(self, request, identity, action, obj=None) -> bool:
        return self.enforcer.enforce(request.session["user"], identity, action)
```

### Precedence

Every decision starts from the view's defaults, which you can override:

* The `can_*` class variables switch an action off for everyone. The routes
  check the flag before calling `check_can_*`, so `can_delete = False` means
  nobody deletes, whatever any grant or override says.
* The default `is_accessible` and `check_can_*` ask the authorization backend.
* An `is_accessible` / `check_can_*` override replaces that default, so it can
  be stricter *or* more permissive than the backend. It cannot turn a
  disabled `can_*` flag back on. To combine your rule with the backend, call
  `super()`.

```python
class AuditLogAdmin(ModelView, model=AuditLog):
    can_edit = False  # nobody, ever
    can_delete = False

    def is_accessible(self, request) -> bool:
        return request.session.get("is_superuser", False)
```

### Identifying the user

Both authorization and [audit logging](./cookbook/audit_logging.md) need to know
who is acting. Implement `AuthenticationBackend.get_user_id` once and both use
it:

```python
class AdminAuth(AuthenticationBackend):
    async def get_user_id(self, request):
        return request.session.get("user_id")
```

The default reads `user_id` from the session. The resolved value is available
anywhere in the request as `sqladmin.authentication.get_current_user_id(request)`,
and it is what `DBAuthorizationBackend` looks the user up by.

!!! warning
    If your `login` stores something else in the session -- the
    [authentication example](./authentication.md) stores a `token` -- override
    `get_user_id` to return the user's primary key. Otherwise every request is
    anonymous, and `DBAuthorizationBackend` answers it with `403`.

## Users, groups and permissions

`sqladmin.contrib.rbac` stores grants in your own database and gives you a
screen to edit them.

SQLAdmin does not ship a `User` model: the primary key type, the password
handling and the columns differ per application, and any app that wants an admin
already has one. It ships the group tables around it.

### Models

```python
from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import mapped_column, relationship

from sqladmin.contrib.rbac import GroupAccessMixin, GroupMixin, user_group_table


class Group(GroupMixin, Base):
    __tablename__ = "admin_groups"


class GroupAccess(GroupAccessMixin, Base):
    __tablename__ = "admin_group_accesses"


# Needs your users table name and primary key type, so it is a factory:
UserGroup = user_group_table(Base, user_table="users", user_pk_type=Integer)


class User(Base):
    __tablename__ = "users"

    id = mapped_column(Integer, primary_key=True)
    email = mapped_column(String)
    is_superuser = mapped_column(Boolean, default=False)

    groups = relationship("Group", secondary=UserGroup)
```

`GroupMixin` gives you `id`, `name` and an `accesses` collection.
`GroupAccessMixin` gives you one `(identity, action)` row per grant, unique per
group. If your classes are not named `Group` / `GroupAccess`, set
`__group_model__`, `__group_table__` or `__access_model__` on the mixins to
match.

The tables are ordinary SQLAlchemy models on your own `Base`, so they are
created by your usual migration tooling.

### Backend

```python
from sqladmin.contrib.rbac import DBAuthorizationBackend

admin = Admin(
    app,
    engine,
    authentication_backend=AdminAuth(secret_key="..."),
    authorization_backend=DBAuthorizationBackend(session_maker, user_model=User),
)
```

The backend looks the user up by the id from
`AuthenticationBackend.get_user_id`, so it needs an `authentication_backend`;
without one, creating the `Admin` fails with `ImproperlyConfigured` rather
than every request silently being denied.

A single query per request reads the user's superuser flag and all the
grants of their groups.
A user whose `is_superuser` is true is granted `("*", "*")`; a user model
without that attribute simply has no superusers. `user_model` is a required
keyword argument, and it needs a single-column primary key. Pass `groups_attr`,
`accesses_attr` or `superuser_attr` if your attributes are named differently;
a wrong relationship name raises `InvalidRelationshipError` when the backend
(or `GroupAdmin`) is created.

Because the grants are read on every request, changing a group in the database
takes effect on the user's next page load -- no restart, no re-login.

### The permission screen

```python
from sqladmin.contrib.rbac import GroupAdmin


class MyGroupAdmin(GroupAdmin, model=Group):
    pass


admin.add_view(MyGroupAdmin)
```

The grant model is taken from the group's `accesses` relationship; set
`accesses_attr` if yours is named differently.

The group form renders a permission matrix instead of a raw list of grant rows:
one row per registered view, one checkbox per action, so an operator ticks
*Users · create* rather than typing `user:create`.

Rows are derived from the views registered on the `Admin` at startup, so adding
a new `ModelView` makes its row appear on the next restart -- there is no
permission table to migrate and no sync step to run. Actions a view has disabled
with `can_*` are not offered, since a grant the class flag overrules is only
confusing. Custom pages (`BaseView`) get a single *Access* checkbox, stored as
their `list` grant.

If you override `form_edit_query` on a `GroupAdmin`, you don't need to load the
grants yourself; the form queries them when they are missing.

Submitted values are validated against the rendered choices, so a forged
permission string fails validation rather than being stored.

Saving only changes the grants the matrix offers. Grants it does not show --
wildcards such as `("*", "*")` added in code or a migration, or grants for an
action a view has since disabled -- are kept as they are. The group and its
grants are written in one transaction.

With an [audit backend](./cookbook/audit_logging.md) configured, the entry for
a group create or update includes `permissions`: the group's grants after the
save, as `"identity:action"` strings, wildcards included:

```python
AuditEntry(
    action="update",
    identity="group",
    pk="3",
    changes={"name": "Editors", "permissions": ["*:*", "article:create"]},
)
```

If you override `on_model_change` or `after_model_change` on your group
admin, call `super()`, or the grants are neither saved nor audited.

### Who may grant what

Whoever can edit a group can change what its members may do. To stop that
from becoming a way to gain access, an editor may by default only *grant*
permissions they hold themselves. Ticking any other box raises
`sqladmin.exceptions.PermissionEscalationError`, which the form shows as an
error, and nothing is saved. Superusers hold every permission.

Taking permissions away is not restricted this way: unticking a box, deleting a
group or removing someone from it cannot give anyone more access. Who may do
those is decided by the ordinary `group` permissions (`edit`, `delete`) and by
your own `check_can_edit` / `check_can_delete` overrides.

The rule lives in `GroupAdmin.can_grant`, so you decide it:

```python
class MyGroupAdmin(GroupAdmin, model=Group):
    def can_grant(self, request, identity, action) -> bool:
        # HR assigns billing access without holding it themselves.
        if identity == "billing":
            return self.has_permission(request, "edit")
        return super().can_grant(request, identity, action)
```

Return `True` unconditionally to let anyone who can edit groups grant
anything.

!!! warning "Editing groups is a privileged action"
    Even with the default rule, someone who can edit groups can hand their own
    permissions to any group, so grant `group` access as carefully as you would
    grant those permissions directly.

    Group *membership* is edited on your own user view, which this rule does
    not cover: anyone who can edit users can add people, themselves included,
    to any group. Restrict that view accordingly.

Restrict the screen itself the ordinary way:

```python
class MyGroupAdmin(GroupAdmin, model=Group):
    def is_accessible(self, request) -> bool:
        return request.session.get("is_superuser", False)
```

## Upgrading

Two existing hooks behave differently, with or without an authorization
backend:

* `Admin._list(request)` now returns whether the list page may show its rows.
  If you override it on an `Admin` subclass, return the result of
  `super()._list(request)`; returning `None` renders the page without rows.
* `DBAuditBackend.get_actor` now returns the id resolved by
  `AuthenticationBackend.get_user_id` instead of `None`. Override it to keep
  the old behaviour.
