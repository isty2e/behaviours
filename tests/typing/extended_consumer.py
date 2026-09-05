from typing import assert_type

from extended_api import Child, Combined, Number, Selected, TextEcho

from behaviours import CompositionReport, inspect_composition
from behaviours.testing import assert_composition

assert_type(Number.from_bytes(b"3"), Number)
assert_type(Child.from_bytes(b"4"), Child)
assert_type(Child.from_text("4"), Child)
assert_type(Number.parse("5"), int)
assert_type(Number(1).parse("5"), int)
assert_type(Selected().render("x"), str)
assert_type(Selected.parse("3"), int)
assert_type(Selected().parse("3"), int)
assert_type(Combined().upper(), str)
assert_type(Combined.kind(), str)
assert_type(Combined.parse("name"), int)
assert_type(inspect_composition(Combined), CompositionReport)
assert_composition(Combined)

assert_type(TextEcho.echo("sample"), str)
