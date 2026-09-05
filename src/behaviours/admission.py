"""Admission lifecycle for class creation, rebuild, and mutation."""

from __future__ import annotations

import sys
import types
import typing
from abc import ABCMeta
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import final

from behaviours.composition import (
    ADMISSION_ATTRIBUTE,
    BOOTSTRAP_TOKEN,
    INTERPRETER_CLASS_NAMES,
    MISSING,
    RESERVED_METADATA_NAME,
    CompositionError,
    class_annotations,
    class_mro,
    class_namespace,
    mro_dict_item,
    nominal_subclass,
)
from behaviours.members import (
    LocalMember,
    MemberKind,
    is_abstract,
    iter_wrapped_functions,
    validate_no_super,
)
from behaviours.origin import MemberOrigin, MemberResolution
from behaviours.topology import ClassRole

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override

GENERIC_ALIAS_TYPE = type(typing.IO[str])


@dataclass(frozen=True, slots=True)
class CompositionSpec:
    """Immutable diagnostic projection of a class admission decision."""

    role: ClassRole
    members: Mapping[str, MemberResolution]


@dataclass(frozen=True, slots=True)
class Admission:
    owner: type
    role: ClassRole
    spec: CompositionSpec
    bindings: Mapping[str, object]
    final_bindings: Mapping[str, object]
    frozen: bool
    root: bool

    @classmethod
    def of(cls, owner: type) -> Admission | None:
        if type(owner) is not BehaviourMeta:
            return None
        state = class_namespace(owner).get(ADMISSION_ATTRIBUTE)
        if type(state) is cls and state.owner is owner:
            return state
        return None

    @classmethod
    def spec_for(cls, owner: type, /) -> CompositionSpec | None:
        """Return the immutable diagnostic snapshot made at class admission.

        Parameters
        ----------
        owner : type
            Class whose own admission is queried; metadata is never inherited.

        Returns
        -------
        CompositionSpec or None
            Snapshot for a behavior definition or composition join. Return ``None``
            for unrelated classes and ordinary descendants. Ordinary classes may
            configure unrelated fields/metadata after admission. The snapshot is not
            a purity proof or a live monitor of external-base changes.
        """

        match cls.of(owner):
            case None | Admission(role=ClassRole.ORDINARY):
                return None
            case Admission() as admission:
                return admission.spec

    @staticmethod
    def bindings_for(owner: type, members: Iterable[str]) -> dict[str, object]:
        bindings: dict[str, object] = {}
        for name in members:
            found = mro_dict_item(owner, name)
            assert found is not None, "postflight validated member presence"
            bindings[name] = found[1]
        return bindings

    @staticmethod
    def prepare_rebuild(
        name: str, bases: tuple[type, ...], namespace: dict[str, object]
    ) -> None:
        """Re-admit an ordinary class copied by a slots-generating decorator."""
        copied = namespace.get(ADMISSION_ATTRIBUTE)
        if type(copied) is not Admission or copied.frozen:
            return
        source = copied.owner
        if (
            Admission.of(source) is not copied
            or type.__getattribute__(source, "__bases__") != bases
            or source.__name__ != name
            or source.__module__ != namespace.get("__module__")
        ):
            raise CompositionError(
                "copied admission must belong to the ordinary class being rebuilt",
                code="invalid-class-rebuild",
            )
        for member_name, original in {
            **copied.bindings,
            **copied.final_bindings,
        }.items():
            found = mro_dict_item(source, member_name)
            if found is None or found[1] is not original:
                raise CompositionError(
                    f"{name}.{member_name} changed before class rebuilding",
                    code="protected-composition-member",
                )
            if member_name in namespace and namespace[member_name] is not original:
                raise CompositionError(
                    f"{name}.{member_name} is implicitly replaced by a class transform",
                    code="protected-composition-member",
                )
            # Removing an explicitly selected implementation must not re-enable an
            # inherited provider merely because the rebuilt namespace omitted it.
            if member_name in class_namespace(source) and member_name not in namespace:
                raise CompositionError(
                    f"{name}.{member_name} is removed by a class transform",
                    code="protected-composition-member",
                )
        for derived in (ADMISSION_ATTRIBUTE, "__abstractmethods__", "_abc_impl"):
            namespace.pop(derived, None)
        for member_name, value in tuple(namespace.items()):
            if (
                isinstance(
                    value, (types.GetSetDescriptorType, types.MemberDescriptorType)
                )
                and value.__objclass__ is source
            ):
                del namespace[member_name]

    @staticmethod
    def reject_write(owner: type, name: str, value: object) -> None:
        admission = Admission.of(owner)
        if name == "__final__":
            if value is True:
                return
            raise CompositionError(
                "a final class marker cannot be cleared",
                code="final-marker-mutation",
            )
        if name in {ADMISSION_ATTRIBUTE, RESERVED_METADATA_NAME, "__bases__"}:
            raise CompositionError(
                f"{owner.__qualname__} has frozen composition topology/metadata",
                code="frozen-composition-surface",
            )
        if admission is None:
            return
        if admission.frozen:
            raise CompositionError(
                f"{owner.__qualname__} is a frozen behavior definition",
                code="frozen-composition-surface",
            )
        if name in admission.final_bindings:
            if value is admission.final_bindings[name]:
                return
            raise CompositionError(
                f"{owner.__qualname__}.{name} is final",
                code="final-member-override",
            )
        if name in admission.bindings:
            if value is admission.bindings[name]:
                return
            raise CompositionError(
                f"{owner.__qualname__}.{name} belongs to behavior composition; "
                "use a compatible source override or disable the decorator's generated method",
                code="protected-composition-member",
            )
        LocalMember.reject_generated_fields(
            {name: value},
            frozenset(admission.bindings) | frozenset(admission.final_bindings),
            owner.__qualname__,
        )
        observed: Mapping[str, object] | None = None
        if name == "__annotations__" and isinstance(value, Mapping):
            observed = value
        elif name in {"__annotate_func__", "__annotate__"}:
            observed = class_annotations({"__annotate_func__": value})
        if observed is not None:
            overlap = set(observed) & (
                set(admission.bindings) | set(admission.final_bindings)
            )
            if overlap:
                raise CompositionError(
                    f"{owner.__qualname__} adds data annotations over {sorted(overlap)}",
                    code="annotation-shadows-member",
                )


@dataclass(frozen=True, slots=True)
class _Pending:
    role: ClassRole
    members: Mapping[str, MemberResolution]
    expected_runtime_owners: Mapping[str, type | None]
    expected_values: Mapping[str, object]
    final_bindings: Mapping[str, object]
    frozen: bool
    root: bool

    @staticmethod
    def is_final_member(value: object) -> bool:
        if type(value) is types.FunctionType:
            return value.__dict__.get("__final__") is True
        if type(value) is classmethod or type(value) is staticmethod:
            return value.__dict__.get("__final__") is True or _Pending.is_final_member(
                value.__func__
            )
        if type(value) is property:
            return _Pending.is_final_member(value.fget)
        return False

    @classmethod
    def final_constraints(
        cls,
        bases: tuple[type, ...],
        namespace: Mapping[str, object],
        class_name: str,
    ) -> dict[str, object]:
        constraints: dict[str, object] = {}
        for base in bases:
            if class_namespace(base).get("__final__") is True:
                raise CompositionError(
                    f"{class_name} cannot subclass final class {base.__qualname__}",
                    code="final-class-subclass",
                )
            for ancestor in class_mro(base):
                for name, value in class_namespace(ancestor).items():
                    if cls.is_final_member(value):
                        previous = constraints.get(name, MISSING)
                        if previous is not MISSING and previous is not value:
                            raise CompositionError(
                                f"{class_name}.{name} has incompatible final providers",
                                code="final-member-conflict",
                            )
                        constraints[name] = value
        for name in constraints:
            if name in namespace:
                raise CompositionError(
                    f"{class_name}.{name} overrides a final member",
                    code="final-member-override",
                )
        # An annotation or generated field is also an override, even if it leaves
        # no function in the class dictionary.
        LocalMember.reject_shadowing(
            namespace, frozenset(constraints), {}, class_name=class_name
        )
        for name, value in namespace.items():
            if cls.is_final_member(value):
                if is_abstract(value):
                    raise CompositionError(
                        f"{class_name}.{name} cannot be both final and abstract",
                        code="final-abstract-member",
                    )
                constraints[name] = value
        return constraints

    @staticmethod
    def reject_custom_set_name(
        namespace: Mapping[str, object],
        /,
        *,
        class_name: str,
    ) -> None:
        for name, value in namespace.items():
            if type(value) is types.CellType:
                continue
            if type(value) is property:
                continue
            if mro_dict_item(type(value), "__set_name__") is not None:
                raise CompositionError(
                    f"{class_name}.{name} uses a custom __set_name__ descriptor on a composition join",
                    code="set-name-transform-not-supported",
                )

    @staticmethod
    def native_wrapper_matches(name: str, original: object, value: object) -> bool:
        """Recognize type.__new__'s automatic wrapping of lifecycle functions."""
        match name:
            case "__new__" if type(value) is staticmethod:
                return value.__func__ is original
            case "__init_subclass__" | "__class_getitem__" if (
                type(value) is classmethod
            ):
                return value.__func__ is original
            case _:
                return False

    @classmethod
    def resolve_surface(
        cls,
        role: ClassRole,
        behaviour_bases: tuple[type, ...],
        ordinary_base: type | None,
        namespace: Mapping[str, object],
        /,
        *,
        class_name: str,
    ) -> tuple[dict[str, MemberResolution], dict[str, type | None]]:
        behaviour_definition = role in {ClassRole.TRAIT, ClassRole.STRICT_MIXIN}
        local = LocalMember.collect(
            namespace,
            class_name=class_name,
            behaviour_definition=behaviour_definition,
        )
        inherited = MemberOrigin.inherited_from(behaviour_bases)

        match role, ordinary_base:
            case ClassRole.ORDINARY, None:
                raise AssertionError("ordinary class lacks ordinary base")
            case ClassRole.ORDINARY, parent_base if parent_base is not None:
                parent = Admission.of(parent_base)
                assert parent is not None
                # A single ordinary spine has already selected its providers. Preserve its
                # effective obligations without reopening previously resolved conflicts.
                for name in parent.spec.members:
                    origin = MemberOrigin.from_ordinary_base(parent_base, name)
                    if origin is not None:
                        inherited[name] = [origin]
            case ClassRole.MIXIN_APPLICATION, None:
                raise AssertionError("mixin application lacks ordinary base")
            case ClassRole.MIXIN_APPLICATION, parent_base if parent_base is not None:
                parent = Admission.of(parent_base)
                names = set(inherited)
                if parent is not None:
                    names.update(parent.spec.members)
                for name in sorted(names):
                    origin = MemberOrigin.from_ordinary_base(parent_base, name)
                    if origin is not None:
                        inherited.setdefault(name, []).append(origin)
            case _:
                pass

        inherited_names = frozenset(inherited)
        match role:
            case ClassRole.STRICT_MIXIN:
                abstract_names = sorted(
                    name for name, member in local.items() if member.abstract
                )
                if abstract_names:
                    raise CompositionError(
                        f"{class_name}.{abstract_names[0]} is abstract; StrictMixin requirements belong in explicit-self Protocols",
                        code="abstract-strict-mixin-member",
                    )
            case ClassRole.TRAIT:
                pass
            case _:
                LocalMember.reject_shadowing(
                    namespace,
                    inherited_names,
                    local,
                    class_name=class_name,
                )

        for name in inherited_names & frozenset(local):
            member = local[name]
            if type(member.value) in (
                types.FunctionType,
                property,
                classmethod,
                staticmethod,
            ):
                if role is not ClassRole.ORDINARY:
                    validate_no_super(member.value, owner=class_name, name=name)
                if type(member.value) is not staticmethod:
                    LocalMember.require_receiver(
                        next(iter_wrapped_functions(member.value)),
                        owner=class_name,
                        name=name,
                    )

        names = set(inherited_names)
        match role:
            case ClassRole.TRAIT | ClassRole.STRICT_MIXIN:
                names.update(local)
            case ClassRole.MIXIN_APPLICATION:
                for name, member in local.items():
                    if member.abstract and name in inherited_names:
                        raise CompositionError(
                            f"{class_name}.{name} may not defer a StrictMixin conflict with an abstract local member",
                            code="abstract-mixin-resolution-not-supported",
                        )
                names.update(name for name in local if name in inherited_names)
            case _:
                names.update(name for name in local if name in inherited_names)

        resolutions: dict[str, MemberResolution] = {}
        expected: dict[str, type | None] = {}
        for name in sorted(names):
            inherited_origins = tuple(inherited.get(name, ()))
            local_member = local.get(name)
            if local_member is None and not inherited_origins:
                continue
            resolution = MemberResolution.resolve(
                class_name,
                name,
                inherited_origins,
                local_member,
            )
            resolutions[name] = resolution
            if resolution.is_local or resolution.provider is None:
                expected[name] = None
            else:
                chosen = next(
                    (
                        origin
                        for origin in MemberOrigin.maximal(
                            MemberOrigin.unique(inherited_origins)
                        )
                        if origin.owner is resolution.provider
                    ),
                    None,
                )
                expected[name] = (
                    resolution.provider
                    if chosen is None or chosen.source_owner is None
                    else chosen.source_owner
                )

        return resolutions, expected

    @classmethod
    def prepare(
        cls,
        bases: tuple[type, ...],
        namespace: dict[str, object],
        /,
        *,
        class_name: str,
        definition: ClassRole | None,
    ) -> _Pending:
        if RESERVED_METADATA_NAME in namespace or ADMISSION_ATTRIBUTE in namespace:
            raise CompositionError(
                f"{class_name} may not declare package admission metadata",
                code="reserved-composition-metadata",
            )
        role, behaviour_bases, ordinary_base = ClassRole.classify(
            bases,
            class_name=class_name,
            definition=definition,
        )
        final_bindings = cls.final_constraints(bases, namespace, class_name)
        match role:
            case ClassRole.TRAIT | ClassRole.STRICT_MIXIN:
                namespace.setdefault("__slots__", ())
                cls.reject_custom_set_name(namespace, class_name=class_name)
                frozen = True
            case _:
                frozen = False
        members, expected = cls.resolve_surface(
            role,
            behaviour_bases,
            ordinary_base,
            namespace,
            class_name=class_name,
        )
        values: dict[str, object] = {}
        for member_name, resolution in members.items():
            if resolution.is_local:
                values[member_name] = namespace.get(member_name)
            elif expected[member_name] is not None:
                owner = expected[member_name]
                assert owner is not None
                values[member_name] = class_namespace(owner)[member_name]
            else:
                for base in bases:
                    found = mro_dict_item(base, member_name)
                    if found is not None:
                        values[member_name] = found[1]
                        break
        return _Pending(
            role=role,
            members=MappingProxyType(members),
            expected_runtime_owners=MappingProxyType(expected),
            expected_values=MappingProxyType(values),
            final_bindings=MappingProxyType(final_bindings),
            frozen=frozen,
            root=False,
        )

    def verify(
        self,
        owner: type,
        namespace: Mapping[str, object],
    ) -> dict[str, MemberResolution]:
        if (
            self.role in {ClassRole.TRAIT, ClassRole.STRICT_MIXIN}
            and type.__getattribute__(owner, "__dictoffset__") != 0
        ):
            raise CompositionError(
                f"{owner.__qualname__} introduces an instance dictionary",
                code="behaviour-layout-drift",
            )

        for final_name, original in self.final_bindings.items():
            found = mro_dict_item(owner, final_name)
            if found is None or not (
                found[1] is original
                or (
                    found[0] is owner
                    and namespace.get(final_name) is original
                    and _Pending.native_wrapper_matches(final_name, original, found[1])
                )
            ):
                raise CompositionError(
                    f"{owner.__qualname__}.{final_name} replaces a final member during construction",
                    code="final-member-override",
                )
        LocalMember.reject_generated_fields(
            class_namespace(owner), frozenset(self.final_bindings), owner.__qualname__
        )
        finalized: dict[str, MemberResolution] = {}
        for name, provisional in self.members.items():
            resolution = provisional.with_class(owner)
            finalized[name] = resolution
            found = mro_dict_item(owner, name)
            if found is None:
                raise CompositionError(
                    f"{owner.__qualname__}.{name} disappeared during class creation",
                    code="runtime-surface-drift",
                )
            runtime_owner, runtime_value = found
            if runtime_value is not self.expected_values[name]:
                raise CompositionError(
                    f"{owner.__qualname__}.{name} was replaced during class construction",
                    code="runtime-surface-drift",
                )
            runtime_kind = MemberKind.of_runtime(name, runtime_value)
            if runtime_kind is not resolution.kind:
                raise CompositionError(
                    f"{owner.__qualname__}.{name} changed kind from {resolution.kind.value} to {runtime_kind.value} during class creation",
                    code="runtime-member-kind-drift",
                )
            expected_owner = self.expected_runtime_owners[name]
            if resolution.is_local:
                expected_owner = owner
            if expected_owner is not None and runtime_owner is not expected_owner:
                raise CompositionError(
                    f"{owner.__qualname__}.{name} resolved to {runtime_owner.__qualname__}, expected {expected_owner.__qualname__}",
                    code="runtime-provider-drift",
                )
            runtime_abstract = name in getattr(
                owner, "__abstractmethods__", frozenset()
            )
            if runtime_abstract is not resolution.abstract:
                raise CompositionError(
                    f"{owner.__qualname__}.{name} abstractness changed during class creation",
                    code="runtime-abstractness-drift",
                )

        match self.role:
            case ClassRole.TRAIT | ClassRole.STRICT_MIXIN:
                for name, original in namespace.items():
                    if name in INTERPRETER_CLASS_NAMES:
                        continue
                    if name not in class_namespace(owner):
                        raise CompositionError(
                            f"{owner.__qualname__}.{name} was removed during class creation",
                            code="class-body-transform-not-supported",
                        )
                    runtime_value = class_namespace(owner)[name]
                    if _Pending.native_wrapper_matches(name, original, runtime_value):
                        continue
                    if runtime_value is not original:
                        raise CompositionError(
                            f"{owner.__qualname__}.{name} was replaced during class creation",
                            code="class-body-transform-not-supported",
                        )
                return finalized
            case _:
                current = class_namespace(owner)
                LocalMember.reject_shadowing(
                    current,
                    frozenset(self.members),
                    LocalMember.collect(
                        current,
                        class_name=owner.__qualname__,
                        behaviour_definition=False,
                    ),
                    class_name=owner.__qualname__,
                    owner=owner,
                )
                return finalized


def _validate_class_input(
    bases: tuple[type, ...], namespace: Mapping[str, object], class_name: str
) -> None:
    if any(not isinstance(base, type) for base in bases):
        raise TypeError("composition bases must be resolved Python classes")
    for name in (
        "__abstractmethods__",
        "_abc_impl",
        "__mro__",
        "__bases__",
        "__dict__",
        "__weakref__",
        "__dictoffset__",
        "__weakrefoffset__",
        "__basicsize__",
        "__itemsize__",
    ):
        if name in namespace:
            raise CompositionError(
                f"{class_name} may not declare interpreter-owned {name}",
                code="interpreter-metadata-not-supported",
            )
    original = namespace.get("__orig_bases__")
    if original is not None:
        if type(original) is not tuple:
            raise CompositionError(
                "__orig_bases__ must be a tuple", code="dynamic-bases-not-supported"
            )
        for base in original:
            if isinstance(base, type):
                continue
            if type(base) not in (GENERIC_ALIAS_TYPE, types.GenericAlias):
                raise CompositionError(
                    "custom __mro_entries__ are unsupported",
                    code="dynamic-bases-not-supported",
                )


@final
class BehaviourMeta(ABCMeta):
    """Authoritative class-creation boundary for the supported subset."""

    def __init_subclass__(cls, **kwargs: object) -> None:
        del kwargs
        raise TypeError("the behaviours metaclass may not be subclassed")

    def __new__(
        metaclass,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, object],
        *,
        _definition: ClassRole | None = None,
        _bootstrap: object | None = None,
        _root_role: ClassRole | None = None,
        **kwargs: object,
    ) -> BehaviourMeta:
        if metaclass is not BehaviourMeta:
            raise TypeError("the behaviours metaclass is closed")
        if (
            type(name) is not str
            or type(bases) is not tuple
            or type(namespace) is not dict
        ):
            raise TypeError(
                "class creation expects a string, tuple of bases, and plain dict"
            )
        if any(type(key) is not str for key in namespace):
            raise TypeError("class namespace keys must be strings")
        if "trait" in kwargs:
            raise CompositionError(
                f"{name} uses the removed trait class keyword; use @trait instead",
                code="unsupported-class-keyword",
            )
        if _definition not in (None, ClassRole.TRAIT, ClassRole.STRICT_MIXIN):
            raise TypeError("internal definition role must be trait or strict-mixin")

        match _bootstrap is BOOTSTRAP_TOKEN, _root_role:
            case True, ClassRole.TRAIT | ClassRole.STRICT_MIXIN as role:
                cls = super().__new__(metaclass, name, bases, namespace)
                spec = CompositionSpec(
                    role=role,
                    members=MappingProxyType({}),
                )
                admission = Admission(
                    owner=cls,
                    role=role,
                    spec=spec,
                    bindings=MappingProxyType({}),
                    final_bindings=MappingProxyType({}),
                    frozen=True,
                    root=True,
                )
                type.__setattr__(cls, ADMISSION_ATTRIBUTE, admission)
                return cls
            case True, _:
                raise AssertionError("invalid root bootstrap role")
            case False, None if _bootstrap is None:
                pass
            case _:
                raise CompositionError(
                    f"{name} attempted to use reserved bootstrap keywords",
                    code="reserved-bootstrap-keyword",
                )

        namespace = dict(namespace)
        Admission.prepare_rebuild(name, bases, namespace)
        _validate_class_input(bases, namespace, name)
        pending = _Pending.prepare(
            bases,
            namespace,
            class_name=name,
            definition=_definition,
        )
        cls = super().__new__(metaclass, name, bases, namespace, **kwargs)
        try:
            finalized_members = pending.verify(cls, namespace)
        except CompositionError as error:
            error.phase = "construction"
            # A registering hook may have retained the rejected object. Prevent
            # accidental instantiation; external registration effects are not undone.
            type.__setattr__(
                cls, "__abstractmethods__", frozenset({"<invalid composition>"})
            )
            raise
        spec = CompositionSpec(
            role=pending.role,
            members=MappingProxyType(finalized_members),
        )
        admission = Admission(
            owner=cls,
            role=pending.role,
            spec=spec,
            bindings=MappingProxyType(Admission.bindings_for(cls, finalized_members)),
            final_bindings=MappingProxyType(
                Admission.bindings_for(cls, pending.final_bindings)
            ),
            frozen=pending.frozen,
            root=pending.root,
        )
        type.__setattr__(cls, ADMISSION_ATTRIBUTE, admission)
        return cls

    @override
    def __instancecheck__(cls, instance: object) -> bool:
        return nominal_subclass(type(instance), cls)

    @override
    def __subclasscheck__(cls, subclass: type) -> bool:
        if not isinstance(subclass, type):
            raise TypeError("issubclass() arg 1 must be a class")
        return nominal_subclass(subclass, cls)

    def __setattr__(cls, name: str, value: object) -> None:
        try:
            Admission.reject_write(cls, name, value)
        except CompositionError as error:
            error.phase = "mutation"
            error.member = name
            raise
        super().__setattr__(name, value)

    def __delattr__(cls, name: str) -> None:
        try:
            Admission.reject_write(cls, name, MISSING)
        except CompositionError as error:
            error.phase = "mutation"
            error.member = name
            raise
        super().__delattr__(name)

    @override
    def register(cls, subclass: type) -> type:
        if Admission.of(cls) is not None:
            raise CompositionError(
                "virtual subclass registration is not supported by the nominal composition calculus",
                code="virtual-subclass-not-supported",
            )
        return super().register(subclass)


__all__ = [
    "Admission",
    "BehaviourMeta",
    "CompositionSpec",
]
