from typing import Generator

import pytest
from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.orm import Session, declarative_base
from starlette.applications import Starlette
from starlette.testclient import TestClient
from wtforms import Form

from sqladmin import Admin, ModelView
from sqladmin.editors import (
    CKEditor5Field,
    FieldMedia,
    QuillField,
    SummernoteField,
    TinyMCEField,
    collect_form_media,
)
from tests.common import sync_engine as engine

Base = declarative_base()


class Post(Base):
    __tablename__ = "posts_editors"

    id = Column(Integer, primary_key=True)
    title = Column(String(100))
    content = Column(Text)
    summary = Column(Text)
    notes = Column(Text)


def _make_client(view_class: type[ModelView]) -> TestClient:
    local_app = Starlette()
    local_admin = Admin(app=local_app, engine=engine)
    local_admin.add_view(view_class)
    return TestClient(app=local_app, base_url="http://testserver")


def _bind(field_class: type, **kwargs: object) -> object:
    """
    Instantiate an editor field bound to a throwaway form.

    WTForms fields cannot be constructed in isolation — calling the class
    returns an UnboundField. Defining it on a Form and reading it back gives
    a real, bound field instance to assert against.
    """

    class _F(Form):
        content = field_class(**kwargs)

    return _F().content


@pytest.fixture(autouse=True)
def prepare_tables() -> Generator[None, None, None]:
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


#  FieldMedia
def test_field_media_empty_by_default() -> None:
    media = FieldMedia()
    assert media.css == []
    assert media.js == []
    assert bool(media) is False


def test_field_media_stores_assets() -> None:
    media = FieldMedia(css=["a.css"], js=["a.js"])
    assert media.css == ["a.css"]
    assert media.js == ["a.js"]
    assert bool(media) is True


def test_field_media_add_merges() -> None:
    a = FieldMedia(css=["a.css"], js=["a.js"])
    b = FieldMedia(css=["b.css"], js=["b.js"])
    merged = a + b
    assert merged.css == ["a.css", "b.css"]
    assert merged.js == ["a.js", "b.js"]


def test_field_media_add_deduplicates() -> None:
    a = FieldMedia(css=["shared.css"], js=["shared.js"])
    b = FieldMedia(css=["shared.css", "b.css"], js=["shared.js", "b.js"])
    merged = a + b
    assert merged.css == ["shared.css", "b.css"]
    assert merged.js == ["shared.js", "b.js"]


def test_field_media_add_preserves_order() -> None:
    a = FieldMedia(js=["1.js", "2.js"])
    b = FieldMedia(js=["3.js"])
    assert (a + b).js == ["1.js", "2.js", "3.js"]


#  Editor field media
def test_ckeditor5_field_media() -> None:
    field = _bind(CKEditor5Field)
    assert any("ckeditor.js" in url for url in field.media.js)


def test_ckeditor5_field_custom_version() -> None:
    field = _bind(CKEditor5Field, version="41.0.0")
    assert any("41.0.0" in url for url in field.media.js)


def test_ckeditor5_field_default_min_height() -> None:
    field = _bind(CKEditor5Field)
    assert field.min_height == 200


def test_ckeditor5_field_init_template() -> None:
    assert CKEditor5Field.editor_init_template == "sqladmin/editors/ckeditor5.html"


def test_tinymce_field_media() -> None:
    field = _bind(TinyMCEField, api_key="my-key")
    assert any("tinymce.min.js" in url for url in field.media.js)
    assert any("my-key" in url for url in field.media.js)


def test_tinymce_field_init_template() -> None:
    assert TinyMCEField.editor_init_template == "sqladmin/editors/tinymce.html"


def test_quill_field_media_has_css_and_js() -> None:
    field = _bind(QuillField)
    assert any("quill" in url for url in field.media.css)
    assert any("quill.js" in url for url in field.media.js)


def test_quill_field_bubble_theme() -> None:
    field = _bind(QuillField, theme="bubble")
    assert any("bubble" in url for url in field.media.css)
    assert field.theme == "bubble"


def test_quill_field_init_template() -> None:
    assert QuillField.editor_init_template == "sqladmin/editors/quill.html"


def test_quill_uses_safe_html_loading() -> None:
    class PostAdmin(ModelView, model=Post):
        form_overrides = {"content": QuillField}

    with _make_client(PostAdmin) as c:
        response = c.get("/admin/post/create")
    assert "clipboard.convert" in response.text
    assert "setContents" in response.text
    assert "dangerouslyPasteHTML" not in response.text


def test_summernote_field_media_includes_jquery() -> None:
    field = _bind(SummernoteField)
    assert any("jquery" in url.lower() for url in field.media.js)


def test_summernote_field_no_jquery_when_disabled() -> None:
    field = _bind(SummernoteField, include_jquery=False)
    assert not any("jquery" in url.lower() for url in field.media.js)


def test_summernote_field_uses_bs4() -> None:
    field = _bind(SummernoteField)
    summernote_js = [url for url in field.media.js if "summernote" in url][0]
    assert "bs4" in summernote_js


def test_summernote_field_init_template() -> None:
    assert SummernoteField.editor_init_template == "sqladmin/editors/summernote.html"


#  collect_form_media
class _FakeField:
    def __init__(self, media=None):
        if media is not None:
            self.media = media


def test_collect_form_media_empty_form() -> None:
    form = [_FakeField(), _FakeField()]  # no media attrs
    media = collect_form_media(form)
    assert media.css == []
    assert media.js == []


def test_collect_form_media_merges_fields() -> None:
    form = [
        _FakeField(FieldMedia(js=["a.js"])),
        _FakeField(FieldMedia(js=["b.js"])),
    ]
    media = collect_form_media(form)
    assert media.js == ["a.js", "b.js"]


def test_collect_form_media_deduplicates() -> None:
    form = [
        _FakeField(FieldMedia(js=["shared.js"])),
        _FakeField(FieldMedia(js=["shared.js"])),
    ]
    media = collect_form_media(form)
    assert media.js == ["shared.js"]


def test_collect_form_media_skips_fields_without_media() -> None:
    form = [
        _FakeField(FieldMedia(js=["a.js"])),
        _FakeField(),  # no media
    ]
    media = collect_form_media(form)
    assert media.js == ["a.js"]


#  Template rendering: CKEditor5
def test_create_page_loads_ckeditor() -> None:
    class PostAdmin(ModelView, model=Post):
        form_overrides = {"content": CKEditor5Field}

    with _make_client(PostAdmin) as c:
        response = c.get("/admin/post/create")
    assert response.status_code == 200
    assert "ckeditor.js" in response.text


def test_edit_page_loads_ckeditor() -> None:
    class PostAdmin(ModelView, model=Post):
        form_overrides = {"content": CKEditor5Field}

    with Session(engine) as session:
        post = Post(title="T", content="C")
        session.add(post)
        session.commit()
        post_id = post.id

    with _make_client(PostAdmin) as c:
        response = c.get(f"/admin/post/edit/{post_id}")
    assert response.status_code == 200
    assert "ckeditor.js" in response.text


def test_create_page_ckeditor_bootstrap_fixes() -> None:
    class PostAdmin(ModelView, model=Post):
        form_overrides = {"content": CKEditor5Field}

    with _make_client(PostAdmin) as c:
        response = c.get("/admin/post/create")
    assert "--ck-z-default" in response.text
    assert ".ck-content .table" in response.text


def test_create_page_ckeditor_custom_min_height() -> None:
    class PostAdmin(ModelView, model=Post):
        form_overrides = {"content": CKEditor5Field}
        form_args = {"content": {"min_height": 350}}

    with _make_client(PostAdmin) as c:
        response = c.get("/admin/post/create")
    assert "350" in response.text


#  Template rendering: TinyMCE
def test_create_page_loads_tinymce() -> None:
    class PostAdmin(ModelView, model=Post):
        form_overrides = {"content": TinyMCEField}
        form_args = {"content": {"api_key": "test-key"}}

    with _make_client(PostAdmin) as c:
        response = c.get("/admin/post/create")
    assert response.status_code == 200
    assert "tinymce.min.js" in response.text
    assert "test-key" in response.text
    assert "ckeditor.js" not in response.text


#  Template rendering: Quill
def test_create_page_loads_quill() -> None:
    class PostAdmin(ModelView, model=Post):
        form_overrides = {"content": QuillField}

    with _make_client(PostAdmin) as c:
        response = c.get("/admin/post/create")
    assert response.status_code == 200
    assert "quill.js" in response.text
    assert "quill.snow.css" in response.text
    assert "submit" in response.text


#  Template rendering: Summernote
def test_create_page_loads_summernote() -> None:
    class PostAdmin(ModelView, model=Post):
        form_overrides = {"content": SummernoteField}

    with _make_client(PostAdmin) as c:
        response = c.get("/admin/post/create")
    assert response.status_code == 200
    assert "summernote" in response.text
    assert "code.jquery.com" in response.text


def test_create_page_summernote_without_jquery() -> None:
    class PostAdmin(ModelView, model=Post):
        form_overrides = {"content": SummernoteField}
        form_args = {"content": {"include_jquery": False}}

    with _make_client(PostAdmin) as c:
        response = c.get("/admin/post/create")
    assert "summernote" in response.text
    assert "code.jquery.com" not in response.text


#  CDN loaded exactly once (dedup via FieldMedia)
def test_two_ckeditor_fields_load_cdn_once() -> None:
    class PostAdmin(ModelView, model=Post):
        form_overrides = {
            "content": CKEditor5Field,
            "summary": CKEditor5Field,
        }

    with _make_client(PostAdmin) as c:
        response = c.get("/admin/post/create")
    assert response.text.count("ckeditor.js") == 1


def test_two_ckeditor_fields_both_init() -> None:
    class PostAdmin(ModelView, model=Post):
        form_overrides = {
            "content": CKEditor5Field,
            "summary": CKEditor5Field,
        }

    with _make_client(PostAdmin) as c:
        response = c.get("/admin/post/create")
    # CDN once, but two init blocks (one per field)
    assert response.text.count("ckeditor.js") == 1
    assert response.text.count("ClassicEditor.create") == 2


def test_mixed_editors_each_cdn_once() -> None:
    class PostAdmin(ModelView, model=Post):
        form_overrides = {
            "content": CKEditor5Field,
            "summary": TinyMCEField,
        }

    with _make_client(PostAdmin) as c:
        response = c.get("/admin/post/create")
    assert response.text.count("ckeditor.js") == 1
    assert response.text.count("tinymce.min.js") == 1


#  No editor when no overrides
def test_no_editor_without_overrides() -> None:
    class PostAdmin(ModelView, model=Post):
        pass

    with _make_client(PostAdmin) as c:
        response = c.get("/admin/post/create")
    assert response.status_code == 200
    assert "ckeditor.js" not in response.text
    assert "tinymce" not in response.text
    assert "quill.js" not in response.text


#  form_args reaches the field
def test_form_args_passed_to_field() -> None:
    class PostAdmin(ModelView, model=Post):
        form_overrides = {"content": QuillField}
        form_args = {"content": {"theme": "bubble"}}

    with _make_client(PostAdmin) as c:
        response = c.get("/admin/post/create")
    assert "quill.bubble.css" in response.text
