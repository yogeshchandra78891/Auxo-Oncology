"""Central locations for data produced by the project pipelines."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
CANONICAL_INPUT = DATA_DIR / "canonical_entities.json"
CATEGORY_OUTPUT = DATA_DIR / "category_abbreviations.json"
DESCRIPTION_OUTPUT = DATA_DIR / "description_abbreviations.json"
LLM_OUTPUT = DATA_DIR / "llm_abbreviations.json"
MASTER_OUTPUT = DATA_DIR / "master_abbreviations.json"
PUBMED = DATA_DIR / "top10_pubmed_abstracts.json"
CLINICAL_TRIALS = DATA_DIR / "top_10_clinical_trials.json"
