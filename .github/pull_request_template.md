## Description

<!-- Describe what this PR does and why. -->

## Type

<!-- Check the one that applies: -->

- [ ] `feat` - New feature
- [ ] `fix` - Bug fix
- [ ] `docs` - Documentation
- [ ] `refactor` - Code refactoring
- [ ] `test` - Adding or updating tests
- [ ] `chore` - Maintenance
- [ ] `ci` - CI / release pipeline

## Changes

<!-- List the main changes introduced by this PR: -->

-

## Related Issues

<!-- Link related issues: Closes #123, Fixes #456 -->

## Checklist

- [ ] Commits follow [Conventional Commits](https://www.conventionalcommits.org/)
- [ ] Branch is up to date with `main`
- [ ] `uv sync` succeeds
- [ ] `uv run ruff check src tests` and `uv run ruff format --check src tests` are clean
- [ ] `uv run mypy src` is clean (if the project uses mypy)
- [ ] `uv run pytest` passes (if the project has tests)
- [ ] `uv tool run multicz validate --strict` passes
- [ ] SPDX license headers are present (`python scripts/add_license_header.py --path . --types py,toml --check`)
- [ ] No `Co-Authored-By` trailer in commit messages
