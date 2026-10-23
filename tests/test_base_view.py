import functools
import importlib
import sys
from collections.abc import Callable, Generator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.orm import declarative_base
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.testclient import TestClient

from sqladmin import Admin, BaseView, expose
from tests.common import sync_engine as engine

Base = declarative_base()  # type: ignore

app = Starlette()
admin = Admin(app=app, engine=engine, templates_dir="tests/templates")


class CustomAdmin(BaseView):
    name = "test"
    icon = "fa fa-test"

    @expose("/custom", methods=["GET"])
    async def custom(self, request: Request):
        return await self.templates.TemplateResponse(request, "custom.html")

    @expose("/custom/report")
    async def custom_report(self, request: Request):
        return await self.templates.TemplateResponse(request, "custom.html")

    # Add this for second test: Before alphabetically (!)
    # first `expose` was BaseView url, now it's first by `order`
    @expose("/a")
    async def a(self, request: Request):
        return await self.templates.TemplateResponse(request, "custom.html")


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app=app, base_url="http://testserver") as c:
        yield c


def test_base_view(client: TestClient) -> None:
    admin.add_view(CustomAdmin)

    response = client.get("/admin/custom")

    assert response.status_code == 200
    assert "<p>Here I'm going to display some data.</p>" in response.text

    response = client.get("/admin/custom/report")
    assert response.status_code == 200


def test_menu_view_url(client: TestClient) -> None:
    admin.add_view(CustomAdmin)

    response = client.get("/admin")
    assert response.status_code == 200

    assert (
        '<a class="nav-link " href="http://testserver/admin/custom">' in response.text
    )


def test_menu_active_on_custom_view(client: TestClient) -> None:
    # Regression test for #956: custom (BaseView) menu items were never marked
    # active, because is_active compared the view identity against an `identity`
    # path param that custom-view routes do not have.
    admin.add_view(CustomAdmin)

    # On the custom view's own page the sidebar link is marked active.
    response = client.get("/admin/custom")
    assert response.status_code == 200
    assert (
        '<a class="nav-link active" href="http://testserver/admin/custom">'
        in response.text
    )

    # On an unrelated page (the admin index) it is not active.
    response = client.get("/admin")
    assert response.status_code == 200
    assert (
        '<a class="nav-link " href="http://testserver/admin/custom">' in response.text
    )


class IndexNamedView(BaseView):
    name = "Activity Analytics"
    icon = "fa fa-chart"

    @expose("/activity-analytics", methods=["GET"])
    async def index(self, request: Request):
        return await self.templates.TemplateResponse(request, "custom.html")


def test_menu_view_url_with_index_method(client: TestClient) -> None:
    # Regression test for #1057: a BaseView whose first `@expose` method is
    # named `index` used to register a route named `admin:index`, colliding
    # with the built-in index route. The sidebar link then resolved to the
    # admin root (`/admin`) instead of the exposed path.
    admin.add_view(IndexNamedView)

    response = client.get("/admin/activity-analytics")
    assert response.status_code == 200

    response = client.get("/admin")
    assert response.status_code == 200
    assert (
        '<a class="nav-link " href="http://testserver/admin/activity-analytics">'
        in response.text
    )


def test_views_register_when_their_source_file_is_gone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Registration reads line numbers from the loaded code, not from the
    # source file: it may have changed or gone since import.
    (tmp_path / "vanishing_views.py").write_text(
        "from sqladmin import BaseView, expose\n"
        "\n"
        "\n"
        "class ReportPage(BaseView):\n"
        '    @expose("/second")\n'
        "    async def second(self, request):\n"
        "        pass\n"
        "\n"
        '    @expose("/first")\n'
        "    async def first(self, request):\n"
        "        pass\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    try:
        module = importlib.import_module("vanishing_views")
    finally:
        sys.modules.pop("vanishing_views", None)
    (tmp_path / "vanishing_views.py").unlink()

    Admin(app=Starlette(), engine=engine).add_view(module.ReportPage)

    assert module.ReportPage.identity == "second"


def test_first_exposed_method_wins_even_when_wrapped() -> None:
    # The identity is the first `expose` in the class body, whatever the
    # method names are and whether a decorator wraps them.
    def track(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await func(*args, **kwargs)

        return wrapper

    class WrappedPage(BaseView):
        name = "Wrapped"

        @expose("/zeta")
        @track
        async def zeta(self, request: Request):
            return await self.templates.TemplateResponse(request, "custom.html")

        @expose("/alpha")
        @track
        async def alpha(self, request: Request):
            return await self.templates.TemplateResponse(request, "custom.html")

    local_app = Starlette()
    local_admin = Admin(app=local_app, engine=engine, templates_dir="tests/templates")
    local_admin.add_view(WrappedPage)

    assert WrappedPage.identity == "zeta"

    with TestClient(app=local_app, base_url="http://testserver") as c:
        assert c.get("/admin/zeta").status_code == 200
        assert c.get("/admin/alpha").status_code == 200
        assert 'href="http://testserver/admin/zeta"' in c.get("/admin").text
