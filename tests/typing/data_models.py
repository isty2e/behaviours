"""Static API contracts for supported data-model transformations."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Generic, Protocol, Self, TypeVar

import attrs
from typing_extensions import override

from behaviours import StrictMixin, trait

T = TypeVar("T")


@trait
class Reading(ABC):
    @abstractmethod
    def value(self) -> int: ...

    def doubled(self) -> int:
        return self.value() * 2

    def same_type(self) -> Self:
        return self


@dataclass(slots=True, frozen=True)
class DataReading(Reading):
    raw: int

    @override
    def value(self) -> int:
        return self.raw


@attrs.define(slots=True)
class AttrReading(Reading):
    raw: int

    @override
    def value(self) -> int:
        return self.raw


@trait
class HasItem(ABC, Generic[T]):
    @abstractmethod
    def item(self) -> T: ...

    def boxed(self) -> list[T]:
        return [self.item()]


@dataclass
class Box(HasItem[T]):
    raw: T

    @override
    def item(self) -> T:
        return self.raw


class SupportsName(Protocol):
    def name(self) -> str: ...


class Upper(StrictMixin):
    def upper(self: SupportsName) -> str:
        return self.name().upper()


class Plain:
    pass


@attrs.define
class Named(Upper, Plain):
    raw: str

    def name(self) -> str:
        return self.raw
