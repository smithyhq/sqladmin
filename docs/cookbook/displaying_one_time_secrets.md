# Displaying one-time secrets

A common pattern in admin panels is generating a secret (API key, tokens, etc.)
that is shown **once** right after creation and never again.

## The problem

By default, `after_model_change` returns `None` and the create handler always
issues a `302` redirect. There is no way to stay on the page and display
extra information after a successful create.

## The solution

Return a `dict` from `after_model_change` on create. The dict is merged into
the template context and the create template is re-rendered with a `200`
status instead of redirecting.

### 1. Override the ModelView

```python
import secrets
from sqladmin import ModelView

class ApiKeyAdmin(ModelView, model=ApiKey):
    # Point to your custom template
    create_template = "create_api_key.html"

    async def after_model_change(self, data, model, is_created, request):
        if is_created:
            # Generate the raw secret, store only the hash in the DB
            raw_secret = secrets.token_urlsafe(32)
            return {"secret": raw_secret}
        # On edit, redirect as usual
        return None
```

### 2. Create a custom template

Create `templates/create_api_key.html` (or wherever your `templates_dir`
points):

```html
{% extends "sqladmin/create.html" %}

{% block content %}
  {% if secret %}
    <div class="alert alert-success">
      <h4>Your API key was created successfully!</h4>
      <p>Copy your secret now — it will not be shown again:</p>
      <div class="input-group mb-3">
        <input type="text" class="form-control" value="{{ secret }}" readonly id="secret-value">
        <button class="btn btn-outline-secondary" type="button"
                onclick="navigator.clipboard.writeText(document.getElementById('secret-value').value)">
          Copy
        </button>
      </div>
    </div>
  {% else %}
    {{ super() }}
  {% endif %}
{% endblock %}
```

When `after_model_change` returns `None` (or the page is loaded via GET), the
template falls through to `{{ super() }}` and renders the normal create form.

When a `dict` is returned, the template has access to `secret` (and any other
keys you include) plus the newly created `obj`.

## Returning a custom Response

If you need full control over the HTTP response, return a Starlette `Response`
directly:

```python
from starlette.responses import HTMLResponse

class ApiKeyAdmin(ModelView, model=ApiKey):
    async def after_model_change(self, data, model, is_created, request):
        if is_created:
            return HTMLResponse(f"<h1>Key created: {model.id}</h1>")
        return None
```

This bypasses template rendering entirely and returns your response as-is.
