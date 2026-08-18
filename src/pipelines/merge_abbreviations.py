import argparse
import sys
from pathlib import Path
from typing import Optional

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


def run_merge(
    category_records: Optional[list] = None,
    description_records: Optional[list] = None,
    llm_records: Optional[list] = None,
    output_path: Optional[Path] = None,
) -> list:
    """Merge category, description, and LLM abbreviation tables into a master output.

    Each argument accepts either an in-memory list of records (passed directly
    from the orchestrator) or None, in which case the corresponding default
    file path from config is read from disk.

    Args:
        category_records:    Records from the article category mode. None = read CATEGORY_OUTPUT.
        description_records: Records from the article description mode. None = read DESCRIPTION_OUTPUT.
        llm_records:         Records from the LLM-only pipeline. None = read LLM_OUTPUT.
        output_path:         Where to write the master JSON. Defaults to MASTER_OUTPUT.

    Returns:
        List of merged master records.
    """
    output_path = output_path or MASTER_OUTPUT

    cat   = by_id(category_records   if category_records   is not None else read_json(CATEGORY_OUTPUT))
    desc  = by_id(description_records if description_records is not None else read_json(DESCRIPTION_OUTPUT))
    llm   = by_id(llm_records         if llm_records         is not None else read_json(LLM_OUTPUT))

    # Preserve natural insertion order across input sources (Category -> Description -> LLM)
    ordered_ids = list(dict.fromkeys(list(cat.keys()) + list(desc.keys()) + list(llm.keys())))

    master = []
    for key in ordered_ids:
        records = [table.get(key) for table in (cat, desc, llm) if table.get(key)]
        if not records:
            continue
        base = records[0]
        cat_abbrevs  = cat.get(key,  {}).get("abbreviations", [])
        desc_abbrevs = desc.get(key, {}).get("abbreviations", [])
        llm_abbrevs  = llm.get(key,  {}).get("abbreviations", [])
        master.append({
            "category_description2": key,
            "category":              base["category"],
            "description_2":         base["description_2"],
            "payload_category":      cat.get(key,  {}).get("payload_category",  {}),
            "abbreviations_category": cat_abbrevs,
            "payload_description":   desc.get(key, {}).get("payload_description", {}),
            "abbreviations_description": desc_abbrevs,
            "payload_llm":           llm.get(key,  {}).get("payload_llm",  {}),
            "abbreviations_llm":     llm_abbrevs,
            "final_abbreviations":   final_abbreviations(cat_abbrevs, desc_abbrevs, llm_abbrevs),
        })

    write_json(master, output_path)
    print(f"  [merge] Wrote {len(master):,} master records → {output_path.resolve()}")
    return master

def main() -> None:
    parser = argparse.ArgumentParser(description="Merge source-specific abbreviation tables by category_description2.")
    parser.add_argument("--category",    default=str(CATEGORY_OUTPUT))
    parser.add_argument("--description", default=str(DESCRIPTION_OUTPUT))
    parser.add_argument("--llm",         default=str(LLM_OUTPUT))
    parser.add_argument("--output",      default=str(MASTER_OUTPUT))
    args = parser.parse_args()
    run_merge(
        category_records=read_json(Path(args.category)),
        description_records=read_json(Path(args.description)),
        llm_records=read_json(Path(args.llm)),
        output_path=Path(args.output),
    )


if __name__ == "__main__":
    main()
