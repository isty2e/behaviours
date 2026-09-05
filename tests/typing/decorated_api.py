"""Source-visible contracts with no import of the package's Trait root."""

from abc import ABC, abstractmethod
from typing import Generic, Protocol, Self, TypeVar

from typing_extensions import override

from behaviours import StrictMixin, trait


@trait
class Feature:
    def value(self) -> int:
        return 3

    def identity(self) -> Self:
        return self


@trait
class ExtraFeature(Feature):
    def doubled(self) -> int:
        return 2 * self.value()


@trait
class Energy(ABC):
    @abstractmethod
    def energy(self) -> float: ...

    def shifted(self, reference: float, /) -> float:
        return self.energy() - reference


@trait
class LabeledEnergy(Energy):
    @property
    @abstractmethod
    def label(self) -> str: ...


class Conformer(ExtraFeature, LabeledEnergy):
    def __init__(self, energy: float, name: str, /) -> None:
        self._energy = energy
        self._label = name

    @override
    def energy(self) -> float:
        return self._energy

    @property
    @override
    def label(self) -> str:
        return self._label


T = TypeVar("T")


@trait
class Value(ABC, Generic[T]):
    @abstractmethod
    def item(self) -> T: ...

    def items(self) -> list[T]:
        return [self.item()]


@trait
class DoubleValue(Value[T]):
    def pair(self) -> tuple[T, T]:
        return self.item(), self.item()


class IntegerValue(DoubleValue[int]):
    @override
    def item(self) -> int:
        return 2


class HasLabel(Protocol):
    @property
    def label(self) -> str: ...


class UpperLabel(StrictMixin):
    def upper_label(self: HasLabel) -> str:
        return self.label.upper()


class DisplayConformer(UpperLabel, Conformer):
    pass
