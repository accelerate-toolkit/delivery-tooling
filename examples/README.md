# Consumer examples

These configurations illustrate the supported contract. The first verified release
is `v0.1.0`, at commit `07f7c9e5703d858742c3de4c93344f69a9d20417`.
Pin each action to that verified commit SHA with a `# v0.1.0` comment so Renovate
can extract the reference. These examples do not migrate any consumer.

- [Source-only](source-only/release.json): one tagged-source stream, no built assets.
- [Application](application/release.json): an independent `app-v` namespace with
  backend, frontend and provenance files. The consumer owns their formats and build.

Run the CLI from the consumer checkout, with TOOLING pointing to an installed,
verified delivery-tooling checkout whose locked dependencies are installed:

```sh
node "$TOOLING/release/cli.mjs" plan --repository example/component --output build/release
# Stop here when the returned release field is false.
# Consumer jobs build/check from the plan's sourceCommit and planned version.
node "$TOOLING/release/cli.mjs" verify --plan build/release/release-plan.json --artifacts dist --output build/release
# Persist original plan, manifest and dist before the privileged job.
node "$TOOLING/release/cli.mjs" publish --plan build/release/release-plan.json --manifest build/release/release-manifest.json --artifacts dist --expected-commit "$SOURCE_COMMIT"
```

Omit `--artifacts dist` for source-only releases. Publication checks the configured
required GitHub checks on SOURCE_COMMIT. Use the explicit source commit from the
trusted workflow/job handoff, not a floating branch name. See the tooling's own
[workflow](../.github/workflows/check.yml) for the separate check, plan and publish
jobs and [release design](../docs/design/releases.md) for recovery and permissions.
