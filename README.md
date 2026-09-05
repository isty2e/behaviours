# behaviours

Python already has inheritance, abstract base classes, structural Protocols, and mixins.
The call site after any of those is ordinary: `x.method(...)`. None of them give a join
where independent providers of the same member cannot be chosen by base order, and where
the behaviour type does not own instance layout.

This package puts that join on native class graphs. A Trait is required members plus
provided members, composed without taking the host’s state. A StrictMixin is the other
join: extra behaviour on a type that already exists. Ordinary mixins still let C3 method
resolution order pick a winner; `StrictMixin` keeps the host last and rejects that use
of order.

The package does not inject methods, generate stubs, or install a type-checker plugin.
Invalid combinations fail when the class is defined, as `CompositionError`.

Two forms:

```python
class Message(Printable): ...  # Trait adoption


class LoggedMessage(Logged, Message): ...  # StrictMixin application
```

Trait adoption is symmetric: `class C(T1, T2, ...)`. There is no ordinary base in that
join. StrictMixin application is asymmetric: `class C(M1, ..., Base)` with exactly one
ordinary base, last.

## A first class

```python
from abc import ABC, abstractmethod

from typing_extensions import override  # or typing.override on 3.12+

from behaviours import StrictMixin, trait


@trait
class Printable(ABC):
    @abstractmethod
    def text(self) -> str: ...

    def show(self) -> str:
        return self.text()


class Message(Printable):
    def __init__(self, body: str) -> None:
        self._body = body

    @override
    def text(self) -> str:
        return self._body


class Logged(StrictMixin):
    def log_line(self) -> str:
        return f"seen {type(self).__name__}"


class LoggedMessage(Logged, Message):
    pass


msg = LoggedMessage("hello")
assert msg.show() == "hello"
assert msg.log_line() == "seen LoggedMessage"
```

`Message` is a `Printable`. `Logged` is not a kind of message; it is applied to one,
with the host last. Empty slots are automatic on behaviour definitions. The decorator is
the trait marker; `Trait` is an optional ABC root and is not required.

## Mixing traits

Independent traits combine when their members do not collide. The adopter still has no
ordinary base in that join.

```python
@trait
class Dated(ABC):
    @abstractmethod
    def timestamp(self) -> str: ...


class Notice(Printable, Dated):
    def __init__(self, body: str, when: str) -> None:
        self._body = body
        self._when = when

    @override
    def text(self) -> str:
        return self._body

    @override
    def timestamp(self) -> str:
        return self._when


note = Notice("hello", "noon")
assert note.show() == "hello"
assert note.timestamp() == "noon"
```

`@trait class Sub(Parent)` is another trait. `class Subject(Parent)` without the
decorator is an ordinary adopter. A decorated class may also list several traits at
once. After adoption, descendants cannot add another trait or merge another ordinary
branch. A trait and a StrictMixin cannot appear in the same class statement: adopt
first, then apply mixins to the adopter.

An abstract trait must visibly inherit `abc.ABC`, directly or through a base. That keeps
missing methods visible to Pyrefly. A decorated class with an abstract method and no
`ABC` ancestry is rejected (`abstract-trait-needs-abc`). `ABCMeta` alone is not a
substitute. `typing.Generic` and `abc.ABC` are infrastructure, not ordinary state-owning
branches.

## Strict mixins

Receiver requirements belong in an explicit-self `Protocol`. Mixins do not declare
abstract methods or own state.

```python
from typing import Protocol

from behaviours import StrictMixin


class HasText(Protocol):
    def text(self) -> str: ...


class LogText(StrictMixin):
    def log_line(self: HasText, /) -> str:
        return f"log: {self.text()}"


class LoggedNotice(LogText, Notice):
    pass


assert LoggedNotice("hello", "noon").log_line() == "log: hello"
```

The host may already have adopted traits; that is still mixin application, not a third
form. Multiple unrelated mixins may precede the one ordinary base. A related mixin
family cannot be reapplied. Two ordinary bases, base-first application, and `object` as
the sole ordinary base are rejected.

`@mixin` is the same role without importing the root class. Mixin-only subclasses stay
mixin definitions, with or without a repeated decorator; adding the ordinary base marks
an application. That differs from trait adoption, where an undecorated subclass is an
ordinary type.

```python
from behaviours import mixin


@mixin
class Formatting:
    @staticmethod
    def format_number(value: int, /) -> str:
        return f"{value:,}"


class Record(Formatting, Message):
    pass


assert Record("hello").format_number(1000) == "1,000"
```

## When providers collide

Independent concrete providers of the same member are a conflict. Base order is not a
resolution rule. Define a compatible member in the joining class.

```python
from behaviours import CompositionError


@trait
class Shout:
    def show(self) -> str:
        return "hey"


# CompositionError: unresolved member conflict on show
try:

    class Broken(Shout, Printable):
        def text(self) -> str:
            return "x"

except CompositionError as error:
    assert error.member == "show"


class LoudMessage(Shout, Printable):
    def __init__(self, body: str) -> None:
        self._body = body

    @override
    def text(self) -> str:
        return self._body

    @override
    def show(self) -> str:
        return f"{Shout.show(self)}: {self.text()}"


assert LoudMessage("hello").show() == "hey: hello"
```

`@override` is recommended so the checker sees the choice. In a strict type-checking
setup it is required. The runtime only needs an explicit compatible local member. A
method cannot resolve a property obligation, and a synchronous method cannot resolve an
asynchronous one. A shared ancestor is one provider, not a conflict. Two abstract
requirements with the same name can coexist until some class implements them. An
unrelated abstract requirement and a concrete provider still need a local
implementation.

`__hash__ = None` is an unhashable provider, not ignorable metadata. It conflicts with a
concrete `__hash__`. Choose explicitly, including `__hash__ = object.__hash__`.

Behaviour members and local join resolutions cannot call `super()`; use a qualified
provider. Ordinary constructors may use `super()` normally. The check catches direct use
and common wrappers or aliases. It is not a proof about arbitrary reflective code.

A native instance alias is a pure choice of implementation: `render = Human.render`.
Static aliases must stay static (`parse = staticmethod(Provider.parse)`). A bare
`parse = Provider.parse` installs a normal function, which binds `self`. A bound
classmethod (`make = Provider.make`) has already captured `Provider` and is rejected;
write a typed local `@classmethod` through `cls` instead.

`typing.final` is honored at managed class boundaries. Subclasses cannot source-override
a final member, replace it by ordinary assignment, or generate a field over it. Put
`@final` on a property getter (`@property` above `@final`). An abstract member cannot
also be final.

## Layout and admitted members

Trait and StrictMixin definitions do not own instance layout. Empty slots are supplied
automatically. Explicit `__slots__ = ()` remains valid; nonempty behaviour slots are
rejected. Ordinary classes keep normal Python layout unless they request slots
themselves.

Behaviour definitions may provide Python instance, class, and static methods, including
coroutine and async-generator non-operator forms, plus read-only built-in properties.
They may not declare data annotations, constructors, nonempty slots, writable or custom
descriptors, or subclass/attribute hooks. Ordinary classes own representation and
lifecycle.

Class methods receive the actual subclass. Static methods receive no implicit receiver.
Both work on traits and mixins. Abstract class or static requirements use native `ABC`
and the usual `@classmethod` / `@staticmethod` above `@abstractmethod` order. Mixins
remain implementation-only.

```python
from typing import Self


@trait
class TextDecodable(ABC):
    @classmethod
    @abstractmethod
    def from_text(cls, text: str, /) -> Self: ...

    @classmethod
    def from_bytes(cls, payload: bytes, /) -> Self:
        return cls.from_text(payload.decode("utf-8"))

    @staticmethod
    def parse_number(text: str, /) -> int:
        return int(text)


class Number(TextDecodable):
    def __init__(self, value: int) -> None:
        self.value = value

    @classmethod
    @override
    def from_text(cls, text: str, /) -> Self:
        return cls(cls.parse_number(text))


assert type(Number.from_bytes(b"3")) is Number
assert Number.parse_number("4") == 4
```

Descriptors must wrap actual Python functions. Custom descriptor chains and
`classmethod(property(...))` are not supported. Binding kind and execution mode are
separate contracts: a property cannot satisfy a method, and sync/async kinds are not
interchangeable.

## API

| Name                  | Role                                                                       |
| --------------------- | -------------------------------------------------------------------------- |
| `trait`               | Admits a fresh trait declaration.                                          |
| `mixin`               | Admits a fresh mixin declaration; equivalent to subclassing `StrictMixin`. |
| `StrictMixin`         | Mixin definition root. Apply with the ordinary host last.                  |
| `Trait`               | Optional ABC base. The decorator, not this root, marks a trait.            |
| `CompositionError`    | `TypeError` raised when a class statement is not an admitted join.         |
| `inspect_composition` | Read-only report of the current composition.                               |

`CompositionError` is raised at class creation, not at first method call. It carries
`.code`, and also `.member`, `.origins`, `.hint`, and `.phase` (`definition`,
`construction`, `mutation`, `inspection`).

## Compared with

- **`ABC`.** Abstracts and `isinstance` checks. Several ABCs that each implement the
  same method still resolve by MRO order.
- **`Protocol`.** Structural typing. It does not define a runtime inheritance join or a
  conflict law.
- **Classic mixins.** Host last is the usual spelling. C3 still chooses among
  overlapping implementations; `super()` is how cooperative mixins are written.
  `StrictMixin` keeps the spelling and forbids that resolution.
- **`zope.interface`.** A separate interface and adapter registry. This package stays on
  class bases and `x.method(...)`.
- **Enthought `traits` / `traitlets`.** Typed attributes and configuration, not this
  composition law.

## What the decorator does

Python applies a class decorator after constructing the initial declaration. `@trait`
and `@mixin` return a replacement class with the same declared bases and members under
the package metaclass, adding empty slots before that result is built. The initial class
is not left as a base, methods are not added, and a live type is not monkeypatched.
Declaration-owned `__class__` cells are retargeted to the public result.

Use it on a fresh class declaration. Late conversion after subclassing is rejected;
decorating an already-decorated trait again is harmless. An arbitrary class-transforming
decorator on the same declaration is unsupported. Root-declaration descriptor callbacks
may already have run; those effects are not rolled back. Once a decorated trait exists,
later joins are checked before native class creation. No per-instance metaclass
`__call__` wrapper is installed.

## Data-model and framework use

Ordinary adopters and mixin applications may use standard data-model decorators
directly:

```python
from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class Recorded(Printable):
    body: str

    @override
    def text(self) -> str:
        return self.body


assert Recorded("hello").show() == "hello"
```

`attrs.define` works on dict and slots, frozen and mutable. Ordinary constructors,
fields, metadata, and subclass hooks may be generated or configured. Only behaviour
definitions stay fully frozen. After admission, normal assignment may not silently
replace or delete a behaviour-bound member, and a generated field may not hide one. If a
trait provides `__repr__`, use `dataclass(repr=False)` rather than replacing it
implicitly.

Ordinary hooks may accept class keywords and need not cooperate with admission. Source
conflicts are checked before hooks; binding changes are checked afterward. Failed
configuration is not rolled back.

SQLAlchemy’s `DeclarativeBaseNoMeta` route supports SQLite persistence. Pydantic
`BaseModel`, default SQLAlchemy `DeclarativeBase`, and Django ORM remain incompatible
because of their own metaclasses.

## Read-only composition inspection

```python
from behaviours import inspect_composition
from behaviours.testing import assert_composition

report = inspect_composition(LoudMessage)
print(report.format())
report.raise_if_invalid()
assert_composition(LoudMessage)
```

The report shows native providers, member kinds, source locations, abstract/final flags,
and changed bindings. It does not invoke property getters or methods, repair bindings,
or register a new admission baseline. Unmanaged classes report `role=None` and
`is_valid=False`. Abstract definitions are valid compositions; validity is not
instantiability.

`behaviours.testing` imports no pytest or Hypothesis. Semantic laws stay in ordinary
tests.

## Supported boundary

This is an error-prevention library for good-faith use, not a sandbox. The supported
envelope is native calls, explicit independent conflicts, decorator traits, base-last
mixins, and ordinary dataclass/attrs construction on adopters and applications.

Hostile reflection, `type.__setattr__`, code or closure mutation, in-place metadata
changes, and mutation of external bases are not contained. Opaque bases may observe new
methods through `self.method()`. Empty behaviour slots do not prove method purity.
Arbitrary unrelated custom metaclasses remain unsupported.

## Install

```sh
python -m pip install behaviours
```

Requires Python 3.11–3.14. On 3.11, `typing_extensions` is a conditional dependency.
From a checkout:

```sh
python -m pip install -e '.[dev,frameworks]'
pre-commit install
ruff format --check .
ruff check .
python -m pytest -q
pyrefly check
```

Typing tests require Pyrefly. It checks method availability, signatures, constructors,
overrides, generics, and incomplete ABC instantiation. Package-specific topology is a
runtime admission check.

Licensed under the MIT License.
