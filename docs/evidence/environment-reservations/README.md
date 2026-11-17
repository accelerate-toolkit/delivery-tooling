# Reservation tooling v0.2.0

Published 2026-11-17 at 08:36:48 UTC from
`45132e8c3888784b8c3ce35523d104a131b80c50`:
[v0.2.0](https://github.com/accelerate-toolkit/delivery-tooling/releases/tag/v0.2.0).

[CI run 44046535825](https://github.com/accelerate-toolkit/delivery-tooling/actions/runs/44046535825)
passed configuration/workflow validation, 56 Python/Node tests (including five CLI
and DynamoDB Local cases) and one mocked plan using the extracted backend archive.
The first publication job failed during setup while downloading a GitHub Action.
Local publication from its retained CI artifacts created a matching draft but the
upload request received HTTP 401. Retrying the failed hosted publication job resumed
the same draft and completed successfully without changing source or artifacts.

The release contains the script, backend ZIP, source-bound release plan/manifest
and SHA256SUMS. Consumer bootstrap downloads verified the published version/source,
inventory, sizes and hashes; repeated setup reused verified local caches.

| Delivery | SHA-256 |
| --- | --- |
| reservation.py | `dbfa5d8242c7a0c1eeb4524f9b198685effd7c4ed3ba10bf9e983922eff07717` |
| reservation-backend.zip | `77997b7b2d225881ddbc250011119982062418fdf5438c911e318d70a4f0ce7e` |

Tests cover owner contention, independent products, stale-owner rejection, explicit
extension/recovery, supervised process expiry, nested target checks, bounded waiting,
private token files and corrupt caches. Mocked Terraform verifies persistent keys,
on-demand capacity, encryption, recovery and absence of TTL. These checks do not
prove live AWS IAM, real provider operation draining or production recovery.
