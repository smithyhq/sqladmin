from __future__ import annotations

import inspect
import io
import json
import logging
from types import MethodType
from typing import (
    Any,
    AsyncGenerator,
    Awaitable,
    Callable,
    List,
    Sequence,
    Tuple,
    cast,
    no_type_check,
)
from urllib.parse import parse_qsl, urljoin

import anyio
from jinja2 import ChoiceLoader, FileSystemLoader, PackageLoader, PrefixLoader
from sqlalchemy import func as sa_func
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session, sessionmaker
from starlette.applications import Starlette
from starlette.datastructures import URL, FormData, MultiDict, UploadFile
from starlette.exceptions import HTTPException
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import (
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from sqladmin._menu import CategoryMenu, Menu, ViewMenu
from sqladmin._queries import Query
from sqladmin._types import ENGINE_TYPE, SESSION_MAKER
from sqladmin.ajax import QueryAjaxModelLoader
from sqladmin.authentication import AuthenticationBackend, login_required
from sqladmin.editors import collect_form_media
from sqladmin.flash import get_flashed_messages
from sqladmin.forms import WTFORMS_ATTRS, WTFORMS_ATTRS_REVERSED
from sqladmin.helpers import (
    coerce_column_value,
    get_object_identifier,
    is_async_session_maker,
    parse_csv,
    slugify_action_name,
)
from sqladmin.models import BaseView, ModelView
from sqladmin.secret import Secret
from sqladmin.templating import Jinja2Templates

__all__ = [
    "Admin",
    "expose",
    "action",
]

logger = logging.getLogger(__name__)


class BaseAdmin:
    """Base class for implementing Admin interface.

    Danger:
        This class should almost never be used directly.
    """

    def __init__(
        self,
        app: Starlette,
        engine: ENGINE_TYPE | None = None,
        session_maker: SESSION_MAKER | None = None,
        base_url: str = "/admin",
        title: str = "Admin",
        logo_url: str | None = None,
        logo_width: int = 64,
        logo_height: int = 64,
        favicon_url: str | None = None,
        templates_dir: str = "templates",
        middlewares: Sequence[Middleware] | None = None,
        authentication_backend: AuthenticationBackend | None = None,
    ) -> None:
        self.app = app
        self.engine = engine
        self.base_url = base_url
        self.templates_dir = templates_dir
        self.title = title
        self.logo_url = logo_url
        self.logo_width = logo_width
        self.logo_height = logo_height
        self.favicon_url = favicon_url

        if session_maker:
            self.session_maker = session_maker
        elif isinstance(self.engine, Engine):
            self.session_maker = sessionmaker(bind=self.engine, class_=Session)
        else:
            self.session_maker = async_sessionmaker(
                bind=self.engine,
                class_=AsyncSession,
            )

        self.session_maker.configure(autoflush=False, autocommit=False)
        self.is_async = is_async_session_maker(self.session_maker)

        middlewares = list(middlewares or [])
        self.authentication_backend = authentication_backend
        if authentication_backend:
            middlewares.extend(authentication_backend.middlewares)

        self.admin = Starlette(middleware=middlewares)
        self.templates = self.init_templating_engine()
        self._views: list[BaseView | ModelView] = []
        self._menu = Menu()

    def init_templating_engine(self) -> Jinja2Templates:
        templates = Jinja2Templates("templates")
        loaders = [
            FileSystemLoader(self.templates_dir),
            PrefixLoader(
                {"sqladmin_original": PackageLoader("sqladmin", "templates/sqladmin")}
            ),
            PackageLoader("sqladmin", "templates"),
        ]

        templates.env.loader = ChoiceLoader(loaders)
        templates.env.globals["min"] = min
        templates.env.globals["zip"] = zip
        templates.env.globals["admin"] = self
        templates.env.globals["is_list"] = lambda x: isinstance(x, (list, set))
        templates.env.globals["get_object_identifier"] = get_object_identifier
        templates.env.globals["get_flashed_messages"] = get_flashed_messages
        templates.env.globals["Secret"] = Secret
        templates.env.globals["collect_form_media"] = collect_form_media

        return templates

    @property
    def views(self) -> list[BaseView | ModelView]:
        """Get list of ModelView and BaseView instances lazily.

        Returns:
            List of ModelView and BaseView instances added to Admin.
        """

        return self._views

    def _find_model_view(self, identity: str) -> ModelView:
        for view in self.views:
            if isinstance(view, ModelView) and view.identity == identity:
                return view

        raise HTTPException(status_code=404)

    def add_view(self, view: type[ModelView] | type[BaseView]) -> None:
        """Add ModelView or BaseView classes to Admin.
        This is a shortcut that will handle both `add_model_view` and `add_base_view`.
        """

        if view.is_model:
            self.add_model_view(view)  # type: ignore
        else:
            self.add_base_view(view)

    @staticmethod
    def _find_decorated_funcs(
        view: type[BaseView | ModelView],
        view_instance: BaseView | ModelView,
        handle_fn: Callable[
            [MethodType, type[BaseView | ModelView], BaseView | ModelView],
            None,
        ],
    ) -> None:
        funcs = inspect.getmembers(view_instance, predicate=inspect.ismethod)

        for _, func in sorted(
            funcs,
            key=lambda x: inspect.getsourcelines(x[1])[1],
            reverse=True,
        ):
            handle_fn(func, view, view_instance)

    def _handle_action_decorated_func(
        self,
        func: MethodType,
        view: type[BaseView | ModelView],
        view_instance: BaseView | ModelView,
    ) -> None:
        if hasattr(func, "_action"):
            view_instance = cast(ModelView, view_instance)
            self.admin.add_route(
                route=func,
                path=f"/{view_instance.identity}/action/" + getattr(func, "_slug"),
                methods=["GET"],
                name=f"action-{view_instance.identity}-{getattr(func, '_slug')}",
                include_in_schema=getattr(func, "_include_in_schema"),
            )

            if getattr(func, "_add_in_list"):
                view_instance._custom_actions_in_list[getattr(func, "_slug")] = getattr(
                    func, "_label"
                )
            if getattr(func, "_add_in_detail"):
                view_instance._custom_actions_in_detail[getattr(func, "_slug")] = (
                    getattr(func, "_label")
                )

            if getattr(func, "_confirmation_message"):
                view_instance._custom_actions_confirmation[getattr(func, "_slug")] = (
                    getattr(func, "_confirmation_message")
                )

    def _handle_expose_decorated_func(
        self,
        func: MethodType,
        view: type[BaseView | ModelView],
        view_instance: BaseView | ModelView,
    ) -> None:
        if hasattr(func, "_exposed"):
            if view.is_model:
                path = f"/{view_instance.identity}" + getattr(func, "_path")
                name = f"view-{view_instance.identity}-{func.__name__}"
            else:
                view.identity = getattr(func, "_identity")
                path = getattr(func, "_path")
                name = f"view-{view.identity}"

            self.admin.add_route(
                route=func,
                path=path,
                methods=getattr(func, "_methods"),
                name=name,
                include_in_schema=getattr(func, "_include_in_schema"),
            )

    def add_model_view(self, view: type[ModelView]) -> None:
        """Add ModelView to the Admin.

        ???+ usage
            ```python
            from sqladmin import Admin, ModelView

            class UserAdmin(ModelView, model=User):
                pass

            admin.add_model_view(UserAdmin)
            ```
        """

        view._admin_ref = self
        # Set database engine from Admin instance
        view.session_maker = self.session_maker
        view.is_async = self.is_async
        view.ajax_lookup_url = urljoin(
            self.base_url + "/", f"{view.identity}/ajax/lookup"
        )
        view.templates = self.templates
        view_instance = view()

        self._find_decorated_funcs(
            view, view_instance, self._handle_action_decorated_func
        )

        self._find_decorated_funcs(
            view, view_instance, self._handle_expose_decorated_func
        )

        self._views.append(view_instance)
        self._build_menu(view_instance)

    def add_base_view(self, view: type[BaseView]) -> None:
        """Add BaseView to the Admin.

        ???+ usage
            ```python
            from sqladmin import BaseView, expose

            class CustomAdmin(BaseView):
                name = "Custom Page"
                icon = "fa-solid fa-chart-line"

                @expose("/custom", methods=["GET"])
                async def test_page(self, request: Request):
                    return await self.templates.TemplateResponse(request, "custom.html")

            admin.add_base_view(CustomAdmin)
            ```
        """

        view._admin_ref = self
        view.templates = self.templates
        view_instance = view()

        self._find_decorated_funcs(
            view, view_instance, self._handle_expose_decorated_func
        )
        self._views.append(view_instance)
        self._build_menu(view_instance)

    def _build_menu(self, view: ModelView | BaseView) -> None:
        if view.category:
            menu = CategoryMenu(name=view.category, icon=view.category_icon)
            menu.add_child(ViewMenu(view=view, name=view.name, icon=view.icon))
            self._menu.add(menu)
        else:
            self._menu.add(ViewMenu(view=view, icon=view.icon, name=view.name))


class BaseAdminView(BaseAdmin):
    """
    Manage right to access to an action from a model
    """

    async def _list(self, request: Request) -> None:
        model_view = self._find_model_view(request.path_params["identity"])
        if not model_view.is_accessible(request):
            raise HTTPException(status_code=403)

    async def _create(self, request: Request) -> None:
        model_view = self._find_model_view(request.path_params["identity"])
        if not model_view.can_create or not model_view.is_accessible(request):
            raise HTTPException(status_code=403)

    async def _details(self, request: Request) -> None:
        model_view = self._find_model_view(request.path_params["identity"])
        if not model_view.can_view_details or not model_view.is_accessible(request):
            raise HTTPException(status_code=403)

        if hasattr(model_view, "check_can_view_details"):
            pk = request.path_params.get("pk")
            if pk is None or not isinstance(pk, str):
                raise ValueError(
                    f'pk not found in request.path_params "{request.path_params}"'
                )
            model = await model_view.get_object_for_details(request)
            can_view_details_row = await model_view.check_can_view_details(
                request, model
            )
            if can_view_details_row is not True:
                raise HTTPException(status_code=403)

    async def _delete(self, request: Request) -> None:
        model_view = self._find_model_view(request.path_params["identity"])

        if not model_view.can_delete or not model_view.is_accessible(request):
            raise HTTPException(status_code=403)

        if hasattr(model_view, "check_can_delete"):
            pks = request.query_params.get("pks")
            if pks is None or not isinstance(pks, str):
                raise ValueError(
                    f'pks not found in request.query_params "{request.query_params}"'
                )

            for pk in pks.split(","):
                request.path_params["pk"] = pk
                model = await model_view.get_object_for_details(request)
                can_delete_row = await model_view.check_can_delete(request, model)
                if can_delete_row is not True:
                    raise HTTPException(status_code=403)

    async def _edit(self, request: Request) -> None:
        model_view = self._find_model_view(request.path_params["identity"])
        if not model_view.can_edit or not model_view.is_accessible(request):
            raise HTTPException(status_code=403)

        if hasattr(model_view, "check_can_edit"):
            pk = request.path_params.get("pk")
            if pk is None or not isinstance(pk, str):
                raise ValueError(
                    f'pk not found in request.path_params "{request.path_params}"'
                )
            model = await model_view.get_object_for_details(request)
            can_edit_row = await model_view.check_can_edit(request, model)
            if can_edit_row is not True:
                raise HTTPException(status_code=403)

    async def _export(self, request: Request) -> None:
        model_view = self._find_model_view(request.path_params["identity"])
        if not model_view.can_export or not model_view.is_accessible(request):
            raise HTTPException(status_code=403)
        if request.path_params["export_type"] not in model_view.export_types:
            raise HTTPException(status_code=404)

    async def _import(self, request: Request) -> None:
        model_view = self._find_model_view(request.path_params["identity"])
        if not model_view.is_accessible(request):
            raise HTTPException(status_code=403)

        can_import = await model_view.check_can_import(request)
        if not can_import:
            raise HTTPException(status_code=403)


class Admin(BaseAdminView):
    """Main entrypoint to admin interface.

    ???+ usage
        ```python
        from fastapi import FastAPI
        from sqladmin import Admin, ModelView

        from mymodels import User # SQLAlchemy model


        app = FastAPI()
        admin = Admin(app, engine)


        class UserAdmin(ModelView, model=User):
            column_list = [User.id, User.name]


        admin.add_view(UserAdmin)
        ```
    """

    def __init__(  # type: ignore[no-any-unimported]
        self,
        app: Starlette,
        engine: ENGINE_TYPE | None = None,
        session_maker: SESSION_MAKER | None = None,
        base_url: str = "/admin",
        title: str = "Admin",
        logo_url: str | None = None,
        logo_width: int = 64,
        logo_height: int = 64,
        favicon_url: str | None = None,
        middlewares: Sequence[Middleware] | None = None,
        debug: bool = False,
        templates_dir: str = "templates",
        authentication_backend: AuthenticationBackend | None = None,
        static_files_kwargs: dict[str, Any] | None = None,
    ) -> None:
        """
        Args:
            app: Starlette or FastAPI application.
            engine: SQLAlchemy engine instance.
            session_maker: SQLAlchemy sessionmaker instance.
            base_url: Base URL for Admin interface.
            title: Admin title.
            logo_url: URL of logo to be displayed instead of title.
            logo_width: Width of the logo image in pixels. Defaults to 64.
            logo_height: Height of the logo image in pixels. Defaults to 64.
            favicon_url: URL of favicon to be displayed.
            static_files_kwargs: Extra keyword arguments for Starlette StaticFiles.
        """

        super().__init__(
            app=app,
            engine=engine,
            session_maker=session_maker,  # type: ignore[arg-type]
            base_url=base_url,
            title=title,
            logo_url=logo_url,
            logo_width=logo_width,
            logo_height=logo_height,
            favicon_url=favicon_url,
            templates_dir=templates_dir,
            middlewares=middlewares,
            authentication_backend=authentication_backend,
        )

        static_files_kwargs = {**(static_files_kwargs or {}), "packages": ["sqladmin"]}
        statics = StaticFiles(**static_files_kwargs)

        async def http_exception(
            request: Request, exc: Exception
        ) -> Response | Awaitable[Response]:
            if not isinstance(exc, HTTPException):
                raise TypeError("Expected HTTPException, got %s" % type(exc))

            context = {
                "status_code": exc.status_code,
                "message": exc.detail,
            }
            return await self.templates.TemplateResponse(
                request, "sqladmin/error.html", context, status_code=exc.status_code
            )

        routes = [
            Mount("/statics", app=statics, name="statics"),
            Route("/", endpoint=self.index, name="index"),
            Route("/{identity}/list", endpoint=self.list, name="list"),
            Route(
                "/{identity}/details/{pk:path}", endpoint=self.details, name="details"
            ),
            Route(
                "/{identity}/delete",
                endpoint=self.delete,
                name="delete",
                methods=["DELETE"],
            ),
            Route(
                "/{identity}/create",
                endpoint=self.create,
                name="create",
                methods=["GET", "POST"],
            ),
            Route(
                "/{identity}/edit/{pk:path}",
                endpoint=self.edit,
                name="edit",
                methods=["GET", "POST"],
            ),
            Route(
                "/{identity}/export/{export_type}", endpoint=self.export, name="export"
            ),
            Route(
                "/{identity}/import",
                endpoint=self.import_endpoint,
                name="import",
                methods=["POST"],
            ),
            Route(
                "/{identity}/ajax/lookup", endpoint=self.ajax_lookup, name="ajax_lookup"
            ),
            Route("/login", endpoint=self.login, name="login", methods=["GET", "POST"]),
            Route("/logout", endpoint=self.logout, name="logout", methods=["GET"]),
        ]

        self.admin.router.routes = routes
        self.admin.exception_handlers = {HTTPException: http_exception}
        self.admin.debug = debug
        self.app.mount(base_url, app=self.admin, name="admin")

    @login_required
    async def index(self, request: Request) -> Response:
        """Index route which can be overridden to create dashboards."""

        return await self.templates.TemplateResponse(request, "sqladmin/index.html")

    @login_required
    async def list(self, request: Request) -> Response:
        """List route to display paginated Model instances."""

        await self._list(request)

        model_view = self._find_model_view(request.path_params["identity"])
        pagination = await model_view.list(request)
        pagination.add_pagination_urls(request.url)

        request_page = model_view.validate_page_number(
            request.query_params.get("page"), 1
        )

        if request_page > pagination.page:
            return RedirectResponse(
                request.url.include_query_params(page=pagination.page), status_code=302
            )

        context = {
            "model_view": model_view,
            "pagination": pagination,
            "can_import": await model_view.check_can_import(request),
        }

        if request.query_params.get("error"):
            context["error"] = request.query_params["error"]

        return await self.templates.TemplateResponse(
            request, model_view.list_template, context
        )

    @login_required
    async def details(self, request: Request) -> Response:
        """Details route."""

        await self._details(request)
        model_view = self._find_model_view(request.path_params["identity"])
        model = await model_view.get_object_for_details(request)

        if not model:
            raise HTTPException(status_code=404)

        context = {
            "model_view": model_view,
            "model": model,
            "title": model_view.name,
        }

        return await self.templates.TemplateResponse(
            request, model_view.details_template, context
        )

    @login_required
    async def delete(self, request: Request) -> Response:
        """Delete route."""

        await self._delete(request)

        identity = request.path_params["identity"]
        model_view = self._find_model_view(identity)

        params = request.query_params.get("pks", "")
        pks = params.split(",") if params else []

        referer_url = URL(request.headers.get("referer", ""))
        referer_params = MultiDict(parse_qsl(referer_url.query))

        try:
            for pk in pks:
                model = await model_view.get_object_for_delete(pk)
                if not model:
                    raise HTTPException(status_code=404, detail="Object not found")

                await model_view.delete_model(request, pk)
        except Exception as e:
            logger.exception(e)
            referer_params["error"] = str(e)

        url = URL(str(request.url_for("admin:list", identity=identity)))
        url = url.include_query_params(**referer_params)
        return PlainTextResponse(content=str(url))

    async def _resolve_after_change_response(
        self,
        request: Request,
        context: dict,
        obj: Any,
        template: str,
        identity: str,
    ) -> Response | None:
        """Return an override response from ``after_model_change`` or the
        one-time secret modal, if either is set on ``request.state``."""

        after_response = getattr(request.state, "_sqladmin_after_change_response", None)
        if isinstance(after_response, Response):
            return after_response

        if Secret.get(request) is not None:
            context["obj"] = obj
            context["secret_next_url"] = str(
                request.url_for("admin:list", identity=identity)
            )
            response = await self.templates.TemplateResponse(request, template, context)
            Secret.apply_no_store_headers(response)
            return response

        return None

    @login_required
    async def create(self, request: Request) -> Response:
        """Create model endpoint."""

        await self._create(request)

        identity = request.path_params["identity"]
        model_view = self._find_model_view(identity)

        Form = await model_view.scaffold_form(model_view._form_create_rules)

        if request.method == "GET":
            form = Form()
            context = {
                "model_view": model_view,
                "form": form,
            }
            return await self.templates.TemplateResponse(
                request, model_view.create_template, context
            )

        form_data = await self._handle_form_data(request)
        form = Form(form_data)

        context = {
            "model_view": model_view,
            "form": form,
        }

        if not form.validate():
            return await self.templates.TemplateResponse(
                request, model_view.create_template, context, status_code=400
            )

        form_data_dict = self._denormalize_wtform_data(form.data, model_view.model)
        try:
            obj = await model_view.insert_model(request, form_data_dict)
        except Exception as e:
            logger.exception(e)
            context["error"] = str(e)
            return await self.templates.TemplateResponse(
                request, model_view.create_template, context, status_code=400
            )

        override = await self._resolve_after_change_response(
            request, context, obj, model_view.create_template, identity
        )
        if override is not None:
            return override

        url = self.get_save_redirect_url(
            request=request,
            form=form_data,
            obj=obj,
            model_view=model_view,
        )
        return RedirectResponse(url=url, status_code=302)

    @login_required
    async def edit(self, request: Request) -> Response:
        """Edit model endpoint."""

        await self._edit(request)

        identity = request.path_params["identity"]
        model_view = self._find_model_view(identity)

        model = await model_view.get_object_for_edit(request)
        if not model:
            raise HTTPException(status_code=404)

        Form = await model_view.scaffold_form(model_view._form_edit_rules)
        context = {
            "obj": model,
            "model_view": model_view,
            "form": Form(obj=model, data=self._normalize_wtform_data(model)),
        }

        if request.method == "GET":
            return await self.templates.TemplateResponse(
                request, model_view.edit_template, context
            )

        form_data = await self._handle_form_data(request, model)
        form = Form(form_data)
        if not form.validate():
            context["form"] = form
            return await self.templates.TemplateResponse(
                request, model_view.edit_template, context, status_code=400
            )

        form_data_dict = self._denormalize_wtform_data(form.data, model)
        try:
            if model_view.save_as and form_data.get("save") == "Save as new":
                obj = await model_view.insert_model(request, form_data_dict)
            else:
                obj = await model_view.update_model(
                    request, pk=request.path_params["pk"], data=form_data_dict
                )
        except Exception as e:
            logger.exception(e)
            context["error"] = str(e)
            return await self.templates.TemplateResponse(
                request, model_view.edit_template, context, status_code=400
            )

        override = await self._resolve_after_change_response(
            request, context, obj, model_view.edit_template, identity
        )
        if override is not None:
            return override

        url = self.get_save_redirect_url(
            request=request,
            form=form_data,
            obj=obj,
            model_view=model_view,
        )
        return RedirectResponse(url=url, status_code=302)

    @login_required
    async def export(self, request: Request) -> Response:
        """Export model endpoint."""

        await self._export(request)

        identity = request.path_params["identity"]
        export_type = request.path_params["export_type"]

        model_view = self._find_model_view(identity)
        rows = await model_view.get_model_objects(
            request=request, limit=model_view.export_max_rows
        )
        return await model_view.export_data(
            rows, export_type=export_type, request=request
        )

    @login_required
    async def import_endpoint(self, request: Request) -> Response:
        """Import model endpoint."""

        await self._import(request)

        identity = request.path_params["identity"]
        model_view = self._find_model_view(identity)

        csv_content, continue_on_error = await self._handle_form_file(
            request,
            model_view,
        )
        if not csv_content:
            return Response(content="Undefined file.", status_code=400)

        try:
            data = parse_csv(csv_content, model_view._import_prop_names)
        except ValueError as exc:
            return Response(content=str(exc), status_code=400)
        except Exception as exc:
            logger.exception(exc)
            return Response(content="Failed to parse CSV file.", status_code=400)

        Form = await model_view.scaffold_form(model_view._form_create_rules)

        async def import_events() -> AsyncGenerator[bytes, None]:
            total = len(data)
            processed = 0
            imported = 0
            skipped = 0
            import_models: list[dict[str, Any]] = []
            missed_rows: list[dict[str, Any]] = []
            missed_rows_omitted_count = 0
            fk_exists_cache: dict[tuple[str, str, str], bool] = {}

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
                    "imported": imported,
                    "skipped": skipped,
                }
            )

            for line_number, row in enumerate(data, start=2):
                await anyio.sleep(0)
                if await request.is_disconnected():
                    return

                processed += 1
                form = Form(row)
                row_errors: dict[str, Any] = {}

                if not form.validate():
                    row_errors.update(form.errors)

                row_data = {col: row.get(col) for col in model_view._import_prop_names}
                form_data_dict = self._denormalize_wtform_data(
                    form.data,
                    model_view.model,
                )

                # Import forms may omit FK columns (when form_include_pk=False).
                # Keep raw CSV values for imported columns missing in the form.
                merged_import_data = dict(form_data_dict)
                for column_name in model_view._import_prop_names:
                    if column_name in merged_import_data:
                        continue
                    if column_name in row_data:
                        merged_import_data[column_name] = row_data[column_name]

                foreign_key_errors = await self._validate_foreign_key_values(
                    model_view=model_view,
                    row_data=merged_import_data,
                    fk_exists_cache=fk_exists_cache,
                )
                row_errors.update(foreign_key_errors)

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
                    imported += 1

                if processed % 20 == 0 or processed == total:
                    yield emit(
                        {
                            "type": "progress",
                            "phase": "validating",
                            "processed": processed,
                            "total": total,
                            "imported": imported,
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
                    "imported": imported,
                    "skipped": skipped,
                }
            )

            if import_models:
                (
                    success,
                    persisted_count,
                    failure_summary,
                    persistence_failed_rows,
                ) = await self._persist_import_models_with_count_check(
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

            imported = persisted_count
            summary = (
                f"Imported {imported} out of {total} row(s). Skipped {skipped} row(s)."
            )

            yield emit(
                {
                    "type": "result",
                    "ok": True,
                    "aborted": False,
                    "processed": total,
                    "total": total,
                    "imported": imported,
                    "skipped": skipped,
                    "missed_rows": missed_rows,
                    "missed_rows_omitted_count": missed_rows_omitted_count,
                    "summary": summary,
                }
            )

        return StreamingResponse(import_events(), media_type="application/x-ndjson")

    async def _persist_import_models_with_count_check(
        self,
        model_view: ModelView,
        request: Request,
        import_models: List[dict[str, Any]],
        continue_on_error: bool,
    ) -> Tuple[bool, int, str | None, List[dict[str, Any]]]:
        if model_view.is_async:
            return await self._persist_import_models_with_count_check_async(
                model_view,
                request,
                import_models,
                continue_on_error,
            )

        return await anyio.to_thread.run_sync(
            self._persist_import_models_with_count_check_sync,
            model_view,
            request,
            import_models,
            continue_on_error,
        )

    async def _validate_foreign_key_values(
        self,
        model_view: ModelView,
        row_data: dict[str, Any],
        fk_exists_cache: dict[tuple[str, str, str], bool],
    ) -> dict[str, List[str]]:
        mapper = sa_inspect(model_view.model)
        foreign_key_errors: dict[str, List[str]] = {}

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

                exists = fk_exists_cache.get(cache_key)
                if exists is None:
                    exists = await self._foreign_key_value_exists(
                        model_view=model_view,
                        target_column=target_column,
                        value=value,
                    )
                    fk_exists_cache[cache_key] = exists

                if not exists:
                    foreign_key_errors.setdefault(column.key, []).append(
                        (
                            "Referenced value does not exist for "
                            f"{foreign_key.target_fullname}."
                        )
                    )

        return foreign_key_errors

    async def _foreign_key_value_exists(
        self,
        model_view: ModelView,
        target_column: Any,
        value: Any,
    ) -> bool:
        try:
            coerced_value = coerce_column_value(target_column, value)
        except (TypeError, ValueError):
            return False

        stmt = (
            select(sa_func.count())
            .select_from(target_column.table)
            .where(target_column == coerced_value)
        )

        if model_view.is_async:
            async with model_view.session_maker(expire_on_commit=False) as session:
                count = int(await session.scalar(stmt) or 0)
                return count > 0

        def run_sync() -> bool:
            with model_view.session_maker(expire_on_commit=False) as session:
                count = int(session.execute(stmt).scalar_one() or 0)
                return count > 0

        return await anyio.to_thread.run_sync(run_sync)

    async def _persist_import_models_with_count_check_async(
        self,
        model_view: ModelView,
        request: Request,
        import_models: List[dict[str, Any]],
        continue_on_error: bool,
    ) -> Tuple[bool, int, str | None, List[dict[str, Any]]]:
        query = Query(model_view)
        failed_rows: List[dict[str, Any]] = []

        try:
            async with model_view.session_maker(expire_on_commit=False) as session:
                persisted_count = 0
                successful_objs_with_data: List[Tuple[Any, dict[str, Any]]] = []

                for row_entry in import_models:
                    line_number = int(row_entry["line"])
                    source_data = row_entry["data"]
                    row = row_entry["model"]

                    if await request.is_disconnected():
                        await session.rollback()
                        return False, 0, "Import canceled. No rows were imported.", []

                    try:
                        async with session.begin_nested():
                            obj = query._get_model_object(row)
                            await model_view.on_model_change(row, obj, True, request)
                            obj = await query._set_attributes_async(session, obj, row)
                            session.add(obj)
                            await session.flush()

                        successful_objs_with_data.append((obj, row))
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

                for obj, row in successful_objs_with_data:
                    await model_view.after_model_change(row, obj, True, request)

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

    def _persist_import_models_with_count_check_sync(
        self,
        model_view: ModelView,
        request: Request,
        import_models: List[dict[str, Any]],
        continue_on_error: bool,
    ) -> Tuple[bool, int, str | None, List[dict[str, Any]]]:
        query = Query(model_view)
        failed_rows: List[dict[str, Any]] = []

        try:
            with model_view.session_maker(expire_on_commit=False) as session:
                persisted_count = 0
                successful_objs_with_data: List[Tuple[Any, dict[str, Any]]] = []

                for row_entry in import_models:
                    line_number = int(row_entry["line"])
                    source_data = row_entry["data"]
                    row = row_entry["model"]

                    if anyio.from_thread.run(request.is_disconnected):
                        session.rollback()
                        return False, 0, "Import canceled. No rows were imported.", []

                    try:
                        with session.begin_nested():
                            obj = query._get_model_object(row)
                            anyio.from_thread.run(
                                model_view.on_model_change,
                                row,
                                obj,
                                True,
                                request,
                            )
                            obj = query._set_attributes_sync(session, obj, row)
                            session.add(obj)
                            session.flush()

                        successful_objs_with_data.append((obj, row))
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

                for obj, row in successful_objs_with_data:
                    anyio.from_thread.run(
                        model_view.after_model_change,
                        row,
                        obj,
                        True,
                        request,
                    )

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

    async def login(self, request: Request) -> Response:
        if self.authentication_backend is None:
            raise HTTPException(
                status_code=503,
                detail="Authentication backend not configured.",
            )

        context = {}
        if request.method == "GET":
            return await self.templates.TemplateResponse(request, "sqladmin/login.html")

        ok = await self.authentication_backend.login(request)
        if not ok:
            context["error"] = "Invalid credentials."
            return await self.templates.TemplateResponse(
                request, "sqladmin/login.html", context, status_code=400
            )

        return RedirectResponse(request.url_for("admin:index"), status_code=302)

    async def logout(self, request: Request) -> Response:
        if self.authentication_backend is None:
            raise HTTPException(
                status_code=503,
                detail="Authentication backend not configured.",
            )

        response = await self.authentication_backend.logout(request)

        if isinstance(response, Response):
            return response

        return RedirectResponse(request.url_for("admin:index"), status_code=302)

    @login_required
    async def ajax_lookup(self, request: Request) -> Response:
        """Ajax lookup route."""

        identity = request.path_params["identity"]
        model_view = self._find_model_view(identity)

        if not model_view.is_accessible(request):
            raise HTTPException(status_code=403)

        name = request.query_params.get("name")
        term = request.query_params.get("term")

        if not name or not term:
            raise HTTPException(status_code=400)

        try:
            loader: QueryAjaxModelLoader = model_view._form_ajax_refs[name]
        except KeyError as exc:
            raise HTTPException(status_code=400) from exc

        data = [loader.format(m) for m in await loader.get_list(term)]
        return JSONResponse({"results": data})

    @staticmethod
    def get_save_redirect_url(
        request: Request, form: FormData, model_view: ModelView, obj: Any
    ) -> str | URL:
        """
        Get the redirect URL after a save action
        which is triggered from create/edit page.
        """

        identity = request.path_params["identity"]
        identifier = get_object_identifier(obj)

        if form.get("save") == "Save":
            url = URL(str(request.url_for("admin:list", identity=identity)))
            if request.url.query:
                url = url.replace(query=request.url.query)
            return url

        if form.get("save") == "Save and continue editing" or (
            form.get("save") == "Save as new" and model_view.save_as_continue
        ):
            return request.url_for("admin:edit", identity=identity, pk=identifier)

        return request.url_for("admin:create", identity=identity)

    @staticmethod
    async def _handle_form_data(request: Request, obj: Any = None) -> FormData:
        """
        Handle form data and modify in case of UploadFile.
        This is needed since in edit page
        there's no way to show current file of object.
        """

        form = await request.form()
        form_data: list[tuple[str, str | UploadFile]] = []
        for key, value in form.multi_items():
            if not isinstance(value, UploadFile):
                form_data.append((key, value))
                continue

            should_clear = form.get(key + "_checkbox")
            empty_upload = len(await value.read(1)) != 1
            await value.seek(0)
            if should_clear:
                form_data.append((key, UploadFile(io.BytesIO(b""))))
            elif empty_upload and obj and getattr(obj, key):
                f = getattr(obj, key)  # In case of update, imitate UploadFile
                form_data.append((key, UploadFile(filename=f.name, file=f.open())))
            else:
                form_data.append((key, value))
        return FormData(form_data)

    async def _handle_form_file(
        self,
        request: Request,
        model_view: ModelView,
    ) -> tuple[bytes | None, bool]:
        async with request.form(max_files=1) as form:
            continue_on_error = str(form.get("continue_on_error", "")).lower() in {
                "1",
                "true",
                "on",
                "yes",
            }
            csv_file = form.get("csvfile")

            if not isinstance(csv_file, UploadFile):
                raise HTTPException(
                    status_code=400, detail="Invalid file upload. Expected UploadFile."
                )

            if (
                not csv_file
                or not csv_file.filename
                or not csv_file.filename.lower().endswith(".csv")
            ):
                return None, continue_on_error

            allowed_content_types = {
                None,
                "",
                "text/csv",
                "application/csv",
                "text/plain",
                "application/vnd.ms-excel",
            }
            if csv_file.content_type not in allowed_content_types:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid CSV file type.",
                )

            csv_content = await csv_file.read()
            if len(csv_content) > model_view.max_import_file_size:
                raise HTTPException(
                    status_code=413,
                    detail="CSV file is too large.",
                )
        return csv_content, continue_on_error

    @staticmethod
    def _normalize_wtform_data(obj: Any) -> dict:
        form_data = {}
        for field_name in WTFORMS_ATTRS:
            if value := getattr(obj, field_name, None):
                form_data[field_name + "_"] = value
        return form_data

    @staticmethod
    def _denormalize_wtform_data(form_data: dict, obj: Any) -> dict:
        data = form_data.copy()
        for field_name in WTFORMS_ATTRS_REVERSED:
            reserved_field_name = field_name[:-1]
            if (
                field_name in data
                and not hasattr(obj, field_name)
                and hasattr(obj, reserved_field_name)
            ):
                data[reserved_field_name] = data.pop(field_name)
        return data


def expose(
    path: str,
    *,
    methods: list[str] | None = None,
    identity: str | None = None,
    include_in_schema: bool = True,
) -> Callable[..., Any]:
    """Expose View with information."""

    @no_type_check
    def wrap(func):
        func._exposed = True
        func._path = path
        func._methods = methods or ["GET"]
        func._identity = identity or func.__name__
        func._include_in_schema = include_in_schema
        return login_required(func)

    return wrap


def action(
    name: str,
    label: str | None = None,
    confirmation_message: str | None = None,
    *,
    include_in_schema: bool = True,
    add_in_detail: bool = True,
    add_in_list: bool = True,
) -> Callable[..., Any]:
    """Decorate a [`ModelView`][sqladmin.models.ModelView] function
    with this to:

    * expose it as a custom "action" route
    * add a button to the admin panel to invoke the action

    When invoked from the admin panel, the following query parameter(s) are passed:

    * `pks`: the comma-separated list of selected object PKs - can be empty

    Args:
        name: Unique name for the action - should be alphanumeric, dash and underscore
        label: Human-readable text describing action
        confirmation_message: Message to show before confirming action
        include_in_schema: Indicating if the endpoint be included in the schema
        add_in_detail: Indicating if action should be displayed on model detail page
        add_in_list: Indicating if action should be displayed on model list page
    """

    @no_type_check
    def wrap(func):
        func._action = True
        func._slug = slugify_action_name(name)
        func._label = label if label is not None else name
        func._confirmation_message = confirmation_message
        func._include_in_schema = include_in_schema
        func._add_in_detail = add_in_detail
        func._add_in_list = add_in_list
        return login_required(func)

    return wrap
