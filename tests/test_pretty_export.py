import csv
import io
from typing import Any, Optional

import pytest
from sqlalchemy import Boolean, Column, ForeignKey, Integer, String
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from starlette.responses import StreamingResponse

from sqladmin import ModelView
from sqladmin.pretty_export import PrettyExport
from tests.common import sync_engine as engine

pytestmark = pytest.mark.anyio

Base = declarative_base()  # type: ignore
session_maker = sessionmaker(bind=engine)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(String)
    email = Column(String)
    is_active = Column(Boolean, default=True)

    addresses = relationship("Address", back_populates="user")


class Address(Base):
    __tablename__ = "addresses"

    id = Column(Integer, primary_key=True)
    street = Column(String)
    city = Column(String)
    user_id = Column(Integer, ForeignKey("users.id"))

    user = relationship("User", back_populates="addresses")


@pytest.fixture(autouse=True)
def prepare_database():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


class TestPrettyExport:
    async def _get_csv_content(self, response: StreamingResponse) -> str:
        content = []
        async for chunk in response.body_iterator:
            if isinstance(chunk, bytes):
                content.append(chunk.decode("utf-8"))
            else:
                content.append(chunk)
        return "".join(content)

    async def test_get_export_row_values_basic(self):
        class UserAdmin(ModelView, model=User):
            column_list = ["id", "name", "email"]
            session_maker = session_maker
            is_async = False

        user = User(id=1, name="John Doe", email="john@example.com", is_active=True)
        model_view = UserAdmin()
        column_names = ["id", "name", "email"]

        values = await PrettyExport._get_export_row_values(
            model_view, user, column_names
        )

        assert len(values) == 3
        assert values[0] == 1
        assert values[1] == "John Doe"
        assert values[2] == "john@example.com"

    async def test_get_export_row_values_with_custom_export_cell(self):
        class UserAdmin(ModelView, model=User):
            column_list = ["id", "name", "email"]
            session_maker = session_maker
            is_async = False

            async def custom_export_cell(
                self, row: Any, name: str, value: Any
            ) -> Optional[str]:
                if name == "name":
                    return f"Mr. {value}"
                if name == "email":
                    return value.upper()
                return None

        user = User(id=1, name="John Doe", email="john@example.com")
        model_view = UserAdmin()
        column_names = ["id", "name", "email"]

        values = await PrettyExport._get_export_row_values(
            model_view, user, column_names
        )

        assert len(values) == 3
        assert values[0] == 1
        assert values[1] == "Mr. John Doe"
        assert values[2] == "JOHN@EXAMPLE.COM"

    async def test_get_export_row_values_with_base_export_cell(self):
        class UserAdmin(ModelView, model=User):
            column_list = ["id", "name", "is_active"]
            session_maker = session_maker
            is_async = False

        user = User(id=1, name="John Doe", is_active=True)
        model_view = UserAdmin()
        column_names = ["id", "name", "is_active"]

        values = await PrettyExport._get_export_row_values(
            model_view, user, column_names
        )

        assert len(values) == 3
        assert values[0] == 1
        assert values[1] == "John Doe"
        assert values[2] == "TRUE"

    async def test_get_export_row_values_with_none_values(self):
        class UserAdmin(ModelView, model=User):
            column_list = ["id", "name", "email"]
            session_maker = session_maker
            is_async = False

        user = User(id=1, name="John Doe", email=None)
        model_view = UserAdmin()
        column_names = ["id", "name", "email"]

        values = await PrettyExport._get_export_row_values(
            model_view, user, column_names
        )

        assert len(values) == 3
        assert values[0] == 1
        assert values[1] == "John Doe"
        assert values[2] == ""

    async def test_get_export_row_values_with_relationships(self):
        class AddressAdmin(ModelView, model=Address):
            column_list = ["id", "street", "user.name"]
            session_maker = session_maker
            is_async = False

        user = User(id=1, name="John Doe")
        address = Address(id=1, street="123 Main St", user=user)
        model_view = AddressAdmin()
        column_names = ["id", "street", "user.name"]

        values = await PrettyExport._get_export_row_values(
            model_view, address, column_names
        )

        assert len(values) == 3
        assert values[0] == 1
        assert values[1] == "123 Main St"
        assert values[2] == "John Doe"

    async def test_pretty_export_csv_basic(self):
        class UserAdmin(ModelView, model=User):
            column_list = ["id", "name", "email"]
            session_maker = session_maker
            is_async = False

        users = [
            User(id=1, name="John Doe", email="john@example.com"),
            User(id=2, name="Jane Smith", email="jane@example.com"),
        ]
        model_view = UserAdmin()

        response = await PrettyExport.pretty_export_csv(model_view, users)
        assert isinstance(response, StreamingResponse)
        assert response.media_type == "text/csv"
        assert "attachment" in response.headers["Content-Disposition"]
        assert "csv" in response.headers["Content-Disposition"]

        csv_content = await self._get_csv_content(response)
        lines = csv_content.strip().split("\n")
        assert len(lines) == 3

        csv_reader = csv.reader(io.StringIO(csv_content))
        rows = list(csv_reader)
        assert rows[0] == ["id", "name", "email"]
        assert rows[1] == ["1", "John Doe", "john@example.com"]
        assert rows[2] == ["2", "Jane Smith", "jane@example.com"]

    async def test_pretty_export_csv_with_column_labels(self):
        class UserAdmin(ModelView, model=User):
            column_list = ["id", "name", "email"]
            column_labels = {
                "id": "User ID",
                "name": "Full Name",
                "email": "Email Address",
            }
            session_maker = session_maker
            is_async = False

        users = [
            User(id=1, name="John Doe", email="john@example.com"),
        ]
        model_view = UserAdmin()

        response = await PrettyExport.pretty_export_csv(model_view, users)
        csv_content = await self._get_csv_content(response)
        csv_reader = csv.reader(io.StringIO(csv_content))
        rows = list(csv_reader)

        assert rows[0] == ["User ID", "Full Name", "Email Address"]
        assert rows[1] == ["1", "John Doe", "john@example.com"]

    async def test_pretty_export_csv_with_partial_column_labels(self):
        class UserAdmin(ModelView, model=User):
            column_list = ["id", "name", "email"]
            column_labels = {
                "name": "Full Name",
            }
            session_maker = session_maker
            is_async = False

        users = [
            User(id=1, name="John Doe", email="john@example.com"),
        ]
        model_view = UserAdmin()

        response = await PrettyExport.pretty_export_csv(model_view, users)
        csv_content = await self._get_csv_content(response)
        csv_reader = csv.reader(io.StringIO(csv_content))
        rows = list(csv_reader)

        assert rows[0] == ["id", "Full Name", "email"]
        assert rows[1] == ["1", "John Doe", "john@example.com"]

    async def test_pretty_export_csv_with_custom_formatters(self):
        class UserAdmin(ModelView, model=User):
            column_list = ["id", "name", "is_active"]
            column_labels = {"id": "ID", "name": "Name", "is_active": "Active Status"}
            session_maker = session_maker
            is_async = False

            async def custom_export_cell(
                self, row: Any, name: str, value: Any
            ) -> Optional[str]:
                if name == "is_active":
                    return "✓" if value else "✗"
                return None

        users = [
            User(id=1, name="John Doe", is_active=True),
            User(id=2, name="Jane Smith", is_active=False),
        ]
        model_view = UserAdmin()

        response = await PrettyExport.pretty_export_csv(model_view, users)

        csv_content = await self._get_csv_content(response)
        csv_reader = csv.reader(io.StringIO(csv_content))
        rows = list(csv_reader)

        assert rows[0] == ["ID", "Name", "Active Status"]
        assert rows[1] == ["1", "John Doe", "✓"]
        assert rows[2] == ["2", "Jane Smith", "✗"]

    async def test_pretty_export_csv_empty_data(self):
        class UserAdmin(ModelView, model=User):
            column_list = ["id", "name", "email"]
            session_maker = session_maker
            is_async = False

        users = []
        model_view = UserAdmin()

        response = await PrettyExport.pretty_export_csv(model_view, users)

        csv_content = await self._get_csv_content(response)
        lines = csv_content.strip().split("\n")
        assert len(lines) == 1

        csv_reader = csv.reader(io.StringIO(csv_content))
        rows = list(csv_reader)
        assert rows[0] == ["id", "name", "email"]

    async def test_pretty_export_csv_with_export_columns(self):
        class UserAdmin(ModelView, model=User):
            column_list = ["id", "name", "email", "is_active"]
            column_export_list = ["name", "email"]
            session_maker = session_maker
            is_async = False

        users = [
            User(id=1, name="John Doe", email="john@example.com", is_active=True),
        ]
        model_view = UserAdmin()

        response = await PrettyExport.pretty_export_csv(model_view, users)
        csv_content = await self._get_csv_content(response)
        csv_reader = csv.reader(io.StringIO(csv_content))
        rows = list(csv_reader)

        assert rows[0] == ["name", "email"]
        assert rows[1] == ["John Doe", "john@example.com"]

    async def test_pretty_export_csv_integration_with_model_view_export(self):
        class UserAdmin(ModelView, model=User):
            column_list = ["id", "name", "email"]
            use_pretty_export = True
            session_maker = session_maker
            is_async = False

        users = [
            User(id=1, name="John Doe", email="john@example.com"),
        ]
        model_view = UserAdmin()

        response = await model_view.export_data(users, "csv")
        csv_content = await self._get_csv_content(response)
        csv_reader = csv.reader(io.StringIO(csv_content))
        rows = list(csv_reader)

        assert isinstance(response, StreamingResponse)
        assert response.media_type == "text/csv"
        assert rows[0] == ["id", "name", "email"]
        assert rows[1] == ["1", "John Doe", "john@example.com"]

    async def test_pretty_export_csv_filename_generation(self):
        class UserAdmin(ModelView, model=User):
            column_list = ["id", "name"]
            session_maker = session_maker
            is_async = False

            def get_export_name(self, export_type: str) -> str:
                return f"test_export_with_special_chars!@#.{export_type}"

        users = [User(id=1, name="John Doe")]
        model_view = UserAdmin()

        response = await PrettyExport.pretty_export_csv(model_view, users)
        content_disposition = response.headers["Content-Disposition"]

        assert "attachment" in content_disposition
        assert (
            "test_export_with_special_chars.csv" in content_disposition
            or "test_export_with_special_chars_.csv" in content_disposition
        )
