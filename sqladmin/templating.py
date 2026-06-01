from __future__ import annotations

from typing import Any, Dict, Optional

import jinja2
from litestar import Request
from litestar.response import Response

from sqladmin.utils import include_query_params, remove_query_params


class Jinja2Templates:
    def __init__(self, directory: str) -> None:
        self._static_file_names: set[str] = set()

        @jinja2.pass_context
        def url_for(context: Dict, __name: str, **path_params: Any) -> str:
            request: Request = context["request"]
            if __name in self._static_file_names and "path" in path_params:
                return request.url_for(__name, file_path=path_params["path"])
            return str(request.url_for(__name, **path_params))

        @jinja2.pass_context
        def url_for_static_asset(
            context: Dict, __name: str, **path_params: Any
        ) -> str:
            request: Request = context["request"]
            return request.url_for_static_asset(__name, **path_params)

        loader = jinja2.FileSystemLoader(directory)
        self.env = jinja2.Environment(
            loader=loader,
            autoescape=True,
            enable_async=True,
        )
        self.env.globals["url_for"] = url_for
        self.env.globals["url_for_static_asset"] = url_for_static_asset
        self.env.globals["include_query_params"] = include_query_params
        self.env.globals["remove_query_params"] = remove_query_params

    async def TemplateResponse(
        self,
        request: Request,
        name: str,
        context: Optional[Dict] = None,
        status_code: int = 200,
    ) -> Response:
        context = context or {}
        context.setdefault("request", request)
        template = self.env.get_template(name)
        content = await template.render_async(context)
        return Response(content, media_type="text/html", status_code=status_code)
