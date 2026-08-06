from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

from starlette.responses import StreamingResponse

from sqladmin.helpers import Writer, secure_filename, stream_to_csv

if TYPE_CHECKING:
    from starlette.requests import Request

    from .models import ModelView


class PrettyExport:
    @staticmethod
    async def _base_export_cell(
        model_view: "ModelView", name: str, value: Any, formatted_value: Any
    ) -> Any:
        """
        Default formatting logic for a cell in pretty export.

        Used when `custom_export_cell` returns None.
        Applies standard rules for related fields, booleans, etc.

        Only used when `use_pretty_export = True`.
        """
        if name in model_view._relation_names:
            if isinstance(formatted_value, str):
                cell_value = formatted_value
            elif isinstance(formatted_value, (set, frozenset)):
                # Unordered collections are sorted so exports are reproducible.
                cell_value = ",".join(sorted(str(item) for item in formatted_value))
            elif isinstance(formatted_value, (list, tuple)):
                cell_value = ",".join(str(item) for item in formatted_value)
            else:
                cell_value = formatted_value
        else:
            if isinstance(value, bool):
                cell_value = "TRUE" if value else "FALSE"
            else:
                cell_value = formatted_value
        return cell_value

    @classmethod
    async def _get_export_row_values(
        cls,
        model_view: "ModelView",
        row: Any,
        column_names: list[str],
        request: "Request | None" = None,
    ) -> list[Any]:
        row_values = []
        for name in column_names:
            value, formatted_value = await model_view.get_list_value(row, name, request)
            custom_value = await model_view.custom_export_cell(row, name, value)
            if custom_value is None:
                cell_value = await cls._base_export_cell(
                    model_view, name, value, formatted_value
                )
            else:
                cell_value = custom_value
            row_values.append(cell_value)
        return row_values

    @classmethod
    async def pretty_export_csv(
        cls,
        model_view: "ModelView",
        rows: list[Any],
        request: "Request | None" = None,
    ) -> StreamingResponse:
        async def generate(writer: Writer) -> AsyncGenerator[Any, None]:
            column_names = model_view.get_export_columns()
            headers = [
                model_view._column_labels.get(name, name) for name in column_names
            ]

            yield writer.writerow(headers)

            for row in rows:
                vals = await cls._get_export_row_values(
                    model_view, row, column_names, request
                )
                yield writer.writerow(vals)

        filename = secure_filename(model_view.get_export_name(export_type="csv"))

        return StreamingResponse(
            content=stream_to_csv(generate),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment;filename={filename}"},
        )
