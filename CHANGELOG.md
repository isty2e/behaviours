# Changelog

## 0.1.0

First public release.

Native trait adoption and base-last strict-mixin application on ordinary class graphs.
Independent providers of the same member are not chosen by base order. Behaviour types
do not own instance layout.

- `@trait` declarations; abstract traits inherit `abc.ABC`
- `@mixin` and `StrictMixin`, applied with one ordinary base last
- Native instance, class, and static methods, including async forms
- Standard `@final` at managed class boundaries
- `CompositionError` with member, origin, hint, and phase
- `inspect_composition` and optional `assert_composition`
- Direct dataclass and attrs use on ordinary adopters and applications
- Python 3.11–3.14
