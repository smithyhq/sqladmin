When dealing with any kind of relationship in your models,
be it One-To-Many, Many-To-One or Many-To-Many,
`SQLAdmin` will load related models in your edit page.

For example if we have the following model definition:

```python
class Parent(Base):
    __tablename__ = "parent_table"

    id = mapped_column(Integer, primary_key=True)
    children = relationship("Child", back_populates="parent")


class Child(Base):
    __tablename__ = "child_table"

    id = mapped_column(Integer, primary_key=True)
    parent_id = mapped_column(ForeignKey("parent_table.id"))
    parent = relationship("Parent", back_populates="children")
```

When we are editing a `Parent` object in the Admin,
there will be an HTML `select` option which loads all possible `Child` objects to be selected.

This is fine for small projects, but if you more than a few hundred records in your tables,
it will be very slow and inefficient.
Practically for each request to the Edit page, all records of `Child` table will be loaded.

In order to solve this you can use Form options available in [configuration](./../configurations.md#form-options).

You have a few options to improve this:

### Using `form_ajax_refs`

Instead of loading all the `Child` objects when editing a `Parent` object,
you can use `form_ajax_refs` to load `Child` objects with an AJAX call:

```py
class ParentAdmin(ModelView, model=Parent):
    form_ajax_refs = {
        "children": {
            "fields": ("id",),
            "order_by": "id",
        }
    }
```

This will allow you to search `Child` objects using the `id` field while also ordering the results.

### Using `form_columns` or `form_excluded_columns`

Another option, which is not as useful as the previous one, is that you might not need
the relationship `children` to be edited for your `Pranet` objects.

In that case you can just exclude that or specifically include the columns
which should be available in the form.

```py
class ParentAdmin(ModelView, model=Parent):
    form_excluded_columns = [Parent.children]
```

### Using `form_edit_query` to customize the edit form data

If you would like to fully customize the query to populate the edit object form, you may override
the `form_edit_query` function with your own SQLAlchemy query. In the following example, overriding
the default query will allow you to filter relationships to show only related children of the parent.

```py
class ParentAdmin(ModelView, model=Parent):
    def form_edit_query(self, request: Request) -> Select:
        parent_id = request.path_params["pk"]
        return (
            self._stmt_by_identifier(parent_id)
            .join(Child)
            .options(contains_eager(Parent.children))
            .filter(Child.parent_id == parent_id)
        )
```
