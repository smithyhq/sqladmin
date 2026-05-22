---

# Model Converters

Model Converters are special classes used to convert SQLAlchemy model properties into web interface form fields. They allow you to customize how backend SQLAlchemy models are represented in the admin interface, providing flexibility in handling different data types and validation rules.

---

## Overview

The `ModelConverter` class is the base class for converting SQLAlchemy model properties into form fields. It provides default conversions for common SQLAlchemy types (e.g., `String`, `Integer`, `JSON`) and allows you to customize or extend these conversions.

### Base Model Converter

The base `ModelConverter` class looks like this:

```python
class ModelConverter(ModelConverterBase):
    @staticmethod
    def _string_common(prop: ColumnProperty) -> list[Validator]:
        li = []
        column: Column = prop.columns[0]
        if isinstance(column.type.length, int) and column.type.length:
            li.append(validators.Length(max=column.type.length))
        return li

    @converts("String", "CHAR")  # includes Unicode
    def conv_string(
        self, model: type, prop: ColumnProperty, kwargs: dict[str, Any]
    ) -> UnboundField:
        extra_validators = self._string_common(prop)
        kwargs.setdefault("validators", [])
        kwargs["validators"].extend(extra_validators)
        return StringField(**kwargs)

    @converts("Text", "LargeBinary", "Binary")  # includes UnicodeText
    def conv_text(
        self, model: type, prop: ColumnProperty, kwargs: dict[str, Any]
    ) -> UnboundField:
        kwargs.setdefault("validators", [])
        extra_validators = self._string_common(prop)
        kwargs["validators"].extend(extra_validators)
        return TextAreaField(**kwargs)
```

This class includes methods like `conv_string` and `conv_text` to handle specific SQLAlchemy types. You can extend this class to add custom behavior or override existing conversions.

---

## Customizing Model Converters

You can inherit from `ModelConverter` to create your own converter and customize how specific SQLAlchemy types are handled. For example, you can define a custom converter for `JSON` fields:

```python
from typing import Any
import json
from wtforms import JSONField
from sqladmin import ModelConverter


class CustomJSONField(JSONField):
    def _value(self) -> str:
        if self.raw_data:
            return self.raw_data[0]
        elif self.data:
            return str(json.dumps(self.data, ensure_ascii=False))
        else:
            return ""


class CustomModelConverter(ModelConverter):
    @converts("JSON", "JSONB")
    def conv_json(self, model: type, prop: ColumnProperty, kwargs: dict[str, Any]) -> UnboundField:
        return CustomJSONField(**kwargs)
```

In this example:
- `CustomJSONField` is a custom field that formats JSON data for display.
- `CustomModelConverter` overrides the `conv_json` method to use `CustomJSONField` for `JSON` and `JSONB` SQLAlchemy types.

---

## Using Custom Model Converters in Admin Views

To use your custom model converter in the admin interface, specify it in your `ModelView` class:

```python
from sqladmin import ModelView


class BaseAdmin(ModelView):
    form_converter: ClassVar[Type[CustomModelConverter]] = CustomModelConverter
```

This ensures that all form fields in the admin interface are generated using your custom converter.

---

## Example: Full Workflow

Here’s a complete example of defining a SQLAlchemy model, creating a custom model converter, and using it in the admin interface:

### Step 1: Define SQLAlchemy Models

```python
from sqlalchemy import Column, Integer, String, JSON, create_engine
from sqlalchemy.orm import declarative_base


Base = declarative_base()
engine = create_engine("sqlite:///example.db", connect_args={"check_same_thread": False})


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(String)
    preferences = Column(JSON)


Base.metadata.create_all(engine)  # Create tables
```

### Step 2: Create Custom Model Converter

```python
from sqladmin import ModelConverter
from wtforms import JSONField
import json


class CustomJSONField(JSONField):
    def _value(self) -> str:
        if self.raw_data:
            return self.raw_data[0]
        elif self.data:
            return str(json.dumps(self.data, ensure_ascii=False))
        else:
            return ""


class CustomModelConverter(ModelConverter):
    @converts("JSON", "JSONB")
    def conv_json(self, model: type, prop: ColumnProperty, kwargs: dict[str, Any]) -> UnboundField:
        return CustomJSONField(**kwargs)
```

### Step 3: Use Custom Converter in Admin Interface

```python
from sqladmin import ModelView


class UserAdmin(BaseAdmin):
    form_converter = CustomModelConverter
```
