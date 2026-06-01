from typing import Generator

import pytest
from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from starlette.applications import Starlette
from starlette.testclient import TestClient

from sqladmin import Admin, ModelView
from tests.common import sync_engine as engine

session_maker = sessionmaker(bind=engine)

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(String(32), default="SQLAdmin")

    addresses = relationship("Address", back_populates="user")


class Address(Base):
    __tablename__ = "addresses"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))

    user = relationship("User", back_populates="addresses")


@pytest.fixture(autouse=True)
def prepare_database() -> Generator[None, None, None]:
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


def test_root_path_ajax_lookup_url_includes_root_path() -> None:
    """AJAX data-url for Select2 relationship fields must include root_path."""
    app = Starlette()
    admin = Admin(app=app, engine=engine)

    class UserAdmin(ModelView, model=User):
        form_ajax_refs = {
            "addresses": {
                "fields": ("id",),
            }
        }

    class AddressAdmin(ModelView, model=Address): ...

    admin.add_view(UserAdmin)
    admin.add_view(AddressAdmin)

    with TestClient(app, root_path="/api/v1") as client:
        # Simulate uvicorn --root-path: requests arrive with prefix in path
        response = client.get("/api/v1/admin/user/create")
        assert response.status_code == 200
        assert (
            'data-url="http://testserver/api/v1/admin/user/ajax/lookup"'
            in response.text
        )

        # The template passes data_url (underscore) as a kwarg. WTForms'
        # clean_key converts it to data-url (dash) before the widget sees it.
        # Verify the underscore variant doesn't leak as a raw HTML attribute.
        assert "data_url=" not in response.text

        # Edit page should also have ajax data-url with root_path
        with session_maker() as session:
            session.add(User(id=1, name="test"))
            session.commit()

        response = client.get("/api/v1/admin/user/edit/1")
        assert response.status_code == 200
        assert (
            'data-url="http://testserver/api/v1/admin/user/ajax/lookup"'
            in response.text
        )
        assert "data_url=" not in response.text
