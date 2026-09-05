"""Native-inheritance composition with explicit conflict semantics."""

from __future__ import annotations

import sys
from collections.abc import Mapping
from typing import Literal

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override


class CompositionError(TypeError):
    """Report an invalid class definition or forbidden surface mutation.

    Parameters
    ----------
    message : str
        Human-readable explanation of the rejected operation.
    code : str
        Machine-readable diagnostic category, also exposed as ``error.code``.
    member : str or None, optional
        Member involved in the failure, when one can be identified.
    origins : tuple[MemberOrigin, ...], optional
        Native provider provenance associated with the conflict.
    hint : str or None, optional
        Suggested direction, without automatically choosing an implementation.
    phase : {"definition", "construction", "mutation", "inspection"}, optional
        Boundary at which the failure was observed.
    """

    def __init__(
        self,
        message: str,
        /,
        *,
        code: str,
        member: str | None = None,
        origins: tuple[MemberOrigin, ...] = (),
        hint: str | None = None,
        phase: Literal[
            "definition", "construction", "mutation", "inspection"
        ] = "definition",
    ) -> None:
        super().__init__(message)
        self.code = code
        self.member = member
        self.origins = origins
        self.hint = hint
        self.phase = phase

    @override
    def __str__(self) -> str:
        lines = [super().__str__()]
        for origin in self.origins:
            owner = origin.source_owner or origin.owner
            location = origin.location
            suffix = "" if location is None else f" ({location.path}:{location.line})"
            lines.append(
                f"  {owner.__module__}.{owner.__qualname__}.{origin.name}: "
                f"{origin.kind.value}{suffix}"
            )
        if self.hint:
            lines.append(self.hint)
        return "\n".join(lines)

    def __reduce__(self) -> tuple[object, tuple[object, ...]]:
        return (
            CompositionError.restore,
            (
                str(self.args[0]),
                self.code,
                self.member,
                self.origins,
                self.hint,
                self.phase,
            ),
        )

    @classmethod
    def restore(
        cls,
        message: str,
        code: str,
        member: str | None,
        origins: tuple[MemberOrigin, ...],
        hint: str | None,
        phase: Literal["definition", "construction", "mutation", "inspection"],
    ) -> CompositionError:
        return cls(
            message, code=code, member=member, origins=origins, hint=hint, phase=phase
        )


BOOTSTRAP_TOKEN = object()
ADMISSION_ATTRIBUTE = "__" + "behaviours_admission__"
RESERVED_METADATA_NAME = "__" + "composition_spec__"
INTERPRETER_CLASS_NAMES = frozenset(
    {
        "__abstractmethods__",
        "__annotate__",
        "__annotate_func__",
        "__annotations__",
        "__annotations_cache__",
        "__classcell__",
        "__classdictcell__",
        "__doc__",
        "__firstlineno__",
        "__final__",
        "__module__",
        "__orig_bases__",
        "__parameters__",
        "__qualname__",
        "__slots__",
        "__static_attributes__",
        "__type_params__",
        "_abc_impl",
    }
)
MISSING = object()


def class_namespace(cls: type) -> Mapping[str, object]:
    return type.__dict__["__dict__"].__get__(cls)


def class_annotations(source: Mapping[str, object] | type) -> dict[str, object]:
    """Return class-body annotations from a live class or a class namespace.

    On Python 3.14+, PEP 649 may store annotations in an annotate function or a
    type descriptor cache rather than an ``__annotations__`` dict. FORWARDREF
    names the annotated members without evaluating arbitrary user expressions.
    """
    if isinstance(source, type):
        if sys.version_info >= (3, 14):
            import annotationlib

            observed = annotationlib.get_annotations(
                source, format=annotationlib.Format.FORWARDREF
            )
            if type(observed) is dict:
                return observed
        source = class_namespace(source)
    if sys.version_info >= (3, 14):
        import annotationlib

        annotate = annotationlib.get_annotate_from_class_namespace(source)
        if annotate is not None:
            observed = annotationlib.call_annotate_function(
                annotate, annotationlib.Format.FORWARDREF
            )
            if type(observed) is dict:
                return observed
    annotations = source.get("__annotations__", {})
    if type(annotations) is dict:
        return annotations
    return {}


def class_mro(cls: type) -> tuple[type, ...]:
    return type.__dict__["__mro__"].__get__(cls)


def nominal_subclass(candidate: type, ancestor: type) -> bool:
    return candidate is ancestor or ancestor in class_mro(candidate)[1:]


def mro_dict_item(cls: type, name: str) -> tuple[type, object] | None:
    for owner in class_mro(cls):
        if name in class_namespace(owner):
            return owner, class_namespace(owner)[name]
    return None


# Owner modules import host names defined above. Keep this after the kernel.
from behaviours.admission import Admission, CompositionSpec
from behaviours.members import LocalMember, MemberKind
from behaviours.origin import MemberOrigin, MemberResolution, SourceLocation
from behaviours.topology import ClassRole

__all__ = [
    "Admission",
    "ClassRole",
    "CompositionError",
    "CompositionSpec",
    "LocalMember",
    "MemberKind",
    "MemberOrigin",
    "MemberResolution",
    "SourceLocation",
]
