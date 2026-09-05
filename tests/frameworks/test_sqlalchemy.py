"""SQLAlchemy watchpoints use real mapping, persistence and instrumentation."""

import pytest

sa = pytest.importorskip("sqlalchemy")
from sqlalchemy import ForeignKey, select
from sqlalchemy.orm import (
    DeclarativeBase,
    DeclarativeBaseNoMeta,
    Mapped,
    Session,
    add_mapped_attribute,
    mapped_column,
    relationship,
)

from behaviours import CompositionError, StrictMixin


class Summary(StrictMixin):
    def summary(self) -> str:
        return type(self).__name__


# This is an expected limitation, not an integration success.
def test_default_declarative_base_remains_an_explicit_watchpoint():
    class Base(DeclarativeBase):
        pass

    with pytest.raises(TypeError, match="metaclass conflict"):

        class Unsupported(Summary, Base):
            __tablename__ = "unsupported"
            id: Mapped[int] = mapped_column(primary_key=True)


def test_no_meta_mapping_relationship_persistence_and_late_column():
    class Base(DeclarativeBaseNoMeta):
        pass

    class Parent(Summary, Base):
        __tablename__ = "parents"
        id: Mapped[int] = mapped_column(primary_key=True)
        name: Mapped[str]
        children: Mapped[list["Child"]] = relationship(back_populates="parent")

    class Child(Summary, Base):
        __tablename__ = "children"
        id: Mapped[int] = mapped_column(primary_key=True)
        parent_id: Mapped[int] = mapped_column(ForeignKey("parents.id"))
        parent: Mapped[Parent] = relationship(back_populates="children")

    add_mapped_attribute(Parent, "extra", mapped_column(sa.Integer, default=7))
    engine = sa.create_engine("sqlite://")
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            parent = Parent(name="sample")
            parent.children.append(Child())
            session.add(parent)
            session.commit()
        with Session(engine) as session:
            row = session.scalars(select(Parent)).one()
            assert row.summary() == "Parent"
            assert row.name == "sample" and row.extra == 7
            assert row.children[0].summary() == "Child"
    finally:
        engine.dispose()
        Base.registry.dispose()


def test_mapped_field_cannot_shadow_mixin_method_before_mapping():
    class Base(DeclarativeBaseNoMeta):
        pass

    with pytest.raises(CompositionError):

        class Bad(Summary, Base):
            __tablename__ = "bad"
            id: Mapped[int] = mapped_column(primary_key=True)
            summary: Mapped[str]

    assert "bad" not in Base.metadata.tables


def test_registry_mapped_as_dataclass_with_trait():
    from sqlalchemy.orm import registry

    from behaviours import trait

    @trait
    class Answer:
        def answer(self):
            return 42

    reg = registry()
    engine = sa.create_engine("sqlite://")
    try:

        @reg.mapped_as_dataclass
        class Entity(Answer):
            __tablename__ = "entities"
            id: Mapped[int] = mapped_column(init=False, primary_key=True)
            name: Mapped[str]

        reg.metadata.create_all(engine)
        with Session(engine) as session:
            session.add(Entity(name="sample"))
            session.commit()
        with Session(engine) as session:
            row = session.scalars(select(Entity)).one()
            assert row.name == "sample" and row.answer() == 42
    finally:
        engine.dispose()
        reg.dispose()
