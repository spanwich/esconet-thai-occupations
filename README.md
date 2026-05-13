# Occupation & Skill Datasets — ESCONET + Thai Classifications

Queryable Parquet datasets for occupation/skill analytics. **Part 1 (ESCONET)** is a normalized + denormalized join of O\*NET-SOC and ESCO with the official crosswalk. **Part 2 (Thai)** is a set of Thai-language occupation/industry classifications extracted from authoritative PDF sources.

All data ships as Parquet (Snappy-compressed). Load directly with DuckDB, pandas, polars, or pyarrow — no build step required.

## Layout

```
ESCONET/   9 Parquet tables + 2 build scripts + detailed README   (~18 MB)
THAI/      3 Parquet tables (TSCO, TSIC, ISCO-08 Thai) + 3 READMEs (~2.3 MB)
```

---

## Part 1 — ESCONET v0.1 (O\*NET × ESCO)

**Sources:** O\*NET-SOC v30.2 (US Dept. of Labor), ESCO v1.2.1 English (European Commission), ESCO–O\*NET crosswalk v1 (Sep 2022).

| File | Purpose | Rows |
|---|---|---|
| `ESCONET/occupations_onet.parquet` | O\*NET occupation dimension | 1,016 |
| `ESCONET/occupations_esco.parquet` | ESCO occupation dimension (NACE, ISCO, alt labels) | 3,043 |
| `ESCONET/isco_groups.parquet` | ISCO 4-level hierarchy | 619 |
| `ESCONET/crosswalk.parquet` | SOC ↔ ESCO bridge with match type | 4,253 |
| `ESCONET/occupation_wask.parquet` | O\*NET WASK — 161-dim long format (IM + LV) | 143,934 |
| `ESCONET/occupation_esco_skills.parquet` | ESCO skill relations (essential/optional) | 126,281 |
| `ESCONET/esco_skill_hierarchy.parquet` | ESCO skill tree (4 levels) | 640 |
| `ESCONET/occupation_tasks.parquet` | O\*NET task statements | 18,796 |
| `ESCONET/esconet_flat.parquet` | Denormalized union view (O\*NET + ESCO) | 836,571 |

Highlights:
- `esconet_flat.parquet` — bi-directional `pair_id × element` view for one-shot queries across both sources.
- `occupation_wask.parquet` — O\*NET's 161 Work-Activities/Abilities/Skills/Knowledge elements in long format with importance (1–5) and level (0–7).
- Reproducible: `python3 build_esconet.py && python3 build_flat.py` inside `ESCONET/`.

Full schema, query patterns, and known limitations: → [`ESCONET/ESCONET_README.md`](ESCONET/ESCONET_README.md)

---

## Part 2 — Thai Classifications

| Dataset | File | Records | Source |
|---|---|---|---|
| **TSCO 2544** (occupations) | `THAI/tsco.parquet` | 2,254 | Dept. of Employment PDF (594 pp.) |
| **TSIC Pass 3** (industries) | `THAI/tsic_pass3.parquet` | 1,892 | LLM-validated industrial classification |
| **ISCO-08 Thai** (occupations) | `THAI/isco08.parquet` | 619 | NSO Thai translation of ISCO-08 |

- **TSCO** — Thai Standard Classification of Occupations 2544 (2001). Based on ISCO-88 with Thailand-specific extensions; 5 hierarchy levels from Major down to Occupation. See [`THAI/TSCO_README.md`](THAI/TSCO_README.md).
- **TSIC** — Thai Standard Industrial Classification. Multi-pass cleanup: DBD overlay + rule-based + LLM (Claude Opus 4.7) review on 324 corrupted records; **81.9% trustworthy** after Pass 3 (up from 19.6% in Pass 1). See [`THAI/TSIC_README.md`](THAI/TSIC_README.md).
- **ISCO-08 Thai** — National Statistical Office's Thai translation of ISCO-08; 4-level hierarchy, 100% structural match against the ISCO-08 reference, 19 Adobe PUA codepoints decoded. See [`THAI/ISCO08-th_README.md`](THAI/ISCO08-th_README.md).

All three share a common schema (`source`, `code`, `level`, `name_th`, `name_en`, `description`, `parent_code`, `page`) for easy unioning.

---

## Quickstart (DuckDB)

```python
import duckdb
con = duckdb.connect()

# ESCONET
for tbl in ["occupations_onet", "occupations_esco", "isco_groups", "crosswalk",
            "occupation_wask", "occupation_esco_skills", "esco_skill_hierarchy",
            "occupation_tasks", "esconet_flat"]:
    con.execute(f"CREATE VIEW {tbl} AS SELECT * FROM read_parquet('ESCONET/{tbl}.parquet')")

# Thai
con.execute("CREATE VIEW tsco       AS SELECT * FROM read_parquet('THAI/tsco.parquet')")
con.execute("CREATE VIEW tsic_pass3 AS SELECT * FROM read_parquet('THAI/tsic_pass3.parquet')")
con.execute("CREATE VIEW isco08_th  AS SELECT * FROM read_parquet('THAI/isco08.parquet')")
```

### Example: top skills for a SOC occupation

```sql
SELECT dimension, element_label, importance_im, level_lv
FROM occupation_wask
WHERE onet_soc = '15-1252.00'
  AND importance_im >= 3.0
  AND NOT recommend_suppress AND NOT not_relevant
ORDER BY importance_im DESC, level_lv DESC;
```

### Example: bridge a Thai occupation to ESCO/O\*NET via ISCO

```sql
-- TSCO occupation → 4-digit Unit → ISCO-08 → ESCO occupations
SELECT t.code AS tsco_code, t.name_th, e.label_preferred AS esco_label
FROM tsco t
JOIN occupations_esco e ON e.isco_code = SUBSTR(t.code, 1, 4)
WHERE t.code LIKE '2511%';
```

---

## Build / Reproduction

- **ESCONET** — fully deterministic from public sources. Scripts: `ESCONET/build_esconet.py` (star schema), `ESCONET/build_flat.py` (denormalized view).
- **Thai datasets** — PDF extraction artifacts. Source PDFs and extractor scripts (`extract_tsco_v2.py`, `extract_tsic_v3.py` + Pass 2/3, `extract_isco08_v3.py`) are not bundled here; full methodology and quirks are documented in each Thai README.

## Versions

- Dataset: ESCONET v0.1 / Thai Pass 3
- Built: 2026-05-13
- Tooling: Python 3.12, pandas 3.0.2, pyarrow 24.0.0, duckdb 1.5.2
- Compression: Snappy

## License / Attribution

- **O\*NET-SOC** — US Department of Labor, Employment and Training Administration. Public domain (with attribution).
- **ESCO** — European Commission, CC-BY 4.0.
- **ESCO–O\*NET crosswalk** — ESCO Secretariat + US DoL (Sep 2022 release).
- **TSCO 2544** — กรมการจัดหางาน, กระทรวงแรงงาน (Thai Dept. of Employment).
- **TSIC** — Thai industrial classification (DBD overlay + LLM-validated corrections).
- **ISCO-08 Thai** — สำนักงานสถิติแห่งชาติ (Thai National Statistical Office).

This compilation packages derived data from the above public sources for research use. No license file is currently attached to the compilation itself — treat as "all rights reserved" pending a formal license decision.
