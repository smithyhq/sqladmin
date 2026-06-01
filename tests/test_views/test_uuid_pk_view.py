from typing import Any, Generator
from uuid import UUID

import pytest
from sqlalchemy import ForeignKey
from sqlalchemy.orm import (
    Mapped,
    declarative_base,
    mapped_column,
    relationship,
    sessionmaker,
)
from starlette.applications import Starlette
from starlette.testclient import TestClient

from sqladmin import Admin, ModelView
from tests.common import sync_engine as engine

if engine.name != "postgresql":
    pytest.skip("PostgreSQL only", allow_module_level=True)


Base = declarative_base()  # type: Any
session_maker = sessionmaker(bind=engine)

app = Starlette()
admin = Admin(app=app, engine=engine)


class User(Base):
    __tablename__ = "users"

    uuid: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str]
    posts: Mapped[list["Post"]] = relationship("Post", back_populates="user")

    def __str__(self) -> str:
        return f"User {self.uuid}"


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.uuid"))
    user: Mapped[User] = relationship("User", back_populates="posts")
    title: Mapped[str]


@pytest.fixture
def prepare_database() -> Generator[None, None, None]:
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def client(prepare_database: Any) -> Generator[TestClient, None, None]:
    with TestClient(app=app, base_url="http://testserver") as c:
        yield c


class UserAdmin(ModelView, model=User):
    column_list = [User.uuid, User.name, User.posts]


class PostAdmin(ModelView, model=Post):
    column_list = [Post.id, Post.title, Post.user]


admin.add_view(UserAdmin)
admin.add_view(PostAdmin)


def base_content():
    with session_maker() as session:
        user = User(uuid=UUID("00000000-0000-0000-0000-000000000001"), name="John")
        session.add(user)

        post1 = Post(id=1, title="Post 1", user_id=user.uuid)
        post2 = Post(id=2, title="Post 2", user_id=user.uuid)
        session.add_all([post1, post2])
        session.commit()


def test_uuid_pk_view(client: TestClient) -> None:
    base_content()
    response = client.get("/admin/user/details/00000000-0000-0000-0000-000000000001")

    assert response.status_code == 200


def test_uuid_url_from_posts(client: TestClient) -> None:
    base_content()
    response = client.get("/admin/post/details/1")

    assert response.status_code == 200

    assert (
        '<a href="http://testserver/admin/user/details/00000000-0000-0000-0000-000000000001">'
        in response.text
    )
