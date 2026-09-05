"""Inheritance topology for trait adoption and strict-mixin application."""

from __future__ import annotations

import typing
from abc import ABC, ABCMeta
from enum import StrEnum

from behaviours.composition import CompositionError, class_mro, nominal_subclass


class ClassRole(StrEnum):
    """A class role admitted by the composition metaclass."""

    TRAIT = "trait"
    TRAIT_ADOPTER = "trait-adopter"
    STRICT_MIXIN = "strict-mixin"
    MIXIN_APPLICATION = "mixin-application"
    ORDINARY = "ordinary"

    @staticmethod
    def is_transparent_base(base: type) -> bool:
        return base is typing.Generic or base is ABC

    @classmethod
    def semantic_bases(cls, bases: tuple[type, ...]) -> tuple[type, ...]:
        return tuple(base for base in bases if not cls.is_transparent_base(base))

    @staticmethod
    def related_direct_bases(bases: tuple[type, ...]) -> tuple[type, type] | None:
        for index, left in enumerate(bases):
            for right in bases[index + 1 :]:
                if nominal_subclass(left, right) or nominal_subclass(right, left):
                    return left, right
        return None

    @staticmethod
    def is_strict_mixin_root(base: type) -> bool:
        from behaviours.admission import Admission

        state = Admission.of(base)
        return state is not None and state.root and state.role is ClassRole.STRICT_MIXIN

    @staticmethod
    def of(base: type) -> ClassRole | None:
        from behaviours.admission import Admission

        admission = Admission.of(base)
        return None if admission is None else admission.role

    @staticmethod
    def reject_unsupported_ordinary_base(base: type) -> None:
        from behaviours.admission import BehaviourMeta

        metaclass = type(base)
        if metaclass not in {type, ABCMeta, BehaviourMeta}:
            raise CompositionError(
                f"ordinary base {base.__qualname__} uses unsupported metaclass {metaclass.__qualname__}",
                code="custom-metaclass-not-supported",
            )

    @classmethod
    def reject_reapplication(
        cls, mixins: tuple[type, ...], ordinary_base: type
    ) -> None:
        applied = tuple(
            candidate
            for candidate in class_mro(ordinary_base)
            if not cls.is_strict_mixin_root(candidate)
            and cls.of(candidate) is ClassRole.STRICT_MIXIN
        )
        for mixin in mixins:
            for previous in applied:
                if nominal_subclass(mixin, previous) or nominal_subclass(
                    previous, mixin
                ):
                    raise CompositionError(
                        f"strict-mixin family {mixin.__qualname__} is already present through {previous.__qualname__}",
                        code="strict-mixin-reapplication",
                    )

    @classmethod
    def classify(
        cls,
        bases: tuple[type, ...],
        /,
        *,
        class_name: str,
        definition: ClassRole | None,
    ) -> tuple[ClassRole, tuple[type, ...], type | None]:
        semantic = cls.semantic_bases(bases)
        roles = tuple(cls.of(base) for base in semantic)
        related = cls.related_direct_bases(semantic)

        match definition, related, semantic, roles:
            case ClassRole.STRICT_MIXIN, None, parents, mixin_roles if all(
                role is ClassRole.STRICT_MIXIN for role in mixin_roles
            ):
                return ClassRole.STRICT_MIXIN, parents, None
            case ClassRole.STRICT_MIXIN, (_, _), parents, mixin_roles if all(
                role is ClassRole.STRICT_MIXIN for role in mixin_roles
            ):
                raise CompositionError(
                    f"{class_name} redundantly lists related mixin bases",
                    code="redundant-behaviour-bases",
                )
            case ClassRole.STRICT_MIXIN, _, _, _:
                raise CompositionError(
                    f"mixin definition {class_name} may inherit only admitted StrictMixin definitions",
                    code="invalid-strict-mixin-bases",
                )
            case ClassRole.TRAIT, None, parents, trait_roles if all(
                role is ClassRole.TRAIT for role in trait_roles
            ):
                return ClassRole.TRAIT, parents, None
            case ClassRole.TRAIT, (left, right), parents, trait_roles if all(
                role is ClassRole.TRAIT for role in trait_roles
            ):
                raise CompositionError(
                    f"{class_name} redundantly lists related Trait bases {left.__qualname__} and {right.__qualname__}",
                    code="redundant-behaviour-bases",
                )
            case ClassRole.TRAIT, _, _, _:
                raise CompositionError(
                    f"trait definition {class_name} may inherit only admitted Trait definitions",
                    code="invalid-trait-bases",
                )
            case None, None, parents, trait_roles if parents and all(
                role is ClassRole.TRAIT for role in trait_roles
            ):
                return ClassRole.TRAIT_ADOPTER, parents, None
            case None, (left, right), parents, trait_roles if parents and all(
                role is ClassRole.TRAIT for role in trait_roles
            ):
                raise CompositionError(
                    f"{class_name} redundantly lists related Trait bases {left.__qualname__} and {right.__qualname__}",
                    code="redundant-behaviour-bases",
                )
            case None, _, parents, mixin_roles if (
                parents
                and all(role is ClassRole.STRICT_MIXIN for role in mixin_roles)
                and any(cls.is_strict_mixin_root(base) for base in parents)
                and len(parents) != 1
            ):
                raise CompositionError(
                    f"{class_name} may not combine the StrictMixin root with definitions",
                    code="invalid-strict-mixin-bases",
                )
            case None, (left, right), parents, mixin_roles if parents and all(
                role is ClassRole.STRICT_MIXIN for role in mixin_roles
            ):
                raise CompositionError(
                    f"{class_name} redundantly lists related StrictMixin bases {left.__qualname__} and {right.__qualname__}",
                    code="redundant-behaviour-bases",
                )
            case None, None, parents, mixin_roles if parents and all(
                role is ClassRole.STRICT_MIXIN for role in mixin_roles
            ):
                return ClassRole.STRICT_MIXIN, parents, None
            case None, _, [*mixins, ordinary_base], [
                *mixin_roles,
                ordinary_role,
            ] if (
                mixins
                and all(role is ClassRole.STRICT_MIXIN for role in mixin_roles)
                and ordinary_role
                in {
                    None,
                    ClassRole.TRAIT_ADOPTER,
                    ClassRole.MIXIN_APPLICATION,
                    ClassRole.ORDINARY,
                }
                and ordinary_base is not object
                and not any(cls.is_strict_mixin_root(base) for base in mixins)
            ):
                match cls.related_direct_bases(tuple(mixins)):
                    case left, right:
                        raise CompositionError(
                            f"{class_name} redundantly lists related StrictMixin bases {left.__qualname__} and {right.__qualname__}",
                            code="redundant-behaviour-bases",
                        )
                    case None:
                        cls.reject_unsupported_ordinary_base(ordinary_base)
                        cls.reject_reapplication(tuple(mixins), ordinary_base)
                        return (
                            ClassRole.MIXIN_APPLICATION,
                            tuple(mixins),
                            ordinary_base,
                        )
            case None, _, (ordinary_base,), (role,) if role in {
                ClassRole.TRAIT_ADOPTER,
                ClassRole.MIXIN_APPLICATION,
                ClassRole.ORDINARY,
            }:
                return ClassRole.ORDINARY, (), ordinary_base
            case None, _, _, _:
                raise CompositionError(
                    f"{class_name} has an unsupported inheritance topology; Traits adopt without an ordinary base, while StrictMixins precede exactly one ordinary base",
                    code="unsupported-inheritance-topology",
                )
            case _:
                raise TypeError(
                    "internal definition role must be trait or strict-mixin"
                )


__all__ = [
    "ClassRole",
]
