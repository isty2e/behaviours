from __future__ import annotations

import concurrent.futures
from abc import ABCMeta

import pytest

try:
    from typing import override
except ImportError:  # pragma: no cover - Python 3.11
    from typing_extensions import override

from behaviours import CompositionError, StrictMixin, Trait, trait
from behaviours.composition import Admission


def assert_code(error: pytest.ExceptionInfo[CompositionError], code: str) -> None:
    assert error.value.code == code


def test_noncooperative_hook_runs_but_cannot_bypass_topology() -> None:
    events: list[str] = []

    class Mixin(StrictMixin):
        def mixed(self) -> bool:
            return True

    class Base:
        def __init_subclass__(cls, **kwargs: object) -> None:
            events.append(cls.__name__)

    class Valid(Mixin, Base):
        pass

    assert Valid().mixed()
    assert events == ["Valid"]
    with pytest.raises(CompositionError):

        class Invalid(Base, Mixin):
            pass

    assert events == ["Valid"]


def test_ordinary_base_hook_cannot_replace_mixin_binding() -> None:
    class Mixin(StrictMixin):
        def mixed(self) -> bool:
            return True

    class ChangingBase:
        def __init_subclass__(cls, **kwargs: object) -> None:
            del kwargs
            cls.mixed = lambda self: False

    with pytest.raises(CompositionError) as error:
        type(
            "Changed",
            (Mixin, ChangingBase),
            {"__module__": __name__, "__slots__": ()},
        )
    assert_code(error, "runtime-surface-drift")


def test_custom_set_name_may_configure_unrelated_ordinary_members() -> None:
    events: list[str] = []

    class Mixin(StrictMixin):
        def mixed(self) -> bool:
            return True

    class Base:
        pass

    class Descriptor:
        def __set_name__(self, owner: type, name: str) -> None:
            events.append(owner.__name__)
            owner.render = lambda self: "configured"

    class Valid(Mixin, Base):
        descriptor = Descriptor()

    assert Valid().mixed()
    assert Valid().render() == "configured"
    assert events == ["Valid"]


def test_custom_set_name_cannot_fake_empty_slots() -> None:
    events: list[str] = []

    class FakeSlots:
        def __set_name__(self, owner: type, name: str) -> None:
            events.append(owner.__name__)
            owner.__slots__ = ()

    with pytest.raises(CompositionError) as error:

        class Invalid(StrictMixin):
            injector = FakeSlots()

            def value(self) -> int:
                return 1

    assert_code(error, "set-name-transform-not-supported")
    assert events == []


def test_metadata_forgery_cannot_skip_admission() -> None:
    class Valid(StrictMixin):
        __slots__ = ()

        def value(self) -> int:
            return 1

    forged = Admission.spec_for(Valid)
    assert forged is not None

    with pytest.raises(CompositionError) as error:

        class Invalid(StrictMixin):
            __slots__ = ()
            __composition_spec__ = forged

            def __init__(self) -> None:
                self.value = 1

    assert_code(error, "reserved-composition-metadata")


def test_nominal_calculus_cannot_be_polluted_by_abc_registration() -> None:
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

    with pytest.raises(CompositionError) as registration_error:
        A.register(B)
    assert_code(registration_error, "virtual-subclass-not-supported")

    with pytest.raises(CompositionError) as conflict_error:

        class Invalid(A, B):
            __slots__ = ()

    assert_code(conflict_error, "unresolved-member-conflict")


def test_custom_metaclass_ordinary_base_is_out_of_scope() -> None:
    class CustomMeta(ABCMeta):
        pass

    class Base(metaclass=CustomMeta):
        pass

    class Mixin(StrictMixin):
        __slots__ = ()

        def value(self) -> int:
            return 1

    with pytest.raises(TypeError):

        class Invalid(Mixin, Base):
            pass


def test_transform_can_add_unrelated_method_but_cannot_replace_behavior() -> None:
    @trait
    class Contract:
        def value(self) -> int:
            return 1

    def transform(cls: type) -> type:
        cls.generated = lambda self: 2
        return cls

    @transform
    class Valid(Contract):
        pass

    assert Valid().generated() == 2
    with pytest.raises(CompositionError) as error:
        Valid.value = lambda self: 3
    assert_code(error, "protected-composition-member")


def test_related_direct_bases_are_rejected() -> None:
    @trait
    class A(Trait):
        __slots__ = ()

        def value(self) -> int:
            return 1

    @trait
    class B(A):
        __slots__ = ()

    with pytest.raises(CompositionError) as error:

        class Invalid(A, B):
            __slots__ = ()

    assert_code(error, "redundant-behaviour-bases")


def test_trait_and_strict_mixin_cannot_share_one_join() -> None:
    @trait
    class Contract(Trait):
        __slots__ = ()

        def value(self) -> int:
            return 1

    class Mixin(StrictMixin):
        __slots__ = ()

        def mixed(self) -> int:
            return 2

    with pytest.raises(CompositionError) as error:

        class Invalid(Mixin, Contract):
            __slots__ = ()

    assert_code(error, "unsupported-inheritance-topology")


def test_mixin_base_order_does_not_resolve_conflict() -> None:
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

    for bases in ((A, B, Base), (B, A, Base)):
        with pytest.raises(CompositionError) as error:
            type("Invalid", bases, {"__module__": __name__})
        assert_code(error, "unresolved-member-conflict")


def test_trait_permutations_have_same_runtime_surface() -> None:
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

    class AB(A, B):
        __slots__ = ()

    class BA(B, A):
        __slots__ = ()

    assert (AB().a(), AB().b()) == ("a", "b")
    assert (BA().a(), BA().b()) == ("a", "b")
    assert set(Admission.spec_for(AB).members) == set(Admission.spec_for(BA).members)


def test_hash_conflict_is_order_independent_at_runtime_boundary() -> None:
    @trait
    class Equal(Trait):
        __slots__ = ()

        def __eq__(self, other: object) -> bool:
            return self is other

    @trait
    class Hashed(Trait):
        __slots__ = ()

        def __hash__(self) -> int:
            return 1

    for bases in ((Equal, Hashed), (Hashed, Equal)):
        with pytest.raises(CompositionError) as error:
            type("Invalid", bases, {"__module__": __name__, "__slots__": ()})
        assert_code(error, "unresolved-member-conflict")


def test_concurrent_class_creation_does_not_cross_contaminate_state() -> None:
    class Mixin(StrictMixin):
        __slots__ = ()

        def value(self) -> int:
            return 1

    class Base:
        pass

    def create(index: int) -> tuple[str, int]:
        cls = type(
            f"Generated{index}",
            (Mixin, Base),
            {"__module__": __name__, "__slots__": ()},
        )
        return cls.__name__, cls().value()

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(create, range(64)))

    assert results == [(f"Generated{index}", 1) for index in range(64)]


def test_ordinary_descendant_hook_does_not_bypass_future_mixin_admission() -> None:
    @trait
    class Contract:
        def value(self) -> int:
            return 1

    class Closed(Contract):
        pass

    class Hooked(Closed):
        def __init_subclass__(cls, **kwargs: object) -> None:
            pass

    class Mixin(StrictMixin):
        def mixed(self) -> int:
            return 2

    class Valid(Mixin, Hooked):
        pass

    assert Valid().mixed() == 2
    assert Valid().value() == 1
    with pytest.raises(CompositionError):

        class Bad(Valid, Closed):
            pass

    with pytest.raises(CompositionError):
        Valid.value = lambda self: 3


def test_local_conflict_resolution_is_checked_before_base_hooks_exist() -> None:
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

    class Valid(A, B, Base):
        @override
        def render(self) -> str:
            return A.render(self)

    assert Valid().render() == "a"
