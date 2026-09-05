::: sqladmin.authorization.AuthorizationBackend
    handler: python
    options:
      members:
        - load
        - has_permission
        - has_any_permission

::: sqladmin.authorization.GrantsAuthorizationBackend
    handler: python
    options:
      members:
        - get_grants
        - is_superuser

::: sqladmin.authorization.matches_grant
    handler: python

::: sqladmin.contrib.rbac.DBAuthorizationBackend
    handler: python
    options:
      members:
        - __init__
        - get_user_id

::: sqladmin.contrib.rbac.GroupMixin
    handler: python

::: sqladmin.contrib.rbac.GroupAccessMixin
    handler: python

::: sqladmin.contrib.rbac.user_group_table
    handler: python

::: sqladmin.contrib.rbac.GroupAdmin
    handler: python
