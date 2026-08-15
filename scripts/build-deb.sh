#!/usr/bin/env bash

# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

# Build the Debian source packages uploaded to the Launchpad PPA.
#
#   scripts/build-deb.sh [series...]        # default: SERIES below
#
# One source package is produced per Ubuntu series, all from the same
# upstream tarball, into ../build-area. They are signed if a key is
# available and can then be sent with:
#
#   dput ppa:goabonga/obd-tui ../build-area/obd-tui_*_source.changes
#
# The Launchpad builders have no network access, so every wheel the
# application needs — its own included — is downloaded here and travels in
# the tarball. Every runtime dependency is a pure-Python wheel, so a single
# set works for every series and architecture.
#
# Signing: SIGN_KEY=<key id> picks a key, UNSIGNED=1 skips signing (for a
# local check — Launchpad rejects an unsigned upload).

set -euo pipefail

PROJECT="obd-tui"
PPA="ppa:goabonga/obd-tui"

# Series whose Python is 3.11 or newer, which the project requires: jammy
# ships 3.10 and is therefore out of reach.
SERIES=(noble plucky questing)

# Debian revision of the upstream version. The `~` suffix added per series
# sorts before the plain revision, which is the backport convention and
# lets the same upstream version be uploaded to several series.
REVISION=1

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_AREA="${BUILD_AREA:-${ROOT}/../build-area}"

# Progress goes to stderr: stdout carries values captured by the callers.
log() { printf '\n==> %s\n' "$*" >&2; }

main() {
    local -a series=("$@")
    [ ${#series[@]} -eq 0 ] && series=("${SERIES[@]}")

    cd "${ROOT}"
    local version
    version="$(project_version)"
    check_changelog "${version}"
    log "packaging ${PROJECT} ${version} for: ${series[*]}"

    collect_wheels
    local tarball
    tarball="$(make_tarball "${version}")"

    mkdir -p "${BUILD_AREA}"
    # Only the first upload carries the upstream tarball. The archive keeps
    # one copy per upstream version, so sending it again with the next
    # series is at best redundant and at worst refused — dpkg warns about
    # exactly that, and Launchpad's upload queue acts on it.
    local include_orig=1
    for name in "${series[@]}"; do
        build_source "${version}" "${name}" "${tarball}" "${include_orig}"
        include_orig=0
    done

    log "done — upload with:"
    printf '    dput %s %s/%s_*_source.changes\n' \
        "${PPA}" "${BUILD_AREA}" "${PROJECT}"
}

project_version() {
    # The version multicz bumped, which is also the one in the built wheel.
    python3 - <<'PY'
import pathlib, re
text = pathlib.Path("src/obd_tui/__init__.py").read_text(encoding="utf-8")
match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', text)
if match is None:
    raise SystemExit("no __version__ found in src/obd_tui/__init__.py")
print(match.group(1))
PY
}

export_requirements() {
    # The pinned runtime closure, straight from the lockfile. The pipeline
    # runs this as a step of its own; a local build falls back to doing it
    # here so the script still stands alone.
    log "exporting debian/requirements.txt"
    uv export --frozen --no-dev --no-emit-project \
        --no-annotate --no-hashes -o debian/requirements.txt >/dev/null
}

check_changelog() {
    # multicz prepends the stanza for the release being cut. If the two
    # disagree, the upload would carry one version's number over another
    # version's notes — stop rather than publish that.
    local version="$1" top
    top="$(dpkg-parsechangelog -l debian/changelog -S Version)"
    if [ "${top%%-*}" != "${version}" ]; then
        log "debian/changelog is at ${top}, the project at ${version}."
        log "Let multicz write the stanza before packaging."
        exit 1
    fi
}

collect_wheels() {
    # The project's own wheel plus its pinned runtime closure. --no-deps
    # because the export is already the full, resolved set.
    log "collecting wheels"
    rm -rf wheels
    mkdir -p wheels

    [ -s debian/requirements.txt ] || export_requirements
    uv build --wheel --out-dir wheels >/dev/null

    # pip, not uv: uv has no wheel-download command.
    python3 -m pip download \
        --only-binary=:all: \
        --no-deps \
        --dest wheels \
        --requirement debian/requirements.txt >/dev/null

    # pip resolves the project itself from the wheelhouse, so name it in
    # the requirements rather than letting dh_virtualenv build the source.
    printf '%s==%s\n' "${PROJECT}" "$(project_version)" >> debian/requirements.txt

    local count
    count="$(find wheels -name '*.whl' | wc -l)"
    log "${count} wheels collected"
    if find wheels -name '*.whl' ! -name '*-none-any.whl' | grep -q .; then
        log "warning: a wheel is platform specific, so the package no longer"
        log "         builds for every series and architecture:"
        find wheels -name '*.whl' ! -name '*-none-any.whl' -printf '    %f\n'
    fi
}

make_tarball() {
    local version="$1"
    local tarball="${BUILD_AREA}/${PROJECT}_${version}.orig.tar.gz"
    log "building ${tarball##*/}"
    mkdir -p "${BUILD_AREA}"
    # Everything git tracks, plus the wheelhouse, minus the packaging
    # itself: debian/ belongs to the .debian.tar.xz, not to the upstream
    # tarball.
    tar --create --gzip --file "${tarball}" \
        --transform "s,^,${PROJECT}-${version}/," \
        --exclude-vcs \
        wheels src tests scripts pyproject.toml uv.lock README.md LICENSE \
        CHANGELOG.md docs
    printf '%s' "${tarball}"
}

build_source() {
    local version="$1" name="$2" tarball="$3" include_orig="${4:-1}"
    local full="${version}-${REVISION}~${name}1"
    local dir="${BUILD_AREA}/${PROJECT}-${version}"

    log "source package for ${name} (${full})"
    rm -rf "${dir}"
    mkdir -p "${dir}"
    tar --extract --file "${tarball}" --strip-components=1 --directory "${dir}"
    cp -r debian "${dir}/debian"
    reheader_changelog "${dir}/debian/changelog" "${full}" "${name}"

    # -S source only. -sa ships the upstream tarball, -sd leaves it out for
    # the series that follow, which reference the copy the archive already
    # holds. -d and -nc because the build dependencies and the clean target
    # are the builders' business — dh-virtualenv is not needed to produce a
    # source package, and the tree was just unpacked, so there is nothing
    # to clean.
    local -a sign=()
    if [ "${UNSIGNED:-0}" = "1" ]; then
        sign=(-us -uc)
    elif [ -n "${SIGN_KEY:-}" ]; then
        sign=("-k${SIGN_KEY}")
    fi
    local source_flag=-sd
    [ "${include_orig}" = "1" ] && source_flag=-sa
    ( cd "${dir}" && debuild -S "${source_flag}" -d -nc "${sign[@]}" )
    rm -rf "${dir}"
}

reheader_changelog() {
    # multicz wrote the stanzas, release bullets and all. Only the topmost
    # header is rewritten, so each upload carries the real release notes
    # under its own series and version.
    local file="$1" full="$2" name="$3"
    python3 "${ROOT}/scripts/reheader_changelog.py" "${file}" "${full}" "${name}"
}

main "$@"
