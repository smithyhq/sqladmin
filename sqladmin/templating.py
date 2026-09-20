from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import jinja2
from markupsafe import Markup
from starlette import status
from starlette.background import BackgroundTask
from starlette.datastructures import URL
from starlette.requests import Request
from starlette.responses import HTMLResponse
from starlette.types import Receive, Scope, Send


def _tojson_filter(value: Any) -> Markup:
    """Embed a Python value inside a ``<script>`` block as a JS literal.

    ``jinja2.ext.i18n``'s gettext output is exempt from Jinja's HTML
    autoescaping by design, so translators can put safe HTML in a translated
    string. That also means a translation containing a plain ``"`` reaches a
    template's ``<script>`` block completely unescaped: it closes the JS
    string literal early, and anything after it becomes live JavaScript. This
    is the correct way to embed any dynamic value — translated or not — inside
    inline script: ``json.dumps`` produces a valid JS literal, and ``<``,
    ``>``, ``&`` and ``'`` are additionally escaped so the value cannot close
    an enclosing ``</script>`` tag either. Wrapped in ``Markup`` so autoescape
    does not re-escape the already-correct output as if it were HTML.
    """

    return Markup(  # nosec: markupsafe_markup_xss
        json.dumps(value, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("'", "\\u0027")
    )


class _TemplateResponse(HTMLResponse):
    def __init__(
        self,
        template: jinja2.Template,
        content: str,
        context: dict,
        status_code: int = status.HTTP_200_OK,
        headers: Mapping[str, str] | None = None,
        media_type: str | None = None,
        background: BackgroundTask | None = None,
    ):
        self.template = template
        self.context = context
        super().__init__(content, status_code, headers, media_type, background)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        request = self.context.get("request", {})
        extensions = request.get("extensions", {})
        if "http.response.debug" in extensions:
            await send(
                {
                    "type": "http.response.debug",
                    "info": {
                        "template": self.template,
                        "context": self.context,
                    },
                }
            )
        await super().__call__(scope, receive, send)


class Jinja2Templates:
    def __init__(self, directory: str) -> None:
        @jinja2.pass_context
        def url_for(context: dict, __name: str, **path_params: Any) -> URL:
            request: Request = context["request"]
            return request.url_for(__name, **path_params)

        loader = jinja2.FileSystemLoader(directory)
        self.env = jinja2.Environment(loader=loader, autoescape=True, enable_async=True)
        self.env.globals["url_for"] = url_for
        self.env.filters["tojson"] = _tojson_filter

    async def TemplateResponse(
        self,
        request: Request,
        name: str,
        context: dict | None = None,
        status_code: int = status.HTTP_200_OK,
    ) -> _TemplateResponse:
        context = context or {}
        context.setdefault("request", request)
        template = self.env.get_template(name)
        content = await template.render_async(context)
        return _TemplateResponse(
            template=template,
            content=content,
            context=context,
            status_code=status_code,
        )
