# /// script
# requires-python = ">=3.11"
# dependencies = ["boto3==1.40.70"]
# ///
"""Reserve an environment/product pair; supervise foreground commands under that lease."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
import uuid

CONTEXT = "DELIVERY_RESERVATION_CONTEXT"


class ReservationError(RuntimeError):
    pass


def scope(environment, product):
    for value in (environment, product):
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", value):
            raise ReservationError("Environment and product must be lowercase names, up to 63 characters")
    return environment + "/" + product


def duration(value):
    match = re.fullmatch(r"([1-9][0-9]*)(s|m|h|d)", value)
    if not match:
        raise argparse.ArgumentTypeError("Use a positive duration such as 30m or 1d")
    seconds = int(match[1]) * {"s": 1, "m": 60, "h": 3600, "d": 86400}[match[2]]
    if seconds > 7 * 86400:
        raise argparse.ArgumentTypeError("Maximum reservation duration is seven days")
    return seconds


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


class DynamoStore:
    """Strong reads and conditional replacement. Records never expire through DynamoDB TTL."""
    def __init__(self, table):
        self.table = table

    def read(self, key):
        return self.table.get_item(Key={"scope": key}, ConsistentRead=True).get("Item")

    def replace(self, key, before, after):
        options = {"Item": dict(after, scope=key)}
        if before is None:
            options["ConditionExpression"] = "attribute_not_exists(#scope)"
            options["ExpressionAttributeNames"] = {"#scope": "scope"}
        else:
            options["ConditionExpression"] = "revision = :revision"
            options["ExpressionAttributeValues"] = {":revision": before["revision"]}
        try:
            self.table.put_item(**options)
        except Exception as error:
            if getattr(error, "response", {}).get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                raise ReservationError("Reservation changed concurrently; inspect status before retrying") from None
            raise


class Lease:
    def __init__(self, store, key, clock=time.time):
        self.store, self.key, self.clock = store, key, clock

    def change(self, before, **updates):
        after = dict(before or {}, **updates, revision=uuid.uuid4().hex, updated_at=int(self.clock()))
        self.store.replace(self.key, before, after)
        return after

    def acquire(self, token, seconds):
        before = self.store.read(self.key)
        if before and before["state"] != "free":
            raise ReservationError("Environment/product is reserved or needs recovery (including expired reservations)")
        return self.change(before, state="held", owner=token_hash(token), expires_at=int(self.clock()) + seconds,
                           operation="", reason="", acquired_at=int(self.clock()))

    def owned(self, token, states=("held", "running")):
        before = self.store.read(self.key)
        if not before or before.get("owner") != token_hash(token) or before["state"] not in states:
            raise ReservationError("Reservation ownership/state does not permit this operation")
        if before["expires_at"] <= self.clock():
            raise ReservationError("Reservation expired; reconcile outstanding work before recovery")
        return before

    def extend(self, token, seconds):
        before = self.owned(token)
        return self.change(before, expires_at=int(before["expires_at"]) + seconds)

    def release(self, token):
        return self.change(self.owned(token, ("held",)), state="free", owner="", operation="")

    def begin(self, token):
        return self.change(self.owned(token, ("held",)), state="running", operation=uuid.uuid4().hex)

    def running(self, token, operation):
        before = self.owned(token, ("running",))
        if before["operation"] != operation:
            raise ReservationError("Reservation operation changed")
        return before

    def finish(self, token, operation):
        return self.change(self.running(token, operation), state="held", operation="")

    def block(self, token, operation, reason):
        before = self.store.read(self.key)
        if before and before.get("owner") == token_hash(token) and before.get("operation") == operation:
            self.change(before, state="blocked", reason=reason)

    def recover(self, revision, reason):
        before = self.store.read(self.key)
        if not before or before["revision"] != revision or before["state"] == "free":
            raise ReservationError("Recovery requires the exact current occupied revision")
        if before["state"] != "blocked" and before["expires_at"] > self.clock():
            raise ReservationError("An unexpired reservation cannot be recovered")
        if not reason.strip():
            raise ReservationError("Recovery requires an audit reason")
        return self.change(before, state="free", owner="", operation="", reason=reason)


def stop(child):
    """Terminate the foreground process group. Remote work still requires reconciliation."""
    try:
        os.killpg(child.pid, signal.SIGTERM)
        child.wait(timeout=10)
    except subprocess.TimeoutExpired:
        os.killpg(child.pid, signal.SIGKILL)
        child.wait()
    except ProcessLookupError:
        child.wait()


def supervise(lease, token, operation, command, context, poll=2):
    lease.running(token, operation)  # Do not launch a command using an expired owner.
    env = dict(os.environ, **{CONTEXT: json.dumps(context)})
    child = subprocess.Popen(command, env=env, start_new_session=True)
    try:
        while True:
            record = lease.running(token, operation)
            # Bound each wait by the remaining lease. Extensions are explicit backend changes.
            wait = max(0.01, min(poll, float(record["expires_at"]) - lease.clock()))
            try:
                result = child.wait(timeout=wait)
            except subprocess.TimeoutExpired:
                continue
            lease.running(token, operation)
            return result
    except BaseException:
        stop(child)
        raise


def private_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as output:
        json.dump(data, output)


def acquire_wait(lease, token, seconds, wait):
    deadline = time.monotonic() + wait
    while True:
        try:
            return lease.acquire(token, seconds)
        except ReservationError:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise
            time.sleep(min(2, remaining))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["acquire", "status", "extend", "release", "run", "check", "recover"])
    parser.add_argument("--table", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--profile")
    parser.add_argument("--environment", required=True)
    parser.add_argument("--product", required=True)
    parser.add_argument("--duration", type=duration, default=1800)
    parser.add_argument("--wait", type=duration, default=0, help="Bounded acquisition wait, e.g. 30m; default fail immediately")
    parser.add_argument("--token-file", type=Path)
    parser.add_argument("--revision")
    parser.add_argument("--reason", default="")
    parser.add_argument("--confirm-drained", action="store_true")
    # Split at -- so options following the action remain argparse options.
    argv = sys.argv[1:]
    split = argv.index("--") if "--" in argv else len(argv)
    args = parser.parse_args(argv[:split])
    command = argv[split + 1:]
    if (args.action == "run") != bool(command):
        parser.error("Only run accepts a required command after --")
    import boto3
    from botocore.config import Config
    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    resource = session.resource("dynamodb", config=Config(connect_timeout=3, read_timeout=3,
                               retries={"total_max_attempts": 2, "mode": "standard"}))
    # Resolve the table ARN: inherited tokens cannot silently cross accounts/regions/tables.
    table = resource.Table(args.table)
    target = {"table": table.table_arn, "scope": scope(args.environment, args.product)}
    lease = Lease(DynamoStore(table), target["scope"])
    if args.action == "status":
        record = lease.store.read(lease.key)
        if record:
            record = {k: v for k, v in record.items() if k != "owner"}
            record["expired"] = record["state"] != "free" and record["expires_at"] <= time.time()
        print(json.dumps(record, default=int, indent=2))
        return 0
    if args.action == "recover":
        if not args.confirm_drained:
            raise ReservationError("Confirm all previous processes AND cloud operations are drained before recovery")
        lease.recover(args.revision, args.reason)
        return 0
    inherited = json.loads(os.environ[CONTEXT]) if os.environ.get(CONTEXT) else None
    if inherited and (inherited.get("target") != target or args.token_file):
        raise ReservationError("Nested reservation target differs, or a token file overrides inherited ownership")
    receipt = None
    if args.action == "acquire":
        if inherited or not args.token_file:
            raise ReservationError("Manual acquisition requires a new token file and no inherited execution")
        token = uuid.uuid4().hex + uuid.uuid4().hex
        receipt = {"target": target, "token": token}
        # Persist before acquiring: an uncertain network response must not lose the owner token.
        private_write(args.token_file, receipt)
        acquire_wait(lease, token, args.duration, args.wait)
        print("Reserved; retain the private token file until release or recovery.")
        return 0
    if args.token_file:
        receipt = json.loads(args.token_file.read_text())
        if receipt.get("target") != target:
            raise ReservationError("Token file is for another reservation target")
    token = (inherited or receipt or {}).get("token")
    if args.action in ("check", "extend", "release"):
        if not token:
            raise ReservationError("Supply a token file or inherited reservation")
        if args.action == "check":
            lease.owned(token)
        elif args.action == "extend":
            lease.extend(token, args.duration)
        else:
            if inherited:
                raise ReservationError("Only the outer owner can release an executing reservation")
            lease.release(token)
            if args.token_file:
                args.token_file.unlink()
        return 0
    automatic = not (inherited or receipt)
    if automatic:
        token = uuid.uuid4().hex + uuid.uuid4().hex
        acquire_wait(lease, token, args.duration, args.wait)
    operation = inherited["operation"] if inherited else lease.begin(token)["operation"]
    context = {"target": target, "token": token, "operation": operation}
    try:
        result = supervise(lease, token, operation, command, context)
        if result:
            lease.block(token, operation, "Command failed; reconcile before recovery")
            return result if result > 0 else 128 - result
        if not inherited:
            lease.finish(token, operation)
            if automatic:
                lease.release(token)
        return 0
    except BaseException:
        lease.block(token, operation, "Interrupted, expired or backend unavailable; reconcile before recovery")
        raise


if __name__ == "__main__":
    def interrupted(signum, frame):
        raise ReservationError("Execution interrupted")
    signal.signal(signal.SIGTERM, interrupted)
    try:
        sys.exit(main())
    except (ReservationError, KeyboardInterrupt) as error:
        print(str(error) or "Interrupted; inspect reservation status", file=sys.stderr)
        sys.exit(1)
