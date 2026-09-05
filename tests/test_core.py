from __future__ import annotations

import asyncio
import functools
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Protocol

import pytest

try:
    from typing import override
except ImportError:  # pragma: no cover - Python 3.11
    from typing_extensions import override

from behaviours import CompositionError, StrictMixin, Trait, trait
from behaviours.composition import Admission, ClassRole, MemberKind


def assert_code(error: pytest.ExceptionInfo[CompositionError], code: str) -> None:
    assert error.value.code == code


def test_trait_required_and_provided_methods_use_native_call_syntax() -> None:
    @trait
    class Energy(Trait):
        __slots__ = ()

        @abstractmethod
        def energy(self) -> float:
            raise NotImplementedError

        def shifted(self, reference: float, /) -> float:
            return self.energy() - reference

    class Conformer(Energy):
        __slots__ = ("_energy",)

        def __init__(self, energy: float) -> None:
            self._energy = energy

        @override
        def energy(self) -> float:
            return self._energy

    conformer = Conformer(-12.5)
    assert conformer.energy() == -12.5
    assert conformer.shifted(-13.0) == 0.5
    assert Admission.spec_for(Energy).role is ClassRole.TRAIT
    assert Admission.spec_for(Conformer).role is ClassRole.TRAIT_ADOPTER


def test_concrete_trait_definition_uses_native_instantiation() -> None:
    @trait
    class Marker(Trait):
        __slots__ = ()

        def marked(self) -> bool:
            return True

    assert Marker().marked() is True
    assert type(Marker).__call__ is type.__call__


def test_trait_decorator_distinguishes_definition_from_adopter() -> None:
    @trait
    class Feature:
        def value(self) -> int:
            return 1

    @trait
    class SubFeature(Feature):
        pass

    class Adopter(Feature):
        pass

    assert Admission.spec_for(Feature).role is ClassRole.TRAIT
    assert Admission.spec_for(SubFeature).role is ClassRole.TRAIT
    assert Admission.spec_for(Adopter).role is ClassRole.TRAIT_ADOPTER
    assert Adopter().value() == 1


def test_trait_aggregate_and_common_origin_diamond() -> None:
    @trait
    class Renderable(Trait):
        __slots__ = ()

        def render(self) -> str:
            return type(self).__name__

    @trait
    class Left(Renderable):
        __slots__ = ()

    @trait
    class Right(Renderable):
        __slots__ = ()

    @trait
    class Combined(Left, Right):
        __slots__ = ()

    class Value(Combined):
        __slots__ = ()

    assert Value().render() == "Value"
    resolution = Admission.spec_for(Combined).members["render"]
    assert resolution.provider is Renderable
    assert {origin.owner for origin in resolution.origins} == {Renderable}


def test_independent_trait_conflict_requires_local_override() -> None:
    @trait
    class Human(Trait):
        __slots__ = ()

        def render(self) -> str:
            return "human"

    @trait
    class Debug(Trait):
        __slots__ = ()

        def render(self) -> str:
            return "debug"

    with pytest.raises(CompositionError) as error:

        class Invalid(Human, Debug):
            __slots__ = ()

    assert_code(error, "unresolved-member-conflict")

    class Resolved(Human, Debug):
        __slots__ = ()

        @override
        def render(self) -> str:
            return Human.render(self)

    assert Resolved().render() == "human"
    assert Admission.spec_for(Resolved).members["render"].is_local


def test_class_body_definition_is_an_explicit_runtime_resolution() -> None:
    @trait
    class Requirement(Trait):
        __slots__ = ()

        @abstractmethod
        def value(self) -> int:
            raise NotImplementedError

    class Concrete(Requirement):
        __slots__ = ()

        def value(self) -> int:
            return 1

    assert Concrete().value() == 1


def test_abstract_requirements_of_same_kind_can_merge() -> None:
    @trait
    class A(Trait):
        __slots__ = ()

        @abstractmethod
        def value(self) -> int:
            raise NotImplementedError

    @trait
    class B(Trait):
        __slots__ = ()

        @abstractmethod
        def value(self) -> int:
            raise NotImplementedError

    @trait
    class Combined(A, B):
        __slots__ = ()

    with pytest.raises(TypeError, match="abstract"):
        Combined()

    class Concrete(Combined):
        __slots__ = ()

        @override
        def value(self) -> int:
            return 3

    assert Concrete().value() == 3


def test_local_kind_must_satisfy_every_obligation() -> None:
    @trait
    class MethodRequirement(Trait):
        __slots__ = ()

        @abstractmethod
        def value(self) -> int:
            raise NotImplementedError

    @trait
    class PropertyRequirement(Trait):
        __slots__ = ()

        @property
        @abstractmethod
        def value(self) -> int:
            raise NotImplementedError

    with pytest.raises(CompositionError) as error:

        class Invalid(MethodRequirement, PropertyRequirement):
            __slots__ = ()

            @override
            def value(self) -> int:
                return 1

    assert_code(error, "incompatible-member-kind")


def test_sync_and_async_obligations_are_incompatible() -> None:
    @trait
    class Sync(Trait):
        __slots__ = ()

        @abstractmethod
        def value(self) -> int:
            raise NotImplementedError

    @trait
    class Async(Trait):
        __slots__ = ()

        @abstractmethod
        async def value(self) -> int:
            raise NotImplementedError

    with pytest.raises(CompositionError) as error:

        @trait
        class Invalid(Sync, Async):
            __slots__ = ()

    assert_code(error, "incompatible-abstract-obligations")


def test_read_only_property_and_async_method_are_supported() -> None:
    @trait
    class Surface(Trait):
        __slots__ = ()

        @property
        @abstractmethod
        def label(self) -> str:
            raise NotImplementedError

        async def async_label(self) -> str:
            await asyncio.sleep(0)
            return self.label

    class Value(Surface):
        __slots__ = ("_label",)

        def __init__(self, label: str) -> None:
            self._label = label

        @property
        @override
        def label(self) -> str:
            return self._label

    value = Value("x")
    assert value.label == "x"
    assert asyncio.run(value.async_label()) == "x"


def test_strict_mixin_uses_base_last_native_inheritance() -> None:
    class SupportsMapping(Protocol):
        def as_mapping(self) -> dict[str, object]: ...

    class Json(StrictMixin):
        __slots__ = ()

        def to_mapping(self: SupportsMapping) -> dict[str, object]:
            return dict(self.as_mapping())

    class Debug(StrictMixin):
        __slots__ = ()

        def debug(self) -> str:
            return type(self).__name__

    class Base:
        __slots__ = ()

        def as_mapping(self) -> dict[str, object]:
            return {"value": 1}

    class Mixed(Json, Debug, Base):
        __slots__ = ()

    value = Mixed()
    assert value.to_mapping() == {"value": 1}
    assert value.debug() == "Mixed"
    assert Admission.spec_for(Mixed).role is ClassRole.MIXIN_APPLICATION


def test_strict_mixin_definition_uses_native_instantiation() -> None:
    class Mixin(StrictMixin):
        __slots__ = ()

        def value(self) -> int:
            return 1

    assert Mixin().value() == 1
    assert type(Mixin).__call__ is type.__call__


def test_strict_mixin_aggregate() -> None:
    class A(StrictMixin):
        __slots__ = ()

        def a(self) -> str:
            return "a"

    class B(StrictMixin):
        __slots__ = ()

        def b(self) -> str:
            return "b"

    class AB(A, B):
        __slots__ = ()

    class Base:
        __slots__ = ()

    class Applied(AB, Base):
        __slots__ = ()

    assert Applied().a() == "a"
    assert Applied().b() == "b"


def test_strict_mixin_application_must_be_base_last() -> None:
    class Mixin(StrictMixin):
        __slots__ = ()

        def mixed(self) -> bool:
            return True

    class Base:
        pass

    with pytest.raises(CompositionError) as error:

        class Invalid(Base, Mixin):
            pass

    assert_code(error, "unsupported-inheritance-topology")


def test_strict_mixin_application_has_one_ordinary_base() -> None:
    class Mixin(StrictMixin):
        __slots__ = ()

        def mixed(self) -> bool:
            return True

    class A:
        pass

    class B:
        pass

    with pytest.raises(CompositionError) as error:

        class Invalid(Mixin, A, B):
            pass

    assert_code(error, "unsupported-inheritance-topology")


def test_repeated_strict_mixin_application_is_supported() -> None:
    class A(StrictMixin):
        __slots__ = ()

        def a(self) -> str:
            return "a"

    class B(StrictMixin):
        __slots__ = ()

        def b(self) -> str:
            return "b"

    class Base:
        __slots__ = ()

    class First(A, Base):
        __slots__ = ()

    class Second(B, First):
        __slots__ = ()

    assert Second().a() == "a"
    assert Second().b() == "b"


def test_strict_mixin_family_cannot_be_reapplied() -> None:
    class A(StrictMixin):
        __slots__ = ()

        def a(self) -> str:
            return "a"

    class Base:
        pass

    class First(A, Base):
        pass

    with pytest.raises(CompositionError) as error:

        class Invalid(A, First):
            pass

    assert_code(error, "strict-mixin-reapplication")


def test_strict_mixin_conflicts_with_base_require_local_override() -> None:
    class Mixin(StrictMixin):
        __slots__ = ()

        def render(self) -> str:
            return "mixin"

    class Base:
        def render(self) -> str:
            return "base"

    with pytest.raises(CompositionError) as error:

        class Invalid(Mixin, Base):
            pass

    assert_code(error, "unresolved-member-conflict")

    class Resolved(Mixin, Base):
        @override
        def render(self) -> str:
            return Mixin.render(self)

    assert Resolved().render() == "mixin"


def test_strict_mixin_conflicts_with_other_mixins() -> None:
    class A(StrictMixin):
        __slots__ = ()

        def render(self) -> str:
            return "a"

    class B(StrictMixin):
        __slots__ = ()

        def render(self) -> str:
            return "b"

    class Base:
        pass

    with pytest.raises(CompositionError) as error:

        class Invalid(A, B, Base):
            pass

    assert_code(error, "unresolved-member-conflict")


def test_ordinary_join_can_own_constructor_and_use_super() -> None:
    class Marker(StrictMixin):
        __slots__ = ()

        def marked(self) -> bool:
            return True

    class Base:
        def __init__(self, value: int) -> None:
            self.value = value

    class Applied(Marker, Base):
        def __init__(self, value: int) -> None:
            super().__init__(value)

    value = Applied(4)
    assert value.value == 4
    assert value.marked()


def test_conflict_resolver_may_not_use_super() -> None:
    @trait
    class A(Trait):
        __slots__ = ()

        def render(self) -> str:
            return "a"

    @trait
    class B(Trait):
        __slots__ = ()

        def render(self) -> str:
            return "b"

    with pytest.raises(CompositionError) as error:

        class Invalid(A, B):
            __slots__ = ()

            @override
            def render(self) -> str:
                return super().render()

    assert_code(error, "super-not-supported")


def test_strict_mixin_cannot_declare_abstract_member() -> None:
    with pytest.raises(CompositionError) as error:

        class Invalid(StrictMixin):
            __slots__ = ()

            @abstractmethod
            def value(self) -> int:
                raise NotImplementedError

    assert_code(error, "abstract-strict-mixin-member")


def test_trait_adoption_closes_trait_set() -> None:
    @trait
    class A(Trait):
        __slots__ = ()

        def a(self) -> str:
            return "a"

    @trait
    class B(Trait):
        __slots__ = ()

        def b(self) -> str:
            return "b"

    class Base(A):
        __slots__ = ()

    class Child(Base):
        __slots__ = ()

    assert Child().a() == "a"

    with pytest.raises(CompositionError) as error:

        class Invalid(B, Child):
            __slots__ = ()

    assert_code(error, "unsupported-inheritance-topology")


def test_trait_adopter_can_be_strict_mixin_base() -> None:
    @trait
    class Named(Trait):
        __slots__ = ()

        @abstractmethod
        def name(self) -> str:
            raise NotImplementedError

    class Upper(StrictMixin):
        __slots__ = ()

        def upper(self) -> str:
            return self.name().upper()

    class Item(Named):
        __slots__ = ("_name",)

        def __init__(self, name: str) -> None:
            self._name = name

        @override
        def name(self) -> str:
            return self._name

    class UpperItem(Upper, Item):
        __slots__ = ()

    assert UpperItem("x").upper() == "X"


def test_plain_abc_can_be_an_ordinary_mixin_base() -> None:
    class Mixin(StrictMixin):
        __slots__ = ()

        def doubled(self) -> int:
            return self.value() * 2

    class Base(ABC):
        @abstractmethod
        def value(self) -> int:
            raise NotImplementedError

    class Applied(Mixin, Base):
        @override
        def value(self) -> int:
            return 5

    assert Applied().doubled() == 10


def test_only_behavior_definitions_are_fully_frozen() -> None:
    @trait
    class Behaviour:
        def value(self) -> int:
            return 1

    class Adopter(Behaviour):
        pass

    with pytest.raises(CompositionError) as error:
        Behaviour.extra = 1
    assert_code(error, "frozen-composition-surface")
    Adopter.extra = 1
    with pytest.raises(CompositionError):
        Adopter.value = lambda self: 2

    class Descendant(Adopter):
        pass

    Descendant.extra = 2
    assert Adopter.extra == 1 and Descendant.extra == 2
    assert Admission.spec_for(Descendant) is None


def test_dataclass_on_direct_abstract_trait_adopter_and_descendant() -> None:
    @trait
    class ValueTrait(Trait):
        @abstractmethod
        def value(self) -> int:
            raise NotImplementedError

    @dataclass
    class Direct(ValueTrait):
        raw: int

        @override
        def value(self) -> int:
            return self.raw

    assert Direct(9).value() == 9

    @dataclass
    class Data(Direct):
        extra: int

        @override
        def value(self) -> int:
            return self.raw + self.extra

    assert Data(9, 1).value() == 10


def test_hash_tombstone_conflicts_with_concrete_hash() -> None:
    @trait
    class Equal(Trait):
        __slots__ = ()

        def __eq__(self, other: object) -> bool:
            return type(self) is type(other)

    @trait
    class Hashed(Trait):
        __slots__ = ()

        def __hash__(self) -> int:
            return 7

    with pytest.raises(CompositionError) as first:

        class InvalidA(Equal, Hashed):
            __slots__ = ()

    assert_code(first, "unresolved-member-conflict")

    with pytest.raises(CompositionError) as second:

        class InvalidB(Hashed, Equal):
            __slots__ = ()

    assert_code(second, "unresolved-member-conflict")

    class Unhashable(Equal, Hashed):
        __slots__ = ()
        __hash__ = None

    class IdentityHashed(Equal, Hashed):
        __slots__ = ()
        __hash__ = object.__hash__

    with pytest.raises(TypeError):
        hash(Unhashable())
    assert isinstance(hash(IdentityHashed()), int)


def test_implicit_hash_disable_cannot_silently_override_concrete_hash() -> None:
    @trait
    class Hashed(Trait):
        __slots__ = ()

        def __hash__(self) -> int:
            return 7

    with pytest.raises(CompositionError) as error:

        class Invalid(Hashed):
            __slots__ = ()

            def __eq__(self, other: object) -> bool:
                return self is other

    assert_code(error, "implicit-hash-resolution")


def test_implicit_hash_disable_without_conflict_is_recorded() -> None:
    @trait
    class Equal(Trait):
        __slots__ = ()

        def __eq__(self, other: object) -> bool:
            return self is other

    resolution = Admission.spec_for(Equal).members["__hash__"]
    assert resolution.kind is MemberKind.HASH_DISABLED

    class Value(Equal):
        __slots__ = ()

    with pytest.raises(TypeError):
        hash(Value())


def test_explicit_object_hash_on_ordinary_base_is_not_discarded() -> None:
    class EqualMixin(StrictMixin):
        __slots__ = ()

        def __eq__(self, other: object) -> bool:
            return self is other

    class IdentityHashBase:
        __hash__ = object.__hash__

    with pytest.raises(CompositionError) as error:

        class Invalid(EqualMixin, IdentityHashBase):
            pass

    assert_code(error, "unresolved-member-conflict")

    class Resolved(EqualMixin, IdentityHashBase):
        __hash__ = object.__hash__

    assert isinstance(hash(Resolved()), int)


def test_inherited_object_defaults_do_not_conflict() -> None:
    class StringMixin(StrictMixin):
        __slots__ = ()

        def __str__(self) -> str:
            return "mixed"

    class Base:
        pass

    class Applied(StringMixin, Base):
        pass

    assert str(Applied()) == "mixed"


def test_virtual_subclass_registration_is_forbidden() -> None:
    @trait
    class Contract(Trait):
        __slots__ = ()

        def value(self) -> int:
            return 1

    class Foreign:
        pass

    with pytest.raises(CompositionError) as error:
        Contract.register(Foreign)
    assert_code(error, "virtual-subclass-not-supported")


def test_behavior_definitions_are_state_and_lifecycle_free() -> None:
    with pytest.raises(CompositionError) as slots_error:

        @trait
        class Slotted(Trait):
            __slots__ = ("value",)

    assert_code(slots_error, "nonempty-behaviour-layout")

    with pytest.raises(CompositionError) as annotation_error:

        @trait
        class Annotated(Trait):
            __slots__ = ()
            value: int

    assert_code(annotation_error, "behaviour-data-annotation")

    with pytest.raises(CompositionError) as data_error:

        class Constant(StrictMixin):
            __slots__ = ()
            value = 1

    assert_code(data_error, "state-or-unsupported-member")

    with pytest.raises(CompositionError) as init_error:

        class Initializing(StrictMixin):
            __slots__ = ()

            def __init__(self) -> None:
                self.value = 1

    assert_code(init_error, "forbidden-behaviour-member")


def test_unsupported_descriptors_are_rejected() -> None:
    async def raw(self: object) -> int:
        return 1

    with pytest.raises(CompositionError) as partial_error:

        class Partial(StrictMixin):
            __slots__ = ()
            value = functools.partial(raw)

    assert_code(partial_error, "state-or-unsupported-member")

    with pytest.raises(CompositionError) as property_error:

        @trait
        class MissingGetter(Trait):
            __slots__ = ()
            value = property()

    assert_code(property_error, "unsupported-property")

    with pytest.raises(CompositionError) as dunder_error:

        class LengthProperty(StrictMixin):
            __slots__ = ()

            @property
            def __len__(self) -> int:
                return 1

    assert_code(dunder_error, "unsupported-property")


def test_wrapped_super_is_rejected_in_every_wrapper_layer() -> None:
    def safe(self: object) -> str:
        return "safe"

    with pytest.raises(CompositionError) as wrapper_error:

        class Wrapped(StrictMixin):
            __slots__ = ()

            @functools.wraps(safe)
            def render(self) -> str:
                return super().render()

    assert_code(wrapper_error, "super-not-supported")

    def unsafe(self: object) -> str:
        return super(type(self), self).__repr__()

    with pytest.raises(CompositionError) as target_error:

        class WrappedTarget(StrictMixin):
            __slots__ = ()

            @functools.wraps(unsafe)
            def render(self) -> str:
                return "wrapper"

    assert_code(target_error, "super-not-supported")


def test_wrapped_callable_cycle_is_rejected() -> None:
    def cyclic(self: object) -> str:
        return "x"

    cyclic.__wrapped__ = cyclic  # type: ignore[attr-defined]

    with pytest.raises(CompositionError) as error:

        class Invalid(StrictMixin):
            __slots__ = ()
            render = cyclic

    assert_code(error, "wrapped-callable-cycle")


def test_unadmitted_local_member_cannot_hide_conflict() -> None:
    @trait
    class A(Trait):
        __slots__ = ()

        def render(self) -> str:
            return "a"

    @trait
    class B(Trait):
        __slots__ = ()

        def render(self) -> str:
            return "b"

    with pytest.raises(CompositionError) as data_error:

        class Data(A, B):
            __slots__ = ()
            render = 42

    assert_code(data_error, "unsupported-local-resolution")

    with pytest.raises(CompositionError) as static_error:

        class Static(A, B):
            __slots__ = ()

            @staticmethod
            def render() -> str:
                return "static"

    assert_code(static_error, "incompatible-member-kind")


def test_annotation_and_slot_cannot_shadow_inherited_member() -> None:
    @trait
    class Contract(Trait):
        __slots__ = ()

        def value(self) -> int:
            return 1

    with pytest.raises(CompositionError) as annotation_error:

        class Annotated(Contract):
            __slots__ = ()
            value: int

    assert_code(annotation_error, "annotation-shadows-member")

    with pytest.raises(CompositionError) as slot_error:

        class Slotted(Contract):
            __slots__ = ("value",)

    assert_code(slot_error, "slot-shadows-member")
