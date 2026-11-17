# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Build deterministic reservation delivery artifacts from this checkout."""
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def package(destination):
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / "reservation/reservation.py", destination / "reservation.py")
    with zipfile.ZipFile(destination / "reservation-backend.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for name in ("main.tf", "README.md"):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, (ROOT / "terraform/reservation-backend" / name).read_bytes())


if __name__ == "__main__":
    package(ROOT / "build/release/artifacts")
