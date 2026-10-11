import asyncio
import json

import pytest
from sqlalchemy import Column, Integer, String, create_engine, select
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.testclient import TestClient

from sqladmin import Admin, ModelView

Base = declarative_base()


class TransactionUser(Base):
    __tablename__ = "transaction_user"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)


@pytest.mark.parametrize("is_async", [False, True], ids=["sync", "async"])
@pytest.mark.parametrize("failure", ["constraint", "hook"])
@pytest.mark.parametrize("continue_on_error", [False, True], ids=["strict", "continue"])
def test_import_failure_preserves_transaction_contract(
    tmp_path, is_async: bool, failure: str, continue_on_error: bool
) -> None:
    database = tmp_path / "import-test.db"
    sync_engine = create_engine(f"sqlite:///{database}")
    Base.metadata.create_all(sync_engine)
    sessions = sessionmaker(bind=sync_engine)
    with sessions() as session:
        session.add(TransactionUser(name="Existing", email="existing@example.com"))
        session.commit()

    engine = (
        create_async_engine(f"sqlite+aiosqlite:///{database}")
        if is_async
        else sync_engine
    )

    class TransactionUserAdmin(ModelView, model=TransactionUser):
        can_import = True
        column_import_list = [TransactionUser.name, TransactionUser.email]

        async def on_import_row(self, data: dict, model, request: Request) -> None:
            if failure == "hook" and data["name"] == "Rejected":
                raise ValueError("Rejected by import hook")

    app = Starlette()
    admin = Admin(app, engine)
    admin.add_view(TransactionUserAdmin)
    csv_content = (
        b"name,email\r\n"
        b"First,first@example.com\r\n"
        b"Rejected,first@example.com\r\n"
        b"Last,last@example.com\r\n"
    )

    try:
        with TestClient(app) as client:
            response = client.post(
                "/admin/transaction-user/import",
                data={"continue_on_error": "1" if continue_on_error else "0"},
                files={"csvfile": ("users.csv", csv_content, "text/csv")},
            )
        assert response.status_code == 200
        result = json.loads(response.text.splitlines()[-1])
        assert result["ok"] is continue_on_error
        assert result["imported"] == (2 if continue_on_error else 0)
        assert result["missed_rows"][0]["line"] == 3
        with sessions() as session:
            names = session.scalars(
                select(TransactionUser.name).order_by(TransactionUser.id)
            ).all()
        assert names == (
            ["Existing", "First", "Last"] if continue_on_error else ["Existing"]
        )
    finally:
        if is_async:
            asyncio.run(engine.dispose())
        sync_engine.dispose()
