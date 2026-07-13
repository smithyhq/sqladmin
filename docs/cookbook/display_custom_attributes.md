If you need to display a custom attribute of your model,
or a calculated attribute or property which is not directly from the database,
it is possible out of the box with `SQLAdmin`.

Let's see an example model:

```py
class User(Base):
    __tablename__ = "user"

    id = mapped_column(Integer, primary_key=True)
    first_name = mapped_column(String)
    last_name = mapped_column(String)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"
```

And in order to for example show the `full_name` property in the
admin, you can just use the `full_name` just like other string model properties.

For example:

```py
class UserAdmin(ModelView, model=User):
    column_list = [User.id, "full_name"]
    column_details_list = [User.id, "full_name"]
```
