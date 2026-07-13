from __future__ import annotations

import csv
import enum
import inspect
import json
import os
import re
import unicodedata
from abc import ABC, abstractmethod
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import (
    Any,
    AsyncGenerator,
    Callable,
    Generator,
    Sequence,
    TypeVar,
    get_args,
    get_origin,
)

from sqlalchemy import Column
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import RelationshipProperty
from starlette.datastructures import MultiDict

from sqladmin._types import MODEL_PROPERTY, SESSION_MAKER

T = TypeVar("T")

_filename_ascii_strip_re = re.compile(r"[^A-Za-z0-9_.-]")
_windows_device_files = (
    "CON",
    "AUX",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "LPT1",
    "LPT2",
    "LPT3",
    "PRN",
    "NUL",
)

standard_duration_re = re.compile(
    r"^"
    r"(?:(?P<days>-?\d+) (days?, )?)?"
    r"(?P<sign>-?)"
    r"((?:(?P<hours>\d+):)(?=\d+:\d+))?"
    r"(?:(?P<minutes>\d+):)?"
    r"(?P<seconds>\d+)"
    r"(?:[\.,](?P<microseconds>\d{1,6})\d{0,6})?"
    r"$"
)

# Support the sections of ISO 8601 date representation that are accepted by timedelta
iso8601_duration_re = re.compile(
    r"^(?P<sign>[-+]?)"
    r"P"
    r"(?:(?P<days>\d+([\.,]\d+)?)D)?"
    r"(?:T"
    r"(?:(?P<hours>\d+([\.,]\d+)?)H)?"
    r"(?:(?P<minutes>\d+([\.,]\d+)?)M)?"
    r"(?:(?P<seconds>\d+([\.,]\d+)?)S)?"
    r")?"
    r"$"
)

# Support PostgreSQL's day-time interval format, e.g. "3 days 04:05:06". The
# year-month and mixed intervals cannot be converted to a timedelta and thus
# aren't accepted.
postgres_interval_re = re.compile(
    r"^"
    r"(?:(?P<days>-?\d+) (days? ?))?"
    r"(?:(?P<sign>[-+])?"
    r"(?P<hours>\d+):"
    r"(?P<minutes>\d\d):"
    r"(?P<seconds>\d\d)"
    r"(?:\.(?P<microseconds>\d{1,6}))?"
    r")?$"
)


def prettify_class_name(name: str) -> str:
    return re.sub(r"(?<=.)([A-Z])", r" \1", name)


def slugify_class_name(name: str) -> str:
    dashed = re.sub("(.)([A-Z][a-z]+)", r"\1-\2", name)
    return re.sub("([a-z0-9])([A-Z])", r"\1-\2", dashed).lower()


def slugify_action_name(name: str) -> str:
    if not re.search(r"^[A-Za-z0-9 \-_]+$", name):
        raise ValueError(
            "name must be non-empty and contain only allowed characters"
            " - use `label` for more expressive names"
        )

    return re.sub(r"[_ ]", "-", name).lower()


def secure_filename(filename: str) -> str:
    """Ported from Werkzeug.

    Pass it a filename and it will return a secure version of it. This
    filename can then safely be stored on a regular file system and passed
    to :func:`os.path.join`. The filename returned is an ASCII only string
    for maximum portability.
    On windows systems the function also makes sure that the file is not
    named after one of the special device files.
    """
    filename = unicodedata.normalize("NFKD", filename)
    filename = filename.encode("ascii", "ignore").decode("ascii")

    for sep in os.path.sep, os.path.altsep:
        if sep:
            filename = filename.replace(sep, " ")
    filename = str(_filename_ascii_strip_re.sub("", "_".join(filename.split()))).strip(
        "._"
    )

    # on nt a couple of special files are present in each folder.  We
    # have to ensure that the target file is not such a filename.  In
    # this case we prepend an underline
    if (
        os.name == "nt"
        and filename
        and filename.split(
            ".",
            maxsplit=1,
        )[0].upper()
        in _windows_device_files
    ):
        filename = f"_{filename}"  # pragma: no cover

    return filename


def is_http_url(value: Any) -> bool:
    """Return True if value is an http(s) URL."""
    return isinstance(value, str) and value.startswith(("http://", "https://"))


def value_is_filepath(value: Any) -> bool:
    """Check if a value is a filepath."""
    return isinstance(value, str) and os.path.isfile(value)


def resolve_storage_path(value: Any) -> str | None:
    """Return filesystem path for a stored file value."""
    if value is None:
        return None
    if hasattr(value, "path"):
        return str(value.path)
    if isinstance(value, str):
        return value
    return str(value)


def get_column_storage_roots(column: Column) -> list[Path]:
    """Return allowed filesystem roots for a SQLAlchemy file column."""
    roots: list[Path] = []
    col_type = column.type
    storage = getattr(col_type, "storage", None)
    if storage is not None:
        storage_path = getattr(storage, "_path", None)
        if storage_path is not None:
            roots.append(Path(storage_path).resolve())
    return roots


def validate_servable_file_path(path: str, allowed_roots: Sequence[Path]) -> Path:
    """Resolve and validate a local file path against allowed storage roots."""
    if "\x00" in path:
        raise ValueError("Invalid path")

    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise ValueError("File not found")

    roots = list(allowed_roots) or [Path.cwd().resolve()]
    for root in roots:
        root_resolved = Path(root).expanduser().resolve()
        try:
            resolved.relative_to(root_resolved)
            return resolved
        except ValueError:
            continue

    raise ValueError("File path not allowed")


def file_display_label(value: Any) -> str:
    """Human-readable label for a file or URL value."""
    if value is None:
        return ""
    if hasattr(value, "name") and value.name:
        return str(value.name)
    if is_http_url(value):
        return value.rsplit("/", 1)[-1] or value
    if isinstance(value, str):
        return get_filename_from_path(value)
    return str(value)


def get_filename_from_path(path: str) -> str:
    """Get filename from path."""
    return os.path.basename(path)


class Writer(ABC):
    """https://docs.python.org/3/library/csv.html#writer-objects"""

    @abstractmethod
    def writerow(self, row: list[str]) -> None:
        pass  # pragma: no cover

    @abstractmethod
    def writerows(self, rows: list[list[str]]) -> None:
        pass  # pragma: no cover

    @property
    @abstractmethod
    def dialect(self) -> csv.Dialect:
        pass  # pragma: no cover


class _PseudoBuffer:
    """An object that implements just the write method of the file-like
    interface.
    """

    encoding = "utf-8"

    def write(self, value: T) -> bytes:
        return str(value).encode(self.encoding)


def stream_to_csv(
    callback: Callable[[Writer], AsyncGenerator[T, None]],
) -> Generator[T, None, None]:
    """Function that takes a callable (that yields from a CSV Writer), and
    provides it a writer that streams the output directly instead of
    storing it in a buffer. The direct output stream is intended to go
    inside a `starlette.responses.StreamingResponse`.

    Loosely adapted from here:

    https://docs.djangoproject.com/en/1.8/howto/outputting-csv/
    """
    writer = csv.writer(_PseudoBuffer())
    return callback(writer)  # type: ignore


def parse_csv(
    csv_content: bytes, columns: list[str], delimiter: str = ","
) -> list[MultiDict]:
    if csv_content[:3] == b"\xef\xbb\xbf":
        csv_content = csv_content[3:]
    try:
        _csv_content = csv_content.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError("CSV file must be UTF-8 encoded.") from exc

    reader = csv.DictReader(_csv_content, delimiter=delimiter)
    if not reader.fieldnames:
        raise ValueError("CSV file is missing a header row.")

    missing_columns = [column for column in columns if column not in reader.fieldnames]
    if missing_columns:
        raise ValueError(
            "CSV file is missing required column(s): "
            + ", ".join(missing_columns)
            + "."
        )

    result = []
    for row in reader:
        md = MultiDict()
        for column, value in row.items():
            if column not in columns:
                continue
            md.append(column, value)
        result.append(md)
    return result


def get_primary_keys(model: Any) -> tuple[Column, ...]:
    return tuple(sa_inspect(model).mapper.primary_key)


def get_object_identifier(obj: Any) -> Any:
    """Returns a value that uniquely identifies this object."""
    primary_keys = get_primary_keys(obj)
    values = [getattr(obj, pk.name) for pk in primary_keys]

    # Unaltered value for tables with a single primary key
    if len(values) == 1:
        return values[0]

    # Combine into single string for multiple primary key support
    return ";".join(str(v).replace("\\", "\\\\").replace(";", r"\;") for v in values)


def _object_identifier_parts(id_string: str, model: type) -> tuple[str, ...]:
    pks = get_primary_keys(model)
    if len(pks) == 1:
        # Only one primary key so no special processing
        return (id_string,)

    values = []
    escape_next = False
    value_start = 0
    for idx, char in enumerate(id_string):
        if escape_next:
            escape_next = False
            continue

        if char == ";":
            values.append(id_string[value_start:idx])
            value_start = idx + 1

        escape_next = char == "\\"

    # Add the last part that's not followed by semicolon
    values.append(id_string[value_start:])

    if len(values) != len(pks):
        raise ValueError(f"Malformed identifier string for model {model.__name__}.")

    # Undo escaping for ; and \
    return tuple(v.replace(r"\;", ";").replace(r"\\", "\\") for v in values)


def coerce_column_value(column: Column, value: Any) -> Any:
    """Coerce a value (typically from CSV import) to a column's Python type."""
    if not isinstance(value, str):
        return value

    type_ = get_column_python_type(column)
    if inspect.isclass(type_) and issubclass(type_, (date, datetime, time)):
        return type_.fromisoformat(value)
    if inspect.isclass(type_) and issubclass(type_, bool):
        return _coerce_bool(value)
    return type_(value)  # type: ignore[call-arg]


def _coerce_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "on", "t"}:
        return True
    if normalized in {"false", "0", "no", "off", "f", ""}:
        return False
    raise ValueError(f"Invalid boolean value {value!r}.")


def serialize_import_value_for_form(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, enum.Enum):
        return value.name
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    return str(value)


def build_import_form_row(
    row: MultiDict,
    merged: dict[str, Any],
    import_columns: list[str],
) -> MultiDict:
    form_row = MultiDict()
    for column_name in import_columns:
        if column_name in merged:
            form_row[column_name] = serialize_import_value_for_form(merged[column_name])
        else:
            form_row[column_name] = row.get(column_name) or ""
    return form_row


def merge_import_row_data(
    model: Any,
    import_columns: list[str],
    row_data: dict[str, Any],
    form_data_dict: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, list[str]]]:
    """Build import row data with CSV values coerced to column Python types."""
    mapper = sa_inspect(model)
    merged: dict[str, Any] = {}
    errors: dict[str, list[str]] = {}

    for column_name in import_columns:
        column = mapper.columns.get(column_name)
        raw_value = row_data.get(column_name)

        if column is None:
            if column_name in form_data_dict:
                merged[column_name] = form_data_dict[column_name]
            elif column_name in row_data:
                merged[column_name] = row_data[column_name]
            continue

        if raw_value in (None, ""):
            if column.nullable:
                merged[column_name] = None
            elif column_name in form_data_dict:
                merged[column_name] = form_data_dict[column_name]
            continue

        try:
            merged[column_name] = coerce_column_value(column, raw_value)
        except (TypeError, ValueError):
            errors.setdefault(column_name, []).append(
                f"Invalid value {raw_value!r} for column {column_name}."
            )

    return merged, errors


def object_identifier_values(id_string: str, model: Any) -> tuple:
    values = []
    pks = get_primary_keys(model)
    for pk, part in zip(pks, _object_identifier_parts(id_string, model)):
        values.append(coerce_column_value(pk, part))
    return tuple(values)


def get_direction(prop: MODEL_PROPERTY) -> str:
    if not isinstance(prop, RelationshipProperty):
        raise TypeError("Expected RelationshipProperty, got %s" % type(prop))

    name = prop.direction.name
    if name == "ONETOMANY" and not prop.uselist:
        return "ONETOONE"
    return name


def get_column_python_type(column: Column) -> type:
    try:
        python_type = column.type.python_type
    except NotImplementedError:
        if hasattr(column.type, "impl"):
            try:
                python_type = column.type.impl.python_type
            except NotImplementedError:
                return str
        else:
            return str

    if get_origin(python_type) is not None:
        args = get_args(python_type)
        python_type = args[0] if args else str

    return python_type


def is_relationship(prop: MODEL_PROPERTY) -> bool:
    return isinstance(prop, RelationshipProperty)


def parse_interval(value: str) -> timedelta | None:
    match = (
        standard_duration_re.match(value)
        or iso8601_duration_re.match(value)
        or postgres_interval_re.match(value)
    )

    if not match:
        return None

    kw: dict[str, Any] = match.groupdict()
    sign = -1 if kw.pop("sign", "+") == "-" else 1
    if kw.get("microseconds"):
        kw["microseconds"] = kw["microseconds"].ljust(6, "0")
    kw = {k: float(v.replace(",", ".")) for k, v in kw.items() if v is not None}
    days = timedelta(kw.pop("days", 0.0) or 0.0)
    if match.re == iso8601_duration_re:
        days *= sign
    return days + sign * timedelta(**kw)


def is_falsy_value(value: Any) -> bool:
    if value is None:
        return True

    if not value and isinstance(value, str):
        return True

    return False


def choice_type_coerce_factory(type_: Any) -> Callable[[Any], Any]:
    from sqlalchemy_utils import Choice

    choices = type_.choices
    if isinstance(choices, type) and issubclass(choices, enum.Enum):
        key, choice_cls = "value", choices
    else:
        key, choice_cls = "code", Choice

    def choice_coerce(value: Any) -> Any:
        if value is None:
            return None

        return (
            getattr(value, key)
            if isinstance(value, choice_cls)
            else type_.python_type(value)
        )

    return choice_coerce


def is_async_session_maker(session_maker: SESSION_MAKER) -> bool:
    return AsyncSession in session_maker.class_.__mro__


def default_encoder(obj: Any) -> Any:
    if hasattr(obj, "isoformat"):  # datetime-like
        return obj.isoformat()
    from decimal import Decimal

    if isinstance(obj, Decimal):
        return float(obj)

    try:
        json.dumps(obj)
        return obj
    except TypeError:
        return str(obj)  # last resort


def get_str_columns(model: Any) -> list[str]:
    """Return names of String columns for a model, used for auto AJAX search."""
    from sqlalchemy import String as SAString

    mapper = sa_inspect(model).mapper
    result = []
    for prop in mapper.column_attrs:
        col = prop.columns[0]
        if isinstance(col.type, SAString):
            result.append(prop.key)
    return result
