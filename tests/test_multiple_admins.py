from collections.abc import Generator

import pytest
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import declarative_base
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.testclient import TestClient

from sqladmin import Admin, ModelView
from tests.common import sync_engine as engine

Base = declarative_base()


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True)
    name = Column(String(32))


class Supplier(Base):
    __tablename__ = "suppliers"

    id = Column(Integer, primary_key=True)
    name = Column(String(32))


class CustomerAdmin(ModelView, model=Customer):
    column_list = [Customer.id, Customer.name]


class SupplierAdmin(ModelView, model=Supplier):
    column_list = [Supplier.id, Supplier.name]


@pytest.fixture(autouse=True)
def prepare_database() -> Generator[None, None, None]:
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def app() -> Starlette:
    app = Starlette()

    first = Admin(app=app, engine=engine, base_url="/first")
    first.add_view(CustomerAdmin)

    second = Admin(app=app, engine=engine, base_url="/second")
    second.add_view(SupplierAdmin)

    async def outside(request: Request) -> PlainTextResponse:
        return PlainTextResponse(str(request.url_for("admin:index")))

    app.add_route("/outside", outside)
    return app


def test_second_admin_links_point_to_its_own_base_url(app: Starlette) -> None:
    with TestClient(app) as client:
        response = client.get("/second/")

    assert response.status_code == 200
    assert 'href="http://testserver/second/supplier/list"' in response.text
    assert "http://testserver/second/statics/" in response.text
    assert "/first/" not in response.text


def test_second_admin_redirects_stay_on_its_own_base_url(app: Starlette) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/second/supplier/create",
            data={"name": "ACME", "save": "Save"},
            follow_redirects=False,
        )

    assert response.status_code == 302
    assert response.headers["location"] == "http://testserver/second/supplier/list"


def test_first_admin_is_unaffected(app: Starlette) -> None:
    with TestClient(app) as client:
        response = client.get("/first/")
        outside = client.get("/outside")

    assert response.status_code == 200
    assert 'href="http://testserver/first/customer/list"' in response.text
    assert "/second/" not in response.text
    assert outside.text == "http://testserver/first/"
