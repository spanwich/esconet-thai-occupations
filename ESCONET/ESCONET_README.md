# ESCONET v0.1 — Occupation × Skill Correlation Dataset

**Built:** 2026-05-13 for CHANCEDEE V3 (CD3-3 Algorithm Sketch data foundation)

**Sources:**
- O*NET-SOC text database v30.2 (US Dept. of Labor)
- ESCO classification v1.2.1, English (European Commission)
- ESCO–O*NET crosswalk v1 (Sep 2022, ESCO Secretariat + US DoL)

**Purpose:** Shared queryable database for occupation ↔ skill correlation work. Designed for other Claude Code sessions to load via DuckDB and join Thai-language corpus matches against ESCO/O*NET skill labels.

---

## Files

| File | Purpose | Rows |
|---|---|---|
| `occupations_onet.parquet` | O*NET occupation dimension | 1,016 |
| `occupations_esco.parquet` | ESCO occupation dimension (NACE, ISCO, alt labels) | 3,043 |
| `isco_groups.parquet` | ISCO 4-level hierarchy (1-digit major → 4-digit unit) | 619 |
| `crosswalk.parquet` | SOC ↔ ESCO bridge with match type | 4,253 |
| `occupation_wask.parquet` | **O*NET WASK** — 161-dim long format, IM + LV per element | 143,934 |
| `occupation_esco_skills.parquet` | **ESCO skill relations** — essential/optional per occupation | 126,281 |
| `esco_skill_hierarchy.parquet` | ESCO skill tree (4 levels deep) | 640 |
| `occupation_tasks.parquet` | O*NET task statements (core/supplemental) | 18,796 |
| `esconet_flat.parquet` | **Denormalized convenience view** — both sources unioned | 836,571 |

Total compressed Parquet: ~18 MB

---

## Schema details

### Star schema (Pass 1)

#### `occupations_onet`
- `onet_soc` (PK) — e.g. `15-1252.00`
- `onet_title`, `onet_description`
- `soc_major_group` (first 2 digits), `soc_major_group_label`

#### `occupations_esco`
- `esco_uri` (PK)
- `label_preferred`, `alt_labels` (array), `esco_description`
- `isco_code` (4-digit), `nace_codes` (array — industry classification, 100% coverage)
- `status`, `modified_date`

#### `isco_groups`
- `isco_uri`, `isco_code` (1–4 digits), `isco_label`, `isco_description`
- `isco_level` (1 = major, 2 = sub-major, 3 = minor, 4 = unit)
- `isco_major_code`, `isco_submajor_code`, `isco_minor_code` — for hierarchy joins

#### `crosswalk`
- `pair_id` (stable hash of `onet_soc | esco_uri` — use as join key for fan-out work)
- `onet_soc`, `esco_uri`
- `match_type` ∈ {`exactMatch`, `closeMatch`, `broadMatch`, `narrowMatch`, `exactISCO`}
  - **Note:** 43 rows have `match_type = exactISCO` and point to ISCO group URIs (not specific ESCO occupation) → these will not join to `occupations_esco` (46 orphans total)
  - Distribution: broadMatch 2,053 | closeMatch 1,432 | exactMatch 498 | narrowMatch 227 | exactISCO 43
  - Ford flagged: token-matching false positives at confidence 0.8+; treat broadMatch with caution

#### `occupation_wask`
Long format. One row per `(onet_soc, dimension, element_id)`.
- `onet_soc`, `dimension` ∈ {`W`, `A`, `S`, `K`} (= Work Activities / Abilities / Skills / Knowledge)
- `element_id` (O*NET hierarchical ID, e.g. `4.A.1.a.1`), `element_label`
- `parent_category` (3rd-level Content Model label)
- `importance_im` (1–5, mean across surveyed workers), `level_lv` (0–7, complexity required)
- `recommend_suppress` (bool — low N or unreliable), `not_relevant` (bool — element doesn't apply)
- `domain_source` (Analyst | Incumbent)

**Element counts: W=41 + A=52 + S=35 + K=33 = 161 dimensions** (matches CD3-3 algo sketch)

#### `occupation_esco_skills`
Long format. One row per `(esco_uri, skill_uri)`.
- `esco_uri`, `skill_uri`, `skill_label_preferred`, `skill_alt_labels` (array)
- `skill_type` ∈ {`knowledge`, `skill/competence`}
- `relation_type` ∈ {`essential`, `optional`}
- `skill_reuse_level` — ESCO reuse categorization

#### `esco_skill_hierarchy`
Lookup table for ESCO 4-level skill tree.
- Columns: `level_0_uri/label/code` through `level_3_uri/label/code`, `description`
- Join on any level URI to walk up/down the tree

#### `occupation_tasks`
- `onet_soc`, `task_id`, `task_statement`, `task_type` ∈ {`Core`, `Supplemental`}

---

### Denormalized flat (Pass 2)

#### `esconet_flat`
**One row per `(pair_id, source, dimension, element_id)`** — crosswalk fan-out × element.

| Column | Notes |
|---|---|
| `pair_id` | Stable hash; same as crosswalk |
| `onet_soc`, `esco_uri` | Pair identity |
| `match_type` | From crosswalk |
| `onet_title`, `esco_label` | Human-readable |
| `isco_code`, `isco_label`, `isco_major_code`, `isco_submajor_code` | Job-family filter |
| `soc_major_group`, `soc_major_group_label` | US BLS occupation grouping |
| `nace_codes` | Array of NACE 2.1 industry codes (ESCO side, 100% coverage) |
| `source` | `onet` (WASK row) or `esco` (skill relation row) |
| `dimension` | `W` / `A` / `S` / `K` (O*NET) or `ESCO_S` / `ESCO_K` (ESCO) |
| `element_id`, `element_label`, `parent_category` | Element identity |
| `importance_im`, `level_lv` | Populated for O*NET rows; NULL for ESCO rows |
| `relation_type`, `skill_type` | Populated for ESCO rows; NULL for O*NET rows |
| `recommend_suppress`, `not_relevant` | O*NET quality flags |

**Row count by source × dimension:**

| source | dimension | rows | distinct pairs | distinct elements |
|---|---|---|---|---|
| onet | A | 208,156 | 3,997 | 52 |
| onet | K | 132,099 | 3,997 | 33 |
| onet | S | 140,105 | 3,997 | 35 |
| onet | W | 164,123 | 3,997 | 41 |
| esco | ESCO_K | 54,060 | 4,106 | 3,070 |
| esco | ESCO_S | 138,028 | 4,207 | 9,896 |

---

## Query patterns

### Load all tables in DuckDB

```python
import duckdb
con = duckdb.connect()
for tbl in ["occupations_onet", "occupations_esco", "isco_groups", "crosswalk",
            "occupation_wask", "occupation_esco_skills", "esco_skill_hierarchy",
            "occupation_tasks", "esconet_flat"]:
    con.execute(f"CREATE VIEW {tbl} AS SELECT * FROM read_parquet('{tbl}.parquet')")
```

### Q1. งานนี้ใช้ skill อะไรบ้าง (occupation → skills)

```sql
-- Top WASK elements for Software Developers
SELECT dimension, element_label, importance_im, level_lv
FROM occupation_wask
WHERE onet_soc = '15-1252.00'
  AND importance_im >= 3.0
  AND NOT recommend_suppress AND NOT not_relevant
ORDER BY importance_im DESC, level_lv DESC;
```

### Q2. มี skill นี้ทำงานไหนดี (skill → occupations)

```sql
-- Occupations needing "Programming" skill ranked by importance
SELECT o.onet_title, w.importance_im, w.level_lv
FROM occupation_wask w
JOIN occupations_onet o USING (onet_soc)
WHERE w.element_label = 'Programming' AND w.dimension = 'S'
  AND NOT w.recommend_suppress
ORDER BY w.importance_im DESC;
```

### Q3. ใช้ flat table — query bi-directional พร้อม ESCO labels

```sql
-- "Programming" via flat table with ESCO equivalents
SELECT DISTINCT onet_title, esco_label, importance_im, match_type
FROM esconet_flat
WHERE element_label = 'Programming' AND dimension = 'S'
  AND match_type IN ('exactMatch', 'closeMatch')  -- precision filter
ORDER BY importance_im DESC;
```

### Q4. Filter ตาม ISCO major group (job family)

```sql
SELECT DISTINCT onet_title, esco_label
FROM esconet_flat
WHERE isco_major_code = '2'  -- ISCO major group 2 = Professionals
  AND dimension = 'S' AND importance_im >= 4.0
LIMIT 50;
```

### Q5. Filter ตาม NACE industry (array contains)

```sql
SELECT DISTINCT onet_title, esco_label, nace_codes
FROM esconet_flat
WHERE list_contains(nace_codes, '6201')  -- NACE 6201 = Computer programming activities
LIMIT 20;
```

### Q6. Match Thai corpus → ESCONET (downstream pattern)

Other Claude Code sessions will likely do:

```sql
-- After Thai text is matched to English skill labels via embeddings
WITH thai_matches AS (
    SELECT 'การเขียนโปรแกรม' AS thai_term, 'Programming' AS matched_english, 0.92 AS confidence
    UNION ALL SELECT 'การวิเคราะห์ระบบ', 'Systems Analysis', 0.88
)
SELECT t.thai_term, f.onet_title, f.esco_label, f.importance_im
FROM thai_matches t
JOIN esconet_flat f ON f.element_label = t.matched_english
WHERE f.dimension = 'S' AND f.match_type IN ('exactMatch', 'closeMatch')
ORDER BY t.confidence DESC, f.importance_im DESC;
```

---

## Known limitations / caveats

1. **Crosswalk fan-out inflates WASK redundantly.** When SOC 15-1252.00 matches 5 ESCO occupations, its 161 WASK rows are duplicated 5x in `esconet_flat`. Use `occupation_wask` directly when you don't need the ESCO side. Use `pair_id` to dedupe.

2. **Match type quality is uneven.** `broadMatch` (48% of crosswalk) and `narrowMatch` are known to have false positives at 0.8+ confidence (token-matching artifacts). Restrict to `exactMatch` + `closeMatch` (45%) for high-confidence work.

3. **46 crosswalk rows orphan against `occupations_esco`** — these point to ISCO group URIs (not specific ESCO occupations). They'll still join to `isco_groups` if needed.

4. **ESCO has no Work Activities or Abilities** — only `S` (skill/competence) and `K` (knowledge). The `W` and `A` dimensions exist only on O*NET side.

5. **NACE labels not included** — only NACE codes (URIs parsed to numeric codes). To get NACE labels, fetch from https://ec.europa.eu/eurostat NACE 2.1 reference. (Future enhancement.)

6. **No Thai labels.** All labels are English. Thai mapping is downstream work.

7. **Recommend Suppress / Not Relevant flags carried but not filtered.** Downstream decides whether to drop them.

8. **No element-element relationships across sources.** O*NET WASK and ESCO skills are not bridged at element level (only at occupation level via crosswalk). Bridging requires embedding similarity work (downstream).

---

## Version & build info

- **Dataset version:** ESCONET v0.1
- **Build date:** 2026-05-13
- **O*NET source:** db_30_2 text release
- **ESCO source:** v1.2.1 EN classification CSV bundle
- **Crosswalk source:** ESCO-O*NET v1 (Sep 2022)
- **Built with:** Python 3.12, pandas 3.0.2, pyarrow 24.0.0, duckdb 1.5.2
- **Compression:** Snappy

## Reproduction

Build scripts (`build_esconet.py`, `build_flat.py`) included alongside Parquet files. Run in order:
```
python3 build_esconet.py   # Pass 1: star schema
python3 build_flat.py      # Pass 2: denormalized flat
```
