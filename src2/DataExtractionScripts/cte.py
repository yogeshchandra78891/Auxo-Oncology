"""Fetch ClinicalTrials.gov studies as structured JSON for the RAG pipeline."""

import json
from pathlib import Path

import requests


keyword = "lung cancer"

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "top_10_clinical_trials.txt"


def fetch_top_10_clinical_trials(
    keyword: str,
    output: Path = DEFAULT_OUTPUT
) -> None:

    response = requests.get(
        "https://clinicaltrials.gov/api/v2/studies",
        params={
            "query.cond": keyword,
            "pageSize": 10,
            "format": "json",
        },
        timeout=30,
    )

    response.raise_for_status()

    studies = response.json().get("studies", [])

    if not studies:
        print("No clinical trials found.")
        return

    records = []

    for study in studies:

        protocol = study.get("protocolSection", {})

        identification = protocol.get(
            "identificationModule", {}
        )

        status_module = protocol.get(
            "statusModule", {}
        )

        design = protocol.get(
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

        records.append({
            "nct_id": identification.get(
                "nctId", ""
            ),

            "title": identification.get(
                "briefTitle", ""
            ),

            "summary": description_module.get(
                "briefSummary", ""
            ),

            "condition": ", ".join(
                conditions_module.get(
                    "conditions", []
                )
            ),

            "status": status_module.get(
                "overallStatus", ""
            ),

            "study_type": design.get(
                "studyType", ""
            ),

            "interventions": ", ".join(
                item.get("name", "")
                for item in arms_module.get(
                    "interventions", []
                )
            ),
        })

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
        encoding="utf-8"
    )

    print(
        f"Saved {len(records)} trials to {output}"
    )


def main() -> None:
    fetch_top_10_clinical_trials(keyword)


if __name__ == "__main__":
    main()