#!/usr/bin/env bash

# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

# Re-author and GPG-sign a Dependabot commit, normalising its subject to
# Conventional Commits with a type that reflects what the bump affects:
#   - GitHub Actions bumps      -> ci          (not shipped)
#   - dev-group / tooling bumps -> chore(deps)  (not shipped, no release)
#   - runtime dependency bumps  -> fix(deps)    (shipped -> patch release)
#
# Runtime vs dev is decided by membership in [dependency-groups].dev of
# pyproject.toml. Run by `git rebase --exec` in dependabot-rewrite.yml.

set -euo pipefail

changed=$(git show --name-only --pretty='' HEAD)
subject=$(git log -1 --pretty=%s HEAD)
body=$(git log -1 --pretty=%b HEAD | sed '/^[Cc]o-authored-by:/d')

# Drop any leading conventional prefix Dependabot already added.
text=$(printf '%s' "$subject" | sed -E 's/^[a-z]+(\([^)]+\))?!?:[[:space:]]*//')

is_dev_dep() {
    # Exit 0 if $1 is declared in [dependency-groups].dev of pyproject.toml.
    python3 - "$1" <<'PY' 2>/dev/null || return 1
import sys, tomllib

pkg = sys.argv[1].strip().lower().replace("_", "-")
data = tomllib.load(open("pyproject.toml", "rb"))
dev = data.get("dependency-groups", {}).get("dev", [])


def name(spec: str) -> str:
    for sep in ("[", ">", "<", "=", "~", "!", ";", " "):
        spec = spec.split(sep)[0]
    return spec.strip().lower().replace("_", "-")


names = {name(d) for d in dev if isinstance(d, str)}
sys.exit(0 if pkg in names else 1)
PY
}

if printf '%s' "$changed" | grep -q '[.]github/workflows/'; then
    prefix="ci"
elif printf '%s' "$text" | grep -qiE 'dev-tools group'; then
    prefix="chore(deps)"
else
    # Single-package bump: "bump <pkg> from X to Y".
    pkg=$(printf '%s' "$text" | sed -nE 's/^[Bb]ump ([A-Za-z0-9._-]+) from .*/\1/p')
    if [ -n "$pkg" ] && is_dev_dep "$pkg"; then
        prefix="chore(deps)"
    elif [ -n "$pkg" ]; then
        prefix="fix(deps)"
    else
        prefix="chore(deps)"
    fi
fi

if [ -n "$body" ]; then
    new_msg=$(printf '%s: %s\n\n%s' "$prefix" "$text" "$body")
else
    new_msg=$(printf '%s: %s' "$prefix" "$text")
fi

git commit --amend --reset-author -m "$new_msg" --quiet
