class SQLAdminException(Exception):
    pass


class InvalidModelError(SQLAdminException):
    pass


class NoConverterFound(SQLAdminException):
    pass


class ValidationError(SQLAdminException):
    def __init__(self, *form_errors: str, **field_errors: str):
        self.form_errors = form_errors
        self.field_errors = field_errors

    def enrich_form(self, form):
        for field_name, error in self.field_errors.items():
            form._fields[field_name].errors.append(error)

        if self.form_errors:
            form.form_errors.append(self.form_errors)
        elif not self.field_errors:
            # default error
            form.form_errors.append("Validation error")
