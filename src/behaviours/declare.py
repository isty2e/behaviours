"""Trait and StrictMixin declaration constructors."""

from __future__ import annotations

import types
from abc import ABC, ABCMeta
from collections.abc import Mapping
from typing import TypeVar, cast

from behaviours.admission import Admission, BehaviourMeta
from behaviours.composition import (
    ADMISSION_ATTRIBUTE,
    BOOTSTRAP_TOKEN,
    CompositionError,
    class_namespace,
    nominal_subclass,
)
from behaviours.members import is_abstract, iter_wrapped_functions
from behaviours.topology import ClassRole

ClassT = TypeVar("ClassT", bound=type)


def _trait_namespace(cls: type) -> dict[str, object]:
    namespace = dict(class_namespace(cls))
    admission = Admission.of(cls)
    if admission is not None:
        namespace.pop(ADMISSION_ATTRIBUTE, None)
    slots = namespace.get("__slots__", ())
    if type(slots) is not tuple or slots != ():
        raise CompositionError(
            f"{cls.__qualname__} may not introduce instance slots",
            code="nonempty-behaviour-layout",
        )
    for name in ("__dict__", "__weakref__"):
        value = namespace.get(name)
        if type(value) is types.GetSetDescriptorType and value.__objclass__ is cls:
            del namespace[name]
    if type(cls) in (ABCMeta, BehaviourMeta):
        namespace.pop("__abstractmethods__", None)
        namespace.pop("_abc_impl", None)
    namespace["__qualname__"] = cls.__qualname__
    return namespace


def _retarget_class_cells(
    source: type, result: type, namespace: Mapping[str, object]
) -> None:
    # The declaration is replaced, not made a base: retaining it would retain its
    # instance dictionary. Its lexical __class__ cells must name the public type.
    for value in namespace.values():
        if type(value) not in (types.FunctionType, property, classmethod, staticmethod):
            continue
        for function in iter_wrapped_functions(value):
            for name, cell in zip(
                function.__code__.co_freevars, function.__closure__ or (), strict=True
            ):
                try:
                    contents = cell.cell_contents
                except ValueError:
                    continue
                if name == "__class__" and contents is source:
                    cell.cell_contents = result


def trait(cls: ClassT, /) -> ClassT:
    """Declare a state-free trait without adding a public method surface.

    Parameters
    ----------
    cls : type
        Fresh class declaration with no ordinary base. Its bases may be traits,
        ``abc.ABC`` and ``typing.Generic``. Abstract declarations must inherit
        ``abc.ABC`` so static checkers see their obligations.

    Returns
    -------
    type
        Replacement class with the same declared bases, methods and type
        signature. Empty slots and the admission metaclass are installed during
        construction. Subsequent undecorated subclasses are ordinary adopters.

    Raises
    ------
    CompositionError
        If the declaration has state, incompatible bases, existing subclasses,
        hidden abstract obligations, or other unsupported behavior members.

    Notes
    -----
    Apply directly to a fresh declaration, before instances or aliases escape.
    This is not an in-place role conversion. Other class-transforming decorators
    on the same declaration are unsupported. No stub or checker plugin is used.
    """
    return _declare_behaviour(cls, ClassRole.TRAIT)


def mixin(cls: ClassT, /) -> ClassT:
    """Declare a state-free strict mixin using ordinary class syntax.

    Parameters
    ----------
    cls : type
        Fresh class whose bases are strict mixins or typing infrastructure.

    Returns
    -------
    type
        Same declared API under the composition metaclass with automatic empty
        slots. Apply it before exactly one ordinary base, placed last.

    Raises
    ------
    CompositionError
        If the class owns state/lifecycle, has abstract requirements, includes an
        ordinary base, or has already been used as an application.

    Notes
    -----
    Like ``StrictMixin`` inheritance, mixin-only subclasses remain definitions.
    Repeating the decorator on an admitted definition is harmless. This differs
    intentionally from traits: a mixin application is identified by its explicit
    ordinary base, not by omission of the decorator.
    """
    return _declare_behaviour(cls, ClassRole.STRICT_MIXIN)


def _declare_behaviour(cls: ClassT, role: ClassRole) -> ClassT:
    marker = "@trait" if role is ClassRole.TRAIT else "@mixin"
    if not isinstance(cls, type) or type(cls) not in (type, ABCMeta, BehaviourMeta):
        raise CompositionError(
            f"{marker} requires a class with the standard or behaviours metaclass",
            code="invalid-trait-target"
            if role is ClassRole.TRAIT
            else "invalid-mixin-target",
        )
    state = Admission.of(cls)
    if state is not None and state.role is role:
        return cls
    if state is not None and not (
        role is ClassRole.TRAIT and state.role is ClassRole.TRAIT_ADOPTER
    ):
        raise CompositionError(
            f"{marker} cannot reopen an ordinary or different behavior lineage",
            code="invalid-trait-target"
            if role is ClassRole.TRAIT
            else "invalid-mixin-target",
        )
    if type.__subclasses__(cls):
        raise CompositionError(
            f"{marker} must precede subclassing of its declaration",
            code="late-trait-decoration"
            if role is ClassRole.TRAIT
            else "late-mixin-decoration",
        )
    namespace = _trait_namespace(cls)
    if (
        role is ClassRole.TRAIT
        and any(is_abstract(value) for value in namespace.values())
        and not nominal_subclass(cls, ABC)
    ):
        raise CompositionError(
            "abstract traits must inherit abc.ABC "
            "so static checkers can enforce missing implementations",
            code="abstract-trait-needs-abc",
        )
    bases = type.__getattribute__(cls, "__bases__")
    if bases == (object,):
        bases = ()
    result = BehaviourMeta(cls.__name__, bases, namespace, _definition=role)
    _retarget_class_cells(cls, result, namespace)
    return cast(ClassT, result)


class Trait(
    ABC,
    metaclass=BehaviourMeta,
    _bootstrap=BOOTSTRAP_TOKEN,
    _root_role=ClassRole.TRAIT,
):
    """Optional ABC base for ``@trait`` declarations.

    The decorator is the role marker. New concrete traits need no base at all;
    abstract traits can use the standard-library ``abc.ABC`` instead of this root.
    """

    __slots__ = ()


class StrictMixin(
    metaclass=BehaviourMeta,
    _bootstrap=BOOTSTRAP_TOKEN,
    _root_role=ClassRole.STRICT_MIXIN,
):
    """Root for state-free implementation providers applied before one base."""

    __slots__ = ()


__all__ = [
    "StrictMixin",
    "Trait",
    "mixin",
    "trait",
]
