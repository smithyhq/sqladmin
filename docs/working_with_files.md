# Working with Files and Images

You can use [fastapi-storages](https://github.com/smithyhq/fastapi-storages) package
to make file management easy in `SQLAdmin`.

Right now `fastapi-storages` provides two storage backends:

- `FileSystemStorage` for storing files in local file system.
- `S3Storage` for storing files in Amazon S3 or S3-compatible storages.

It also includes custom SQLAlchemy types to make it easier to integrate into `SQLAdmin`:

- `FileType`
- `ImageType`

File upload and download links are **opt-in**. Enable them explicitly on your `ModelView`
with `form_overrides` and `column_formatters`.

## Local files (upload + admin download links)

```python
from fastapi import FastAPI
from sqladmin import Admin, ModelView
from sqladmin.fields import FileField, file_display_formatter
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
    form_overrides = {User.file: FileField}
    column_formatters = {User.file: file_display_formatter}
    column_formatters_detail = {User.file: file_display_formatter}


Base.metadata.create_all(engine)  # Create tables

admin.add_view(UserAdmin)
```

- **`FileField`** — file input on create/edit forms (not applied automatically).
- **`file_display_formatter`** — view/download links on list and detail pages for local files.

## CDN or remote URLs

Store a URL string in the database and use **`CDNURLField`** for the form plus the same
display formatter:

```python
from sqlalchemy import Column, Integer, String
from sqladmin.fields import CDNURLField, file_display_formatter


class Asset(Base):
    __tablename__ = "assets"

    id = Column(Integer, primary_key=True)
    url = Column(String, nullable=False)


class AssetAdmin(ModelView, model=Asset):
    column_list = [Asset.id, Asset.url]
    form_overrides = {Asset.url: CDNURLField}
    column_formatters = {Asset.url: file_display_formatter}
    column_formatters_detail = {Asset.url: file_display_formatter}
```

Remote `http://` / `https://` values are rendered as external links. Local filesystem
paths use the admin `file_read` / `file_download` routes.

For complete features and API reference of the `fastapi-storages` you can visit the docs at [https://smithyhq.github.io/fastapi-storages](https://smithyhq.github.io/fastapi-storages).
