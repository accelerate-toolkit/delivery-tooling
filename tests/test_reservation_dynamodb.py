# /// script
# requires-python = ">=3.11"
# dependencies = ["boto3==1.40.70"]
# ///
"""CLI and DynamoDB conditional-write integration in an ephemeral local container."""
import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
import boto3

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "reservation/reservation.py"
IMAGE = "amazon/dynamodb-local:3.3.2@sha256:6ada631ec7aa5fc83446855eb17233e3dad184fec47477e8140c6c569cfe0c86"


class LocalDynamo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.container = subprocess.check_output(["docker", "run", "-d", "--rm", "-p", "127.0.0.1::8000", IMAGE,
                                                 "-jar", "DynamoDBLocal.jar", "-inMemory", "-sharedDb"], text=True).strip()
        cls.addClassCleanup(subprocess.run, ["docker", "stop", cls.container], stdout=subprocess.DEVNULL, check=True)
        port = subprocess.check_output(["docker", "port", cls.container, "8000/tcp"], text=True).strip().split(":")[-1]
        cls.endpoint = "http://127.0.0.1:" + port
        cls.db = boto3.client("dynamodb", endpoint_url=cls.endpoint, region_name="us-east-1",
                             aws_access_key_id="local", aws_secret_access_key="local")
        for attempt in range(60):
            try:
                cls.db.list_tables()
                break
            except Exception:
                if attempt == 59:
                    raise
                time.sleep(0.25)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.table = "reservations-" + uuid.uuid4().hex
        self.db.create_table(TableName=self.table, BillingMode="PAY_PER_REQUEST", KeySchema=[{"AttributeName": "scope", "KeyType": "HASH"}],
                             AttributeDefinitions=[{"AttributeName": "scope", "AttributeType": "S"}])
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("AWS_") and k != "DELIVERY_RESERVATION_CONTEXT"}
        self.env.update(AWS_ACCESS_KEY_ID="local", AWS_SECRET_ACCESS_KEY="local", AWS_CONFIG_FILE="/dev/null",
                        AWS_SHARED_CREDENTIALS_FILE="/dev/null", AWS_EC2_METADATA_DISABLED="true", AWS_ENDPOINT_URL_DYNAMODB=self.endpoint)

    def command(self, action, *extra, product="example"):
        return [sys.executable, str(SCRIPT), action, "--table", self.table, "--region", "us-east-1",
                "--environment", "integration", "--product", product, *extra]

    def cli(self, action, *extra, expected=0, product="example"):
        result = subprocess.run(self.command(action, *extra, product=product), env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, expected, result.stderr)
        return result

    def test_contending_processes_manual_use_and_stale_release(self):
        def acquire(index):
            return subprocess.run(self.command("acquire", "--token-file", str(self.root / str(index))),
                                  env=self.env, capture_output=True, text=True, timeout=30).returncode
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            outcomes = list(pool.map(acquire, range(2)))
        self.assertCountEqual(outcomes, [0, 1])
        owner = self.root / str(outcomes.index(0))
        loser = self.root / str(outcomes.index(1))
        self.cli("release", "--token-file", str(loser), expected=1)
        self.cli("run", "--token-file", str(owner), "--", sys.executable, "-c", "pass")
        self.assertEqual(json.loads(self.cli("status").stdout)["state"], "held")
        self.cli("release", "--token-file", str(owner))
        self.assertFalse(owner.exists())

    def test_nested_run_reuses_owner_and_other_products_are_independent(self):
        nested = self.command("run", "--", sys.executable, "-c", "pass")
        self.cli("run", "--", *nested)
        self.assertEqual(json.loads(self.cli("status").stdout)["state"], "free")
        self.cli("acquire", "--token-file", str(self.root / "manual"))
        self.cli("run", "--", sys.executable, "-c", "pass", product="another")

    def test_nested_target_mismatch_and_failure_stay_blocked(self):
        nested = self.command("run", "--", sys.executable, "-c", "pass", product="another")
        self.cli("run", "--", *nested, expected=1)
        status = json.loads(self.cli("status").stdout)
        self.assertEqual(status["state"], "blocked")
        self.cli("run", "--", sys.executable, "-c", "pass", expected=1)
        self.cli("recover", "--revision", status["revision"], "--reason", "drained", expected=1)
        self.cli("recover", "--revision", status["revision"], "--reason", "drained", "--confirm-drained")
        self.cli("run", "--", sys.executable, "-c", "pass")

    def test_expiry_stops_child_and_keeps_record(self):
        self.cli("run", "--duration", "2s", "--", sys.executable, "-c", "import time; time.sleep(20)", expected=1)
        status = json.loads(self.cli("status").stdout)
        self.assertTrue(status["expired"])
        self.assertEqual(status["state"], "blocked")
        self.cli("run", "--", sys.executable, "-c", "pass", expected=1)

    def test_waiting_execution_starts_only_after_manual_release(self):
        token = self.root / "manual"
        self.cli("acquire", "--token-file", str(token))
        marker = self.root / "started"
        child = subprocess.Popen(self.command("run", "--wait", "15s", "--", sys.executable,
                                  "-c", f"open({str(marker)!r}, 'w').close()"), env=self.env,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            time.sleep(1)
            self.assertFalse(marker.exists())
            self.cli("release", "--token-file", str(token))
            stdout, stderr = child.communicate(timeout=20)
            self.assertEqual(child.returncode, 0, stderr)
            self.assertTrue(marker.exists())
        finally:
            if child.poll() is None:
                child.kill()
                child.wait()


if __name__ == "__main__":
    unittest.main()
