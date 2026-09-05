Where [authentication](./authentication.md) answers *who is this request*,
authorization answers *what may they do*. SQLAdmin provides an optional
`AuthorizationBackend` for the second question, and an opt-in group-based
implementation of it in `sqladmin.contrib.rbac`.

Without an authorization backend nothing changes: the `can_*` class variables
and any `is_accessible` / `check_can_*` overrides you have written keep working
exactly as before.

## AuthorizationBackend

The class has two methods:

* `load`: called once per request, right after authentication succeeds. This is
  where I/O belongs -- query your database, call your IAM service -- storing the
  result on `request.state`.
* `has_permission`: called for every permission decision, many times per page.
  It must be cheap and must not perform I/O.

```python
from sqladmin import Admin
from sqladmin.authorization import AuthorizationBackend

ROLES = {
    "viewer": {"list", "details"},
    "editor": {"list", "details", "create", "edit"},
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

`action` is one of `list`, `details`, `create`, `edit`, `delete`, `export`,
`import`, or `action:<slug>` for an endpoint declared with `@action`:

```python
class UserAdmin(ModelView, model=User):
    @action(name="deactivate", label="Deactivate")
    async def deactivate(self, request):
        ...
```

is asked about as `("user", "action:deactivate")`. Buttons for actions the user
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

### Grants and wildcards

For the common case of a set of `(identity, action)` pairs, subclass
`GrantsAuthorizationBackend` instead. It caches the grants on the request and
matches them, with `*` allowed on either side of the pair:

```python
from sqladmin.authorization import GrantsAuthorizationBackend


class SessionAuthorization(GrantsAuthorizationBackend):
    async def get_grants(self, request) -> set[tuple[str, str]]:
        return {("user", "list"), ("movie", "*")}

    async def is_superuser(self, request) -> bool:
        return request.session.get("is_admin", False)
```

| Grant | Allows |
| --- | --- |
| `("user", "edit")` | editing on the `user` view |
| `("user", "*")` | every action on the `user` view |
| `("*", "edit")` | editing on every view |
| `("*", "*")` | everything |

A `GrantsAuthorizationBackend` whose `load` never ran denies everything rather
than falling open.

### Third-party engines

An external policy engine is an adapter of the same two methods:

```python
class CasbinAuthorization(AuthorizationBackend):
    def __init__(self, enforcer):
        self.enforcer = enforcer

    def has_permission(self, request, identity, action, obj=None) -> bool:
        return self.enforcer.enforce(request.session["user"], identity, action)
```

### Precedence

The backend is one of three layers, and the most restrictive wins:

1. The `can_*` class variables are a hard ceiling. `can_delete = False` means
   nobody deletes, whatever any grant says.
2. Your own `is_accessible` / `check_can_*` overrides on a view. An override
   replaces the default behaviour entirely, so it can be stricter *or* more
   permissive than the backend.
3. The authorization backend.

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
anywhere in the request as `sqladmin.authentication.get_current_user_id(request)`.

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

One query per request loads the user, their groups and the groups' grants.
`is_superuser` on the user model bypasses grant checks entirely; a user model
without that attribute simply has no superusers. Pass `groups_attr`,
`accesses_attr` or `superuser_attr` if your attributes are named differently.

Because the grants are read on every request, changing a group in the database
takes effect on the user's next page load -- no restart, no re-login.

### The permission screen

```python
from sqladmin.contrib.rbac import GroupAdmin


class MyGroupAdmin(GroupAdmin, model=Group):
    access_model = GroupAccess


admin.add_view(MyGroupAdmin)
```

The group form renders a permission matrix instead of a raw list of grant rows:
one row per registered view, one checkbox per action, so an operator ticks
*Users · create* rather than typing `user:create`.

Rows are derived from the views registered on the `Admin` at startup, so adding
a new `ModelView` makes its row appear on the next restart -- there is no
permission table to migrate and no sync step to run. Actions a view has disabled
with `can_*` are not offered, since a grant the class flag overrules is only
confusing. Custom pages (`BaseView`) get a single *access* checkbox.

Submitted values are validated against the rendered choices, so a forged
permission string fails validation rather than being stored.

Restrict the screen itself the ordinary way:

```python
class MyGroupAdmin(GroupAdmin, model=Group):
    access_model = GroupAccess

    def is_accessible(self, request) -> bool:
        return request.session.get("is_superuser", False)
```
