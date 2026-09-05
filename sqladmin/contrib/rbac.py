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
        access_model = GroupAccess


    admin.add_view(MyGroupAdmin)
    ```
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dataclass_field
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
    selectinload,
)
from starlette.requests import Request
from wtforms import Form, SelectMultipleField

from sqladmin.authentication import get_current_user_id
from sqladmin.authorization import ACTIONS, WILDCARD, GrantsAuthorizationBackend
from sqladmin.helpers import get_primary_keys, is_async_session_maker
from sqladmin.models import ModelView

if TYPE_CHECKING:
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
    def accesses(cls) -> Mapped[list[Any]]:
        return relationship(
            cls.__access_model__,
            back_populates="group",
            cascade="all, delete-orphan",
            lazy="selectin",
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
    def group_id(cls) -> Mapped[int]:
        return mapped_column(
            ForeignKey(f"{cls.__group_table__}.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )

    @declared_attr
    def group(cls) -> Mapped[Any]:
        return relationship(cls.__group_model__, back_populates="accesses")

    @declared_attr.directive
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
        user_model: Your user model. Required.
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
    [`AuthenticationBackend.get_user_id`][sqladmin.authentication.AuthenticationBackend.get_user_id];
    override [`get_user_id`][sqladmin.contrib.rbac.DBAuthorizationBackend.get_user_id]
    here to resolve it differently.
    """

    user_state_attr = "sqladmin_rbac_user"

    def __init__(
        self,
        session_maker: Any,
        *,
        user_model: Any = None,
        groups_attr: str = "groups",
        accesses_attr: str = "accesses",
        superuser_attr: str = "is_superuser",
    ) -> None:
        if user_model is None:
            raise ValueError("DBAuthorizationBackend requires a user_model.")

        self.session_maker = session_maker
        self.is_async = is_async_session_maker(session_maker)
        self.user_model = user_model
        self.groups_attr = groups_attr
        self.accesses_attr = accesses_attr
        self.superuser_attr = superuser_attr

        mapper = sa_inspect(user_model).mapper
        if groups_attr not in mapper.relationships:
            raise ValueError(
                f"{user_model.__name__} has no relationship named "
                f"{groups_attr!r}. Pass groups_attr= to name the one that "
                "points at your group model."
            )
        self.group_model = mapper.relationships[groups_attr].mapper.class_

        group_mapper = sa_inspect(self.group_model).mapper
        if accesses_attr not in group_mapper.relationships:
            raise ValueError(
                f"{self.group_model.__name__} has no relationship named "
                f"{accesses_attr!r}."
            )

    async def get_user_id(self, request: Request) -> Any:
        """Return the current user's primary key, or `None` when anonymous."""

        return get_current_user_id(request)

    def _select_user(self, user_id: Any) -> Any:
        pk = get_primary_keys(self.user_model)[0]
        return (
            select(self.user_model)
            .where(pk == user_id)
            .options(
                selectinload(getattr(self.user_model, self.groups_attr)).selectinload(
                    getattr(self.group_model, self.accesses_attr)
                )
            )
        )

    def _load_user_sync(self, user_id: Any) -> Any:
        with self.session_maker() as session:
            user = session.execute(self._select_user(user_id)).scalars().first()
            if user is None:
                return None
            # Materialise everything needed before the session closes.
            return (
                bool(getattr(user, self.superuser_attr, False)),
                self._collect_grants(user),
            )

    async def _load_user_async(self, user_id: Any) -> Any:
        async with self.session_maker() as session:
            result = await session.execute(self._select_user(user_id))
            user = result.scalars().first()
            if user is None:
                return None
            return (
                bool(getattr(user, self.superuser_attr, False)),
                self._collect_grants(user),
            )

    def _collect_grants(self, user: Any) -> set[tuple[str, str]]:
        grants = set()
        for group in getattr(user, self.groups_attr, []) or []:
            for access in getattr(group, self.accesses_attr, []) or []:
                grants.add((access.identity, access.action))
        return grants

    async def _resolve(self, request: Request) -> tuple[bool, set[tuple[str, str]]]:
        """Load superuser flag and grants, at most once per request."""

        cached = getattr(request.state, self.user_state_attr, None)
        if cached is not None:
            return cached

        user_id = await self.get_user_id(request)
        if user_id is None:
            resolved: tuple[bool, set[tuple[str, str]]] = (False, set())
        elif self.is_async:
            resolved = await self._load_user_async(user_id) or (False, set())
        else:
            resolved = await anyio.to_thread.run_sync(
                self._load_user_sync, user_id
            ) or (False, set())

        setattr(request.state, self.user_state_attr, resolved)
        return resolved

    async def is_superuser(self, request: Request) -> bool:
        superuser, _ = await self._resolve(request)
        return superuser

    async def get_grants(self, request: Request) -> set[tuple[str, str]]:
        _, grants = await self._resolve(request)
        return grants


@dataclass
class _ActionChoice:
    value: str
    label: str


@dataclass
class _ViewRow:
    identity: str
    label: str
    standard: list[_ActionChoice] = dataclass_field(default_factory=list)
    custom: list[_ActionChoice] = dataclass_field(default_factory=list)

    @property
    def choices(self) -> list[_ActionChoice]:
        return self.standard + self.custom


# ``list`` has no ``can_*`` flag; the others are only offered when the view
# allows them at all, since a grant the class flag overrules is just confusing.
_ACTION_FLAGS = {
    "details": "can_view_details",
    "create": "can_create",
    "edit": "can_edit",
    "delete": "can_delete",
    "export": "can_export",
    "import": "can_import",
}


def build_permission_rows(admin: BaseAdmin) -> list[_ViewRow]:
    """Build the permission matrix from the views registered on ``admin``.

    Rows come from what is registered at import time, so a newly added
    `ModelView` shows up on the next restart with no migration and no
    permission-sync step.
    """

    rows = []
    for view in admin.views:
        identity = getattr(view, "identity", "")
        if not identity:
            continue

        label = getattr(view, "name_plural", "") or view.name or identity
        row = _ViewRow(identity=identity, label=label)

        if getattr(view, "is_model", False):
            for action in ACTIONS:
                flag = _ACTION_FLAGS.get(action)
                if flag is not None and not getattr(view, flag, True):
                    continue
                row.standard.append(_ActionChoice(f"{identity}:{action}", action))

            custom = {
                **getattr(view, "_custom_actions_in_list", {}),
                **getattr(view, "_custom_actions_in_detail", {}),
            }
            for slug, action_label in custom.items():
                row.custom.append(
                    _ActionChoice(f"{identity}:action:{slug}", action_label or slug)
                )
        else:
            # Custom pages have no per-action semantics: one grant opens them.
            row.standard.append(_ActionChoice(f"{identity}:{WILDCARD}", "access"))

        rows.append(row)

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
            _HEAD.format(view=field.view_header, permission=field.permission_header),
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
        view_header: str = "View",
        permission_header: str = "Permissions",
        **kwargs: Any,
    ) -> None:
        self.rows = rows or []
        self.view_header = view_header
        self.permission_header = permission_header
        choices = [
            (choice.value, choice.label) for row in self.rows for choice in row.choices
        ]
        super().__init__(label, validators, choices=choices, **kwargs)


class GroupAdmin(ModelView):
    """Admin view for editing a group and its permissions.

    Subclass it with your models::

        class MyGroupAdmin(GroupAdmin, model=Group):
            access_model = GroupAccess

    The permission matrix replaces the raw list of grant rows: one row per
    registered view, one checkbox per action.
    """

    access_model: ClassVar[Any] = None
    """The model holding ``(identity, action)`` rows. Required."""

    access_group_fk: ClassVar[str] = "group_id"
    """Foreign key column on `access_model` pointing back at the group."""

    name: ClassVar[str] = "Group"
    name_plural: ClassVar[str] = "Groups"
    icon: ClassVar[str] = "fa-solid fa-users"

    column_list: ClassVar[Any] = ["id", "name"]
    form_columns: ClassVar[Any] = ["name"]

    permissions_field_name: ClassVar[str] = "permissions"

    def _require_access_model(self) -> Any:
        if self.access_model is None:
            raise ValueError(
                f"{type(self).__name__}.access_model must be set to the model "
                "holding group permissions."
            )
        return self.access_model

    async def scaffold_form(self, rules: list[str] | None = None) -> type[Form]:
        base_form = await super().scaffold_form(rules)
        rows = build_permission_rows(self._admin_ref)
        field_name = self.permissions_field_name

        return type(
            "GroupPermissionForm",
            (base_form,),
            {
                field_name: PermissionMatrixField(
                    label="Permissions",
                    rows=rows,
                    validate_choice=True,
                )
            },
        )

    async def get_form_data_for_edit(self, obj: Any) -> dict[str, Any]:
        data = await super().get_form_data_for_edit(obj)
        data[self.permissions_field_name] = await self._load_permissions(
            getattr(obj, self._group_pk_name())
        )
        return data

    def _group_pk_name(self) -> str:
        return get_primary_keys(self.model)[0].name

    # Persistence ---------------------------------------------------------

    async def insert_model(self, request: Request, data: dict) -> Any:
        data, permissions = self._split_permissions(data)
        obj = await super().insert_model(request, data)
        await self._store_permissions(getattr(obj, self._group_pk_name()), permissions)
        return obj

    async def update_model(self, request: Request, pk: str, data: dict) -> Any:
        data, permissions = self._split_permissions(data)
        obj = await super().update_model(request, pk, data)
        await self._store_permissions(getattr(obj, self._group_pk_name()), permissions)
        return obj

    def _split_permissions(self, data: dict) -> tuple[dict, list[str]]:
        data = dict(data)
        permissions = data.pop(self.permissions_field_name, None) or []
        return data, list(permissions)

    @staticmethod
    def _parse(value: str) -> tuple[str, str]:
        identity, _, action = value.partition(":")
        return identity, action

    async def _load_permissions(self, group_pk: Any) -> list[str]:
        access_model = self._require_access_model()
        stmt = select(access_model).where(
            getattr(access_model, self.access_group_fk) == group_pk
        )

        if self.is_async:
            async with self.session_maker() as session:
                result = await session.execute(stmt)
                rows = result.scalars().all()
        else:

            def _run() -> list[Any]:
                with self.session_maker() as session:
                    return list(session.execute(stmt).scalars().all())

            rows = await anyio.to_thread.run_sync(_run)

        return [f"{row.identity}:{row.action}" for row in rows]

    async def _store_permissions(self, group_pk: Any, permissions: list[str]) -> None:
        access_model = self._require_access_model()
        desired = {self._parse(value) for value in permissions}
        fk = self.access_group_fk

        def _sync(session: Any) -> None:
            existing = {
                (row.identity, row.action): row
                for row in session.execute(
                    select(access_model).where(getattr(access_model, fk) == group_pk)
                )
                .scalars()
                .all()
            }

            for key, row in existing.items():
                if key not in desired:
                    session.delete(row)

            for identity, action in desired - set(existing):
                session.add(
                    access_model(
                        **{fk: group_pk, "identity": identity, "action": action}
                    )
                )

        if self.is_async:
            async with self.session_maker() as session:
                await session.run_sync(_sync)
                await session.commit()
        else:

            def _run() -> None:
                with self.session_maker() as session:
                    _sync(session)
                    session.commit()

            await anyio.to_thread.run_sync(_run)
