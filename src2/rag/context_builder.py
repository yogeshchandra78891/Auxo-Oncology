from typing import Any


def build_context(results: dict[str, list[dict[str, Any]]]) -> str:
    sections: list[str] = []
    for label, records in (("PubMed", results.get("pubmed", [])), ("ClinicalTrials", results.get("clinical_trials", []))):
        lines = [label]
        for index, record in enumerate(records, start=1):
            identifier = record.get("id") or record.get("pmid") or record.get("nct_id") or "unknown"
            title = record.get("title") or record.get("brief_title") or record.get("official_title") or ""
            summary = record.get("abstract") or record.get("summary") or record.get("brief_summary") or ""
            lines.append(f"{index}. ID: {identifier}\nTitle: {title}\nSummary: {summary}")
        sections.append("\n".join(lines))
    return "\n\n".join(sections)
