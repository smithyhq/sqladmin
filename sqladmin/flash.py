from enum import Enum
from typing import Dict, List, Optional

from starlette.requests import Request


class FlashLevel(Enum):
    """
    Defines the standard severity levels for flash messages.
    These values are typically used as CSS classes or categories.
    """

    info = "primary"
    error = "danger"
    warning = "warning"
    success = "success"


class Flash:
    """
    A utility class providing convenient class methods for creating
    session-based flash messages with predefined severity levels.
    """

    @classmethod
    def flash(
        cls,
        request: Request,
        message: str,
        level: FlashLevel = FlashLevel.info,
        title: str = "",
    ) -> bool:
        """
        Adds a custom flash message in any custom level.

        Args:
            request: The incoming request object.
            message: The message content.
            level: The custom flash level.
            title: An optional title.
        """
        return flash(
            request,
            message,
            level.value,
            title,
        )

    @classmethod
    def info(cls, request: Request, message: str, title: str = "") -> bool:
        """
        Adds an informational flash message (level: INFO).

        Args:
            request: The incoming request object.
            message: The message content.
            title: An optional title.
        """
        return cls.flash(
            request,
            message,
            FlashLevel.info,
            title,
        )

    @classmethod
    def error(cls, request: Request, message: str, title: str = "") -> bool:
        """
        Adds an error flash message (level: ERROR).

        Args:
            request: The incoming request object.
            message: The message content.
            title: An optional title.
        """
        return cls.flash(
            request,
            message,
            FlashLevel.error,
            title,
        )

    @classmethod
    def warning(cls, request: Request, message: str, title: str = "") -> bool:
        """
        Adds a warning flash message (level: WARNING).

        Args:
            request: The incoming request object.
            message: The message content.
            title: An optional title.
        """
        return cls.flash(
            request,
            message,
            FlashLevel.warning,
            title,
        )

    @classmethod
    def success(cls, request: Request, message: str, title: str = "") -> bool:
        """
        Adds a successful action flash message (level: SUCCESS).

        Args:
            request: The incoming request object.
            message: The message content.
            title: An optional title.
        """
        return cls.flash(
            request,
            message,
            FlashLevel.success,
            title,
        )

    @classmethod
    def secret(
        cls,
        request: Request,
        value: str,
        title: str = "Your secret",
        label: str = "Copy this value now, it will not be shown again.",
    ) -> None:
        """Stash a one-time secret to render as a modal on the next response.

        The value lives only on ``request.state`` (never in the session), so it
        does not survive a redirect. Callers that want the modal to show on a
        create/edit submission should call this from ``after_model_change``;
        the create/edit handler will re-render instead of redirecting when a
        secret is set.
        """
        request.state.sqladmin_secret = {
            "value": value,
            "title": title,
            "label": label,
        }


def get_flashed_messages(request: Request) -> List[Dict[str, str]]:
    messages: List[Dict[str, str]] = []
    if "session" not in request.scope:
        return messages

    if "_messages" in request.session:
        messages = request.session.pop("_messages")

    return messages


def get_secret(request: Request) -> Optional[Dict[str, str]]:
    """Return the one-time secret stashed via ``Flash.secret``, if any."""
    return getattr(request.state, "sqladmin_secret", None)


def flash(
    request: Request, message: str, category: str = "primary", title: str = ""
) -> bool:
    if "session" not in request.scope:
        return False

    if "_messages" not in request.session:
        request.session["_messages"] = []

    request.session["_messages"].append(
        {
            "category": category,
            "title": title,
            "message": message,
        }
    )

    return True
