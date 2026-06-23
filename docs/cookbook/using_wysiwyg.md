# Using rich text editor

SQLAdmin ships with rich text editor (WYSIWYG) fields that you can drop onto
any `Text` column using the standard `form_overrides` and `form_args`
mechanism. The editor's assets are loaded automatically, and a library used by
several fields is only loaded once.

## Quick start

```python
from sqladmin import ModelView
from sqladmin.editors import CKEditor5Field

class PostAdmin(ModelView, model=Post):
    form_overrides = {"content": CKEditor5Field}
```

The `content` field now uses CKEditor 5 on both the create and edit pages.

## Configuring an editor

Pass options through `form_args`, exactly as you would for any other field:

```python
from sqladmin.editors import CKEditor5Field

class PostAdmin(ModelView, model=Post):
    form_overrides = {"content": CKEditor5Field}
    form_args = {"content": {"min_height": 300}}
```

## Available editors

SQLAdmin includes four editor fields.

### CKEditor 5

No API key required.

```python
from sqladmin.editors import CKEditor5Field

class PostAdmin(ModelView, model=Post):
    form_overrides = {"content": CKEditor5Field}
    form_args = {"content": {"version": "39.0.1", "min_height": 300}}
```

### TinyMCE

Requires a free API key from [tiny.cloud](https://www.tiny.cloud/auth/signup/).

```python
from sqladmin.editors import TinyMCEField

class PostAdmin(ModelView, model=Post):
    form_overrides = {"content": TinyMCEField}
    form_args = {
        "content": {
            "api_key": "your-api-key",
            "plugins": "lists link table code",
            "toolbar": "bold italic | link | code",
        }
    }
```

### Quill

No API key required.

```python
from sqladmin.editors import QuillField

class PostAdmin(ModelView, model=Post):
    form_overrides = {"content": QuillField}
    form_args = {"content": {"theme": "snow"}}
```

### Summernote

No API key required. Built on Bootstrap 4, so it matches the admin interface.
Requires jQuery, which is loaded automatically unless you disable it.

```python
from sqladmin.editors import SummernoteField

class PostAdmin(ModelView, model=Post):
    form_overrides = {"content": SummernoteField}
    form_args = {"content": {"min_height": 300}}
```

If jQuery is already loaded in your project:

```python
form_args = {"content": {"include_jquery": False}}
```

## Multiple fields

Use different editors on the same form. Each library is loaded only once even
when several fields share it:

```python
from sqladmin.editors import CKEditor5Field, TinyMCEField

class PostAdmin(ModelView, model=Post):
    form_overrides = {
        "content": CKEditor5Field,
        "summary": TinyMCEField,
    }
    form_args = {
        "content": {"min_height": 300},
        "summary": {"api_key": "your-key"},
    }
```

## Pinning a version

Editors load their assets from a CDN, so you can pin whichever version you
want:

```python
form_args = {"content": {"version": "43.0.0"}}
```

## How asset loading works

Each editor field exposes a `media` property listing its CSS and JS URLs.
On the create and edit pages, SQLAdmin merges the media of every field
(deduplicating shared libraries) and injects the CSS in `<head>` and the JS
before `</body>`. Each field also renders a small init script that wires the
editor to its textarea.

## Writing a custom editor

A rich text editor is just a `TextAreaField` that declares its assets and an
init template:

```python
from sqladmin.editors import FieldMedia
from wtforms.fields import TextAreaField

class MyEditorField(TextAreaField):
    editor_init_template = "myapp/editors/my_editor.html"

    def __init__(self, *args, min_height: int = 200, **kwargs):
        self.min_height = min_height
        super().__init__(*args, **kwargs)

    @property
    def media(self) -> FieldMedia:
        return FieldMedia(
            css=["https://example.com/my-editor.css"],
            js=["https://example.com/my-editor.js"],
        )
```

The init template receives the field instance as `field`:

```html
<!-- myapp/editors/my_editor.html -->
<script>
  (function () {
    var el = document.getElementById("{{ field.id }}");
    if (el) {
      MyEditor.create(el, { minHeight: {{ field.min_height }} });
    }
  })();
</script>
```

Use it like any built-in editor:

```python
class PostAdmin(ModelView, model=Post):
    form_overrides = {"content": MyEditorField}
```