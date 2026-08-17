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

# FETCH CLINICAL TRIALS

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

    # SEARCH CLINICALTRIALS.GOV

    # --------------------------------------------------------
 
    params = {

        # Matches the "Condition/disease" field

        "query.cond": keyword,
 
        # IMPORTANT:

        # Match the website's default "Relevance" ordering

        "sort": "@relevance",
 
        # Number of results requested

        "pageSize": max_results,

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

    # GET STUDIES

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
 
    # --------------------------------------------------------

    # PARSE + DEDUPLICATE

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

    # KEEP TOP N

    # --------------------------------------------------------
 
    records = records[:max_results]
 
    # --------------------------------------------------------

    # PRINT RESULTS

    # --------------------------------------------------------
 
    print()

    print("=" * 80)

    print("CLINICALTRIALS.GOV SEARCH RESULTS")

    print("=" * 80)
 
    print(f"Search term : {keyword}")

    print("Search field: Condition/disease")

    print("Sort        : Relevance")

    print(f"Results     : {len(records)}")

    print()
 
    for index, record in enumerate(

        records,

        start=1

    ):
 
        print(

            f"{index:2}. "

            f"{record['nct_id']} | "

            f"{record['title']}"

        )
 
    print("=" * 80)
 
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
 
    print(

        f"\n[cte] Saved "

        f"{len(records)} studies → {output}"

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
 