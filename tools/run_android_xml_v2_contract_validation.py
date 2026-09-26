#!/usr/bin/env python3
"""Run the pre-registered V2.1 Development contract validation."""
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import run_android_xml_v2_rag_experiment as runner
from tools.android_xml_contract_v2_1 import (
    CONTRACT_VERSION,
    evaluate_and_commit_candidate,
)
from tools.run_android_xml_rag_pilot import recorded_path, sha256_file


PROTOCOL_PATH = (
    ROOT
    / "experiments/android_xml_v2_rag/contract_v2_1/protocol_v2_1.json"
)
DEFAULT_OUTPUT = ROOT / "experiments/android_xml_v2_rag/contract_v2_1/matrix"
ORIGINAL_IMPLEMENTATION_HASHES = runner.implementation_hashes


def v2_1_implementation_hashes():
    hashes = ORIGINAL_IMPLEMENTATION_HASHES()
    extension = ROOT / "tools/android_xml_contract_v2_1.py"
    hashes.update({
        "contract_validation_runner": {
            "path": recorded_path(Path(__file__).resolve()),
            "sha256": sha256_file(Path(__file__).resolve()),
        },
        "operation_contract_extension": {
            "path": recorded_path(extension),
            "sha256": sha256_file(extension),
            "version": CONTRACT_VERSION,
        },
    })
    return hashes


def configure_runner():
    runner.PROTOCOL_PATH = PROTOCOL_PATH
    runner.RAG_TOP_K_VALUES = (2,)
    runner.CONDITIONS = ("no_rag", "rag_topk2")
    runner.evaluate_and_commit_candidate = evaluate_and_commit_candidate
    runner.implementation_hashes = v2_1_implementation_hashes


def main():
    configure_runner()
    if "--output" not in sys.argv:
        sys.argv.extend(["--output", str(DEFAULT_OUTPUT)])
    runner.main()


if __name__ == "__main__":
    main()
