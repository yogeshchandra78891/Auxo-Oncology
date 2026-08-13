import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.config import CATEGORY_OUTPUT, DESCRIPTION_OUTPUT, LLM_OUTPUT, MASTER_OUTPUT
from utils.json_utils import read_json, write_json


def by_id(records):
    return {record["category_description2"]: record for record in records}


def final_abbreviations(*sources):
    """Combine source lists in order, removing case-insensitive duplicates and 404."""
    combined = []
    seen = set()
    for source in sources:
        for value in source:
            abbreviation = str(value).strip()
            key = abbreviation.casefold()
            if not abbreviation or key == "404" or key in seen:
                continue
            seen.add(key)
            combined.append(abbreviation)
    return combined if combined else ["404"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge source-specific abbreviation tables by category_description2.")
    parser.add_argument("--category", default=str(CATEGORY_OUTPUT))
    parser.add_argument("--description", default=str(DESCRIPTION_OUTPUT))
    parser.add_argument("--llm", default=str(LLM_OUTPUT))
    parser.add_argument("--output", default=str(MASTER_OUTPUT))
    args = parser.parse_args()
    category, description, llm = map(by_id, (read_json(Path(args.category)), read_json(Path(args.description)), read_json(Path(args.llm))))
    ids = set(category) | set(description) | set(llm)
    master = []
    for key in sorted(ids):
        records = [table.get(key) for table in (category, description, llm) if table.get(key)]
        if not records:
            continue
        base = records[0]
        category_abbreviations = category.get(key, {}).get("abbreviations", [])
        description_abbreviations = description.get(key, {}).get("abbreviations", [])
        llm_abbreviations = llm.get(key, {}).get("abbreviations", [])
        master.append({
            "category_description2": key,
            "category": base["category"],
            "description_2": base["description_2"],
            "payload_category": category.get(key, {}).get("payload_category", {}),
            "abbreviations_category": category_abbreviations,
            "payload_description": description.get(key, {}).get("payload_description", {}),
            "abbreviations_description": description_abbreviations,
            "payload_llm": llm.get(key, {}).get("payload_llm", {}),
            "abbreviations_llm": llm_abbreviations,
            "final_abbreviations": final_abbreviations(
                category_abbreviations, description_abbreviations, llm_abbreviations
            ),
        })
    write_json(master, Path(args.output))
    print(f"Wrote {len(master):,} master records to {Path(args.output).resolve()}")


if __name__ == "__main__":
    main()
