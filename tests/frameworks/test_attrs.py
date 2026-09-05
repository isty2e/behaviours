"""Real attrs transformations, including accidental late field collisions."""

from abc import ABC, abstractmethod

import pytest

attrs = pytest.importorskip("attrs")

from behaviours import CompositionError, StrictMixin, trait


@trait
class Value(ABC):
    @abstractmethod
    def value(self) -> int: ...

    def doubled(self) -> int:
        return self.value() * 2


class Answer(StrictMixin):
    def answer(self) -> int:
        return 42


class Base:
    pass


@pytest.mark.parametrize("slots", [False, True])
@pytest.mark.parametrize("frozen", [False, True])
def test_direct_trait_with_fields_validation_and_evolution(slots, frozen):
    @attrs.define(slots=slots, frozen=frozen)
    class Record(Value):
        raw: int = attrs.field(converter=int, validator=attrs.validators.ge(0))
        tags: list[str] = attrs.field(factory=list)

        def value(self) -> int:
            return self.raw

    obj = Record("4")
    assert obj.doubled() == 8
    assert attrs.asdict(obj) == {"raw": 4, "tags": []}
    assert attrs.evolve(obj, raw=5).doubled() == 10
    assert hasattr(obj, "__dict__") is not slots
    with pytest.raises(ValueError):
        Record(-1)
    if frozen:
        with pytest.raises(attrs.exceptions.FrozenInstanceError):
            obj.raw = 5


@pytest.mark.parametrize("slots", [False, True])
@pytest.mark.parametrize("frozen", [False, True])
def test_direct_mixin_application(slots, frozen):
    @attrs.define(slots=slots, frozen=frozen)
    class Record(Answer, Base):
        raw: int

    assert Record(3).answer() == 42
    assert attrs.evolve(Record(3), raw=4).raw == 4


@pytest.mark.parametrize("slots", [False, True])
def test_field_shadow_is_rejected(slots):
    with pytest.raises(CompositionError):

        @attrs.define(slots=slots)
        class Bad(Answer, Base):
            answer: int


@pytest.mark.parametrize("slots", [False, True])
def test_field_transformer_cannot_introduce_hidden_shadow(slots):
    def rename(cls, fields):
        return [field.evolve(name="answer", alias="answer") for field in fields]

    with pytest.raises(CompositionError):

        @attrs.define(slots=slots, field_transformer=rename)
        class Bad(Answer, Base):
            raw: int


@pytest.mark.parametrize("slots", [False, True])
def test_unrelated_field_transformer_is_supported(slots):
    def transform(cls, fields):
        return [field.evolve(converter=int) for field in fields]

    @attrs.define(slots=slots, field_transformer=transform)
    class Record(Answer, Base):
        raw: int

    assert Record("4").raw == 4
    assert Record("4").answer() == 42


@pytest.mark.parametrize("slots", [False, True])
def test_attrs_post_class_hook_may_add_metadata(slots):
    class HookBase:
        @classmethod
        def __attrs_init_subclass__(cls):
            cls.field_names = tuple(field.name for field in attrs.fields(cls))

    @attrs.define(slots=slots)
    class Record(Answer, HookBase):
        raw: int

    assert Record.field_names == ("raw",)
    assert Record(1).answer() == 42


def test_programmatic_attrs_fields_cannot_shadow_behavior():
    def rename(cls, fields):
        return [field.evolve(name="answer", alias="answer") for field in fields]

    with pytest.raises(CompositionError):

        @attrs.define(
            slots=False,
            these={"raw": attrs.field(type=int)},
            field_transformer=rename,
        )
        class Bad(Answer, Base):
            pass


def test_existing_programmatic_attrs_field_cannot_be_mixin_method():
    @attrs.define(slots=False, these={"answer": attrs.field(type=int)})
    class DataBase:
        pass

    with pytest.raises(CompositionError):

        class Bad(Answer, DataBase):
            pass


def test_cached_property_on_slotted_ordinary_attrs_class():
    from functools import cached_property

    @attrs.define(slots=True)
    class Record(Answer, Base):
        raw: int

        @cached_property
        def cached(self):
            return self.raw * 2

    obj = Record(3)
    assert obj.cached == obj.cached == 6
    assert obj.answer() == 42
