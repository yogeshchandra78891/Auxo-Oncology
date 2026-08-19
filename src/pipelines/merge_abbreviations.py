import argparse
import csv
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
    combined = []
    seen = set()
    for source in sources:
        if isinstance(source, dict):
            items = []
            for val_list in source.values():
                if isinstance(val_list, list):
                    items.extend(val_list)
        else:
            items = source or []

        for value in items:
            abbreviation = str(value).strip()
            key = abbreviation.casefold()
            if not abbreviation or key == "404" or key in seen:
                continue
            seen.add(key)
            combined.append(abbreviation)
    return combined if combined else ["404"]

def write_master_csv(records: list, csv_path: Path):
    with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "category_desc2",
            "category",
            "description2",
            "pubmed abbreviations",
            "clinical abbreviations",
            "llm abbreviations",
            "final abbreviations"
        ])
        for r in records:
            cat_abbr = r.get("abbreviations_category", {})
            desc_abbr = r.get("abbreviations_description", {})

            pubmed_raw = cat_abbr.get("pubmed", []) + desc_abbr.get("pubmed", [])
            pubmed_clean = list(dict.fromkeys(p for p in pubmed_raw if p and p.casefold() != "404"))

            clinical_raw = cat_abbr.get("clinical_trials", []) + desc_abbr.get("clinical_trials", [])
            clinical_clean = list(dict.fromkeys(c for c in clinical_raw if c and c.casefold() != "404"))

            llm_raw = r.get("abbreviations_llm", [])
            llm_clean = list(dict.fromkeys(x for x in llm_raw if x and x.casefold() != "404"))
            
            final_raw = r.get("final_abbreviations", [])
            final_clean = list(dict.fromkeys(x for x in final_raw if x and x.casefold() != "404"))

            writer.writerow([
                r.get("category_description2", ""),
                r.get("category", ""),
                r.get("description_2", ""),
                ", ".join(pubmed_clean),
                ", ".join(clinical_clean),
                ", ".join(llm_clean),
                ", ".join(final_clean)
            ])

def run_merge(
    category_records: Optional[list] = None,
    description_records: Optional[list] = None,
    llm_records: Optional[list] = None,
    output_path: Optional[Path] = None,
) -> list:
    output_path = output_path or MASTER_OUTPUT

    cat   = by_id(category_records   if category_records   is not None else read_json(CATEGORY_OUTPUT))
    desc  = by_id(description_records if description_records is not None else read_json(DESCRIPTION_OUTPUT))
    llm   = by_id(llm_records        if llm_records        is not None else read_json(LLM_OUTPUT))

    ordered_ids = list(dict.fromkeys(list(cat.keys()) + list(desc.keys()) + list(llm.keys())))

    master = []
    for key in ordered_ids:
        records = [table.get(key) for table in (cat, desc, llm) if table.get(key)]
        if not records:
            continue
        base = records[0]
        
        cat_abbrevs  = cat.get(key,  {}).get("abbreviations", {})
        desc_abbrevs = desc.get(key, {}).get("abbreviations", {})
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
    print(f"  [merge] Wrote {len(master):,} master records JSON → {output_path.resolve()}")
    
    csv_path = output_path.with_suffix('.csv')
    write_master_csv(master, csv_path)
    print(f"  [merge] Wrote {len(master):,} master records CSV → {csv_path.resolve()}")
    
    return master

def main() -> None:
    parser = argparse.ArgumentParser()
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