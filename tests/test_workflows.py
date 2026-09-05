"""Normal class-building workflows and accidental composition regressions."""

from dataclasses import dataclass, field, replace

import pytest

from behaviours import CompositionError, StrictMixin, trait


@trait
class Answer:
    def answer(self) -> int:
        return 42


class AnswerMixin(StrictMixin):
    def answer(self) -> int:
        return 42


class Plain:
    pass


@pytest.mark.parametrize("slots", [False, True])
@pytest.mark.parametrize("frozen", [False, True])
def test_dataclass_direct_adoption(slots: bool, frozen: bool) -> None:
    @dataclass(slots=slots, frozen=frozen)
    class Record(Answer):
        value: int
        tags: list[str] = field(default_factory=list)

    value = Record(3)
    assert value.answer() == 42
    assert replace(value, value=4).value == 4
    assert value.tags == []
    assert hasattr(value, "__dict__") is not slots


@pytest.mark.parametrize("slots", [False, True])
def test_dataclass_direct_mixin_join(slots: bool) -> None:
    @dataclass(slots=slots)
    class Record(AnswerMixin, Plain):
        value: int

    assert Record(3).answer() == 42


def test_hook_runs_once_with_keywords_and_may_add_metadata() -> None:
    events = []

    class Base:
        def __init_subclass__(cls, *, label="default", **kwargs):
            events.append((cls, label))
            cls.label = label
            cls.build = classmethod(lambda cls: cls())
            super().__init_subclass__(**kwargs)

    class Applied(AnswerMixin, Base, label="records"):
        pass

    assert events == [(Applied, "records")]
    assert Applied.build().answer() == 42
    assert Applied.label == "records"


def test_noncooperative_hook_cannot_disable_admission() -> None:
    class Base:
        def __init_subclass__(cls, **kwargs):
            pass

    class Applied(AnswerMixin, Base):
        pass

    assert Applied().answer() == 42
    with pytest.raises(CompositionError):

        class Bad(Base, AnswerMixin):
            pass

    with pytest.raises(CompositionError):

        class BadDescendant(Applied, Plain):
            pass


def test_hook_changes_protected_provider_is_rejected() -> None:
    class Base:
        def __init_subclass__(cls, **kwargs):
            cls.answer = lambda self: -1

    with pytest.raises(CompositionError):

        class Applied(AnswerMixin, Base):
            pass


def test_nonconflicting_descriptor_is_allowed() -> None:
    class Constant:
        def __set_name__(self, owner, name):
            self.name = name

        def __get__(self, instance, owner=None):
            return 7

    class Record(Answer):
        constant = Constant()

    assert Record().constant == 7
    assert Record().answer() == 42


def test_unrelated_class_configuration_is_allowed_but_member_is_protected() -> None:
    class Record(Answer):
        pass

    Record.label = "test"
    assert Record.label == "test"
    del Record.label
    with pytest.raises(CompositionError):
        Record.answer = lambda self: -1
    with pytest.raises(CompositionError):
        del Record.answer
    assert Record().answer() == 42


def test_descendant_field_shadow_is_rejected() -> None:
    class Record(Answer):
        pass

    with pytest.raises(CompositionError):

        @dataclass
        class Bad(Record):
            answer: int


def test_explicit_ordinary_override_can_use_super() -> None:
    class Record(Answer):
        pass

    class Child(Record):
        def answer(self) -> int:
            return super().answer() + 1

    assert Child().answer() == 43


@pytest.mark.parametrize("slots", [False, True])
def test_generated_repr_must_not_replace_trait_repr(slots):
    @trait
    class Renderable:
        def __repr__(self):
            return "trait-repr"

    with pytest.raises(CompositionError):

        @dataclass(slots=slots)
        class Bad(Renderable):
            raw: int

    @dataclass(slots=slots, repr=False)
    class Good(Renderable):
        raw: int

    assert repr(Good(3)) == "trait-repr"


@pytest.mark.parametrize("slots", [False, True])
def test_generated_hash_must_not_replace_trait_hash(slots):
    @trait
    class Hashed:
        def __hash__(self):
            return 13

    with pytest.raises(CompositionError):

        @dataclass(slots=slots, frozen=True)
        class Bad(Hashed):
            raw: int

    @dataclass(slots=slots, eq=False)
    class Good(Hashed):
        raw: int

    assert hash(Good(3)) == 13


def test_hook_metadata_changes_do_not_change_provided_function_identity():
    original = AnswerMixin.__dict__["answer"]

    class ConfiguredBase:
        def __init_subclass__(cls, **kwargs):
            cls.schema = {"version": 1}
            cls.extra = lambda self: 8

    class Result(AnswerMixin, ConfiguredBase):
        pass

    import inspect

    assert inspect.getattr_static(Result, "answer") is original
    assert Result().extra() == 8


def test_same_owner_replacement_by_hook_is_detected():
    class HookBase:
        def __init_subclass__(cls):
            cls.answer = lambda self: -1

    with pytest.raises(CompositionError, match="replaced"):

        class Bad(AnswerMixin, HookBase):
            def answer(self):
                return 43


def test_failed_hook_class_retained_by_registry_cannot_be_instantiated():
    registry = []

    class Base:
        def __init_subclass__(cls):
            registry.append(cls)
            cls.answer = lambda self: -1

    with pytest.raises(CompositionError):

        class Bad(AnswerMixin, Base):
            pass

    assert len(registry) == 1  # Registration is not transactionally rolled back.
    with pytest.raises(TypeError):
        registry[0]()


def test_hook_cannot_add_data_annotation_over_inherited_method():
    class Base:
        def __init_subclass__(cls):
            cls.__annotations__ = {"answer": int}

    with pytest.raises(CompositionError):

        class Bad(AnswerMixin, Base):
            pass


def test_related_old_members_stay_protected_after_mixin_application():
    class Extra(StrictMixin):
        def extra(self):
            return 7

    class First(Answer):
        pass

    class Second(Extra, First):
        pass

    class Third(Second):
        def extra(self):
            return super().extra() + 1

    assert Third().answer() == 42 and Third().extra() == 8
    for cls in (Second, Third):
        with pytest.raises(CompositionError):
            cls.answer = 3
        with pytest.raises(CompositionError):

            @dataclass
            class Bad(cls):
                answer: int


def test_dataclass_initvar_classvar_and_post_init():
    from dataclasses import InitVar
    from typing import ClassVar

    @dataclass(kw_only=True)
    class Record(Answer):
        raw: int
        scale: InitVar[int] = 2
        marker: ClassVar[str] = "record"
        computed: int = field(init=False)

        def __post_init__(self, scale):
            self.computed = self.raw * scale

    assert Record(raw=3).computed == 6
    assert Record(raw=3, scale=4).computed == 12
    assert Record(raw=3).answer() == 42


def test_source_conflicts_precede_registration_hook():
    events = []

    class Left(StrictMixin):
        def value(self):
            return 1

    class Right(StrictMixin):
        def value(self):
            return 2

    class Base:
        def __init_subclass__(cls):
            events.append(cls)

    with pytest.raises(CompositionError):

        class Bad(Left, Right, Base):
            pass

    assert events == []


def test_benign_hooks_run_after_rebuilding_just_like_native_dataclasses():
    events = []

    class Base:
        def __init_subclass__(cls, *, label="default"):
            events.append((cls, label))

    @dataclass(slots=True)
    class Record(AnswerMixin, Base):
        raw: int

    # slots=True creates a replacement class: Python runs its base hook again.
    assert len(events) == 2
    assert events[-1] == (Record, "default")
    assert Record(3).answer() == 42
