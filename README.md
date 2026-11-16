# Delivery tooling

The public repository contains the initial Renovate preset and runner. Release
planning, artifact verification and publication machinery have published the first
verified source release, [v0.1.0](https://github.com/accelerate-toolkit/delivery-tooling/releases/tag/v0.1.0).
Consumer migration remains pending; see the implementation status below.

Consumers can use the [release CLI and composable actions](docs/design/releases.md)
with [small release configurations](examples/README.md). The self-hosting workflow
provides an explicit check → plan → publish job chain for tagged-source releases.

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
this action. The verified `v0.1.0` source commit is
`07f7c9e5703d858742c3de4c93344f69a9d20417`. The action resolves `run.sh` through `github.action_path`, binding helper
execution to the same action revision rather than the consumer checkout.

For initial onboarding before this repository is published, consumers can use
the existing upstream `renovatebot/github-action` directly. Do not replace working
runners until the shared action has passed a real pilot with the required managers.

## Validation and publication

This repository enables Renovate-managed squash automerge with passing checks
required and `platformAutomerge: false`. Its existing weekly Actions runner remains
in place until hosted-app migration, so green PRs may wait until its next run.
The agreed [hosted dependency update design](https://github.com/accelerate-toolkit/renovate-config/blob/main/docs/design/dependency-updates.md)
separates Monday update creation from subsequent merge runs. The reusable runner
remains available for consumers that choose self-hosting.

With Docker, Go, Node 22+, npm and uv available, run `make`, `make setup`, then
`make check`. Run `make release-plan` for a non-publishing preview. This validates
Renovate configuration, lints workflows and tests runner behavior without bot
credentials. The behavioral tests stub the CLI and check target isolation,
preview defaults, explicit normal runs, private-module environment forwarding,
invalid inputs and failure propagation. They do not contact GitHub.
Validate composite action metadata and perform credential-free dependency extraction before publication.
An authenticated preview and real update PR remain required live acceptance steps.

Use one immutable SemVer stream for this tooling. The self-hosting workflow has
published its first source-only release; see [verification evidence](docs/evidence/first-source-release/README.md).
Its local action invocations bootstrap without an unpublished tooling version.
Keep the existing preset address unchanged until resolved-policy equivalence and
pin updates have been verified. Roll back consumers by restoring their previous
runner and pin; never move a published tooling tag.

See [implementation status](docs/wip/delivery-tooling/README.md).
