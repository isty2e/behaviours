"""Method binding is native; all descriptor kinds use the same conflict rules."""

import asyncio
import inspect
from abc import ABC, abstractmethod
from typing import Self

import pytest
from typing_extensions import override

from behaviours import CompositionError, StrictMixin, mixin, trait
from behaviours.composition import Admission


@trait
class Decode(ABC):
    @classmethod
    @abstractmethod
    def from_text(cls, text: str) -> Self: ...

    @classmethod
    def from_bytes(cls, data: bytes) -> Self:
        return cls.from_text(data.decode())

    @staticmethod
    def parse(text: str) -> int:
        return int(text)


class Number(Decode):
    def __init__(self, value: int):
        self.value = value

    @classmethod
    @override
    def from_text(cls, text: str) -> Self:
        return cls(cls.parse(text))


def test_factory_binds_actual_subclass_and_static_calls_through_instances():
    class Specialized(Number):
        pass

    assert type(Number.from_bytes(b"4")) is Number
    assert type(Specialized.from_bytes(b"5")) is Specialized
    assert Specialized.from_bytes(b"5").value == 5
    assert Number.parse("6") == Number(1).parse("6") == 6
    assert inspect.getattr_static(Number, "from_bytes") is inspect.getattr_static(
        Decode, "from_bytes"
    )
    with pytest.raises(TypeError, match="abstract"):
        Decode()


@pytest.mark.parametrize("decorate", [trait, mixin])
@pytest.mark.parametrize("binding", [classmethod, staticmethod])
def test_async_and_async_generator_descriptor_modes(decorate, binding):
    if binding is classmethod:

        async def get(cls, n: int):
            return cls, n

        async def items(cls, n: int):
            yield cls, n
    else:

        async def get(n: int):
            return n

        async def items(n: int):
            yield n

    Feature = decorate(
        type("Feature", (), {"get": binding(get), "items": binding(items)})
    )

    class Base:
        pass

    bases = (Feature,) if decorate is trait else (Feature, Base)
    Subject = type("Subject", bases, {})
    expected = (Subject, 3) if binding is classmethod else 3
    assert asyncio.run(Subject.get(3)) == expected

    async def collect():
        return [v async for v in Subject().items(3)]

    assert asyncio.run(collect()) == [expected]


@pytest.mark.parametrize("decorate", [trait, mixin])
@pytest.mark.parametrize("binding", [classmethod, staticmethod])
def test_independent_conflicts_and_descriptor_correct_alias(decorate, binding):
    if binding is classmethod:

        def a(cls, n):
            return cls, "a", n

        def b(cls, n):
            return cls, "b", n
    else:

        def a(n):
            return "a", n

        def b(n):
            return "b", n

    A = decorate(type("A", (), {"read": binding(a)}))
    B = decorate(type("B", (), {"read": binding(b)}))

    class Base:
        pass

    bases = (A, B) if decorate is trait else (A, B, Base)
    with pytest.raises(CompositionError) as caught:
        type("Bad", bases, {})
    assert caught.value.code == "unresolved-member-conflict"
    # Copy the actual native descriptor, not an already-bound classmethod.
    C = type("C", bases, {"read": inspect.getattr_static(A, "read")})
    expected = (C, "a", 3) if binding is classmethod else ("a", 3)
    assert C.read(3) == C().read(3) == expected


def test_explicit_classmethod_wrapper_preserves_cls():
    @trait
    class OtherDecode(ABC):
        @classmethod
        def from_bytes(cls, data: bytes) -> Self:
            return cls.from_text(data.hex())

        @classmethod
        @abstractmethod
        def from_text(cls, text: str) -> Self: ...

    class Both(Decode, OtherDecode):
        @classmethod
        @override
        def from_text(cls, text: str) -> Self:
            return cls()

        @classmethod
        @override
        def from_bytes(cls, data: bytes) -> Self:
            return Decode.from_bytes.__func__(cls, data)

    assert type(Both.from_bytes(b"3")) is Both


def test_bound_classmethod_is_not_a_local_descriptor():
    @trait
    class A:
        @classmethod
        def make(cls):
            return cls()

    @trait
    class B:
        @classmethod
        def make(cls):
            return cls()

    with pytest.raises(CompositionError):

        class Bad(A, B):
            make = A.make


@pytest.mark.parametrize(
    "left,right",
    [
        (lambda f: f, classmethod),
        (classmethod, staticmethod),
        (staticmethod, lambda f: f),
    ],
)
def test_binding_kinds_must_not_silently_change(left, right):
    @trait
    class A:
        read = left(lambda receiver=None: 1)

    with pytest.raises(CompositionError):

        class B(A):
            read = right(lambda receiver=None: 2)


def test_abstract_staticmethod_is_an_abc_obligation():
    @trait
    class Predicate(ABC):
        @staticmethod
        @abstractmethod
        def accepts(text: str) -> bool: ...

    class Missing(Predicate):
        pass

    with pytest.raises(TypeError, match="abstract"):
        Missing()

    class Present(Predicate):
        @staticmethod
        @override
        def accepts(text: str) -> bool:
            return bool(text)

    assert Present.accepts("x")
    assert not Present().accepts("")


@pytest.mark.parametrize("binding", [classmethod, staticmethod])
def test_super_and_lifecycle_restrictions_apply_to_descriptors(binding):
    with pytest.raises(CompositionError):

        @trait
        class Bad:
            @binding
            def method(cls=None):
                return super()

    with pytest.raises(CompositionError):

        @trait
        class BadLifecycle:
            __init__ = binding(lambda cls: None)


def test_class_cell_retarget_in_classmethod_and_staticmethod():
    @trait
    class A:
        @classmethod
        def declaring(cls):
            return __class__, cls

        @staticmethod
        def origin():
            return __class__

    class C(A):
        pass

    assert C.declaring() == (A, C)
    assert C.origin() is A


def test_mixin_decorator_is_same_grammar_as_native_base():
    @mixin
    class M:
        def answer(self) -> int:
            return 42

    @mixin
    class N(M):
        def double(self) -> int:
            return 2 * self.answer()

    class Native(StrictMixin):
        def label(self) -> str:
            return "x"

    class Base:
        pass

    class C(N, Native, Base):
        pass

    assert C().double() == 84
    assert C().label() == "x"
    assert M.__dict__["__slots__"] == N.__dict__["__slots__"] == ()
    assert M.__dictoffset__ == N.__dictoffset__ == 0
    assert mixin(M) is M
    assert Admission.spec_for(C).role.value == "mixin-application"
    with pytest.raises(CompositionError):
        trait(M)
    with pytest.raises(CompositionError):
        mixin(C)
    with pytest.raises(CompositionError):
        type("WrongOrder", (Base, M), {})
    with pytest.raises(CompositionError):

        @mixin
        class State:
            x: int

    with pytest.raises(CompositionError):

        @mixin
        class Abstract(ABC):
            @abstractmethod
            def missing(self): ...


@pytest.mark.parametrize("binding", [classmethod, staticmethod])
@pytest.mark.parametrize("decorate", [trait, mixin])
def test_descriptors_require_real_python_function_bodies(binding, decorate):
    from functools import partial

    with pytest.raises(CompositionError) as caught:
        decorate(type("Bad", (), {"method": binding(partial(int, base=10))}))
    assert caught.value.code == "unsupported-wrapped-callable"


@pytest.mark.parametrize("binding", [classmethod, staticmethod])
def test_abstract_descriptors_require_visible_abc(binding):
    with pytest.raises(CompositionError) as caught:

        @trait
        class Bad:
            method = binding(abstractmethod(lambda receiver=None: None))

    assert caught.value.code == "abstract-trait-needs-abc"


def test_classmethod_must_accept_a_receiver_but_staticmethod_need_not():
    with pytest.raises(CompositionError):

        @trait
        class Bad:
            @classmethod
            def answer():
                return 42

    @trait
    class Good:
        @staticmethod
        def answer():
            return 42

    class Subject(Good):
        pass

    assert Subject().answer() == Subject.answer() == 42


@pytest.mark.parametrize("decorate", [trait, mixin])
def test_classmethod_common_origin_diamond_keeps_actual_receiver(decorate):
    @decorate
    class Root:
        @classmethod
        def factory(cls):
            return cls()

    Left = decorate(type("Left", (Root,), {}))
    Right = decorate(type("Right", (Root,), {}))

    class Base:
        pass

    bases = (Left, Right) if decorate is trait else (Left, Right, Base)
    Subject = type("Subject", bases, {})
    assert type(Subject.factory()) is Subject
    assert inspect.getattr_static(Subject, "factory") is inspect.getattr_static(
        Root, "factory"
    )
