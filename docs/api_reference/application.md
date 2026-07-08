::: sqladmin.application.Admin
    handler: python
    options:
      members:
        - __init__

::: sqladmin.application.BaseAdmin
    handler: python
    options:
      members:
        - views
        - add_view
        - add_model_view
        - add_base_view

::: sqladmin.application.action
    handler: python

::: sqladmin.flash.FlashLevel
    handler: python

::: sqladmin.flash.Flash
    handler: python
    options:
      members:
        - flash
        - info
        - success
        - warning
        - error

::: sqladmin.flash.flash
    handler: python

::: sqladmin.flash.get_flashed_messages
    handler: python