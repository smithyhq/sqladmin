import logging
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Column, Integer, String, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from starlette.applications import Starlette
from starlette.requests import Request

from sqladmin import Admin, ModelView
from sqladmin.audit import (
    AuditBackend,
    AuditEntry,
    DBAuditBackend,
    LoggingAuditBackend,
    NullAuditBackend,
)
from tests.common import async_engine

pytestmark = pytest.mark.anyio

Base = declarative_base()
async_session_maker = async_sessionmaker(
    bind=async_engine, class_=AsyncSession, expire_on_commit=False
)


class AuditThing(Base):
    __tablename__ = "audit_things_async"

    id = Column(Integer, primary_key=True)
    name = Column(String(50))


class AuditLog(Base):
    __tablename__ = "audit_logs_async"

    id = Column(Integer, primary_key=True)
    action = Column(String(20))
    identity = Column(String(50))
    object_pk = Column(String(50), nullable=True)
    actor = Column(String(50), nullable=True)


class AuditThingAdmin(ModelView, model=AuditThing):
    column_list = [AuditThing.id, AuditThing.name]


class RecordingBackend(AuditBackend):
    def __init__(self) -> None:
        self.entries: list[AuditEntry] = []

    async def log(self, entry: AuditEntry, request: Request) -> None:
        self.entries.append(entry)


@pytest.fixture(autouse=True)
async def prepare_database() -> AsyncGenerator[None, None]:
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    # conftest scopes the anyio backend per module, so each test module runs on its
    # own event loop while async_engine is shared process-wide. Pooled connections
    # stay bound to the loop that opened them, and asyncpg raises "attached to a
    # different loop" when a later module picks one up. Disposing drops the pool so
    # the next loop gets fresh connections. SQLite/aiosqlite tolerates this; the
    # Postgres CI matrix does not.
    await async_engine.dispose()


async def test_null_backend_does_not_break_crud() -> None:
    admin = Admin(app=Starlette(), engine=async_engine)
    admin.add_view(AuditThingAdmin)

    assert isinstance(admin.audit_backend, NullAuditBackend)

    transport = ASGITransport(app=admin.app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/admin/audit-thing/create", data={"name": "x"})
        assert response.status_code == 302

    async with async_session_maker() as s:
        things = (await s.scalars(select(AuditThing))).all()
    assert [t.name for t in things] == ["x"]


async def test_recording_backend_captures_crud() -> None:
    backend = RecordingBackend()
    admin = Admin(app=Starlette(), engine=async_engine, audit_backend=backend)
    admin.add_view(AuditThingAdmin)

    transport = ASGITransport(app=admin.app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        await c.post("/admin/audit-thing/create", data={"name": "alpha"})
        await c.post("/admin/audit-thing/edit/1", data={"name": "beta"})
        await c.delete("/admin/audit-thing/delete?pks=1")

    assert [e.action for e in backend.entries] == ["create", "update", "delete"]
    create_entry = backend.entries[0]
    assert create_entry.identity == "audit-thing"
    assert create_entry.pk == "1"
    assert create_entry.changes is not None
    assert create_entry.changes.get("name") == "alpha"
    assert backend.entries[2].changes is None  # delete carries no changes


async def test_logging_backend_emits_record() -> None:
    admin = Admin(
        app=Starlette(), engine=async_engine, audit_backend=LoggingAuditBackend()
    )
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
        transport = ASGITransport(app=admin.app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as c:
            await c.post("/admin/audit-thing/create", data={"name": "log-me"})
    finally:
        audit_logger.removeHandler(handler)

    assert any("action=create" in r.getMessage() for r in records)


async def test_db_backend_get_actor_admin() -> None:
    class MyDBBackend(DBAuditBackend):
        async def get_actor(self, request: Request) -> str:
            return "admin"

        def build_row(self, entry: AuditEntry, actor: object, request: Request):
            return AuditLog(
                action=entry.action,
                identity=entry.identity,
                object_pk=entry.pk,
                actor=actor,
            )

    admin = Admin(
        app=Starlette(),
        engine=async_engine,
        audit_backend=MyDBBackend(async_session_maker),
    )
    admin.add_view(AuditThingAdmin)

    transport = ASGITransport(app=admin.app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        await client.post("/admin/audit-thing/create", data={"name": "persisted"})

        async with async_session_maker() as s:
            logs = (await s.scalars(select(AuditLog))).all()

            assert len(logs) == 1
            assert logs[0].action == "create"
            assert logs[0].identity == "audit-thing"
            assert logs[0].object_pk == "1"
            assert logs[0].actor == "admin"


async def test_db_backend_get_actor_not_override() -> None:
    class MyDBBackend(DBAuditBackend):
        def build_row(self, entry: AuditEntry, actor: object, request: Request):
            return AuditLog(
                action=entry.action,
                identity=entry.identity,
                object_pk=entry.pk,
                actor=actor,
            )

    admin = Admin(
        app=Starlette(),
        engine=async_engine,
        audit_backend=MyDBBackend(async_session_maker),
    )
    admin.add_view(AuditThingAdmin)

    transport = ASGITransport(app=admin.app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        await client.post("/admin/audit-thing/create", data={"name": "persisted"})

        async with async_session_maker() as s:
            logs = (await s.scalars(select(AuditLog))).all()

            assert len(logs) == 1
            assert logs[0].action == "create"
            assert logs[0].identity == "audit-thing"
            assert logs[0].object_pk == "1"
            assert logs[0].actor is None
