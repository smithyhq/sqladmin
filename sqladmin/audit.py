from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqladmin.helpers import is_async_session_maker

if TYPE_CHECKING:
    from starlette.requests import Request

__all__ = [
    "AuditEntry",
    "AuditBackend",
    "NullAuditBackend",
    "LoggingAuditBackend",
    "DBAuditBackend",
]


@dataclass
class AuditEntry:
    """A single audited change.

    The set of fields is intentionally fixed -- storage backends map it onto
    whatever model or columns they use, rather than the shape changing per app.
    """

    action: str
    """The change type: ``"create"``, ``"update"`` or ``"delete"``."""

    identity: str
    """The ``ModelView.identity`` the change happened on."""

    pk: str | None = None
    """The affected object's identifier, if known."""

    changes: dict[str, Any] | None = None
    """The submitted field values for the change (``None`` for deletes)."""

    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    """When the change happened, in UTC."""


class AuditBackend(ABC):
    """Strategy for recording :class:`AuditEntry` objects.

    Configure one on ``Admin(audit_backend=...)``. The default is
    :class:`NullAuditBackend`, which records nothing.
    """

    @abstractmethod
    async def log(
        self, entry: AuditEntry, request: Request
    ) -> None: ...  # pragma: no cover


class NullAuditBackend(AuditBackend):
    """The default backend: records nothing."""

    async def log(self, entry: AuditEntry, request: Request) -> None:
        return None


class LoggingAuditBackend(AuditBackend):
    """Emit each entry through the standard :mod:`logging` module.

    Useful when you already ship logs somewhere and just want the audit trail
    in that same stream. The logger name defaults to ``"sqladmin.audit"``.
    """

    def __init__(
        self,
        logger_name: str = "sqladmin.audit",
        level: int = logging.INFO,
    ) -> None:
        self.logger = logging.getLogger(logger_name)
        self.level = level

    async def log(self, entry: AuditEntry, request: Request) -> None:
        self.logger.log(
            self.level,
            "audit action=%s identity=%s pk=%s changes=%s",
            entry.action,
            entry.identity,
            entry.pk,
            entry.changes,
        )


class DBAuditBackend(AuditBackend):
    """Persist entries to a database table that you define.

    SQLAdmin does not ship an audit model, because the right shape depends on
    your app -- most importantly the type of your users' primary key (int, str
    or UUID) and the foreign key to it. Instead you subclass this backend and:

    * override :meth:`build_row` to turn an :class:`AuditEntry` (plus the
      resolved actor) into an instance of *your* model, and
    * override :meth:`get_actor` to map the current request/session to your
      user's primary key (or any actor identifier).

    The :class:`AuditEntry` fields never change; only the mapping to your
    storage does.

    Example::

        class MyAuditBackend(DBAuditBackend):
            async def get_actor(self, request):
                return request.session.get("user_id")

            def build_row(self, entry, actor, request):
                return AuditLog(
                    action=entry.action,
                    table=entry.identity,
                    object_pk=entry.pk,
                    changes=entry.changes,
                    created_at=entry.timestamp,
                    user_id=actor,
                )

        admin = Admin(app, engine, audit_backend=MyAuditBackend(session_maker))
    """

    def __init__(self, session_maker: Any) -> None:
        self.session_maker = session_maker
        self.is_async = is_async_session_maker(session_maker)

    async def get_actor(self, request: Request) -> Any:
        """Resolve the actor (e.g. your user's PK) for this request.

        Override to read your authentication/session. Returns ``None`` by
        default. This value is passed to :meth:`build_row`
        to be stored in the audit model.
        """
        return None

    def build_row(self, entry: AuditEntry, actor: Any, request: Request) -> Any:
        """Return an instance of your audit model for ``entry``.

        Must be overridden by subclasses. This method is called with the actor value
        returned by :meth:`get_actor`.
        """
        raise NotImplementedError(
            "Subclasses of DBAuditBackend must implement build_row()."
        )

    async def log(self, entry: AuditEntry, request: Request) -> None:
        actor = await self.get_actor(request)
        row = self.build_row(entry, actor, request)

        if self.is_async:
            async with self.session_maker() as session:
                session.add(row)
                await session.commit()
        else:
            import anyio

            await anyio.to_thread.run_sync(self._persist_sync, row)

    def _persist_sync(self, row: Any) -> None:
        with self.session_maker() as session:
            session.add(row)
            session.commit()
