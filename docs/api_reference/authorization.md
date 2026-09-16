::: sqladmin.authorization.Action
    handler: python

::: sqladmin.authorization.ACTIONS
    handler: python

::: sqladmin.authorization.custom_action
    handler: python

::: sqladmin.authorization.AuthorizationBackend
    handler: python
    options:
      members:
        - setup
        - load
        - has_permission

::: sqladmin.authorization.AllowAllAuthorizationBackend
    handler: python

::: sqladmin.authorization.GrantsAuthorizationBackend
    handler: python
    options:
      members:
        - get_grants

::: sqladmin.authorization.matches_grant
    handler: python

::: sqladmin.contrib.rbac.DBAuthorizationBackend
    handler: python
    options:
      members:
        - __init__

::: sqladmin.contrib.rbac.GroupMixin
    handler: python

::: sqladmin.contrib.rbac.GroupAccessMixin
    handler: python

::: sqladmin.contrib.rbac.user_group_table
    handler: python

::: sqladmin.contrib.rbac.GroupAdmin
    handler: python
    options:
      members:
        - can_grant

::: sqladmin.exceptions.PermissionEscalationError
    handler: python

::: sqladmin.exceptions.InvalidRelationshipError
    handler: python

::: sqladmin.exceptions.ImproperlyConfigured
    handler: python
