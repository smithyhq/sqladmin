from enum import Enum
from typing import Dict, List

from starlette.requests import Request


class FlashLevel(Enum):
    """Defines the standard severity levels for flash messages.

    These values map directly to Bootstrap contextual color classes
    used in the toast notification UI.

    Attributes:
        info: General informational message. Maps to Bootstrap `primary` (blue).
        error: High-severity error message. Maps to Bootstrap `danger` (red).
        warning: Cautionary message. Maps to Bootstrap `warning` (yellow).
        success: Successful operation message. Maps to Bootstrap `success` (green).
    """

    info = "primary"
    error = "danger"
    warning = "warning"
    success = "success"


class Flash:
    """Utility class providing class methods for session-based flash messages.

    Flash messages are stored in the session and displayed as Bootstrap toast
    notifications on the next page render. They are automatically cleared after
    being displayed.

    All methods are class methods and require the `request` object to access
    the user session. If no session is available, messages are silently ignored.
    """

    @classmethod
    def flash(
        cls,
        request: Request,
        message: str,
        level: FlashLevel = FlashLevel.info,
        title: str = "",
    ) -> bool:
        """Add a flash message with an explicitly defined severity level.

        This is the primary method. Use the convenience methods (`info`,
        `success`, `warning`, `error`) to avoid specifying the level manually.

        Args:
            request: The current incoming request object.
            message: The main text content of the message.
            level: The severity level. Defaults to `FlashLevel.info`.
            title: An optional title shown in the toast header. Defaults to `""`.

        Returns:
            `True` if the message was stored successfully,
            `False` if no session is available.

        Example:
            ```python
            from sqladmin import Flash, FlashLevel

            Flash.flash(
                request,
                "A crucial server process has started.",
                FlashLevel.warning,
                "System Alert",
            )
            ```
        """
        return flash(
            request,
            message,
            level.value,
            title,
        )

    @classmethod
    def info(cls, request: Request, message: str, title: str = "") -> bool:
        """Add an informational flash message.

        Args:
            request: The current incoming request object.
            message: The message content.
            title: An optional title shown in the toast header. Defaults to `""`.

        Returns:
            `True` if the message was stored successfully,
            `False` if no session is available.

        Example:
            ```python
            from sqladmin import Flash

            Flash.info(request, "Your export is being processed in the background.")
            ```
        """
        return cls.flash(request, message, FlashLevel.info, title)

    @classmethod
    def success(cls, request: Request, message: str, title: str = "") -> bool:
        """Add a success flash message.

        Args:
            request: The current incoming request object.
            message: The message content.
            title: An optional title shown in the toast header. Defaults to `""`.

        Returns:
            `True` if the message was stored successfully,
            `False` if no session is available.

        Example:
            ```python
            from sqladmin import Flash

            Flash.success(request, "Users approved successfully.", "Done")
            ```
        """
        return cls.flash(request, message, FlashLevel.success, title)

    @classmethod
    def warning(cls, request: Request, message: str, title: str = "") -> bool:
        """Add a warning flash message.

        Args:
            request: The current incoming request object.
            message: The message content.
            title: An optional title shown in the toast header. Defaults to `""`.

        Returns:
            `True` if the message was stored successfully,
            `False` if no session is available.

        Example:
            ```python
            from sqladmin import Flash

            Flash.warning(request, "Some records could not be processed.")
            ```
        """
        return cls.flash(request, message, FlashLevel.warning, title)

    @classmethod
    def error(cls, request: Request, message: str, title: str = "") -> bool:
        """Add an error flash message.

        Args:
            request: The current incoming request object.
            message: The message content.
            title: An optional title shown in the toast header. Defaults to `""`.

        Returns:
            `True` if the message was stored successfully,
            `False` if no session is available.

        Example:
            ```python
            from sqladmin import Flash

            Flash.error(request, "Access denied. Invalid credentials.", "Error")
            ```
        """
        return cls.flash(request, message, FlashLevel.error, title)


def get_flashed_messages(request: Request) -> List[Dict[str, str]]:
    """Retrieve and clear all stored flash messages from the session.

    Called automatically by the built-in templates. You only need this
    function if you are writing a fully custom template.

    Args:
        request: The current incoming request object.

    Returns:
        A list of dicts, each with keys `message`, `category`, and `title`.
        Returns an empty list if no session is available or no messages exist.

    Example:
        ```html
        {# In a custom Jinja2 template #}
        {% with messages = get_flashed_messages(request) %}
          {% for msg in messages %}
            <div class="alert alert-{{ msg.category }}">{{ msg.message }}</div>
          {% endfor %}
        {% endwith %}
        ```
    """
    messages: List[Dict[str, str]] = []
    if "session" not in request.scope:
        return messages

    if "_messages" in request.session:
        messages = request.session.pop("_messages")

    return messages


def flash(
    request: Request,
    message: str,
    category: str = "primary",
    title: str = "",
) -> bool:
    """Store a flash message directly in the session.

    Low-level function used internally by the `Flash` class methods.
    Prefer using `Flash.success()`, `Flash.error()` etc. for type-safe
    level selection. Use this function only when you need to pass a raw
    Bootstrap color class string as the category.

    Args:
        request: The current incoming request object.
        message: The message content.
        category: A Bootstrap color class string. One of: `"primary"`,
            `"success"`, `"warning"`, `"danger"`. Defaults to `"primary"`.
        title: An optional title shown in the toast header. Defaults to `""`.

    Returns:
        `True` if the message was stored successfully,
        `False` if no session is available.

    Example:
        ```python
        from sqladmin.flash import flash

        flash(request, "Operation completed.", category="success", title="Done")
        ```
    """
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
