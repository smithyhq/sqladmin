# Using rich text editor

SQLAdmin has built-in support for rich text editors (WYSIWYG) on your model
fields. Set the `rich_text_fields` attribute on your `ModelView` and the editor
is automatically loaded on the create and edit pages — no custom templates
required.

Only fields backed by a `Text` or `UnicodeText` SQLAlchemy column are supported,
as these render as `<textarea>` elements. Using a `String` (or any other) column
raises a `ValueError`.

## Quick start

Let's say you have the following model:

```python
class Post(Base):
    id = Column(Integer, primary_key=True)
    title = Column(String(100))
    content = Column(Text)
    summary = Column(Text)
```

Add `rich_text_fields` to your `ModelView`:

```python
class PostAdmin(ModelView, model=Post):
    rich_text_fields = ["content", "summary"]
```

That's it. The `content` and `summary` fields now use CKEditor 5 on both the
create and edit pages.

## Choosing an editor

When `rich_text_fields` is a list, all fields use the default `CKEditor5`. To
use a different editor, or a different editor per field, pass a dictionary
mapping each field name to an editor instance:

```python
from sqladmin.editors import CKEditor5, TinyMCE, QuillEditor, Summernote

class PostAdmin(ModelView, model=Post):
    rich_text_fields = {
        "content": CKEditor5(min_height=300),
        "summary": TinyMCE(api_key="your-api-key"),
    }
```

SQLAdmin ships with four built-in editors.

### CKEditor 5

The default editor. No API key required.

```python
from sqladmin.editors import CKEditor5

class PostAdmin(ModelView, model=Post):
    rich_text_fields = {"content": CKEditor5(version="39.0.1", min_height=300)}
```

### TinyMCE

Requires a free API key from [tiny.cloud](https://www.tiny.cloud/auth/signup/).

```python
from sqladmin.editors import TinyMCE

class PostAdmin(ModelView, model=Post):
    rich_text_fields = {
        "content": TinyMCE(
            api_key="your-api-key",
            plugins="lists link table code",
            toolbar="bold italic | link | code",
        )
    }
```

### Quill

No API key required. Quill renders into a `div`; SQLAdmin hides the original
textarea and syncs the content back to it on form submit.

```python
from sqladmin.editors import QuillEditor

class PostAdmin(ModelView, model=Post):
    rich_text_fields = {"content": QuillEditor(theme="snow")}
```

### Summernote

No API key required. Built on Bootstrap 4, so it matches the admin interface.
Requires jQuery, which is loaded automatically unless you disable it.

```python
from sqladmin.editors import Summernote

class PostAdmin(ModelView, model=Post):
    rich_text_fields = {"content": Summernote(height=300)}
```

If jQuery is already loaded in your project, avoid loading it twice:

```python
rich_text_fields = {"content": Summernote(include_jquery=False)}
```

## Sharing an editor instance

When several fields use the same editor *instance*, the editor's CDN assets are
loaded only once:

```python
editor = CKEditor5(min_height=300)

class PostAdmin(ModelView, model=Post):
    rich_text_fields = {"content": editor, "summary": editor}
```

If you pass two separate instances instead, each field keeps its own
configuration while the shared library is still loaded only once.

## Writing a custom editor

To integrate an editor that isn't built in, subclass `RichTextEditor` and
provide a `template_name`, the `scripts` to load, and a `get_context()` method.

```python
from sqladmin.editors import RichTextEditor

class MyEditor(RichTextEditor):
    template_name = "myapp/editors/my_editor.html"

    @property
    def scripts(self) -> list[str]:
        return ["https://example.com/my-editor.js"]

    @property
    def styles(self) -> list[str]:
        return ["https://example.com/my-editor.css"]

    def get_context(self) -> dict:
        return {"min_height": 200}
```

Then create the template. It receives `field_ids` (the list of field names) and
`editor` (your instance) in its context:

```html
<!-- myapp/editors/my_editor.html -->
<script>
  document.addEventListener("DOMContentLoaded", function () {
    var fieldIds = {{ field_ids | tojson }};
    fieldIds.forEach(function (fieldId) {
      var el = document.querySelector("#" + fieldId);
      if (el) {
        MyEditor.create(el, { minHeight: {{ editor.get_context().min_height }} });
      }
    });
  });
</script>
```

Use it like any built-in editor:

```python
class PostAdmin(ModelView, model=Post):
    rich_text_fields = {"content": MyEditor()}
```

## Customizing templates manually

If you need full control, you can still inject the editor JavaScript yourself by
customizing the templates, without using `rich_text_fields`.

Add a `custom_edit.html` to your project's `templates/sqladmin` directory:

```html
{% extends "sqladmin/edit.html" %}
{% block tail %}
{{ super() }}
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

Then point your `ModelView` at it:

```python
class PostAdmin(ModelView, model=Post):
    edit_template = "custom_edit.html"
```

You can do the same thing with the `create_template` field.