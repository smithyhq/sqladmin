import datetime
import math
import re
from typing import Any, Callable, List, Optional, Tuple, Type, cast

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    inspect,
)
from sqlalchemy.orm import Mapper
from sqlalchemy.sql.expression import Select, select
from sqlalchemy.sql.sqltypes import TypeEngine, _Binary
from starlette.requests import Request

from sqladmin._types import MODEL_ATTR

# Try to import UUID type for SQLAlchemy 2.0+
try:
    import uuid

    from sqlalchemy import Uuid  # type: ignore[attr-defined]

    HAS_UUID_SUPPORT = True
except ImportError:  # pragma: no cover
    # Fallback for SQLAlchemy < 2.0
    HAS_UUID_SUPPORT = False
    Uuid = None  # type: ignore[misc, assignment]


def get_parameter_name(column: MODEL_ATTR) -> str:
    if isinstance(column, str):
        return column

    return column.key


def prettify_attribute_name(name: str) -> str:
    return re.sub(r"_([A-Za-z])", r" \1", name).title()


def get_title(column: MODEL_ATTR) -> str:
    name = get_parameter_name(column)
    return prettify_attribute_name(name)


def get_column_obj(column: MODEL_ATTR, model: Any = None) -> Any:
    if isinstance(column, str):
        if model is None:  # pragma: no cover
            raise ValueError("model is required for string column filters")
        # Handle SQLAlchemy Table objects (for association tables)
        if hasattr(model, "c"):
            return model.c[column]
        return getattr(model, column)
    return column


def get_foreign_column_name(column_obj: Any) -> str:
    fk = next(iter(column_obj.foreign_keys))
    return fk.column.name


def get_model_from_column(column: Any) -> Any:
    return column.parent.class_


def _get_filter_value(values_list: list[str], column_type: Any) -> list:
    """Convert list of string values to appropriate types based on column type."""
    if isinstance(column_type, Integer):
        return [int(item) for item in values_list]
    if isinstance(column_type, Float):
        return [float(item) for item in values_list]
    return [item for item in values_list]


class BooleanFilter:
    has_operator = False
    template = "sqladmin/filters/lookup_filter.html"

    def __init__(
        self,
        column: MODEL_ATTR,
        title: Optional[str] = None,
        parameter_name: Optional[str] = None,
    ):
        self.column = column
        self.title = title or get_title(column)
        self.parameter_name = parameter_name or get_parameter_name(column)

    async def lookups(
        self,
        request: Request,
        model: Any,
        run_query: Callable[[Select], Any],
    ) -> List[Tuple[str, str]]:
        return [
            ("all", "All"),
            ("true", "Yes"),
            ("false", "No"),
        ]

    async def get_filtered_query(self, query: Select, value: Any, model: Any) -> Select:
        column_obj = get_column_obj(self.column, model)
        if value == "true":
            return query.filter(column_obj.is_(True))

        if value == "false":
            return query.filter(column_obj.is_(False))

        return query


class AllUniqueStringValuesFilter:
    has_operator = False
    template = "sqladmin/filters/lookup_filter.html"

    def __init__(
        self,
        column: MODEL_ATTR,
        title: Optional[str] = None,
        parameter_name: Optional[str] = None,
    ):
        self.column = column
        self.title = title or get_title(column)
        self.parameter_name = parameter_name or get_parameter_name(column)

    async def lookups(
        self,
        request: Request,
        model: Any,
        run_query: Callable[[Select], Any],
    ) -> List[Tuple[str, str]]:
        column_obj = get_column_obj(self.column, model)

        return [("", "All")] + [
            (value[0], value[0])
            for value in await run_query(select(column_obj).distinct())
        ]

    async def get_filtered_query(self, query: Select, value: Any, model: Any) -> Select:
        if value == "":
            return query

        column_obj = get_column_obj(self.column, model)
        return query.filter(column_obj == value)


class StaticValuesFilter:
    has_operator = False
    template = "sqladmin/filters/lookup_filter.html"

    def __init__(
        self,
        column: MODEL_ATTR,
        values: List[Tuple[str, str]],
        title: Optional[str] = None,
        parameter_name: Optional[str] = None,
    ):
        self.column = column
        self.title = title or get_title(column)
        self.parameter_name = parameter_name or get_parameter_name(column)
        self.values = values

    async def lookups(
        self,
        request: Request,
        model: Any,
        run_query: Callable[[Select], Any],
    ) -> List[Tuple[str, str]]:
        return [("", "All")] + self.values

    async def get_filtered_query(self, query: Select, value: Any, model: Any) -> Select:
        column_obj = get_column_obj(self.column, model)
        if value == "":  # pragma: no cover
            return query
        return query.filter(column_obj == value)


class ForeignKeyFilter:
    has_operator = False
    template = "sqladmin/filters/lookup_filter.html"

    def __init__(
        self,
        foreign_key: MODEL_ATTR,
        foreign_display_field: MODEL_ATTR,
        foreign_model: Any = None,
        title: Optional[str] = None,
        parameter_name: Optional[str] = None,
        lookups_order: MODEL_ATTR | None = None,
    ):
        self.foreign_key = foreign_key
        self.foreign_display_field = foreign_display_field
        self.foreign_model = foreign_model
        self.title = title or get_title(foreign_key)
        self.parameter_name = parameter_name or get_parameter_name(foreign_key)
        self.lookups_order = lookups_order

    async def lookups(
        self,
        request: Request,
        model: Any,
        run_query: Callable[[Select], Any],
    ) -> List[Tuple[str, str]]:
        foreign_key_obj = get_column_obj(self.foreign_key, model)
        if self.foreign_model is None and isinstance(
            self.foreign_display_field, str
        ):  # pragma: no cover
            raise ValueError("foreign_model is required for string foreign key filters")
        if self.foreign_model is None:
            if isinstance(self.foreign_display_field, str):
                raise ValueError("foreign_model should not be string")

            foreign_display_field_obj = self.foreign_display_field
        else:
            foreign_display_field_obj = get_column_obj(
                self.foreign_display_field, self.foreign_model
            )
        if not self.foreign_model:
            self.foreign_model = get_model_from_column(foreign_display_field_obj)
        foreign_model_key_name = get_foreign_column_name(foreign_key_obj)
        foreign_model_key_obj = getattr(self.foreign_model, foreign_model_key_name)

        query = select(foreign_model_key_obj, foreign_display_field_obj).distinct()
        if self.lookups_order is not None:
            query = query.order_by(self.lookups_order)

        return [("", "All")] + [
            (str(key), str(value)) for key, value in await run_query(query)
        ]

    async def get_filtered_query(self, query: Select, value: Any, model: Any) -> Select:
        if value == "" or value == [""] or not value:
            return query

        foreign_key_obj = get_column_obj(self.foreign_key, model)
        column_type = foreign_key_obj.type

        # Handle both single value and list of values
        if isinstance(value, str):
            value = [value]

        filter_value = _get_filter_value(value, column_type)
        return query.filter(foreign_key_obj.in_(filter_value))


class UniqueValuesFilter:
    """Filter by unique column values with support for Integer, Float types."""

    has_operator = False

    def __init__(
        self,
        column: MODEL_ATTR,
        title: Optional[str] = None,
        parameter_name: Optional[str] = None,
        lookups_order: MODEL_ATTR | None = None,
        lookups_ui_method: Callable[..., Any] | None = None,
        float_round_method: Callable[..., Any] | None = None,
    ):
        self.column = column
        self.title = title or get_title(column)
        self.parameter_name = parameter_name or get_parameter_name(column)
        self.lookups_order = lookups_order
        self.lookups_ui_method = lookups_ui_method
        self.float_round_method = float_round_method

    def _build_float_lookups(self, lookups_objects: List[Any]) -> List[Tuple[str, Any]]:
        display_method = self.lookups_ui_method or (lambda value: round(value, 2))
        float_round_method = self.float_round_method or (
            lambda value: math.floor(value)
        )

        rounded_values = {
            float_round_method(value[0]) for value in lookups_objects if value[0]
        }
        sorted_values = sorted(list(rounded_values))
        lookups = [(str(value), display_method(value)) for value in sorted_values]
        return lookups

    async def lookups(
        self, request: Request, model: Any, run_query: Callable[[Select], Any]
    ) -> List[Tuple[Any, Any]]:
        column_obj = get_column_obj(self.column, model)
        lookups_order = self.lookups_order if self.lookups_order else column_obj

        result = await run_query(select(column_obj).order_by(lookups_order).distinct())

        if isinstance(column_obj.type, Integer):
            return [("", "All")] + [(str(value[0]), value[0]) for value in result]
        if isinstance(column_obj.type, Float):
            return [("", "All")] + self._build_float_lookups(result)

        lookups = [("", "All")] + [(value[0], value[0]) for value in result]
        return lookups

    async def get_filtered_query(self, query: Select, value: Any, model: Any) -> Select:
        if value == "" or value == [""] or not value:
            return query

        column_obj = get_column_obj(self.column, model)
        column_type = column_obj.type

        # Handle both single value and list of values
        if isinstance(value, str):
            value = [value]

        filter_value = _get_filter_value(value, column_type)

        if isinstance(column_type, Float):  # pragma: no cover
            # For float columns, use floor() to match rounded lookup values
            from sqlalchemy import func

            return query.filter(func.floor(column_obj).in_(filter_value))

        return query.filter(column_obj.in_(filter_value))


class ManyToManyFilter:
    """Filter through many-to-many relationships using a link table."""

    has_operator = False

    def __init__(
        self,
        column: MODEL_ATTR,
        link_model: Any,
        local_field: str,
        foreign_field: str,
        foreign_model: Any,
        foreign_display_field: MODEL_ATTR,
        title: str | None = None,
        parameter_name: str | None = None,
        lookups_order: MODEL_ATTR | None = None,
    ):
        self.column = column
        self.link_model = link_model
        self.local_field = local_field
        self.foreign_field = foreign_field
        self.foreign_model = foreign_model
        self.foreign_display_field = foreign_display_field
        self.title = title or get_title(foreign_display_field)
        self.parameter_name = parameter_name or get_parameter_name(
            foreign_display_field
        )
        self.lookups_order = lookups_order

    async def lookups(
        self, request: Request, model: Any, run_query: Callable[[Select], Any]
    ) -> List[Tuple[str, str]]:
        display_column = get_column_obj(self.foreign_display_field, self.foreign_model)
        model_mapper = cast(Mapper, inspect(self.foreign_model))
        foreign_pk = model_mapper.primary_key[0]

        # Handle Table objects (association tables) vs ORM models
        if hasattr(self.link_model, "c"):
            link_model_foreign_column = self.link_model.c[self.foreign_field]
        else:
            link_model_foreign_column = get_column_obj(
                self.foreign_field, self.link_model
            )

        query = (
            select(foreign_pk, display_column)
            .where(foreign_pk.in_(select(link_model_foreign_column).distinct()))
            .order_by(self.lookups_order or foreign_pk)
            .distinct()
        )
        rows = await run_query(query)
        lookups = [("", "All")] + [(str(row[0]), str(row[1])) for row in rows]
        return lookups

    async def get_filtered_query(self, query: Select, value: Any, model: Any) -> Select:
        if value == "" or value == [""] or not value:
            return query

        foreign_pk = cast(Mapper, inspect(self.foreign_model)).primary_key[0]
        model_pk = cast(Mapper, inspect(model)).primary_key[0]

        # Handle Table objects (association tables) vs ORM models
        if hasattr(self.link_model, "c"):
            link_local_col = self.link_model.c[self.local_field]
            link_foreign_col = self.link_model.c[self.foreign_field]
        else:
            link_local_col = getattr(self.link_model, self.local_field)
            link_foreign_col = getattr(self.link_model, self.foreign_field)

        # Handle both single value and list of values
        if isinstance(value, str):
            value = [value]

        filter_value = _get_filter_value(value, foreign_pk.type)
        subquery = (
            select(link_local_col).where(link_foreign_col.in_(filter_value)).subquery()
        )
        return query.where(model_pk.in_(select(subquery.c[link_local_col.name])))


class RelatedModelFilter:
    """Filter by columns in related models through JOIN."""

    has_operator = False

    def __init__(
        self,
        column: MODEL_ATTR,
        foreign_column: MODEL_ATTR,
        foreign_model: Any,
        title: Optional[str] = None,
        parameter_name: Optional[str] = None,
        lookups_order: MODEL_ATTR | None = None,
    ):
        self.column = column
        self.foreign_column = foreign_column
        self.foreign_model = foreign_model
        self.title = title or get_title(foreign_column)
        self.parameter_name = parameter_name or get_parameter_name(foreign_column)
        self.lookups_order = lookups_order

    @staticmethod
    def _safe_join(stmt: Select, target_model: Any) -> Select:
        """Safely join a model, avoiding duplicate joins."""
        for from_obj in stmt.get_final_froms():
            target_table = target_model.__tablename__
            is_table_already_joined = (
                from_obj._is_join and from_obj.right.fullname == target_table  # type: ignore[attr-defined]
            )
            if is_table_already_joined:
                return stmt
        return stmt.join(target_model)

    def _get_filter_condition(self, foreign_column: Any, value: Any) -> Any:
        column_type = foreign_column.type
        if isinstance(column_type, Boolean):
            if value == ["true"]:
                return foreign_column.is_(True)
            elif value == ["false"]:
                return foreign_column.is_(False)
            return None

        # Handle both single value and list of values
        if isinstance(value, str):
            value = [value]

        filter_value = _get_filter_value(value, column_type)
        return foreign_column.in_(filter_value)

    async def lookups(
        self, request: Request, model: Any, run_query: Callable[[Select], Any]
    ) -> List[Tuple[str, str]]:
        foreign_column_obj = get_column_obj(self.foreign_column, self.foreign_model)
        if isinstance(foreign_column_obj.type, Boolean):
            return [
                ("all", "All"),
                ("true", "Yes"),
                ("false", "No"),
            ]

        query_order = self.lookups_order if self.lookups_order else self.foreign_column
        lookup_objects = await run_query(
            select(foreign_column_obj).order_by(query_order).distinct()
        )
        return [("", "All")] + [(str(*value), str(*value)) for value in lookup_objects]

    async def get_filtered_query(self, query: Select, value: Any, model: Any) -> Select:
        if value == "" or value == "all" or value == [""] or not value:
            return query

        foreign_column = get_column_obj(self.foreign_column, self.foreign_model)
        filter_condition = self._get_filter_condition(foreign_column, value)
        if filter_condition is None:
            return query

        joined_query = self._safe_join(query, self.foreign_model)
        return joined_query.filter(filter_condition)


class DateRangeFilter:
    """Filter by date/datetime range with start and end values."""

    has_operator = False
    is_date_filter = True

    def __init__(
        self,
        column: MODEL_ATTR,
        title: Optional[str] = None,
        parameter_name: Optional[str] = None,
    ):
        self.column = column
        self.title = title or get_title(column)
        self.parameter_name = parameter_name or get_parameter_name(column)

    async def lookups(
        self, request: Request, model: Any, run_query: Callable[[Select], Any]
    ) -> List[Tuple[str, str]]:
        # Date range filters don't use lookups - they use input fields
        return []

    async def get_filtered_query(self, query: Select, value: Any, model: Any) -> Select:
        """Filter by date range. Value can be dict, list, or from request params."""
        column_obj = get_column_obj(self.column, model)

        # Handle different value formats
        start = None
        end = None

        if isinstance(value, dict):
            start = value.get("start")
            end = value.get("end")
        elif isinstance(value, list) and len(value) == 2:
            start, end = value
        elif isinstance(value, list) and len(value) == 1:
            # Single value, treat as start
            start = value[0] if value[0] else None
        else:
            return query

        # Parse date strings if needed
        if isinstance(start, str) and start:
            try:
                start = datetime.datetime.fromisoformat(start.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                start = None

        if isinstance(end, str) and end:
            try:
                end = datetime.datetime.fromisoformat(end.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                end = None

        # Apply filters
        if start and end:
            return query.filter(column_obj >= start, column_obj <= end)
        elif start:
            return query.filter(column_obj >= start)
        elif end:
            return query.filter(column_obj <= end)

        return query


class OperationColumnFilter:
    """Universal filter that provides appropriate filter types based on column type"""

    has_operator = True
    template = "sqladmin/filters/operation_filter.html"

    def __init__(
        self,
        column: MODEL_ATTR,
        title: Optional[str] = None,
        parameter_name: Optional[str] = None,
    ):
        self.column = column
        self.title = title or get_title(column)
        self.parameter_name = parameter_name or get_parameter_name(column)

    def get_operation_options(self, column_obj: Any) -> List[Tuple[str, str]]:
        """Return operation options based on column type"""
        if self._is_string_type(column_obj):
            return [
                ("contains", "Contains"),
                ("equals", "Equals"),
                ("starts_with", "Starts with"),
                ("ends_with", "Ends with"),
            ]

        if self._is_numeric_type(column_obj):
            return [
                ("equals", "Equals"),
                ("greater_than", "Greater than"),
                ("less_than", "Less than"),
            ]

        if self._is_date_type(column_obj):
            return [
                ("equals", "Equals"),
                ("greater_than", "Greater than"),
                ("less_than", "Less than"),
            ]

        if self._is_uuid_type(column_obj):
            return [
                ("equals", "Equals"),
                ("contains", "Contains"),
                ("starts_with", "Starts with"),
            ]

        return [
            ("equals", "Equals"),
        ]

    def get_operation_options_for_model(self, model: Any) -> List[Tuple[str, str]]:
        """Return operation options based on column type for given model"""
        column_obj = get_column_obj(self.column, model)
        return self.get_operation_options(column_obj)

    def _is_string_type(self, column_obj: Any) -> bool:
        return isinstance(column_obj.type, (String, Text, _Binary))

    def _is_numeric_type(self, column_obj: Any) -> bool:
        return isinstance(
            column_obj.type, (Integer, Numeric, Float, BigInteger, SmallInteger)
        )

    def _is_date_type(self, column_obj: Any) -> bool:
        return isinstance(column_obj.type, (Date, DateTime))

    def _is_uuid_type(self, column_obj: Any) -> bool:
        # Check if UUID support is available and column is UUID type
        return HAS_UUID_SUPPORT and isinstance(column_obj.type, Uuid)

    def _convert_value_for_column(
        self, value: str, column_obj: Any, operation: str = "equals"
    ) -> Any:
        if not value:
            return None

        column_type = column_obj.type

        converters: List[Tuple[Tuple[Type[TypeEngine], ...], Callable[[str], Any]]] = [
            ((String, Text, _Binary), str),
            ((Integer, BigInteger, SmallInteger), int),
            ((Numeric, Float), float),
            ((DateTime,), datetime.datetime.fromisoformat),
            ((Date,), datetime.date.fromisoformat),
        ]

        try:
            for types, converter in converters:
                if isinstance(column_type, types):
                    return converter(value)

            if HAS_UUID_SUPPORT and isinstance(column_type, Uuid):
                return (
                    str(value.strip())
                    if operation in ("contains", "starts_with")
                    else uuid.UUID(value.strip())
                )

        except (ValueError, TypeError):
            return None

        return value

    async def lookups(
        self,
        request: Request,
        model: Any,
        run_query: Callable[[Select], Any],
    ) -> List[Tuple[str, str]]:
        # This method is not used for has_operator=True filters
        # The UI uses get_operation_options_for_model instead
        return []

    async def get_filtered_query(
        self,
        query: Select,
        operation: str,
        value: Any,
        model: Any,
    ) -> Select:
        """Handle filtering with separate operation and value parameters"""
        if not value or value == "" or not operation:
            return query

        column_obj = get_column_obj(self.column, model)
        converted_value = self._convert_value_for_column(
            str(value).strip(),
            column_obj,
            operation,
        )

        if converted_value is None:
            return query

        if operation == "contains":
            if self._is_uuid_type(column_obj):
                # For UUID, cast to text for LIKE operations
                search_value = f"%{str(value).strip()}%"
                return query.filter(column_obj.cast(String).ilike(search_value))

            return query.filter(column_obj.ilike(f"%{str(value).strip()}%"))

        if operation == "equals":
            return query.filter(column_obj == converted_value)

        if operation == "starts_with":
            if self._is_uuid_type(column_obj):
                # For UUID, cast to text for LIKE operations
                search_value = f"{str(value).strip()}%"
                return query.filter(column_obj.cast(String).ilike(search_value))

            return query.filter(column_obj.startswith(str(value).strip()))

        if operation == "ends_with":
            return query.filter(column_obj.endswith(str(value).strip()))
        if operation == "greater_than":
            return query.filter(column_obj > converted_value)
        if operation == "less_than":
            return query.filter(column_obj < converted_value)

        return query
