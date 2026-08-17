import json
import re
import pandas as pd


# ============================================================
# INPUT FILES
# ============================================================

CATEGORY_JSON = "data/category_abbreviations.json"
DESCRIPTION_JSON = "data/description_abbreviations.json"
ONCOLOGY_CSV = "data/Indication_Oncology(in).csv"

OUTPUT_CSV = "data/category_abbreviation_comparison.csv"

# Only first 85 rows from Oncology CSV
TOP_N_ROWS = 85


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def normalize_category(value):
    """Normalize category names for matching."""

    if pd.isna(value):
        return ""

    value = str(value).strip().lower()
    value = re.sub(r"\s+", " ", value)

    return value


def clean_value(value):
    """Clean a value."""

    if pd.isna(value):
        return ""

    return str(value).strip()


def unique_preserve_order(values):
    """
    Remove duplicate values while preserving order.
    Duplicate checking is case-insensitive.
    """

    result = []
    seen = set()

    for value in values:

        value = clean_value(value)

        if not value:
            continue

        # Ignore placeholder/error value
        if value == "404":
            continue

        key = value.lower()

        if key not in seen:
            seen.add(key)
            result.append(value)

    return result


# ============================================================
# READ ORIGINAL JSON FILE
# ============================================================

def read_abbreviation_json(json_file):
    """
    Read the new JSON structure.

    Structure:

    [
        {
            "category": "Lip Cancer",
            "description_2": "...",
            "abbreviations": [
                "Lip Cancer",
                "Lip Carcinoma",
                "LSCC"
            ]
        }
    ]

    Returns:

    {
        normalized_category: {
            "category": original_category,
            "abbreviations": [...]
        }
    }
    """

    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    result = {}

    # JSON is a list of records
    if not isinstance(data, list):
        raise ValueError(
            f"Expected a list in {json_file}, "
            f"but found {type(data).__name__}"
        )

    for item in data:

        category = clean_value(item.get("category", ""))

        if not category:
            continue

        normalized_category = normalize_category(category)

        abbreviations = item.get("abbreviations", [])

        if not isinstance(abbreviations, list):
            abbreviations = []

        abbreviations = unique_preserve_order(abbreviations)

        # ----------------------------------------------------
        # Multiple records may belong to the same category
        # ----------------------------------------------------

        if normalized_category not in result:

            result[normalized_category] = {
                "category": category,
                "abbreviations": []
            }

        result[normalized_category]["abbreviations"].extend(
            abbreviations
        )

    # Remove duplicates after combining records
    for normalized_category in result:

        result[normalized_category]["abbreviations"] = (
            unique_preserve_order(
                result[normalized_category]["abbreviations"]
            )
        )

    return result


# ============================================================
# READ CATEGORY + DESCRIPTION JSON
# ============================================================

category_data = read_abbreviation_json(CATEGORY_JSON)

description_data = read_abbreviation_json(DESCRIPTION_JSON)


# ============================================================
# READ ONCOLOGY CSV
# ============================================================

df_oncology = pd.read_csv(ONCOLOGY_CSV)

# Only first 85 rows
df_oncology = df_oncology.head(TOP_N_ROWS).copy()


# ============================================================
# BUILD ONCOLOGY CATEGORY -> ABBREVIATIONS
# ============================================================

oncology_data = {}


for _, row in df_oncology.iterrows():

    category = clean_value(row["category"])

    if not category:
        continue

    normalized_category = normalize_category(category)

    # --------------------------------------------------------
    # Get abbreviations directly from Oncology CSV
    # --------------------------------------------------------

    oncology_abbreviations = row["abbreviations"]

    if pd.isna(oncology_abbreviations):

        oncology_abbreviations = []

    else:

        oncology_abbreviations = [
            clean_value(x)
            for x in str(oncology_abbreviations).split("|")
            if clean_value(x)
        ]

    # --------------------------------------------------------
    # Create category entry
    # --------------------------------------------------------

    if normalized_category not in oncology_data:

        oncology_data[normalized_category] = {
            "category": category,
            "abbreviations": []
        }

    oncology_data[normalized_category]["abbreviations"].extend(
        oncology_abbreviations
    )


# ============================================================
# REMOVE DUPLICATES FROM ONCOLOGY DATA
# ============================================================

for normalized_category in oncology_data:

    oncology_data[normalized_category]["abbreviations"] = (
        unique_preserve_order(
            oncology_data[normalized_category]["abbreviations"]
        )
    )


# ============================================================
# CREATE FINAL DATA
# ============================================================

# Categories appearing in either generated JSON
all_categories = (
    set(category_data.keys())
    | set(description_data.keys())
)


output_rows = []


for normalized_category in sorted(all_categories):

    # --------------------------------------------------------
    # CATEGORY ABBREVIATIONS
    # --------------------------------------------------------

    category_info = category_data.get(
        normalized_category,
        {}
    )

    category_abbreviations = category_info.get(
        "abbreviations",
        []
    )


    # --------------------------------------------------------
    # DESCRIPTIVE ABBREVIATIONS
    # --------------------------------------------------------

    description_info = description_data.get(
        normalized_category,
        {}
    )

    descriptive_abbreviations = description_info.get(
        "abbreviations",
        []
    )


    # --------------------------------------------------------
    # CATEGORY NAME
    # --------------------------------------------------------

    category = (
        category_info.get("category")
        or description_info.get("category")
        or normalized_category
    )


    # --------------------------------------------------------
    # MASTER ABBREVIATION
    #
    # Master =
    # Category Abbreviation
    # +
    # Descriptive Abbreviation
    # --------------------------------------------------------

    master_abbreviations = unique_preserve_order(
        category_abbreviations
        + descriptive_abbreviations
    )


    # --------------------------------------------------------
    # ORIGINAL ABBREVIATIONS FROM ONCOLOGY
    # --------------------------------------------------------

    oncology_info = oncology_data.get(
        normalized_category,
        {}
    )

    correct_abbreviations = oncology_info.get(
        "abbreviations",
        []
    )


    # --------------------------------------------------------
    # DIFFERENCE
    #
    # Original Oncology abbreviations
    # that are NOT present in Master
    # --------------------------------------------------------

    master_lower = {
        x.lower()
        for x in master_abbreviations
    }

    difference = [
        x
        for x in correct_abbreviations
        if x.lower() not in master_lower
    ]


    # --------------------------------------------------------
    # ADD ROW
    # --------------------------------------------------------

    output_rows.append({

        "Category": category,

        "Category Abbreviation": " | ".join(
            category_abbreviations
        ),

        "Descriptive Abbreviation": " | ".join(
            descriptive_abbreviations
        ),

        "Master Abbreviation": " | ".join(
            master_abbreviations
        ),

        "Correct Abbreviation": " | ".join(
            correct_abbreviations
        ),

        "Difference": " | ".join(
            difference
        )
    })


# ============================================================
# CREATE DATAFRAME
# ============================================================

output_df = pd.DataFrame(output_rows)


# ============================================================
# SAVE CSV
# ============================================================

output_df.to_csv(
    OUTPUT_CSV,
    index=False,
    encoding="utf-8-sig"
)


# ============================================================
# SUMMARY
# ============================================================

print("=" * 60)
print("CSV CREATED SUCCESSFULLY")
print("=" * 60)

print(f"Output file              : {OUTPUT_CSV}")
print(f"Categories               : {len(output_df)}")
print(f"Oncology rows considered : {TOP_N_ROWS}")

print("\nColumns:")

for column in output_df.columns:
    print(f" - {column}")

print("\nSample output:")

print(
    output_df.head(10).to_string(index=False)
)