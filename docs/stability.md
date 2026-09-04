# Stability and deprecation policy

obd-tui follows [Semantic Versioning](https://semver.org/).

## Versioning

- **MAJOR** - incompatible API changes (`feat!` / `BREAKING CHANGE:`).
- **MINOR** - backwards-compatible features (`feat`) and deprecations
  (`deprecate`) / removals after a deprecation window (`remove`).
- **PATCH** - backwards-compatible fixes (`fix`) and performance (`perf`).

Versions are computed from [Conventional Commits](https://www.conventionalcommits.org/)
by [multicz](https://github.com/goabonga/multicz). While `0.x`, treat minor
bumps as potentially breaking.

## Deprecation cadence (n + 2)

The project uses the standard Python `n + 2` cadence:

1. **Announce + warn** - in release *n*, mark the API deprecated with a
   `DeprecationWarning` and a `deprecate:` commit. The old behaviour still
   works.
2. **Grace period** - release *n + 1* keeps the deprecated API working.
3. **Remove** - release *n + 2* removes it with a `remove:` commit.

Each step is a normal release; the deprecation announcement is the
breaking-change notice, so the removal itself is a minor bump.

## What is covered

Public, documented API only. Anything underscore-prefixed, undocumented, or
explicitly marked internal may change at any time.
