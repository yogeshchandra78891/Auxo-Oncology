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

# Force reprocess (ignore cache)
python src/pipelines/run_article_abbreviations.py --category "Liver Cancer" --refresh-cache

# Run only article step (skip LLM and merge)
python src/pipelines/run_article_abbreviations.py --category "Liver Cancer" --skip-llm --skip-merge

# Run article + LLM only (skip final merge)
python src/pipelines/run_article_abbreviations.py --category "Liver Cancer" --skip-merge
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
│   ├── master_abbreviations.json   # FINAL OUTPUT (most important)
│   ├── top10_pubmed_abstracts.json # PubMed evidence cache
│   ├── top_10_clinical_trials.json # ClinicalTrials evidence cache
│   └── cache/                      # SHA-256 fingerprint-based caches
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
```

**The orchestrator** (`run_article_abbreviations.py`) automatically runs Steps 3, 4, and beyond.

---

## 📊 Master Output Example

Each record in `master_abbreviations.json`:

```json
{
  "category_description2": "liver cancer|malignant neoplasm of liver and intrahepatic bile ducts",
  "category": "Liver Cancer",
  "description_2": "Malignant neoplasm of liver and intrahepatic bile ducts",
  "payload_category": { "category": "Liver Cancer" },
  "abbreviations_category": ["Liver Cancer", "HCC", "Hepatoma"],
  "payload_description": { "description_2": "Malignant neoplasm of liver..." },
  "abbreviations_description": ["Hepatocellular Carcinoma", "ICC", "Primary Liver Cancer"],
  "abbreviations_llm": ["Liver Cancer", "Liver Carcinoma", "HCC", "Hepatoma"],
  "final_abbreviations": [
    "Liver Cancer", "HCC", "Hepatoma", "Hepatocellular Carcinoma", 
    "ICC", "Primary Liver Cancer", "Liver Carcinoma"
  ]
}
```

**Key field**: `final_abbreviations` — the deduplicated union of all three strategies. This is the field used downstream for entity matching.

---

## 🧠 Three Abbreviation Generation Strategies

### Strategy 1: RAG-Grounded (article_abbreviation.py)
- **Evidence Source**: Fresh PubMed abstracts + ClinicalTrials studies per category
- **Modes**: 
  - `category` — queries by category name
  - `description` — queries by full description
- **Quality Control**: Only extracts aliases explicitly mentioned in evidence
- **Output**: `category_abbreviations.json`, `description_abbreviations.json`
- **Fallback**: Returns `["404"]` when evidence doesn't support any alias

### Strategy 2: LLM-Only (llm_abbreviation.py)
- **Knowledge Base**: Pure LLM clinical knowledge (no external sources)
- **Input**: Just category + description_2
- **Scope**: Full practical alias family (common names, carcinoma forms, acronyms, lay terms)
- **Output**: `llm_abbreviations.json`
- **Advantage**: Covers aliases not found in current literature

### Strategy 3: Merge (merge_abbreviations.py)
- **Process**: Combines all three sources, deduplicated by key `category_description2`
- **Case-Insensitive**: Merges "HCC" and "hcc" into one
- **404 Handling**: Drops all `"404"` sentinels, returns `["404"]` only when all three are empty
- **Output**: `master_abbreviations.json`

---

## ⚙️ Configuration

All file paths are centralized in [config/config.py](config/config.py). Update paths there if you move data files.

### .env Credentials

```env
OPENAI_API_KEY=sk-...
OPENAI_API_VERSION=2024-08-01
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
```

---

## 💾 Caching

All three strategies use **SHA-256 fingerprint-based caching** stored in `data/cache/`:

- `category_abbreviations_cache.json`
- `description_abbreviations_cache.json`
- `llm_abbreviations_cache.json`

Cache keys include prompt version, so bumping `PROMPT_VERSION` in any script automatically invalidates old entries and forces reprocessing.

**Force Cache Refresh**:
```bash
python src/pipelines/run_article_abbreviations.py --refresh-cache
```

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
# Test with refresh
python src/pipelines/run_article_abbreviations.py --category "Liver Cancer" --refresh-cache

# Skip LLM step
python src/pipelines/run_article_abbreviations.py --category "Liver Cancer" --skip-llm

# Skip both LLM and merge
python src/pipelines/run_article_abbreviations.py --category "Liver Cancer" --skip-merge
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
| **data/master_abbreviations.json** | Primary output — final abbreviations for downstream use |
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
   python src/pipelines/run_article_abbreviations.py --category "Test Category" --refresh-cache
   ```
2. Review generated abbreviations in `master_abbreviations.json`
3. Run quality checks:
   ```bash
   python src/generate_abbreviation_diff.py
   ```

---

## 📚 For More Details

See [CONTEXT.md](CONTEXT.md) for:
- Detailed architecture and data flow
- Advanced configuration options
- Troubleshooting and performance tuning
- In-depth strategy explanations

---

## 📄 License

Proprietary — ProcDNA Analytics Pvt. Ltd.

---

## 🆘 Support

For issues or questions:
- Check [CONTEXT.md](CONTEXT.md) for detailed technical documentation
- Review `.env.example` for configuration
- Ensure all dependencies are installed: `pip install -r requirements.txt`
- Test with a single category and `--refresh-cache` flag

---

**Last Updated**: 2026-08-20
