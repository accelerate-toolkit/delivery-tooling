# Repository guidance

Run `make` to discover actions and `make check` to validate changes.
Keep source and examples generic and suitable for public distribution. Keep
credentials, organization schedules, private target inventories and rollout
records in their owning repositories. Do not enable consumer automerge implicitly.

Consumers own their jobs; share release and dependency-update mechanics through
composable actions and CLI interfaces. Do not require APM to use this repository.
Optional APM provisioning belongs to consumer runner execution only.

Use Conventional Commits with a body. Obtain review before committing unless the
user explicitly requests a commit or repository creation and publication.
Do not publish speculative release tags or point consumers at unpublished refs.
