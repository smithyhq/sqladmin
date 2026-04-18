from typing import Generator

import pytest
from sqlalchemy import (
    Integer,
    String,
    func,
    select,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    MappedAsDataclass,
    mapped_column,
    sessionmaker,
)
from starlette.applications import Starlette
from starlette.testclient import TestClient

from sqladmin import Admin, ModelView
from tests.common import sync_engine as engine

session_maker = sessionmaker(bind=engine)


class Base(MappedAsDataclass, DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False)
    name: Mapped[str] = mapped_column(String(length=16), init=True)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=True, init=False)


class UserAdmin(ModelView, model=User):
    column_list = ["name", "email"]
    column_labels = {"name": "Name", "email": "Email"}


app = Starlette()
admin = Admin(app=app, engine=engine)
admin.add_model_view(UserAdmin)


@pytest.fixture(autouse=True)
def prepare_database() -> Generator[None, None, None]:
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app=app, base_url="http://testserver") as c:
        yield c


def test_sync_create_dataclass(client: TestClient) -> None:
    client.post("/admin/user/create", data={"name": "foo", "email": "bar"})
    stmt = select(func.count(User.id))
    with session_maker() as s:
        result = s.execute(stmt)
    assert result.scalar_one() == 1


def test_update_dataclass(client: TestClient) -> None:
    with session_maker() as session:
        user = User(name="John Doe")
        session.add(user)
        session.commit()

    client.post("/admin/user/edit/1", data={"name": "foo", "email": "bar"})

    stmt = select(User)
    with session_maker() as s:
        user = s.execute(stmt).scalar_one()
    assert user.name == "foo"
    assert user.email == "bar"
