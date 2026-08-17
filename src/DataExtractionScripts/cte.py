from __future__ import annotations

import json
from pathlib import Path

import requests


# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_OUTPUT = (
    PROJECT_ROOT / "data" / "top_10_clinical_trials.json"
)

API_URL = "https://clinicaltrials.gov/api/v2/studies"

# Fetch more than required so we can verify ranking
FETCH_LIMIT = 100


# ============================================================
# PARSE STUDY
# ============================================================

def _parse_study(study: dict) -> dict:

    protocol = study.get("protocolSection", {})

    identification = protocol.get(
        "identificationModule", {}
    )

    status_module = protocol.get(
        "statusModule", {}
    )

    design_module = protocol.get(
        "designModule", {}
    )

    conditions_module = protocol.get(
        "conditionsModule", {}
    )

    arms_module = protocol.get(
        "armsInterventionsModule", {}
    )

    description_module = protocol.get(
        "descriptionModule", {}
    )

    nct_id = identification.get(
        "nctId", ""
    )

    return {
        "nct_id": nct_id,

        "title": identification.get(
            "briefTitle", ""
        ),

        "summary": description_module.get(
            "briefSummary", ""
        ),

        "detailed_description": description_module.get(
            "detailedDescription", ""
        ),

        "condition": ", ".join(
            conditions_module.get(
                "conditions", []
            )
        ),

        "status": status_module.get(
            "overallStatus", ""
        ),

        "study_type": design_module.get(
            "studyType", ""
        ),

        "interventions": ", ".join(
            item.get("name", "")
            for item in arms_module.get(
                "interventions", []
            )
        ),

        "url": (
            f"https://clinicaltrials.gov/study/{nct_id}"
            if nct_id
            else ""
        ),
    }


# ============================================================
# FETCH STUDIES
# ============================================================

def fetch_top_10_clinical_trials(
    keyword: str,
    max_results: int = 10,
    output: Path = DEFAULT_OUTPUT,
) -> None:

    keyword = keyword.strip()

    if not keyword:
        print("[warn] Empty search term.")
        return

    # --------------------------------------------------------
    # API SEARCH
    # --------------------------------------------------------

    params = {
        # IMPORTANT:
        # This corresponds to the ClinicalTrials.gov
        # "Condition/disease" search field.
        "query.cond": keyword,

        # Fetch more candidates first
        "pageSize": FETCH_LIMIT,
    }

    try:

        response = requests.get(
            API_URL,
            params=params,
            timeout=30,
        )

        response.raise_for_status()

        data = response.json()

    except requests.RequestException as exc:

        print(
            f"[ERROR] ClinicalTrials.gov request failed: {exc}"
        )

        return

    # --------------------------------------------------------
    # READ RESULTS
    # --------------------------------------------------------

    studies = data.get(
        "studies",
        []
    )

    if not studies:

        print(
            f"[WARN] No studies found for: {keyword}"
        )

        return

    print()
    print("=" * 70)
    print("CLINICALTRIALS.GOV SEARCH")
    print("=" * 70)
    print(f"Search term : {keyword}")
    print(f"Results API : {len(studies)}")
    print()

    # --------------------------------------------------------
    # PARSE RESULTS IN API ORDER
    # --------------------------------------------------------

    records = []

    seen_ids = set()

    for study in studies:

        record = _parse_study(study)

        nct_id = record["nct_id"]

        if not nct_id:
            continue

        if nct_id in seen_ids:
            continue

        seen_ids.add(nct_id)

        records.append(record)

    # --------------------------------------------------------
    # TAKE TOP RESULTS
    # --------------------------------------------------------

    records = records[:max_results]

    # --------------------------------------------------------
    # PRINT RESULTS FOR COMPARISON
    # --------------------------------------------------------

    print("TOP RESULTS FROM API:")
    print("-" * 70)

    for index, record in enumerate(
        records,
        start=1
    ):

        print(
            f"{index:2}. "
            f"{record['nct_id']} | "
            f"{record['title']}"
        )

    print("-" * 70)

    # --------------------------------------------------------
    # SAVE JSON
    # --------------------------------------------------------

    output.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    output.write_text(
        json.dumps(
            records,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8",
    )

    print()
    print(
        f"[cte] Saved {len(records)} studies → {output}"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    fetch_top_10_clinical_trials(
        keyword="lung cancer",
        max_results=10,
    )


if __name__ == "__main__":
    main()