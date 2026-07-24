import re
from typing import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Column, ForeignKey, Integer, String, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base, foreign, relationship, selectinload
from sqlalchemy.sql.elements import ColumnElement
from starlette.applications import Starlette
from starlette.requests import Request

from sqladmin import Admin, ModelView
from sqladmin.ajax import AjaxWhereClause, QueryAjaxModelLoader, create_ajax_loader
from tests.common import async_engine as engine

pytestmark = pytest.mark.anyio

Base = declarative_base()
session_maker = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)

app = Starlette()
admin = Admin(app=app, engine=engine)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(String(length=16))

    addresses = relationship("Address", back_populates="user")
    rooms = relationship("Room", back_populates="user")

    def __str__(self) -> str:
        return f"User {self.id}"


class City(Base):
    __tablename__ = "cities"

    id = Column(Integer, primary_key=True)
    name = Column(String(length=16))
    state = Column(String(length=3))

    addresses = relationship("Address", back_populates="city")
    rooms = relationship("Room", back_populates="city")

    def __str__(self) -> str:
        return f"{self.name}, {self.state}"


class Address(Base):
    __tablename__ = "addresses"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    city_id = Column(Integer, ForeignKey("cities.id"))

    user = relationship("User", back_populates="addresses")
    city = relationship("City", back_populates="addresses")

    def __str__(self) -> str:
        return f"Address {self.id}"


class Room(Base):
    __tablename__ = "rooms"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    city_id = Column(Integer, ForeignKey("cities.id"))

    user = relationship("User", back_populates="rooms")
    city = relationship("City", back_populates="rooms")


class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True)
    name = Column(String(length=32), nullable=False)

    def __str__(self) -> str:
        return f"Team {self.id}"


class Member(Base):
    __tablename__ = "members"

    id = Column(Integer, primary_key=True)
    name = Column(String(length=32), nullable=False)
    team_id = Column(Integer, ForeignKey("teams.id"))

    team = relationship("Team")


class CompositeTag(Base):
    __tablename__ = "composite_tags"

    key = Column(String(length=16), primary_key=True)
    locale = Column(String(length=8), primary_key=True)
    label = Column(String(length=32), nullable=False)

    def __str__(self) -> str:
        return f"{self.label}:{self.key}:{self.locale}"


class MissedField(Base):
    __tablename__ = "missed_field"

    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey("teams.id"))

    team = relationship("Team")


class ParentMissmatchIdsField(Base):
    __tablename__ = "parent_missmatch_ids_field"

    id = Column(Integer, ForeignKey("teams.id"), primary_key=True)

    missmatch_ids_field = relationship(
        "MissmatchIdsField",
        primaryjoin=lambda: or_(
            ParentMissmatchIdsField.id == foreign(MissmatchIdsField.team_1_id),
            ParentMissmatchIdsField.id == foreign(MissmatchIdsField.team_2_id),
        ),
        viewonly=True,
    )


class MissmatchIdsField(Base):
    __tablename__ = "missmatch_ids_field"

    team_1_id = Column(Integer, ForeignKey("teams.id"), primary_key=True)
    team_2_id = Column(Integer, ForeignKey("teams.id"), primary_key=True)

    team_1 = relationship("Team", foreign_keys=[team_1_id])
    team_2 = relationship("Team", foreign_keys=[team_2_id])


class UserAdmin(ModelView, model=User):
    form_ajax_refs = {
        "addresses": {
            "fields": ("id",),
        }
    }


class AddressAdmin(ModelView, model=Address):
    form_ajax_refs = {
        "user": {
            "fields": ("name",),
            "order_by": ("id"),
        },
        "city": {
            "fields": ("name", "state"),
            "order_by": ["state", "id"],
            "limit": 2,
        },
    }


class RoomAdmin(ModelView, model=Room):
    form_ajax_refs = {
        "user": {"fields": ("name",), "order_by": ("id"), "limit": 3},
        "city": {
            "fields": ("name", "state"),
            "order_by": ["state", "name"],
            "limit": 2,
        },
    }


class TeamAjaxWhereClause(AjaxWhereClause):
    async def __call__(self, request: Request, term: str) -> ColumnElement:
        return Team.name != "BB"


class MemberAdmin(ModelView, model=Member):
    form_ajax_refs = {
        "team": {
            "fields": ("name",),
            "where": TeamAjaxWhereClause(),
        }
    }


admin.add_view(UserAdmin)
admin.add_view(AddressAdmin)
admin.add_view(RoomAdmin)
admin.add_view(MemberAdmin)


@pytest.fixture(autouse=True)
async def prepare_database() -> AsyncGenerator[None, None]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


async def test_ajax_lookup_invalid_query_params(client: AsyncClient) -> None:
    response = await client.get("/admin/user/ajax/lookup")
    assert response.status_code == 400

    response = await client.get("/admin/address/ajax/lookup")
    assert response.status_code == 400

    response = await client.get("/admin/user/ajax/lookup?name=test&term=x")
    assert response.status_code == 400


async def test_ajax_response_test(client: AsyncClient) -> None:
    user = User(name="John Snow")
    async with session_maker() as s:
        s.add(user)
        await s.commit()

    response = await client.get("/admin/address/ajax/lookup?name=user&term=john")

    assert response.status_code == 200
    assert response.json() == {"results": [{"id": "1", "text": "User 1"}]}


async def test_ajax_response_order_by(client: AsyncClient) -> None:
    async with session_maker() as s:
        s.add(City(name="Sydney", state="NSW"))
        s.add(City(name="Melbourne", state="VIC"))
        s.add(City(name="Newcastle", state="NSW"))
        s.add(City(name="Byron Bay", state="NSW"))
        s.add(City(name="Melbourne", state="TAS"))
        await s.commit()

    response = await client.get("/admin/address/ajax/lookup?name=city&term=nsw")
    # Sorted by state then id
    assert response.status_code == 200
    assert response.json() == {
        "results": [
            {"id": "1", "text": "Sydney, NSW"},
            {"id": "3", "text": "Newcastle, NSW"},
        ]
    }

    response = await client.get("/admin/room/ajax/lookup?name=city&term=nsw")
    # Sorted by state then name
    assert response.status_code == 200
    assert response.json() == {
        "results": [
            {"id": "4", "text": "Byron Bay, NSW"},
            {"id": "3", "text": "Newcastle, NSW"},
        ]
    }
    response = await client.get("/admin/room/ajax/lookup?name=city&term=melb")
    # Sorted by state then name
    assert response.status_code == 200
    assert response.json() == {
        "results": [
            {"id": "5", "text": "Melbourne, TAS"},
            {"id": "2", "text": "Melbourne, VIC"},
        ]
    }


async def test_ajax_response_limit(client: AsyncClient) -> None:
    users_to_create = 5
    user_list = [User(name=f"John Snow {i}") for i in range(users_to_create)]
    async with session_maker() as s:
        for user in user_list:
            s.add(user)
        await s.commit()

    response = await client.get("/admin/address/ajax/lookup?name=user&term=john")

    assert response.status_code == 200
    # Address admin has no limit so will return all created users
    # (up to default cap of 10)
    assert response.json() == {
        "results": [
            {"id": f"{i + 1}", "text": f"User {i + 1}"} for i in range(users_to_create)
        ]
    }

    response = await client.get("/admin/room/ajax/lookup?name=user&term=john")

    assert response.status_code == 200
    # Room admin has a limit 3 of
    assert response.json() == {
        "results": [{"id": f"{i + 1}", "text": f"User {i + 1}"} for i in range(3)]
    }


async def test_create_ajax_loader_exceptions() -> None:
    with pytest.raises(ValueError):
        create_ajax_loader(model_admin=AddressAdmin(), name="x", options={})

    with pytest.raises(ValueError):
        create_ajax_loader(model_admin=AddressAdmin(), name="user", options={})


async def test_nullable_multi_select_ajax_field_does_not_allow_clear(
    client: AsyncClient,
) -> None:
    response = await client.get("/admin/user/create")

    # Multi-select AJAX fields should never have data-allow-blank,
    # even if allow_blank=True in the field definition
    assert 'data-role="select2-ajax"' in response.text
    assert 'multiple="1"' in response.text
    assert 'data-allow-blank="1"' not in response.text


async def test_create_page_template(client: AsyncClient) -> None:
    response = await client.get("/admin/user/create")

    assert 'data-json="[]"' in response.text
    assert 'data-role="select2-ajax"' in response.text
    assert 'data-url="http://testserver/admin/user/ajax/lookup"' in response.text
    assert 'data-allow-blank="1"' not in response.text

    response = await client.get("/admin/address/create")

    assert 'data-role="select2-ajax"' in response.text
    assert 'data-url="http://testserver/admin/address/ajax/lookup"' in response.text
    assert 'data-allow-blank="1"' in response.text


async def test_edit_page_template(client: AsyncClient) -> None:
    user = User(name="John Snow")
    async with session_maker() as s:
        s.add(user)
        await s.flush()

        address = Address(user=user)
        s.add(address)
        await s.commit()

    response = await client.get("/admin/user/edit/1")
    assert (
        'data-json="[{&#34;id&#34;: &#34;1&#34;, &#34;text&#34;: &#34;Address 1&#34;}]"'
        in response.text
    )
    assert 'data-role="select2-ajax"' in response.text
    assert 'data-url="http://testserver/admin/user/ajax/lookup"' in response.text

    response = await client.get("/admin/address/edit/1")
    assert (
        'data-json="[{&#34;id&#34;: &#34;1&#34;, &#34;text&#34;: &#34;User 1&#34;}]"'
        in response.text
    )
    assert 'data-role="select2-ajax"' in response.text
    assert 'data-url="http://testserver/admin/address/ajax/lookup"' in response.text
    assert 'data-allow-blank="1"' in response.text


async def test_create_and_edit_forms(client: AsyncClient) -> None:
    response = await client.post("/admin/address/create", data={})
    assert response.status_code == 302
    response = await client.post("/admin/address/create", data={"id": "2"})
    assert response.status_code == 302

    data = {"addresses": ["1"], "name": "Tyrion"}
    response = await client.post("/admin/user/create", data=data)
    assert response.status_code == 302

    data = {}
    response = await client.post("/admin/address/edit/1", data=data)
    assert response.status_code == 302

    async with session_maker() as s:
        stmt = select(User).options(selectinload(User.addresses))
        result = await s.execute(stmt)
        address = await s.get(Address, 1)

    user = result.scalar_one()
    assert len(user.addresses) == 0
    assert address is not None
    assert address.user_id is None

    data = {"addresses": ["1"]}
    response = await client.post("/admin/user/edit/1", data=data)
    assert response.status_code == 302

    async with session_maker() as s:
        stmt = select(User).options(selectinload(User.addresses))
        result = await s.execute(stmt)

    user = result.scalar_one()
    assert len(user.addresses) == 1

    data = {"addresses": ["1", "2"]}
    response = await client.post("/admin/user/edit/1", data=data)
    assert response.status_code == 302

    async with session_maker() as s:
        stmt = select(User).options(selectinload(User.addresses))
        result = await s.execute(stmt)

    user = result.scalar_one()
    assert len(user.addresses) == 2


async def test_edit_validation_error_preserves_selected_ajax_value(
    client: AsyncClient,
) -> None:
    async with session_maker() as s:
        s.add_all([Team(name="A"), Team(name="B")])
        await s.commit()

    async with session_maker() as s:
        member = Member(name="John", team_id=1)
        s.add(member)
        await s.commit()

    response = await client.post(
        "/admin/member/edit/1",
        data={"name": "", "team": "2"},
    )

    assert response.status_code == 400
    assert (
        'data-json="[{&#34;id&#34;: &#34;2&#34;, &#34;text&#34;: &#34;Team 2&#34;}]"'
        in response.text
    )


async def test_ajax_where_condition(
    client: AsyncClient,
) -> None:
    """It was supposed to return two records, but the filter dropped one"""

    async with session_maker() as s:
        s.add_all([Team(name="AB"), Team(name="BB")])
        await s.commit()

    async with session_maker() as s:
        member = Member(name="John", team_id=1)
        s.add(member)
        await s.commit()

    response = await client.get("/admin/member/ajax/lookup?name=team&term=B")

    assert response.status_code == 200
    assert '{"results":[{"id":"1","text":"Team 1"}]}' == response.text


async def test_format_by_pk_single_pk() -> None:
    async with session_maker() as s:
        user = User(name="Arya")
        s.add(user)
        await s.commit()

    loader = QueryAjaxModelLoader(
        name="user",
        model=User,
        model_admin=UserAdmin(),
        fields=("name",),
    )

    assert await loader.format_by_pk(1) == {"id": "1", "text": "User 1"}


async def test_format_by_pk_composite_pk_identifier() -> None:
    async with session_maker() as s:
        tag = CompositeTag(key="greeting", locale="en", label="Hello")
        s.add(tag)
        await s.commit()

    loader = QueryAjaxModelLoader(
        name="composite",
        model=CompositeTag,
        model_admin=UserAdmin(),
        fields=("label",),
    )

    assert await loader.format_by_pk("greeting;en") == {
        "id": "greeting;en",
        "text": "Hello:greeting:en",
    }


async def test_format_by_pk_returns_empty_for_missing_record() -> None:
    loader = QueryAjaxModelLoader(
        name="user",
        model=User,
        model_admin=UserAdmin(),
        fields=("name",),
    )

    assert await loader.format_by_pk("999") == {}


async def test_missed_field_in_ajax() -> None:
    class MissedFieldAdmin(ModelView, model=MissedField):
        form_ajax_refs = {
            "team": {
                "fields": ("error",),
            }
        }

    with pytest.raises(ValueError, match="error does not exist"):
        admin.add_view(MissedFieldAdmin)


async def test_ajax_where_clause_valid_override(client: AsyncClient) -> None:
    class AjaxWhereClauseValidOverride(Base):
        __tablename__ = "AjaxWhereClauseValidOverride"
        id = Column(Integer, primary_key=True)
        team_id = Column(Integer, ForeignKey("teams.id"))
        team = relationship("Team")

    class AjaxWhereClauseValidOverrideAdmin(
        ModelView, model=AjaxWhereClauseValidOverride
    ):
        class WhereClause(AjaxWhereClause):
            async def __call__(self, request: Request, term: str) -> ColumnElement:
                return Team.id == 1

        form_ajax_refs = {"team": {"fields": ("id",), "where": WhereClause()}}

    admin.add_view(AjaxWhereClauseValidOverrideAdmin)

    identity = AjaxWhereClauseValidOverrideAdmin().identity
    response = await client.get(f"/admin/{identity}/ajax/lookup?name=team&term=abc")

    assert response.status_code == 200
    assert response.text == '{"results":[]}'


async def test_ajax_where_clause_invalid_call_function_return(
    client: AsyncClient,
) -> None:
    class AjaxWhereClauseInvalidCallFunctionReturn(Base):
        __tablename__ = "AjaxWhereClauseInvalidCallFunctionReturn"
        id = Column(Integer, primary_key=True)
        team_id = Column(Integer, ForeignKey("teams.id"))
        team = relationship("Team")

    class AjaxWhereClauseInvalidCallFunctionReturnAdmin(
        ModelView, model=AjaxWhereClauseInvalidCallFunctionReturn
    ):
        class WhereClause(AjaxWhereClause):
            async def __call__(self, request: Request, term: str) -> ColumnElement:
                return "id = 1"

        form_ajax_refs = {"team": {"fields": ("id",), "where": WhereClause()}}

    admin.add_view(AjaxWhereClauseInvalidCallFunctionReturnAdmin)
    error_msg = (
        "WhereClause.__call__ function should return value of type ColumnElement."
    )
    with pytest.raises(ValueError, match=re.escape(error_msg)):
        identity = AjaxWhereClauseInvalidCallFunctionReturnAdmin().identity
        await client.get(f"/admin/{identity}/ajax/lookup?name=team&term=abc")


async def test_ajax_where_clause_invalid_class() -> None:
    class AjaxWhereClauseInvalidClass(Base):
        __tablename__ = "AjaxWhereClauseInvalidClass"
        id = Column(Integer, primary_key=True)
        team_id = Column(Integer, ForeignKey("teams.id"))
        team = relationship("Team")

    class AjaxWhereClauseInvalidClassAdmin(
        ModelView, model=AjaxWhereClauseInvalidClass
    ):
        form_ajax_refs = {"team": {"fields": ("id",), "where": "error"}}

    error_msg = '"where" option should be is instance of subclass AjaxWhereClause'
    with pytest.raises(ValueError, match=re.escape(error_msg)):
        admin.add_view(AjaxWhereClauseInvalidClassAdmin)


async def test_fields_not_str_in_ajax() -> None:
    class MissedFieldAdmin(ModelView, model=MissedField):
        form_ajax_refs = {
            "team": {
                "fields": (MissedField.id,),
            }
        }

    assert MissedFieldAdmin()._form_ajax_refs["team"]._cached_fields == [MissedField.id]


async def test_format_by_pk_with_empty_pk_in_ajax() -> None:
    class MissedFieldAdmin(ModelView, model=MissedField):
        form_ajax_refs = {
            "team": {
                "fields": (MissedField.id,),
            }
        }

    assert await MissedFieldAdmin()._form_ajax_refs["team"].format_by_pk(None) == {}


async def test_format_by_pk_missmatch_pk_count_in_ajax() -> None:
    async with session_maker() as s:
        s.add_all(
            [
                Team(id=1, name="A"),
                Team(id=2, name="B"),
                MissmatchIdsField(team_1_id=1, team_2_id=2),
            ]
        )
        await s.commit()

    class ParentMissmatchIdsFieldAdmin(ModelView, model=ParentMissmatchIdsField):
        form_ajax_refs = {
            "missmatch_ids_field": {
                "fields": (MissmatchIdsField.team_1_id, MissmatchIdsField.team_2_id),
            }
        }

    admin.add_view(ParentMissmatchIdsFieldAdmin)
    assert (
        await ParentMissmatchIdsFieldAdmin()
        ._form_ajax_refs["missmatch_ids_field"]
        .format_by_pk("1")
    ) == {}


async def test_format_by_pk_many_pks_in_ajax() -> None:
    async with session_maker() as s:
        s.add_all(
            [
                Team(id=1, name="A"),
                Team(id=2, name="B"),
                MissmatchIdsField(team_1_id=1, team_2_id=2),
            ]
        )
        await s.commit()

    class ParentMissmatchIdsFieldAdmin(ModelView, model=ParentMissmatchIdsField):
        form_ajax_refs = {
            "missmatch_ids_field": {
                "fields": (MissmatchIdsField.team_1_id, MissmatchIdsField.team_2_id),
            }
        }

    admin.add_view(ParentMissmatchIdsFieldAdmin)
    assert (
        await ParentMissmatchIdsFieldAdmin()
        ._form_ajax_refs["missmatch_ids_field"]
        .format_by_pk("1;2")
    )["id"] == "1;2"


async def test_format_by_pk_with_wrong_pk_in_ajax() -> None:
    class MissedFieldAdmin(ModelView, model=MissedField):
        form_ajax_refs = {"team": {"fields": (Team.id,), "order_by": Team.id}}

    admin.add_view(MissedFieldAdmin)
    assert await MissedFieldAdmin()._form_ajax_refs["team"].format_by_pk(123) == {}


async def test_order_by_iterable_in_ajax() -> None:
    class MissedFieldAdmin(ModelView, model=MissedField):
        form_ajax_refs = {
            "team": {"fields": (MissedField.id,), "order_by": [MissedField.id]}
        }

    admin.add_view(MissedFieldAdmin)

    assert (
        MissedFieldAdmin()._form_ajax_refs["team"]._cached_fields_order_by[0].key
        == "id"
    )


async def test_order_by_in_ajax() -> None:
    class MissedFieldAdmin(ModelView, model=MissedField):
        form_ajax_refs = {
            "team": {"fields": (MissedField.id,), "order_by": MissedField.id}
        }

    admin.add_view(MissedFieldAdmin)

    assert (
        MissedFieldAdmin()._form_ajax_refs["team"]._cached_fields_order_by[0].key
        == "id"
    )


async def test_order_by_desc_in_ajax() -> None:
    class MissedFieldAdmin(ModelView, model=MissedField):
        form_ajax_refs = {
            "team": {"fields": (MissedField.id,), "order_by": MissedField.id.desc()}
        }

    admin.add_view(MissedFieldAdmin)

    assert len(MissedFieldAdmin()._form_ajax_refs["team"]._cached_fields_order_by) == 1


async def test_order_by_relationship_in_ajax() -> None:
    class MissedFieldAdmin(ModelView, model=MissedField):
        form_ajax_refs = {
            "team": {"fields": (MissedField.id,), "order_by": MissedField.team}
        }

    admin.add_view(MissedFieldAdmin)

    assert len(MissedFieldAdmin()._form_ajax_refs["team"]._cached_fields_order_by) == 1


async def test_order_by_func_in_ajax() -> None:
    class MissedFieldAdmin(ModelView, model=MissedField):
        form_ajax_refs = {
            "team": {
                "fields": (MissedField.id,),
                "order_by": func.lower(MissedField.team_id),
            }
        }

    admin.add_view(MissedFieldAdmin)

    assert len(MissedFieldAdmin()._form_ajax_refs["team"]._cached_fields_order_by) == 1


async def test_order_by_error_type_in_ajax() -> None:
    class MissedFieldAdmin(ModelView, model=MissedField):
        form_ajax_refs = {"team": {"fields": (MissedField.id,), "order_by": 1234}}

    error_msg = (
        "The form_ajax_refs.field.order_by field accepts only str "
        "and sqlalchemy.orm.attributes.InstrumentedAttribute or collections of them. "
        "Received: 1234"
    )
    with pytest.raises(ValueError, match=re.escape(error_msg)):
        admin.add_view(MissedFieldAdmin)


async def test_order_by_error_type_list_in_ajax() -> None:
    class MissedFieldAdmin(ModelView, model=MissedField):
        form_ajax_refs = {"team": {"fields": (MissedField.id,), "order_by": [None]}}

    error_msg = (
        "The form_ajax_refs.field.order_by field accepts only str "
        "and sqlalchemy.orm.attributes.InstrumentedAttribute or collections of them. "
        "Received <class 'NoneType'>: None"
    )
    with pytest.raises(ValueError, match=re.escape(error_msg)):
        admin.add_view(MissedFieldAdmin)


async def test_order_by_error_type_field_not_found_in_ajax() -> None:
    class MissedFieldAdmin(ModelView, model=MissedField):
        form_ajax_refs = {"team": {"fields": (MissedField.id,), "order_by": "error"}}

    with pytest.raises(ValueError, match="error does not exist"):
        admin.add_view(MissedFieldAdmin)
