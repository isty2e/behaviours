from typing import assert_type

from pydantic.dataclasses import dataclass
from sqlalchemy.orm import Mapped, mapped_column, registry

from behaviours import trait


@trait
class Answer:
    def answer(self) -> int:
        return 42


@dataclass
class PlainValidated:
    raw: int


@dataclass
class Validated(Answer):
    raw: int


reg = registry()


@reg.mapped_as_dataclass
class Entity(Answer):
    __tablename__ = "entities"
    name: Mapped[str]
    id: Mapped[int] = mapped_column(init=False, primary_key=True)


assert_type(Validated(3), Validated)
assert_type(Validated(3).raw, int)
assert_type(Validated(3).answer(), int)
assert_type(Entity(name="x"), Entity)
assert_type(Entity(name="x").name, str)
assert_type(Entity(name="x").answer(), int)

# Native Pydantic constructor input is coercive for either base graph.
assert_type(PlainValidated("3").raw, int)
assert_type(Validated("3").raw, int)
