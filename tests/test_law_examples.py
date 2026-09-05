"""Reusable semantic laws remain ordinary user-owned tests, not a runtime DSL."""

from collections.abc import Callable

import pytest

from behaviours import mixin
from behaviours.testing import assert_composition


@mixin
class Trimmed:
    @staticmethod
    def normalize(value: str) -> str:
        return value.strip()


@mixin
class Folded:
    @staticmethod
    def normalize(value: str) -> str:
        return value.casefold().strip()


@pytest.fixture(params=[Trimmed.normalize, Folded.normalize])
def normalizer(request) -> Callable[[str], str]:
    return request.param


@pytest.mark.parametrize("value", ["", " a ", "ABC", "  Straße\n", " \t\n"])
def test_normalization_is_idempotent(normalizer, value):
    # This law is chosen for these implementations, not inferred from the name.
    assert normalizer(normalizer(value)) == normalizer(value)


def test_testing_adapter_is_explicit_and_does_not_import_a_test_framework():
    assert_composition(Trimmed)
    assert_composition(Folded)
    with pytest.raises(AssertionError, match="not managed"):
        assert_composition(str)
