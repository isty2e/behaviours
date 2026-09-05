"""Member grammar for admitted methods and read-only properties."""

from __future__ import annotations

import builtins
import dis
import inspect
import types
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from behaviours.composition import (
    ADMISSION_ATTRIBUTE,
    INTERPRETER_CLASS_NAMES,
    MISSING,
    RESERVED_METADATA_NAME,
    CompositionError,
    class_annotations,
)

if TYPE_CHECKING:
    from behaviours.origin import MemberOrigin

_FORBIDDEN_BEHAVIOUR_NAMES = frozenset(
    {
        "__aenter__",
        "__aexit__",
        "__del__",
        "__delattr__",
        "__enter__",
        "__exit__",
        "__getattr__",
        "__getattribute__",
        "__init__",
        "__init_subclass__",
        "__new__",
        "__post_init__",
        "__setattr__",
    }
)

_ALLOWED_DUNDER_METHODS = frozenset(
    {
        "__abs__",
        "__add__",
        "__and__",
        "__bool__",
        "__bytes__",
        "__call__",
        "__ceil__",
        "__contains__",
        "__delitem__",
        "__divmod__",
        "__eq__",
        "__float__",
        "__floor__",
        "__floordiv__",
        "__format__",
        "__ge__",
        "__getitem__",
        "__gt__",
        "__hash__",
        "__index__",
        "__int__",
        "__invert__",
        "__iter__",
        "__le__",
        "__len__",
        "__lshift__",
        "__lt__",
        "__matmul__",
        "__mod__",
        "__mul__",
        "__ne__",
        "__neg__",
        "__next__",
        "__or__",
        "__pos__",
        "__pow__",
        "__radd__",
        "__rand__",
        "__rdivmod__",
        "__repr__",
        "__reversed__",
        "__rfloordiv__",
        "__rlshift__",
        "__rmatmul__",
        "__rmod__",
        "__rmul__",
        "__ror__",
        "__round__",
        "__rpow__",
        "__rrshift__",
        "__rshift__",
        "__rsub__",
        "__rtruediv__",
        "__rxor__",
        "__setitem__",
        "__str__",
        "__sub__",
        "__truediv__",
        "__trunc__",
        "__xor__",
    }
)

_METHOD_DESCRIPTOR_TYPES = (
    types.FunctionType,
    types.MethodDescriptorType,
    types.WrapperDescriptorType,
)


class MemberKind(StrEnum):
    """A composition-relevant member category."""

    METHOD = "method"
    ASYNC_METHOD = "async-method"
    ASYNC_GENERATOR_METHOD = "async-generator-method"
    READ_ONLY_PROPERTY = "read-only-property"
    HASH_DISABLED = "hash-disabled"
    CLASS_METHOD = "class-method"
    ASYNC_CLASS_METHOD = "async-class-method"
    ASYNC_GENERATOR_CLASS_METHOD = "async-generator-class-method"
    STATIC_METHOD = "static-method"
    ASYNC_STATIC_METHOD = "async-static-method"
    ASYNC_GENERATOR_STATIC_METHOD = "async-generator-static-method"

    @classmethod
    def of_function(cls, value: types.FunctionType) -> MemberKind:
        match inspect.isasyncgenfunction(value), inspect.iscoroutinefunction(value):
            case True, _:
                return cls.ASYNC_GENERATOR_METHOD
            case False, True:
                return cls.ASYNC_METHOD
            case False, False:
                return cls.METHOD
            case _:
                raise AssertionError("unreachable function kind")

    @classmethod
    def of_descriptor(cls, value: object) -> MemberKind:
        if type(value) is classmethod:
            kinds = (
                cls.CLASS_METHOD,
                cls.ASYNC_CLASS_METHOD,
                cls.ASYNC_GENERATOR_CLASS_METHOD,
            )
            function = value.__func__
        elif type(value) is staticmethod:
            kinds = (
                cls.STATIC_METHOD,
                cls.ASYNC_STATIC_METHOD,
                cls.ASYNC_GENERATOR_STATIC_METHOD,
            )
            function = value.__func__
        else:
            raise CompositionError(
                "classmethod/staticmethod must wrap an ordinary Python function",
                code="unsupported-wrapped-callable",
            )
        if type(function) is not types.FunctionType:
            raise CompositionError(
                "classmethod/staticmethod must wrap an ordinary Python function",
                code="unsupported-wrapped-callable",
            )
        match (
            inspect.isasyncgenfunction(function),
            inspect.iscoroutinefunction(function),
        ):
            case True, _:
                return kinds[2]
            case False, True:
                return kinds[1]
            case False, False:
                return kinds[0]
            case _:
                raise AssertionError("unreachable descriptor kind")

    @classmethod
    def of_runtime(cls, name: str, value: object) -> MemberKind:
        if name == "__hash__" and value is None:
            return cls.HASH_DISABLED
        if name == "__hash__" and value is object.__hash__:
            return cls.METHOD
        if type(value) is types.FunctionType:
            return cls.of_function(value)
        if type(value) is classmethod or type(value) is staticmethod:
            return cls.of_descriptor(value)
        if type(value) is property:
            if value.fget is None or value.fset is not None or value.fdel is not None:
                raise CompositionError(
                    f"runtime member {name} is not a readable, read-only property",
                    code="runtime-member-kind-drift",
                )
            return cls.READ_ONLY_PROPERTY
        if type(value) in _METHOD_DESCRIPTOR_TYPES:
            return cls.METHOD
        raise CompositionError(
            f"runtime member {name} is not an admitted instance member",
            code="unsupported-runtime-member",
        )

    @staticmethod
    def compatible_local(
        name: str,
        local_kind: MemberKind,
        active_kinds: frozenset[MemberKind],
    ) -> bool:
        if not active_kinds:
            return True
        if name == "__hash__":
            return active_kinds <= {
                MemberKind.METHOD,
                MemberKind.HASH_DISABLED,
            } and local_kind in {
                MemberKind.METHOD,
                MemberKind.HASH_DISABLED,
            }
        return active_kinds == frozenset({local_kind})


def _is_dunder(name: str) -> bool:
    return len(name) > 4 and name.startswith("__") and name.endswith("__")


def is_abstract(value: object) -> bool:
    if type(value) is property:
        return is_abstract(value.fget)
    if type(value) is classmethod or type(value) is staticmethod:
        return is_abstract(value.__func__)
    if type(value) is types.FunctionType:
        marker = value.__dict__.get("__isabstractmethod__", False)
        if type(marker) is not bool:
            raise CompositionError(
                "__isabstractmethod__ must be a literal bool",
                code="invalid-abstract-marker",
            )
        return marker
    return False


def iter_wrapped_functions(value: object) -> Iterator[types.FunctionType]:
    if type(value) is property:
        if value.fget is None:
            return
        current: object = value.fget
    elif type(value) is classmethod or type(value) is staticmethod:
        current = value.__func__
    else:
        current = value

    seen: set[int] = set()
    while True:
        identity = id(current)
        if identity in seen:
            raise CompositionError(
                "wrapped callable chain contains a cycle",
                code="wrapped-callable-cycle",
            )
        seen.add(identity)

        if type(current) is not types.FunctionType:
            raise CompositionError(
                "wrapped callable chain must contain only Python functions",
                code="unsupported-wrapped-callable",
            )
        yield current

        wrapped = getattr(current, "__wrapped__", None)
        if wrapped is None:
            return
        current = wrapped


def _code_names(code: types.CodeType) -> Iterator[str]:
    for instruction in dis.get_instructions(code):
        if instruction.opname in {
            "LOAD_GLOBAL",
            "LOAD_NAME",
            "LOAD_ATTR",
            "LOAD_METHOD",
        } and isinstance(instruction.argval, str):
            yield instruction.argval
    for constant in code.co_consts:
        if isinstance(constant, types.CodeType):
            yield from _code_names(constant)


def _contains_super(value: object, seen: set[int]) -> bool:
    # Do not invoke user-defined iteration, descriptors, or equality during admission.
    if value is builtins.super:
        return True
    identity = id(value)
    if identity in seen:
        return False
    seen.add(identity)
    if (
        type(value) is tuple
        or type(value) is list
        or type(value) is set
        or type(value) is frozenset
    ):
        return any(_contains_super(item, seen) for item in value)
    if type(value) is dict:
        return any(
            _contains_super(item, seen) for pair in value.items() for item in pair
        )
    return False


def validate_no_super(value: object, /, *, owner: str, name: str) -> None:
    for function in iter_wrapped_functions(value):
        names = set(_code_names(function.__code__))
        uses_super = "super" in names
        if not uses_super:
            references = [function.__globals__.get(key) for key in names]
            references.extend(function.__defaults__ or ())
            references.extend((function.__kwdefaults__ or {}).values())
            for cell in function.__closure__ or ():
                try:
                    references.append(cell.cell_contents)
                except ValueError:
                    continue
            uses_super = any(_contains_super(item, set()) for item in references)
        if uses_super:
            raise CompositionError(
                f"{owner}.{name} may not use super(); use a qualified provider call",
                code="super-not-supported",
            )


@dataclass(frozen=True, slots=True)
class LocalMember:
    value: object
    kind: MemberKind
    abstract: bool
    explicit: bool

    @staticmethod
    def require_receiver(value: types.FunctionType, *, owner: str, name: str) -> None:
        if value.__code__.co_argcount < 1:
            raise CompositionError(
                f"{owner}.{name} needs a positional receiver",
                code="missing-method-receiver",
            )

    @classmethod
    def classify_function(
        cls,
        name: str,
        value: types.FunctionType,
        /,
        *,
        owner: str,
    ) -> MemberKind:
        if name in _FORBIDDEN_BEHAVIOUR_NAMES:
            raise CompositionError(
                f"{owner}.{name} owns lifecycle or attribute-resolution behaviour",
                code="forbidden-behaviour-member",
            )
        if _is_dunder(name) and name not in _ALLOWED_DUNDER_METHODS:
            raise CompositionError(
                f"{owner}.{name} is not an admitted operator method",
                code="unsupported-dunder-member",
            )

        validate_no_super(value, owner=owner, name=name)

        cls.require_receiver(value, owner=owner, name=name)
        kind = MemberKind.of_function(value)
        if _is_dunder(name) and kind is not MemberKind.METHOD:
            raise CompositionError(
                f"{owner}.{name} may not be an async operator method",
                code="async-dunder-not-supported",
            )
        if (
            _is_dunder(name)
            and inspect.isgeneratorfunction(value)
            and name
            not in {
                "__iter__",
                "__reversed__",
                "__call__",
            }
        ):
            raise CompositionError(
                f"{owner}.{name} may not be a generator operator method",
                code="generator-dunder-not-supported",
            )
        return kind

    @classmethod
    def classify(
        cls,
        name: str,
        value: object,
        /,
        *,
        owner: str,
        behaviour_definition: bool,
    ) -> LocalMember | None:
        if name in INTERPRETER_CLASS_NAMES:
            return None
        if name == RESERVED_METADATA_NAME:
            raise CompositionError(
                f"{owner} may not define reserved member {RESERVED_METADATA_NAME}",
                code="reserved-composition-metadata",
            )
        if name == "__hash__" and value is None:
            return LocalMember(
                value=value,
                kind=MemberKind.HASH_DISABLED,
                abstract=False,
                explicit=True,
            )
        if name == "__hash__" and value is object.__hash__:
            return LocalMember(
                value=value,
                kind=MemberKind.METHOD,
                abstract=False,
                explicit=True,
            )
        if type(value) is types.FunctionType:
            kind = (
                cls.classify_function(name, value, owner=owner)
                if behaviour_definition
                else MemberKind.of_function(value)
            )
            return LocalMember(
                value=value,
                kind=kind,
                abstract=is_abstract(value),
                explicit=True,
            )
        if type(value) is classmethod or type(value) is staticmethod:
            kind = MemberKind.of_descriptor(value)
            if behaviour_definition:
                if name in _FORBIDDEN_BEHAVIOUR_NAMES or _is_dunder(name):
                    raise CompositionError(
                        f"{owner}.{name} must use the native instance-operator convention",
                        code="unsupported-dunder-binding",
                    )
                validate_no_super(value, owner=owner, name=name)
                if type(value) is classmethod:
                    cls.require_receiver(value.__func__, owner=owner, name=name)
            return LocalMember(
                value=value, kind=kind, abstract=is_abstract(value), explicit=True
            )
        if type(value) is property:
            admitted = (
                type(value.fget) is types.FunctionType
                and not inspect.iscoroutinefunction(value.fget)
                and not inspect.isasyncgenfunction(value.fget)
                and value.fset is None
                and value.fdel is None
                and not _is_dunder(name)
            )
            if not admitted:
                if behaviour_definition:
                    raise CompositionError(
                        f"{owner}.{name} must be a readable, read-only non-operator property",
                        code="unsupported-property",
                    )
                return None
            if behaviour_definition:
                validate_no_super(value, owner=owner, name=name)
                getter = value.fget
                assert type(getter) is types.FunctionType
                cls.require_receiver(getter, owner=owner, name=name)
            return LocalMember(
                value=value,
                kind=MemberKind.READ_ONLY_PROPERTY,
                abstract=is_abstract(value),
                explicit=True,
            )
        if behaviour_definition:
            raise CompositionError(
                f"{owner}.{name} is state or an unsupported descriptor; behaviour definitions may contain only supported methods and read-only properties",
                code="state-or-unsupported-member",
            )
        return None

    @staticmethod
    def generated_field_names(name: str, value: object) -> frozenset[str]:
        match name, value:
            case "__dataclass_fields__", fields if isinstance(fields, Mapping):
                return frozenset(key for key in fields if isinstance(key, str))
            case "__attrs_attrs__", fields if isinstance(fields, tuple):
                return frozenset(
                    field_name
                    for field in fields
                    if isinstance(field_name := getattr(field, "name", None), str)
                )
            case _:
                return frozenset()

    @classmethod
    def reject_generated_fields(
        cls,
        namespace: Mapping[str, object],
        protected: frozenset[str],
        class_name: str,
    ) -> None:
        for marker in ("__dataclass_fields__", "__attrs_attrs__"):
            overlap = protected & cls.generated_field_names(
                marker, namespace.get(marker)
            )
            if overlap:
                raise CompositionError(
                    f"{class_name} generates data fields over behavior members: {sorted(overlap)}",
                    code="generated-field-shadows-member",
                    member=min(overlap),
                    hint="Keep a separate backing field and an explicit accessor; fields do not replace behavior methods.",
                )

    @classmethod
    def reject_shadowing(
        cls,
        namespace: Mapping[str, object],
        inherited_names: frozenset[str],
        local_members: Mapping[str, LocalMember],
        /,
        *,
        class_name: str,
        owner: type | None = None,
    ) -> None:
        cls.reject_generated_fields(namespace, inherited_names, class_name)
        for name in inherited_names & frozenset(
            class_annotations(owner if owner is not None else namespace)
        ):
            if name not in namespace:
                raise CompositionError(
                    f"{class_name}.{name} annotates over an inherited composition member without implementing it",
                    code="annotation-shadows-member",
                    member=name,
                )

        slots = namespace.get("__slots__", ())
        if type(slots) is str:
            declared_slots = (slots,)
        elif (type(slots) is tuple or type(slots) is list) and all(
            type(item) is str for item in slots
        ):
            declared_slots = tuple(slots)
        else:
            raise CompositionError(
                f"{class_name} must use a string or string tuple/list for __slots__",
                code="unsupported-slot-declaration",
            )
        owner_name = class_name.lstrip("_")
        slot_names = frozenset(
            f"_{owner_name}{item}"
            if owner_name and item.startswith("__") and not item.endswith("__")
            else item
            for item in declared_slots
        )
        overlap = inherited_names & slot_names
        if overlap:
            name = min(overlap)
            raise CompositionError(
                f"{class_name}.{name} declares a slot over an inherited composition member",
                code="slot-shadows-member",
                member=name,
            )

        for name in inherited_names:
            if name in namespace and name not in local_members:
                raise CompositionError(
                    f"{class_name}.{name} replaces an inherited composition member with an unsupported value",
                    code="unsupported-local-resolution",
                    member=name,
                )

    @staticmethod
    def reject_implicit_hash(
        class_name: str,
        name: str,
        local: LocalMember,
        active: tuple[MemberOrigin, ...],
    ) -> None:
        if name != "__hash__" or local.explicit or not active:
            return
        if local.kind is MemberKind.HASH_DISABLED and all(
            origin.kind is MemberKind.HASH_DISABLED for origin in active
        ):
            return
        raise CompositionError(
            f"{class_name} implicitly disables an inherited concrete __hash__; declare __hash__ = None or an explicit hash implementation",
            code="implicit-hash-resolution",
        )

    @classmethod
    def collect(
        cls,
        namespace: Mapping[str, object],
        /,
        *,
        class_name: str,
        behaviour_definition: bool,
    ) -> dict[str, LocalMember]:
        if RESERVED_METADATA_NAME in namespace or ADMISSION_ATTRIBUTE in namespace:
            raise CompositionError(
                f"{class_name} may not define reserved member {RESERVED_METADATA_NAME}",
                code="reserved-composition-metadata",
            )

        if behaviour_definition:
            slots = namespace.get("__slots__", MISSING)
            if type(slots) is not tuple or slots != ():
                raise CompositionError(
                    f"{class_name} may not introduce instance slots; omit __slots__ or use ()",
                    code="nonempty-behaviour-layout",
                )
            annotations = class_annotations(namespace)
            raw_annotations = namespace.get("__annotations__", MISSING)
            if annotations or (
                raw_annotations is not MISSING and type(raw_annotations) is not dict
            ):
                raise CompositionError(
                    f"{class_name} may not declare data annotations",
                    code="behaviour-data-annotation",
                )

        local: dict[str, LocalMember] = {}
        for name, value in namespace.items():
            member = cls.classify(
                name,
                value,
                owner=class_name,
                behaviour_definition=behaviour_definition,
            )
            if member is not None:
                local[name] = member

        if "__eq__" in local and "__hash__" not in local:
            local["__hash__"] = LocalMember(
                value=None,
                kind=MemberKind.HASH_DISABLED,
                abstract=False,
                explicit=False,
            )
        return local


__all__ = [
    "LocalMember",
    "MemberKind",
    "is_abstract",
    "iter_wrapped_functions",
    "validate_no_super",
]
