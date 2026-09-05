"""Origin algebra for inherited and local composition members."""

from __future__ import annotations

import types
from collections.abc import Iterable
from dataclasses import dataclass

from behaviours.composition import (
    CompositionError,
    class_annotations,
    class_mro,
    class_namespace,
    mro_dict_item,
    nominal_subclass,
)
from behaviours.members import LocalMember, MemberKind, is_abstract

# Replaced with the newly created class before a public spec is installed.
_CURRENT_CLASS_PLACEHOLDER = type("_CurrentClassPlaceholder", (), {})


@dataclass(frozen=True, slots=True)
class SourceLocation:
    """Location recorded by a Python function's code object.

    Parameters
    ----------
    path : str
        Code filename, which may be a synthetic name rather than an existing file.
    line : int
        One-based first source line recorded for that function.
    """

    path: str
    line: int


def source_location(value: object) -> SourceLocation | None:
    if type(value) is classmethod or type(value) is staticmethod:
        value = value.__func__
    elif type(value) is property:
        value = value.fget
    if type(value) is types.FunctionType:
        return SourceLocation(value.__code__.co_filename, value.__code__.co_firstlineno)
    return None


@dataclass(frozen=True, slots=True)
class MemberOrigin:
    """One source-level obligation or provider contributing to a member."""

    owner: type
    name: str
    kind: MemberKind
    abstract: bool
    source_owner: type | None = None

    @property
    def location(self) -> SourceLocation | None:
        """Return the defining function's location, without reading source files."""
        found = mro_dict_item(self.source_owner or self.owner, self.name)
        return None if found is None else source_location(found[1])

    def sort_key(self) -> tuple[str, str, str, str]:
        source = self.source_owner
        return (
            self.owner.__module__,
            self.owner.__qualname__,
            "" if source is None else f"{source.__module__}.{source.__qualname__}",
            self.kind.value,
        )

    @classmethod
    def unique(cls, origins: Iterable[MemberOrigin]) -> tuple[MemberOrigin, ...]:
        collected: dict[
            tuple[type, str, MemberKind, bool, type | None], MemberOrigin
        ] = {}
        for origin in origins:
            key = (
                origin.owner,
                origin.name,
                origin.kind,
                origin.abstract,
                origin.source_owner,
            )
            collected[key] = origin
        return tuple(sorted(collected.values(), key=MemberOrigin.sort_key))

    @staticmethod
    def maximal(origins: tuple[MemberOrigin, ...]) -> tuple[MemberOrigin, ...]:
        return tuple(
            origin
            for origin in origins
            if not any(
                other.owner is not origin.owner
                and nominal_subclass(other.owner, origin.owner)
                for other in origins
            )
        )

    @staticmethod
    def inherited_from(bases: tuple[type, ...]) -> dict[str, list[MemberOrigin]]:
        from behaviours.admission import Admission

        collected: dict[str, list[MemberOrigin]] = {}
        for base in bases:
            admission = Admission.of(base)
            if admission is None:
                raise CompositionError(
                    f"base {base.__qualname__} lacks package-owned admission state",
                    code="unadmitted-behaviour-base",
                )
            for name, resolution in admission.spec.members.items():
                collected.setdefault(name, []).extend(resolution.origins)
        return collected

    @classmethod
    def from_ordinary_base(cls, base: type, name: str) -> MemberOrigin | None:
        for owner in class_mro(base):
            LocalMember.reject_generated_fields(
                class_namespace(owner), frozenset({name}), base.__qualname__
            )
        found = mro_dict_item(base, name)
        if found is None:
            for owner in class_mro(base):
                if name in class_annotations(owner):
                    raise CompositionError(
                        f"ordinary base {base.__qualname__}.{name} declares data over a mixin member",
                        code="base-data-conflict",
                    )
            return None
        source_owner, value = found
        if source_owner is object:
            return None
        kind = MemberKind.of_runtime(name, value)
        return cls(
            owner=base,
            name=name,
            kind=kind,
            abstract=is_abstract(value),
            source_owner=source_owner,
        )


@dataclass(frozen=True, slots=True)
class MemberResolution:
    """The admitted resolution of one composition-relevant member."""

    name: str
    kind: MemberKind
    abstract: bool
    provider: type | None
    origins: tuple[MemberOrigin, ...]
    is_local: bool

    @classmethod
    def resolve(
        cls,
        class_name: str,
        name: str,
        inherited: tuple[MemberOrigin, ...],
        local: LocalMember | None,
    ) -> MemberResolution:
        inherited = MemberOrigin.unique(inherited)
        active = MemberOrigin.maximal(inherited)
        active_kinds = frozenset(origin.kind for origin in active)

        if local is not None:
            if not MemberKind.compatible_local(name, local.kind, active_kinds):
                kinds = ", ".join(sorted(kind.value for kind in active_kinds))
                raise CompositionError(
                    f"{class_name}.{name} has incompatible kind {local.kind.value}; inherited obligations require: {kinds}",
                    code="incompatible-member-kind",
                    member=name,
                    origins=tuple(active),
                    hint="Use one compatible access convention; selecting a body cannot change the inherited contracts.",
                )
            LocalMember.reject_implicit_hash(class_name, name, local, active)
            local_origin = MemberOrigin(
                owner=_CURRENT_CLASS_PLACEHOLDER,
                name=name,
                kind=local.kind,
                abstract=local.abstract,
            )
            origins = (*inherited, local_origin)
            return MemberResolution(
                name=name,
                kind=local.kind,
                abstract=local.abstract,
                provider=None,
                origins=tuple(origins),
                is_local=True,
            )

        if not active:
            raise AssertionError(
                f"member {name!r} has neither inherited nor local input"
            )

        if name == "__hash__" and all(
            origin.kind is MemberKind.HASH_DISABLED for origin in active
        ):
            return MemberResolution(
                name=name,
                kind=MemberKind.HASH_DISABLED,
                abstract=False,
                provider=None,
                origins=tuple(inherited),
                is_local=False,
            )

        if len(active) == 1:
            chosen = active[0]
            return MemberResolution(
                name=name,
                kind=chosen.kind,
                abstract=chosen.abstract,
                provider=chosen.owner,
                origins=tuple(inherited),
                is_local=False,
            )

        if all(origin.abstract for origin in active):
            if len(active_kinds) != 1:
                kinds = ", ".join(sorted(kind.value for kind in active_kinds))
                raise CompositionError(
                    f"{class_name}.{name} has incompatible abstract obligations: {kinds}",
                    code="incompatible-abstract-obligations",
                    member=name,
                    origins=tuple(active),
                )
            kind = next(iter(active_kinds))
            return MemberResolution(
                name=name,
                kind=kind,
                abstract=True,
                provider=None,
                origins=tuple(inherited),
                is_local=False,
            )

        providers = ", ".join(
            f"{origin.owner.__module__}.{origin.owner.__qualname__}.{name}"
            for origin in active
        )
        raise CompositionError(
            f"{class_name}.{name} has unresolved independent providers: {providers}; define it locally",
            code="unresolved-member-conflict",
            member=name,
            origins=tuple(active),
            hint="Define a compatible local member. Base order never chooses an independent provider.",
        )

    def with_class(self, owner: type) -> MemberResolution:
        if not self.is_local:
            return self
        origins = tuple(
            MemberOrigin(
                owner=owner
                if origin.owner is _CURRENT_CLASS_PLACEHOLDER
                else origin.owner,
                name=origin.name,
                kind=origin.kind,
                abstract=origin.abstract,
                source_owner=origin.source_owner,
            )
            for origin in self.origins
        )
        return MemberResolution(
            name=self.name,
            kind=self.kind,
            abstract=self.abstract,
            provider=owner,
            origins=origins,
            is_local=True,
        )


__all__ = [
    "MemberOrigin",
    "MemberResolution",
    "SourceLocation",
    "source_location",
]
