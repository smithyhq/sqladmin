from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List


class RichTextEditor(ABC):
    """
    Abstract base class for rich text editor adapters.

    Implements the Strategy pattern - each subclass is a concrete strategy
    representing a different rich text editor. The Template Method pattern
    is applied through Jinja2's ``{% include %}`` in ``create.html`` and
    ``edit.html``: the rendering pipeline is always the same (load styles
    -> load scripts -> run init block), while each editor provides its own
    ``template_name`` and ``get_context()``.

    To implement a custom editor, subclass this class and provide:

    * ``template_name``- Jinja2 template path resolvable by the admin's
      template loader.
    * ``get_context()``- dict of variables available inside the template.
    * ``scripts`` - CDN JS URLs.
    * ``styles`` - CDN CSS URLs (optional).

    Example:
        ```python
        from sqladmin.editors import RichTextEditor

        class MyEditor(RichTextEditor):
            template_name = "myapp/editors/my_editor.html"

            @property
            def scripts(self) -> list[str]:
                return ["https://example.com/my-editor.js"]

            def get_context(self) -> dict:
                return {"min_height": 200}

        class PostAdmin(ModelView, model=Post):
            rich_text_fields = {"content": MyEditor()}
        ```
    """

    @property
    @abstractmethod
    def template_name(self) -> str:
        """Jinja2 template path for this editor's initialization block."""

    @abstractmethod
    def get_context(self) -> dict:
        """
        Editor-specific configuration variables passed to the template.

        These are available as top-level variables alongside ``editor``
        (the adapter instance) and ``field_ids`` (list of field names).
        """

    @property
    def styles(self) -> List[str]:
        """CDN CSS URLs to load. Defaults to empty list."""
        return []

    @property
    @abstractmethod
    def scripts(self) -> List[str]:
        """CDN JS URLs to load."""


class CKEditor5(RichTextEditor):
    """
    CKEditor 5 Classic Build adapter.

    No API key required. Bootstrap 4 z-index and table conflicts are
    patched automatically inside the template.

    Args:
        version: CKEditor 5 CDN version. Defaults to ``"39.0.1"``.
        min_height: Minimum height of the editing area in pixels.
            Defaults to ``200``.

    Example:
        ```python
        class PostAdmin(ModelView, model=Post):
            rich_text_fields = {
                "content": CKEditor5(),
                "summary": CKEditor5(min_height=300),
            }
        ```
    """

    template_name = "sqladmin/editors/ckeditor5.html"

    def __init__(self, version: str = "39.0.1", min_height: int = 200) -> None:
        self.version = version
        self.min_height = min_height

    @property
    def scripts(self) -> List[str]:
        return [
            f"https://cdn.ckeditor.com/ckeditor5/{self.version}/classic/ckeditor.js"
        ]

    def get_context(self) -> dict:
        return {"min_height": self.min_height}


class TinyMCE(RichTextEditor):
    """
    TinyMCE 6 adapter.

    Requires a free API key from tiny.cloud (1,000 loads/month on free tier).

    Args:
        api_key: API key from tiny.cloud. Defaults to ``"no-api-key"``.
        plugins: Space-separated TinyMCE plugin list.
        toolbar: TinyMCE toolbar layout string.
        min_height: Minimum editor height in pixels. Defaults to ``200``.

    Example:
        ```python
        class PostAdmin(ModelView, model=Post):
            rich_text_fields = {"content": TinyMCE(api_key="your-key")}
        ```
    """

    template_name = "sqladmin/editors/tinymce.html"

    def __init__(
        self,
        api_key: str = "no-api-key",
        plugins: str = "lists link table code wordcount",
        toolbar: str = "bold italic | link | code",
        min_height: int = 200,
    ) -> None:
        self.api_key = api_key
        self.plugins = plugins
        self.toolbar = toolbar
        self.min_height = min_height

    @property
    def scripts(self) -> List[str]:
        return [f"https://cdn.tiny.cloud/1/{self.api_key}/tinymce/6/tinymce.min.js"]

    def get_context(self) -> dict:
        return {
            "plugins": self.plugins,
            "toolbar": self.toolbar,
            "min_height": self.min_height,
        }


class QuillEditor(RichTextEditor):
    """
    Quill.js v2 adapter.

    No API key required. Quill renders into a ``<div>`` rather than
    directly into the ``<textarea>``. The template hides the original
    textarea, inserts a Quill container, and syncs the HTML back to the
    textarea on form submit so the value is included in POST data.

    Args:
        version: Quill CDN version. Defaults to ``"2.0.2"``.
        theme: ``"snow"`` (toolbar) or ``"bubble"`` (inline toolbar).
            Defaults to ``"snow"``.
        min_height: Minimum editor height in pixels. Defaults to ``200``.

    Example:
        ```python
        class PostAdmin(ModelView, model=Post):
            rich_text_fields = {"content": QuillEditor(theme="bubble")}
        ```
    """

    template_name = "sqladmin/editors/quill.html"

    def __init__(
        self,
        version: str = "2.0.2",
        theme: str = "snow",
        min_height: int = 200,
    ) -> None:
        self.version = version
        self.theme = theme
        self.min_height = min_height

    @property
    def styles(self) -> List[str]:
        return [
            f"https://cdn.jsdelivr.net/npm/quill@{self.version}/dist/quill.{self.theme}.css"
        ]

    @property
    def scripts(self) -> List[str]:
        return [f"https://cdn.jsdelivr.net/npm/quill@{self.version}/dist/quill.js"]

    def get_context(self) -> dict:
        return {"theme": self.theme, "min_height": self.min_height}


class Summernote(RichTextEditor):
    """
    Summernote 0.8.18 (Bootstrap 4) adapter.

    No API key required. Visually consistent with SQLAdmin's Tabler/Bootstrap 4
    UI. Requires jQuery; loads it automatically unless disabled.

    Args:
        include_jquery: Load jQuery from CDN. Set ``False`` if jQuery is
            already available. Defaults to ``True``.
        height: Editor height in pixels. Defaults to ``200``.

    Example:
        ```python
        class PostAdmin(ModelView, model=Post):
            rich_text_fields = {"content": Summernote(height=300)}
        ```
    """

    template_name = "sqladmin/editors/summernote.html"
    _VERSION = "0.8.18"

    def __init__(self, include_jquery: bool = True, height: int = 200) -> None:
        self.include_jquery = include_jquery
        self.height = height

    @property
    def styles(self) -> List[str]:
        return [
            f"https://cdn.jsdelivr.net/npm/summernote@{self._VERSION}/dist/summernote-bs4.min.css"
        ]

    @property
    def scripts(self) -> List[str]:
        result: List[str] = []
        if self.include_jquery:
            result.append("https://code.jquery.com/jquery-3.6.0.min.js")
        result.append(
            f"https://cdn.jsdelivr.net/npm/summernote@{self._VERSION}/dist/summernote-bs4.min.js"
        )
        return result

    def get_context(self) -> dict:
        return {"height": self.height}
