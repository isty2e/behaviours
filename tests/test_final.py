"""Standard final markers are respected without instance wrappers or a new DSL."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import final

import pytest

from behaviours import CompositionError, mixin, trait


@pytest.mark.parametrize("decorate", [trait, mixin])
@pytest.mark.parametrize(
    "descriptor", [lambda f: f, classmethod, staticmethod, property]
)
def test_final_behavior_member_blocks_both_source_and_late_replacement(
    decorate, descriptor
):
    def value(self=None):
        return 1

    Feature = decorate(type("Feature", (), {"value": descriptor(final(value))}))

    class Base:
        pass

    bases = (Feature,) if decorate is trait else (Feature, Base)
    with pytest.raises(CompositionError, match="final"):
        type("Bad", bases, {"value": descriptor(lambda self=None: 2)})
    Subject = type("Subject", bases, {})
    with pytest.raises(CompositionError):
        Subject.value = descriptor(lambda self=None: 2)
    with pytest.raises(CompositionError):
        del Subject.value


@pytest.mark.parametrize("binding", [classmethod, staticmethod])
@pytest.mark.parametrize("outer", [False, True])
def test_final_can_wrap_descriptor_or_underlying_function(binding, outer):
    def f(cls=None):
        return 1

    member = final(binding(f)) if outer else binding(final(f))

    @trait
    class Feature:
        value = member

    with pytest.raises(CompositionError):
        type("Bad", (Feature,), {"value": binding(lambda cls=None: 2)})


def test_final_ordinary_parent_and_descendant_members_are_checked():
    @mixin
    class Feature:
        def feature(self):
            return 2

    class Base:
        @final
        def value(self):
            return 1

    with pytest.raises(CompositionError):

        class Bad(Feature, Base):
            def value(self):
                return 3

    class Good(Feature, Base):
        pass

    with pytest.raises(CompositionError):

        class BadChild(Good):
            value: int

    with pytest.raises(CompositionError):

        class BadSlots(Good):
            __slots__ = ("value",)

    class Middle(Good):
        @final
        def another(self):
            return 4

    with pytest.raises(CompositionError):

        class BadGrandchild(Middle):
            def another(self):
                return 5


@pytest.mark.parametrize("before", [False, True])
def test_final_class_decorator_orders(before):
    if before:

        @trait
        @final
        class Feature:
            def value(self):
                return 1
    else:

        @final
        @trait
        class Feature:
            def value(self):
                return 1

    with pytest.raises(CompositionError, match="final"):

        class Bad(Feature):
            pass


def test_final_adopter_and_data_class_rebuild():
    @trait
    class Feature:
        def feature(self):
            return 1

    @final
    @dataclass(slots=True)
    class Data(Feature):
        value: int

        @final
        def doubled(self):
            return 2 * self.value

    assert Data(3).doubled() == 6
    with pytest.raises(CompositionError):

        class Child(Data):
            pass


def test_final_methods_survive_slots_rebuild_and_generated_fields_are_rejected():
    @trait
    class Feature:
        @final
        def feature(self):
            return 1

    @dataclass(slots=True, frozen=True)
    class Data(Feature):
        value: int

    assert Data(3).feature() == 1
    with pytest.raises(CompositionError):

        class Bad(Data):
            feature: int


def test_abstract_final_contract_is_rejected():
    with pytest.raises(CompositionError):

        @trait
        class Bad(ABC):
            @final
            @abstractmethod
            def value(self): ...


def test_hook_cannot_replace_an_ordinary_final_member():
    @mixin
    class Feature:
        def feature(self):
            return 1

    class Base:
        @final
        def value(self):
            return 2

        def __init_subclass__(cls, **kwargs):
            cls.value = lambda self: 3
            super().__init_subclass__(**kwargs)

    with pytest.raises(CompositionError, match="final"):

        class Bad(Feature, Base):
            pass


def test_final_ordinary_subclass_hook_keeps_native_wrapping():
    from behaviours import inspect_composition

    @trait
    class Feature:
        def feature(self):
            return 1

    events = []

    class Subject(Feature):
        @final
        def __init_subclass__(cls, **kwargs):
            events.append(cls.__name__)
            super().__init_subclass__(**kwargs)

    class Child(Subject):
        pass

    assert events == ["Child"]
    assert inspect_composition(Subject).is_valid
    assert inspect_composition(Child).is_valid
    with pytest.raises(CompositionError, match="final"):

        class Bad(Subject):
            def __init_subclass__(cls, **kwargs):
                pass

    assert events == ["Child"]  # Rejected before the parent's hook can run.


def test_final_ordinary_new_keeps_native_static_wrapping():
    from behaviours import inspect_composition

    @trait
    class Feature:
        def feature(self):
            return 1

    class Subject(Feature):
        @final
        def __new__(cls):
            return super().__new__(cls)

    class Child(Subject):
        pass

    assert type(Child()) is Child
    assert inspect_composition(Child).is_valid
    with pytest.raises(CompositionError, match="final"):

        class Bad(Subject):
            def __new__(cls):
                return super().__new__(cls)
