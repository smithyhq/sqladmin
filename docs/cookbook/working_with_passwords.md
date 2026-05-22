It's a comment use-case that you have a model
with a `Password` field which needs a custom behaviour.

Let's say you have the following `User` model:

```py
class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    hashed_password: Mapped[str] = mapped_column(String)
```

In this specific case we want the following features to be available in the Admin console:

- We only want `hashed_password` when creating a new `User`, and we want to hide it when editing a `User`.
- When a User is created, the password should be hashed and stored in the `hashed_password` column.

So we define the following `UserAdmin` class for it:

```py
class UserAdmin(ModelView, model=User):
    column_labels = {"hashed_password": "password"}
    form_create_rules = ["name", "hashed_password"]
    form_edit_rules = ["name"]

    async def on_model_change(self, data, model, is_created, request) -> None:
        if is_created:
            # Hash the password before saving into DB !
            data["hashed_password"] = data["hashed_password"] +  "_hashed"

```

So let's see what is happening.

The `column_labels` is just saying to rename `hashed_password` to `password` when displaying or creating a form for the `User`.

Next we have defined two extra attributes called `form_create_rules` and `form_edit_rules` which
controls how the create and edit forms are created.

In the `form_create_rules` declaration we specify we want `name` and `hashed_password` when creating a `User`.

But in `form_edit_rules` we specifically excluded `hashed_password` so we only want to edit `name` of the `User`.

And finally the last step is to hash the password before saving into the database.
There could be a few options to do this, but in this case we are overriding `on_model_change` and only hashing the password
when we are creating a `User`.
