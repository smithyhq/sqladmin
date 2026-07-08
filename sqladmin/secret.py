from typing import Dict, Optional

from starlette.requests import Request
from starlette.responses import Response


class Secret:
    """One-time, request-scoped values rendered on the next response.

    Stashed on `request.state` only - never the session, never a cookie.
    """

    STATE_KEY = "sqladmin_secret"

    @classmethod
    def reveal_once(
        cls,
        request: Request,
        value: str,
        title: str = "Your secret",
        label: str = "Copy this value now, it will not be shown again.",
    ) -> None:
        """Stash a one-time secret to render as a modal on the next response.

        Callers that want the modal to show on a create/edit submission
        should call this from `after_model_change`; the create/edit handler
        will re-render instead of redirecting when a secret is set.
        """
        setattr(
            request.state,
            cls.STATE_KEY,
            {"value": value, "title": title, "label": label},
        )

    @classmethod
    def get(cls, request: Request) -> Optional[Dict[str, str]]:
        """Return the secret stashed via `reveal_once`, if any."""
        return getattr(request.state, cls.STATE_KEY, None)

    @staticmethod
    def apply_no_store_headers(response: Response) -> None:
        """Stamp cache-busting headers on a response carrying a secret."""
        response.headers["Cache-Control"] = (
            "no-store, no-cache, must-revalidate, max-age=0"
        )
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
