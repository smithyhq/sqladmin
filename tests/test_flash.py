from typing import Generator

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import RedirectResponse
from starlette.testclient import TestClient

from sqladmin import Admin, BaseView, expose
from sqladmin.authentication import AuthenticationBackend
from sqladmin.flash import Flash, FlashLevel, flash, get_flashed_messages
from tests.common import sync_engine as engine


@pytest.fixture
def mock_request_with_session():
    mock_scope = {"session": {}, "type": "http"}
    request = Request(scope=mock_scope)

    return request


@pytest.fixture
def mock_request_without_session():
    mock_scope = {"type": "http"}
    request = Request(scope=mock_scope)

    return request


def test_flash_success_with_defaults(mock_request_with_session):
    request = mock_request_with_session

    result = flash(request, message="Test message")

    assert result is True

    messages = request.session.get("_messages")
    assert len(messages) == 1
    assert messages[0]["message"] == "Test message"
    assert messages[0]["category"] == "primary"  # Default category
    assert messages[0]["title"] == ""  # Default title


def test_flash_success_with_custom_values(mock_request_with_session):
    request = mock_request_with_session

    result = flash(request, message="Custom message", category="danger", title="Error")

    assert result is True

    messages = request.session.get("_messages")
    assert len(messages) == 1
    assert messages[0]["message"] == "Custom message"
    assert messages[0]["category"] == "danger"
    assert messages[0]["title"] == "Error"


def test_flash_multiple_messages(mock_request_with_session):
    request = mock_request_with_session

    flash(request, message="First message")
    flash(request, message="Second message", category="success")

    messages = request.session.get("_messages")
    assert len(messages) == 2
    assert messages[1]["category"] == "success"


def test_flash_no_session_middleware(mock_request_without_session):
    request = mock_request_without_session

    result = flash(request, message="Should fail")

    assert result is False

    assert "session" not in request.scope


def test_get_flashed_messages_no_session_middleware(mock_request_without_session):
    request = mock_request_without_session

    messages = get_flashed_messages(request)

    assert messages == []
    assert isinstance(messages, list)


def test_get_flashed_messages_empty_session(mock_request_with_session):
    request = mock_request_with_session

    messages = get_flashed_messages(request)

    assert messages == []
    assert "_messages" not in request.session


def test_get_flashed_messages_retrieval_and_pop(mock_request_with_session):
    request = mock_request_with_session

    initial_messages = [
        {"category": "info", "title": "", "message": "Message 1"},
        {"category": "warning", "title": "Alert", "message": "Message 2"},
    ]
    request.session["_messages"] = initial_messages

    retrieved_messages = get_flashed_messages(request)

    assert len(retrieved_messages) == 2
    assert retrieved_messages[0]["message"] == "Message 1"
    assert retrieved_messages[1]["category"] == "warning"

    assert "_messages" not in request.session


def test_get_flashed_messages_idempotency(mock_request_with_session):
    request = mock_request_with_session

    request.session["_messages"] = [{"message": "Only once"}]
    first_retrieval = get_flashed_messages(request)

    second_retrieval = get_flashed_messages(request)

    assert len(first_retrieval) == 1
    assert second_retrieval == []
    assert "_messages" not in request.session


@pytest.mark.parametrize(
    "method_name, expected_level",
    [
        ("info", FlashLevel.info.value),
        ("error", FlashLevel.error.value),
        ("warning", FlashLevel.warning.value),
        ("success", FlashLevel.success.value),
    ],
)
def test_flash_shortcuts(
    mock_request_with_session, method_name: str, expected_level: str
):
    request = mock_request_with_session
    message = f"Message for {method_name}"
    title = f"Title for {method_name}"

    flash_method = getattr(Flash, method_name)
    flash_method(request, message, title)

    messages = request.session.get("_messages")
    assert len(messages) == 1

    # Comprobamos los contenidos del mensaje añadido
    assert messages[0] == {
        "category": expected_level,
        "title": title,
        "message": message,
    }


# --- Integration tests: flash renders as toast in HTTP response context ---


class _AlwaysAuthBackend(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        return True

    async def logout(self, request: Request) -> bool:
        return True

    async def authenticate(self, request: Request) -> bool:
        return True


class _FlashTriggerView(BaseView):
    @expose("/flash-trigger", methods=["GET"])
    async def trigger_flash(self, request: Request):
        flash(request, message="Toast test message", category="success", title="Done")
        return RedirectResponse(request.url_for("admin:index"), status_code=302)


_app = Starlette()
_admin = Admin(
    app=_app,
    engine=engine,
    authentication_backend=_AlwaysAuthBackend(secret_key="test-flash"),
)
_admin.add_base_view(_FlashTriggerView)


@pytest.fixture
def flash_client() -> Generator[TestClient, None, None]:
    with TestClient(_app, base_url="http://testserver") as c:
        yield c


def test_flash_renders_toast_in_request_context(flash_client: TestClient) -> None:
    response = flash_client.get("/admin/flash-trigger")

    assert response.status_code == 200
    assert "toast-container" in response.text
    assert "Toast test message" in response.text
    assert "text-bg-success" in response.text
    assert "Done" in response.text


def test_flash_toast_consumed_after_one_render(flash_client: TestClient) -> None:
    flash_client.get("/admin/flash-trigger")

    second_response = flash_client.get("/admin/")
    assert "Toast test message" not in second_response.text
