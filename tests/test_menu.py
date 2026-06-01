from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import declarative_base
from starlette.requests import Request

from sqladmin import ModelView
from sqladmin._menu import CategoryMenu, ItemMenu, Menu, ViewMenu

Base = declarative_base()  # type: ignore


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(String)


class UserAdmin(ModelView, model=User): ...


request = Request({"type": "http"})


def test_item_menu():
    item_menu = ItemMenu(name="item")
    child_menu = ItemMenu(name="child")
    item_menu.add_child(child_menu)

    assert item_menu.display_name == "item"
    assert item_menu.url(request) == "#"
    assert item_menu.is_visible(request) is True
    assert item_menu.is_accessible(request) is True
    assert item_menu.is_active(request) is False
    assert item_menu.type_ == "ItemMenu"


def test_category_menu():
    item_menu = CategoryMenu(name="category")

    assert item_menu.is_active(request) is False
    assert item_menu.type_ == "Category"


def test_category_menu_is_active_when_child_is_active():
    request = Request(
        {
            "type": "http",
            "path_params": {"identity": "user"},
        }
    )
    user_menu = ViewMenu(view=UserAdmin(), name="user")

    category_menu = CategoryMenu(name="Models")
    category_menu.add_child(user_menu)

    assert user_menu.is_active(request) is True
    assert category_menu.is_active(request) is True


def test_category_menu_is_not_active_when_no_child_is_active():
    user_menu = ViewMenu(view=UserAdmin(), name="user")

    category_menu = CategoryMenu(name="Models")
    category_menu.add_child(user_menu)

    assert user_menu.is_active(request) is False
    assert category_menu.is_active(request) is False


def test_view_menu():
    item_menu = ViewMenu(view=UserAdmin(), name="view")

    assert item_menu.display_name == "Users"
    assert item_menu.type_ == "View"
    assert item_menu.is_visible(request) is True
    assert item_menu.is_accessible(request) is True
    assert item_menu.is_active(request) is False


def test_menu():
    item_menu = ItemMenu(name="item")
    child_menu = ItemMenu(name="child")
    item_menu.add_child(child_menu)

    menu = Menu()
    menu.add(item_menu)

    item_menu = ItemMenu(name="item")
    another_child = ItemMenu(name="another_child")
    item_menu.add_child(another_child)

    menu.add(item_menu)

    assert len(menu.items) == 1
    assert len(menu.items.pop().children) == 2
