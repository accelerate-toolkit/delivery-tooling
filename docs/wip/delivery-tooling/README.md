# Delivery tooling implementation

The public repository is created and its reviewed initial Renovate implementation
is pushed. Composable release machinery and repeatable runner checks are published
as the verified source release `v0.1.0`. Consumer adoption remains pending.

## Implemented

- Credential-free version planning using conventional-commits-parser and semver;
  strict configuration/plan schemas, initial/no-release rules, independent streams,
  path scoping, legacy tag prefixes and the organization 0.x breaking rule.
- Exact artifact verification, source-bound manifests and checksums.
- GitHub publisher with source-history/policy revalidation, required-check gating,
  immutable tag/asset handling, matching-draft recovery and concurrent retry handling.
- Plan, verify and publish composite actions that execute code from their own
  pinned revision. Consumers retain their job graph and build implementation.
- Self-hosting source-release workflow with separate check, plan and publication
  permissions and a retained plan artifact for failed-job retries.
- Renovate runner tests for target isolation, preview defaults and credential guards.

See [release design](../../design/releases.md) for interfaces, library assessment,
limitations and recovery. No private consumer inventory is stored in this repository.

## Evidence

The initial preset copy was byte-identical to the compatibility entry point, and
Renovate 44.151.0 validated both configurations. Credential-free extraction found
SHA/version-comment action pins, Node/uv, Renovate CLI and validator versions.
These extraction checks used staged local preset content and did not prove remote
preset resolution or authenticated version lookup.

Verification on 15 November 2026:

- `make check`: strict Renovate configuration validation, actionlint, five runner
  tests and 26 release tests pass.
- The 26 release tests also pass inside the pinned Node 24.21.0 Linux image.
- All four composite actions pass the GitHub Action JSON schema check.
- A local CLI preview and source-only manifest generation succeed. That preview
  uses uncommitted configuration; it is not a publishable release candidate.
- Read-only GitHub adapter calls verify the initial public commit's `check` job,
  an empty release list and correct handling of an absent tag. No release API
  mutation was used for these checks.

The [first live source release](../../evidence/first-source-release/README.md) is
verified. Application publication, live interrupted-upload recovery, signed
provenance verification, real dependency PR creation and shared-runner APM lockfile
updates remain unverified.

## Remaining

- Verify live interrupted-publication recovery in an explicitly scoped pilot.
- Pilot an application with its complete artifact set and provenance checks.
- Complete repository inventory privately and migrate consumers in reviewed batches.
- Supply missing bot credentials in their owning repositories; verify actual PRs.
- Prove action/preset pin updates and resolved-policy equivalence before switching
  the existing preset entry point. Preserve existing merge and schedule policies.

The source release is verified. No consumer migration, deployment or product
acceptance is claimed.
