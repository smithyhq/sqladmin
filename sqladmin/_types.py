import sys
from enum import Enum
from typing import (
    Any,
    AnyStr,
    Callable,
    Dict,
    Iterable,
    List,
    Protocol,
    Tuple,
    Type,
    TypeVar,
    Union,
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
from sqlalchemy.sql.expression import Select
from starlette.requests import Request
from typing_extensions import TypeAlias

if sys.version_info < (3, 11):

    class StrEnum(str, Enum):
        __str__ = str.__str__
        __repr__ = Enum.__repr__
else:
    from enum import StrEnum as StrEnum  # noqa: F401

MODEL_PROPERTY = Union[ColumnProperty, RelationshipProperty]
ENGINE_TYPE = Union[Engine, AsyncEngine]
MODEL_ATTR = Union[str, InstrumentedAttribute]
SESSION_MAKER = Union[sessionmaker, async_sessionmaker]

T = TypeVar("T")


class _UnsetType:
    def __repr__(self) -> str:
        return "_UNSET"


_UNSET = _UnsetType()

Unset = Union[T, _UnsetType]
UnsetN = Union[T, _UnsetType, None]

UnsetAny = UnsetN[Any]
UnsetBool = UnsetN[bool]


@runtime_checkable
class SimpleColumnFilter(Protocol):
    """Protocol for filters with simple value-based filtering"""

    title: str
    parameter_name: str
    default_value: UnsetAny = _UNSET
    template: str

    async def lookups(
        self, request: Request, model: Any, run_query: Callable[[Select], Any]
    ) -> List[Tuple[str, str]]: ...  # pragma: no cover

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
    ) -> List[Tuple[str, str]]: ...  # pragma: no cover

    async def get_filtered_query(
        self, query: Select, operation: str, value: Any, model: Any
    ) -> Select: ...  # pragma: no cover


ColumnFilter = Union[SimpleColumnFilter, OperationColumnFilter]

BASE_FORMATTERS_TYPE: TypeAlias = Dict[
    Type[Any],
    Callable[[Any], Union[Markup, Iterable[Markup], AnyStr, Iterable[AnyStr]]],
]
