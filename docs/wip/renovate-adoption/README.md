# Renovate machinery

Status: local implementation prepared, pending review and publication. Repository
visibility is awaiting the owner's decision. No live adoption is claimed.

Implemented: unchanged preset copy; composite runner with an exact Renovate
version, caller-derived target, optional APM CLI and non-writing preview default.
The public source contains no private adoption inventory or account data.

Local verification on 15 November 2026:

- Renovate 44.151.0 strictly validates the preset and repository configuration.
- The copied preset is byte-identical to the existing compatibility entry point.
- Actionlint 1.7.7 accepts the two workflows and a workflow representation of the
  composite steps; the GitHub Action JSON schema accepts the action metadata.
- Bash syntax checks and input-guard smoke checks pass for valid versions,
  optional APM, missing credentials, floating versions and invalid preview modes.
- Credential-free extraction detects action SHA pins with version comments, Node,
  uv, Renovate's CLI default and validator image. The staged check uses the local
  preset contents; it does not prove remote preset resolution or authenticated
  version lookup. GitHub dependencies report the expected missing-token warning.

No authenticated run, dependency PR, APM installation/lock update or live consumer
migration has been verified for this shared action.

Before the first release:

- Confirm repository visibility and review the source.
- Validate configuration, action metadata, and representative extraction.
- Complete the maintained-repository inventory in the owning private context.
- Publish a verified immutable source release through the approved process.
- Verify native extraction of consumer SHA pins with release-version comments.
- Pilot actual dependency PR creation and required checks, including private
  modules and APM lockfile updates where applicable.
- Replace duplicated runners in reviewed batches, preserving each consumer's
  tool availability, schedules, grouping and merge policy.

Release automation remains outside this initial Renovate implementation. The
broader delivery plan remains in the existing preset repository and is retained
until its full execution handoff exists.
