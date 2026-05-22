You can customize the templates and add custom javascript code to enable CKEditor to your fields.
In order to use `CKEditor` you need to inject some JS code into the SQLAdmin and that works by customizing the templates.

Let's say you have the following model:

```py
class Post(Base):
    id = Column(Integer, primary_key=True)
    content = Column(Text, nullable=False)
```

- First create a `templates/sqladmin` directory in your project.
- Then add a file `custom_edit.html` there with the following content:
```html title="custom_edit.html"
{% extends "sqladmin/edit.html" %}
{% block tail %}
<script src="https://cdn.ckeditor.com/ckeditor5/39.0.1/classic/ckeditor.js"></script>
<script>
    ClassicEditor
        .create(document.querySelector('#content'))
        .catch(error => {
            console.error(error);
        });
</script>
{% endblock %}
```

- Use the `custom_edit.html` template in your admin:

```py
class PostAdmin(ModelView, model=Post):
    edit_template = "custom_edit.html"
```

Now whenever editing a Post object in admin, the CKEditor will be applied to the `content` field of the model.
You can do the same thing with `create_template` field.
