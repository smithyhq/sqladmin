from typing import Generator

import pytest
from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.orm import Session, declarative_base
from starlette.applications import Starlette
from starlette.testclient import TestClient

from sqladmin import Admin, ModelView
from sqladmin.editors import (
    CKEditor5,
    QuillEditor,
    RichTextEditor,
    Summernote,
    TinyMCE,
)
from tests.common import sync_engine as engine

Base = declarative_base()


class Post(Base):
    __tablename__ = "posts_rich_text"

    id = Column(Integer, primary_key=True)
    title = Column(String(100))
    content = Column(Text)
    summary = Column(Text)
    notes = Column(Text)


class PostAdmin(ModelView, model=Post):
    rich_text_fields = ["content", "summary"]


app = Starlette()
admin = Admin(app=app, engine=engine)
admin.add_view(PostAdmin)


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app=app, base_url="http://testserver") as c:
        yield c


@pytest.fixture(autouse=True)
def prepare_tables() -> Generator[None, None, None]:
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


def _make_client(view_class: type[ModelView]) -> TestClient:
    local_app = Starlette()
    local_admin = Admin(app=local_app, engine=engine)
    local_admin.add_view(view_class)
    return TestClient(app=local_app, base_url="http://testserver")


#  RichTextEditor base class
def test_rich_text_editor_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        RichTextEditor()


def test_rich_text_editor_styles_default_empty() -> None:
    class Minimal(RichTextEditor):
        template_name = "sqladmin/editors/ckeditor5.html"

        @property
        def scripts(self) -> list:
            return ["https://example.com/ed.js"]

        def get_context(self) -> dict:
            return {}

    assert Minimal().styles == []


def test_custom_editor_implementation() -> None:
    class MyEditor(RichTextEditor):
        template_name = "myapp/editors/my_editor.html"

        @property
        def scripts(self) -> list:
            return ["https://example.com/my.js"]

        @property
        def styles(self) -> list:
            return ["https://example.com/my.css"]

        def get_context(self) -> dict:
            return {"min_height": 250}

    editor = MyEditor()
    assert editor.template_name == "myapp/editors/my_editor.html"
    assert editor.scripts == ["https://example.com/my.js"]
    assert editor.styles == ["https://example.com/my.css"]
    assert editor.get_context() == {"min_height": 250}


def test_editor_missing_scripts_raises() -> None:
    with pytest.raises(TypeError):

        class Bad(RichTextEditor):
            template_name = "x.html"

            def get_context(self) -> dict:
                return {}

        Bad()


def test_editor_missing_template_name_raises() -> None:
    with pytest.raises(TypeError):

        class Bad(RichTextEditor):
            @property
            def scripts(self) -> list:
                return []

            def get_context(self) -> dict:
                return {}

        Bad()


def test_editor_missing_get_context_raises() -> None:
    with pytest.raises(TypeError):

        class Bad(RichTextEditor):
            template_name = "x.html"

            @property
            def scripts(self) -> list:
                return []

        Bad()


#  CKEditor5
def test_ckeditor5_template_name() -> None:
    assert CKEditor5().template_name == "sqladmin/editors/ckeditor5.html"


def test_ckeditor5_default_version() -> None:
    assert "39.0.1" in CKEditor5().scripts[0]


def test_ckeditor5_custom_version() -> None:
    assert "41.0.0" in CKEditor5(version="41.0.0").scripts[0]


def test_ckeditor5_scripts_url() -> None:
    assert CKEditor5(version="39.0.1").scripts == [
        "https://cdn.ckeditor.com/ckeditor5/39.0.1/classic/ckeditor.js"
    ]


def test_ckeditor5_styles_empty() -> None:
    assert CKEditor5().styles == []


def test_ckeditor5_default_min_height() -> None:
    assert CKEditor5().get_context()["min_height"] == 200


def test_ckeditor5_custom_min_height() -> None:
    assert CKEditor5(min_height=350).get_context()["min_height"] == 350


#  TinyMCE
def test_tinymce_template_name() -> None:
    assert TinyMCE().template_name == "sqladmin/editors/tinymce.html"


def test_tinymce_default_api_key() -> None:
    assert "no-api-key" in TinyMCE().scripts[0]


def test_tinymce_custom_api_key() -> None:
    assert "my-key" in TinyMCE(api_key="my-key").scripts[0]


def test_tinymce_cdn_domain() -> None:
    assert "cdn.tiny.cloud" in TinyMCE().scripts[0]


def test_tinymce_styles_empty() -> None:
    assert TinyMCE().styles == []


def test_tinymce_context() -> None:
    context = TinyMCE().get_context()
    assert "plugins" in context
    assert "toolbar" in context
    assert context["min_height"] == 200


def test_tinymce_custom_plugins() -> None:
    assert TinyMCE(plugins="link image").get_context()["plugins"] == "link image"


def test_tinymce_custom_toolbar() -> None:
    assert TinyMCE(toolbar="bold | italic").get_context()["toolbar"] == "bold | italic"


#  QuillEditor
def test_quill_template_name() -> None:
    assert QuillEditor().template_name == "sqladmin/editors/quill.html"


def test_quill_default_version() -> None:
    editor = QuillEditor()
    assert "2.0.2" in editor.scripts[0]
    assert "2.0.2" in editor.styles[0]


def test_quill_default_theme_snow() -> None:
    assert "snow" in QuillEditor().styles[0]


def test_quill_bubble_theme() -> None:
    editor = QuillEditor(theme="bubble")
    assert "bubble" in editor.styles[0]
    assert editor.get_context()["theme"] == "bubble"


def test_quill_cdn_domain() -> None:
    editor = QuillEditor()
    assert "cdn.jsdelivr.net" in editor.scripts[0]
    assert "cdn.jsdelivr.net" in editor.styles[0]


def test_quill_context_keys() -> None:
    assert set(QuillEditor().get_context().keys()) == {"theme", "min_height"}


#  Summernote
def test_summernote_template_name() -> None:
    assert Summernote().template_name == "sqladmin/editors/summernote.html"


def test_summernote_default_includes_jquery() -> None:
    assert any("jquery" in url.lower() for url in Summernote().scripts)


def test_summernote_no_jquery_when_disabled() -> None:
    scripts = Summernote(include_jquery=False).scripts
    assert not any("jquery" in url.lower() for url in scripts)


def test_summernote_scripts_count_with_jquery() -> None:
    assert len(Summernote(include_jquery=True).scripts) == 2


def test_summernote_scripts_count_without_jquery() -> None:
    assert len(Summernote(include_jquery=False).scripts) == 1


def test_summernote_uses_bs4_build() -> None:
    summernote_script = [url for url in Summernote().scripts if "summernote" in url][0]
    assert "bs4" in summernote_script


def test_summernote_default_height() -> None:
    assert Summernote().get_context()["height"] == 200


def test_summernote_custom_height() -> None:
    assert Summernote(height=450).get_context()["height"] == 450


#  ModelView._rich_text_map
def test_rich_text_fields_default_empty() -> None:
    class EmptyAdmin(ModelView, model=Post):
        pass

    assert EmptyAdmin.rich_text_fields == []
    assert EmptyAdmin()._rich_text_map == {}


def test_rich_text_map_list_form_uses_ckeditor5() -> None:
    class ListAdmin(ModelView, model=Post):
        rich_text_fields = ["content", "summary"]

    rich_map = ListAdmin()._rich_text_map
    assert set(rich_map.keys()) == {"content", "summary"}
    assert all(isinstance(editor, CKEditor5) for editor in rich_map.values())


def test_rich_text_map_list_form_fresh_instance_per_field() -> None:
    class ListAdmin(ModelView, model=Post):
        rich_text_fields = ["content", "summary"]

    rich_map = ListAdmin()._rich_text_map
    assert rich_map["content"] is not rich_map["summary"]


def test_rich_text_map_dict_form_returned_as_is() -> None:
    content_editor = CKEditor5(min_height=100)
    summary_editor = TinyMCE()

    class DictAdmin(ModelView, model=Post):
        rich_text_fields = {"content": content_editor, "summary": summary_editor}

    rich_map = DictAdmin()._rich_text_map
    assert rich_map["content"] is content_editor
    assert rich_map["summary"] is summary_editor


def test_rich_text_map_does_not_bleed_between_views() -> None:
    class AdminA(ModelView, model=Post):
        rich_text_fields = ["content"]

    class AdminB(ModelView, model=Post):
        pass

    assert "content" in AdminA()._rich_text_map
    assert AdminB()._rich_text_map == {}


#  Text column validation
def test_rich_text_map_text_columns_allowed() -> None:
    class TextAdmin(ModelView, model=Post):
        rich_text_fields = ["content", "summary", "notes"]

    assert set(TextAdmin()._rich_text_map.keys()) == {"content", "summary", "notes"}


def test_rich_text_map_string_column_raises_list_form() -> None:
    class StringAdmin(ModelView, model=Post):
        rich_text_fields = ["title"]

    with pytest.raises(ValueError, match="must be backed by a Text"):
        _ = StringAdmin()._rich_text_map


def test_rich_text_map_string_column_raises_dict_form() -> None:
    class StringAdmin(ModelView, model=Post):
        rich_text_fields = {"title": CKEditor5()}

    with pytest.raises(ValueError, match="must be backed by a Text"):
        _ = StringAdmin()._rich_text_map


def test_rich_text_map_error_message_includes_field_and_type() -> None:
    class StringAdmin(ModelView, model=Post):
        rich_text_fields = ["title"]

    with pytest.raises(ValueError) as exc_info:
        _ = StringAdmin()._rich_text_map

    message = str(exc_info.value)
    assert "title" in message
    assert "String" in message


def test_rich_text_map_mixed_valid_invalid_raises() -> None:
    class MixedAdmin(ModelView, model=Post):
        rich_text_fields = ["content", "title"]

    with pytest.raises(ValueError, match="title"):
        _ = MixedAdmin()._rich_text_map


def test_rich_text_map_unknown_field_does_not_raise() -> None:
    class UnknownAdmin(ModelView, model=Post):
        rich_text_fields = ["nonexistent_field"]

    assert "nonexistent_field" in UnknownAdmin()._rich_text_map


#  ModelView._rich_text_assets
def test_rich_text_assets_empty_when_no_fields() -> None:
    class EmptyAdmin(ModelView, model=Post):
        pass

    assert EmptyAdmin()._rich_text_assets == {"scripts": [], "styles": []}


def test_rich_text_assets_single_editor() -> None:
    class SingleAdmin(ModelView, model=Post):
        rich_text_fields = ["content"]

    scripts = SingleAdmin()._rich_text_assets["scripts"]
    assert len(scripts) == 1
    assert "ckeditor.js" in scripts[0]


def test_rich_text_assets_deduplicates_distinct_instances() -> None:
    class DedupAdmin(ModelView, model=Post):
        rich_text_fields = {"content": CKEditor5(), "summary": CKEditor5()}

    scripts = DedupAdmin()._rich_text_assets["scripts"]
    assert len([s for s in scripts if "ckeditor.js" in s]) == 1


def test_rich_text_assets_different_editors_each_listed() -> None:
    class MixedAdmin(ModelView, model=Post):
        rich_text_fields = {"content": CKEditor5(), "summary": TinyMCE()}

    scripts = MixedAdmin()._rich_text_assets["scripts"]
    assert len([s for s in scripts if "ckeditor.js" in s]) == 1
    assert len([s for s in scripts if "tinymce" in s]) == 1


def test_rich_text_assets_includes_quill_styles() -> None:
    class QuillAdmin(ModelView, model=Post):
        rich_text_fields = {"content": QuillEditor()}

    styles = QuillAdmin()._rich_text_assets["styles"]
    assert any("quill" in s for s in styles)


#  ModelView._rich_text_groups
def test_rich_text_groups_empty_when_no_fields() -> None:
    class EmptyAdmin(ModelView, model=Post):
        pass

    assert EmptyAdmin()._rich_text_groups == []


def test_rich_text_groups_same_instance_one_group() -> None:
    shared = CKEditor5()

    class SharedAdmin(ModelView, model=Post):
        rich_text_fields = {"content": shared, "summary": shared}

    groups = SharedAdmin()._rich_text_groups
    assert len(groups) == 1
    assert set(groups[0]["field_ids"]) == {"content", "summary"}
    assert groups[0]["editor"] is shared


def test_rich_text_groups_distinct_instances_two_groups() -> None:
    class DistinctAdmin(ModelView, model=Post):
        rich_text_fields = {"content": CKEditor5(), "summary": CKEditor5()}

    assert len(DistinctAdmin()._rich_text_groups) == 2


def test_rich_text_groups_mixed_editors() -> None:
    ckeditor = CKEditor5()
    tinymce = TinyMCE()

    class MixedAdmin(ModelView, model=Post):
        rich_text_fields = {
            "content": ckeditor,
            "summary": ckeditor,
            "notes": tinymce,
        }

    groups = MixedAdmin()._rich_text_groups
    assert len(groups) == 2
    by_type = {type(group["editor"]).__name__: group for group in groups}
    assert set(by_type["CKEditor5"]["field_ids"]) == {"content", "summary"}
    assert by_type["TinyMCE"]["field_ids"] == ["notes"]


#  Template rendering: CKEditor5
def test_create_page_loads_ckeditor(client: TestClient) -> None:
    response = client.get("/admin/post/create")
    assert response.status_code == 200
    assert "ckeditor.js" in response.text


def test_edit_page_loads_ckeditor(client: TestClient) -> None:
    with Session(engine) as session:
        post = Post(title="T", content="C", summary="S")
        session.add(post)
        session.commit()
        post_id = post.id

    response = client.get(f"/admin/post/edit/{post_id}")
    assert response.status_code == 200
    assert "ckeditor.js" in response.text


def test_create_page_contains_field_ids(client: TestClient) -> None:
    response = client.get("/admin/post/create")
    assert "content" in response.text
    assert "summary" in response.text


def test_create_page_contains_bootstrap_z_index_fix(client: TestClient) -> None:
    response = client.get("/admin/post/create")
    assert "--ck-z-default" in response.text


def test_create_page_contains_bootstrap_table_fix(client: TestClient) -> None:
    response = client.get("/admin/post/create")
    assert ".ck-content .table" in response.text


def test_create_page_custom_min_height() -> None:
    class CustomAdmin(ModelView, model=Post):
        rich_text_fields = {"content": CKEditor5(min_height=350)}

    with _make_client(CustomAdmin) as c:
        response = c.get("/admin/post/create")
    assert "350" in response.text


#  Template rendering: TinyMCE
def test_create_page_loads_tinymce() -> None:
    class TinyAdmin(ModelView, model=Post):
        rich_text_fields = {"content": TinyMCE(api_key="test-key")}

    with _make_client(TinyAdmin) as c:
        response = c.get("/admin/post/create")
    assert response.status_code == 200
    assert "tinymce.min.js" in response.text
    assert "test-key" in response.text
    assert "ckeditor.js" not in response.text


#  Template rendering: QuillEditor
def test_create_page_loads_quill() -> None:
    class QuillAdmin(ModelView, model=Post):
        rich_text_fields = {"content": QuillEditor()}

    with _make_client(QuillAdmin) as c:
        response = c.get("/admin/post/create")
    assert response.status_code == 200
    assert "quill.js" in response.text
    assert "quill.snow.css" in response.text
    assert "submit" in response.text
    assert "innerHTML" in response.text


#  Template rendering: Summernote
def test_create_page_loads_summernote() -> None:
    class SummernoteAdmin(ModelView, model=Post):
        rich_text_fields = {"content": Summernote()}

    with _make_client(SummernoteAdmin) as c:
        response = c.get("/admin/post/create")
    assert response.status_code == 200
    assert "summernote" in response.text
    assert "jquery" in response.text.lower()


def test_create_page_summernote_without_jquery() -> None:
    class SummernoteAdmin(ModelView, model=Post):
        rich_text_fields = {"content": Summernote(include_jquery=False)}

    with _make_client(SummernoteAdmin) as c:
        response = c.get("/admin/post/create")
    assert "summernote" in response.text
    # The adapter must not inject its own jQuery CDN. The admin layout itself
    # may already include jQuery, so we check for the specific CDN URL the
    # adapter would add, not the generic word "jquery".
    assert "code.jquery.com" not in response.text


#  CDN loaded exactly once (regression)
def test_same_instance_loads_cdn_once() -> None:
    shared = CKEditor5()

    class SharedAdmin(ModelView, model=Post):
        rich_text_fields = {"content": shared, "summary": shared}

    with _make_client(SharedAdmin) as c:
        response = c.get("/admin/post/create")
    assert response.text.count("ckeditor.js") == 1


def test_distinct_instances_load_cdn_once() -> None:
    class DistinctAdmin(ModelView, model=Post):
        rich_text_fields = {
            "content": CKEditor5(min_height=200),
            "summary": CKEditor5(min_height=400),
        }

    with _make_client(DistinctAdmin) as c:
        response = c.get("/admin/post/create")
    assert response.text.count("ckeditor.js") == 1
    assert "200" in response.text
    assert "400" in response.text


def test_mixed_editors_load_each_cdn_once() -> None:
    ckeditor = CKEditor5()
    tinymce = TinyMCE()

    class MixedAdmin(ModelView, model=Post):
        rich_text_fields = {
            "content": ckeditor,
            "summary": ckeditor,
            "notes": tinymce,
        }

    with _make_client(MixedAdmin) as c:
        response = c.get("/admin/post/create")
    assert response.text.count("ckeditor.js") == 1
    assert response.text.count("tinymce.min.js") == 1


#  No editor when fields empty
def test_no_editor_when_fields_empty() -> None:
    class EmptyAdmin(ModelView, model=Post):
        pass

    with _make_client(EmptyAdmin) as c:
        response = c.get("/admin/post/create")
    assert response.status_code == 200
    assert "ckeditor.js" not in response.text
    assert "tinymce" not in response.text
    assert "quill.js" not in response.text
    assert "summernote" not in response.text


#  List vs dict form parity
def test_list_form_renders_editor() -> None:
    class ListAdmin(ModelView, model=Post):
        rich_text_fields = ["content"]

    with _make_client(ListAdmin) as c:
        assert "ckeditor.js" in c.get("/admin/post/create").text


def test_dict_form_renders_correct_editor_per_field() -> None:
    class DictAdmin(ModelView, model=Post):
        rich_text_fields = {"content": CKEditor5(), "summary": TinyMCE()}

    with _make_client(DictAdmin) as c:
        response = c.get("/admin/post/create")
    assert "ckeditor.js" in response.text
    assert "tinymce.min.js" in response.text
