#!/usr/bin/env python3
"""Apply auditable researcher source-review adjudications to formal runs."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.run_android_xml_experiment import write_json  # noqa: E402


def main():
    adjudications = json.loads(
        (ROOT / "experiments/android_xml/source_review_adjudications.json").read_text(
            encoding="utf-8"
        )
    )
    manifest = json.loads(
        (ROOT / "experiments/android_xml/experiment_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    paths = {
        record["experiment_id"]: ROOT / record["result_path"] / "manual_review.json"
        for record in manifest.get("runs", [])
    }
    applied = 0
    for experiment_id, adjudication in adjudications.get("runs", {}).items():
        path = paths.get(experiment_id)
        if path is None or not path.exists():
            raise FileNotFoundError(f"Missing formal review record: {experiment_id}")
        review = json.loads(path.read_text(encoding="utf-8"))
        review["source_review_status"] = adjudication["source_review_status"]
        if adjudication["source_review_status"] == "completed":
            for file_review in review["files"].values():
                file_review["source_review_status"] = "completed"
                for group_name in ("baseline", "proposed"):
                    group = file_review[group_name]
                    if group["unrelated_change_count"] is None:
                        group["unrelated_change_count"] = 0
                    if group["dynamic_semantics_risk_count"] is None:
                        group["dynamic_semantics_risk_count"] = 0
        for xml_file, file_adjudication in adjudication.get("files", {}).items():
            if xml_file not in review["files"]:
                raise KeyError(f"{experiment_id}: unknown XML file {xml_file}")
            file_review = review["files"][xml_file]
            file_review["source_review_status"] = file_adjudication[
                "source_review_status"
            ]
            for group_name in ("baseline", "proposed"):
                metrics = file_adjudication.get(group_name)
                if metrics:
                    file_review[group_name].update(metrics)
        write_json(path, review)
        applied += 1
    print(f"Applied {applied} source-review adjudications.")


if __name__ == "__main__":
    main()
