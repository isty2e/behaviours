"""Inspection observes native members without invoking or re-admitting them."""

import copy
import pickle
from abc import ABC, abstractmethod
from dataclasses import FrozenInstanceError, dataclass
from typing import final

import pytest

from behaviours import CompositionError, inspect_composition, mixin, trait


@trait
class A:
    def value(self) -> int:
        return 1


@trait
class B:
    def value(self) -> int:
        return 2


def test_conflict_contains_provenance_and_serializes():
    with pytest.raises(CompositionError) as caught:

        class Bad(A, B):
            pass

    e = caught.value
    assert e.code == "unresolved-member-conflict"
    assert e.member == "value"
    assert e.phase == "definition"
    assert {o.owner for o in e.origins} == {A, B}
    assert all(o.location.path == __file__ and o.location.line > 0 for o in e.origins)
    assert "test_inspection.py:" in str(e)
    assert e.hint is not None
    for restored in (copy.copy(e), pickle.loads(pickle.dumps(e))):
        assert str(restored) == str(e)
        assert restored.code == e.code and restored.member == e.member


def test_valid_reports_include_ordinary_descendants_without_calling_getters():
    @trait
    class Feature:
        @property
        def read(self) -> int:
            raise AssertionError("must not call getter")

        @classmethod
        def create(cls):
            return cls()

        @staticmethod
        def parse(text):
            return int(text)

        @final
        def value(self):
            return 1

    class Subject(Feature):
        pass

    class Child(Subject):
        pass

    for c in (Feature, Subject, Child):
        report = inspect_composition(c)
        assert report.is_valid and not report.issues
        assert report.members["value"].final
        assert report.members["create"].expected_kind.value == "class-method"
        assert report.members["read"].location.path == __file__
        assert "value" in report.format()
        report.raise_if_invalid()
        with pytest.raises(TypeError):
            report.members["new"] = report.members["value"]
        with pytest.raises(FrozenInstanceError):
            report.role = None


def test_unmanaged_is_explicitly_not_verified():
    class Plain:
        pass

    report = inspect_composition(Plain)
    assert report.role is None and not report.is_valid
    assert "not managed" in report.format()
    with pytest.raises(CompositionError):
        report.raise_if_invalid()
    with pytest.raises(TypeError):
        inspect_composition(Plain())


def test_external_base_drift_is_reported_not_repaired():
    @mixin
    class M:
        def value(self):
            return 1

    class Base:
        def value(self):
            return 2

    class Subject(M, Base):
        value = Base.value

    before = inspect_composition(Subject)
    assert before.is_valid

    # A second managed class inherits an ordinary final member through an opaque base.
    class OtherBase:
        @final
        def stable(self):
            return 3

    class Other(M, OtherBase):
        pass

    original = OtherBase.stable
    OtherBase.stable = lambda self: 4
    try:
        report = inspect_composition(Other)
        assert not report.is_valid
        assert any(
            i.code == "binding-drift" and i.member == "stable" for i in report.issues
        )
        assert Other().stable() == 4  # Inspection never repairs/re-registers drift.
    finally:
        OtherBase.stable = original


def test_in_place_generated_field_change_is_detected_on_request():
    @dataclass
    class Subject(A):
        field: int

    old = dict(Subject.__dataclass_fields__)
    try:
        Subject.__dataclass_fields__["value"] = Subject.__dataclass_fields__["field"]
        report = inspect_composition(Subject)
        assert not report.is_valid
        assert any(i.code == "generated-field-shadows-member" for i in report.issues)
    finally:
        Subject.__dataclass_fields__.clear()
        Subject.__dataclass_fields__.update(old)


def test_abstract_declaration_is_valid_not_incomplete_configuration():
    @trait
    class Abstract(ABC):
        @abstractmethod
        def value(self): ...

    report = inspect_composition(Abstract)
    assert report.is_valid
    assert report.members["value"].abstract


def test_mutation_and_postflight_errors_identify_phase():
    class Subject(A):
        pass

    with pytest.raises(CompositionError) as caught:
        Subject.value = lambda self: 2
    assert caught.value.phase == "mutation" and caught.value.member == "value"

    @mixin
    class M:
        def value(self):
            return 1

    class Base:
        def __init_subclass__(cls, **kwargs):
            cls.value = lambda self: 2

    with pytest.raises(CompositionError) as caught:

        class Bad(M, Base):
            pass

    assert caught.value.phase == "construction"


def test_abstractness_compares_saved_obligation_not_mutated_function_marker():
    from abc import update_abstractmethods

    @trait
    class Feature(ABC):
        @abstractmethod
        def value(self): ...

    class Subject(Feature):
        pass

    function = Feature.__dict__["value"]
    try:
        function.__isabstractmethod__ = False
        update_abstractmethods(Subject)
        report = inspect_composition(Subject)
        assert not report.is_valid
        assert report.members["value"].abstract
        assert any(i.code == "abstractness-drift" for i in report.issues)
    finally:
        function.__isabstractmethod__ = True
        update_abstractmethods(Subject)
