from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol

from typing_extensions import override

from behaviours import StrictMixin, trait


@trait
class Energy(ABC):
    @abstractmethod
    def energy(self) -> float:
        raise NotImplementedError

    def shifted(self, reference: float, /) -> float:
        return self.energy() - reference


class Missing(Energy):
    pass


class Wrong(Energy):
    @override
    def energy(self) -> str:
        return "bad"


class NeedsName(StrictMixin):
    def upper_name(self: HasName) -> str:
        return self.name().upper()


class HasName(Protocol):
    def name(self) -> str:
        return "x"


class NoName:
    pass


class Bad(NeedsName, NoName):
    pass


Missing()
Wrong().shifted("not-a-float")
Bad().upper_name()
