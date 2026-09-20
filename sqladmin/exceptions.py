class SQLAdminException(Exception):
    pass


class InvalidModelError(SQLAdminException):
    pass


class NoConverterFound(SQLAdminException):
    pass


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
