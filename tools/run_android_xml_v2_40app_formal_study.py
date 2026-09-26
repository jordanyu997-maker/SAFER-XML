#!/usr/bin/env python3
"""Run the registered V2.3 40-App multi-model formal comparison."""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import prepare_android_xml_v2_40app_formal_study as prepared  # noqa: E402
from tools import run_android_xml_v2_formal_study as runner  # noqa: E402


def configure_runner() -> None:
    prepared.configure_formal_preparer()
    runner.prepared = prepared
    runner.PROTOCOL_PATH = prepared.PROTOCOL_PATH
    runner.PREPARED_ROOT = prepared.DEFAULT_OUTPUT
    runner.FORMAL_MANIFEST = runner.PREPARED_ROOT / "formal_manifest.json"
    runner.DEFAULT_OUTPUT = prepared.FORMAL_RUN_ROOT
    runner.GROUPS = prepared.GROUPS


def main() -> None:
    configure_runner()
    runner.main()


if __name__ == "__main__":
    main()
