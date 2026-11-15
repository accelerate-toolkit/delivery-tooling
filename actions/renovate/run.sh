#!/usr/bin/env bash
set -euo pipefail

# This helper comes from the same pinned action revision, never the consumer tree.
case "${1-}" in
  ''|--check) ;;
  *) echo 'Usage: run.sh [--check]' >&2; exit 2 ;;
esac
[[ $# -le 1 ]] || { echo 'Usage: run.sh [--check]' >&2; exit 2; }
[[ -n "${RENOVATE_TOKEN-}" ]] || { echo 'Configure a repository-scoped GitHub-only bot token.' >&2; exit 1; }
[[ "${BOT_VERSION-}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo 'Renovate requires an exact version.' >&2; exit 1; }
[[ -z "${APM_VERSION-}" || "$APM_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo 'APM requires an exact version.' >&2; exit 1; }
[[ "${CALLER_REPOSITORY-}" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || { echo 'A single caller repository is required.' >&2; exit 1; }
export RENOVATE_DRY_RUN="${RENOVATE_DRY_RUN-full}"
[[ -z "$RENOVATE_DRY_RUN" || "$RENOVATE_DRY_RUN" == full ]] || { echo 'dry-run must be full or empty.' >&2; exit 1; }
[[ "${1-}" != --check ]] || exit 0

export RENOVATE_PLATFORM=github
export RENOVATE_REPOSITORIES="$CALLER_REPOSITORY"
export RENOVATE_AUTODISCOVER=false
export RENOVATE_ONBOARDING=false
export RENOVATE_REQUIRE_CONFIG=required
export RENOVATE_BINARY_SOURCE=global
export GITHUB_TOKEN="$RENOVATE_TOKEN"
export LOG_LEVEL=info
exec npx --yes --package="renovate@$BOT_VERSION" renovate
