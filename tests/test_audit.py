import logging
from collections.abc import Generator

import pytest
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import declarative_base, sessionmaker
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.testclient import TestClient

from sqladmin import Admin, ModelView
from sqladmin.audit import (
    AuditBackend,
    AuditEntry,
    DBAuditBackend,
    LoggingAuditBackend,
    NullAuditBackend,
)
from tests.common import sync_engine as engine

Base = declarative_base()
session_maker = sessionmaker(bind=engine)


class AuditThing(Base):
    __tablename__ = "audit_things"

    id = Column(Integer, primary_key=True)
    name = Column(String(50))


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    action = Column(String(20))
    identity = Column(String(50))
    object_pk = Column(String(50), nullable=True)
    actor = Column(String(50), nullable=True)


class AuditThingAdmin(ModelView, model=AuditThing):
    column_list = [AuditThing.id, AuditThing.name]


@pytest.fixture(autouse=True)
def prepare() -> Generator[None, None, None]:
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


class RecordingBackend(AuditBackend):
    def __init__(self) -> None:
        self.entries: list[AuditEntry] = []

    async def log(self, entry: AuditEntry, request: Request) -> None:
        self.entries.append(entry)


def _client(admin: Admin) -> TestClient:
    return TestClient(app=admin.app, base_url="http://testserver")


def test_default_backend_is_null() -> None:
    admin = Admin(app=Starlette(), engine=engine)
    assert isinstance(admin.audit_backend, NullAuditBackend)


def test_null_backend_does_not_break_crud() -> None:
    admin = Admin(app=Starlette(), engine=engine)
    admin.add_view(AuditThingAdmin)
    with _client(admin) as c:
        response = c.post("/admin/audit-thing/create", data={"name": "x"})
    assert response.status_code in (200, 302)


def test_recording_backend_captures_crud() -> None:
    backend = RecordingBackend()
    admin = Admin(app=Starlette(), engine=engine, audit_backend=backend)
    admin.add_view(AuditThingAdmin)

    with _client(admin) as c:
        c.post("/admin/audit-thing/create", data={"name": "alpha"})
        c.post("/admin/audit-thing/edit/1", data={"name": "beta"})
        c.delete("/admin/audit-thing/delete?pks=1")

    assert [e.action for e in backend.entries] == ["create", "update", "delete"]
    create_entry = backend.entries[0]
    assert create_entry.identity == "audit-thing"
    assert create_entry.pk == "1"
    assert create_entry.changes is not None
    assert create_entry.changes.get("name") == "alpha"
    assert backend.entries[2].changes is None  # delete carries no changes


def test_logging_backend_emits_record() -> None:
    admin = Admin(app=Starlette(), engine=engine, audit_backend=LoggingAuditBackend())
    admin.add_view(AuditThingAdmin)

    records: list[logging.LogRecord] = []

    class _Handler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _Handler()
    audit_logger = logging.getLogger("sqladmin.audit")
    audit_logger.addHandler(handler)
    audit_logger.setLevel(logging.INFO)
    try:
        with _client(admin) as c:
            c.post("/admin/audit-thing/create", data={"name": "log-me"})
    finally:
        audit_logger.removeHandler(handler)

    assert any("action=create" in r.getMessage() for r in records)


def test_db_backend_persists_row() -> None:
    class MyDBBackend(DBAuditBackend):
        async def get_actor(self, request: Request) -> str:
            return "tester"

        def build_row(self, entry: AuditEntry, actor: object, request: Request):
            return AuditLog(
                action=entry.action,
                identity=entry.identity,
                object_pk=entry.pk,
                actor=actor,
            )

    admin = Admin(
        app=Starlette(), engine=engine, audit_backend=MyDBBackend(session_maker)
    )
    admin.add_view(AuditThingAdmin)

    with _client(admin) as c:
        c.post("/admin/audit-thing/create", data={"name": "persisted"})

    with session_maker() as s:
        logs = s.query(AuditLog).all()

    assert len(logs) == 1
    assert logs[0].action == "create"
    assert logs[0].identity == "audit-thing"
    assert logs[0].object_pk == "1"
    assert logs[0].actor == "tester"
