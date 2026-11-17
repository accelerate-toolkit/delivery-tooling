# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Bootstrap a pinned public delivery-tooling release into a verified local cache."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import tempfile
import urllib.request
import zipfile

FILES = ("reservation.py", "reservation-backend.zip")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(directory, version):
    manifest = json.loads((directory / "release-manifest.json").read_text())
    if (manifest.get("schemaVersion") != 1 or manifest.get("repository") != "accelerate-toolkit/delivery-tooling"
            or manifest.get("version") != version or manifest.get("tag") != "v" + version
            or not re.fullmatch(r"[a-f0-9]{40}", manifest.get("sourceCommit", ""))):
        raise ValueError("Release manifest does not match the tooling pin")
    entries = {}
    for line in (directory / "SHA256SUMS").read_text().splitlines():
        value, name = line.split(maxsplit=1)
        if name in entries or not re.fullmatch(r"[a-f0-9]{64}", value) or Path(name).name != name:
            raise ValueError("Invalid release checksums")
        entries[name] = value
    for name in (*FILES, "release-manifest.json"):
        if name not in entries or (directory / name).is_symlink() or digest(directory / name) != entries[name]:
            raise ValueError("Tooling cache checksum mismatch: " + name)
    assets = manifest.get("assets", [])
    if len(assets) != len(FILES) or {a["name"] for a in assets} != set(FILES):
        raise ValueError("Unexpected tooling inventory")
    for asset in assets:
        path = directory / asset["name"]
        if asset["sha256"] != entries[asset["name"]] or asset["size"] != path.stat().st_size:
            raise ValueError("Tooling manifest hash/size mismatch")
    return directory


def module(directory):
    """Extract only the reviewed flat module layout; reject a modified extracted cache."""
    destination = directory / "backend"
    with zipfile.ZipFile(directory / "reservation-backend.zip") as archive:
        if sorted(archive.namelist()) != ["README.md", "main.tf"]:
            raise ValueError("Unexpected backend module entries")
        if destination.exists():
            if destination.is_symlink() or sorted(p.name for p in destination.iterdir()) != ["README.md", "main.tf"]:
                raise ValueError("Modified backend module cache")
            for name in archive.namelist():
                path = destination / name
                if path.is_symlink() or path.read_bytes() != archive.read(name):
                    raise ValueError("Modified backend module cache")
        else:
            destination.mkdir()
            for name in archive.namelist():
                info = archive.getinfo(name)
                if info.file_size > 1024 * 1024 or (info.external_attr >> 16) & 0o170000 not in (0, 0o100000):
                    raise ValueError("Invalid backend module entry")
                (destination / name).write_bytes(archive.read(name))


def ensure(version, root, fetch=None):
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise ValueError("Pin an exact stable delivery-tooling version")
    root.mkdir(parents=True, exist_ok=True)
    destination = root / version
    with (root / ".cache.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if destination.exists():
            verify(destination, version)
            module(destination)
            return destination
        with tempfile.TemporaryDirectory(dir=root, prefix="download-") as temporary:
            stage = Path(temporary) / version
            stage.mkdir()
            for name in (*FILES, "release-manifest.json", "SHA256SUMS"):
                url = f"https://github.com/accelerate-toolkit/delivery-tooling/releases/download/v{version}/{name}"
                if fetch:
                    body = fetch(url)
                else:
                    with urllib.request.urlopen(url, timeout=60) as response:
                        body = response.read(16 * 1024 * 1024 + 1)
                if len(body) > 16 * 1024 * 1024:
                    raise ValueError("Tooling asset exceeds download size limit")
                (stage / name).write_bytes(body)
            verify(stage, version)
            module(stage)
            stage.rename(destination)
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--cache", type=Path, default=Path(".tools/delivery-tooling"))
    args = parser.parse_args()
    print(ensure(args.version, args.cache))
