"""Do not offer field/property coercion that works only for one native layout."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

import pytest

from behaviours import CompositionError, trait


@pytest.mark.parametrize("builder", ["dataclass", "attrs"])
@pytest.mark.parametrize("slots", [False, True])
def test_native_boundary_and_package_rejection_are_explicit(builder, slots):
    class Named(ABC):
        @property
        @abstractmethod
        def name(self) -> str: ...

    class Native(Named):
        name: str

    if builder == "dataclass":
        Native = dataclass(slots=slots)(Native)
    else:
        attrs = pytest.importorskip("attrs")
        Native = attrs.define(slots=slots)(Native)

    if slots:
        assert Native("sample").name == "sample"
    else:
        with pytest.raises(TypeError, match="abstract"):
            Native("sample")

    @trait
    class Required(ABC):
        @property
        @abstractmethod
        def name(self) -> str: ...

    # Both requested layouts are refused at declaration: no silent half-support.
    with pytest.raises(CompositionError, match="name"):

        class Unsupported(Required):
            name: str

    class Implemented(Required):
        raw_name: str

        @property
        def name(self) -> str:
            return self.raw_name

    if builder == "dataclass":
        Implemented = dataclass(slots=slots)(Implemented)
    else:
        Implemented = attrs.define(slots=slots)(Implemented)
    assert Implemented("sample").name == "sample"
