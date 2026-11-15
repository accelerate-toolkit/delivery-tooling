# Release machinery

Status: implemented, tested and approved for publication; live release verification
remains pending.

Consumers own their job graph, checks, build commands, runner selection, matrices,
artifact contents, compatibility boundary and deployment. Shared CLI commands and
composite actions supply planning, artifact verification and GitHub publication.
The tooling's own workflow is a source-only consumer of these same operations.

## Library choice

[Release Please](https://github.com/googleapis/release-please) maintains a release
PR before tagging. That extra merge step is not the agreed normal publication path.
[semantic-release](https://semantic-release.gitbook.io/semantic-release/usage/configuration)
provides automatic release orchestration, but its dry run verifies push permission
and its full lifecycle does not directly provide the separate credential-free plan
and consumer-owned build handoff required here.

Use [conventional-commits-parser](https://github.com/conventional-changelog/conventional-changelog)
for commit structure and [node-semver](https://github.com/npm/node-semver) for version
validation, ordering and increments. Their MIT/ISC licenses allow this use. Ajv
validates configuration and plan contracts. Exact versions and integrity hashes
are committed in package-lock.json; installation disables lifecycle scripts.

The orchestration layer owns organization policy, source binding, artifact
verification and publication recovery. It does not implement another SemVer parser.
Existing source-only and application publishers informed the assessment; the new
publisher does not copy application-specific metadata or use asset overwrites.

## Configuration and version planning

The consumer's `release.json` follows [the configuration schema](../../schemas/release.schema.json).
Each named stream declares its tag prefix, initial version, required check names,
optional legacy tag prefixes, optional Git pathspecs and exact artifact filenames.
There are no build commands in this configuration. Tag prefixes cannot be shared
between streams. Use independent streams only for independently versioned interfaces.

The planner requires full Git history and tags. It considers the highest stable
SemVer tag reachable from the selected source commit in the stream's current and
legacy namespaces. Scoped streams consider commits touching their configured paths.
The highest commit impact wins: `feat` is minor, `fix`/`perf` patch, and `!` or a
breaking footer major. A breaking change on 0.x advances to 1.0.0. Other types do
not trigger releases. Initial eligible changes use the configured initial version;
an initial breaking change with a 0.x initial version uses 1.0.0. No eligible
commits produces an explicit no-release plan. Prereleases are not supported yet.

The [plan contract](../../schemas/release-plan.schema.json) binds repository, stream,
policy, source commit, baseline, version, tag and notes with a deterministic digest.
Local previews may use edited configuration, but publication requires that exact
configuration at the source commit. Publication recomputes the plan from committed
policy and source history, ignoring only its own possibly reserved tag during retry.
A changed plan cannot be legitimized merely by recalculating its digest.

Commit classification remains a consumer responsibility. Runtime dependency
updates that change a shipped artifact need an eligible commit type. Tooling-only
changes do not automatically release applications. This implementation does not
infer compatibility impact from a changed file or dependency name.

## Consumer workflow contract

1. Check out the source with `fetch-depth: 0`. Run the required checks without
   publication credentials. Give required checks unique, stable names.
2. Plan from that source. If `release` is false, stop the release path.
3. Build/package from `source-commit`, using the planned version. Verify the exact
   artifact directory and persist the original plan, manifest and built artifacts
   as workflow artifacts before entering publication.
4. In a separate publication job, check out `source-commit`, download those exact
   artifacts from the same workflow run, and publish with the expected commit.

Serialize releases per repository/stream with `cancel-in-progress: false`. Restrict
publication to reviewed default-branch changes and use `needs` to bind build/check
jobs. Branch protection and review policy stay with the consumer. The publisher
independently queries the explicitly required check-run names or legacy status
contexts on the exact source SHA and refuses missing, pending or unsuccessful
results. It does not infer branch-review policy from a successful check.

The CLI requires Node 22+, Git and locked dependencies. Publication additionally
requires `gh` and a GitHub token with contents write and checks read access.
Composite actions install pinned Node and their locked dependencies from the action
revision. Helpers are located through `github.action_path`, not consumer files.
Do not invoke the publisher on untrusted pull-request source. Fork PR checks and
planning require no publishing token. No deployment credentials are used.

## Artifacts and provenance

Verification rejects missing, extra, non-regular or symlinked artifacts. It records
size and SHA-256 for each expected file and emits `release-plan.json`,
`release-manifest.json` and `SHA256SUMS`. Keep generated metadata separate from the
consumer artifact directory. A source-only stream has an empty artifact list and
publishes immutable tagged source plus these release records.

The manifest is unsigned build metadata, not a cryptographic provenance
attestation. Applications must include their required provenance/attestation file
in the expected artifact list and validate its content in their own check/build
jobs. Shared tooling verifies its bytes like the other artifacts; it does not yet
validate attestation signatures or builder identity. The application example
requires a provenance file explicitly. Artifacts are buffered in memory during
publication; large-artifact streaming is not implemented.

## Publication and recovery

All local verification precedes remote mutations. The publisher checks the
recorded manifest, source, policy, plan and required checks, then reserves the
exact tag. Existing conflicting tags are rejected and never moved. Existing drafts
must match the original source and plan; a foreign draft is rejected before tag
creation. Draft assets are downloaded and verified by size and SHA-256. Missing
matching assets can be uploaded; conflicting or unexpected assets are never
replaced or deleted. Complete asset verification precedes publication.

Matching concurrent creation/upload races converge; other conflicts fail closed.
A completed release is verified and left unchanged. Missing or changed published
assets require a corrective release, not repair in place. GitHub tag protection
and release-immutability account settings are separate controls; this tooling does
not configure them or claim other actors cannot modify a release.

Retry an interrupted **publication job** using its retained original plan and
artifacts. A reserved tag does not invalidate that plan. Do not regenerate a plan
from newer source and reuse an old draft. A newer release is blocked while its
baseline lacks a completed GitHub release. For legacy tag-only streams, establish
a reviewed GitHub source release for the baseline before enabling publication;
planning understands the legacy namespace without retagging it.

The self-hosting workflow saves plan/manifest artifacts for 90 days. Consumers
must choose retention sufficient for recovery; if originals expire, restore the
original verified files from retained evidence. No new tag or release event is
needed to trigger another job: orchestration is an explicit job dependency chain.
GitHub publication has not yet been exercised live for this implementation.
