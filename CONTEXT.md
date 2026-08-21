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
  "description_3": "Additional descriptive field from canonical entities (if available)",
  "payload_category": {
    "category": "Liver Cancer",
    "evidence": {...}
  },
  "abbreviations_category": {
    "pubmed": ["HCC", "Hepatoma"],
    "clinical_trials": ["Liver Cancer", "Hepatocellular Carcinoma"]
  },
  "payload_description": {
    "description_2": "Malignant neoplasm of liver...",
    "evidence": {...}
  },
  "abbreviations_description": {
    "pubmed": ["Hepatocellular Carcinoma", "ICC"],
    "clinical_trials": ["Primary Liver Cancer", "HCC"]
  },
  "payload_llm": {
    "strategy": "llm_only",
    "context": "..."
  },
  "abbreviations_llm": ["Liver Cancer", "Liver Carcinoma", "HCC", "Hepatoma"],
  "final_abbreviations": [
    "HCC", "Hepatoma", "Liver Cancer", "Hepatocellular Carcinoma", 
    "ICC", "Primary Liver Cancer", "Liver Carcinoma"
  ]
}
```

**Key fields**:
- `category_description2` — Unique composite key: `category|description_2`
- `description_3` — Additional description field for traceability
- `abbreviations_category` — Dict with "pubmed" and "clinical_trials" lists
- `abbreviations_description` — Dict with "pubmed" and "clinical_trials" lists (description-query mode)
- `abbreviations_llm` — List of LLM-only generated aliases
- `payload_*` — Metadata for each strategy (for debugging and traceability)
- `final_abbreviations` — **Deduplicated union of all three strategies** — this field is used downstream for entity matching

### CSV Output
The merge step also generates `master_abbreviations.csv` with columns:
- `category_desc2` — Composite key
- `category` — Disease category name
- `description2` — ICD description
- `description3` — Additional description (if available)
- `pubmed abbreviations` — Comma-separated PubMed abbreviations
- `clinical abbreviations` — Comma-separated ClinicalTrials abbreviations
- `llm abbreviations` — Comma-separated LLM abbreviations
- `final abbreviations` — Comma-separated final deduplicated list

---

## Abbreviation Generation — Three Strategies

### Strategy 1 — RAG (article_abbreviation.py)
- **Per-Category Orchestration**: For each category:
  - Flush stale KB files (old PubMed and ClinicalTrials data)
  - Fetch fresh PubMed abstracts for that category
  - Fetch fresh ClinicalTrials.gov studies for that category
  - Build in-memory knowledge base from normalized evidence

- **Two Query Modes**:
  - `category` mode: Search PubMed/ClinicalTrials by category name
  - `description` mode: Search by full description_2, with category fallback

- **Token-Based Relevance Scoring**:
  - Tokenizes query and knowledge base records
  - Filters generic stopwords (e.g., "cancer", "disease", "malignant", "of")
  - Scores KB records by entity-specific token overlap
  - Ranks results and returns top-K records as context

- **Evidence Filtering**:
  - Only extracts abbreviations explicitly mentioned in the supplied evidence
  - Stops if no relevant context found
  - Returns `["404"]` when evidence doesn't support any alias

### Strategy 2 — LLM-only (llm_abbreviation.py)
- **Input**: Only canonical `category` + `description_2` + optional previous evidence
- **No External KB**: Relies entirely on LLM's clinical knowledge
- **Comprehensive Output**: Generates practical alias family:
  - Canonical common disease names
  - Site-based variants (Cancer, Carcinoma, Malignancy, etc.)
  - Established histological subtypes
  - Widely used acronyms
  - Anatomical synonyms
  - Lay/clinical terms
  - Subsite and directional variants
  - Up to 10 unique variants per entity

- **Output Modes**: Generates with or without previous RAG evidence as reference

### Strategy 3 — Merge (merge_abbreviations.py)
- **Combines All Sources**: Merges category, description, and LLM abbreviations
- **Keyed by `category_description2`**: Unique identifier per entity
- **Case-Insensitive Deduplication**: "HCC" and "hcc" merge into one entry
- **404 Sentinel Handling**: Drops all `"404"` entries, returns `["404"]` only when all sources are empty
- **Output Enrichment**:
  - Generates both JSON and CSV outputs
  - Writes `master_abbreviations.json` and `master_abbreviations.csv`
  - Updates ICD CSV with final abbreviations if requested
- **Payload Preservation**: Retains `payload_*` and `description_3` fields for traceability

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

# Control knowledge base size
python src/pipelines/run_article_abbreviations.py --top-k 10  # Default: 5 articles per query

# Single category with custom KB size
python src/pipelines/run_article_abbreviations.py --category "Lung Cancer" --top-k 8

# Article step only (skip LLM and merge)
python src/pipelines/run_article_abbreviations.py --skip-llm

# Article + LLM only (skip final merge)
python src/pipelines/run_article_abbreviations.py --skip-merge

# Skip LLM step
python src/pipelines/run_article_abbreviations.py --skip-llm --skip-merge
```

**Behavior**:
- When `--category` is used, the orchestrator processes only that category and upserts results
- Other categories' records are preserved in output files
- KB files are flushed between categories to prevent data bleed
- Each category gets fresh PubMed and ClinicalTrials evidence

**Command-line Options**:
- `--category TEXT` — Process only one category (exact match, for testing)
- `--top-k INT` — Max KB records per query (default: 5)
- `--skip-llm` — Skip LLM-only abbreviation generation
- `--skip-merge` — Skip final merge step

---

## Knowledge Base & Relevance Scoring

### KB Fetching Strategy
The orchestrator uses a two-tier fetching approach for descriptions:

1. **Primary Query**: Fetch up to 5 PubMed articles using `description_2` as the search term
2. **Fallback Top-up**: If fewer than 5 articles returned, fetch additional articles using `category` name to reach target (e.g., 10 total)
3. **ClinicalTrials**: Apply same strategy independently to ClinicalTrials.gov

This ensures rich evidence for specific descriptions while preventing evidence starvation.

### Token-Based Relevance Scoring

The `article_abbreviation.py` module scores KB records using entity-specific token overlap:

- **Tokenization**: Extracts lowercase alphanumeric tokens (3+ chars)
- **Stopwords**: Filters generic tokens:
  - Common disease words: "cancer", "disease", "disorder", "malignant", "neoplasm"
  - Common prepositions: "of", "the", "and", "or"
  - Example: "liver cancer|tumor" → tokens = {"liver", "tumor"} (cancer filtered)

- **Scoring**: For each KB record:
  - Counts entity-specific tokens that appear in the record
  - Sorts by score (descending)
  - Returns top-K records as context

### KB Normalization

**PubMed records** are normalized to:
```
{
  "source": "PubMed",
  "text": "{title} {abstract}"  # Combined title + abstract for scoring
}
```

**ClinicalTrials records** are normalized to:
```
{
  "source": "ClinicalTrials.gov",
  "text": "{title}\n{condition}\n{interventions}\n{summary}"  # Merged fields
}
```

---

## LLM-Only Strategy — Prompt Engineering

### Purpose
When RAG evidence is insufficient or missing, the LLM-only strategy generates clinically plausible abbreviations using pure LLM knowledge without external sources.

### Input
- `category` — Disease category name (e.g., "Liver Cancer")
- `description_2` — Full ICD description (e.g., "Malignant neoplasm of liver and intrahepatic bile ducts")
- Optional: Previous RAG evidence (for context)

### Generation Priority (in order)
1. **Canonical common disease names** (most clinically recognized)
2. **Site-based variants** (e.g., "Liver Cancer", "Liver Carcinoma", "Malignancy of Liver")
3. **Established histological subtypes** (if mentioned in evidence)
4. **Widely used acronyms** (e.g., "HCC" for Hepatocellular Carcinoma)
5. **Anatomical synonyms** (organ/location variations)
6. **Lay/clinical terms** (patient-friendly and professional variants)
7. **Subsite and directional variants** (e.g., left/right, upper/lower)
8. **Histology + anatomical combinations**
9. **Overlap/combination site variants**
10. **Additional variants** (up to 10 total)

### Critical Constraints
- **NO external KB usage**: Uses only category + description_2 + LLM knowledge
- **NO PubMed queries**: Pure LLM generation
- **NO ClinicalTrials queries**: Pure LLM generation
- **Deduplication**: Case-insensitive, drops "404" sentinels
- **Format**: Returns list of strings or ["404"] if generation fails

### LLM Model
Uses Azure OpenAI (GPT-4o by default) via `create_client()` in `utils/azure_client.py`

---

## Data Format Reference

### Canonical Entities (canonical_entities.json)
**Input to all abbreviation strategies**

```json
[
  {
    "category_description2": "liver cancer|malignant neoplasm of liver and intrahepatic bile ducts",
    "category": "Liver Cancer",
    "description_2": "Malignant neoplasm of liver and intrahepatic bile ducts",
    "description_3": "Optional additional description field"
  },
  ...
]
```

- **Key field**: `category_description2` — Composite key (category|description_2)
- **Purpose**: Single source of truth for all entities

### Category Abbreviations (category_abbreviations.json)
**RAG output from category-mode queries**

```json
[
  {
    "category_description2": "liver cancer|malignant neoplasm...",
    "category": "Liver Cancer",
    "description_2": "Malignant neoplasm...",
    "payload_category": { "category": "Liver Cancer", "evidence_count": 5 },
    "abbreviations": {
      "pubmed": ["HCC", "Hepatoma"],
      "clinical_trials": ["Liver Cancer", "Hepatocellular Carcinoma"]
    }
  },
  ...
]
```

### Description Abbreviations (description_abbreviations.json)
**RAG output from description-mode queries**

```json
[
  {
    "category_description2": "liver cancer|malignant neoplasm...",
    "category": "Liver Cancer",
    "description_2": "Malignant neoplasm...",
    "payload_description": { "description_2": "Malignant neoplasm...", "evidence_count": 8 },
    "abbreviations": {
      "pubmed": ["Hepatocellular Carcinoma", "ICC"],
      "clinical_trials": ["Primary Liver Cancer"]
    }
  },
  ...
]
```

### LLM Abbreviations (llm_abbreviations.json)
**LLM-only generation output**

```json
[
  {
    "category_description2": "liver cancer|malignant neoplasm...",
    "category": "Liver Cancer",
    "description_2": "Malignant neoplasm...",
    "payload_llm": { "strategy": "llm_only", "model": "gpt-4o" },
    "abbreviations": ["Liver Cancer", "Liver Carcinoma", "HCC", "Hepatoma"]
  },
  ...
]
```

### Master Abbreviations (master_abbreviations.json)
**Final merged output used downstream** — See earlier section for full structure

### Evidence Files (Temporary)
- `top10_pubmed_abstracts.json` — Fetched PubMed articles (flushed between categories)
- `top_10_clinical_trials.json` — Fetched ClinicalTrials studies (flushed between categories)

---

## Caching

PubMed and ClinicalTrials evidence is **not formally cached** in fingerprint-based caches. Instead:

- **Per-Run KB Files**: `data/top10_pubmed_abstracts.json` and `data/top_10_clinical_trials.json` are fetched fresh per category
- **KB Flush**: KB files are deleted between categories to prevent cross-contamination
- **Partial Caching**: May be added in future to optimize repeated searches

The abbreviation generation results (category, description, LLM modes) are **not cached** and regenerated on each run. To save on API calls, avoid re-running the same category in succession.

### Avoiding Redundant Fetches

To minimize external API calls:
- Use `--category` only when testing specific entities
- Run full pipeline once per complete dataset update
- Monitor PubMed and ClinicalTrials rate limits in output logs

---

## Quality Analysis Scripts

```bash
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

### Required `.env` Configuration

```env
# Azure OpenAI Configuration
OPENAI_API_KEY=your_azure_openai_api_key_here
OPENAI_API_VERSION=2024-08-01  # or your preferred API version
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=your-deployment-name

# Optional: PubMed Email (for Biopython Entrez)
# Entrez.email = "your_email@example.com"
```

**Key Secrets**:
- `OPENAI_API_KEY` — Your Azure OpenAI API key (keep private, gitignored)
- `AZURE_OPENAI_ENDPOINT` — Your Azure resource endpoint (HTTPS URL)
- `AZURE_OPENAI_DEPLOYMENT` — Name of the deployed model (e.g., "gpt-4o")
- `OPENAI_API_VERSION` — Must match your Azure OpenAI service version

The `.env` file is gitignored. See `.env.example` for the template.

---

## Known Issues / Notes

- PubMed fetching via `pubmed.py` now returns JSON with `title` and `text` (abstract) fields; ClinicalTrials returns structured JSON
- Evidence files (`top10_pubmed_abstracts.json`, `top_10_clinical_trials.json`) are flushed between categories; they are NOT meant to be persistent cache
- `icd_category_cache_v2.json` (if present in project root) is legacy and can be safely deleted
- The `description_3` field is populated from canonical entities if available; falls back to empty string
- CSV output (`master_abbreviations.csv`) is always generated alongside JSON output during merge
