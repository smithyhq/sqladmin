from typing import Generator

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
