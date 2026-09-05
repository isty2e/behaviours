from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, Protocol, Self, TypeVar, assert_type

from typing_extensions import override

from behaviours import StrictMixin, trait


@trait
class Energy(ABC):
    @abstractmethod
    def energy(self) -> float:
        raise NotImplementedError

    def shifted(self, reference: float, /) -> float:
        return self.energy() - reference

    def lower_than(self, other: Self, /) -> bool:
        return self.energy() < other.energy()


class Conformer(Energy):
    __slots__ = ("_energy",)

    def __init__(self, energy: float) -> None:
        self._energy = energy

    @override
    def energy(self) -> float:
        return self._energy


class SupportsName(Protocol):
    def name(self) -> str: ...


class UpperName(StrictMixin):
    def upper_name(self: SupportsName) -> str:
        return self.name().upper()


class Named:
    def name(self) -> str:
        return "item"


class UpperNamed(UpperName, Named):
    pass


conformer = Conformer(1.5)
assert_type(conformer.energy(), float)
assert_type(conformer.shifted(1.0), float)
assert_type(conformer.lower_than(Conformer(2.0)), bool)
assert_type(UpperNamed().upper_name(), str)

assert_type(Conformer(1.0), Conformer)
assert_type(UpperNamed(), UpperNamed)


T = TypeVar("T")


@trait
class Value(ABC, Generic[T]):
    @abstractmethod
    def value(self) -> T: ...

    def as_list(self) -> list[T]:
        return [self.value()]


class IntegerValue(Value[int]):
    @override
    def value(self) -> int:
        return 42


class Echo(StrictMixin, Generic[T]):
    def echo(self, x: T) -> T:
        return x


class IntegerEcho(Echo[int], IntegerValue):
    pass


assert_type(IntegerEcho(), IntegerEcho)
assert_type(IntegerEcho().as_list(), list[int])
assert_type(IntegerEcho().echo(3), int)


@trait
class RenderA(ABC):
    def render(self) -> str:
        return "a"


@trait
class RenderB(ABC):
    def render(self) -> str:
        return "b"


class Rendered(RenderA, RenderB):
    @override
    def render(self) -> str:
        return RenderA.render(self)


assert_type(Rendered().render(), str)
