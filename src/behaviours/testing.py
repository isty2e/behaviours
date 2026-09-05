"""Optional assertion adapter; no pytest or Hypothesis runtime dependency."""

from behaviours.inspect import inspect_composition


def assert_composition(cls: type, /) -> None:
    """Assert that a managed class still has its admitted composition bindings.

    Parameters
    ----------
    cls : type
        A managed behavior definition, adopter, application or ordinary descendant.

    Raises
    ------
    AssertionError
        If the class is unmanaged or inspection detects damaged bindings/fields.
    TypeError
        If the argument is not a class.

    Notes
    -----
    This checks structural composition, not domain laws or arbitrary instance state.
    Use ordinary parametrized tests and user-owned strategies for semantic laws.
    """
    report = inspect_composition(cls)
    if not report.is_valid:
        raise AssertionError(report.format())


__all__ = ["assert_composition"]
