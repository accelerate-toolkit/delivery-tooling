# Delivery tooling

Prepared locally; no release is published and consumer migration has not started.
The initial implementation supplies a public Renovate preset and a composite
runner action. Release planning and publication machinery remain future work.

Consumers own their jobs, runner selection, schedule, concurrency and permissions.
The action supplies pinned Node/Renovate tooling, optional pinned APM provisioning,
credential validation and single-repository execution. It targets the caller's
`github.repository`, including after renames. It does not enable automerge;
repository policy still controls merging. The copied public preset retains its
existing automerge policy, so new consumers must explicitly choose their policy.

## Runner contract

`actions/renovate` runs on an Ubuntu runner with Bash. The caller checks out its
repository with persisted checkout credentials disabled, supplies a GitHub-only
bot token, and installs additional manager tools such as Go or Terraform when
needed. Those tool requirements must be checked against actual extraction and
lockfile updates before migrating an existing Docker-based runner.

Inputs:

- `token`: required repository-scoped bot credential; never a deployment token.
- `dry-run`: `full` by default, or an empty string for normal writes.
- `renovate-version`: exact version, default `44.151.0`.
- `apm-version`: optional exact version, only for consumers needing lockfile updates.

The caller owns `contents: read` for its workflow token; the separate bot token
needs the repository permissions for contents, issues, PRs and workflow updates.
Do not invoke this action on untrusted PR code. Caller-controlled environment can
supply private-module settings; keep credentials in secrets. Avoid overlapping
hosted and self-hosted runners for the same repository.

Use a published release's verified commit SHA with a version comment when adopting
this action. No deployable consumer example is provided until such a release
exists. Helper logic is embedded in the pinned composite action, so it cannot
accidentally execute a helper from the consumer checkout.

For initial onboarding before this repository is published, consumers can use
the existing upstream `renovatebot/github-action` directly. Do not replace working
runners until the shared action has passed a real pilot with the required managers.

## Validation and publication

Run `make`, then `make check`. Validate GitHub workflows and composite action
metadata, and perform credential-free dependency extraction before publication.
An authenticated preview and real update PR remain required live acceptance steps.

Use one immutable SemVer stream for this tooling. The first source-only release
requires reviewed publication; automated release machinery is not implemented.
Keep the existing preset address unchanged until resolved-policy equivalence and
pin updates have been verified. Roll back consumers by restoring their previous
runner and pin; never move a published tooling tag.

See [implementation status](docs/wip/renovate-adoption/README.md).
