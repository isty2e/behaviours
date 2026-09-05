"""Good-faith decorator use: layout, identity, closure, and native contracts."""

import functools
import gc
import inspect
import sys
import weakref
from abc import ABC, ABCMeta, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from typing import Generic, TypeVar

import pytest
from typing_extensions import override

from behaviours import CompositionError, StrictMixin, trait
from behaviours.composition import Admission, ClassRole, MemberKind


@trait
class ModuleFeature:
    def value(self) -> int:
        return 1


def test_plain_trait_has_no_hidden_base_or_dictionary() -> None:
    assert ModuleFeature.__bases__ == (object,)
    assert ModuleFeature.__slots__ == ()
    assert ModuleFeature.__dictoffset__ == 0
    assert ModuleFeature.__weakrefoffset__ == 0
    assert ModuleFeature().value() == 1
    assert type(ModuleFeature).__call__ is type.__call__

    class Slotted(ModuleFeature):
        __slots__ = ("state",)

    item = Slotted()
    item.state = 3
    assert not hasattr(item, "__dict__")
    assert isinstance(item, ModuleFeature)


def test_subtrait_marker_and_ordinary_state_owner() -> None:
    @trait
    class Extended(ModuleFeature):
        def doubled(self) -> int:
            return 2 * self.value()

    class Subject(Extended):
        def __init__(self, state: int) -> None:
            self.state = state

    assert Admission.spec_for(Extended).role is ClassRole.TRAIT
    assert Admission.spec_for(Subject).role is ClassRole.TRAIT_ADOPTER
    assert Subject(4).__dict__ == {"state": 4}
    assert Subject(4).doubled() == 2
    assert Extended.__dictoffset__ == 0
    with pytest.raises(CompositionError, match="topology"):
        type("Reopened", (Subject, ModuleFeature), {})


def test_abstract_root_needs_static_abc_evidence() -> None:
    with pytest.raises(CompositionError) as failure:

        @trait
        class HiddenRequirement:
            @abstractmethod
            def value(self) -> int: ...

    assert failure.value.code == "abstract-trait-needs-abc"

    @trait
    class Requirement(ABC):
        @abstractmethod
        def value(self) -> int: ...

        def derived(self) -> int:
            return self.value() + 1

    @trait
    class Subrequirement(Requirement):
        @abstractmethod
        def label(self) -> str: ...

    class Missing(Subrequirement):
        pass

    with pytest.raises(TypeError, match="abstract"):
        Missing()

    class Value(Subrequirement):
        @override
        def value(self) -> int:
            return 4

        @override
        def label(self) -> str:
            return "four"

    assert Value().derived() == 5
    assert Value().label() == "four"


def test_abstract_subtrait_can_introduce_visible_abc() -> None:
    @trait
    class Required(ModuleFeature, ABC):
        @abstractmethod
        def label(self) -> str: ...

    assert Required.__bases__ == (ModuleFeature, ABC)
    assert Required.__dictoffset__ == 0
    with pytest.raises(TypeError, match="abstract"):
        Required()


def test_explicit_abc_meta_does_not_replace_required_visible_abc_base() -> None:
    # A single uniform ABC rule also applies when later subtraits add requirements.
    with pytest.raises(CompositionError) as failure:

        @trait
        class Contract(metaclass=ABCMeta):
            @abstractmethod
            def value(self) -> int: ...

    assert failure.value.code == "abstract-trait-needs-abc"


def test_slots_and_keyword_are_not_required_on_strict_mixins() -> None:
    class Upper(StrictMixin):
        def upper(self) -> str:
            return self.name().upper()

    class Suffix(Upper):
        def suffixed(self) -> str:
            return self.upper() + "!"

    class Name:
        __slots__ = ("text",)

        def __init__(self, text: str) -> None:
            self.text = text

        def name(self) -> str:
            return self.text

    class Result(Suffix, Name):
        __slots__ = ()

    assert Upper.__dictoffset__ == Suffix.__dictoffset__ == 0
    assert Result("ok").suffixed() == "OK!"
    assert not hasattr(Result("ok"), "__dict__")
    with pytest.raises(CompositionError):
        type("WrongOrder", (Name, Suffix), {})


@pytest.mark.parametrize("slots", [("state",), ("__dict__",), ["state"]])
def test_explicit_nonempty_layout_is_rejected(slots) -> None:
    declaration = type("Stateful", (), {"__slots__": slots})
    with pytest.raises(CompositionError) as failure:
        trait(declaration)
    assert failure.value.code == "nonempty-behaviour-layout"
    with pytest.raises(CompositionError):
        type("StatefulMixin", (StrictMixin,), {"__slots__": slots})


def test_explicit_empty_slots_remain_compatible() -> None:
    @trait
    class Feature:
        __slots__ = ()

        def value(self) -> int:
            return 3

    assert Feature().value() == 3
    assert Feature.__dictoffset__ == 0


def test_data_and_constructor_still_rejected() -> None:
    with pytest.raises(CompositionError) as annotation:

        @trait
        class Data:
            value: int

    assert annotation.value.code == "behaviour-data-annotation"
    with pytest.raises(CompositionError) as constructor:

        @trait
        class Lifecycle:
            def __init__(self) -> None:
                self.value = 1

    assert constructor.value.code == "forbidden-behaviour-member"


def test_ordinary_bases_and_closed_lineages_cannot_be_decorated() -> None:
    class Base:
        pass

    with pytest.raises(CompositionError) as failure:

        @trait
        class Invalid(Base):
            pass

    assert failure.value.code == "invalid-trait-bases"

    class Adopter(ModuleFeature):
        pass

    class Descendant(Adopter):
        pass

    with pytest.raises(CompositionError, match="reopen"):
        trait(Descendant)
    with pytest.raises(CompositionError, match="subclassing"):
        trait(Adopter)


def test_trait_declaration_is_replaced_without_mutating_ordinary_layout() -> None:
    class Declaration:
        def value(self) -> int:
            return 1

    method = Declaration.value
    result = trait(Declaration)
    assert result is not Declaration
    assert result.value is method
    assert Declaration.__dictoffset__ != 0
    assert result.__dictoffset__ == 0
    assert result.__name__ == Declaration.__name__
    assert result.__qualname__ == Declaration.__qualname__
    assert result.__module__ == Declaration.__module__
    assert trait(result) is result


def test_class_cell_is_bound_to_public_decorated_class() -> None:
    @trait
    class Feature:
        def defining_class(self):
            return __class__

        @property
        def defining_property(self):
            return __class__

        def nested(self):
            def inner():
                return __class__

            return inner()

    @trait
    class Sub(Feature):
        def sub_class(self):
            return __class__

    class Subject(Sub):
        pass

    obj = Subject()
    assert obj.defining_class() is Feature
    assert obj.defining_property is Feature
    assert obj.nested() is Feature
    assert obj.sub_class() is Sub


def test_wrapped_method_class_cell_and_signature_survive() -> None:
    def traced(function):
        @functools.wraps(function)
        def wrapper(self, *args, **kwargs):
            return function(self, *args, **kwargs)

        return wrapper

    @trait
    class Feature:
        @traced
        def defining_class(self):
            return __class__

    class Subject(Feature):
        pass

    assert Subject().defining_class() is Feature
    assert tuple(inspect.signature(Feature.defining_class).parameters) == ("self",)


def test_decorator_preserves_hash_and_abstract_property() -> None:
    @trait
    class Equal:
        def __eq__(self, other: object) -> bool:
            return self is other

    @trait
    class Hashed:
        def __hash__(self) -> int:
            return 8

    assert Equal.__hash__ is None
    assert (
        Admission.spec_for(Equal).members["__hash__"].kind is MemberKind.HASH_DISABLED
    )
    for bases in ((Equal, Hashed), (Hashed, Equal)):
        with pytest.raises(CompositionError):
            type("Conflict", bases, {})

    @trait
    class Combined(Equal, Hashed):
        __hash__ = object.__hash__

    class Result(Combined):
        pass

    assert isinstance(hash(Result()), int)

    @trait
    class Label(ABC):
        @property
        @abstractmethod
        def label(self) -> str: ...

    class Named(Label):
        @property
        @override
        def label(self) -> str:
            return "ok"

    assert Named().label == "ok"


def test_generic_subtraits_keep_type_arguments_and_abstractness() -> None:
    t = TypeVar("t")

    @trait
    class Value(ABC, Generic[t]):
        @abstractmethod
        def value(self) -> t: ...

        def as_list(self) -> list[t]:
            return [self.value()]

    @trait
    class Extended(Value[t]):
        def twice(self) -> tuple[t, t]:
            return self.value(), self.value()

    class Integer(Extended[int]):
        def value(self) -> int:
            return 2

    assert Extended.__parameters__ == (t,)
    assert Extended.__dictoffset__ == 0
    assert Integer().as_list() == [2]
    assert Integer().twice() == (2, 2)


@pytest.mark.skipif(sys.version_info < (3, 12), reason="PEP 695 syntax")
def test_pep695_generic_trait() -> None:
    scope = {"trait": trait}
    exec(  # noqa: S102 - fixed PEP 695 fixture, parsed only on supporting interpreters.
        "@trait\nclass Echo[T]:\n"
        "    def echo(self, value: T) -> T: return value\n"
        "class IntEcho(Echo[int]): pass\n",
        scope,
    )
    assert scope["IntEcho"]().echo(3) == 3
    assert scope["Echo"].__dictoffset__ == 0


def test_declaration_rebuild_does_not_pin_temporary_class() -> None:
    def make():
        class Declaration:
            def cls(self):
                return __class__

        original = weakref.ref(Declaration)
        decorated = trait(Declaration)
        assert decorated().cls() is decorated
        return original, weakref.ref(decorated)

    original, decorated = make()
    gc.collect()
    assert original() is None
    assert decorated() is None


def test_concurrent_declarations_have_isolated_roles_and_class_cells() -> None:
    def create(i: int) -> int:
        @trait
        class Feature:
            def identity(self):
                return __class__

            def value(self) -> int:
                return i

        class Subject(Feature):
            pass

        assert Subject().identity() is Feature
        assert Admission.spec_for(Feature).role is ClassRole.TRAIT
        return Subject().value()

    with ThreadPoolExecutor(max_workers=8) as executor:
        assert list(executor.map(create, range(64))) == list(range(64))


def test_root_descriptor_effects_are_not_claimed_to_be_rolled_back() -> None:
    events = []

    class Descriptor:
        def __set_name__(self, owner, name):
            events.append(name)

    with pytest.raises(CompositionError) as failure:

        @trait
        class Invalid:
            member = Descriptor()

    assert failure.value.code == "set-name-transform-not-supported"
    # A normal class decorator runs after the raw declaration was created.
    assert events == ["member"]


def test_source_keyword_is_rejected_with_migration_hint() -> None:
    with pytest.raises(CompositionError) as failure:
        type("OldSpelling", (ModuleFeature,), {}, trait=True)
    assert failure.value.code == "unsupported-class-keyword"
    assert "@trait" in str(failure.value)
