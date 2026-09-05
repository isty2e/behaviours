"""Read-only comparison of current bindings with admission observations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from behaviours.composition import (
    ADMISSION_ATTRIBUTE,
    Admission,
    ClassRole,
    CompositionError,
    LocalMember,
    MemberKind,
    MemberOrigin,
    SourceLocation,
    class_annotations,
    class_mro,
    class_namespace,
    mro_dict_item,
)
from behaviours.origin import source_location


@dataclass(frozen=True, slots=True)
class CompositionIssue:
    """One observed mismatch, not a new admission decision.

    Parameters
    ----------
    code : str
        Machine-readable reason for the observed mismatch.
    member : str or None
        Affected member, when the issue concerns a single identifiable binding.
    message : str
        Explanation of the observed failure, without changing the class.
    """

    code: str
    member: str | None
    message: str


@dataclass(frozen=True, slots=True)
class MemberObservation:
    """Expected contract and currently observed native member binding.

    Parameters
    ----------
    name : str
        Protected member name.
    expected_kind : MemberKind
        Binding and execution mode accepted at admission.
    actual_kind : MemberKind or None
        Currently observed kind, or None for a missing/unsupported value.
    actual_owner : type or None
        Current defining MRO class, or None when missing.
    location : SourceLocation or None
        Location of the expected Python implementation, when available.
    origins : tuple[MemberOrigin, ...]
        Recorded provider provenance. Ordinary final-only members have no trait origins.
    abstract : bool
        Whether the admitted contract deliberately left this member abstract.
    final : bool
        Whether the admitted standard final marker protects the member.
    unchanged : bool
        Whether the currently resolved object has the admitted identity. This flag
        alone does not establish kind, field or abstractness validity.
    """

    name: str
    expected_kind: MemberKind
    actual_kind: MemberKind | None
    actual_owner: type | None
    location: SourceLocation | None
    origins: tuple[MemberOrigin, ...]
    abstract: bool
    final: bool
    unchanged: bool


@dataclass(frozen=True, slots=True)
class CompositionReport:
    """Read-only observations made when inspection was requested.

    An unrelated class is explicitly unverified, not a valid empty composition.
    Holding this report does not watch for subsequent mutation.

    Parameters
    ----------
    subject : type
        Class that was inspected; retained while the report is held.
    role : ClassRole or None
        Admitted class role, or None for an unmanaged class.
    members : Mapping[str, MemberObservation]
        Read-only observations for behavior-bound and final members, not every
        arbitrary attribute on the class.
    issues : tuple[CompositionIssue, ...]
        Detected mismatches against the recorded admission baseline.
    """

    subject: type
    role: ClassRole | None
    members: Mapping[str, MemberObservation]
    issues: tuple[CompositionIssue, ...]

    @property
    def is_valid(self) -> bool:
        """Return whether a managed class has no observed composition damage."""
        return self.role is not None and not self.issues

    def raise_if_invalid(self) -> None:
        """Reject an unmanaged or damaged composition.

        Raises
        ------
        CompositionError
            If inspection had no managed baseline or found a binding/field mismatch.
        """
        if not self.is_valid:
            raise CompositionError(
                self.format(), code="composition-inspection-failed", phase="inspection"
            )

    def format(self) -> str:
        """Render the observed role, native providers and mismatches as plain text.

        Returns
        -------
        str
            Human-readable diagnostic text; structured fields are the machine interface.
        """
        heading = f"{self.subject.__module__}.{self.subject.__qualname__}"
        if self.role is None:
            return f"{heading}: not managed; no composition was checked"
        lines = [
            f"{heading}: {self.role.value} ({'valid' if self.is_valid else 'changed'})"
        ]
        for name, member in self.members.items():
            provider = (
                "<missing>"
                if member.actual_owner is None
                else member.actual_owner.__qualname__
            )
            flags = ", ".join(
                flag
                for flag, on in (("abstract", member.abstract), ("final", member.final))
                if on
            )
            lines.append(
                f"  {name}: {member.expected_kind.value} <- {provider}"
                + (f" [{flags}]" if flags else "")
            )
        lines.extend(f"  ! {issue.code}: {issue.message}" for issue in self.issues)
        return "\n".join(lines)


def inspect_composition(cls: type, /) -> CompositionReport:
    """Compare current native bindings with this class's admission observations.

    Parameters
    ----------
    cls : type
        Managed definition, adopter, application or ordinary descendant to inspect.

    Returns
    -------
    CompositionReport
        Immutable observations including final members and field-shadow diagnostics.
        Unrelated classes have ``role=None`` and ``is_valid=False``. Abstract members
        are reported but do not make a deliberately abstract declaration invalid.

    Raises
    ------
    TypeError
        If the argument is not a class.

    Notes
    -----
    No member is called, repaired or registered. Method bodies, arbitrary instance
    state, external registries and function-code mutations are outside this check.
    """
    if not isinstance(cls, type):
        raise TypeError("inspect_composition expects a class")
    state = Admission.of(cls)
    if state is None:
        return CompositionReport(cls, None, MappingProxyType({}), ())
    expected = {**state.bindings, **state.final_bindings}
    members: dict[str, MemberObservation] = {}
    issues: list[CompositionIssue] = []
    for name, original in sorted(expected.items()):
        resolution = state.spec.members.get(name)
        expected_kind = (
            MemberKind.of_runtime(name, original)
            if resolution is None
            else resolution.kind
        )
        expected_abstract = False if resolution is None else resolution.abstract
        found = mro_dict_item(cls, name)
        actual_kind = None
        if found is not None:
            try:
                actual_kind = MemberKind.of_runtime(name, found[1])
            except CompositionError:
                pass
        unchanged = found is not None and found[1] is original
        members[name] = MemberObservation(
            name,
            expected_kind,
            actual_kind,
            None if found is None else found[0],
            source_location(original),
            () if resolution is None else resolution.origins,
            expected_abstract,
            name in state.final_bindings,
            unchanged,
        )
        if not unchanged or actual_kind is not expected_kind:
            issues.append(
                CompositionIssue(
                    "binding-drift",
                    name,
                    f"{cls.__qualname__}.{name} no longer has its admitted binding",
                )
            )
        actual_abstract = name in getattr(cls, "__abstractmethods__", ())
        if actual_abstract != expected_abstract:
            issues.append(
                CompositionIssue(
                    "abstractness-drift",
                    name,
                    f"{cls.__qualname__}.{name} abstractness changed",
                )
            )
    namespace = dict(class_namespace(cls))
    namespace.pop(ADMISSION_ATTRIBUTE, None)
    try:
        local = LocalMember.collect(
            namespace, class_name=cls.__qualname__, behaviour_definition=False
        )
        LocalMember.reject_shadowing(
            namespace,
            frozenset(expected),
            local,
            class_name=cls.__qualname__,
            owner=cls,
        )
        # External ordinary ancestors can be reconfigured outside our metaclass.
        for ancestor in class_mro(cls)[1:]:
            LocalMember.reject_generated_fields(
                class_namespace(ancestor), frozenset(expected), cls.__qualname__
            )
            for name in frozenset(class_annotations(ancestor)) & frozenset(expected):
                if name not in class_namespace(ancestor):
                    raise CompositionError(
                        f"{cls.__qualname__}.{name} annotates over an inherited composition member without implementing it",
                        code="annotation-shadows-member",
                        member=name,
                    )
    except CompositionError as error:
        issues.append(CompositionIssue(error.code, error.member, str(error)))
    return CompositionReport(cls, state.role, MappingProxyType(members), tuple(issues))


__all__ = [
    "CompositionIssue",
    "CompositionReport",
    "MemberObservation",
    "inspect_composition",
]
