# mypy: disable-error-code="override"
import base64
import json
import logging
from typing import TYPE_CHECKING, Any

from fastapi_storages import StorageFile
from markupsafe import Markup, escape
from wtforms import Field, SelectFieldBase, widgets
from wtforms.widgets import html_params

if TYPE_CHECKING:
    from sqladmin.fields import AjaxSelectField

__all__ = [
    "AjaxSelect2Widget",
    "DatePickerWidget",
    "DateTimePickerWidget",
    "Select2TagsWidget",
]

logger = logging.getLogger(__name__)


class DatePickerWidget(widgets.TextInput):
    """
    Date picker widget.
    """

    def __call__(self, field: Field, **kwargs: Any) -> str:
        kwargs.setdefault("data-role", "datepicker")
        return super().__call__(field, **kwargs)


class DateTimePickerWidget(widgets.TextInput):
    """
    Datetime picker widget.
    """

    def __call__(self, field: Field, **kwargs: Any) -> str:
        kwargs.setdefault("data-role", "datetimepicker")
        return super().__call__(field, **kwargs)


class AjaxSelect2Widget(widgets.Select):
    def __init__(self, multiple: bool = False):
        self.multiple = multiple
        self.lookup_url = ""

    async def __call__(self, field: "AjaxSelectField", **kwargs: Any) -> Markup:
        kwargs.setdefault("data-role", "select2-ajax")
        kwargs.setdefault("data-url", field.loader.model_admin.ajax_lookup_url)

        allow_blank = getattr(field, "allow_blank", False)
        if allow_blank and not self.multiple:
            kwargs.setdefault("data-allow-blank", "1")

        kwargs.setdefault("id", field.id)
        kwargs.setdefault("type", "hidden")

        if self.multiple:
            result = []
            for value in field.data:
                try:
                    result.append(field.loader.format(value))
                    continue
                except Exception:
                    logger.debug(
                        "Fallback to format_by_pk for ajax value=%r",
                        value,
                        exc_info=True,
                    )

                try:
                    result_value = await field.loader.format_by_pk(value)
                    if result_value == {}:
                        continue
                    else:
                        result.append(result_value)
                except Exception:
                    logger.debug(
                        "Unable to resolve ajax value by pk for field=%s value=%r",
                        field.name,
                        value,
                        exc_info=True,
                    )

            kwargs.setdefault("data-json", json.dumps(result))
            kwargs.setdefault("multiple", "1")

        else:
            try:
                data = field.loader.format(field.data)
            except Exception:
                logger.debug(
                    "Fallback to format_by_pk for ajax field=%s value=%r",
                    field.name,
                    field.data,
                    exc_info=True,
                )
                try:
                    data = await field.loader.format_by_pk(field.data)
                    if data == {}:
                        data = None
                except Exception:
                    logger.debug(
                        "Unable to resolve ajax single value by pk for "
                        "field=%s value=%r",
                        field.name,
                        field.data,
                        exc_info=True,
                    )
                    data = None

            if data:
                kwargs.setdefault("data-json", json.dumps([data]))

        return Markup(f"<select {html_params(name=field.name, **kwargs)}></select>")  # nosec: markupsafe_markup_xss


class Select2TagsWidget(widgets.Select):
    def __call__(self, field: SelectFieldBase, **kwargs: Any) -> str:
        kwargs.setdefault("data-role", "select2-tags")
        kwargs.setdefault("data-json", json.dumps(field.data))
        kwargs.setdefault("multiple", "multiple")
        return super().__call__(field, **kwargs)


class FileInputWidget(widgets.FileInput):
    """
    File input widget with clear checkbox.
    """

    def __call__(self, field: Field, **kwargs: Any) -> Markup:
        filename = ""
        base64_bytes = ""
        current_value = Markup("")

        if isinstance(field.data, StorageFile):
            filename = field.data.name
            current_value = Markup("Currently: {value}").format(
                value=escape(field.data.path)
            )
            base64_bytes = base64.b64encode(field.data.open().read()).decode("utf-8")

        input_html = super().__call__(field, **kwargs)

        if not field.flags.required:
            clear_button = Markup(
                "<button "
                'type="button" '
                'class="btn btn-secondary" '
                'data-field-id="#{field_id}" '
                'data-role="clear-file-input">'
                '<i class="fa-solid fa-xmark"></i>'
                "</button>"
            ).format(field_id=escape(field.id))
        else:
            clear_button = Markup()

        return Markup(
            "<div "
            'class="file-input-container" '
            'data-base64="{base64}" '
            'data-field-id="{field_id}" '
            'data-filename="{filename}" '
            ">"
            '<div class="row m-0 p-0 pb-1">{current_value}</div>'
            '<div class="row m-0 p-0">'
            '<div class="col m-0 p-0">{input_html}</div>'
            '<div class="col m-0 p-0 col-auto">{clear_button}</div>'
            "</div>"
            "</div>"
        ).format(
            base64=escape(base64_bytes),
            field_id=escape(field.id),
            filename=escape(filename),
            current_value=current_value,
            input_html=input_html,
            clear_button=clear_button,
        )


class BooleanInputWidget(widgets.CheckboxInput):
    """
    Render a checkbox.

    The ``checked`` HTML attribute is set if the field's data is a non-false value.
    """

    def __call__(self, field: Field, **kwargs: Any) -> Markup:
        if field.data:
            kwargs.setdefault("checked", True)

        template = Markup(
            '<div class="form-switch d-flex align-items-center h-100">{text}</div>'
        )

        return template.format(text=super().__call__(field, **kwargs))


class TextAreaWidget(widgets.TextArea):
    """
    Render a textarea that automatically resizes on input.
    """

    validation_attrs = ["required", "disabled", "readonly", "maxlength", "minlength"]

    def __call__(self, field: Field, **kwargs: Any) -> Markup:
        kwargs.setdefault("id", field.id)
        flags = getattr(field, "flags", {})
        for k in dir(flags):
            if k in self.validation_attrs and k not in kwargs:
                kwargs[k] = getattr(flags, k)

        class_ = kwargs.get("class")
        if getattr(field, "enable_autoresize", True) is True:
            class_ = " ".join(filter(None, (class_, "autoresize-textarea")))
            kwargs.setdefault("rows", "1")

        if class_:
            kwargs["class"] = class_

        if hasattr(field, "_value") and callable(field._value):
            kwargs["value"] = field._value()

        if getattr(field, "show_chars_count", True) is True:
            chars_count = '<div class="chars-count-label pt-1"></div>'
        else:
            chars_count = ""

        value = kwargs.pop("value", "")

        return Markup(
            f"<textarea {html_params(name=field.name, **kwargs)}>"
            f"{escape(value)}</textarea>" + chars_count
        )  # nosec: markupsafe_markup_xss
