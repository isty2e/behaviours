"""Strict native-inheritance behaviour composition."""

from importlib.metadata import PackageNotFoundError, version

from behaviours.composition import CompositionError
from behaviours.declare import StrictMixin, Trait, mixin, trait
from behaviours.inspect import CompositionReport, inspect_composition

try:
    __version__ = version("behaviours")
except PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "CompositionError",
    "CompositionReport",
    "StrictMixin",
    "Trait",
    "inspect_composition",
    "mixin",
    "trait",
]
