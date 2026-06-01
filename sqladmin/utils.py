from typing import Any

from litestar.datastructures import URL


def include_query_params(url: URL, **kwargs: Any) -> URL:
    query_params = url.query_params.copy()
    query_params.update(kwargs)
    return url.with_replacements(query=query_params)


def remove_query_params(url: URL, *params: str) -> URL:
    query_params = url.query_params.copy()
    for param in params:
        query_params.pop(param, None)
    return url.with_replacements(query=query_params)
