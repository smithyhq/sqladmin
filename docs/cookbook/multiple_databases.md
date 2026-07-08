SQLAlchemy offers some partitioning strategies to use multiple databases per session.
An example from the SQLAlchemy docs is:

```py
from sqlalchemy.orm.session import sessionmaker, Session

engine1 = create_engine("postgresql+psycopg://db1")
engine2 = create_engine("postgresql+psycopg://db2")

Session = sessionmaker()

# bind User operations to engine 1, Account operations to engine 2
Session.configure(binds={User: engine1, Account: engine2})
```

With this `Session` the `User` table will be in engine1
and `Account` will be in engine2.

And when instantiating the `Admin` object you can use the `sessionmaker` factory you have:

```py
from sqladmin import Admin


admin = Admin(app=app, session_maker=Session)
admin.add_view(...)
```

This is different from other places where you could just use `engine` argument,
and now you can use the `sessionmaker` factory.

!!! tip
    In addition to being useful for partitioning, you could use the `sessionmaker` factory
    instead of the `engine` if you have one database for your application, SQLAdmin internally
    creates a `sessionmaker` for your `engine` but if you pass the `sessionmaker` you can keep
    any configuration you have on your sessions.
