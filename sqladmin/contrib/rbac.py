"""Group-based access control for SQLAdmin.

SQLAdmin deliberately does not ship a `User` model -- the primary key type, the
password handling and the columns differ per application, and any app that
wants an admin already has one. What it ships here is everything *around* it:
group tables you mix into your own `Base`, an
[`AuthorizationBackend`][sqladmin.authorization.AuthorizationBackend] that reads
them, and an admin view with a permission matrix so the grants can be edited
from the admin itself.

???+ usage
    ```python
    from sqladmin.contrib.rbac import (
        DBAuthorizationBackend,
        GroupAccessMixin,
        GroupAdmin,
        GroupMixin,
        user_group_table,
    )


    class Group(GroupMixin, Base):
        __tablename__ = "admin_groups"


    class GroupAccess(GroupAccessMixin, Base):
        __tablename__ = "admin_group_accesses"


    UserGroup = user_group_table(Base, user_table="users")


    class User(Base):
        __tablename__ = "users"

        id = mapped_column(Integer, primary_key=True)
        is_superuser = mapped_column(Boolean, default=False)
        groups = relationship("Group", secondary=UserGroup)


    admin = Admin(
        app,
        engine,
        authentication_backend=MyAuth(secret_key="..."),
        authorization_backend=DBAuthorizationBackend(session_maker, user_model=User),
    )


    class MyGroupAdmin(GroupAdmin, model=Group):
        pass


    admin.add_view(MyGroupAdmin)
    ```
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

import anyio
from markupsafe import Markup
from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    String,
    Table,
    UniqueConstraint,
    false,
    select,
)
from sqlalchemy import (
    inspect as sa_inspect,
)
from sqlalchemy.orm import (
    Mapped,
    declared_attr,
    mapped_column,
    relationship,
    with_parent,
)
from starlette.requests import Request
from starlette.responses import Response
from wtforms import Form, SelectMultipleField

from sqladmin.authentication import get_current_user_id
from sqladmin.authorization import (
    WILDCARD,
    Action,
    GrantsAuthorizationBackend,
    custom_action,
)
from sqladmin.exceptions import (
    ImproperlyConfigured,
    InvalidRelationshipError,
    PermissionEscalationError,
)
from sqladmin.helpers import get_primary_keys, is_async_session_maker
from sqladmin.i18n import gettext, lazy_gettext
from sqladmin.models import ModelView

if TYPE_CHECKING:
    from sqlalchemy.sql import Select

    from sqladmin.application import BaseAdmin

__all__ = [
    "DBAuthorizationBackend",
    "GroupAccessMixin",
    "GroupAdmin",
    "GroupMixin",
    "PermissionMatrixField",
    "user_group_table",
]

DEFAULT_GROUP_TABLE = "admin_groups"
DEFAULT_GROUP_MODEL = "Group"
DEFAULT_ACCESS_MODEL = "GroupAccess"


class GroupMixin:
    """Declarative mixin for the group table.

    Mix into your own `Base` and set ``__tablename__``. If you name the access
    model something other than ``GroupAccess``, set ``__access_model__`` to
    match.
    """

    __access_model__: ClassVar[str] = DEFAULT_ACCESS_MODEL

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    @declared_attr
    @classmethod
    def accesses(cls) -> Mapped[list[Any]]:
        return relationship(
            cls.__access_model__,
            back_populates="group",
            cascade="all, delete-orphan",
        )

    def __str__(self) -> str:
        return self.name


class GroupAccessMixin:
    """Declarative mixin for one ``(identity, action)`` grant on a group.

    Mix into your own `Base` and set ``__tablename__``. Set ``__group_table__``
    and ``__group_model__`` if your group table or class is not named
    ``admin_groups`` / ``Group``.
    """

    __group_table__: ClassVar[str] = DEFAULT_GROUP_TABLE
    __group_model__: ClassVar[str] = DEFAULT_GROUP_MODEL

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    identity: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)

    @declared_attr
    @classmethod
    def group_id(cls) -> Mapped[int]:
        return mapped_column(
            ForeignKey(f"{cls.__group_table__}.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )

    @declared_attr
    @classmethod
    def group(cls) -> Mapped[Any]:
        return relationship(cls.__group_model__, back_populates="accesses")

    @declared_attr.directive
    @classmethod
    def __table_args__(cls) -> tuple:
        return (UniqueConstraint("group_id", "identity", "action"),)

    def __str__(self) -> str:
        return f"{self.identity}:{self.action}"


def user_group_table(
    base: Any,
    user_table: str,
    *,
    user_pk_column: str = "id",
    user_pk_type: Any = Integer,
    group_table: str = DEFAULT_GROUP_TABLE,
    table_name: str = "admin_user_groups",
) -> Table:
    """Build the user-to-group association table.

    This is a factory rather than a mixin because it needs your user table's
    name and primary key type, which SQLAdmin cannot know.

    Args:
        base: Your declarative base (its ``metadata`` is used).
        user_table: Name of your users table, e.g. ``"users"``.
        user_pk_column: Primary key column on that table.
        user_pk_type: SQLAlchemy type of that column -- ``Integer``,
            ``String(36)``, ``Uuid()``, etc.
        group_table: Name of the group table.
        table_name: Name for the association table itself.
    """

    return Table(
        table_name,
        base.metadata,
        Column(
            "user_id",
            user_pk_type,
            ForeignKey(f"{user_table}.{user_pk_column}", ondelete="CASCADE"),
            primary_key=True,
        ),
        Column(
            "group_id",
            Integer,
            ForeignKey(f"{group_table}.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )


class DBAuthorizationBackend(GrantsAuthorizationBackend):
    """Resolve a user's grants from the group tables, once per request.

    Args:
        session_maker: A sync or async sessionmaker.
        user_model: Your user model. Required, keyword-only.
        groups_attr: Relationship on the user model pointing at groups.
        accesses_attr: Relationship on the group model pointing at grants.
        superuser_attr: Boolean attribute on the user model that bypasses all
            grant checks. Missing attributes are treated as `False`, so a user
            model without one simply has no superusers.

    ???+ usage
        ```python
        backend = DBAuthorizationBackend(session_maker, user_model=User)
        admin = Admin(app, engine, authorization_backend=backend)
        ```

    The user id comes from
    [`AuthenticationBackend.get_user_id`][sqladmin.authentication.AuthenticationBackend.get_user_id].
    Superusers are granted ``("*", "*")``. Without an
    ``Admin(authentication_backend=...)`` there is no user id to look up, so
    creating the `Admin` fails with
    [`ImproperlyConfigured`][sqladmin.exceptions.ImproperlyConfigured].
    """

    def __init__(
        self,
        session_maker: Any,
        *,
        user_model: Any,
        groups_attr: str = "groups",
        accesses_attr: str = "accesses",
        superuser_attr: str = "is_superuser",
    ) -> None:
        self.session_maker = session_maker
        self.is_async = is_async_session_maker(session_maker)

        pks = get_primary_keys(user_model)
        if len(pks) != 1:
            raise ImproperlyConfigured(
                f"{type(self).__name__} needs {user_model.__name__} to have a "
                "single-column primary key."
            )

        mapper = sa_inspect(user_model).mapper
        group_model = _related_model(
            user_model,
            groups_attr,
            "Pass groups_attr= with its relationship to the group model.",
        )
        access_model = _related_model(
            group_model,
            accesses_attr,
            "Pass accesses_attr= with its relationship to the grant model.",
        )

        # A missing superuser column means there are no superusers.
        superuser = (
            getattr(user_model, superuser_attr)
            if superuser_attr in mapper.column_attrs
            else false()
        )

        # One round trip: the superuser flag plus every grant of every group,
        # each once even when several groups hold it. A user without groups
        # yields one row of NULL grants; an unknown user yields no rows.
        self._grants_query = (
            select(superuser, access_model.identity, access_model.action)
            .select_from(user_model)
            .outerjoin(getattr(user_model, groups_attr))
            .outerjoin(getattr(group_model, accesses_attr))
            .distinct()
        )
        self._user_pk = pks[0]

    def _query_for(self, user_id: Any) -> Select:
        return self._grants_query.where(self._user_pk == user_id)

    @staticmethod
    def _grants_from_rows(rows: Any) -> set[tuple[str, str]]:
        grants = set()
        for is_superuser, identity, action in rows:
            if is_superuser:
                return {(WILDCARD, WILDCARD)}
            if identity is not None:
                grants.add((identity, action))
        return grants

    def _load_grants_sync(self, user_id: Any) -> set[tuple[str, str]]:
        with self.session_maker() as session:
            return self._grants_from_rows(session.execute(self._query_for(user_id)))

    def setup(self, admin: BaseAdmin) -> None:
        if admin.authentication_backend is None:
            raise ImproperlyConfigured(
                f"{type(self).__name__} looks users up by the id from the "
                "authentication backend, but none is configured. Pass "
                "authentication_backend= to Admin."
            )

    async def get_grants(self, request: Request) -> set[tuple[str, str]]:
        user_id = get_current_user_id(request)
        if user_id is None:
            return set()
        if not self.is_async:
            return await anyio.to_thread.run_sync(self._load_grants_sync, user_id)
        async with self.session_maker() as session:
            result = await session.execute(self._query_for(user_id))
            return self._grants_from_rows(result)


def _related_model(model: Any, attr: str, hint: str) -> Any:
    """Return the class ``model.<attr>`` points at, or fail with a clear error."""

    relationships = sa_inspect(model).mapper.relationships
    if attr not in relationships:
        raise InvalidRelationshipError(
            f"{model.__name__} has no relationship named {attr!r}. {hint}"
        )
    return relationships[attr].mapper.class_


@dataclass
class _ActionChoice:
    value: str
    label: str


@dataclass
class _ViewRow:
    identity: str
    label: str
    choices: list[_ActionChoice] = field(default_factory=list)


_ACTION_LABELS: dict[str, str] = {
    Action.LIST: lazy_gettext("List"),
    Action.DETAILS: lazy_gettext("Details"),
    Action.CREATE: lazy_gettext("Create"),
    Action.EDIT: lazy_gettext("Edit"),
    Action.DELETE: lazy_gettext("Delete"),
    Action.EXPORT: lazy_gettext("Export"),
    Action.IMPORT: lazy_gettext("Import"),
}

_ROWS_CACHE_ATTR = "_sqladmin_rbac_permission_rows"


def build_permission_rows(admin: BaseAdmin) -> list[_ViewRow]:
    """Build the permission matrix from the views registered on ``admin``.

    Rows come from what is registered, so a newly added `ModelView` shows up
    on the next restart with no migration and no permission-sync step. Views
    are only ever added, so the result is cached until the next one is.
    """

    cached = getattr(admin, _ROWS_CACHE_ATTR, None)
    if cached is not None and cached[0] == len(admin.views):
        return cached[1]

    rows = []
    for view in admin.views:
        identity = view.identity
        if not identity:
            continue

        # One checkbox per action the view is asked about, so the matrix
        # offers exactly what can open it. Actions switched off with a
        # ``can_*`` flag are left out: such a grant would do nothing.
        if isinstance(view, ModelView):
            row = _ViewRow(identity, view.name_plural or view.name or identity)
            labels = {
                **_ACTION_LABELS,
                **{
                    custom_action(slug): action_label or slug
                    for slug, action_label in {
                        **view._custom_actions_in_list,
                        **view._custom_actions_in_detail,
                    }.items()
                },
            }
        else:
            # A custom page has nothing to list, so ``list`` means viewing it.
            row = _ViewRow(identity, view.name or identity)
            labels = {Action.LIST: lazy_gettext("Access")}

        for action in view._authorization_actions():
            row.choices.append(
                _ActionChoice(_grant_value(identity, action), labels[action])
            )

        rows.append(row)

    setattr(admin, _ROWS_CACHE_ATTR, (len(admin.views), rows))
    return rows


# Every fragment below is a ``Markup`` built from a string *literal*, and every
# value is interpolated through ``Markup.format``, which escapes it. Nothing
# untrusted is ever passed to ``Markup()`` itself, so the markup is safe by
# construction rather than by a suppression comment.
_TABLE_OPEN = Markup(
    '<div class="table-responsive">'
    '<table class="table table-sm table-vcenter permission-matrix">'
)
_TABLE_CLOSE = Markup("</tbody></table></div>")
_HEAD = Markup("<thead><tr><th>{view}</th><th>{permission}</th></tr></thead><tbody>")
_ROW_OPEN = Markup(
    '<tr><td class="w-25"><strong>{label}</strong>'
    '<div class="text-muted small">{identity}</div></td><td>'
)
_ROW_CLOSE = Markup("</td></tr>")
_CHECKBOX = Markup(
    '<label class="form-check form-check-inline">'
    '<input type="checkbox" class="form-check-input me-1" '
    'name="{name}" value="{value}" id="{id}"{checked}>'
    '<span class="form-check-label">{label}</span>'
    "</label>"
)
_CHECKED = Markup(" checked")
_EMPTY = Markup("")


class PermissionMatrixWidget:
    """Render a `PermissionMatrixField` as a table of checkboxes."""

    def __call__(self, field: PermissionMatrixField, **kwargs: Any) -> Markup:
        selected = set(field.data or [])
        html = [
            _TABLE_OPEN,
            _HEAD.format(
                view=lazy_gettext("Page"), permission=lazy_gettext("Permissions")
            ),
        ]

        for row in field.rows:
            html.append(_ROW_OPEN.format(label=row.label, identity=row.identity))
            for choice in row.choices:
                html.append(
                    _CHECKBOX.format(
                        name=field.name,
                        value=choice.value,
                        id=f"{field.id}-{choice.value}",
                        checked=_CHECKED if choice.value in selected else _EMPTY,
                        label=choice.label,
                    )
                )
            html.append(_ROW_CLOSE)

        html.append(_TABLE_CLOSE)
        return _EMPTY.join(html)


class PermissionMatrixField(SelectMultipleField):
    """A grid of ``(view, action)`` checkboxes.

    Values are ``"<identity>:<action>"``. Because it is a `SelectMultipleField`
    underneath, WTForms rejects any submitted value that is not one of the
    rendered choices -- a forged permission string fails validation instead of
    being stored.
    """

    widget = PermissionMatrixWidget()

    def __init__(
        self,
        label: str | None = None,
        validators: Any = None,
        rows: list[_ViewRow] | None = None,
        **kwargs: Any,
    ) -> None:
        self.rows = rows or []
        choices = [
            (choice.value, choice.label) for row in self.rows for choice in row.choices
        ]
        super().__init__(label, validators, choices=choices, **kwargs)


class GroupAdmin(ModelView):
    """Admin view for editing a group and its permissions.

    Subclass it with your group model::

        class MyGroupAdmin(GroupAdmin, model=Group):
            pass

    The permission matrix replaces the raw list of grant rows: one row per
    registered view, one checkbox per action.

    Saving only touches the grants the matrix offers. Anything else stored on
    the group -- wildcard grants such as ``("*", "*")``, or grants for an action
    a view has since disabled -- is left alone.

    By default an editor may only *grant* permissions they hold themselves
    (superusers hold all of them), so edit access to this view cannot be
    turned into more access than the editor already has. Ticking any other box
    fails with a form error and nothing is saved. Override
    [`can_grant`][sqladmin.contrib.rbac.GroupAdmin.can_grant] to change that
    rule. Removing grants is not restricted beyond access to this view:
    who may edit or delete groups is decided by the ``group`` permissions.

    The grants are written in the same transaction as the group, and the
    resulting grants are recorded in the audit entry under the permissions
    field. If you override `on_model_change` or `after_model_change`, call
    ``super()``.
    """

    accesses_attr: ClassVar[str] = "accesses"
    """Relationship on the group model holding its ``(identity, action)`` rows."""

    icon: ClassVar[str] = "fa-solid fa-users"

    column_list: ClassVar[Any] = ["id", "name"]
    form_columns: ClassVar[Any] = ["name"]

    def __init__(self) -> None:
        super().__init__()
        # Checked here so a misconfigured view fails when it is added.
        self._access_model = _related_model(
            self.model,
            self.accesses_attr,
            f"Set {type(self).__name__}.accesses_attr to its relationship to grants.",
        )
        # The edit form reads the grants and saving changes them, so load them
        # with the group there -- and only there.
        self._form_relations = [
            *self._form_relations,
            getattr(self.model, self.accesses_attr),
        ]

    async def scaffold_form(self, rules: list[str] | None = None) -> type[Form]:
        base_form = await super().scaffold_form(rules)
        return type(
            "GroupPermissionForm",
            (base_form,),
            {
                _PERMISSIONS_FIELD: PermissionMatrixField(
                    label=lazy_gettext("Permissions"),
                    rows=build_permission_rows(self._admin_ref),
                    validate_choice=True,
                )
            },
        )

    async def get_form_data_for_edit(self, obj: Any) -> dict[str, Any]:
        data = await super().get_form_data_for_edit(obj)
        # ``form_edit_query`` loads the grants unless an override dropped them.
        if self.accesses_attr in sa_inspect(obj).unloaded:
            relation = getattr(self.model, self.accesses_attr)
            accesses = await self._run_query(
                select(self._access_model).where(with_parent(obj, relation))
            )
        else:
            accesses = getattr(obj, self.accesses_attr)
        data[_PERMISSIONS_FIELD] = [
            _grant_value(access.identity, access.action) for access in accesses
        ]
        return data

    # Persistence ---------------------------------------------------------

    async def on_model_change(
        self, data: dict, model: Any, is_created: bool, request: Request
    ) -> None:
        await super().on_model_change(data, model, is_created, request)

        if _PERMISSIONS_FIELD not in data:
            return
        # Popped so the base class does not try to set it as a model attribute.
        # No box ticked arrives as ``None``, not ``[]``.
        submitted = data.pop(_PERMISSIONS_FIELD) or []

        offered = {
            choice.value: f"{row.label}: {choice.label}"
            for row in build_permission_rows(self._admin_ref)
            for choice in row.choices
        }
        accesses = getattr(model, self.accesses_attr)
        existing = {_grant_value(a.identity, a.action): a for a in accesses}

        desired = set(submitted) & offered.keys()
        changed = (desired ^ set(existing)) & offered.keys()

        added = changed & desired
        forbidden = sorted(
            offered[value]
            for value in added
            if not self.can_grant(request, *_parse_grant(value))
        )
        if forbidden:
            raise PermissionEscalationError(
                gettext("You are not allowed to grant: %(permissions)s")
                % {"permissions": ", ".join(forbidden)}
            )

        for value in changed - desired:
            accesses.remove(existing[value])

        for value in sorted(added):
            identity, action = _parse_grant(value)
            accesses.append(self._access_model(identity=identity, action=action))

        # The field was popped above so it is not set on the model; hand the
        # outcome to ``after_model_change`` so the audit entry includes it.
        setattr(
            request.state,
            _SAVED_PERMISSIONS_ATTR,
            sorted((set(existing) - changed) | added),
        )

    async def after_model_change(
        self, data: dict, model: Any, is_created: bool, request: Request
    ) -> Response | None:
        saved = getattr(request.state, _SAVED_PERMISSIONS_ATTR, None)
        if saved is not None:
            delattr(request.state, _SAVED_PERMISSIONS_ATTR)
            # ``data`` is the dict the audit entry is built from.
            data[_PERMISSIONS_FIELD] = saved
        return await super().after_model_change(data, model, is_created, request)

    def can_grant(self, request: Request, identity: str, action: str) -> bool:
        """Return whether the current user may give ``(identity, action)`` to a group.

        Called for every newly ticked box when a group is saved. The default
        allows only permissions the user holds themselves, so nobody can use
        this screen to gain access they do not already have.

        ???+ usage
            ```python
            class MyGroupAdmin(GroupAdmin, model=Group):
                def can_grant(self, request, identity, action):
                    # HR assigns billing access without using it themselves.
                    if identity == "billing":
                        return self.has_permission(request, "edit")
                    return super().can_grant(request, identity, action)
            ```
        """

        return self._authorization_backend().has_permission(request, identity, action)


_PERMISSIONS_FIELD = "permissions"
_SAVED_PERMISSIONS_ATTR = "sqladmin_rbac_saved_permissions"


def _grant_value(identity: str, action: str) -> str:
    return f"{identity}:{action}"


def _parse_grant(value: str) -> tuple[str, str]:
    identity, _, action = value.partition(":")
    return identity, action
