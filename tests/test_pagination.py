import pytest
from starlette.datastructures import URL

from sqladmin.pagination import PageControl, Pagination

BASE_URL = URL("http://testserver/users/list")


def test_single_page() -> None:
    pagination = Pagination(rows=[], page=1, page_size=5, count=5)
    pagination.add_pagination_urls(BASE_URL)

    assert pagination.has_previous is False
    assert pagination.has_next is False
    with pytest.raises(RuntimeError):
        pagination.next_page
    with pytest.raises(RuntimeError):
        pagination.previous_page


def test_multi_page_first_page() -> None:
    pagination = Pagination(rows=[], page=1, page_size=5, count=15)
    pagination.add_pagination_urls(BASE_URL)

    assert pagination.has_previous is False
    assert pagination.has_next is True
    assert pagination.next_page.url == "http://testserver/users/list?page=2"
    with pytest.raises(RuntimeError):
        pagination.previous_page


def test_multi_page_last_page() -> None:
    pagination = Pagination(rows=[], page=4, page_size=5, count=18)
    pagination.add_pagination_urls(BASE_URL)

    page_control = PageControl(number=4, url="http://testserver/users/list?page=4")
    assert page_control in pagination.page_controls
    assert pagination.has_previous is True
    with pytest.raises(RuntimeError):
        pagination.next_page


def test_multi_page_equal_previous_and_next() -> None:
    pagination = Pagination(rows=[], page=5, page_size=5, count=50)
    pagination.add_pagination_urls(BASE_URL)

    page_controls = [
        PageControl(number=i, url=f"http://testserver/users/list?page={i}")
        for i in range(2, 9)
    ]

    assert pagination.page_controls == page_controls


def test_multi_page_unequal_previous_and_next() -> None:
    pagination = Pagination(rows=[], page=2, page_size=5, count=50)
    pagination.add_pagination_urls(BASE_URL)

    page_controls = [
        PageControl(number=i, url=f"http://testserver/users/list?page={i}")
        for i in range(1, 8)
    ]

    assert pagination.page_controls == page_controls

    pagination = Pagination(rows=[], page=8, page_size=5, count=50)
    pagination.add_pagination_urls(BASE_URL)

    page_controls = [
        PageControl(number=i, url=f"http://testserver/users/list?page={i}")
        for i in range(4, 11)
    ]

    assert pagination.page_controls == page_controls


@pytest.mark.parametrize(
    ("count", "page", "expected"),
    [(0, 2, 1), (10, 0, 1), (10, 3, 2), (11, 3, 3)],
)
def test_clamp_page(count: int, page: int, expected: int) -> None:
    pagination = Pagination(rows=[], page=page, page_size=5, count=count)

    assert pagination.page == expected


@pytest.mark.parametrize("page_size", [0, -1])
def test_page_size_must_be_positive(page_size: int) -> None:
    with pytest.raises(ValueError, match="page_size must be greater than 0"):
        Pagination(rows=[], page=1, page_size=page_size, count=10)


def test_resize_pagination() -> None:
    pagination = Pagination(rows=[], page=3, page_size=5, count=20)
    assert pagination.resize(100).page == 1

    pagination = Pagination(rows=[], page=3, page_size=5, count=20)
    assert pagination.resize(1).page == 11

    pagination = Pagination(rows=[], page=3, page_size=5, count=20)
    assert pagination.resize(8).page == 2
