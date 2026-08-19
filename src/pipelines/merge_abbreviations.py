import argparse
import csv
import sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.config import CANONICAL_INPUT, CATEGORY_OUTPUT, DESCRIPTION_OUTPUT, LLM_OUTPUT, MASTER_OUTPUT
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

def extract_clean_abbreviations(r: dict) -> dict:
    cat_abbr = r.get("abbreviations_category", {})
    desc_abbr = r.get("abbreviations_description", {})

    cat_dict = cat_abbr if isinstance(cat_abbr, dict) else {}
    desc_dict = desc_abbr if isinstance(desc_abbr, dict) else {}

    pubmed_raw = cat_dict.get("pubmed", []) + desc_dict.get("pubmed", [])
    pubmed_clean = list(dict.fromkeys(p for p in pubmed_raw if p and p.casefold() != "404"))

    clinical_raw = cat_dict.get("clinical_trials", []) + desc_dict.get("clinical_trials", [])
    clinical_clean = list(dict.fromkeys(c for c in clinical_raw if c and c.casefold() != "404"))

    llm_raw = r.get("abbreviations_llm", [])
    llm_clean = list(dict.fromkeys(x for x in llm_raw if x and x.casefold() != "404"))
    
    final_raw = r.get("final_abbreviations", [])
    final_clean = list(dict.fromkeys(x for x in final_raw if x and x.casefold() != "404"))

    return {
        "pubmed": ", ".join(pubmed_clean),
        "clinical": ", ".join(clinical_clean),
        "llm": ", ".join(llm_clean),
        "final": ", ".join(final_clean)
    }

def write_master_csv(records: list, csv_path: Path):
    with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "category_desc2",
            "category",
            "description2",
            "description3",
            "pubmed abbreviations",
            "clinical abbreviations",
            "llm abbreviations",
            "final abbreviations"
        ])
        
        for r in records:
            abbrs = extract_clean_abbreviations(r)
            writer.writerow([
                r.get("category_description2", ""),
                r.get("category", ""),
                r.get("description_2", ""),
                r.get("description_3", ""),
                abbrs["pubmed"],
                abbrs["clinical"],
                abbrs["llm"],
                abbrs["final"]
            ])

def update_icd_with_abbreviations(master_records: list, icd_csv_path: Path):
    if not icd_csv_path.exists():
        print(f"  [merge] Warning: ICD CSV not found at {icd_csv_path}. Skipping append operation.")
        return

    lookup = {}
    for r in master_records:
        key = str(r.get("category_description2", "")).strip().casefold()
        lookup[key] = extract_clean_abbreviations(r)

    with open(icd_csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = list(reader)

    cat_idx = next((i for i, h in enumerate(header) if h.lower() == "category"), None)
    desc_idx = next((i for i, h in enumerate(header) if h.lower() == "description_2"), None)

    if cat_idx is None or desc_idx is None:
        print("  [merge] Error: 'Category' or 'description_2' column not found in ICD CSV.")
        return

    new_header = header + [
        "pubmed abbreviations", 
        "clinical abbreviations", 
        "llm abbreviations", 
        "final abbreviations"
    ]

    out_rows = []
    match_count = 0

    for row in rows:
        cat_val = row[cat_idx].strip() if cat_idx < len(row) else ""
        desc_val = row[desc_idx].strip() if desc_idx < len(row) else ""
        
        row_key = f"{cat_val}|{desc_val}".strip().casefold()

        match = lookup.get(row_key)
        
        if match:
            new_row = row + [match["pubmed"], match["clinical"], match["llm"], match["final"]]
            match_count += 1
            out_rows.append(new_row)
        else:
            new_row = row + ["", "", "", ""]
            out_rows.append(new_row)

    out_path = icd_csv_path.parent / f"{icd_csv_path.stem}_updated.csv"
    with open(out_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(new_header)
        writer.writerows(out_rows)

    print(f"  [merge] Successfully matched and injected data into {match_count} rows!")
    print(f"  [merge] Wrote enriched ICD CSV → {out_path.resolve()} (Original order preserved)")

def run_merge(
    canonical_records: Optional[list] = None,
    category_records: Optional[list] = None,
    description_records: Optional[list] = None,
    llm_records: Optional[list] = None,
    output_path: Optional[Path] = None,
    icd_input_path: Optional[Path] = None,
) -> list:
    output_path = output_path or MASTER_OUTPUT

    canon = by_id(canonical_records if canonical_records is not None else read_json(CANONICAL_INPUT))
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
        
        canonical_base = canon.get(key, {})
        description_3 = canonical_base.get("description_3", canonical_base.get("description3", ""))
        
        cat_abbrevs  = cat.get(key,  {}).get("abbreviations", {})
        desc_abbrevs = desc.get(key, {}).get("abbreviations", {})
        llm_abbrevs  = llm.get(key,  {}).get("abbreviations", [])
        
        master.append({
            "category_description2": key,
            "category":              base["category"],
            "description_2":         base["description_2"],
            "description_3":         description_3,
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
    print(f"  [merge] Wrote {len(master):,} master records CSV  → {csv_path.resolve()}")

    if icd_input_path:
        update_icd_with_abbreviations(master, icd_input_path)
    
    return master

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical",   default=str(CANONICAL_INPUT))
    parser.add_argument("--category",    default=str(CATEGORY_OUTPUT))
    parser.add_argument("--description", default=str(DESCRIPTION_OUTPUT))
    parser.add_argument("--llm",         default=str(LLM_OUTPUT))
    parser.add_argument("--output",      default=str(MASTER_OUTPUT))
    parser.add_argument("--icd_input",   default=str(PROJECT_ROOT / "data" / "ICD_with_categories.csv"))
    args = parser.parse_args()
    
    run_merge(
        canonical_records=read_json(Path(args.canonical)),
        category_records=read_json(Path(args.category)),
        description_records=read_json(Path(args.description)),
        llm_records=read_json(Path(args.llm)),
        output_path=Path(args.output),
        icd_input_path=Path(args.icd_input)
    )

if __name__ == "__main__":
    main()