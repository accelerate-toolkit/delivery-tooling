# First source release

Verified on 15 November 2026.

The [self-hosting workflow](https://github.com/accelerate-toolkit/delivery-tooling/actions/runs/43749715169)
completed its check, plan and publish jobs successfully and published
[v0.1.0](https://github.com/accelerate-toolkit/delivery-tooling/releases/tag/v0.1.0)
from `07f7c9e5703d858742c3de4c93344f69a9d20417`.

An independent download confirmed:

- The release is published, not a draft.
- Its tag, release target, plan and manifest all identify the exact checked source.
- The complete source-only asset set is `release-plan.json`,
  `release-manifest.json` and `SHA256SUMS`.
- Both recorded file checksums match the downloaded bytes.
- The manifest references the downloaded plan's digest and declares no built
  application artifacts, as required by the source-only configuration.

The check job ran the configuration/workflow checks, five Renovate runner tests
and 26 release tests. The local release suite also passed on pinned Node 24.21.0.

This proves the first live tagged-source publication and metadata retrieval. It
does not prove application packaging, signed provenance validation, live recovery
from an interrupted upload, consumer adoption or release-immutability account
settings. Those remain separate rollout acceptance checks.
