"""Each error is an intentional independent consumer-contract witness."""

from decorated_api import (
    Conformer,
    DoubleValue,
    Energy,
    Feature,
    IntegerValue,
    LabeledEnergy,
    UpperLabel,
)
from typing_extensions import override

from behaviours import trait


class Missing(Energy):
    pass


@trait
class AbstractSubtrait(LabeledEnergy):
    def unrelated(self) -> int:
        return 1


class BadReturn(Feature):
    @override
    def value(self) -> str:
        return "not an int"


class BadGeneric(DoubleValue[int]):
    @override
    def item(self) -> str:
        return "not an int"


class NoLabel:
    pass


class BadReceiver(UpperLabel, NoLabel):
    pass


class WrongProperty(LabeledEnergy):
    @override
    def energy(self) -> float:
        return 1.0

    @property
    @override
    def label(self) -> int:
        return 3


Missing()  # EXPECT: bad-instantiation
AbstractSubtrait()  # EXPECT: bad-instantiation
Conformer("wrong", "label")  # EXPECT: bad-argument-type
Conformer(1.0, "x").shifted("x")  # EXPECT: bad-argument-type
BadReceiver().upper_label()  # EXPECT: bad-argument-type
x: str = IntegerValue().items()  # EXPECT: bad-assignment
