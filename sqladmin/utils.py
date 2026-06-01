from typing import Any
from urllib.parse import parse_qsl, urlencode

from litestar.datastructures import URL


def include_query_params(url: str | URL, **kwargs: Any) -> str:
    url = URL(str(url))
    query_items = parse_qsl(url.query, keep_blank_values=True)
    updated_keys = set()
    updated_items = []

    for key, value in query_items:
        if key in kwargs:
            updated_items.append((key, kwargs[key]))
            updated_keys.add(key)
        else:
            updated_items.append((key, value))

    for key, value in kwargs.items():
        if key not in updated_keys:
            updated_items.append((key, value))

    return str(url.with_replacements(query=urlencode(updated_items, doseq=True)))


def remove_query_params(url: str | URL, *params: str) -> str:
    url = URL(str(url))
    query_items = [
        (key, value)
        for key, value in parse_qsl(url.query, keep_blank_values=True)
        if key not in params
    ]
    return str(url.with_replacements(query=urlencode(query_items, doseq=True)))
