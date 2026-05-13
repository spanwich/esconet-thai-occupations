"""
ESCONET v0.1 — Build script
Sources: O*NET text DB v30.2, ESCO classification v1.2.1 (en), ESCO-O*NET crosswalk v1
Output: 7 Parquet star-schema tables + 1 denormalized flat table + README
Target: queryable shared database for CHANCEDEE V3 Recommendation work
"""
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import duckdb
from pathlib import Path
import csv
import re
import hashlib

ROOT = Path("/home/claude")
ONET = ROOT / "onet" / "db_30_2_text"
ESCO = ROOT / "esco"
CROSSWALK = Path("/mnt/user-data/uploads/ONET_ESCO_crosswalk.csv")
OUT = ROOT / "esconet_build"
OUT.mkdir(exist_ok=True)


def write_parquet(df: pd.DataFrame, name: str):
    path = OUT / f"{name}.parquet"
    df.to_parquet(path, compression="snappy", index=False)
    print(f"  ✓ {name}.parquet  rows={len(df):>8,}  cols={len(df.columns):>2}  size={path.stat().st_size//1024} KB")
    return path


def stable_hash(s: str) -> str:
    """Short stable hash for pair_id."""
    return hashlib.blake2s(s.encode(), digest_size=8).hexdigest()


# ============================================================
# 1. occupations_onet
# ============================================================
print("\n[1/8] occupations_onet")
onet_occ = pd.read_csv(ONET / "Occupation Data.txt", sep="\t", dtype=str)
onet_occ.columns = ["onet_soc", "onet_title", "onet_description"]
onet_occ["soc_major_group"] = onet_occ["onet_soc"].str[:2]

# SOC major group labels (BLS standard)
SOC_MAJOR_LABELS = {
    "11": "Management",
    "13": "Business and Financial Operations",
    "15": "Computer and Mathematical",
    "17": "Architecture and Engineering",
    "19": "Life, Physical, and Social Science",
    "21": "Community and Social Service",
    "23": "Legal",
    "25": "Educational Instruction and Library",
    "27": "Arts, Design, Entertainment, Sports, and Media",
    "29": "Healthcare Practitioners and Technical",
    "31": "Healthcare Support",
    "33": "Protective Service",
    "35": "Food Preparation and Serving Related",
    "37": "Building and Grounds Cleaning and Maintenance",
    "39": "Personal Care and Service",
    "41": "Sales and Related",
    "43": "Office and Administrative Support",
    "45": "Farming, Fishing, and Forestry",
    "47": "Construction and Extraction",
    "49": "Installation, Maintenance, and Repair",
    "51": "Production",
    "53": "Transportation and Material Moving",
    "55": "Military Specific",
}
onet_occ["soc_major_group_label"] = onet_occ["soc_major_group"].map(SOC_MAJOR_LABELS)
write_parquet(onet_occ, "occupations_onet")


# ============================================================
# 2. occupations_esco
# ============================================================
print("\n[2/8] occupations_esco")
esco_occ_raw = pd.read_csv(ESCO / "occupations_en.csv", dtype=str).fillna("")
esco_occ = esco_occ_raw[esco_occ_raw["conceptType"] == "Occupation"].copy()

# Parse NACE (multi-value, comma+newline separated URIs → list of codes)
def parse_nace(s):
    if not s:
        return []
    # NACE values come as "http://data.europa.eu/ux2/nace2.1/CODE,\nhttp://..."
    parts = re.split(r"[,\n]+", s)
    codes = []
    for p in parts:
        p = p.strip()
        m = re.search(r"nace2\.1/([^/\s]+)$", p)
        if m:
            codes.append(m.group(1))
    return codes

# Parse altLabels (newline separated)
def split_alt(s):
    if not s:
        return []
    return [x.strip() for x in s.split("\n") if x.strip()]

esco_occ["nace_codes"] = esco_occ["naceCode"].apply(parse_nace)
esco_occ["alt_labels"] = esco_occ["altLabels"].apply(split_alt)
esco_occ_out = esco_occ[[
    "conceptUri", "preferredLabel", "alt_labels", "description",
    "iscoGroup", "nace_codes", "status", "modifiedDate"
]].rename(columns={
    "conceptUri": "esco_uri",
    "preferredLabel": "label_preferred",
    "description": "esco_description",
    "iscoGroup": "isco_code",
    "modifiedDate": "modified_date",
})
write_parquet(esco_occ_out, "occupations_esco")


# ============================================================
# 3. isco_groups (ISCO hierarchy lookup)
# ============================================================
print("\n[3/8] isco_groups")
isco_raw = pd.read_csv(ESCO / "ISCOGroups_en.csv", dtype=str).fillna("")
isco = isco_raw[["conceptUri", "code", "preferredLabel", "description"]].copy()
isco.columns = ["isco_uri", "isco_code", "isco_label", "isco_description"]
# Derive hierarchy: 1-digit major, 2-digit submajor, 3-digit minor, 4-digit unit
isco["isco_level"] = isco["isco_code"].str.len()
isco["isco_major_code"] = isco["isco_code"].str[:1]
isco["isco_submajor_code"] = isco["isco_code"].str[:2]
isco["isco_minor_code"] = isco["isco_code"].str[:3]
write_parquet(isco, "isco_groups")


# ============================================================
# 4. crosswalk
# ============================================================
print("\n[4/8] crosswalk")
with open(CROSSWALK, encoding="utf-8-sig") as f:
    rows = list(csv.reader(f))
# Find header row containing "O*NET Id"
header_idx = next(i for i, r in enumerate(rows) if r and r[0].strip() == "O*NET Id")
data_rows = rows[header_idx + 1:]
cw = pd.DataFrame(data_rows, columns=[
    "onet_soc", "onet_title", "onet_description_cw",
    "esco_uri", "esco_label_cw", "esco_description_cw", "match_type"
])
# Drop blank rows
cw = cw[cw["onet_soc"].str.match(r"^\d{2}-\d{4}\.\d{2}$", na=False)].copy()
# Add deterministic pair_id
cw["pair_id"] = cw.apply(lambda r: stable_hash(r["onet_soc"] + "|" + r["esco_uri"]), axis=1)
cw_out = cw[["pair_id", "onet_soc", "esco_uri", "match_type"]]
write_parquet(cw_out, "crosswalk")


# ============================================================
# 5. occupation_wask (CORE) — pivot IM/LV into columns
# ============================================================
print("\n[5/8] occupation_wask")
WASK_FILES = [
    ("Work Activities.txt", "W"),
    ("Abilities.txt", "A"),
    ("Skills.txt", "S"),
    ("Knowledge.txt", "K"),
]
wask_parts = []
for fname, dim in WASK_FILES:
    df = pd.read_csv(ONET / fname, sep="\t", dtype=str)
    df.columns = [c.strip() for c in df.columns]
    df = df[["O*NET-SOC Code", "Element ID", "Element Name", "Scale ID",
             "Data Value", "N", "Standard Error", "Recommend Suppress",
             "Not Relevant", "Domain Source"]].copy()
    df.columns = ["onet_soc", "element_id", "element_label", "scale_id",
                  "data_value", "n", "standard_error", "recommend_suppress",
                  "not_relevant", "domain_source"]
    df["dimension"] = dim
    df["data_value"] = pd.to_numeric(df["data_value"], errors="coerce")
    wask_parts.append(df)
wask_long = pd.concat(wask_parts, ignore_index=True)
print(f"    raw long rows (IM+LV separate): {len(wask_long):,}")

# Pivot IM and LV into columns (use minimal key; flags merged back from LV rows)
pivot_key = ["onet_soc", "dimension", "element_id", "element_label"]
wask_pivot = (
    wask_long
    .pivot_table(index=pivot_key, columns="scale_id", values="data_value", aggfunc="first")
    .reset_index()
)
wask_pivot.columns.name = None
wask_pivot = wask_pivot.rename(columns={"IM": "importance_im", "LV": "level_lv"})
# Merge metadata back from LV rows (which carry Not Relevant + flags)
meta = wask_long[wask_long["scale_id"] == "LV"][
    pivot_key + ["recommend_suppress", "not_relevant", "domain_source"]
].drop_duplicates(subset=pivot_key)
wask_pivot = wask_pivot.merge(meta, on=pivot_key, how="left")
# Derive element category from element_id prefix (using Content Model Reference)
cmr = pd.read_csv(ONET / "Content Model Reference.txt", sep="\t", dtype=str)
cmr.columns = [c.strip() for c in cmr.columns]
# Build lookup: level-3 prefix (e.g. "4.A.1" → "Information Input")
cmr_lookup = dict(zip(cmr["Element ID"], cmr["Element Name"]))

def get_parent_category(elem_id):
    """Get level-3 parent (e.g. 4.A.1.a.1 → 4.A.1 label)."""
    parts = elem_id.split(".")
    if len(parts) >= 3:
        parent = ".".join(parts[:3])
        return cmr_lookup.get(parent, "")
    return ""

wask_pivot["parent_category"] = wask_pivot["element_id"].apply(get_parent_category)
# Convert flag columns to bool
wask_pivot["recommend_suppress"] = wask_pivot["recommend_suppress"].fillna("N").map({"Y": True, "N": False}).fillna(False)
wask_pivot["not_relevant"] = wask_pivot["not_relevant"].fillna("N").map({"Y": True, "N": False}).fillna(False)
# Reorder
wask_out = wask_pivot[[
    "onet_soc", "dimension", "element_id", "element_label", "parent_category",
    "importance_im", "level_lv",
    "recommend_suppress", "not_relevant", "domain_source"
]]
write_parquet(wask_out, "occupation_wask")


# ============================================================
# 6. occupation_esco_skills (CORE)
# ============================================================
print("\n[6/8] occupation_esco_skills")
osr = pd.read_csv(ESCO / "occupationSkillRelations_en.csv", dtype=str).fillna("")
# Skills metadata for richer labels
skills_meta = pd.read_csv(ESCO / "skills_en.csv", dtype=str).fillna("")
skills_meta = skills_meta[skills_meta["conceptType"].isin(["KnowledgeSkillCompetence", "Skill"])].copy()
skills_meta["alt_labels_skill"] = skills_meta["altLabels"].apply(split_alt)
skills_meta_slim = skills_meta[["conceptUri", "preferredLabel", "alt_labels_skill",
                                 "skillType", "reuseLevel", "description"]].copy()
skills_meta_slim.columns = ["skill_uri", "skill_label_preferred", "skill_alt_labels",
                            "skill_type_canonical", "skill_reuse_level", "skill_description"]

esco_skills = osr.merge(skills_meta_slim, left_on="skillUri", right_on="skill_uri", how="left")
esco_skills_out = esco_skills[[
    "occupationUri", "skill_uri", "skill_label_preferred", "skill_alt_labels",
    "skillType", "relationType", "skill_reuse_level"
]].rename(columns={
    "occupationUri": "esco_uri",
    "skillType": "skill_type",
    "relationType": "relation_type",
})
write_parquet(esco_skills_out, "occupation_esco_skills")


# ============================================================
# 7. esco_skill_hierarchy (4-level skill tree)
# ============================================================
print("\n[7/8] esco_skill_hierarchy")
sh = pd.read_csv(ESCO / "skillsHierarchy_en.csv", dtype=str).fillna("")
sh_out = sh.rename(columns={
    "Level 0 URI": "level_0_uri", "Level 0 preferred term": "level_0_label", "Level 0 code": "level_0_code",
    "Level 1 URI": "level_1_uri", "Level 1 preferred term": "level_1_label", "Level 1 code": "level_1_code",
    "Level 2 URI": "level_2_uri", "Level 2 preferred term": "level_2_label", "Level 2 code": "level_2_code",
    "Level 3 URI": "level_3_uri", "Level 3 preferred term": "level_3_label", "Level 3 code": "level_3_code",
    "Description": "description",
})
sh_out = sh_out[[
    "level_0_uri", "level_0_label", "level_0_code",
    "level_1_uri", "level_1_label", "level_1_code",
    "level_2_uri", "level_2_label", "level_2_code",
    "level_3_uri", "level_3_label", "level_3_code",
    "description"
]]
write_parquet(sh_out, "esco_skill_hierarchy")


# ============================================================
# 8. occupation_tasks
# ============================================================
print("\n[8/8] occupation_tasks")
tasks = pd.read_csv(ONET / "Task Statements.txt", sep="\t", dtype=str).fillna("")
tasks.columns = [c.strip() for c in tasks.columns]
tasks_out = tasks[["O*NET-SOC Code", "Task ID", "Task", "Task Type", "Incumbents Responding"]].copy()
tasks_out.columns = ["onet_soc", "task_id", "task_statement", "task_type", "incumbents_responding"]
write_parquet(tasks_out, "occupation_tasks")

print("\n✓ Pass 1 (star schema) complete\n")
