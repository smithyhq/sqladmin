from typing import AsyncGenerator

import pytest
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base, relationship

from sqladmin.forms import get_model_form
from tests.common import async_engine as engine

pytestmark = pytest.mark.anyio

Base = declarative_base()
session_maker = async_sessionmaker(bind=engine, class_=AsyncSession)


class Service(Base):
    __tablename__ = "service"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)

    subscriptions = relationship("Subscription", back_populates="service")


class Customer(Base):
    __tablename__ = "customer"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)

    subscriptions = relationship("Subscription", back_populates="customer")


class Subscription(Base):
    __tablename__ = "subscription"

    service_id = Column(ForeignKey("service.id"), primary_key=True)
    customer_id = Column(ForeignKey("customer.id"), primary_key=True)
    start = Column(DateTime, nullable=False)
    end = Column(DateTime, nullable=True)

    customer = relationship("Customer", back_populates="subscriptions")
    service = relationship("Service", back_populates="subscriptions")


@pytest.fixture(autouse=True)
async def prepare_database() -> AsyncGenerator[None, None]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


async def test_multipk_form():
    Form = await get_model_form(model=Subscription, session_maker=session_maker)
    assert len(Form()._fields) == 4


async def test_model_form_include_pks():
    Form = await get_model_form(
        model=Subscription, session_maker=session_maker, form_include_pk=True
    )
    assert len(Form()._fields) == 6
    assert "service_id" in Form()._fields
    assert "customer_id" in Form()._fields
