"""Separate-module consumer: constructors, properties, Self and generics."""

from typing import assert_type

from decorated_api import Conformer, DisplayConformer, Feature, IntegerValue

value = Conformer(2.0, "sample")
assert_type(value, Conformer)
assert_type(value.identity(), Conformer)
assert_type(value.value(), int)
assert_type(value.doubled(), int)
assert_type(value.shifted(1.0), float)
assert_type(value.label, str)
assert_type(IntegerValue().items(), list[int])
assert_type(IntegerValue().pair(), tuple[int, int])
assert_type(DisplayConformer(2.0, "x").upper_label(), str)
assert_type(DisplayConformer(2.0, "x").identity(), DisplayConformer)
assert_type(Feature, type[Feature])
assert_type(Feature().identity(), Feature)


def as_feature(value: Feature) -> int:
    return value.value()


assert as_feature(value) == 3
assert isinstance(value, Feature)
assert value.shifted(1.0) == 1.0
assert DisplayConformer(2.0, "x").upper_label() == "X"
