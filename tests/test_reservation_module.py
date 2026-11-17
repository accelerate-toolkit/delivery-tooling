# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Validate and mock-plan the actual extracted backend delivery, without AWS credentials."""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "hashicorp/terraform:1.14.0@sha256:3abcdb56739bf9c61a0290cfd1a2e41ef9c3799c0e6fa7f3c467f883367d3ecb"
spec = importlib.util.spec_from_file_location("package", ROOT / "reservation/package.py")
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)

with tempfile.TemporaryDirectory() as temporary:
    stage = Path(temporary)
    package.package(stage / "artifacts")
    archive = stage / "artifacts/reservation-backend.zip"
    original = archive.read_bytes()
    package.package(stage / "artifacts")
    assert original == archive.read_bytes(), "Module packaging is not reproducible"
    module = stage / "module"
    with zipfile.ZipFile(archive) as bundle:
        assert set(bundle.namelist()) == {"main.tf", "README.md"}
        bundle.extractall(module)
    (module / "test_override.tf").write_text('terraform {\n  required_providers {\n    aws = { source = "hashicorp/aws", version = "6.73.0" }\n  }\n}\n')
    (module / "tests").mkdir()
    (module / "tests/backend.tftest.hcl").write_text('''mock_provider "aws" {}
run "persistent_reservation_backend" {
  command = plan
  variables { table_name = "example-reservations" }
  assert {
    condition = aws_dynamodb_table.reservations.hash_key == "scope" && aws_dynamodb_table.reservations.billing_mode == "PAY_PER_REQUEST"
    error_message = "Reservations need an atomic environment/product key and on-demand capacity."
  }
  assert {
    condition = aws_dynamodb_table.reservations.deletion_protection_enabled && length(aws_dynamodb_table.reservations.ttl) == 0
    error_message = "Expired reservations must not disappear through TTL or accidental table deletion."
  }
  assert {
    condition = aws_dynamodb_table.reservations.point_in_time_recovery[0].enabled && aws_dynamodb_table.reservations.server_side_encryption[0].enabled
    error_message = "Reservation data must have recovery and encryption enabled."
  }
}
''')
    command = ["docker", "run", "--rm", "--user", f"{os.getuid()}:{os.getgid()}", "-v", str(module) + ":/work", "-w", "/work", "-e", "CHECKPOINT_DISABLE=1"]
    if os.environ.get("CODEX_PROXY_CERT"):
        command += ["-v", os.environ["CODEX_PROXY_CERT"] + ":/run/ca.pem:ro", "-e", "SSL_CERT_FILE=/run/ca.pem"]
    for args in (["init", "-backend=false", "-input=false"], ["validate", "-no-color"], ["test", "-no-color"]):
        subprocess.run(command + [IMAGE, *args], check=True)
