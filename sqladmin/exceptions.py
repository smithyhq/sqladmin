from logging import getLogger
from typing import cast

from wtforms import Form

logger = getLogger(__name__)


class SQLAdminException(Exception):
    pass


class InvalidModelError(SQLAdminException):
    pass


class NoConverterFound(SQLAdminException):
    pass


class ValidationError(SQLAdminException):
    """Validation error that can carry both field-level and form-level messages.

    Usage::

        ValidationError("Form-wide error message")
        ValidationError(field_name="Field-level error message")
        ValidationError("Form error", field_a="Field A error", field_b="Field B error")

    .. note::
        This method is called from the ``ValidationError`` handler in
        ``Admin.create`` and ``Admin.edit``.  If a ``ValidationError`` is
        raised inside ``after_model_change`` (which runs *after* the database
        commit), the row will already be persisted — the error will still be
        rendered on the form, but the data change cannot be rolled back.
    """

    def __init__(self, *form_errors: str, **field_errors: str):
        self.form_errors = form_errors
        self.field_errors = field_errors

    def enrich_form(self, form: Form) -> None:
        """Enrich *form* with the stored validation errors.

        Unknown field names are silently skipped (with a warning).
        """
        for field_name, error in self.field_errors.items():
            field = form._fields.get(field_name)
            if field is None:
                logger.warning("enrich_form: unknown field '%s'", field_name)
                continue
            cast(list[str], field.errors).append(error)

        if self.form_errors:
            form.form_errors += self.form_errors
        elif not self.field_errors:
            # default error
            form.form_errors.append("Validation error")


class ImproperlyConfigured(SQLAdminException, ValueError):
    """SQLAdmin was set up in a way that cannot work.

    Raised as soon as the mistake can be detected: usually when the view or
    backend is created, or on the first admin request when it depends on how
    the `Admin` was configured. Also a `ValueError`, so existing
    ``except ValueError`` handlers still work.
    """


class InvalidRelationshipError(ImproperlyConfigured):
    """A model has no relationship under the name SQLAdmin was told to use.

    Raised at startup when an RBAC model or view is misconfigured, e.g. when
    `DBAuthorizationBackend(groups_attr=...)` names a missing relationship.
    """


class PermissionEscalationError(SQLAdminException, PermissionError):
    """A group editor tried to grant a permission they may not grant.

    See `GroupAdmin.can_grant`.
    """
