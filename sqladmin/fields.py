# mypy: disable-error-code="override"

from __future__ import annotations

import json
import operator
from enum import Enum
from typing import Any, Callable, Generator
from uuid import UUID

import wtforms
from wtforms import Form, ValidationError, fields, widgets

from sqladmin import widgets as sqladmin_widgets
from sqladmin.ajax import QueryAjaxModelLoader
from sqladmin.helpers import (
    file_display_label,
    get_object_identifier,
    is_http_url,
    parse_interval,
    resolve_storage_path,
    value_is_filepath,
)

__all__ = [
    "AjaxSelectField",
    "AjaxSelectMultipleField",
    "CDNURLField",
    "DateField",
    "DateTimeField",
    "FileField",
    "IntervalField",
    "JSONField",
    "QuerySelectField",
    "QuerySelectMultipleField",
    "SelectField",
    "Select2TagsField",
    "file_display_formatter",
    "BooleanField",
    "FileField",
    "UuidField",
    "TextAreaField",
]


class DateField(fields.DateField):
    """
    Add custom DatePickerWidget for data-format and data-date-format fields
    """

    widget = sqladmin_widgets.DatePickerWidget()  # type: ignore[assignment]


class DateTimeField(fields.DateTimeField):
    """
    Allows modifying the datetime format of a DateTimeField using form_args.
    """

    widget = sqladmin_widgets.DateTimePickerWidget()  # type: ignore[assignment]


class IntervalField(fields.StringField):
    """
    A text field which stores a `datetime.timedelta` object.
    """

    def process_formdata(self, valuelist: list[str]) -> None:
        if not valuelist:
            return

        interval = parse_interval(valuelist[0])
        if not interval:
            raise ValueError("Invalid timedelta format.")

        self.data = interval  # type: ignore[assignment]


class SelectField(fields.SelectField):
    def __init__(
        self,
        label: str | None = None,
        validators: list | None = None,
        coerce: type = str,
        choices: list | Callable | None = None,
        allow_blank: bool = False,
        blank_text: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(label, validators, coerce, choices, **kwargs)
        self.allow_blank = allow_blank
        self.blank_text = blank_text or " "

    def iter_choices(self) -> Generator[tuple[str, str, bool, dict], None, None]:
        choices = self.choices or []

        if self.allow_blank:
            yield ("__None", self.blank_text, self.data is None, {})

        for choice in choices:
            if isinstance(choice, tuple):
                yield (choice[0], choice[1], self.coerce(choice[0]) == self.data, {})
            elif isinstance(choice, Enum):
                yield (
                    choice.value,
                    choice.name,
                    self.coerce(choice.value) == self.data,
                    {},
                )
            else:
                yield (str(choice), str(choice), self.coerce(choice) == self.data, {})

    def process_formdata(self, valuelist: list[str]) -> None:
        if valuelist:
            if valuelist[0] == "__None":
                self.data = None
            else:
                try:
                    self.data = self.coerce(valuelist[0])
                except ValueError as exc:
                    raise ValueError(
                        self.gettext("Invalid Choice: could not coerce")
                    ) from exc

    def pre_validate(self, form: Form) -> None:
        if self.allow_blank and self.data is None:
            return

        super().pre_validate(form)


class JSONField(fields.TextAreaField):
    def _value(self) -> str:
        if self.raw_data:
            return self.raw_data[0]

        if self.data:
            return str(json.dumps(self.data, ensure_ascii=False))

        return "{}"

    def process_formdata(self, valuelist: list[str]) -> None:
        if valuelist:
            value = valuelist[0]

            # allow saving blank field as None
            if not value:
                self.data = None
                return

            try:
                self.data = json.loads(valuelist[0])
            except ValueError as exc:
                raise ValueError(self.gettext("Invalid JSON")) from exc


class QuerySelectField(fields.SelectFieldBase):
    widget = widgets.Select()

    def __init__(
        self,
        data: list | None = None,
        label: str | None = None,
        validators: list | None = None,
        get_label: Callable | str | None = None,
        allow_blank: bool = False,
        blank_text: str = "",
        **kwargs: Any,
    ) -> None:
        super().__init__(label=label, validators=validators, **kwargs)

        self._select_data = data or []

        if get_label is None:
            self.get_label = lambda x: x
        elif isinstance(get_label, str):
            self.get_label = operator.attrgetter(get_label)
        else:
            self.get_label = get_label

        self.allow_blank = allow_blank
        self.blank_text = blank_text
        self._data: tuple | None
        self._formdata: str | list[str] | None

    @property
    def data(self) -> tuple | None:
        if self._formdata is not None:
            for pk, _ in self._select_data:
                if pk == self._formdata:
                    self.data = pk
                    break
        return self._data

    @data.setter
    def data(self, data: tuple | None) -> None:
        self._data = data
        self._formdata = None

    def iter_choices(self) -> Generator[tuple[str, str, bool, dict], None, None]:
        if self.allow_blank:
            yield ("__None", self.blank_text, self.data is None, {})

        if self.data:
            primary_key = (
                self.data
                if isinstance(self.data, str)
                else str(get_object_identifier(self.data))
            )
        else:
            primary_key = None

        for pk, label in self._select_data:
            yield (pk, self.get_label(label), str(pk) == primary_key, {})

    def process_formdata(self, valuelist: list[str]) -> None:
        if valuelist:
            if self.allow_blank and valuelist[0] == "__None":
                self.data = None
            else:
                self._data = None
                self._formdata = valuelist[0]

    def pre_validate(self, form: Form) -> None:
        data = self.data
        if data is not None:
            for pk, _ in self._select_data:
                if data == pk:
                    break
            else:  # pragma: no cover
                raise ValidationError(self.gettext("Not a valid choice"))
        elif self._formdata or not self.allow_blank:
            raise ValidationError(self.gettext("Not a valid choice"))


class QuerySelectMultipleField(QuerySelectField):
    """
    Very similar to QuerySelectField with the difference that this will
    display a multiple select. The data property will hold a list with ORM
    model instances and will be an empty list when no value is selected.

    If any of the items in the data list or submitted form data cannot be
    found in the query, this will result in a validation error.
    """

    widget = widgets.Select(multiple=True)

    def __init__(
        self,
        data: list | None = None,
        label: str | None = None,
        validators: list | None = None,
        default: Any = None,
        **kwargs: Any,
    ) -> None:
        default = default or []
        super().__init__(label=label, validators=validators, default=default, **kwargs)

        self._select_data = data or []

        if kwargs.get("allow_blank", False):
            import warnings

            warnings.warn(
                "allow_blank=True does not do anything for QuerySelectMultipleField."
            )
        self._invalid_formdata = False
        self._formdata: list[str] | None = None
        self._data: tuple | None = None

    @property
    def data(self) -> tuple | None:
        formdata = self._formdata
        if formdata is not None:
            data = []
            for pk, _ in self._select_data:
                if not formdata:
                    break

                if pk in formdata:
                    formdata.remove(pk)
                    data.append(pk)
            if formdata:
                self._invalid_formdata = True
            self.data = data or self._data  # type: ignore
        return self._data

    @data.setter
    def data(self, data: tuple | None) -> None:
        self._data = data
        self._formdata = None

    def iter_choices(self) -> Generator[tuple[str, Any, bool, dict], None, None]:
        if self.data is not None:
            primary_keys = (
                self.data
                if all(isinstance(d, str) for d in self.data)
                else [str(get_object_identifier(m)) for m in self.data]
            )
            for pk, label in self._select_data:
                yield (pk, self.get_label(label), pk in primary_keys, {})

    def process_formdata(self, valuelist: list[str]) -> None:
        self._formdata = list(set(valuelist))

    def pre_validate(self, form: Form) -> None:
        if self._invalid_formdata:
            raise ValidationError(self.gettext("Not a valid choice"))

        if self.data:
            pk_list = [x[0] for x in self._select_data]
            for v in self.data:
                if v not in pk_list:  # pragma: no cover
                    raise ValidationError(self.gettext("Not a valid choice"))


class AjaxSelectField(fields.SelectFieldBase):
    widget = sqladmin_widgets.AjaxSelect2Widget()  # type: ignore[assignment]
    separator = ","

    def __init__(
        self,
        loader: QueryAjaxModelLoader,
        label: str | None = None,
        validators: list | None = None,
        allow_blank: bool = False,
        **kwargs: Any,
    ) -> None:
        kwargs.pop("data", None)  # Handled by JS side
        self.loader = loader
        self.allow_blank = allow_blank
        super().__init__(label, validators, **kwargs)

    @property
    def data(self) -> Any:
        if self._formdata:
            self.data = self._formdata

        return self._data

    @data.setter
    def data(self, data: Any) -> None:
        self._data = data
        self._formdata = None

    def process_formdata(self, valuelist: list) -> None:
        if valuelist:
            if self.allow_blank and valuelist[0] == "__None":
                self.data = None
            else:
                self._data = None
                self._formdata = valuelist[0]

    def pre_validate(self, form: Form) -> None:
        if not self.allow_blank and self.data is None:
            raise ValidationError("Not a valid choice")


class AjaxSelectMultipleField(fields.SelectFieldBase):
    widget = sqladmin_widgets.AjaxSelect2Widget(multiple=True)  # type: ignore[assignment]
    separator = ","

    def __init__(
        self,
        loader: QueryAjaxModelLoader,
        label: str | None = None,
        validators: list | None = None,
        default: list | None = None,
        allow_blank: bool = False,
        **kwargs: Any,
    ) -> None:
        kwargs.pop("data", None)  # Handled by JS side
        self.loader = loader
        self.allow_blank = allow_blank
        default = default or []
        self._formdata: set[Any] = set()

        super().__init__(label, validators, default=default, **kwargs)

    @property
    def data(self) -> Any:
        if self._formdata:
            self.data = self._formdata

        return self._data

    @data.setter
    def data(self, data: Any) -> None:
        self._data = data
        self._formdata = set()

    def process_formdata(self, valuelist: list) -> None:
        self._formdata = set()

        for field in valuelist:
            for n in field.split(self.separator):
                self._formdata.add(n)


class Select2TagsField(fields.SelectField):
    widget = sqladmin_widgets.Select2TagsWidget()  # type: ignore[assignment]

    def pre_validate(self, form: Form) -> None: ...

    def process_formdata(self, valuelist: list) -> None:
        self.data = valuelist

    def process_data(self, value: list | None) -> None:
        self.data = value or []


class FileField(fields.FileField):
    """
    File upload field for local storage (e.g. fastapi-storages FileType).

    ``FileType`` / ``ImageType`` columns use this field automatically via the
    model converter. Override with ``form_overrides`` when needed.

    For list/detail links, set ``column_formatters`` / ``column_formatters_detail``
    to :func:`file_display_formatter`.
    """

    widget = sqladmin_widgets.FileInputWidget()


class CDNURLField(fields.StringField):
    """
    URL field for CDN or remote file links (https://...).

    Use via ``form_overrides`` together with :func:`file_display_formatter` in
    ``column_formatters`` for list/detail pages.
    """

    widget = widgets.TextInput()

    def __init__(
        self,
        label: str | None = None,
        validators: list | None = None,
        **kwargs: Any,
    ) -> None:
        merged_validators = list(validators or kwargs.pop("validators", None) or [])
        merged_validators.append(wtforms.validators.Optional())
        merged_validators.append(wtforms.validators.URL(require_tld=False))
        super().__init__(label, validators=merged_validators, **kwargs)


def file_display_formatter(obj: Any, prop: str, request: Any) -> Any:
    """
    Optional column formatter for file columns (local path, StorageFile, or CDN URL).

    Register on ModelView explicitly:

        form_overrides = {User.file: FileField}
        column_formatters = {User.file: file_display_formatter}
        column_formatters_detail = {User.file: file_display_formatter}
    """
    from markupsafe import Markup, escape

    value = getattr(obj, prop, None)
    if value is None or value == "":
        return ""

    label = escape(file_display_label(value))

    if is_http_url(value):
        url = escape(str(value))
        return Markup(
            '<a href="{url}" target="_blank" rel="noopener noreferrer">{label}</a>'
        ).format(url=url, label=label)

    path = resolve_storage_path(value)
    identity = request.path_params["identity"]
    pk = get_object_identifier(obj)

    if path and value_is_filepath(path):
        preview_url = request.url_for(
            "admin:file_preview",
            identity=identity,
            pk=pk,
            column_name=prop,
        )
        download_url = request.url_for(
            "admin:file_download",
            identity=identity,
            pk=pk,
            column_name=prop,
        )
        return Markup(
            '<a href="{preview_url}">{label}</a> '
            '<a href="{download_url}">'
            '<span class="me-1"><i class="fa-solid fa-download"></i></span>'
            "</a>"
        ).format(
            preview_url=preview_url,
            download_url=download_url,
            label=label,
        )

    return Markup("<span>{label}</span>").format(label=label)


class BooleanField(fields.BooleanField):
    """
    Boolean checkbox field.
    """

    widget = sqladmin_widgets.BooleanInputWidget()


class UuidField(fields.StringField):
    def process_formdata(self, valuelist: list) -> None:
        """Convert submitted string to UUID object."""
        if valuelist:
            value = valuelist[0]
            if not value:  # Empty string
                self.data = None
                return

            try:
                self.data = UUID(value)  # type: ignore[assignment]
            except (ValueError, AttributeError, TypeError) as e:
                self.data = None
                raise ValidationError(f"Invalid UUID format. {e}")
        else:
            self.data = None

    def process_data(self, value: str | UUID | None) -> None:
        """Handle initial data (from object or default)."""
        if value is None:
            self.data = None
        elif isinstance(value, UUID):
            self.data = value  # type: ignore[assignment]
        elif isinstance(value, str):
            try:
                self.data = UUID(value)  # type: ignore[assignment]
            except (ValueError, AttributeError, TypeError):
                self.data = None
        else:
            self.data = None


class TextAreaField(fields.StringField):
    """
    This field represents an HTML `textarea` and can be used to take
    multi-line input.

    To disable automatic updating of the input size,
    you need to pass enable_autoresize = False to the field arguments.
    ```python
    form_args = {
        'field_name': {
            'enable_autoresize': False
        }
    }
    ```

    To disable the display of the number of characters,
    you need to pass the value show_chars_count = False to the field arguments.

    ```python
    form_args = {
        'field_name': {
            'show_chars_count': False
        }
    }
    ```
    """

    def __init__(
        self,
        label: str | None = None,
        validators: list | None = None,
        *,
        enable_autoresize: bool = True,
        show_chars_count: bool = True,
        **kwargs: Any,
    ):
        super().__init__(label, validators, **kwargs)
        self.enable_autoresize = enable_autoresize
        self.show_chars_count = show_chars_count

    widget = sqladmin_widgets.TextAreaWidget()
