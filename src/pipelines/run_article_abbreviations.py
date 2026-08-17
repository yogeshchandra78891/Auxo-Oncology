"""
Orchestrator: full end-to-end abbreviation pipeline.

For each unique category in canonical_entities.json:
  1. Flush the shared PubMed and ClinicalTrials data files.
  2. Fetch fresh PubMed abstracts for that category.
  3. Fetch fresh ClinicalTrials.gov trials for that category.
  4. Build an in-memory knowledge base from those files.
  5. Run article_abbreviation in "category" mode for all entities in this category.
  6. Run article_abbreviation in "description" mode for all entities in this category.
  7. Accumulate results; move to the next category.

After all categories:
  8.  Write merged category_abbreviations.json and description_abbreviations.json.
  9.  Run LLM-only abbreviations (llm_abbreviation) for the same entity scope.
  10. Run merge (merge_abbreviations) to produce master_abbreviations.json.

Usage:
    python src/pipelines/run_article_abbreviations.py
    python src/pipelines/run_article_abbreviations.py --top-k 5 --refresh-cache
    python src/pipelines/run_article_abbreviations.py --category "Lung Cancer"
    python src/pipelines/run_article_abbreviations.py --category "Liver Cancer"
    python src/pipelines/run_article_abbreviations.py --skip-llm
    python src/pipelines/run_article_abbreviations.py --skip-merge
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.config import (
    CANONICAL_INPUT,
    CATEGORY_OUTPUT,
    CLINICAL_TRIALS,
    DESCRIPTION_OUTPUT,
    LLM_OUTPUT,
    MASTER_OUTPUT,
    PUBMED,
)
from src.DataExtractionScripts.cte import fetch_top_10_clinical_trials
from src.DataExtractionScripts.pubmed import fetch_top_pubmed_abstracts
from src.pipelines.article_abbreviation import load_knowledge_base, run_abbreviations
from src.pipelines.llm_abbreviation import run_llm
from src.pipelines.merge_abbreviations import run_merge
from utils.json_utils import read_json, write_json


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def flush_kb_files() -> None:
    """Delete the shared PubMed and ClinicalTrials data files so stale data
    from the previous category cannot bleed into the current one."""
    for path in (PUBMED, CLINICAL_TRIALS):
        if path.exists():
            path.unlink()
            print(f"  [flush] Removed {path.name}")


def prune_output_to_canonical(path: Path, canonical_ids: set[str]) -> None:
    """Remove generated records that no longer exist in canonical_entities.json."""
    records = read_json(path)
    retained = [
        record for record in records
        if record.get("category_description2") in canonical_ids
    ]
    removed = len(records) - len(retained)
    if removed:
        write_json(retained, path)
        print(f"  [cleanup] Removed {removed:,} stale record(s) from {path.name}")


def fetch_kb_for_category(category: str, descriptions: list[str]) -> None:
    """Fetch PubMed abstracts and ClinicalTrials studies for *category* and
    its *descriptions*, then write them to the shared data-directory paths
    that load_knowledge_base() reads from."""
    search_terms = [category] + descriptions
    print(f"  [fetch] PubMed  ← {category!r} + {len(descriptions)} description(s)")
    try:
        fetch_top_pubmed_abstracts(
            topic=search_terms,
            max_results=10,
            per_term_limit=5,
            output=PUBMED,
        )
    except Exception as exc:
        print(f"  [warn]  PubMed fetch failed for {category!r}: {exc}")

    print(f"  [fetch] CTE     ← {category!r} + {len(descriptions)} description(s)")
    try:
        fetch_top_10_clinical_trials(
            keyword=search_terms,
            max_results=10,
            per_term_limit=5,
            output=CLINICAL_TRIALS,
        )
    except Exception as exc:
        print(f"  [warn]  CTE fetch failed for {category!r}: {exc}")


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def run(
    top_k: int = 5,
    refresh_cache: bool = False,
    only_category: Optional[str] = None,
    skip_llm: bool = False,
    skip_merge: bool = False,
) -> None:
    # ---- Load canonical entities -------------------------------------------
    all_entities: list[dict] = read_json(CANONICAL_INPUT)
    if not all_entities:
        raise SystemExit(f"No entities found in {CANONICAL_INPUT}. Run build_input.py first.")
    canonical_ids = {entity["category_description2"] for entity in all_entities}
    # Clean the generated source tables first. The merge stage can then remain
    # a direct union of those tables without inheriting old canonical records.
    for output_path in (CATEGORY_OUTPUT, DESCRIPTION_OUTPUT, LLM_OUTPUT):
        prune_output_to_canonical(output_path, canonical_ids)

    # ---- Determine categories to process ------------------------------------
    all_categories: list[str] = list(dict.fromkeys(
        e["category"] for e in all_entities if e.get("category")
    ))
    if only_category:
        if only_category not in all_categories:
            raise SystemExit(f"Category {only_category!r} not found in canonical entities.")
        categories_to_run = [only_category]
    else:
        categories_to_run = all_categories

    # Entities in scope — used later for LLM step
    scoped_entities = (
        [e for e in all_entities if e.get("category") == only_category]
        if only_category else all_entities
    )

    print(f"\n{'='*60}")
    print(f"Orchestrator: {len(all_entities)} total entities | {len(scoped_entities)} in scope")
    print(f"Categories to process: {len(categories_to_run)}")
    if only_category:
        print(f"Scope limited to: {only_category!r}")
    print(f"Steps: article ✓ | llm {'SKIP' if skip_llm else '✓'} | merge {'SKIP' if skip_merge else '✓'}")
    print(f"{'='*60}\n")

    # Accumulators for article abbreviation results
    all_category_results:    list[dict] = []
    all_description_results: list[dict] = []

    # ---- Step 1–7: Per-category article abbreviation loop ------------------
    for idx, category in enumerate(categories_to_run, start=1):
        cat_entities = [e for e in all_entities if e.get("category") == category]
        print(f"[{idx}/{len(categories_to_run)}] Category: {category!r}  ({len(cat_entities)} entities)")

        flush_kb_files()

        unique_descriptions = list(dict.fromkeys(
            e["description_2"] for e in cat_entities if e.get("description_2")
        ))
        fetch_kb_for_category(category, unique_descriptions)

        knowledge_base = load_knowledge_base()
        if not knowledge_base:
            print(f"  [warn]  No KB records loaded for {category!r}; both modes will return 404.")

        cat_output = CATEGORY_OUTPUT.parent / f"_tmp_cat_{idx:03d}.json"
        try:
            cat_results = run_abbreviations(
                entities=cat_entities,
                mode="category",
                output_path=cat_output,
                top_k=top_k,
                refresh_cache=refresh_cache,
                knowledge_base=knowledge_base,
            )
            all_category_results.extend(cat_results)
        except Exception as exc:
            print(f"  [error] category mode failed for {category!r}: {exc}")

        desc_output = DESCRIPTION_OUTPUT.parent / f"_tmp_desc_{idx:03d}.json"
        try:
            desc_results = run_abbreviations(
                entities=cat_entities,
                mode="description",
                output_path=desc_output,
                top_k=top_k,
                refresh_cache=refresh_cache,
                knowledge_base=knowledge_base,
            )
            all_description_results.extend(desc_results)
        except Exception as exc:
            print(f"  [error] description mode failed for {category!r}: {exc}")

        if idx < len(categories_to_run):
            time.sleep(1)

        print()

    # ---- Step 8: Write article abbreviation outputs ------------------------
    print(f"{'='*60}")
    print("Step 8 — Writing article abbreviation outputs...")

    # Always upsert by category_description2 key.
    # Records for categories processed in this run overwrite existing entries;
    # records for categories NOT in this run are preserved from the output files.
    # Canonical input is authoritative: do not preserve records from an older
    # canonical file when a scoped run upserts its new results.
    existing_cat = {
        record["category_description2"]: record
        for record in read_json(CATEGORY_OUTPUT)
        if record.get("category_description2") in canonical_ids
    }
    existing_desc = {
        record["category_description2"]: record
        for record in read_json(DESCRIPTION_OUTPUT)
        if record.get("category_description2") in canonical_ids
    }
    for r in all_category_results:
        existing_cat[r["category_description2"]] = r
    for r in all_description_results:
        existing_desc[r["category_description2"]] = r
    all_category_results    = list(existing_cat.values())
    all_description_results = list(existing_desc.values())

    write_json(all_category_results, CATEGORY_OUTPUT)
    print(f"  category_abbreviations    → {len(all_category_results):,} records → {CATEGORY_OUTPUT.resolve()}")

    write_json(all_description_results, DESCRIPTION_OUTPUT)
    print(f"  description_abbreviations → {len(all_description_results):,} records → {DESCRIPTION_OUTPUT.resolve()}")

    # Clean up temp files
    for tmp in CATEGORY_OUTPUT.parent.glob("_tmp_cat_*.json"):
        tmp.unlink(missing_ok=True)
    for tmp in DESCRIPTION_OUTPUT.parent.glob("_tmp_desc_*.json"):
        tmp.unlink(missing_ok=True)

    # ---- Step 9: LLM-only abbreviations ------------------------------------
    llm_results: Optional[list] = None

    if skip_llm:
        print(f"\nStep 9 — LLM abbreviations SKIPPED (--skip-llm).")
    else:
        print(f"\n{'='*60}")
        print(f"Step 9 — LLM-only abbreviations ({len(scoped_entities)} entities in scope)...")

        # Run LLM for the scoped entities, then upsert into the existing LLM
        # output file so records from other categories are preserved and the
        # just-processed ones are replaced (not duplicated).
        llm_scoped = run_llm(
            entities=scoped_entities,
            output_path=LLM_OUTPUT.parent / "_tmp_llm_scoped.json",
            refresh_cache=refresh_cache,
            category_records=all_category_results,
            description_records=all_description_results,
        )
        existing_llm = {
            record["category_description2"]: record
            for record in read_json(LLM_OUTPUT)
            if record.get("category_description2") in canonical_ids
        }
        for r in llm_scoped:
            existing_llm[r["category_description2"]] = r
        llm_results = list(existing_llm.values())
        write_json(llm_results, LLM_OUTPUT)
        print(f"  [llm] Updated {LLM_OUTPUT.resolve()} ({len(llm_results):,} total records)")
        # Clean temp file
        tmp_llm = LLM_OUTPUT.parent / "_tmp_llm_scoped.json"
        tmp_llm.unlink(missing_ok=True)

    # ---- Step 10: Merge ----------------------------------------------------
    if skip_merge:
        print(f"\nStep 10 — Merge SKIPPED (--skip-merge).")
    else:
        print(f"\n{'='*60}")
        print("Step 10 — Merging all abbreviation sources → master_abbreviations.json...")
        run_merge(
            category_records=all_category_results,
            description_records=all_description_results,
            llm_records=llm_results,   # None = read from disk if LLM was skipped
            output_path=MASTER_OUTPUT,
        )

    print(f"\n{'='*60}")
    print(f"Done. Processed {len(categories_to_run)} category/categories.")
    print(f"  category_abbreviations    → {CATEGORY_OUTPUT.resolve()}")
    print(f"  description_abbreviations → {DESCRIPTION_OUTPUT.resolve()}")
    if not skip_llm:
        print(f"  llm_abbreviations         → {LLM_OUTPUT.resolve()}")
    if not skip_merge:
        print(f"  master_abbreviations      → {MASTER_OUTPUT.resolve()}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="End-to-end abbreviation orchestrator: article → LLM → merge."
    )
    parser.add_argument(
        "--top-k", type=int, default=5,
        help="Max KB records used as evidence per query (default: 5).",
    )
    parser.add_argument(
        "--refresh-cache", action="store_true",
        help="Ignore existing cache entries and reprocess everything.",
    )
    parser.add_argument(
        "--category", default=None,
        help="Process only this one category (exact match). Useful for testing.",
    )
    parser.add_argument(
        "--skip-llm", action="store_true",
        help="Skip the LLM-only abbreviation step.",
    )
    parser.add_argument(
        "--skip-merge", action="store_true",
        help="Skip the final merge step.",
    )
    args = parser.parse_args()
    run(
        top_k=args.top_k,
        refresh_cache=args.refresh_cache,
        only_category=args.category,
        skip_llm=args.skip_llm,
        skip_merge=args.skip_merge,
    )


if __name__ == "__main__":
    main()
