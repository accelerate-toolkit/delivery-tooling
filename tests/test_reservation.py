# /// script
# requires-python = ">=3.11"
# dependencies = ["boto3==1.40.70"]
# ///
"""Lease state, contention, stale-owner and real foreground-process checks."""
import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest

spec = importlib.util.spec_from_file_location("reservation", Path(__file__).resolve().parents[1] / "reservation/reservation.py")
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


class Memory:
    def __init__(self):
        self.items = {}
        self.lock = threading.Lock()

    def read(self, key):
        with self.lock:
            return copy.deepcopy(self.items.get(key))

    def replace(self, key, before, after):
        with self.lock:
            current = self.items.get(key)
            if (current or {}).get("revision") != (before or {}).get("revision"):
                raise r.ReservationError("Concurrent change")
            self.items[key] = copy.deepcopy(after)


class LeaseTests(unittest.TestCase):
    def setUp(self):
        self.store = Memory()
        self.now = 1000
        self.lease = r.Lease(self.store, "integration/example", lambda: self.now)

    def test_exclusive_key_and_independent_products(self):
        self.lease.acquire("a", 30)
        with self.assertRaises(r.ReservationError):
            self.lease.acquire("b", 30)
        r.Lease(self.store, "integration/other").acquire("b", 30)
        r.Lease(self.store, "staging/example").acquire("b", 30)

    def test_contenders_cannot_both_acquire(self):
        barrier = threading.Barrier(2)
        original = self.store.read
        def read(key):
            value = original(key)
            barrier.wait()
            return value
        self.store.read = read
        results = []
        def acquire(token):
            try:
                self.lease.acquire(token, 30)
                results.append("acquired")
            except r.ReservationError:
                results.append("rejected")
        threads = [threading.Thread(target=acquire, args=(str(i),)) for i in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertCountEqual(results, ["acquired", "rejected"])

    def test_expiry_never_implicitly_admits_another_writer(self):
        self.lease.acquire("a", 30)
        self.now += 31
        for action in (lambda: self.lease.acquire("b", 30), lambda: self.lease.extend("a", 30),
                       lambda: self.lease.release("a"), lambda: self.lease.begin("a")):
            with self.assertRaises(r.ReservationError):
                action()
        record = self.store.read(self.lease.key)
        self.lease.recover(record["revision"], "operator verified old runner and cloud operations stopped")
        self.lease.acquire("b", 30)
        with self.assertRaises(r.ReservationError):
            self.lease.release("a")

    def test_recovery_rejects_stale_revision_and_live_owner(self):
        record = self.lease.acquire("a", 30)
        with self.assertRaises(r.ReservationError):
            self.lease.recover(record["revision"], "not drained")
        self.lease.extend("a", 30)
        self.now += 61
        with self.assertRaises(r.ReservationError):
            self.lease.recover(record["revision"], "stale observation")

    def test_commands_serialize_within_manual_reservation(self):
        self.lease.acquire("a", 30)
        operation = self.lease.begin("a")["operation"]
        for action in (lambda: self.lease.release("a"), lambda: self.lease.begin("a")):
            with self.assertRaises(r.ReservationError):
                action()
        self.lease.finish("a", operation)
        next_operation = self.lease.begin("a")["operation"]
        self.assertNotEqual(operation, next_operation)
        with self.assertRaises(r.ReservationError):
            self.lease.finish("a", operation)

    def test_checks_do_not_renew_and_extension_is_explicit(self):
        record = self.lease.acquire("a", 30)
        operation = self.lease.begin("a")["operation"]
        self.now += 10
        self.assertEqual(self.lease.running("a", operation)["expires_at"], record["expires_at"])
        self.assertEqual(self.lease.extend("a", 60)["expires_at"], 1090)

    def test_failure_blocks_until_explicit_recovery(self):
        self.lease.acquire("a", 30)
        operation = self.lease.begin("a")["operation"]
        self.lease.block("a", operation, "failed")
        with self.assertRaises(r.ReservationError):
            self.lease.release("a")
        record = self.store.read(self.lease.key)
        self.lease.recover(record["revision"], "reviewed partial apply")
        self.lease.acquire("b", 30)
        self.lease.block("a", operation, "late old writer")
        self.assertEqual(self.lease.owned("b")["state"], "held")

    def test_owner_token_is_not_stored_in_backend(self):
        record = self.lease.acquire("private-owner-token", 30)
        self.assertNotIn("private-owner-token", json.dumps(record))

    def test_expired_owner_cannot_launch_process(self):
        self.lease.acquire("a", 30)
        operation = self.lease.begin("a")["operation"]
        self.now += 31
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "launched"
            with self.assertRaises(r.ReservationError):
                r.supervise(self.lease, "a", operation, [sys.executable, "-c", f"open({str(path)!r}, 'w').close()"], {})
            self.assertFalse(path.exists())

    def test_running_process_is_stopped_when_lease_expires(self):
        lease = r.Lease(self.store, "integration/process")
        lease.acquire("a", 2)
        operation = lease.begin("a")["operation"]
        start = time.monotonic()
        with self.assertRaises(r.ReservationError):
            r.supervise(lease, "a", operation, [sys.executable, "-c", "import time; time.sleep(20)"], {}, poll=0.05)
        self.assertLess(time.monotonic() - start, 5)

    def test_success_and_failure_exit_codes(self):
        self.lease.acquire("a", 30)
        operation = self.lease.begin("a")["operation"]
        for code in (0, 7):
            self.assertEqual(r.supervise(self.lease, "a", operation,
                             [sys.executable, "-c", f"raise SystemExit({code})"], {}), code)

    def test_invalid_keys_and_durations(self):
        for value in ("../prod", "product/env", "", "A", "x" * 64):
            with self.assertRaises(r.ReservationError):
                r.scope("integration", value)
        self.assertEqual(r.duration("1d"), 86400)
        for value in ("0m", "-1s", "forever", "8d"):
            with self.assertRaises(argparse.ArgumentTypeError):
                r.duration(value)

    def test_private_token_file_cannot_overwrite_another_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "token.json"
            r.private_write(path, {"token": "a"})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                r.private_write(path, {"token": "b"})


class DynamoTests(unittest.TestCase):
    def test_transport_uses_strong_reads_and_conditional_writes(self):
        import boto3
        from botocore.stub import Stubber
        table = boto3.resource("dynamodb", region_name="us-east-1", aws_access_key_id="test",
                               aws_secret_access_key="test").Table("reservations")
        store = r.DynamoStore(table)
        with Stubber(table.meta.client) as stub:
            stub.add_response("get_item", {}, {"TableName": "reservations", "Key": {"scope": "integration/example"}, "ConsistentRead": True})
            self.assertIsNone(store.read("integration/example"))
            expected = {"TableName": "reservations", "Item": {"scope": "integration/example", "revision": "new"},
                        "ConditionExpression": "revision = :revision", "ExpressionAttributeValues": {":revision": "old"}}
            stub.add_client_error("put_item", "ConditionalCheckFailedException", expected_params=expected)
            with self.assertRaises(r.ReservationError):
                store.replace("integration/example", {"revision": "old"}, {"revision": "new"})
            stub.assert_no_pending_responses()


if __name__ == "__main__":
    unittest.main()
