"""Independent provider-set oracle checked against calls, not admission metadata."""

import inspect
import random
from itertools import permutations

import pytest

from behaviours import CompositionError, StrictMixin, trait


def provider(value: tuple[int, int]):
    def method(self):
        return value

    return method


@pytest.mark.parametrize("mode", ["trait", "mixin"])
def test_seeded_provider_graphs_and_all_orders(mode: str) -> None:
    rng = random.Random(20260905)
    definition_bases = () if mode == "trait" else (StrictMixin,)

    class Base:
        pass

    for case in range(120):
        declarations = []
        origins = {name: [] for name in ("a", "b", "c", "d")}
        for branch in range(3):
            methods = {}
            for name, member_origins in origins.items():
                if rng.randrange(3) != 0:
                    method = provider((case, branch))
                    methods[name] = method
                    member_origins.append(method)
            declaration = type(
                f"Branch{case}_{branch}",
                definition_bases,
                methods,
            )
            declarations.append(trait(declaration) if mode == "trait" else declaration)
        conflicts = {name for name, methods in origins.items() if len(methods) > 1}
        resolutions = {name: origins[name][-1] for name in conflicts}
        for order in permutations(declarations):
            bases = order if mode == "trait" else (*order, Base)
            if conflicts:
                with pytest.raises(CompositionError):
                    type("Unresolved", bases, {"__slots__": ()})
            combined = type("Resolved", bases, {"__slots__": (), **resolutions})
            obj = combined()
            for name, methods in origins.items():
                if not methods:
                    assert not hasattr(obj, name)
                    continue
                expected = resolutions.get(name, methods[0])
                assert inspect.getattr_static(combined, name) is expected
                assert getattr(obj, name)() == expected(obj)
