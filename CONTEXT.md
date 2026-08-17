# Auxo-Oncology — Repository Context

## Purpose

This project generates a comprehensive, clinically valid **abbreviation and alias dictionary** for ICD-coded diagnoses (oncology + cardiovascular + metabolic). Each ICD entity gets a `final_abbreviations` list that combines three independent generation strategies, deduplicated into a single clean output used downstream for entity recognition and matching.

---

## Technology Stack

| Component | Technology |
|---|---|
| Language | Python 3.9+ |
| LLM | Azure OpenAI (GPT-4o) via `openai` SDK |
| Evidence sources | PubMed (via Biopython/Entrez), ClinicalTrials.gov (REST API v2) |
| Data | ICD-10 CSV, Indication_Oncology reference CSV |
| Key libraries | `pandas`, `biopython`, `httpx`, `python-dotenv`, `openai` |

---

## Repository Structure

```
Auxo-Oncology/
│
├── config/
│   └── config.py                   # Central path constants for all data files
│
├── data/                           # All input/output data files (gitignored except reference data)
│   ├── ICD_raw_2025(in).csv        # Raw ICD-10 codes + descriptions (input)
│   ├── ICD_with_categories.csv     # ICD CSV after category assignment (intermediate)
│   ├── Indication_Oncology(in).csv # Ground truth reference abbreviations for comparison
│   ├── canonical_entities.json     # Deduplicated (category, description_2) pairs — MAIN INPUT
│   ├── category_abbreviations.json # RAG output: category-query mode
│   ├── description_abbreviations.json # RAG output: description-query mode
│   ├── llm_abbreviations.json      # LLM-only output
│   ├── master_abbreviations.json   # FINAL merged output — most important file
│   ├── top10_pubmed_abstracts.json # PubMed evidence fetched per category (per-run)
│   ├── top_10_clinical_trials.json # ClinicalTrials evidence fetched per category (per-run)
│   └── cache/
│       ├── category_abbreviations_cache.json
│       ├── description_abbreviations_cache.json
│       └── llm_abbreviations_cache.json
│
├── src/
│   ├── CategoryCreation/
│   │   └── add_disease_categories.py   # Step 1: assigns ICD category labels via LLM
│   │
│   ├── DataExtractionScripts/
│   │   ├── pubmed.py                   # Fetches PubMed abstracts (XML, structured JSON output)
│   │   └── cte.py                      # Fetches ClinicalTrials.gov studies (JSON output)
│   │
│   ├── pipelines/
│   │   ├── build_input.py              # Step 2: builds canonical_entities.json from ICD CSV
│   │   ├── article_abbreviation.py     # Step 3a: RAG-grounded abbreviation generation
│   │   ├── llm_abbreviation.py         # Step 3b: LLM-only abbreviation generation
│   │   ├── merge_abbreviations.py      # Step 4: merges all three sources → master
│   │   └── run_article_abbreviations.py # ORCHESTRATOR: runs steps 3a + 3b + 4 end-to-end
│   │
│   ├── generate_abbreviation_diff.py   # Compares master output vs Indication_Oncology reference
│   └── test_keyword_difference.py      # Simpler category-level comparison script (top 85 rows)
│
├── utils/
│   ├── azure_client.py     # Creates AzureOpenAI client from .env
│   ├── cache.py            # load/save cache JSON helpers
│   └── json_utils.py       # read_json, write_json, fingerprint, entity_id, normalize
│
├── .env                    # Local credentials (gitignored)
├── .env.example            # Credential template
├── requirements.txt        # Python dependencies
└── CONTEXT.md              # This file
```

---

## Data Pipeline — Step by Step

```
ICD_raw_2025(in).csv
        │
        ▼  Step 1: src/CategoryCreation/add_disease_categories.py
ICD_with_categories.csv          (LLM assigns a short category label to each description)
        │
        ▼  Step 2: src/pipelines/build_input.py
data/canonical_entities.json     (deduplicates to unique category+description_2 pairs)
        │
        ├──▶  Step 3a: article_abbreviation.py  (RAG: PubMed + ClinicalTrials evidence)
        │         → category_abbreviations.json
        │         → description_abbreviations.json
        │
        ├──▶  Step 3b: llm_abbreviation.py      (LLM-only, no external KB)
        │         → llm_abbreviations.json
        │
        ▼  Step 4: merge_abbreviations.py
data/master_abbreviations.json   (merged, deduplicated final_abbreviations per entity)
```

The orchestrator `run_article_abbreviations.py` runs steps 3a + 3b + 4 in one command.

---

## Key Files

| File | Role |
|---|---|
| `data/canonical_entities.json` | **Primary input** for all abbreviation steps |
| `data/master_abbreviations.json` | **Primary output** — use this downstream |
| `config/config.py` | Single source of truth for all file paths |
| `src/pipelines/run_article_abbreviations.py` | Main entry point for the pipeline |

---

## Master Output Record Structure

Each record in `master_abbreviations.json`:

```json
{
  "category_description2": "liver cancer|malignant neoplasm of liver and intrahepatic bile ducts",
  "category": "Liver Cancer",
  "description_2": "Malignant neoplasm of liver and intrahepatic bile ducts",
  "payload_category":      { "category": "Liver Cancer" },
  "abbreviations_category": ["Liver Cancer", "HCC", "Hepatoma"],
  "payload_description":   { "description_2": "Malignant neoplasm of liver..." },
  "abbreviations_description": ["Hepatocellular Carcinoma", "ICC", "Primary Liver Cancer"],
  "abbreviations_llm":     ["Liver Cancer", "Liver Carcinoma", "HCC", "Hepatoma"],
  "final_abbreviations":   ["Liver Cancer", "HCC", "Hepatoma", "Hepatocellular Carcinoma", "ICC", "Primary Liver Cancer", "Liver Carcinoma"]
}
```

`final_abbreviations` is the deduplicated union of all three sources with 404 sentinels removed. This is the field used downstream.

---

## Abbreviation Generation — Three Strategies

### Strategy 1 — RAG (article_abbreviation.py)
- For each category, flushes stale KB files, fetches fresh PubMed abstracts and ClinicalTrials studies
- Runs in two modes: `category` (queries by category name) and `description` (queries by description_2)
- Evidence is filtered to only records mentioning entity-specific tokens
- LLM is instructed to extract aliases supported by the evidence only
- Returns `["404"]` when evidence doesn't support any alias

### Strategy 2 — LLM-only (llm_abbreviation.py)
- Uses only the canonical `category` + `description_2` as input
- No external knowledge base — relies entirely on the LLM's clinical knowledge
- Generates the full practical alias family: common name, carcinoma form, malignancy form, acronyms, anatomical synonyms, lay terms

### Strategy 3 — Merge (merge_abbreviations.py)
- Combines all three sources keyed by `category_description2`
- Deduplicates case-insensitively, drops all 404 sentinels
- Falls back to `["404"]` only when all three sources returned nothing

---

## Caching

All three strategies use SHA-256 fingerprint-based caches stored in `data/cache/`. Cache keys include the prompt version, so bumping `PROMPT_VERSION` in a script automatically invalidates old entries and forces reprocessing.

---

## Orchestrator Usage

```bash
# Full run — all categories, all steps (article + LLM + merge)
python src/pipelines/run_article_abbreviations.py

# Single category test run
python src/pipelines/run_article_abbreviations.py --category "Liver Cancer"

# Force reprocess (ignore cache)
python src/pipelines/run_article_abbreviations.py --category "Liver Cancer" --refresh-cache

# Article step only (skip LLM and merge)
python src/pipelines/run_article_abbreviations.py --category "Liver Cancer" --skip-llm --skip-merge

# Article + LLM only (skip merge)
python src/pipelines/run_article_abbreviations.py --category "Liver Cancer" --skip-merge
```

When `--category` is used, the orchestrator upserts only that category's records into the output files — records for all other categories are preserved.

---

## Quality Analysis Scripts

```bash
# Compare master_abbreviations.json vs Indication_Oncology(in).csv
# Outputs: data/abbreviation_difference.csv
python src/generate_abbreviation_diff.py

# Simpler category-level comparison (top 85 rows of reference CSV)
# Outputs: data/category_abbreviation_comparison.csv
python src/test_keyword_difference.py
```

Both scripts produce CSVs with columns: Category, Category Abbreviation, Descriptive Abbreviation, Master Abbreviation, Correct Abbreviation (from reference), Difference (in reference but missing from master).

---

## Environment Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Copy and fill credentials
cp .env.example .env
```

Required `.env` values:
```
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=...
AZURE_OPENAI_API_VERSION=2025-01-01-preview
AZURE_OPENAI_DEPLOYMENT=...
```

---

## Known Issues / Notes

- `config/config.py` still has `PUBMED = DATA_DIR / "top10_pubmed_abstracts.txt"` — should be `.json` after the pubmed.py rewrite
- `cte.py` now accepts `keyword: str` (single string only); the orchestrator currently passes a list — needs to be updated to pass only the category string
- `pubmed.py` now fetches via XML and no longer applies the `free full text` filter, giving broader search coverage
- `icd_category_cache_v2.json` at project root is a legacy file from before the data directory restructuring
