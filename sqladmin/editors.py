from __future__ import annotations

from typing import Any, Iterable, List

from wtforms import Form
from wtforms.fields import TextAreaField


class FieldMedia:
    """
    Holds the CSS and JS asset URLs a form field needs.

    Modelled on Django's ``Media`` class. Adding two ``FieldMedia`` objects
    merges their assets while preserving order and dropping duplicates, so a
    library referenced by several fields is only loaded once.
    """

    def __init__(
        self,
        css: Iterable[str] = (),
        js: Iterable[str] = (),
    ) -> None:
        self.css: List[str] = list(css)
        self.js: List[str] = list(js)

    def __add__(self, other: "FieldMedia") -> "FieldMedia":
        seen_css = set(self.css)
        seen_js = set(self.js)
        return FieldMedia(
            css=self.css + [u for u in other.css if u not in seen_css],
            js=self.js + [u for u in other.js if u not in seen_js],
        )

    def __bool__(self) -> bool:
        return bool(self.css or self.js)


def collect_form_media(form: Form) -> FieldMedia:
    """
    Merge the media of every field in a form into a single ``FieldMedia``.

    Fields that do not declare a ``media`` attribute are skipped. The result
    is deduplicated, so each library is loaded exactly once regardless of how
    many fields use it.

    Registered as a Jinja global by ``Admin`` so the create and edit templates
    can compute the media of the current ``form`` directly. This keeps it
    correct even when the form is re-rendered after a validation error.
    """
    media = FieldMedia()
    for field in form:
        field_media = getattr(field, "media", None)
        if field_media is not None:
            media = media + field_media
    return media


class CKEditor5Field(TextAreaField):
    """
    A ``TextAreaField`` rendered with the CKEditor 5 rich text editor.

    Use it through ``form_overrides`` and configure it with ``form_args``::

        class PostAdmin(ModelView, model=Post):
            form_overrides = {"content": CKEditor5Field}
            form_args = {"content": {"min_height": 300}}

    Assets are loaded from the CKEditor CDN. Pass ``version`` to pin a
    specific release.
    """

    editor_init_template = "sqladmin/editors/ckeditor5.html"

    def __init__(
        self,
        *args: Any,
        version: str = "39.0.1",
        min_height: int = 200,
        **kwargs: Any,
    ) -> None:
        self.version = version
        self.min_height = min_height
        super().__init__(*args, **kwargs)

    @property
    def media(self) -> FieldMedia:
        return FieldMedia(
            js=[
                f"https://cdn.ckeditor.com/ckeditor5/{self.version}/classic/ckeditor.js"
            ],
        )


class TinyMCEField(TextAreaField):
    """
    A ``TextAreaField`` rendered with the TinyMCE rich text editor.

    Requires a free API key from tiny.cloud::

        class PostAdmin(ModelView, model=Post):
            form_overrides = {"content": TinyMCEField}
            form_args = {"content": {"api_key": "your-key"}}
    """

    editor_init_template = "sqladmin/editors/tinymce.html"

    def __init__(
        self,
        *args: Any,
        api_key: str = "no-api-key",
        plugins: str = "lists link table code wordcount",
        toolbar: str = "bold italic | link | code",
        min_height: int = 200,
        **kwargs: Any,
    ) -> None:
        self.api_key = api_key
        self.plugins = plugins
        self.toolbar = toolbar
        self.min_height = min_height
        super().__init__(*args, **kwargs)

    @property
    def media(self) -> FieldMedia:
        return FieldMedia(
            js=[f"https://cdn.tiny.cloud/1/{self.api_key}/tinymce/6/tinymce.min.js"],
        )


class QuillField(TextAreaField):
    """
    A ``TextAreaField`` rendered with the Quill rich text editor.

    Quill renders into a ``<div>``; the init template hides the original
    textarea and syncs its content back on submit::

        class PostAdmin(ModelView, model=Post):
            form_overrides = {"content": QuillField}
            form_args = {"content": {"theme": "bubble"}}
    """

    editor_init_template = "sqladmin/editors/quill.html"

    def __init__(
        self,
        *args: Any,
        version: str = "2.0.2",
        theme: str = "snow",
        min_height: int = 200,
        **kwargs: Any,
    ) -> None:
        self.version = version
        self.theme = theme
        self.min_height = min_height
        super().__init__(*args, **kwargs)

    @property
    def media(self) -> FieldMedia:
        return FieldMedia(
            css=[
                f"https://cdn.jsdelivr.net/npm/quill@{self.version}/dist/quill.{self.theme}.css"
            ],
            js=[f"https://cdn.jsdelivr.net/npm/quill@{self.version}/dist/quill.js"],
        )


class SummernoteField(TextAreaField):
    """
    A ``TextAreaField`` rendered with the Summernote rich text editor.

    Built on Bootstrap 4, so it matches the admin UI. Requires jQuery, which
    is loaded automatically unless disabled::

        class PostAdmin(ModelView, model=Post):
            form_overrides = {"content": SummernoteField}
            form_args = {"content": {"min_height": 300}}
    """

    editor_init_template = "sqladmin/editors/summernote.html"
    _VERSION = "0.8.18"

    def __init__(
        self,
        *args: Any,
        include_jquery: bool = True,
        min_height: int = 200,
        **kwargs: Any,
    ) -> None:
        self.include_jquery = include_jquery
        self.min_height = min_height
        super().__init__(*args, **kwargs)

    @property
    def media(self) -> FieldMedia:
        js: List[str] = []
        if self.include_jquery:
            js.append("https://code.jquery.com/jquery-3.6.0.min.js")
        js.append(
            f"https://cdn.jsdelivr.net/npm/summernote@{self._VERSION}/dist/summernote-bs4.min.js"
        )
        return FieldMedia(
            css=[
                f"https://cdn.jsdelivr.net/npm/summernote@{self._VERSION}/dist/summernote-bs4.min.css"
            ],
            js=js,
        )
