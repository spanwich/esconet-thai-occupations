# TSIC ⇄ ESCONET — Industry-to-Occupation Crosswalk

A data-foundation crosswalk that connects a **Thai industry** (TSIC) to the **occupations
employed in it** (ESCONET / O\*NET-SOC), with an empirical employment weight on each link.

It exists to answer one question the recommendation engine needs and that ESCO's own
`nace_codes` could not: *given an industry, which occupations actually work in it?*
ESCO industry tags are definitional (an occupation's "home" sector) and return empty for
cross-sector cases such as a software developer in banking. This crosswalk instead routes
through the **US BLS National Employment Matrix** — an empirical occupation × industry
employment table — so cross-sector employment is captured.

## The chain

```
TSIC  →  ISIC Rev.4  →  NAICS 2012  →  BLS National Employment Matrix  →  O*NET-SOC (ESCONET)
        (UNSD struct)   (UNSD concord.) (SOC × NAICS employment)         (occupations_onet)
```

Each hop is a published correspondence except the first (TSIC→ISIC), which is derived here,
and the join into the BLS matrix, which is anchored at the **NAICS 3-digit** level (see
*Known limitations*).

## Tables

| File | Rows | Grain |
|---|---|---|
| `xwalk_tsic_isic4.parquet` | 2,906 | one row per (TSIC code, ISIC Rev.4 code) pair |
| `xwalk_isic4_naics.parquet` | 1,663 | one row per (ISIC Rev.4, NAICS 2012) pair |
| `bls_nem.parquet` | 113,473 | BLS NEM matrix cell (SOC × NEM-industry) |
| `tsic_occupation_flat.parquet` | 839,640 | denormalised end-to-end (TSIC → O\*NET-SOC) |

### `xwalk_tsic_isic4.parquet`
TSIC ⇄ ISIC Rev.4, many-to-many and hierarchy-expanded. Columns: `tsic_code`,
`tsic_level` (Section/Division/Group/Class/Activity), `tsic_name_th`, `tsic_name_en`,
`isic4_code`, `isic4_name_en`, `match_type`.

`match_type` values: `exact` (4-digit TSIC Class = ISIC Class), `rollup_activity`
(5-digit TSIC Activity rolled up to its 4-digit Class), `group_expand` / `division_expand`
/ `section_expand` (a 3/2/1-level TSIC code expanded to all of its 4-digit ISIC
descendants), `group_fallback` (Thailand-specific 4-digit code with no ISIC Class match,
resolved to the 4-digit children of its 3-digit group), `unmatched`.

1,861 of 1,892 TSIC codes receive at least one ISIC mapping.

### `xwalk_isic4_naics.parquet`
The UNSD ISIC Rev.4 → NAICS 2012 (US) concordance, filtered to numeric NAICS codes.
Columns: `isic4`, `naics2012` (6-digit), `naics3` (3-digit prefix), `detail`.

### `bls_nem.parquet`
The BLS National Employment Matrix 2024–34, "Matrix" sheet, lightly renamed. Columns:
`occ_type`, `ind_type` (`Line item` vs `Summary`), `soc_code`, `soc_title`,
`nem_industry_code`, `nem_industry_title`, `naics3` (3-digit prefix derived from the NEM
industry code; `NULL` for the `TE####` total codes), `emp_2024`, `pct_of_industry`,
`pct_of_occupation`, `emp_2034`. Employment is in thousands.

### `tsic_occupation_flat.parquet`
The end-to-end convenience table — the one most consumers will use. Built by joining
`xwalk_tsic_isic4 → xwalk_isic4_naics → bls_nem` at the NAICS 3-digit level, then attaching
ESCONET's O\*NET-SOC occupations. Columns: `tsic_code`, `tsic_level`, `tsic_name_th`,
`tsic_name_en`, `naics3`, `soc_code`, `soc_title`, `onet_soc_code`, `onet_soc_title`,
`emp_2024_k`. 1,780 TSIC codes resolve to 953 distinct O\*NET-SOC occupations.

## How to use it

To get the occupations for an industry, filter `tsic_occupation_flat` by `tsic_code` and
sort by `emp_2024_k` descending. A code at any hierarchy level works: an `Activity`-level
code resolves to the occupations of its single ISIC class, while a `Division`-level code
resolves to the union over all of its classes.

Example — TSIC `64191` (การธนาคาร / commercial banking):

```sql
SELECT soc_title, onet_soc_code, emp_2024_k
FROM tsic_occupation_flat
WHERE tsic_code = '64191' AND onet_soc_code IS NOT NULL
ORDER BY emp_2024_k DESC;
```

returns Tellers, Securities & financial services sales agents, Loan officers, Customer
service representatives … and **Software developers (`15-1252.00`)** further down the list
— the cross-sector case ESCO's `nace_codes` missed.

## Known limitations

**NAICS version gap.** UNSD only publishes ISIC Rev.4 ↔ NAICS **2012**, but the BLS NEM
uses NAICS **2022**. The join into the matrix is therefore anchored at the **3-digit NAICS**
level, where the two vintages are essentially stable. Anything finer is not reliable across
the gap. The Information sector (NAICS 51x) was restructured in the 2022 revision and is the
known weak spot; treat 51x results as approximate.

**Employment weight is a structural proxy, not Thai labour data.** `emp_2024_k` comes from
the US BLS matrix. It indicates *which occupations are structurally employed in an industry
and roughly how concentrated they are* — it is **not** a count of Thai workers. Use it for
ranking and filtering, not for Thai market sizing.

**31 unmatched TSIC codes.** Genuinely Thailand-specific codes with no ISIC parent, e.g.
`0730` การทำเหมืองสินแร่โลหะมีค่า, `4940` การขนส่งทางระบบท่อลำเลียง, `8560`
การศึกษาระดับก่อนประถมศึกษา. They appear in `xwalk_tsic_isic4` with `match_type='unmatched'`
and do not reach occupations.

**Hierarchy expansion is a union, not a weighting.** A Division/Group/Section TSIC code
returns every occupation found in any descendant class, deduplicated. It is broad but
correct; it does not down-weight by sub-industry size.

**Inherited TSIC Pass-3 quality.** ~15% of TSIC Pass-3 rows carry `name_quality='no_name'`
upstream. Codes are unaffected; only some Thai/English labels are missing.

## Reproduction

`build_crosswalk.py` rebuilds all four tables from source. Required inputs: `tsic_pass3.parquet`
and `occupations_onet.parquet` from the ESCONET repo, `ISIC_Rev_4_english_structure.csv` and
`matrix.xlsx` (BLS NEM 2024–34) as uploads, and `raw/isic4_naics2012.csv` (the UNSD
ISIC4→NAICS2012 US concordance, fetched from
`unstats.un.org/unsd/classifications/Econ/tables/ISIC/ISIC4_NAICS2012US/`). Edit the path
constants at the top of the script to match your layout. Dependencies: `pandas`, `duckdb`,
`pyarrow`, `openpyxl`.

## Sources

- **TSIC** — Thai Standard Industrial Classification, curated from National Statistical
  Office publications (TSIC Pass-3).
- **ISIC Rev.4** structure and **ISIC Rev.4 → NAICS 2012 (US)** concordance — UN Statistics
  Division.
- **National Employment Matrix 2024–34** — US Bureau of Labor Statistics.
- **O\*NET-SOC occupations** — ESCONET dataset (O\*NET-SOC v30.2).
