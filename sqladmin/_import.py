from __future__ import annotations

import json
import logging
from typing import Any, AsyncGenerator, Callable, List, NamedTuple, Tuple, Type

import anyio
from sqlalchemy import func as sa_func
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from starlette.datastructures import MultiDict, UploadFile
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from wtforms import Form

from sqladmin._queries import Query
from sqladmin.helpers import (
    build_import_form_row,
    coerce_column_value,
    merge_import_row_data,
    parse_csv,
)
from sqladmin.models import ModelView

logger = logging.getLogger(__name__)


class ImportUploadResult(NamedTuple):
    content: bytes | None
    continue_on_error: bool
    error: str | None = None
    status_code: int = 400


def import_error_response(message: str, status_code: int = 400) -> Response:
    return Response(
        content=message,
        status_code=status_code,
        media_type="text/plain; charset=utf-8",
    )


async def handle_import_upload(
    request: Request,
    model_view: ModelView,
) -> ImportUploadResult:
    async with request.form(max_files=1) as form:
        continue_on_error = str(form.get("continue_on_error", "")).lower() in {
            "1",
            "true",
            "on",
            "yes",
        }
        csv_file = form.get("csvfile")

        if not isinstance(csv_file, UploadFile):
            return ImportUploadResult(
                None,
                continue_on_error,
                "Invalid file upload. Expected a CSV file.",
            )

        if (
            not csv_file
            or not csv_file.filename
            or not csv_file.filename.lower().endswith(".csv")
        ):
            return ImportUploadResult(None, continue_on_error)

        allowed_content_types = {
            None,
            "",
            "text/csv",
            "application/csv",
            "text/plain",
            "application/vnd.ms-excel",
        }
        if csv_file.content_type not in allowed_content_types:
            return ImportUploadResult(
                None,
                continue_on_error,
                "Invalid CSV file type.",
            )

        csv_content = await csv_file.read()
        if len(csv_content) > model_view.max_import_file_size:
            return ImportUploadResult(
                None,
                continue_on_error,
                "CSV file is too large.",
                413,
            )
    return ImportUploadResult(csv_content, continue_on_error)


def validate_import_row(
    row: MultiDict,
    import_columns: list[str],
    model: Any,
    form_class: Type[Form],
    denormalize_wtform_data: Callable[[dict, Any], dict],
) -> tuple[dict[str, Any], dict[str, list[str]], dict[str, Any]]:
    """Coerce CSV values, then run WTForms validation on coerced form input."""
    row_data = {col: row.get(col) for col in import_columns}

    fallback_form = form_class(row)
    fallback_data = denormalize_wtform_data(fallback_form.data, model)

    merged_import_data, row_errors = merge_import_row_data(
        model,
        import_columns,
        row_data,
        fallback_data,
    )

    validation_form = form_class(
        build_import_form_row(row, merged_import_data, import_columns)
    )
    if not validation_form.validate():
        for field_name, field_errors in validation_form.errors.items():
            row_errors.setdefault(field_name, []).extend(field_errors)

    return merged_import_data, row_errors, row_data


async def validate_foreign_key_values(
    model_view: ModelView,
    row_data: dict[str, Any],
    fk_error_cache: dict[tuple[str, str, str], str],
) -> dict[str, list[str]]:
    mapper = sa_inspect(model_view.model)
    foreign_key_errors: dict[str, list[str]] = {}

    for column in mapper.columns:
        if not column.foreign_keys:
            continue

        value = row_data.get(column.key)
        if value in (None, ""):
            continue

        for foreign_key in column.foreign_keys:
            target_column = foreign_key.column
            cache_key = (
                column.key,
                str(value),
                foreign_key.target_fullname,
            )

            cached_error = fk_error_cache.get(cache_key)
            if cached_error is None:
                error_message = await foreign_key_error_message(
                    model_view=model_view,
                    target_column=target_column,
                    value=value,
                    column_key=column.key,
                    target_fullname=foreign_key.target_fullname,
                )
                fk_error_cache[cache_key] = error_message or ""
                cached_error = fk_error_cache[cache_key]

            if cached_error:
                foreign_key_errors.setdefault(column.key, []).append(cached_error)

    return foreign_key_errors


async def foreign_key_error_message(
    model_view: ModelView,
    target_column: Any,
    value: Any,
    column_key: str,
    target_fullname: str,
) -> str | None:
    try:
        coerced_value = coerce_column_value(target_column, value)
    except (TypeError, ValueError):
        return f"Invalid value {value!r} for column {column_key}."

    stmt = (
        select(sa_func.count())
        .select_from(target_column.table)
        .where(target_column == coerced_value)
    )

    if model_view.is_async:
        async with model_view.session_maker(expire_on_commit=False) as session:
            count = int(await session.scalar(stmt) or 0)
    else:

        def run_sync() -> int:
            with model_view.session_maker(expire_on_commit=False) as session:
                return int(session.execute(stmt).scalar_one() or 0)

        count = await anyio.to_thread.run_sync(run_sync)

    if count > 0:
        return None

    return f"Referenced value does not exist for {target_fullname}."


async def persist_import_row_async(
    query: Query,
    session: AsyncSession,
    model_view: ModelView,
    request: Request,
    row_entry: dict[str, Any],
) -> Any:
    row = row_entry["model"]
    async with session.begin_nested():
        obj = query._get_model_object(row)
        await model_view.on_import_row(row, obj, request)
        obj = await query._set_attributes_async(session, obj, row)
        session.add(obj)
        await session.flush()
    return obj


def persist_import_row_sync(
    query: Query,
    session: Session,
    model_view: ModelView,
    request: Request,
    row_entry: dict[str, Any],
) -> Any:
    row = row_entry["model"]
    with session.begin_nested():
        obj = query._get_model_object(row)
        anyio.from_thread.run(model_view.on_import_row, row, obj, request)
        obj = query._set_attributes_sync(session, obj, row)
        session.add(obj)
        session.flush()
    return obj


async def persist_import_models_with_count_check(
    model_view: ModelView,
    request: Request,
    import_models: List[dict[str, Any]],
    continue_on_error: bool,
) -> Tuple[bool, int, str | None, List[dict[str, Any]]]:
    if model_view.is_async:
        return await persist_import_models_with_count_check_async(
            model_view,
            request,
            import_models,
            continue_on_error,
        )

    return await anyio.to_thread.run_sync(
        persist_import_models_with_count_check_sync,
        model_view,
        request,
        import_models,
        continue_on_error,
    )


async def persist_import_models_with_count_check_async(
    model_view: ModelView,
    request: Request,
    import_models: List[dict[str, Any]],
    continue_on_error: bool,
) -> Tuple[bool, int, str | None, List[dict[str, Any]]]:
    query = Query(model_view)
    failed_rows: List[dict[str, Any]] = []
    session: AsyncSession
    try:
        async with model_view.session_maker(expire_on_commit=False) as session:
            persisted_count = 0

            for row_entry in import_models:
                line_number = int(row_entry["line"])
                source_data = row_entry["data"]

                if await request.is_disconnected():
                    await session.rollback()
                    return False, 0, "Import canceled. No rows were imported.", []

                try:
                    await persist_import_row_async(
                        query,
                        session,
                        model_view,
                        request,
                        row_entry,
                    )
                    persisted_count += 1
                except Exception as exc:
                    failed_rows.append(
                        {
                            "line": line_number,
                            "data": source_data,
                            "errors": {"__all__": [str(exc)]},
                        }
                    )
                    if not continue_on_error:
                        await session.rollback()
                        return (
                            False,
                            0,
                            (
                                "Import aborted on invalid row "
                                f"{line_number}. No rows were imported."
                            ),
                            failed_rows,
                        )

            await session.commit()

            return True, persisted_count, None, failed_rows
    except Exception as exc:
        logger.exception(exc)
        return (
            False,
            0,
            (
                "Import failed during database commit. "
                "No rows were imported (rolled back)."
            ),
            failed_rows,
        )


def persist_import_models_with_count_check_sync(
    model_view: ModelView,
    request: Request,
    import_models: List[dict[str, Any]],
    continue_on_error: bool,
) -> Tuple[bool, int, str | None, List[dict[str, Any]]]:
    query = Query(model_view)
    failed_rows: List[dict[str, Any]] = []
    session: Session
    try:
        with model_view.session_maker(expire_on_commit=False) as session:
            persisted_count = 0

            for row_entry in import_models:
                line_number = int(row_entry["line"])
                source_data = row_entry["data"]

                if anyio.from_thread.run(request.is_disconnected):
                    session.rollback()
                    return False, 0, "Import canceled. No rows were imported.", []

                try:
                    persist_import_row_sync(
                        query,
                        session,
                        model_view,
                        request,
                        row_entry,
                    )
                    persisted_count += 1
                except Exception as exc:
                    failed_rows.append(
                        {
                            "line": line_number,
                            "data": source_data,
                            "errors": {"__all__": [str(exc)]},
                        }
                    )
                    if not continue_on_error:
                        session.rollback()
                        return (
                            False,
                            0,
                            (
                                "Import aborted on invalid row "
                                f"{line_number}. No rows were imported."
                            ),
                            failed_rows,
                        )

            session.commit()

            return True, persisted_count, None, failed_rows
    except Exception as exc:
        logger.exception(exc)
        return (
            False,
            0,
            (
                "Import failed during database commit. "
                "No rows were imported (rolled back)."
            ),
            failed_rows,
        )


async def stream_import_response(
    request: Request,
    model_view: ModelView,
    data: list[MultiDict],
    form_class: Type[Form],
    continue_on_error: bool,
    denormalize_wtform_data: Callable[[dict, Any], dict],
) -> StreamingResponse:
    async def import_events() -> AsyncGenerator[bytes, None]:
        total = len(data)
        processed = 0
        validated = 0
        skipped = 0
        import_models: list[dict[str, Any]] = []
        missed_rows: list[dict[str, Any]] = []
        missed_rows_omitted_count = 0
        fk_error_cache: dict[tuple[str, str, str], str] = {}

        def append_missed_row(row_report: dict[str, Any]) -> None:
            nonlocal missed_rows_omitted_count
            if len(missed_rows) < model_view.max_reported_missed_rows:
                missed_rows.append(row_report)
            else:
                missed_rows_omitted_count += 1

        def emit(payload: dict[str, Any]) -> bytes:
            return (json.dumps(payload, default=str) + "\n").encode("utf-8")

        yield emit(
            {
                "type": "progress",
                "phase": "validating",
                "processed": processed,
                "total": total,
                "imported": validated,
                "skipped": skipped,
            }
        )

        for line_number, row in enumerate(data, start=2):
            await anyio.sleep(0)
            if await request.is_disconnected():
                return

            processed += 1
            merged_import_data, row_errors, row_data = validate_import_row(
                row,
                model_view._import_prop_names,
                model_view.model,
                form_class,
                denormalize_wtform_data,
            )

            foreign_key_errors = await validate_foreign_key_values(
                model_view=model_view,
                row_data=merged_import_data,
                fk_error_cache=fk_error_cache,
            )
            for field_name, field_errors in foreign_key_errors.items():
                row_errors.setdefault(field_name, []).extend(field_errors)

            if row_errors:
                skipped += 1

                row_report = {
                    "line": line_number,
                    "data": row_data,
                    "errors": row_errors,
                }
                append_missed_row(row_report)

                if not continue_on_error:
                    yield emit(
                        {
                            "type": "result",
                            "ok": False,
                            "aborted": True,
                            "rolled_back": True,
                            "processed": processed,
                            "total": total,
                            "imported": 0,
                            "skipped": skipped,
                            "missed_rows": missed_rows,
                            "missed_rows_omitted_count": missed_rows_omitted_count,
                            "summary": (
                                "Import aborted on invalid row "
                                f"{line_number}. No rows were imported."
                            ),
                        }
                    )
                    return
            else:
                import_models.append(
                    {
                        "line": line_number,
                        "data": row_data,
                        "model": merged_import_data,
                    }
                )
                validated += 1

            if processed % 20 == 0 or processed == total:
                yield emit(
                    {
                        "type": "progress",
                        "phase": "validating",
                        "processed": processed,
                        "total": total,
                        "imported": validated,
                        "skipped": skipped,
                    }
                )

        if await request.is_disconnected():
            return

        yield emit(
            {
                "type": "progress",
                "phase": "persisting",
                "processed": processed,
                "total": total,
                "imported": validated,
                "skipped": skipped,
            }
        )

        if import_models:
            (
                success,
                persisted_count,
                failure_summary,
                persistence_failed_rows,
            ) = await persist_import_models_with_count_check(
                model_view,
                request,
                import_models,
                continue_on_error,
            )
        else:
            success, persisted_count, failure_summary, persistence_failed_rows = (
                True,
                0,
                None,
                [],
            )

        for failed_row in persistence_failed_rows:
            skipped += 1
            append_missed_row(failed_row)

        if not success:
            yield emit(
                {
                    "type": "result",
                    "ok": False,
                    "aborted": True,
                    "rolled_back": True,
                    "processed": processed,
                    "total": total,
                    "imported": 0,
                    "skipped": skipped,
                    "missed_rows": missed_rows,
                    "missed_rows_omitted_count": missed_rows_omitted_count,
                    "summary": failure_summary,
                }
            )
            return

        summary = (
            f"Imported {persisted_count} out of {total} row(s). "
            f"Skipped {skipped} row(s)."
        )

        yield emit(
            {
                "type": "result",
                "ok": True,
                "aborted": False,
                "processed": total,
                "total": total,
                "imported": persisted_count,
                "skipped": skipped,
                "missed_rows": missed_rows,
                "missed_rows_omitted_count": missed_rows_omitted_count,
                "summary": summary,
            }
        )

    return StreamingResponse(import_events(), media_type="application/x-ndjson")


async def import_csv(
    request: Request,
    model_view: ModelView,
    csv_content: bytes,
    continue_on_error: bool,
    denormalize_wtform_data: Callable[[dict, Any], dict],
) -> Response:
    try:
        data = parse_csv(csv_content, model_view._import_prop_names)
    except ValueError as exc:
        return import_error_response(str(exc))
    except Exception as exc:
        logger.exception(exc)
        return import_error_response("Failed to parse CSV file.")

    if model_view.import_max_rows > 0 and len(data) > model_view.import_max_rows:
        return import_error_response(
            f"CSV file exceeds the maximum of {model_view.import_max_rows} data "
            "row(s) for this model."
        )

    form_class = await model_view.scaffold_form(model_view._form_create_rules)
    return await stream_import_response(
        request,
        model_view,
        data,
        form_class,
        continue_on_error,
        denormalize_wtform_data,
    )
