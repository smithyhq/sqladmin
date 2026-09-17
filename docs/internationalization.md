SQLAdmin can translate its interface into multiple languages using
[Babel](https://babel.pocoo.org/). Compiled catalogs for Azerbaijani (`az`),
German (`de`), English (`en`), Russian (`ru`) and Turkish (`tr`) ship with the
package.

Translation is optional. Install the extra to enable it:

```shell
pip install sqladmin[i18n]
```

## Enabling i18n

Pass an `I18nConfig` to `Admin`. Setting `language_switcher` also renders a
language switcher in the navigation:

!!! example

    ```python title="admin.py"
    from sqladmin import Admin
    from sqladmin.i18n import I18nConfig

    admin = Admin(
        app,
        engine,
        i18n_config=I18nConfig(
            default_locale="en",
            language_switcher=["en", "az", "de", "ru", "tr"],
        ),
    )
    ```

`I18nConfig` accepts:

- `default_locale`: locale used when nothing else is detected.
- `language_cookie_name`: cookie that persists the visitor's choice (`"language"` by default; set to `None` to disable).
- `language_header_name`: request header inspected for a preferred locale (`"Accept-Language"` by default; set to `None` to disable).
- `language_switcher`: locale codes shown in the switcher. `None` hides it.

## How the active locale is resolved

For every request the locale is resolved in this order, highest priority first:

1. The `?lang=` query parameter set by the switcher (persisted to the cookie).
2. The language cookie.
3. The `Accept-Language` header, negotiated against the supported locales.
4. `default_locale`.

Only locales in `sqladmin.i18n.SUPPORTED_LOCALES` are accepted.

## Translating your own strings

The translation functions resolve against the visitor's active locale, so they
work for flash messages and any custom output:

!!! example

    ```python title="admin.py"
    from sqladmin import Flash
    from sqladmin.i18n import gettext as _


    class UserAdmin(ModelView, model=User):
        async def after_model_change(self, data, model, is_created, request):
            Flash.success(request, _("User saved."))
    ```

For strings defined at import time, use `lazy_gettext`, which defers
translation until the string is rendered:

!!! example

    ```python
    from sqladmin.i18n import lazy_gettext as _

    SAVE_LABEL = _("Save")
    ```

In custom templates the functions are installed by the Jinja `i18n` extension,
so both `{{ _("...") }}` and `{% trans %}` blocks work:

!!! example

    ```html title="custom_list.html"
    {% extends "sqladmin/list.html" %}
    {% block content %}
        {{ super() }}
        <p>{{ _("Export is ready.") }}</p>
    {% endblock %}
    ```

## Plurals

`ngettext` selects the form using the `Plural-Forms` rule compiled into each
catalog, so languages with more than two forms (Russian, Polish, Arabic, ...)
are handled correctly:

!!! example

    ```python
    from sqladmin.i18n import ngettext

    ngettext("%(num)d row", "%(num)d rows", 5) % {"num": 5}
    ```

## Adding a language

New languages are shipped with the package rather than registered at runtime.
The set of interface strings is small and stable, so bundling a compiled
catalog keeps every install working out of the box with no per-application
setup, and the translations stay quality-controlled. To add one, translate a
catalog and open a pull request.

SQLAdmin marks its translatable text with `_("...")` in the Jinja templates.
The workflow uses [Babel](https://babel.pocoo.org/) through the `Makefile`
targets (each wraps the equivalent `pybabel` command). The extraction config
lives in the `[tool.babel]` table of `pyproject.toml` — run these commands from
the repository root:

```shell
# 1. Refresh the .pot template and sync every existing catalog
make i18n-extract

# 2. Create a catalog for the new locale, e.g. French
make i18n-init LOCALE=fr

# 3. Translate the messages in
#    sqladmin/translations/fr/LC_MESSAGES/admin.po
#    then remove the `#, fuzzy` line from its header

# 4. Compile every .po into the binary .mo files loaded at runtime
make i18n-compile
```

`make i18n-init` creates the `fr/LC_MESSAGES/` directory for you, so nothing
needs to be created by hand. Finally, add the locale code to
`SUPPORTED_LOCALES` in `sqladmin/i18n.py` and commit both the `.po` (source)
and `.mo` (compiled) files.

!!! note

    Babel marks new or changed catalog entries `#, fuzzy`, and
    `pybabel compile` skips a catalog whose header is fuzzy. After reviewing a
    translation, delete the `#, fuzzy` line so `make i18n-compile` picks it up.

!!! note

    Model field labels and WTForms validation messages are not covered by this
    layer. Field labels come from your SQLAlchemy columns (use `column_labels`
    to customise them), and WTForms ships its own validator translations.
