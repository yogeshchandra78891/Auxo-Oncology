"""
abbreviation_analysis.py
------------------------
Produces a summary Excel/CSV with the following columns for each canonical entity:

  category                  – disease category name (e.g. "Stomach Cancer")
  category_abbreviations    – pipe-separated abbreviations derived from the category field
  description_abbreviations – pipe-separated abbreviations derived from the description field
  master_abbreviations      – distinct union of both sources (de-duplicated, case-insensitive)
  indication_oncology       – pipe-separated abbreviations already stored in the
                              Indication_Oncology CSV (abbreviations column)
  difference                – abbreviations that are in indication_oncology but NOT in
                              master_abbreviations (i.e. gaps / extras in the CSV)

Data sources
------------
  category_abbreviations  → data/category_abbreviations.json
  description_abbreviations → data/description_abbreviations.json
  indication oncology     → data/Indication_Oncology(in).csv  (abbreviations column, | delimited)

Usage
-----
  python abbreviation_analysis.py                        # writes abbreviation_analysis.csv
  python abbreviation_analysis.py --output my_report.csv
  python abbreviation_analysis.py --output report.xlsx   # auto-detects Excel from extension
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

# ── Paths ─────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"

CATEGORY_ABBREV_FILE = DATA_DIR / "category_abbreviations.json"
DESCRIPTION_ABBREV_FILE = DATA_DIR / "description_abbreviations.json"
INDICATION_CSV = DATA_DIR / "Indication_Oncology(in).csv"

OUTPUT_DEFAULT = PROJECT_ROOT / "abbreviation_analysis.csv"


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_json(path: Path) -> list:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def clean_list(values: list[str]) -> list[str]:
    """Strip whitespace and drop empty / sentinel '404' values."""
    return [v.strip() for v in values if v.strip() and v.strip() != "404"]


def distinct_union(*lists: list[str]) -> list[str]:
    """
    Merge multiple lists into a single de-duplicated list.
    Order preserving; case-insensitive duplicate check.
    """
    seen: set[str] = set()
    result: list[str] = []
    for lst in lists:
        for item in lst:
            key = item.casefold()
            if key not in seen:
                seen.add(key)
                result.append(item)
    return result


def parse_pipe_separated(value: str) -> list[str]:
    """Parse a '|' delimited cell from the Indication_Oncology CSV."""
    if not isinstance(value, str):
        return []
    return [part.strip() for part in value.split("|") if part.strip()]


# ── Load raw data ─────────────────────────────────────────────────────────────

def load_category_abbreviations() -> dict[str, list[str]]:
    """Returns {category_description2: [abbreviations...]}"""
    records = load_json(CATEGORY_ABBREV_FILE)
    return {
        rec["category_description2"]: clean_list(rec.get("abbreviations", []))
        for rec in records
    }


def load_description_abbreviations() -> dict[str, list[str]]:
    """Returns {category_description2: [abbreviations...]}"""
    records = load_json(DESCRIPTION_ABBREV_FILE)
    return {
        rec["category_description2"]: clean_list(rec.get("abbreviations", []))
        for rec in records
    }


def load_indication_oncology() -> dict[str, list[str]]:
    """
    Returns {category_description2_key: [abbreviations...]}

    The key is built the same way the pipeline does it:
        f"{category.lower()}|{description_2.lower()}"
    """
    df = pd.read_csv(INDICATION_CSV, dtype=str)
    df.columns = df.columns.str.strip()

    # Build index key matching category_description2 format used in JSON files
    df["_key"] = (
        df["category"].str.strip().str.lower()
        + "|"
        + df["description_2"].str.strip().str.lower()
    )

    indication: dict[str, list[str]] = {}
    for key, group in df.groupby("_key"):
        all_abbrevs: list[str] = []
        for cell in group["abbreviations"].dropna():
            all_abbrevs.extend(parse_pipe_separated(cell))
        # Remove ICD codes (patterns like C00, C00.1, etc.) – keep only text aliases
        text_abbrevs = [a for a in all_abbrevs if not a.upper().startswith("C")]
        indication[key] = list(dict.fromkeys(text_abbrevs))  # preserve order, dedup

    return indication


# ── Build the report ─────────────────────────────────────────────────────────

def build_report() -> pd.DataFrame:
    cat_map  = load_category_abbreviations()
    desc_map = load_description_abbreviations()
    ind_map  = load_indication_oncology()

    # All unique entity keys across both abbreviation sources
    all_keys = sorted(set(cat_map) | set(desc_map))

    rows = []
    for key in all_keys:
        cat_abbrevs  = cat_map.get(key, [])
        desc_abbrevs = desc_map.get(key, [])
        master       = distinct_union(cat_abbrevs, desc_abbrevs)
        indication   = ind_map.get(key, [])

        # Difference: in indication_oncology but NOT in master (case-insensitive)
        master_lower = {m.casefold() for m in master}
        difference   = [a for a in indication if a.casefold() not in master_lower]

        # Recover human-readable names from the JSON records
        parts = key.split("|", 1)
        category_name = parts[0].title() if parts else key

        rows.append({
            "category":                   category_name,
            "category_abbreviations":     " | ".join(cat_abbrevs),
            "description_abbreviations":  " | ".join(desc_abbrevs),
            "master_abbreviations":       " | ".join(master),
            "indication_oncology":        " | ".join(indication),
            "difference":                 " | ".join(difference),
        })

    return pd.DataFrame(rows)


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build an abbreviation comparison report across category, description, "
                    "master, and Indication_Oncology sources."
    )
    parser.add_argument(
        "--output", "-o",
        default=str(OUTPUT_DEFAULT),
        help="Output file path. Use .xlsx extension for Excel output. "
             f"Default: {OUTPUT_DEFAULT}",
    )
    args = parser.parse_args()

    output_path = Path(args.output)

    print("Loading data …")
    df = build_report()

    print(f"\nReport summary: {len(df)} entities\n")
    print(df.to_string(index=False, max_colwidth=80))

    if output_path.suffix.lower() in {".xlsx", ".xls"}:
        try:
            df.to_excel(output_path, index=False, engine="openpyxl")
        except ModuleNotFoundError:
            csv_path = output_path.with_suffix(".csv")
            print("⚠  openpyxl not installed — saving as CSV instead.")
            print("   Install it with:  pip install openpyxl")
            df.to_csv(csv_path, index=False)
            output_path = csv_path
    else:
        df.to_csv(output_path, index=False)

    print(f"\nSaved → {output_path.resolve()}")


if __name__ == "__main__":
    main()
