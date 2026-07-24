from __future__ import annotations

import abc
from typing import TYPE_CHECKING, Any, Iterable

from sqlalchemy import String, cast, inspect, or_, select
from sqlalchemy.orm.attributes import InstrumentedAttribute
from sqlalchemy.sql.elements import ColumnElement
from starlette.requests import Request

from sqladmin.helpers import (
    get_object_identifier,
    get_primary_keys,
    object_identifier_values,
)

if TYPE_CHECKING:
    from sqladmin.models import ModelView


DEFAULT_PAGE_SIZE = 10


class AjaxWhereClause(abc.ABC):
    @abc.abstractmethod
    async def __call__(self, request: Request, term: str) -> ColumnElement:
        """
        A function for generating conditions for the
        QueryAjaxModelLoader.get_list method.
        Example:
        ```py
        class UserAjaxWhereClause(AjaxWhereClause):
            async def __call__(self, request: Request, term: str) -> ColumnElement:
                return User.active.is_(True)

        form_ajax_refs = {
            "field_name": {
                "fields": (User.id,),
                "where": UserAjaxWhereClause()
            }
        }
        ```
        """
        ...  # pragma: no cover


class QueryAjaxModelLoader:
    def __init__(
        self,
        name: str,
        model: type,
        model_admin: "ModelView",
        **options: Any,
    ):
        self.name = name
        self.model = model
        self.model_admin = model_admin
        self.fields = options.get("fields", {})
        self.where_clause_builder: AjaxWhereClause | None = options.get("where", None)
        self.order_by = options.get("order_by", [])
        self.limit = options.get("limit", DEFAULT_PAGE_SIZE)

        pks = get_primary_keys(self.model)
        self.pk = pks[0] if len(pks) == 1 else None

        if not self.fields:
            raise ValueError(
                "AJAX loading requires `fields` to be specified for "
                f"{self.model}.{self.name}"
            )

        if self.where_clause_builder is not None and not isinstance(
            self.where_clause_builder, AjaxWhereClause
        ):
            raise ValueError(
                '"where" option should be is instance of subclass AjaxWhereClause'
            )

        self._cached_fields = self._process_fields()
        self._cached_fields_order_by = self._process_order_by_fields()

    def _process_fields(self) -> list:
        remote_fields = []

        for field in self.fields:
            if isinstance(field, str):
                attr = getattr(self.model, field, None)

                if not attr:
                    raise ValueError(f"{self.model}.{field} does not exist.")

                remote_fields.append(attr)
            else:
                remote_fields.append(field)

        return remote_fields

    def _process_order_by_fields(self) -> list[InstrumentedAttribute | ColumnElement]:
        order_by = []

        if isinstance(self.order_by, (str, InstrumentedAttribute, ColumnElement)):
            self.order_by = [self.order_by]
        elif not isinstance(self.order_by, Iterable):
            raise ValueError(
                f"The form_ajax_refs.field.order_by field accepts only str and "
                f"sqlalchemy.orm.attributes.InstrumentedAttribute "
                f"or collections of them. "
                f"Received: {self.order_by}"
            )

        for field in self.order_by:
            if isinstance(field, str):
                attr = getattr(self.model, field, None)

            elif isinstance(field, (InstrumentedAttribute, ColumnElement)):
                attr = field

            else:
                raise ValueError(
                    f"The form_ajax_refs.field.order_by field accepts only str and "
                    f"sqlalchemy.orm.attributes.InstrumentedAttribute "
                    f"or collections of them. "
                    f"Received {type(field)}: {field}"
                )

            if attr is None or not isinstance(
                attr, (InstrumentedAttribute, ColumnElement)
            ):
                raise ValueError(f"{self.model}.{field} does not exist.")

            order_by.append(attr)

        return order_by

    def format(self, model: type) -> dict[str, Any]:
        if not model:
            return {}

        return {"id": str(get_object_identifier(model)), "text": str(model)}

    async def format_by_pk(self, pk: Any) -> dict[str, Any]:
        if pk is None:
            return {}

        stmt = select(self.model)
        primary_keys = tuple(inspect(self.model).primary_key)

        try:
            values = object_identifier_values(str(pk), self.model)
        except (TypeError, ValueError):
            return {}

        if len(values) != len(primary_keys):
            return {}

        conditions = [field == value for field, value in zip(primary_keys, values)]
        stmt = stmt.where(*conditions)

        if self._cached_fields_order_by:
            stmt = stmt.order_by(*self._cached_fields_order_by)

        stmt = stmt.limit(1)

        result = await self.model_admin._run_query(stmt)
        if len(result) < 1:
            return {}

        return {"id": str(get_object_identifier(result[0])), "text": str(result[0])}

    async def get_list(self, request: Request, term: str) -> list[Any]:
        stmt = select(self.model)

        # no type casting to string if a ColumnAssociationProxyInstance is given
        filters = [
            cast(field, String).ilike("%%%s%%" % term) for field in self._cached_fields
        ]

        stmt = stmt.filter(or_(*filters))

        if self.where_clause_builder:
            where_clause = await self.where_clause_builder(request, term)
            if not isinstance(where_clause, ColumnElement):
                raise ValueError(
                    f"{self.where_clause_builder.__class__.__name__}.__call__ "
                    f"function should return value of type ColumnElement."
                )

            stmt = stmt.where(where_clause)

        if self._cached_fields_order_by:
            stmt = stmt.order_by(*self._cached_fields_order_by)

        stmt = stmt.limit(self.limit)
        result = await self.model_admin._run_query(stmt)
        return result


def create_ajax_loader(
    *,
    model_admin: "ModelView",
    name: str,
    options: dict,
) -> QueryAjaxModelLoader:
    mapper = inspect(model_admin.model)

    try:
        attr = mapper.relationships[name]
    except KeyError as exc:
        raise ValueError(f"{model_admin.model}.{name} is not a relation.") from exc

    remote_model = attr.mapper.class_
    return QueryAjaxModelLoader(name, remote_model, model_admin, **options)
