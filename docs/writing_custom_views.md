### Basic example

You might need to add custom views to the existing SQLAdmin views, for example to create dashboards, show custom info or add new forms.

To add custom views to the Admin interface, you can use the `BaseView` included in SQLAdmin. Here's an example to add custom views:

!!! example

    ```python
    from sqladmin import BaseView, expose

    class ReportView(BaseView):
        name = "Report Page"
        icon = "fa-solid fa-chart-line"

        @expose("/report", methods=["GET"])
        async def report_page(self, request):
            return await self.templates.TemplateResponse(request, "report.html")

    admin.add_view(ReportView)
    ```

This will assume there's a `templates` directory in your project and you have created a `report.html` in that directory.

If you want to use a custom directory name, you can change that with:

```python
from sqladmin import Admin

admin = Admin(templates_dir="my_templates", ...)
```

Now visiting `/admin/report` you can render your `report.html` file.

It is also possible to use the expose decorator to add extra endpoints to a ModelView. 
The `path` is in this case prepended with the view's identity, in this case `/admin/user/profile/{pk}`.

!!! example

    ```python
    from sqladmin import ModelView, expose

    class UserView(ModelView):

        @expose("/profile/{pk}", methods=["GET"])
        async def profile(self, request):
            user: User = await self.get_object_for_edit(request)
            return await self.templates.TemplateResponse(
                request, "user.html", {"user": user}
            )

    admin.add_view(UserView)
    ```

### Database access

The example above was very basic and you probably want to access database and SQLAlchemy models in your custom view. You can use `sessionmaker` the same way SQLAdmin is using it to do so:

!!! example

    ```python
    from sqlalchemy import Column, Integer, String, select, func
    from sqlalchemy.orm import sessionmaker, declarative_base
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqladmin import Admin, BaseView, expose
    from starlette.applications import Starlette

    Base = declarative_base()
    engine = create_async_engine("sqlite+aiosqlite:///test.db")
    Session = sessionmaker(bind=engine, class_=AsyncSession)

    app = Starlette()
    admin = Admin(app=app, engine=engine)


    class User(Base):
        __tablename__ = "users"

        id = Column(Integer, primary_key=True)
        name = Column(String(length=16))


    class ReportView(BaseView):
        name = "Report Page"
        icon = "fa-solid fa-chart-line"

        @expose("/report", methods=["GET"])
        async def report_page(self, request):
            # async with engine.begin() as conn:
            #     await conn.run_sync(Base.metadata.create_all)

            async with Session(expire_on_commit=False) as session:
                stmt = select(func.count(User.id))
                result = await session.execute(stmt)
                users_count = result.scalar_one()

            return await self.templates.TemplateResponse(
                request,
                "report.html",
                context={"users_count": users_count},
            )


    admin.add_view(ReportView)

    ```

Next we update the `report.html` file in the `templates` directory with the following content:

!!! example
    ```html
    {% extends "sqladmin/layout.html" %}
    {% block content %}
    <div class="col-12">
    <div class="card">
        <div class="card-header">
        <h3 class="card-title">User reports</h3>
        </div>
        <div class="card-body border-bottom py-3">
        Users count: {{ users_count }}
        </div>
    </div>
    </div>
    {% endblock %}
    ```

Now running your server you can head to `/admin/report` and you can see the number of users.
