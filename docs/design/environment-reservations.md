# Environment reservations

The standalone `reservation.py` delivery runs through `uv run --script` with pinned
inline boto3 dependencies. Infrastructure deploys the shared DynamoDB module;
consumers invoke the script inside Make targets. There is no hosted application
service and no GitHub Actions-specific ownership model.

## Identity and lifecycle

The key is **environment/product**: `integration/example-product`. Components of
that product use the same key. Another product is independent in the same environment.
If different products share mutable resources, model that contention explicitly;
different keys cannot protect the same mutable resource. Table ARN binds ownership
to the AWS account, region and table. The client resolves it before using tokens.

Atomic conditional writes and strongly consistent reads protect acquisition and
updates. Every update creates a new revision. Unique owner tokens are hashed in the
backend and passed only through private token files or inherited process environment.
Do not put tokens in command arguments, logs or source control. Consumers choose
duration (30m by default, maximum seven days). Extension adds a stated duration to
the current deadline; status/check calls never extend it. Hosts require synchronized
UTC clocks. This is cooperative execution coordination, not an AWS authorization
boundary: a client bypassing the runner can still use its AWS credentials.

Records transition `free -> held -> running -> held -> free`. Failures become
`blocked`. Expired records of any occupied state remain occupied. No automatic
takeover or DynamoDB TTL is used. A killed process cannot remove its reservation.
Recovery needs the exact observed revision, an audit reason and an explicit
confirmation that earlier processes **and cloud operations** are drained/reconciled.
Live unexpired owners cannot be recovered unless already blocked. Backend errors
stop command admission; uncertain writes require status inspection, never blind
assumptions of success. Status reports expiry separately from stored state.

`run` supervises a foreground process group, checks ownership every two seconds and
stops it on expiry, ownership loss, interruption or backend failure. AWS request
timeouts/retries can delay detection; this is not instantaneous fencing. It leaves
the key occupied on error even when the local child has stopped. Commands must wait
for their work, not daemonize or submit unattended remote jobs and report success.
The script cannot cancel already accepted AWS operations. Operator recovery is the
first implementation's explicit protection against stale cloud writes.

Nested Make invocations inherit and validate the same target/token/operation. They
do not reacquire or release the outer reservation. A different target is rejected.
Separate `run` calls using a manual token serialize through the running state.
An outer successful invocation releases its automatic reservation; manual ownership
remains held between commands for plan review, evidence collection and exploration.

## Local and CI consumption

Copy the small [cache bootstrap](../../examples/cache_delivery_tooling.py) into the
consumer's tooling setup. Pin an actually published version in its Makefile, and
let Renovate update that value. The [Make include](../../examples/delivery.mk)
provides setup and operator targets; prefix cloud recipes with `$(RESERVATION_RUN)`
and depend on `delivery-tools`. Nested calls validate inherited ownership. Cloud
runners can call `make reservation-check` before cloud access to reject accidental
direct execution. The bootstrap downloads `reservation.py`,
`reservation-backend.zip`, `release-manifest.json` and `SHA256SUMS` over HTTPS into
an ignored `.tools/delivery-tooling/<version>/` directory. It verifies source/version,
inventory, sizes and hashes before atomic installation. Cached bytes are rechecked
on every use without network access. Corruption fails closed; remove the affected
cache directory deliberately to refetch. Cache setup uses a local filesystem lock;
that lock has no role in cross-machine environment coordination.
The verified module is extracted under the version directory's `backend/` folder;
subsequent setup checks those extracted bytes against the archive as well.

Checksums and unsigned manifest trust the GitHub release publisher; they are not
independent provenance attestations. Only tooling files are cached. Reservation
state always comes from DynamoDB. Linux/macOS with Python 3.11+, uv and foreground
POSIX processes are supported; Windows is not supported by this first version.

```sh
uv run --script .tools/delivery-tooling/VERSION/reservation.py run \
  --table delivery-reservations --region eu-west-2 \
  --environment integration --product example-product --duration 30m \
  -- make qualify-reserved
```

For manual work, use `acquire --token-file .private/reservation.json --duration 1d`
with the same target options. Supply that file to `run`, `check`, `extend` or
`release`. Acquisition never overwrites an existing file, including after an
uncertain response: inspect status before removing or reusing any ownership file.
An existing reservation fails immediately by default. CI can use `--wait 30m` for
bounded acquisition retries. It waits for release or explicit recovery, including
after expiry, and never replaces an occupied record. Waiting is not FIFO scheduling;
the first successful conditional acquisition wins.

For recovery, inspect `status`, drain/reconcile old work, then invoke `recover`
with `--revision <observed revision> --reason <audit reason> --confirm-drained`.
The retained record keeps the most recent recovery reason; use CloudTrail and the
consumer's evidence records for durable audit history.
