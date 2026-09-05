"""Regression witnesses for public admission and actual Python behavior."""

import asyncio
import builtins
import functools
import gc
import inspect
import weakref
from abc import ABCMeta, abstractmethod
from itertools import permutations
from typing import Generic, TypeVar

import pytest
from typing_extensions import override

from behaviours import CompositionError, StrictMixin, Trait, trait
from behaviours.composition import Admission

T = TypeVar("T")
SUPER_ALIAS = super


def test_concrete_construction_has_no_python_metaclass_call() -> None:
    assert type(Trait).__call__ is type.__call__
    assert type(StrictMixin).__call__ is type.__call__


def test_temporary_classes_are_not_retained_by_admission_metadata() -> None:
    def make() -> tuple[weakref.ReferenceType[type], weakref.ReferenceType[type]]:
        @trait
        class Temporary(Trait):
            __slots__ = ()

            def value(self) -> int:
                return 1

        class Adopter(Temporary):
            __slots__ = ()

            @override
            def value(self) -> int:
                return 2

        assert Adopter().value() == 2
        return weakref.ref(Temporary), weakref.ref(Adopter)

    refs = make()
    gc.collect()
    assert all(ref() is None for ref in refs)


def test_exact_property_only_rejected_before_callback() -> None:
    events = []

    class ChangingProperty(property):
        def __set_name__(self, owner: type, name: str) -> None:
            events.append(name)
            owner.__slots__ = ()

    for root in (StrictMixin,):
        with pytest.raises(CompositionError):
            type(
                "Invalid",
                (root,),
                {
                    "__slots__": (),
                    "value": ChangingProperty(lambda self: 1),
                },
            )
    assert events == []


def test_abc_virtual_registration_cannot_change_nominal_instance_contract() -> None:
    @trait
    class A(Trait):
        __slots__ = ()

        def value(self) -> str:
            return "a"

    @trait
    class B(Trait):
        __slots__ = ()

        def value(self) -> str:
            return "b"

    ABCMeta.register(A, B)
    assert not issubclass(B, A)
    assert not isinstance(B(), A)
    for order in ((A, B), (B, A)):
        with pytest.raises(CompositionError):
            type("Conflict", order, {"__slots__": ()})


@pytest.mark.parametrize("style", ["direct", "builtin", "global", "default", "closure"])
def test_super_rejected_in_definition_and_conflict_resolver(style: str) -> None:
    alias = super

    def direct(self):
        return super().value()

    def builtin(self):
        return builtins.super(type(self), self).value()

    def global_alias(self):
        return SUPER_ALIAS(type(self), self).value()

    def default(self, call=super):
        return call(type(self), self).value()

    def closure(self):
        return alias(type(self), self).value()

    body = {
        "direct": direct,
        "builtin": builtin,
        "global": global_alias,
        "default": default,
        "closure": closure,
    }[style]
    with pytest.raises(CompositionError, match="super"):
        type("Invalid", (StrictMixin,), {"__slots__": (), "value": body})

    @trait
    class A(Trait):
        __slots__ = ()

        def value(self):
            return 1

    @trait
    class B(Trait):
        __slots__ = ()

        def value(self):
            return 2

    with pytest.raises(CompositionError, match="super"):
        type("Invalid", (A, B), {"__slots__": (), "value": override(body)})


def test_wrapper_and_wrapped_body_are_both_checked() -> None:
    def safe(self):
        return 1

    @functools.wraps(safe)
    def unsafe(self):
        return super().value()

    with pytest.raises(CompositionError, match="super"):
        type("Invalid", (StrictMixin,), {"__slots__": (), "value": unsafe})


def test_abstract_marker_cannot_execute_user_truthiness() -> None:
    events = []

    class Marker:
        def __bool__(self):
            events.append(True)
            return True

    def method(self):
        return 1

    method.__isabstractmethod__ = Marker()
    with pytest.raises(CompositionError, match="literal bool"):
        type("Invalid", (StrictMixin,), {"__slots__": (), "method": method})
    assert not events


def test_fake_signature_does_not_create_receiver() -> None:
    def no_receiver():
        return 1

    no_receiver.__signature__ = inspect.Signature(
        [
            inspect.Parameter("self", inspect.Parameter.POSITIONAL_ONLY),
        ]
    )
    with pytest.raises(CompositionError, match="receiver"):
        type("Invalid", (StrictMixin,), {"__slots__": (), "value": no_receiver})


@pytest.mark.parametrize("value", [property(), functools.partial(lambda self: 1)])
def test_nonmethod_descriptors_rejected(value: object) -> None:
    with pytest.raises(CompositionError):
        type("Invalid", (StrictMixin,), {"__slots__": (), "value": value})


def test_async_partial_is_not_a_method() -> None:
    async def raw(self):
        return 1

    with pytest.raises(CompositionError):
        type(
            "Invalid",
            (StrictMixin,),
            {"__slots__": (), "value": functools.partial(raw)},
        )


def test_async_generator_is_distinct_from_coroutine() -> None:
    @trait
    class Generator(Trait):
        __slots__ = ()

        async def values(self):
            yield 1

    @trait
    class Coroutine(Trait):
        __slots__ = ()

        async def values(self):
            return [1]

    with pytest.raises(CompositionError, match="incompatible"):

        class Bad(Generator, Coroutine):
            __slots__ = ()

            @override
            async def values(self):
                yield 2

    class Good(Generator):
        __slots__ = ()

    async def consume():
        return [x async for x in Good().values()]

    assert asyncio.run(consume()) == [1]


def test_method_property_resolver_must_satisfy_both() -> None:
    @trait
    class Method(Trait):
        __slots__ = ()

        @abstractmethod
        def value(self): ...

    @trait
    class Property(Trait):
        __slots__ = ()

        @property
        @abstractmethod
        def value(self): ...

    with pytest.raises(CompositionError, match="incompatible"):

        class Invalid(Method, Property):
            __slots__ = ()

            @override
            def value(self):
                return 1


def test_explicit_object_hash_is_not_discarded() -> None:
    class Eq(StrictMixin):
        __slots__ = ()

        def __eq__(self, other):
            return self is other

    class Base:
        __hash__ = object.__hash__

    with pytest.raises(CompositionError, match="__hash__"):

        class Invalid(Eq, Base):
            pass

    class Good(Eq, Base):
        __hash__ = object.__hash__

    assert isinstance(hash(Good()), int)


def test_generic_trait_and_mixin() -> None:
    @trait
    class Value(Trait, Generic[T]):
        __slots__ = ()

        @abstractmethod
        def value(self) -> T: ...

        def values(self) -> list[T]:
            return [self.value()]

    class Concrete(Value[int]):
        __slots__ = ()

        @override
        def value(self) -> int:
            return 3

    class Echo(StrictMixin, Generic[T]):
        __slots__ = ()

        def echo(self, value: T) -> T:
            return value

    class Joined(Echo[int], Concrete):
        __slots__ = ()

    assert Joined().values() == [3]
    assert Joined().echo(4) == 4


def test_dynamic_mro_entries_rejected() -> None:
    class M(StrictMixin):
        __slots__ = ()

        def value(self):
            return 1

    class Base:
        pass

    class Alias:
        def __mro_entries__(self, bases):
            return (M,)

    with pytest.raises(CompositionError, match="__mro_entries__"):

        class Invalid(Alias(), Base):
            pass


def test_ordinary_descendant_cannot_reassign_bases() -> None:
    @trait
    class T(Trait):
        __slots__ = ()

    class Closed(T):
        pass

    class Child(Closed):
        pass

    class Other:
        pass

    with pytest.raises(CompositionError):
        Child.__bases__ = (Other,)


def test_constructor_super_remains_native() -> None:
    class M(StrictMixin):
        __slots__ = ()

        def value(self):
            return 1

    class Base:
        def __init__(self, number):
            self.number = number

    class Joined(M, Base):
        def __init__(self, number):
            super().__init__(number)

    assert Joined(3).number == 3


def test_diagnostic_metadata_is_not_writable_admission_authority() -> None:
    @trait
    class T(Trait):
        __slots__ = ()

        def value(self):
            return 1

    spec = Admission.spec_for(T)
    with pytest.raises(TypeError):
        spec.members["fake"] = spec.members["value"]
    with pytest.raises(CompositionError):
        type("Fake", (T,), {"__behaviours_admission__": spec})


def test_runtime_provider_oracle_across_all_permutations() -> None:
    @trait
    class A(Trait):
        __slots__ = ()

        def a(self):
            return "a"

    @trait
    class B(Trait):
        __slots__ = ()

        def b(self):
            return "b"

    @trait
    class C(Trait):
        __slots__ = ()

        def c(self):
            return "c"

    for bases in permutations((A, B, C)):
        cls = type("Joined", bases, {"__slots__": ()})
        obj = cls()
        assert (obj.a(), obj.b(), obj.c()) == ("a", "b", "c")
        assert inspect.getattr_static(cls, "a") is A.__dict__["a"]


def test_descriptor_metaclass_cannot_hide_set_name_or_execute_introspection() -> None:
    events = []

    class Meta(type):
        @property
        def __mro__(cls):
            events.append("mro")
            return (object,)

        @property
        def __dict__(cls):
            events.append("dict")
            return {}

    class Descriptor(metaclass=Meta):
        def __set_name__(self, owner, name):
            events.append("set-name")

    @trait
    class T(Trait):
        __slots__ = ()

    with pytest.raises(CompositionError):

        class Invalid(StrictMixin):
            descriptor = Descriptor()

    assert not events


def test_fake_function_class_property_is_not_executed() -> None:
    events = []

    class Pretend:
        @property
        def __class__(self):
            events.append(True)
            return type(lambda: None)

    with pytest.raises(CompositionError):

        class Invalid(StrictMixin):
            __slots__ = ()
            method = Pretend()

    assert not events


def test_slotted_frozen_dataclass_on_ordinary_descendant() -> None:
    from dataclasses import dataclass

    @trait
    class T(Trait):
        __slots__ = ()

        def value(self) -> int:
            return 1

    class Closed(T):
        __slots__ = ()

    @dataclass(frozen=True, slots=True)
    class Data(Closed):
        number: int

    assert Data(3).value() == 1
    assert Data(3).number == 3
    assert Admission.spec_for(Data) is None


def test_native_lifecycle_wrapping_on_adopter() -> None:
    @trait
    class T(Trait):
        __slots__ = ()

        def value(self):
            return 1

    events = []

    class Closed(T):
        __slots__ = ()

        def __new__(cls):
            return super().__new__(cls)

        def __init_subclass__(cls, **kwargs):
            events.append(cls.__name__)
            super().__init_subclass__(**kwargs)

    assert Closed().value() == 1

    class Child(Closed):
        __slots__ = ()

    assert Child().value() == 1
    assert events == ["Child"]


def test_ordinary_creation_hook_cannot_rewrite_bases_before_admission() -> None:
    @trait
    class Capability(Trait):
        __slots__ = ()

    class Adopted(Capability):
        pass

    class Other:
        pass

    class Parent(Adopted):
        def __init_subclass__(cls, **kwargs):
            cls.__bases__ = (Adopted, Other)

    with pytest.raises(CompositionError, match="frozen"):

        class Child(Parent):
            pass
