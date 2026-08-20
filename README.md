# Auxo-Oncology — Abbreviation Dictionary Generator

A comprehensive clinical abbreviation and alias dictionary generator for ICD-coded diagnoses across oncology, cardiovascular, and metabolic domains. Combines three independent generation strategies (RAG-grounded and LLM-only) into a single, deduplicated, clinically validated output.

## 🎯 Purpose

This project transforms raw ICD-10 codes into a rich abbreviation dictionary where each entity gets a `final_abbreviations` list synthesized from:
- **RAG Strategy**: Evidence-grounded aliases from PubMed abstracts and ClinicalTrials.gov
- **LLM Strategy**: Pure LLM-generated aliases using clinical knowledge
- **Merge Strategy**: Intelligent deduplication across all three sources

The output (`master_abbreviations.json`) is used downstream for entity recognition, matching, and clinical data harmonization.

---

## 🛠️ Technology Stack

| Component | Technology |
|---|---|
| **Language** | Python 3.9+ |
| **LLM** | Azure OpenAI (GPT-4o) via `openai` SDK |
| **Evidence Sources** | PubMed (Biopython/Entrez), ClinicalTrials.gov (REST API v2) |
| **Data Format** | CSV (input), JSON (processing & output) |
| **Key Libraries** | `pandas`, `biopython`, `httpx`, `python-dotenv`, `openai` |

---

## 📦 Installation

### Prerequisites
- Python 3.9 or later
- Azure OpenAI API key and endpoint
- Internet connection (for PubMed and ClinicalTrials.gov APIs)

### Setup

1. **Clone or extract the repository**
   ```bash
   cd python
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv env
   source env/bin/activate  # On Windows: env\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure credentials**
   ```bash
   cp .env.example .env
   # Edit .env with your Azure OpenAI credentials:
   # OPENAI_API_KEY=your_key_here
   # OPENAI_API_VERSION=2024-08-01
   # AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
   ```

---

## 🚀 Quick Start

### Run the Full Pipeline

```bash
# Process all categories through all steps (article + LLM + merge)
python src/pipelines/run_article_abbreviations.py
```

This generates `data/master_abbreviations.json` with final abbreviations for all ICD entities.

### Test with a Single Category

```bash
# Process only "Liver Cancer" category
python src/pipelines/run_article_abbreviations.py --category "Liver Cancer"

# Control knowledge base size (default: 5 articles per query)
python src/pipelines/run_article_abbreviations.py --top-k 10

# Single category with custom KB size
python src/pipelines/run_article_abbreviations.py --category "Lung Cancer" --top-k 8

# Run only article step (skip LLM and merge)
python src/pipelines/run_article_abbreviations.py --skip-llm

# Run article + LLM only (skip final merge)
python src/pipelines/run_article_abbreviations.py --skip-merge
```

### Quality Checks

```bash
# Compare master output vs reference abbreviations
python src/generate_abbreviation_diff.py
# Output: data/abbreviation_difference.csv

# Simpler category-level comparison (top 85 rows)
python src/test_keyword_difference.py
# Output: data/category_abbreviation_comparison.csv
```

---

## 📋 Project Structure

```
python/
│
├── config/
│   └── config.py                   # Central path constants for all data files
│
├── data/                           # Input/output data files
│   ├── ICD_raw_2025(in).csv        # Raw ICD-10 codes + descriptions (INPUT)
│   ├── ICD_with_categories.csv     # After category assignment (intermediate)
│   ├── Indication_Oncology(in).csv # Ground truth reference for comparison
│   ├── canonical_entities.json     # Deduplicated entities (PRIMARY INPUT)
│   ├── category_abbreviations.json # RAG category-query results
│   ├── description_abbreviations.json # RAG description-query results
│   ├── llm_abbreviations.json      # LLM-only results
│   ├── master_abbreviations.json   # FINAL OUTPUT (JSON format)
│   ├── master_abbreviations.csv    # FINAL OUTPUT (CSV format)
│   ├── top10_pubmed_abstracts.json # PubMed evidence (temporary, flushed between categories)
│   ├── top_10_clinical_trials.json # ClinicalTrials evidence (temporary, flushed between categories)
│   └── cache/                      # (Currently unused; reserved for future optimization)
│
├── src/
│   ├── CategoryCreation/
│   │   └── add_disease_categories.py   # Step 1: LLM assigns category labels
│   │
│   ├── DataExtractionScripts/
│   │   ├── pubmed.py                   # Fetches PubMed abstracts
│   │   └── cte.py                      # Fetches ClinicalTrials.gov studies
│   │
│   ├── pipelines/
│   │   ├── build_input.py              # Step 2: builds canonical_entities.json
│   │   ├── article_abbreviation.py     # Step 3a: RAG generation
│   │   ├── llm_abbreviation.py         # Step 3b: LLM-only generation
│   │   ├── merge_abbreviations.py      # Step 4: merges all sources
│   │   └── run_article_abbreviations.py # ORCHESTRATOR (main entry point)
│   │
│   ├── rag/                            # RAG pipeline components
│   ├── generate_abbreviation_diff.py   # Quality check: compare vs reference
│   └── test_keyword_difference.py      # Quality check: category-level comparison
│
├── utils/
│   ├── azure_client.py     # Creates AzureOpenAI client from .env
│   ├── cache.py            # load/save cache JSON helpers
│   └── json_utils.py       # read_json, write_json, fingerprint, entity_id, normalize
│
├── .env                    # Local credentials (gitignored)
├── .env.example            # Credential template
├── requirements.txt        # Python dependencies
├── CONTEXT.md              # Detailed technical documentation
└── README.md               # This file
```

---

## 🔄 Data Pipeline

```
ICD_raw_2025(in).csv
        │
        ▼  Step 1: add_disease_categories.py
ICD_with_categories.csv    (LLM assigns category labels)
        │
        ▼  Step 2: build_input.py
canonical_entities.json    (deduplicate to unique category+description pairs)
        │
        ├──▶  Step 3a: article_abbreviation.py  (RAG: PubMed + ClinicalTrials)
        │     → category_abbreviations.json
        │     → description_abbreviations.json
        │
        ├──▶  Step 3b: llm_abbreviation.py      (LLM-only, pure knowledge)
        │     → llm_abbreviations.json
        │
        ▼  Step 4: merge_abbreviations.py
master_abbreviations.json  (FINAL: merged, deduplicated per entity)
master_abbreviations.csv   (FINAL: same data in readable CSV format)
```

**The orchestrator** (`run_article_abbreviations.py`) automatically runs Steps 3, 4, and beyond. Both JSON and CSV outputs are generated in the final merge step.

---

## 📊 Master Output Example

Each record in `master_abbreviations.json`:

```json
{
  "category_description2": "liver cancer|malignant neoplasm of liver and intrahepatic bile ducts",
  "category": "Liver Cancer",
  "description_2": "Malignant neoplasm of liver and intrahepatic bile ducts",
  "description_3": "Additional description from canonical entities (if available)",
  "payload_category": {
    "category": "Liver Cancer",
    "evidence_count": 5
  },
  "abbreviations_category": {
    "pubmed": ["HCC", "Hepatoma"],
    "clinical_trials": ["Liver Cancer", "Hepatocellular Carcinoma"]
  },
  "payload_description": {
    "description_2": "Malignant neoplasm of liver...",
    "evidence_count": 8
  },
  "abbreviations_description": {
    "pubmed": ["Hepatocellular Carcinoma", "ICC"],
    "clinical_trials": ["Primary Liver Cancer"]
  },
  "payload_llm": {
    "strategy": "llm_only",
    "model": "gpt-4o"
  },
  "abbreviations_llm": ["Liver Cancer", "Liver Carcinoma", "HCC", "Hepatoma"],
  "final_abbreviations": [
    "HCC", "Hepatoma", "Liver Cancer", "Hepatocellular Carcinoma", 
    "ICC", "Primary Liver Cancer", "Liver Carcinoma"
  ]
}
```

**Key fields**:
- `category_description2` — Unique composite key
- `description_3` — Additional description for traceability
- `abbreviations_category` & `abbreviations_description` — Separated by source (pubmed/clinical_trials)
- `payload_*` — Metadata fields for debugging and traceability
- `final_abbreviations` — **Deduplicated union used downstream** for entity matching

---

## 🧠 Three Abbreviation Generation Strategies

### Strategy 1: RAG-Grounded (article_abbreviation.py)
- **Per-Category Processing**: Fetches fresh evidence for each category separately
- **Two Query Modes**:
  - `category` — searches PubMed/ClinicalTrials by category name
  - `description` — searches by full description_2, with category fallback
- **Token-Based Relevance**: Scores KB records by entity-specific token overlap (filters stopwords)
- **KB Normalization**: PubMed records and ClinicalTrials trials are normalized to consistent format
- **Quality Control**: Only extracts aliases explicitly mentioned in evidence
- **Output**: `category_abbreviations.json` and `description_abbreviations.json` (separated by source)
- **Fallback**: Returns `["404"]` when evidence doesn't support any alias

### Strategy 2: LLM-Only (llm_abbreviation.py)
- **Knowledge Base**: Pure LLM clinical knowledge (GPT-4o, no external sources)
- **No External Data**: Uses only category + description_2
- **Generation Priority**:
  1. Canonical common disease names
  2. Site-based variants (Cancer, Carcinoma, Malignancy forms)
  3. Established histological subtypes
  4. Widely used acronyms
  5. Anatomical synonyms through lay/clinical terms
  6. Up to 10 total unique variants
- **Output**: `llm_abbreviations.json`
- **Advantage**: Covers aliases not found in current literature

### Strategy 3: Merge (merge_abbreviations.py)
- **Combines All Sources**: Merges category, description, and LLM abbreviations
- **Deduplication**: Case-insensitive merge ("HCC" and "hcc" → single entry)
- **Output Format**: Both JSON and CSV outputs
  - JSON: `master_abbreviations.json` (detailed with payloads)
  - CSV: `master_abbreviations.csv` (readable table format)
- **404 Handling**: Drops all `"404"` sentinels; returns `["404"]` only when all sources empty
- **ICD Update**: Optionally updates ICD CSV with final abbreviations

---

## ⚙️ Configuration

All file paths are centralized in [config/config.py](config/config.py). Update paths there if you move data files.

### .env Credentials

```env
# Azure OpenAI Configuration (required)
OPENAI_API_KEY=your_azure_openai_api_key_here
OPENAI_API_VERSION=2024-08-01
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=your-deployment-name  # e.g., "gpt-4o"
```

**Security**: Keep `.env` out of version control (already in `.gitignore`). Never commit credentials.

For reference, see `.env.example` in the repository.

---

## 💾 Evidence Fetching & KB Management

### How It Works
- **Per-Category KB Fetching**: PubMed and ClinicalTrials evidence is fetched fresh for each category
- **KB Flush Between Categories**: The orchestrator deletes old evidence files between categories to prevent cross-contamination
- **Temporary Files**: `data/top10_pubmed_abstracts.json` and `data/top_10_clinical_trials.json` are working files, not persistent caches
- **No Fingerprint Caching**: Abbreviation generation results are not formally cached; regenerated on each run

### Optimizing for Performance
- Use `--category` flag only when testing specific entities
- Run full pipeline once per dataset update to minimize external API calls
- Monitor PubMed and ClinicalTrials.gov rate limits in output logs
- Consider caching if doing many repeated runs on the same data

---

## 📖 Usage Examples

### Full Pipeline with All Categories
```bash
python src/pipelines/run_article_abbreviations.py
```
Processes all categories and generates `master_abbreviations.json`.

### Single Category Processing
```bash
python src/pipelines/run_article_abbreviations.py --category "Breast Cancer"
```
Upserts only "Breast Cancer" records; other categories are preserved.

### Staging/Testing
```bash
# Test single category with custom KB size
python src/pipelines/run_article_abbreviations.py --category "Liver Cancer" --top-k 8

# Skip LLM step
python src/pipelines/run_article_abbreviations.py --skip-llm

# Skip merge step
python src/pipelines/run_article_abbreviations.py --skip-merge

# Combine options: single category, skip merge, custom KB size
python src/pipelines/run_article_abbreviations.py --category "Breast Cancer" --skip-merge --top-k 5
```

### Quality Checks
```bash
# Full comparison against reference
python src/generate_abbreviation_diff.py

# Quick category-level check
python src/test_keyword_difference.py
```

---

## 🔑 Key Files

| File | Purpose |
|---|---|
| **data/canonical_entities.json** | Primary input to all abbreviation steps |
| **data/master_abbreviations.json** | Primary output (JSON) — final abbreviations for downstream use |
| **data/master_abbreviations.csv** | Primary output (CSV) — same data in readable table format |
| **config/config.py** | Single source of truth for all file paths |
| **src/pipelines/run_article_abbreviations.py** | Main entry point for the entire pipeline |
| **src/DataExtractionScripts/pubmed.py** | PubMed evidence fetching |
| **src/DataExtractionScripts/cte.py** | ClinicalTrials.gov evidence fetching |

---

## 📝 Dependencies

```
pandas>=2.0                    # Data processing
google-genai>=1.0              # Google AI integration
python-dotenv>=1.0             # Environment variable management
httpx>=0.28                    # HTTP client
truststore>=0.10               # SSL certificate management
openai>=1.0                    # Azure OpenAI API
biopython>=1.80                # PubMed/Entrez integration
```

Install all at once:
```bash
pip install -r requirements.txt
```

---

## 🤝 Contributing

For bug reports or feature requests, please refer to the team. For code changes:

1. Test with a single category first:
   ```bash
   python src/pipelines/run_article_abbreviations.py --category "Test Category" --top-k 5
   ```
2. Review generated abbreviations in `data/master_abbreviations.json` and `data/master_abbreviations.csv`
3. Run quality checks:
   ```bash
   python src/generate_abbreviation_diff.py
   ```
4. Verify both JSON and CSV outputs are present and valid

---

## ⚡ Command-Line Options

| Option | Type | Default | Description |
|---|---|---|---|
| `--category TEXT` | string | (none) | Process only one category (exact match). For testing. |
| `--top-k INT` | integer | 5 | Maximum KB records per evidence query (controls PubMed/ClinicalTrials volume). |
| `--skip-llm` | flag | (not set) | Skip LLM-only abbreviation generation. |
| `--skip-merge` | flag | (not set) | Skip final merge step. |

**Examples**:
```bash
python src/pipelines/run_article_abbreviations.py --category "Liver Cancer" --top-k 10
python src/pipelines/run_article_abbreviations.py --skip-llm --skip-merge
python src/pipelines/run_article_abbreviations.py --top-k 3  # Quick run with minimal evidence
```

---

## 📚 For More Details

See [CONTEXT.md](CONTEXT.md) for:
- Detailed architecture and data flow
- Token-based relevance scoring algorithm
- KB fetching and normalization strategies
- LLM prompt engineering and generation priorities
- Data format reference for all intermediate files
- Known issues and troubleshooting

---

## 📄 License

Proprietary — ProcDNA Analytics Pvt. Ltd.

---

## 🆘 Support

For issues or questions:
- Check [CONTEXT.md](CONTEXT.md) for detailed technical documentation (architecture, strategies, token scoring, etc.)
- Review `.env.example` for credential setup
- Ensure all dependencies are installed: `pip install -r requirements.txt`
- Test with a single category: `python src/pipelines/run_article_abbreviations.py --category "Test Category"`
- Check both JSON and CSV outputs in `data/master_abbreviations.*`
- Review `description_3` field for additional entity context (if available)

---

**Last Updated**: 2026-08-20  
**Version**: 1.0  
**Status**: Production-ready
