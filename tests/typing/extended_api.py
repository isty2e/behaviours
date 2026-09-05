"""Cross-module consumer API for all ordinary method binding conventions."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Generic, Protocol, Self, TypeVar, final

from typing_extensions import override

from behaviours import mixin, trait


@trait
class Decode(ABC):
    @classmethod
    @abstractmethod
    def from_text(cls, text: str, /) -> Self: ...

    @classmethod
    def from_bytes(cls, payload: bytes, /) -> Self:
        return cls.from_text(payload.decode())

    @staticmethod
    def parse(text: str, /) -> int:
        return int(text)


@dataclass
class Number(Decode):
    value: int

    @classmethod
    @override
    def from_text(cls, text: str, /) -> Self:
        return cls(cls.parse(text))


class Child(Number):
    pass


@trait
class Human:
    def render(self, prefix: str = "") -> str:
        return prefix + "human"

    @staticmethod
    def parse(text: str) -> int:
        return len(text)


@trait
class Debug:
    def render(self, prefix: str = "") -> str:
        return prefix + "debug"

    @staticmethod
    def parse(text: str) -> int:
        return int(text)


class Selected(Human, Debug):
    render = Human.render
    parse = staticmethod(Debug.parse)


T = TypeVar("T")


@trait
class Item(ABC, Generic[T]):
    @abstractmethod
    def item(self) -> T: ...

    def items(self) -> list[T]:
        return [self.item()]


class HasName(Protocol):
    def name(self) -> str: ...


@mixin
class Upper:
    def upper(self: HasName) -> str:
        return self.name().upper()

    @staticmethod
    def parse(text: str) -> int:
        return len(text)


@mixin
class Suffix(Upper):
    @classmethod
    def kind(cls) -> str:
        return cls.__name__


class Base:
    def name(self) -> str:
        return "base"


class Combined(Suffix, Base):
    pass


@trait
class Fixed:
    @final
    def stable(self) -> int:
        return 1


class FixedUser(Fixed):
    pass


@mixin
class Echo(Generic[T]):
    @staticmethod
    def echo(item: T) -> T:
        return item


class TextEcho(Echo[str], Base):
    pass
