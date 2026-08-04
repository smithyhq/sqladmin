from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, NamedTuple

from sqlalchemy import Select, select
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from sqladmin.helpers import get_object_identifier
from sqladmin.models import ModelView

if TYPE_CHECKING:
    from sqladmin.application import BaseAdmin

__all__ = [
    "PaletteResult",
    "default_model_commands",
    "palette_base_query",
    "palette_search_query",
    "search_model_records",
    "build_palette_response",
]


class PaletteResult(NamedTuple):
    """A single command-palette hit with a fully-resolved details URL."""

    identity: str
    model_name: str
    pk: str
    label: str
    url: str

    def as_dict(self) -> dict[str, Any]:
        return self._asdict()


def palette_base_query(view: ModelView) -> Select:
    """Base statement for palette search.

    Kept separate from ``ModelView.list_query`` (which takes a ``Request`` and
    may apply per-request scoping that does not make sense for a global search).
    Relationships are intentionally *not* eager-loaded: the label is rendered
    from already-selected columns, so we avoid extra joins.
    """

    return select(view.model)


def palette_search_query(view: ModelView, term: str) -> Select:
    """Statement used for palette record search of a single model.

    Reuses ``ModelView.search_query`` — the same ``ilike`` expression as the
    list page — and caps rows at ``view.palette_search_limit``.
    """

    stmt = palette_base_query(view)
    stmt = view.search_query(stmt=stmt, term=term)
    return stmt.limit(view.palette_search_limit)


async def search_model_records(
    view: ModelView, request: Request, term: str
) -> list[PaletteResult]:
    """Run the palette search for one model and format the hits.

    One database round-trip. Works on both sync and async engines through the
    view's existing ``_run_query`` (async sessions are awaited; sync sessions
    are off-loaded to a worker thread).

    Returns ``[]`` when the model has no searchable columns or does not expose
    details pages, so callers can fan out uniformly. Rows the user may not view
    are filtered out via ``check_can_view_details``, so row-level permissions
    are honoured exactly as they are on the details route.
    """

    if not view._search_fields or not view.can_view_details:
        return []

    stmt = palette_search_query(view, term)
    rows = await view._run_query(stmt)

    allowed = await asyncio.gather(
        *(view.check_can_view_details(request, obj) for obj in rows)
    )

    return [
        PaletteResult(
            identity=view._identity_for_object(obj),
            model_name=view.name,
            pk=str(get_object_identifier(obj)),
            label=str(obj),
            url=str(view._build_url_for("admin:details", request, obj)),
        )
        for obj, can_view in zip(rows, allowed)
        if can_view
    ]


def default_model_commands(view: ModelView, request: Request) -> list[dict[str, Any]]:
    """Commands offered for a single model.

    Override ``ModelView.palette_commands`` to add, remove or reorder these.
    Each entry needs ``label`` and ``url``; ``icon`` and ``badge`` are optional
    and purely cosmetic.
    """

    commands: list[dict[str, Any]] = [
        {
            "label": "goTo",
            "name": view.name,
            "url": str(request.url_for("admin:list", identity=view.identity)),
            "icon": "\u203a",
            "badge": "page",
        }
    ]
    if view.can_create:
        commands.append(
            {
                "label": "create",
                "name": view.name,
                "url": str(request.url_for("admin:create", identity=view.identity)),
                "icon": "+",
                "badge": "new",
            }
        )
    return commands


def _model_payload(view: ModelView, request: Request) -> dict[str, Any]:
    return {
        "identity": view.identity,
        "name": view.name,
        "name_plural": view.name_plural,
        "category": view.category,
        "url": str(request.url_for("admin:list", identity=view.identity)),
        "create_url": (
            str(request.url_for("admin:create", identity=view.identity))
            if view.can_create
            else None
        ),
        "searchable": (
            view.palette_search and bool(view._search_fields) and view.can_view_details
        ),
    }


async def build_palette_response(admin: BaseAdmin, request: Request) -> Response:
    """Assemble the palette JSON response.

    Three concerns, each kept cheap:

    * **Models** are matched against the in-memory view registry and never
      touch the database.
    * **Scoped search** (``?scope=<identity>``) runs exactly one query against
      one model, regardless of how many models are registered.
    * **Unscoped search** fans out *only* across models that opted in with
      ``palette_search = True``, capped by ``palette_search_max_models`` and
      executed concurrently on async engines.

    Authorization is enforced per model via ``is_accessible`` and per row via
    ``check_can_view_details``; a hidden, inaccessible or unreadable record is
    never searched and never surfaced.
    """

    term = (request.query_params.get("q") or "").strip()
    scope = request.query_params.get("scope")

    accessible: list[ModelView] = [
        view
        for view in admin.views
        if isinstance(view, ModelView)
        and view.is_visible(request)
        and view.is_accessible(request)
    ]

    # ---- scoped: a single model was selected --------------------------------
    if scope is not None:
        model_view: ModelView | None = next(
            (v for v in accessible if v.identity == scope), None
        )
        if model_view is None:
            raise HTTPException(status_code=404)
        scoped = await search_model_records(model_view, request, term) if term else []
        return JSONResponse(
            {
                "scope": scope,
                "models": [],
                "commands": [],
                "records": [r.as_dict() for r in scoped],
            }
        )

    # ---- model matches (registry only, no DB) -------------------------------
    term_lower = term.lower()
    models = [
        _model_payload(v, request)
        for v in accessible
        if not term or term_lower in v.name.lower()
    ]

    # ---- commands for the best-matching model -------------------------------
    # Tied to what the user typed: with no term there is no "best match", so no
    # commands are offered rather than arbitrarily picking the first model.
    commands: list[dict[str, Any]] = []
    if term and models:
        best = next(v for v in accessible if v.identity == models[0]["identity"])
        commands = best.palette_commands(request)

    # ---- unscoped record fan-out (opt-in models only) -----------------------
    records: list[PaletteResult] = []
    if len(term) >= admin.palette_search_min_chars:
        searchable = [v for v in accessible if v.palette_search and v._search_fields][
            : admin.palette_search_max_models
        ]
        chunks = await asyncio.gather(
            *(search_model_records(v, request, term) for v in searchable)
        )
        for chunk in chunks:
            records.extend(chunk)

    return JSONResponse(
        {
            "scope": None,
            "models": models,
            "commands": commands,
            "records": [r.as_dict() for r in records],
        }
    )
