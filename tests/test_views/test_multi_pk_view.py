from typing import Generator

import pytest
from sqlalchemy import Column, ForeignKey, ForeignKeyConstraint, Integer, String
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from starlette.applications import Starlette
from starlette.testclient import TestClient

from sqladmin import Admin, ModelView
from tests.common import sync_engine as engine

Base = declarative_base()  # type: Any
session_maker = sessionmaker(bind=engine)

app = Starlette()
admin = Admin(app=app, engine=engine)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)

    movie_reviews = relationship("Review", back_populates="user")

    def __str__(self) -> str:
        return f"User {self.id}"


class Movie(Base):
    __tablename__ = "movies"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)

    reviews = relationship("Review", back_populates="movie")

    def __str__(self) -> str:
        return f"Movie {self.id}"


class Review(Base):
    __tablename__ = "reviews"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    movie_id = Column(Integer, ForeignKey("movies.id"), primary_key=True)
    rating = Column(Integer, nullable=False)
    review_text = Column(String, nullable=True)

    movie = relationship("Movie", back_populates="reviews")
    user = relationship("User", back_populates="movie_reviews")

    complaints = relationship("ReviewComplaint", back_populates="review")

    def __str__(self) -> str:
        return f"Review by {self.user_id} for {self.movie_id}"


class ReviewComplaint(Base):
    __tablename__ = "review_complaints"

    id = Column(Integer, primary_key=True)
    # FKs intentionally in oposite order of the corresponding PKs since
    # SQLAdmin should not assume they always match in order.
    review_movie_id = Column(Integer, nullable=False)
    review_user_id = Column(Integer, nullable=False)
    complaint = Column(String, nullable=False)

    review = relationship("Review", back_populates="complaints")

    __table_args__ = (
        ForeignKeyConstraint(
            ["review_user_id", "review_movie_id"],
            ["reviews.user_id", "reviews.movie_id"],
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
    )

    def __str__(self) -> str:
        return f"ReviewComplaint {self.id}"


@pytest.fixture(autouse=True)
def prepare_database() -> Generator[None, None, None]:
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app=app, base_url="http://testserver") as c:
        yield c


class UserAdmin(ModelView, model=User):
    column_list = [
        User.id,
        User.name,
    ]


class MovieAdmin(ModelView, model=Movie):
    column_list = [
        User.id,
        User.name,
    ]


class ReviewAdmin(ModelView, model=Review):
    column_list = [
        Review.user_id,
        Review.movie_id,
        Review.rating,
    ]


class ReviewComplaintAdmin(ModelView, model=ReviewComplaint):
    column_list = [
        ReviewComplaint.id,
        ReviewComplaint.review_user_id,
        ReviewComplaint.review_movie_id,
    ]


admin.add_view(UserAdmin)
admin.add_view(MovieAdmin)
admin.add_view(ReviewAdmin)
admin.add_view(ReviewComplaintAdmin)


def base_content():
    with session_maker() as session:
        session.add(Movie(id=1, name="Python"))
        session.add(Movie(id=2, name="Cobra"))
        session.add(Movie(id=3, name="Cobra 2"))

        session.add(User(id=1, name="John Doe"))
        session.add(User(id=2, name="Foo"))
        session.add(User(id=3, name="Bar"))

        session.add(Review(user_id=1, movie_id=2, rating=8))
        session.add(
            Review(
                user_id=1,
                movie_id=1,
                rating=9,
                review_text="Love movies about venomous snakes, great sequel!",
            )
        )
        session.add(Review(user_id=2, movie_id=1, rating=6))
        session.add(Review(user_id=2, movie_id=2, rating=10))
        session.add(
            Review(
                user_id=3,
                movie_id=3,
                rating=10,
                review_text="Haven't seen it yet but the last movie was great!",
            )
        )
        session.add(Review(user_id=3, movie_id=1, rating=4))

        session.add(
            ReviewComplaint(
                id=1,
                review_user_id=1,
                review_movie_id=1,
                complaint="Python isn't a venomous. "
                "They probably meant this as a review for Cobra 2.",
            )
        )
        session.add(
            ReviewComplaint(
                id=2,
                review_user_id=3,
                review_movie_id=3,
                complaint="Not a review, they admit they haven't seen the movie.",
            )
        )
        session.commit()


def test_root_view(client: TestClient) -> None:
    response = client.get("/admin")

    assert response.status_code == 200
    assert '<span class="nav-link-title">Users</span>' in response.text
    assert '<span class="nav-link-title">Movies</span>' in response.text
    assert '<span class="nav-link-title">Reviews</span>' in response.text
    assert '<span class="nav-link-title">Review Complaints</span>' in response.text


def test_list_multipk_items(client: TestClient) -> None:
    base_content()
    response = client.get("/admin/review/list")
    assert response.status_code == 200

    # Links contain multiple primary keys
    assert '<a href="http://testserver/admin/review/details/1;1"' in response.text
    assert '<a href="http://testserver/admin/review/edit/1;2"' in response.text
    assert (
        'data-url="http://testserver/admin/review/delete?pks=3%3B1"' in response.text
    )  # 3;1


def test_delete_by_multipk(client: TestClient) -> None:
    base_content()
    del_response = client.delete("/admin/review/delete?pks=3%3B1")
    assert del_response.status_code == 200

    get_response = client.get("/admin/review/details/3;1")
    assert get_response.status_code == 404


def test_edit_by_multipk(client: TestClient) -> None:
    base_content()
    data = {
        "movie": "1",
        "user": "1",
        "complaints": "1",
        "rating": "-99",
        "review_test": "_",
        "save": "Save",
    }
    response = client.post("/admin/review/edit/1;1", data=data)
    assert response.status_code == 200
    assert response.text.count("<td>-99</td>") == 1


def test_detail_view_with_multipk_relation(client: TestClient) -> None:
    base_content()
    response = client.get("/admin/review-complaint/details/1")
    assert "Review by 1 for 1" in response.text


def test_delete_selected_multipk(client: TestClient) -> None:
    base_content()
    response = client.delete("/admin/review/delete?pks=1;2,2;2")
    assert response.status_code == 200

    assert client.get("/admin/review/details/1;2").status_code == 404
    assert client.get("/admin/review/details/2;2").status_code == 404
    assert client.get("/admin/review/details/2;1").status_code == 200


def test_query_one_to_many(client: TestClient) -> None:
    base_content()
    # Change name, reassign movie 3 review from user 3 to user 1
    data = {"name": "Jane Doe", "movie_reviews": ["1;1", "1;2", "3;3"]}
    response = client.post("/admin/user/edit/1", data=data)
    assert response.status_code == 200

    assert client.get("/admin/review/details/3;3").status_code == 404

    details_response = client.get("/admin/user/details/1")
    assert "<td>Jane Doe</td>" in details_response.text
    assert "(Review by 1 for 3)" in details_response.text
