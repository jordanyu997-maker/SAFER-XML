#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RULES_PATH = ROOT / "knowledge" / "sources" / "wcag_rules.json"
INVENTORY_PATH = ROOT / "knowledge" / "sources" / "wcag_22_inventory.json"


def load_json(path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def main():
    parser = argparse.ArgumentParser(description="Show WCAG 2.2 coverage of the local knowledge base.")
    parser.add_argument(
        "--code-related",
        action="store_true",
        help="Only count success criteria that are directly useful for frontend code generation.",
    )
    parser.add_argument(
        "--levels",
        nargs="+",
        choices=["A", "AA", "AAA"],
        default=["A", "AA", "AAA"],
        help="Conformance levels to count. Default: A AA AAA.",
    )
    args = parser.parse_args()

    rules = load_json(RULES_PATH)
    inventory = load_json(INVENTORY_PATH)
    inventory = [item for item in inventory if item["level"] in args.levels]
    if args.code_related:
        inventory = [item for item in inventory if item["code_related"]]

    covered_ids = {rule["id"] for rule in rules}
    expected_ids = {item["id"] for item in inventory}
    covered = [item for item in inventory if item["id"] in covered_ids]
    missing = [item for item in inventory if item["id"] not in covered_ids]

    coverage = len(covered) / len(inventory) * 100 if inventory else 0

    level_scope = "/".join(args.levels)
    scope = f"代码生成强相关 WCAG 2.2 {level_scope}" if args.code_related else f"全部 WCAG 2.2 {level_scope}"
    print(f"范围：{scope}")
    print(f"已覆盖：{len(covered)} / {len(inventory)} ({coverage:.1f}%)")
    print()

    print("已覆盖规则：")
    for item in covered:
        print(f"- {item['id']} {item['name']} ({item['level']})")

    print()
    print("缺失规则：")
    for item in missing:
        print(f"- {item['id']} {item['name']} ({item['level']})")


if __name__ == "__main__":
    main()
