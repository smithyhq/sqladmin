# Working with Files and Images

You can use [fastapi-storages](https://github.com/smithyhq/fastapi-storages) package
to make file management easy in `SQLAdmin`.

Right now `fastapi-storages` provides two storage backends:

- `FileSystemStorage` for storing files in local file system.
- `S3Storage` for storing files in Amazon S3 or S3-compatible storages.

It also includes custom SQLAlchemy types to make it easier to integrate into `SQLAdmin`:

- `FileType`
- `ImageType`

Let's see a minimal example:

```python
from fastapi import FastAPI
from sqladmin import Admin, ModelView
from sqlalchemy import Column, Integer, create_engine
from sqlalchemy.orm import declarative_base
from fastapi_storages import FileSystemStorage
from fastapi_storages.integrations.sqlalchemy import FileType


Base = declarative_base()
engine = create_engine("sqlite:///example.db")
app = FastAPI()
admin = Admin(app, engine)
storage = FileSystemStorage(path="/tmp")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)    
    file = Column(FileType(storage=storage))


class UserAdmin(ModelView, model=User):
    column_list = [User.id, User.file]


Base.metadata.create_all(engine)  # Create tables

admin.add_view(UserAdmin)
```

First we define a `FileSystemStorage(path="/tmp")` and configure it to use our local `/tmp` directory for file uploads.
Then we define a custom field called `file` in our model using the `FileType` and our storage.

Now visiting `/admin/user` to create a new User,
there's an HTML file field to upload files form local.
After creating the file you will see that the file name is stored in the database
and displayed in the admin dashboard.

You can replace `FileSystemStorage` with `S3Storage` to upload to S3 or any S3-compatible API.

For complete features and API reference of the `fastapi-storages` you can visit the docs at [https://smithyhq.github.io/fastapi-storages](https://smithyhq.github.io/fastapi-storages).
