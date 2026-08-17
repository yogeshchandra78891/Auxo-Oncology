from __future__ import annotations

import json
from pathlib import Path

from Bio import Entrez

"""Fetch PubMed abstracts for one or more search terms and save them as a JSON array.

When multiple terms are supplied (e.g. category + description_2 values),
`per_term_limit` abstracts are fetched per term and the results are
deduplicated by PMID before the final `max_results` cap is applied.
"""

from __future__ import annotations
import json
import re
from Bio import Entrez
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "top10_pubmed_abstracts.json"

Entrez.email = "your_email@example.com"


def fetch_top_pubmed_abstracts(
    topic: str | list[str],
    max_results: int = 10,
    per_term_limit: int = 5,
    output: Path = DEFAULT_OUTPUT,
) -> None:

    terms = [topic] if isinstance(topic, str) else list(topic)

    # ------------------------------------------------------------
    # Search PubMed
    # ------------------------------------------------------------

    seen_ids: dict[str, int] = {}

    for term in terms:

        limit = per_term_limit if len(terms) > 1 else max_results

        try:
            handle = Entrez.esearch(
                db="pubmed",
                term=term,
                retmax=limit,
                sort="relevance",
            )

            results = Entrez.read(handle)
            handle.close()

            for pmid in results.get("IdList", []):
                if pmid not in seen_ids:
                    seen_ids[pmid] = len(seen_ids)

        except Exception as exc:
            print(f"[warn] PubMed search failed for {term!r}: {exc}")

    if not seen_ids:
        print(f"[warn] No PubMed articles found for: {terms}")
        return

    # Preserve PubMed relevance order
    ordered_ids = list(seen_ids.keys())[:max_results]

    print(f"\nSearch: {terms}")
    print(f"PMIDs found: {ordered_ids}")

    # ------------------------------------------------------------
    # Fetch article information
    # ------------------------------------------------------------


def fetch_top_pubmed_abstracts(
    topic: str | list[str],
    max_results: int = 10,
    per_term_limit: int = 5,
    output: Path = DEFAULT_OUTPUT,
) -> None:
    """Fetch PubMed abstracts and write them to *output* as a JSON array.

    Each element in the array is a dict with keys:
        - "pmid": the PubMed ID string
        - "text": the full abstract text for that article

    Args:
        topic:          A single search term or a list of search terms.
                        When a list is given, `per_term_limit` PMIDs are
                        collected per term, deduplicated, then the top
                        `max_results` abstracts are fetched together.
        max_results:    Maximum total abstracts to save.
        per_term_limit: How many PMIDs to fetch per individual term
                        (only used when `topic` is a list).
        output:         Destination file path.
    """
    terms: list[str] = [topic] if isinstance(topic, str) else list(topic)

    # ---- Collect PMIDs per term, deduplicate --------------------------------
    seen_ids: dict[str, int] = {}  # PMID -> order of first appearance
    for term in terms:
        limit = per_term_limit if len(terms) > 1 else max_results
        try:
            handle = Entrez.esearch(
                db="pubmed",
                term=f"{term} AND free full text[Filter]",
                retmax=limit,
                sort="relevance",
            )
            results = Entrez.read(handle)
            handle.close()
            for pmid in results.get("IdList", []):
                if pmid not in seen_ids:
                    seen_ids[pmid] = len(seen_ids)
        except Exception as exc:
            print(f"  [warn] PubMed search failed for {term!r}: {exc}")

    if not seen_ids:
        print(f"  [warn] No PubMed articles found for: {terms}")
        return

    # Sort by first-appearance order, then cap at max_results
    ordered_ids = sorted(seen_ids, key=lambda pmid: seen_ids[pmid])[:max_results]

    # ---- Fetch abstracts for the collected PMIDs ----------------------------
    try:
        fetch_handle = Entrez.efetch(
            db="pubmed",
            id=ordered_ids,
            rettype="abstract",
            retmode="xml",
        )

        data = Entrez.read(fetch_handle)
        fetch_handle.close()

    except Exception as exc:
        print(f"[warn] PubMed efetch failed: {exc}")
        return

    # ------------------------------------------------------------
    # Extract PMID + title + abstract
    # ------------------------------------------------------------

    records = []

    for article in data["PubmedArticle"]:

        medline = article["MedlineCitation"]

        pmid = str(medline["PMID"])

        article_data = medline["Article"]

        title = str(article_data.get("ArticleTitle", ""))

        abstract_parts = []

        abstract = article_data.get("Abstract")

        if abstract:
            for item in abstract.get("AbstractText", []):
                abstract_parts.append(str(item))

        abstract_text = " ".join(abstract_parts)

        records.append(
            {
                "pmid": pmid,
                "title": title,
                "text": abstract_text,
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            }
        )

    # ------------------------------------------------------------
    # Save JSON
    # ------------------------------------------------------------

    output.parent.mkdir(parents=True, exist_ok=True)

            retmode="text",
        )
        abstract_data = fetch_handle.read()
        fetch_handle.close()
    except Exception as exc:
        print(f"  [warn] PubMed efetch failed: {exc}")
        return

    # ---- Split plain-text response into per-article records -----------------
    # PubMed plain-text format starts each article with "<N>. " on its own line.
    articles = re.split(r"(?m)(?=^\d+\.\s)", abstract_data)
    records: list[dict[str, str]] = []
    for pmid, article_text in zip(ordered_ids, (a.strip() for a in articles if a.strip())):
        records.append({"pmid": pmid, "text": article_text})

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(
        f"[pubmed] Fetched {len(records)} articles "
        f"for {len(terms)} search term(s) → {output}"
    )


def main():
    fetch_top_pubmed_abstracts(
        "lung cancer",
        max_results=10,
    )

    print(f"  [pubmed] Fetched {len(records)} abstracts ({len(terms)} term(s)) → {output.name}")


def main() -> None:
    fetch_top_pubmed_abstracts("lung cancer", max_results=10)

if __name__ == "__main__":
    main()