"""Fetch ClinicalTrials.gov studies as structured JSON..

When multiple keywords are supplied (e.g. category + description_2 values),
`per_term_limit` studies are fetched per keyword and the results are
deduplicated by NCT ID before the final `max_results` cap is applied.
"""

from __future__ import annotations
import json
from pathlib import Path
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "top_10_clinical_trials.json"


def _parse_study(study: dict) -> dict:
    """Extract the fields used downstream from a raw ClinicalTrials API study."""
    protocol = study.get("protocolSection", {})
    identification = protocol.get("identificationModule", {})
    status_module = protocol.get("statusModule", {})
    design = protocol.get("designModule", {})
    conditions_module = protocol.get("conditionsModule", {})
    arms_module = protocol.get("armsInterventionsModule", {})
    description_module = protocol.get("descriptionModule", {})

    return {
        "nct_id": identification.get("nctId", ""),
        "title": identification.get("briefTitle", ""),
        "summary": description_module.get("briefSummary", ""),
        "condition": ", ".join(conditions_module.get("conditions", [])),
        "status": status_module.get("overallStatus", ""),
        "study_type": design.get("studyType", ""),
        "interventions": ", ".join(
            item.get("name", "")
            for item in arms_module.get("interventions", [])
        ),
    }


def fetch_top_10_clinical_trials(
    keyword: str | list[str],
    max_results: int = 10,
    per_term_limit: int = 5,
    output: Path = DEFAULT_OUTPUT,
) -> None:
    """Fetch ClinicalTrials.gov studies and write them as a JSON array.

    Args:
        keyword:        A single search keyword or a list of keywords.
                        When a list is given, `per_term_limit` studies are
                        fetched per keyword, deduplicated by NCT ID, then
                        capped at `max_results`.
        max_results:    Maximum total studies to save.
        per_term_limit: How many studies to fetch per individual keyword
                        (only used when `keyword` is a list).
        output:         Destination file path.
    """
    keywords: list[str] = [keyword] if isinstance(keyword, str) else list(keyword)

    # ---- Collect studies per keyword, deduplicate by NCT ID -----------------
    seen: dict[str, dict] = {}  # nct_id -> parsed record (first seen wins)

    for kw in keywords:
        limit = per_term_limit if len(keywords) > 1 else max_results
        try:
            response = requests.get(
                "https://clinicaltrials.gov/api/v2/studies",
                params={"query.cond": kw, "pageSize": limit, "format": "json"},
                timeout=30,
            )
            response.raise_for_status()
            for study in response.json().get("studies", []):
                record = _parse_study(study)
                nct_id = record["nct_id"]
                if nct_id and nct_id not in seen:
                    seen[nct_id] = record
        except Exception as exc:
            print(f"  [warn] CTE fetch failed for {kw!r}: {exc}")

    if not seen:
        print(f"  [warn] No clinical trials found for: {keywords}")
        return

    # Preserve insertion order (category results come first), cap at max_results
    records = list(seen.values())[:max_results]

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  [cte]    Fetched {len(records)} trials ({len(keywords)} keyword(s)) → {output.name}")


def main() -> None:
    fetch_top_10_clinical_trials("lung cancer", max_results=10)

if __name__ == "__main__":
    main()