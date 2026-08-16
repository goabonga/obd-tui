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
#
# SKIP_ORIG=1 leaves the upstream tarball out of every source package, for
# re-uploading a version the archive already holds.

set -euo pipefail

PROJECT="obd-tui"
PPA="ppa:goabonga/obd-tui"

# Series to publish for. Two constraints narrow the list: the project needs
# Python 3.11, which rules out jammy and anything older, and Launchpad
# refuses an upload for a series that has gone obsolete - questing and
# plucky were both dropped after answering exactly that. Only the two
# supported LTS releases are left; revisit as they age out.
SERIES=(noble resolute)

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
    # Every series carries the upstream tarball. dpkg warns that it may be
    # redundant, and it is — but all three are built from the same file, so
    # the archive sees a byte-identical duplicate, which it accepts. Having
    # only the first upload carry it makes the others depend on that one
    # being accepted first: if it is refused for any reason, the rest are
    # refused too, for a tarball the archive never received.
    #
    # SKIP_ORIG=1 leaves it out of all of them, for a re-upload of a
    # version whose tarball is already in the archive.
    local include_orig=1
    [ "${SKIP_ORIG:-0}" = "1" ] && include_orig=0
    for name in "${series[@]}"; do
        build_source "${version}" "${name}" "${tarball}" "${include_orig}"
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

release_epoch() {
    # The release's own date, from the stanza multicz wrote. Every
    # timestamp that ends up in the tarball is pinned to it, so the same
    # release always produces the same bytes.
    dpkg-parsechangelog -l debian/changelog -S Timestamp
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
    # The build backend stamps the wheel from the clock unless told
    # otherwise, and a wheel that differs between two builds of the same
    # release makes the tarball differ too - which the archive refuses.
    SOURCE_DATE_EPOCH="$(release_epoch)" uv build --wheel --out-dir wheels >/dev/null

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

    # The archive keeps one tarball per upstream version and refuses a
    # second one whose bytes differ, so two builds of the same release must
    # produce the same file. Left to itself tar records the checkout's
    # mtimes, the builder's uid and whatever order the directory walk
    # returns, and gzip stamps its own header - all of which change between
    # runs. The release date pins the timestamps.
    # Everything git tracks, plus the wheelhouse, minus the packaging
    # itself: debian/ belongs to the .debian.tar.xz, not to the upstream
    # tarball.
    tar --create \
        --sort=name \
        --mtime="@$(release_epoch)" \
        --owner=0 --group=0 --numeric-owner \
        --transform "s,^,${PROJECT}-${version}/," \
        --exclude-vcs \
        wheels src tests scripts pyproject.toml uv.lock README.md LICENSE \
        CHANGELOG.md docs \
    | gzip --best --no-name > "${tarball}"

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
