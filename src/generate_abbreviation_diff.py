import argparse
import csv
import sys
from pathlib import Path

# Align project path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.config import CATEGORY_OUTPUT, DESCRIPTION_OUTPUT, MASTER_OUTPUT
from utils.json_utils import entity_id, read_json


def load_original_abbreviations(csv_path: Path) -> dict[str, dict]:
    """Parse Indication_Oncology(in).csv and group unique original abbreviations by entity_id."""
    entities: dict[str, dict] = {}
    
    with csv_path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            category = str(row.get("category", "")).strip()
            description = str(row.get("description_2", row.get("description", ""))).strip()
            if not category or not description:
                continue
            
            key = entity_id(category, description)
            if key not in entities:
                entities[key] = {
                    "category": category,
                    "description_2": description,
                    "abbreviations": [],
                    "seen_lower": set()
                }
            
            # Parse pipe-separated abbreviations string
            raw_abbrevs = str(row.get("abbreviations", ""))
            for item in raw_abbrevs.split("|"):
                cleaned = item.strip()
                normalized = cleaned.casefold()
                if cleaned and normalized not in entities[key]["seen_lower"]:
                    entities[key]["seen_lower"].add(normalized)
                    entities[key]["abbreviations"].append(cleaned)
                    
    return entities


def generate_difference_report(
    indication_csv: Path,
    category_json: Path,
    description_json: Path,
    master_json: Path,
    output_csv: Path
) -> None:
    # 1. Load original indication data
    orig_data = load_original_abbreviations(indication_csv)

    # 2. Load generated abbreviation tables
    cat_by_id = {r["category_description2"]: r.get("abbreviations", []) for r in read_json(category_json)}
    desc_by_id = {r["category_description2"]: r.get("abbreviations", []) for r in read_json(description_json)}
    master_by_id = {r["category_description2"]: r.get("final_abbreviations", []) for r in read_json(master_json)}

    # 3. Gather all unique entity keys
    all_keys = sorted(set(orig_data.keys()) | set(cat_by_id.keys()) | set(desc_by_id.keys()) | set(master_by_id.keys()))

    fieldnames = [
        "category_description2",
        "category",
        "description_2",
        "category_abbreviations",
        "descriptive_abbreviations",
        "master_abbreviations",
        "original_indication_oncology_abbreviations",
        "difference"
    ]

    rows = []
    for key in all_keys:
        orig_info = orig_data.get(key, {})
        cat_abbrevs = cat_by_id.get(key, [])
        desc_abbrevs = desc_by_id.get(key, [])
        master_abbrevs = master_by_id.get(key, [])
        orig_abbrevs = orig_info.get("abbreviations", [])

        # Build case-insensitive set for master abbreviations
        master_lower_set = {m.casefold() for m in master_abbrevs if m != "404"}

        # Find items in original indication oncology NOT present in generated master
        diff_items = [
            term for term in orig_abbrevs
            if term.casefold() not in master_lower_set
        ]

        # Determine category and description labels
        category_label = orig_info.get("category", "")
        desc_label = orig_info.get("description_2", "")

        rows.append({
            "category_description2": key,
            "category": category_label,
            "description_2": desc_label,
            "category_abbreviations": " | ".join(cat_abbrevs),
            "descriptive_abbreviations": " | ".join(desc_abbrevs),
            "master_abbreviations": " | ".join(master_abbrevs),
            "original_indication_oncology_abbreviations": " | ".join(orig_abbrevs),
            "difference": " | ".join(diff_items)
        })

    # Write comparison CSV output
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Comparison completed. Wrote {len(rows):,} rows to {output_csv.resolve()}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate abbreviation difference file for comparison.")
    parser.add_argument("--csv-input", default="data/Indication_Oncology(in).csv", help="Path to original Indication Oncology CSV")
    parser.add_argument("--category-json", default=str(CATEGORY_OUTPUT), help="Path to category abbreviations JSON")
    parser.add_argument("--description-json", default=str(DESCRIPTION_OUTPUT), help="Path to description abbreviations JSON")
    parser.add_argument("--master-json", default=str(MASTER_OUTPUT), help="Path to master abbreviations JSON")
    parser.add_argument("--output", default="data/abbreviation_difference.csv", help="Output comparison CSV path")
    args = parser.parse_args()

    generate_difference_report(
        indication_csv=Path(args.csv_input),
        category_json=Path(args.category_json),
        description_json=Path(args.description_json),
        master_json=Path(args.master_json),
        output_csv=Path(args.output)
    )


if __name__ == "__main__":
    main()