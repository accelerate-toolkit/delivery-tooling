# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

spec = importlib.util.spec_from_file_location("cache", Path(__file__).resolve().parents[1] / "examples/cache_delivery_tooling.py")
cache = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cache)


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.files = {name: name.encode() for name in cache.FILES}
        body = io.BytesIO()
        with zipfile.ZipFile(body, "w") as archive:
            archive.writestr("main.tf", "# module")
            archive.writestr("README.md", "Backend")
        self.files["reservation-backend.zip"] = body.getvalue()
        self.manifest = {"schemaVersion": 1, "repository": "accelerate-toolkit/delivery-tooling", "version": "0.2.0",
                         "tag": "v0.2.0", "sourceCommit": "a" * 40,
                         "assets": [{"name": n, "size": len(b), "sha256": hashlib.sha256(b).hexdigest()} for n, b in self.files.items()]}
        self.sign()
        self.calls = []

    def sign(self):
        self.files["release-manifest.json"] = json.dumps(self.manifest).encode()
        self.files["SHA256SUMS"] = "".join(hashlib.sha256(body).hexdigest() + "  " + name + "\n"
                                          for name, body in self.files.items() if name != "SHA256SUMS").encode()

    def fetch(self, url):
        self.calls.append(url)
        return self.files[url.rsplit("/", 1)[1]]

    def test_cached_bytes_reverified_without_network(self):
        path = cache.ensure("0.2.0", self.root, self.fetch)
        count = len(self.calls)
        self.assertEqual(cache.ensure("0.2.0", self.root, self.fetch), path)
        self.assertEqual(len(self.calls), count)
        (path / "reservation.py").write_text("corrupt")
        with self.assertRaises(ValueError):
            cache.ensure("0.2.0", self.root, self.fetch)
        self.assertEqual(len(self.calls), count)

    def test_failed_download_never_publishes_partial_cache(self):
        self.files["reservation.py"] += b"corrupt"
        with self.assertRaises(ValueError):
            cache.ensure("0.2.0", self.root, self.fetch)
        self.assertFalse((self.root / "0.2.0").exists())
        self.assertEqual(list(self.root.iterdir()), [self.root / ".cache.lock"])

    def test_wrong_version_and_inventory_rejected(self):
        for field, value in (("version", "0.1.0"), ("assets", [])):
            previous = self.manifest[field]
            self.manifest[field] = value
            self.sign()
            with self.assertRaises(ValueError):
                cache.ensure("0.2.0", self.root, self.fetch)
            self.manifest[field] = previous

    def test_symlinked_artifact_rejected(self):
        path = cache.ensure("0.2.0", self.root, self.fetch)
        original = path / "reservation.py"
        original.rename(self.root / "original")
        original.symlink_to(self.root / "original")
        with self.assertRaises(ValueError):
            cache.ensure("0.2.0", self.root, self.fetch)

    def test_version_cannot_escape_cache(self):
        for version in ("../v1", "main", "v0.2.0"):
            with self.assertRaises(ValueError):
                cache.ensure(version, self.root, self.fetch)

    def test_modified_extracted_module_rejected(self):
        path = cache.ensure("0.2.0", self.root, self.fetch)
        (path / "backend/main.tf").write_text("changed")
        with self.assertRaises(ValueError):
            cache.ensure("0.2.0", self.root, self.fetch)


if __name__ == "__main__":
    unittest.main()
