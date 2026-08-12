import argparse
import csv
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.config import CANONICAL_INPUT
from utils.json_utils import entity_id, read_json, write_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Create canonical category/description JSON entities.")
    parser.add_argument("--input", required=True, help="Categorized ICD CSV or JSON file")
    parser.add_argument("--output", default=str(CANONICAL_INPUT))
    args = parser.parse_args()
    path = Path(args.input)
    if path.suffix.casefold() == ".json":
        rows = read_json(path)
    else:
        with path.open(encoding="utf-8-sig", newline="") as file:
            rows = list(csv.DictReader(file))
    entities: dict[str, dict[str, str]] = {}
    for row in rows:
        category = str(row.get("category", row.get("Category", ""))).strip()
        description = str(row.get("description_2", row.get("description", ""))).strip()
        if not category or not description:
            continue
        key = entity_id(category, description)
        entities[key] = {"category_description2": key, "category": category, "description_2": description}
    write_json(list(entities.values()), Path(args.output))
    print(f"Wrote {len(entities):,} canonical entities to {Path(args.output).resolve()}")


if __name__ == "__main__":
    main()
