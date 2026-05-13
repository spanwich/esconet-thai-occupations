# ESCONET v0.1 — Instructions for Claude

> **Read this before any work involving occupation × skill data in the CHANCEDEE V3 project.** This is the operating manual for the ESCONET Parquet dataset. The data lives in a GitHub repo, not in Project Knowledge. Follow the bootstrap pattern below — don't reinvent loading code, don't re-derive what's already decided.

---

## What ESCONET is (30 seconds)

A **denormalized Parquet star-schema** bridging **O\*NET-SOC** (US, with quantitative WASK ratings) and **ESCO** (EU, with curated essential/optional skill relations) via the official **ESCO–O\*NET crosswalk**. Built to answer:

1. **"What skills does this occupation need?"** (occupation → skills)
2. **"Which occupations need this skill?"** (skill → occupations)

Built 2026-05-13. Sources: O\*NET text DB v30.2 + ESCO v1.2.1 EN + ESCO–O\*NET crosswalk v1 (Sep 2022). Total ~18 MB compressed, 9 files. Repo also includes a `THAI/` folder with TSCO/TSIC/ISCO-08-th Parquet for Thai-language downstream work.

**Use DuckDB on the Parquet directly.** Do not convert to CSV. Don't load into pandas unless you must — DuckDB handles 836k-row joins in milliseconds.

---

## ★ Bootstrap: clone the repo first (REQUIRED)

The Parquet files are hosted in a public GitHub repo. **In Claude.ai sessions, `git clone` is the only working access method** — `raw.githubusercontent.com` and DuckDB HTTPFS are network-blocked in this environment. So bootstrap like this once per session:

```bash
cd /home/claude
git clone --depth 1 https://github.com/nanseapor/esconet-thai-occupations.git esconet
ls esconet/ESCONET/*.parquet | wc -l   # expect: 9
```

Then in Python, point DuckDB at the cloned files:

```python
import duckdb
from pathlib import Path

ESCONET_DIR = Path("/home/claude/esconet/ESCONET")
con = duckdb.connect()
TABLES = [
    "occupations_onet", "occupations_esco", "isco_groups", "crosswalk",
    "occupation_wask", "occupation_esco_skills", "esco_skill_hierarchy",
    "occupation_tasks", "esconet_flat",
]
for tbl in TABLES:
    p = ESCONET_DIR / f"{tbl}.parquet"
    if not p.exists():
        raise FileNotFoundError(f"Missing {p} — clone the repo first (see Bootstrap section)")
    con.execute(f"CREATE VIEW {tbl} AS SELECT * FROM read_parquet('{p}')")

print("ESCONET loaded:", con.execute("SELECT COUNT(*) FROM esconet_flat").fetchone()[0], "flat rows")
# Expect: 836571
```

**If `git clone` fails** (network restrictions in some environments): tell the user and ask them to either run code execution mode, or upload the Parquet bundle manually to `/mnt/user-data/uploads/`.

**If you're running outside a Python environment**, DuckDB CLI works identically once files are local:
```bash
duckdb -c "SELECT COUNT(*) FROM read_parquet('/home/claude/esconet/ESCONET/esconet_flat.parquet');"
```

---

## File inventory (relative to `ESCONET/` inside the cloned repo)

| File | Rows | Use when... |
|---|---|---|
| `esconet_flat.parquet` | 836,571 | **Default for most queries.** Pre-joined long format with both O\*NET WASK and ESCO skills, fan-out by crosswalk. One row per (occupation pair, dimension, element). |
| `occupation_wask.parquet` | 143,934 | You need O\*NET WASK only, no crosswalk fan-out duplication. |
| `occupation_esco_skills.parquet` | 126,281 | You need ESCO skill relations only, no fan-out. |
| `crosswalk.parquet` | 4,253 | You're evaluating SOC↔ESCO match quality or building your own join. |
| `occupations_onet.parquet` | 1,016 | O\*NET title/description lookup. |
| `occupations_esco.parquet` | 3,043 | ESCO label/NACE/ISCO lookup (incl. `alt_labels` arrays). |
| `isco_groups.parquet` | 619 | ISCO 1-4 digit hierarchy. |
| `esco_skill_hierarchy.parquet` | 640 | ESCO 4-level skill tree. |
| `occupation_tasks.parquet` | 18,796 | O\*NET task statements. |

**If you're not sure which to use, start with `esconet_flat.parquet`.** It has 95% of what most queries need.

The repo also contains `THAI/*.parquet` (TSCO/TSIC/ISCO-08-th) — see `THAI/*_README.md` in the repo when you need Thai classification data.

---

## Task patterns — use these as templates

### Pattern 1: Find skills for an occupation

```sql
-- O*NET-SOC by code (most precise)
SELECT dimension, element_label, parent_category, importance_im, level_lv
FROM occupation_wask
WHERE onet_soc = '15-1252.00'        -- Software Developers
  AND importance_im >= 3.0
  AND NOT recommend_suppress AND NOT not_relevant
ORDER BY importance_im DESC, level_lv DESC;
```

```sql
-- By title fuzzy match (need esconet_flat for ESCO labels)
SELECT DISTINCT dimension, element_label, importance_im, level_lv
FROM esconet_flat
WHERE LOWER(onet_title) LIKE '%software developer%'
  AND source = 'onet' AND importance_im >= 3.0
ORDER BY importance_im DESC LIMIT 30;
```

### Pattern 2: Find occupations for a skill

```sql
-- Exact element name (O*NET vocabulary)
SELECT DISTINCT onet_title, importance_im, level_lv
FROM esconet_flat
WHERE element_label = 'Programming' AND dimension = 'S'
  AND match_type IN ('exactMatch', 'closeMatch')  -- precision filter, see Gotcha #1
ORDER BY importance_im DESC LIMIT 20;
```

```sql
-- ESCO skill (use esco label)
SELECT DISTINCT esco_label, relation_type, skill_type
FROM esconet_flat
WHERE element_label ILIKE '%python%' AND source = 'esco'
LIMIT 20;
```

### Pattern 3: Match an external term (Thai/English/anything) → ESCONET

Canonical pattern for Thai corpus matching downstream:

```sql
-- Step 1: caller provides matched_english labels with confidence (from embedding model, fuzzy match, etc.)
WITH external_matches AS (
    SELECT 'การเขียนโปรแกรม' AS source_term, 'Programming' AS matched_label, 0.92 AS match_confidence
    UNION ALL SELECT 'การวิเคราะห์ระบบ', 'Systems Analysis', 0.88
    UNION ALL SELECT 'การคิดเชิงวิพากษ์', 'Critical Thinking', 0.85
)
-- Step 2: join to ESCONET — filter for high-precision match types
SELECT
    e.source_term, e.match_confidence,
    f.onet_title, f.esco_label,
    f.dimension, f.importance_im, f.match_type
FROM external_matches e
JOIN esconet_flat f
  ON f.element_label = e.matched_label
WHERE f.source = 'onet'
  AND f.dimension IN ('S', 'K')
  AND f.match_type IN ('exactMatch', 'closeMatch')
ORDER BY e.match_confidence DESC, f.importance_im DESC;
```

**For ESCO skills (vocab ~13k labels), use ILIKE or pre-index labels:**

```sql
SELECT skill_uri, skill_label_preferred
FROM occupation_esco_skills
WHERE LOWER(skill_label_preferred) LIKE LOWER('%' || 'project management' || '%')
GROUP BY skill_uri, skill_label_preferred
LIMIT 20;
```

### Pattern 4: Filter by job family (ISCO) or industry (NACE)

```sql
-- ISCO major group (1-digit) → "occupation family"
-- 1=Managers, 2=Professionals, 3=Technicians, 4=Clerical, 5=Service, 6=Skilled agriculture,
-- 7=Craft, 8=Plant/machine operators, 9=Elementary, 0=Armed forces
SELECT DISTINCT esco_label, isco_label
FROM esconet_flat
WHERE isco_major_code = '2'  -- Professionals
  AND dimension = 'S' AND importance_im >= 4.0;
```

```sql
-- NACE industry (multi-value array on each occupation)
-- IMPORTANT: ESCO assigns occupations at multiple NACE levels (1-4 digits).
-- IT/computing occupations are typically assigned at the GROUP level (3-digit):
-- e.g. NACE 621 = Computer programming, consultancy and related activities GROUP
-- NOT 6201 (Computer programming activities CLASS) — that level isn't used here
SELECT DISTINCT esco_label, nace_codes
FROM esconet_flat
WHERE list_contains(nace_codes, '621')
LIMIT 20;
```

To explore which codes exist in the data first:

```sql
WITH unnested AS (SELECT UNNEST(nace_codes) AS code FROM occupations_esco)
SELECT LENGTH(code) AS code_len, COUNT(*) AS n
FROM unnested GROUP BY 1 ORDER BY 1;
-- 1-char (section) ~62, 2-char (division) ~337, 3-char (group) ~1665, 4-char (class) ~2506
```

### Pattern 5: Get skill hierarchy / category

```sql
SELECT s.skill_uri, s.skill_label_preferred,
       h.level_0_label, h.level_1_label, h.level_2_label, h.level_3_label
FROM occupation_esco_skills s
LEFT JOIN esco_skill_hierarchy h
  ON h.level_3_uri = s.skill_uri
WHERE s.skill_uri = 'http://data.europa.eu/esco/skill/...'
LIMIT 1;
```

For O\*NET WASK, `parent_category` is inlined on each row already.

### Pattern 6: Occupation similarity (cosine on WASK vector)

```sql
WITH a AS (
    SELECT element_id, importance_im AS a_im
    FROM occupation_wask
    WHERE onet_soc = '15-1252.00' AND dimension IN ('S', 'K')
      AND NOT recommend_suppress AND NOT not_relevant
), b AS (
    SELECT element_id, importance_im AS b_im
    FROM occupation_wask
    WHERE onet_soc = '15-1212.00' AND dimension IN ('S', 'K')
      AND NOT recommend_suppress AND NOT not_relevant
), joined AS (
    SELECT a.element_id, COALESCE(a.a_im, 0) AS av, COALESCE(b.b_im, 0) AS bv
    FROM a FULL OUTER JOIN b USING (element_id)
)
SELECT
    SUM(av * bv) / (SQRT(SUM(av*av)) * SQRT(SUM(bv*bv))) AS cosine_sim
FROM joined;
```

---

## Schema cheatsheet (memorize this)

### `esconet_flat` — most useful columns

| Column | Type | Notes |
|---|---|---|
| `pair_id` | string | Stable hash; dedupe key for crosswalk fan-out |
| `onet_soc` | string | e.g. `15-1252.00` |
| `esco_uri` | string | Full URI |
| `match_type` | enum | `exactMatch`, `closeMatch`, `broadMatch`, `narrowMatch`, `exactISCO` |
| `onet_title`, `esco_label` | string | Human-readable |
| `isco_code`, `isco_label` | string | 4-digit + label |
| `isco_major_code`, `isco_submajor_code` | string | 1-digit, 2-digit |
| `soc_major_group`, `soc_major_group_label` | string | 2-digit SOC + label |
| `nace_codes` | array\<string\> | NACE 2.1 industry codes |
| **`source`** | enum | `onet` (WASK row) or `esco` (skill relation row) |
| **`dimension`** | enum | `W` `A` `S` `K` (O\*NET) or `ESCO_S` `ESCO_K` (ESCO) |
| `element_id` | string | O\*NET hierarchical ID or ESCO skill URI |
| `element_label` | string | Element/skill name |
| `parent_category` | string | O\*NET 3rd-level category (NULL for ESCO rows) |
| `importance_im` | double 1–5 | NULL on ESCO rows |
| `level_lv` | double 0–7 | NULL on ESCO rows |
| `relation_type` | enum | `essential` or `optional`, NULL on O\*NET rows |
| `skill_type` | enum | `knowledge` or `skill/competence`, NULL on O\*NET rows |
| `recommend_suppress`, `not_relevant` | bool | O\*NET quality flags |

### Dimension reference

- **W** (Work Activities, 41 elements) — what you *do* (e.g. "Getting Information")
- **A** (Abilities, 52 elements) — innate capacities (e.g. "Oral Comprehension")
- **S** (Skills, 35 elements) — developed competencies (e.g. "Critical Thinking")
- **K** (Knowledge, 33 elements) — domain expertise (e.g. "Mathematics")
- **ESCO_S** (~10k skills) — fine-grained ESCO `skill/competence`
- **ESCO_K** (~3k items) — fine-grained ESCO `knowledge`

O\*NET = coarse-grained. ESCO = fine-grained. Use both depending on task granularity.

---

## Gotchas — read all of these

### Gotcha 1: `broadMatch` has known false positives at confidence 0.8+

The crosswalk was built with token-matching and has false positives in `broadMatch` (48% of all crosswalk rows). For high-precision work, **always filter `match_type IN ('exactMatch', 'closeMatch')`** (45% of rows). Use `broadMatch`/`narrowMatch` only when you explicitly need wider recall and can tolerate noise. Document this in any output.

```sql
WHERE match_type IN ('exactMatch', 'closeMatch')
```

### Gotcha 2: Fan-out inflates WASK rows in `esconet_flat`

When one SOC matches 5 ESCO occupations, its 161 WASK elements appear 5× in `esconet_flat`. **If you're doing pure occupation→element analysis (no ESCO context), use `occupation_wask` directly** instead. For correctness with `esconet_flat`, dedupe by `pair_id` or by `(onet_soc, element_id)`.

### Gotcha 3: ESCO has no Work Activities or Abilities

ESCO classification only has `skill/competence` and `knowledge`. The `W` and `A` dimensions only exist on the O\*NET side. Don't search ESCO for "abilities".

### Gotcha 4: 46 crosswalk rows orphan against `occupations_esco`

These 46 rows have `match_type = exactISCO` (or fringe cases) and point to ISCO group URIs, not specific ESCO occupations. Their `esco_label` in `esconet_flat` will be NULL. Either filter them out (`WHERE esco_uri IS NOT NULL AND esco_label IS NOT NULL`) or join to `isco_groups` instead.

### Gotcha 5: O\*NET ratings come in TWO scales — don't conflate

- `importance_im` (1–5): how *important* is this element to the job
- `level_lv` (0–7): what *level* of this element is required

Pick the right one for your question:
- Ranking required skills → `importance_im`
- Skill gap analysis (match candidate level) → `level_lv`
- Research convention → weighted combination, e.g. `(importance_im - 1) / 4 * level_lv / 7`

### Gotcha 6: `recommend_suppress` and `not_relevant` are kept raw

NOT pre-filtered. Add `WHERE NOT recommend_suppress AND NOT not_relevant` for clean analysis.

### Gotcha 7: ESCO `relation_type` is curated, not statistical

- `essential` = ESCO Secretariat declared "you need this skill for this occupation"
- `optional` = commonly co-occurs but not required

This is curated expert judgment, not survey data. **Don't compare ESCO `essential` confidence directly with O\*NET `importance_im`** — different epistemic source.

### Gotcha 8: NACE codes are present, multi-level, and labels are not

`nace_codes` is an array of NACE 2.1 codes (e.g. `['621', '622']` for software developer). **Codes appear at 4 hierarchy levels in this dataset, and ESCO doesn't always assign at the same level across occupation types:**

- 1-char (section): `B`, `R` — used for ~62 occupations
- 2-char (division): `62`, `55` — ~337 occupations
- 3-char (group): `621`, `622` — ~1,665 (most IT/computing here)
- 4-char (class): `0113`, `9699` — ~2,506

When filtering by NACE, **inspect what level the relevant industries use first** (run the UNNEST query in Pattern 4). Filtering by class (4-digit) often returns empty results for IT — use group (3-digit) instead.

Labels are not in the dataset — only codes. For human-readable NACE labels, fetch the NACE 2.1 reference from Eurostat separately. Treat NACE as opaque codes for filtering now.

### Gotcha 9: All English labels — Thai is downstream

ESCONET has zero Thai content by design. The repo's `THAI/` folder has separate Thai classifications (TSCO/TSIC/ISCO-08-th). Match Thai terms to English labels in your pipeline, then join into ESCONET.

### Gotcha 10: Network restrictions in Claude.ai

In Claude.ai code-execution sessions, `raw.githubusercontent.com` and `extensions.duckdb.org` are network-blocked, so DuckDB's `httpfs` extension and direct URL-reads will fail. **Use `git clone` instead** — `github.com` is allowed. Claude Code (CLI) doesn't have this restriction; either pattern works there.

### Gotcha 11: DuckDB function-name differences across versions

DuckDB function naming changed across versions. In v1.5.x (Claude.ai sandbox default) some array functions are not available under the names you might expect:

| Want to use | v1.5.x works | v1.5.x fails |
|---|---|---|
| Array length | `len(arr)` or `array_length(arr)` | `list_length(arr)` ❌ |
| Element check | `list_contains(arr, x)` ✅ | — |
| Unnest | `UNNEST(arr)` ✅ | — |

When in doubt, check with `SELECT * FROM duckdb_functions() WHERE function_name LIKE 'list%'` in the session.

---

## Versioning rules

This is **ESCONET v0.1**. Do not overwrite — version up (v0.2, v0.3, etc.). Source versions are pinned:
- O\*NET text DB v30.2
- ESCO v1.2.1 (en)
- ESCO–O\*NET crosswalk v1 (Sep 2022)

Don't mix versions across sessions silently.

---

## When you need more

- Full schema, build details, reproduction scripts → `ESCONET/ESCONET_README.md` in the repo.
- Thai classification details → `THAI/TSCO_README.md`, `THAI/TSIC_README.md`, `THAI/ISCO08-th_README.md`.
- CHANCEDEE V3 project context, sprint state, decisions log → Confluence MEMORY page (id `20381723`).
- Algorithm Sketch using ESCONET → Confluence page id `20381793`.

---

## Quick sanity check (run after bootstrap)

```python
# Confirm the dataset is what you think it is
con.execute("""
    SELECT 'flat rows' AS m, COUNT(*) AS v FROM esconet_flat
    UNION ALL SELECT 'crosswalk pairs', COUNT(*) FROM crosswalk
    UNION ALL SELECT 'O*NET WASK elements', COUNT(DISTINCT element_id) FROM occupation_wask
    UNION ALL SELECT 'ESCO skills', COUNT(DISTINCT skill_uri) FROM occupation_esco_skills
""").fetchdf()
# Expected: flat=836571, crosswalk=4253, WASK elements=161, ESCO skills=~13475
```

If numbers don't match, you have a wrong version or files are corrupted — stop and re-check.
