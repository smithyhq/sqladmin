# Audit logging

SQLAdmin can record every create, update and delete made through the admin to
an *audit backend*. Configure one with the `audit_backend` argument of `Admin`.
The default is `NullAuditBackend`, which records nothing, so auditing is fully
opt-in.

Each change is described by a fixed `AuditEntry` dataclass:

```python
@dataclass
class AuditEntry:
    action: str          # "create", "update" or "delete"
    identity: str        # the ModelView identity, e.g. "user"
    pk: str | None       # the affected object's identifier
    changes: dict | None # submitted field values ("None" for deletes)
    timestamp: datetime  # UTC
```

## Logging to your existing log stream

`LoggingAuditBackend` emits each entry through the standard `logging` module,
under the `sqladmin.audit` logger by default:

```python
from sqladmin import Admin
from sqladmin.audit import LoggingAuditBackend

admin = Admin(app, engine, audit_backend=LoggingAuditBackend())
```

## Persisting to your own table

`DBAuditBackend` writes entries to a database table — but SQLAdmin does not ship
an audit model, because the right shape depends on your app, most importantly
the type of your users' primary key (int, str or UUID) and the foreign key to
it. Instead you define the model and subclass the backend, overriding two
methods:

* `get_actor(request)` — map the current request/session to your user's primary
  key (or any actor identifier).
* `build_row(entry, actor, request)` — turn an `AuditEntry` plus the resolved
  actor into an instance of *your* model.

The `AuditEntry` fields never change; only this mapping does.

```python
from sqlalchemy import Column, Integer, String, JSON, DateTime, ForeignKey
from sqladmin import Admin
from sqladmin.audit import DBAuditBackend


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True)
    action = Column(String(20))
    table = Column(String(100))
    object_pk = Column(String(100), nullable=True)
    changes = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True))
    # FK to your own user table; the PK type is entirely yours (int/str/UUID).
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)


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
```

Because the audit log is just one of your own models, you can register it as a
read-only `ModelView` to browse the trail inside the admin with the usual list,
filter and detail pages.

!!! note

    Auditing is best-effort: a backend that raises is logged (to
    `sqladmin.audit`) rather than propagated, so a misconfigured audit backend
    cannot break an already-committed change. The `DBAuditBackend` writes in its
    own transaction, separate from the change it records.

## Writing a custom backend

For anything else — a message queue, an external audit service — subclass
`AuditBackend` directly and implement the single async `log` method:

```python
from sqladmin.audit import AuditBackend


class QueueAuditBackend(AuditBackend):
    async def log(self, entry, request):
        await queue.publish(entry.__dict__)
```
