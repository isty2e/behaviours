"""Pydantic's dataclass path is distinct from its incompatible BaseModel path."""

import pytest

pydantic = pytest.importorskip("pydantic")
from pydantic.dataclasses import dataclass

from behaviours import CompositionError, trait


@trait
class Answer:
    def answer(self) -> int:
        return 42


@pytest.mark.parametrize("frozen", [False, True])
@pytest.mark.parametrize("slots", [False, True])
def test_pydantic_dataclass_validation_and_serialization(frozen, slots):
    @dataclass(frozen=frozen, slots=slots)
    class Record(Answer):
        raw: int

    obj = Record("3")
    assert obj.raw == 3 and obj.answer() == 42
    assert pydantic.TypeAdapter(Record).dump_python(obj) == {"raw": 3}
    with pytest.raises(pydantic.ValidationError):
        Record("not an integer")


def test_pydantic_dataclass_field_cannot_shadow_behavior():
    with pytest.raises(CompositionError):

        @dataclass
        class Bad(Answer):
            answer: int
