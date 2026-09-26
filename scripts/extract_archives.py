#!/usr/bin/env python3
"""Safely extract all immutable release archives into data/extracted/."""

from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[1]
ARCHIVES = ROOT / "data" / "archives"
DESTINATION = ROOT / "data" / "extracted"


def safe_members(archive: tarfile.TarFile):
    base = DESTINATION.resolve()
    for member in archive.getmembers():
        target = (DESTINATION / member.name).resolve()
        if target != base and base not in target.parents:
            raise RuntimeError(f"Unsafe archive member: {member.name}")
        if member.issym() or member.islnk():
            raise RuntimeError(f"Links are not allowed: {member.name}")
        yield member


def main():
    DESTINATION.mkdir(parents=True, exist_ok=True)
    for path in sorted(ARCHIVES.glob("*.tar.gz")):
        print(f"Extracting {path.name}")
        with tarfile.open(path, "r:gz") as archive:
            archive.extractall(DESTINATION, members=safe_members(archive), filter="data")
    print(f"Extracted archives to {DESTINATION}")


if __name__ == "__main__":
    main()
