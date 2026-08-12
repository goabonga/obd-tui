# Contributing to obd-tui

Thanks for taking the time to contribute. This document is the short version
of how to propose a change and what the project expects in return.

## Code of Conduct

Participation in this project is governed by the
[Code of Conduct](CODE_OF_CONDUCT.md). By contributing you agree to abide by
its terms.

## Development setup

```bash
git clone https://github.com/goabonga/obd-tui.git
cd obd-tui
uv sync
uv run pre-commit install   # installs the pre-commit + commit-msg hooks
```

## Quality gates

Before pushing, make sure your code passes the same gates the `ci` workflow
runs:

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src                 # if the project uses mypy
uv run pytest                   # if the project has tests
uv tool run multicz validate --strict
python scripts/add_license_header.py --path . --types py,toml --check
```

## Commit messages

Commit messages MUST follow
[Conventional Commits](https://www.conventionalcommits.org/). They drive the
version bump and CHANGELOG computed by
[multicz](https://github.com/goabonga/multicz).

| Type | Effect on version | Use it for |
| --- | --- | --- |
| `feat` | minor | new capability |
| `fix` | patch | bug fix |
| `perf` | patch | performance improvement |
| `refactor`, `docs`, `test`, `chore`, `ci`, `build`, `style` | none | maintenance |
| `feat!` / `BREAKING CHANGE:` | major | incompatible change |

Only commits that touch the tracked paths (`src/**`, `pyproject.toml`)
trigger a release. Do not append `Co-Authored-By` trailers.

## Releasing

Releases are automated: on every push to `main`, the `ci` workflow runs
`multicz bump` (signed commit + tag) and publishes the artifact. Maintainers
do not bump versions or edit the changelog by hand.

## Reporting bugs and asking for features

Please open a GitHub issue. For security-sensitive reports, follow
[SECURITY.md](SECURITY.md) instead of the public tracker.
