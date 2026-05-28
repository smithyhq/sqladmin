# Displaying one-time secrets

A common pattern in admin panels is generating a secret (API key, token, etc.)
that is shown **once** right after creation and never again.

## The solution

Call `Secret.reveal_once(request, value)` from `after_model_change`. SQLAdmin
will skip the usual redirect, re-render the create/edit page, and display the
value in a one-time modal rendered by `layout.html`.

The secret lives only on `request.state` - it is never written to the session
or sent as a cookie, so it cannot leak across requests.

```python
import secrets
from sqladmin import ModelView, Secret


class ApiKeyAdmin(ModelView, model=ApiKey):
    async def on_model_change(self, data, model, is_created, request):
        if is_created:
            # Generate the raw value and store the hash on the model
            # *before* the row is committed.
            raw_secret = secrets.token_urlsafe(32)
            model.secret_hash = hash_secret(raw_secret)
            request.state._raw_secret = raw_secret

    async def after_model_change(self, data, model, is_created, request):
        raw_secret = getattr(request.state, "_raw_secret", None)
        if raw_secret:
            Secret.reveal_once(
                request,
                value=raw_secret,
                title="Your API key",
                label="Copy this value now, it will not be shown again.",
            )
```

`Secret.reveal_once` is also usable from a `BaseView`. Call it before returning
a `TemplateResponse` and the modal will render through `layout.html`. The
built-in create/edit handlers stamp anti-cache headers on the response
automatically; custom views must do so explicitly:

```python
response = await self.templates.TemplateResponse(request, "your_template.html", context)
Secret.apply_no_store_headers(response)
return response
```

## Custom rendering

If you need full control over the response (custom template, redirect to a
wizard step, file download, etc.), return a Starlette `Response` from
`after_model_change` instead - see
[Controlling the response with `after_model_change`](../configurations.md#controlling-the-response-with-after_model_change).
