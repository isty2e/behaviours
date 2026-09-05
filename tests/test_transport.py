"""Normal module-owned objects keep Python copy/pickle/spawn behavior."""

import copy
import multiprocessing
import pickle
import queue
import sys
from abc import ABC
from dataclasses import dataclass

import pytest

from behaviours import inspect_composition, mixin, trait


@trait
class Label:
    def label(self) -> str:
        return type(self).__name__

    @classmethod
    def category(cls) -> str:
        return cls.__name__


@dataclass(slots=True, frozen=True)
class Record(Label):
    number: int
    text: str


@mixin
class Title:
    def title(self) -> str:
        return type(self).__name__


class Plain:
    def __init__(self, value: int) -> None:
        self.value = value


class Mixed(Title, Plain):
    pass


def echo_object(value, output) -> None:
    output.put((value, value.label() if isinstance(value, Record) else value.title()))


@pytest.mark.parametrize("value", [Record(3, "name"), Mixed(4)])
def test_copy_deepcopy_and_pickle(value):
    for copied in (
        copy.copy(value),
        copy.deepcopy(value),
        pickle.loads(pickle.dumps(value)),
    ):
        assert type(copied) is type(value)
        assert inspect_composition(type(copied)).is_valid
        if isinstance(value, Record):
            assert copied == value
            assert copied.label() == "Record"
        else:
            assert copied.value == 4 and copied.title() == "Mixed"


@pytest.mark.parametrize("value", [Record(3, "name"), Mixed(4)])
def test_spawn_roundtrip(value):
    context = multiprocessing.get_context("spawn")
    out = context.Queue()
    proc = context.Process(target=echo_object, args=(value, out))
    proc.start()
    try:
        received, name = out.get(timeout=20)
        assert type(received) is type(value)
        assert name == type(value).__name__
        proc.join(20)
        assert proc.exitcode == 0
    except queue.Empty:
        pytest.fail(f"spawn worker produced no object; exit={proc.exitcode}")
    finally:
        if proc.is_alive():
            proc.terminate()
            proc.join(5)
        out.close()
        out.join_thread()


def test_decorated_classes_themselves_pickle_to_public_identity():
    assert pickle.loads(pickle.dumps(Label)) is Label
    assert pickle.loads(pickle.dumps(Title)) is Title


@pytest.mark.skipif(
    sys.version_info < (3, 12),
    reason="native type-parameter syntax requires Python 3.12",
)
def test_native_generic_metadata_and_classmethod_self():
    scope = {"__name__": __name__, "trait": trait, "mixin": mixin, "ABC": ABC}
    exec(  # noqa: S102 -- fixed syntax fixture must remain importable on Python 3.11.
        """
from typing import Self
from abc import abstractmethod
@trait
class Item[T](ABC):
    @abstractmethod
    def item(self) -> T: ...
    def items(self) -> list[T]: return [self.item()]
    @classmethod
    def type_name(cls) -> str: return cls.__name__
class IntItem(Item[int]):
    def item(self) -> int: return 3
@mixin
class Format[T]:
    @staticmethod
    def echo(item: T) -> T: return item
class Base: pass
class Text(Format[str],Base): pass
""",
        scope,
    )
    Item = scope["Item"]
    IntItem = scope["IntItem"]
    Text = scope["Text"]
    assert len(Item.__type_params__) == 1
    assert Item.__parameters__ == Item.__type_params__
    assert IntItem().items() == [3] and IntItem.type_name() == "IntItem"
    assert Text.echo("a") == "a"
