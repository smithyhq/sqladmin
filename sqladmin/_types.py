import sys
from collections.abc import Awaitable, Callable, Iterable
from enum import Enum
from typing import (
    Any,
    AnyStr,
    Protocol,
    TypeAlias,
    TypeVar,
    runtime_checkable,
)

from markupsafe import Markup
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlalchemy.orm import (
    ColumnProperty,
    InstrumentedAttribute,
    RelationshipProperty,
    sessionmaker,
)
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.expression import Select
from starlette.requests import Request

if sys.version_info < (3, 11):

    class StrEnum(str, Enum):  # pragma: no cover
        __str__ = str.__str__
        __repr__ = Enum.__repr__
else:
    from enum import StrEnum as StrEnum  # noqa: F401  # pragma: no cover

MODEL_PROPERTY = ColumnProperty | RelationshipProperty
ENGINE_TYPE = Engine | AsyncEngine
MODEL_ATTR = str | InstrumentedAttribute
SESSION_MAKER = sessionmaker | async_sessionmaker

# Signature of a user supplied column formatter. The first argument is the model
# *instance* being rendered, the second is the name of the attribute and the
# optional third one is the current request.
COLUMN_FORMATTER_TYPE: TypeAlias = (
    Callable[[Any, Any], Any] | Callable[[Any, Any, Request], Any]
)

T = TypeVar("T")


class _UnsetType:
    def __repr__(self) -> str:  # pragma: no cover
        return "_UNSET"


_UNSET = _UnsetType()

Unset: TypeAlias = T | _UnsetType
UnsetN: TypeAlias = T | _UnsetType | None

UnsetAny: TypeAlias = UnsetN[Any]
UnsetBool: TypeAlias = UnsetN[bool]


@runtime_checkable
class SimpleColumnFilter(Protocol):
    """Protocol for filters with simple value-based filtering"""

    title: str
    parameter_name: str
    default_value: UnsetAny = _UNSET
    template: str

    async def lookups(
        self, request: Request, model: Any, run_query: Callable[[Select], Any]
    ) -> list[tuple[str, str]]: ...  # pragma: no cover

    async def get_filtered_query(
        self, query: Select, value: Any, model: Any
    ) -> Select: ...  # pragma: no cover


@runtime_checkable
class OperationColumnFilter(Protocol):
    """Protocol for filters with operation-based filtering"""

    title: str
    parameter_name: str
    has_operator: bool
    template: str

    async def lookups(
        self, request: Request, model: Any, run_query: Callable[[Select], Any]
    ) -> list[tuple[str, str]]: ...  # pragma: no cover

    async def get_filtered_query(
        self, query: Select, operation: str, value: Any, model: Any
    ) -> Select: ...  # pragma: no cover


ColumnFilter = SimpleColumnFilter | OperationColumnFilter

BASE_FORMATTERS_TYPE: TypeAlias = dict[
    type[Any],
    Callable[[Any], Markup | Iterable[Markup] | AnyStr | Iterable[AnyStr]],
]

AJAX_WHERE_CLAUSES_TYPE: TypeAlias = (
    ColumnElement
    | Iterable[ColumnElement]
    | Callable[[Request, str], ColumnElement]
    | Callable[[Request, str], Awaitable[ColumnElement]]
    | Callable[[Request, str], Iterable[ColumnElement]]
    | Callable[[Request, str], Awaitable[Iterable[ColumnElement]]]
)
