The template uses `Jinja2` template engine and by default looks for a `templates/sqladmin` directory in your project.

If your `templates/sqladmin` directory has the default template files like `list.html` or `create.html` then they will be used.
Otherwise you can create custom templates and use them.

## Customizing templates

As the first step you should create a `templates/sqladmin` directory in you project.

Since `Jinja2` is modular, you can override your specific template file and do your changes.
For example you can create a `custom_details.html` file which overrides the `details.html` from
SQLAdmin and in the `content` block it adds custom HTML tags:

!!! example

    ```html title="custom_details.html"
    {% extends "sqladmin/details.html" %}
    {% block content %}
        {{ super() }}
        <p>Custom HTML</p>
    {% endblock %}
    ```

    ```python title="admin.py"
    class UserAdmin(ModelView, model=User):
        details_template = "sqladmin/custom_details.html"
    ```

### Customizing column filter templates

Each built-in column filter declares a `template` attribute which defaults to one of
`sqladmin/filters/lookup_filter.html` or `sqladmin/filters/operation_filter.html`.
You can point a filter to your own template for full control over its UI—for example,
to render lookup values in a drop-down instead of a long list of links:

!!! example

    ```python title="admin.py"
    from sqladmin.filters import StaticValuesFilter


    class StatusDropdownFilter(StaticValuesFilter):
        template = "filters/status_dropdown_filter.html"

        def __init__(self):
            super().__init__(
                column=Article.status,
                values=[("draft", "Draft"), ("published", "Published")],
                title="Status",
            )
    ```

    ```html title="templates/filters/status_dropdown_filter.html"
    {% extends "sqladmin/filters/base_filter.html" %}

    {% block filter_body %}
      {% set current_value = request.query_params.get(filter.parameter_name, '') %}

      <form method="get" class="d-flex flex-column" style="gap: 8px;">
        {% for key, value in request.query_params.items() %}
          {% if key != filter.parameter_name %}
          <input type="hidden" name="{{ key }}" value="{{ value }}">
          {% endif %}
        {% endfor %}

        <select name="{{ filter.parameter_name }}" class="form-select form-select-sm">
          {% for value, label in filter.lookups(request, model_view.model, model_view._run_arbitrary_query) %}
            <option value="{{ value }}" {% if current_value == value %}selected{% endif %}>{{ label }}</option>
          {% endfor %}
        </select>

        <div class="d-flex align-items-center" style="gap: 8px;">
          <button type="submit" class="btn btn-sm btn-outline-primary">Apply</button>
          {% if current_value %}
          <a href="{{ request.url.remove_query_params(filter.parameter_name) }}" class="text-decoration-none small">Clear</a>
          {% endif %}
        </div>
      </form>
    {% endblock %}
    ```

This makes it possible to ship custom filter widgets by subclassing an existing filter
and only overriding its template.

## Overriding default templates

The recommended way to customize existing default templates (like adding a script to every page) without redefining the entire HTML structure is to extend the original template using the `sqladmin_original/` prefix. This allows you to selectively override or append to specific Jinja blocks using `{{ super() }}` while preserving the rest of the template.

For example, if there is some Javascript you want to run on every page, you can extend the original `layout.html` and append to the `tail` or `tail_js` block like so:

!!! example

    ```html title="myproject/templates/sqladmin/layout.html"
    {% extends "sqladmin_original/layout.html" %}

    {% block tail_js %}
    {{ super() }}
    <script type="text/javascript">
        console.log('hello world');
    </script>
    {% endblock %}
    ```

**Alternative method (Full override):**

If your customizations are so extensive that using blocks isn't sufficient, you can completely replace a default template. To do this, copy the existing template from SQLAdmin's `templates/sqladmin` into your project's `templates/sqladmin` directory without using `extends`. It will then be loaded instead of the one in the package, bypassing the original entirely.

## Customizing Jinja2 environment

You can add custom environment options to use it on your custom templates. First set up a project:

```python
from sqladmin import Admin
from starlette.applications import Starlette


app = Starlette()
admin = Admin(app, engine)
```

Then you can add your environment options:

### Adding filters

```python
def datetime_format(value, format="%H:%M %d-%m-%y"):
    return value.strftime(format)

admin.templates.env.filters["datetime_format"] = datetime_format
```

Usage in templates:

```
{{ article.pub_date|datetimeformat }}
{{ article.pub_date|datetimeformat("%B %Y") }}
```

### Adding tests

```python
import math

def is_prime(n):
    if n == 2:
        return True

    for i in range(2, int(math.ceil(math.sqrt(n))) + 1):
        if n % i == 0:
            return False

    return True

admin.templates.env.tests["prime"] = is_prime
```

Usage in templates:

```
{% if value is prime %}
    {{ value }} is a prime number
{% else %}
    {{ value }} is not a prime number
{% endif %}
```

# Adding globals

```python
def value_is_filepath(value: Any) -> bool:
    return isinstance(value, str) and os.path.isfile(value)

admin.templates.env.globals["value_is_filepath"] = value_is_filepath
```

Usage in templates:

```
{% if value_is_filepath(value) %}
    {{ value }} is file path
{% else %}
    {{ value }} is not file path
{% endif %}
```

# Template Blocks
The SQLAdmin templates use blocks to allow easy customization and extension of the templates. Here is a list of the main blocks available SQLAdmin templates:

| Block Name | Description |
|------------|-------------|
| `head_meta`  | Page metadata in the header |
| `head_css`    | Various CSS includes in the header |
| `head`     | Empty block in HTML head, in case you want to put something there |
| `head_tail`  | Additional HTML elements before the closing `</head>` tag |
| `body`     | The main body of the page |
| `main`     | The main container for the page content |
| `content`  | The main content area where page-specific content is rendered |
| `tail`     | Additional HTML elements before the closing `</body>` tag |
| `tail_js `  | Various JavaScript includes before the closing `</body>` tag |
| `create_form` | The form used in the create view containing fields |
| `edit_form` | The form used in the edit view containing fields |
| `details_table` | The the div containing the records details table|
| `submit_buttons_bottom` | The submit buttons at the bottom of create/edit views |
| `action_buttons_bottom` | The action buttons at the bottom of details view |
| `model_list_table` | The table displaying records in the list view |
| `model_menu_bar` | The menu bar at the top of model list view |


You can override these blocks in your custom templates to modify the layout and appearance of the admin interface as needed.
