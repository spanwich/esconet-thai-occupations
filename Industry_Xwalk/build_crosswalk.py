#!/usr/bin/env python3
"""
TSIC <-> ESCONET occupation crosswalk builder
CHANCEDEE V3 / CD3-3 data foundation

Chain:  TSIC -> ISIC Rev.4 -> NAICS 2012 -> BLS National Employment Matrix -> O*NET-SOC (ESCONET)

Inputs (expected paths):
  THAI/tsic_pass3.parquet                 - TSIC Pass-3 (curated from NSO PDFs)
  ISIC_Rev_4_english_structure.csv        - UNSD ISIC Rev.4 hierarchy
  raw/isic4_naics2012.csv                 - UNSD ISIC Rev.4 <-> NAICS 2012 US concordance
  matrix.xlsx (sheet "Matrix")            - BLS National Employment Matrix 2024-34
  ESCONET/occupations_onet.parquet        - ESCONET O*NET-SOC occupations

Outputs (parquet, written to ./):
  xwalk_tsic_isic4.parquet      - TSIC <-> ISIC Rev.4   (many-to-many, hierarchy-expanded)
  xwalk_isic4_naics.parquet     - ISIC Rev.4 <-> NAICS 2012
  bls_nem.parquet               - BLS NEM matrix (SOC x NEM-industry employment)
  tsic_occupation_flat.parquet  - denormalised end-to-end TSIC -> O*NET-SOC, joined at NAICS 3-digit
"""
import pandas as pd
import duckdb

# ---- paths (edit to match your layout) ----
THAI = "../esconet/THAI"
ESC  = "../esconet/ESCONET"
UP   = "/mnt/user-data/uploads"
RAW  = "../raw"
OUT  = "."

# ---------- LOAD ----------
tsic = pd.read_parquet(f"{THAI}/tsic_pass3.parquet")
tsic['code'] = tsic['code'].astype(str).str.strip()

isic4 = pd.read_csv(f"{UP}/ISIC_Rev_4_english_structure.csv", dtype=str)
isic4.columns = ['code', 'name_en']
isic4['code'] = isic4['code'].str.strip()

i2n = pd.read_csv(f"{RAW}/isic4_naics2012.csv", dtype=str)
i2n.columns = ['isic4', 'isic4_part', 'naics2012', 'naics_part', 'detail']

nem  = pd.read_excel(f"{UP}/matrix.xlsx", sheet_name="Matrix")
onet = pd.read_parquet(f"{ESC}/occupations_onet.parquet")

# ---------- ISIC Rev.4 helpers ----------
# section map: structure file is ordered (letter, then its 2/3/4-digit codes)
section_of, cur = {}, None
for _, r in isic4.iterrows():
    c = r['code']
    if len(c) == 1 and c.isalpha():
        cur = c
    elif cur:
        section_of[c] = cur
isic4_4d   = sorted([c for c in isic4['code'] if len(c) == 4 and c.isdigit()])
isic4_name = dict(zip(isic4['code'], isic4['name_en']))

# ---------- 1. xwalk_tsic_isic4 (many-to-many, hierarchy-expanded) ----------
def expand(code):
    """Map a TSIC code to a list of (isic4_code, match_type) pairs."""
    L = len(code)
    if L == 5:                                   # Activity -> roll up to Class
        cls = code[:4]
        if cls in isic4_name:
            return [(cls, 'rollup_activity')]
        kids = [c for c in isic4_4d if c.startswith(code[:3])]
        return [(k, 'group_fallback') for k in kids]
    if L == 4:                                   # Class
        if code in isic4_name:
            return [(code, 'exact')]
        kids = [c for c in isic4_4d if c.startswith(code[:3])]   # Thailand-specific
        return [(k, 'group_fallback') for k in kids]
    if L == 3:                                   # Group -> all 4-digit descendants
        return [(c, 'group_expand') for c in isic4_4d if c.startswith(code)]
    if L == 2:                                   # Division -> all 4-digit descendants
        return [(c, 'division_expand') for c in isic4_4d if c.startswith(code)]
    if L == 1 and code.isalpha():                # Section -> all 4-digit in section
        return [(c, 'section_expand') for c in isic4_4d if section_of.get(c) == code]
    return []

rows = []
for _, r in tsic.iterrows():
    pairs = expand(r['code'])
    if not pairs:
        rows.append(dict(tsic_code=r['code'], tsic_level=r['level'], tsic_name_th=r['name_th'],
                         tsic_name_en=r['name_en'], isic4_code=None, isic4_name_en=None,
                         match_type='unmatched'))
    for ic, mt in pairs:
        rows.append(dict(tsic_code=r['code'], tsic_level=r['level'], tsic_name_th=r['name_th'],
                         tsic_name_en=r['name_en'], isic4_code=ic, isic4_name_en=isic4_name.get(ic),
                         match_type=mt))
xw_tsic_isic = pd.DataFrame(rows)
xw_tsic_isic.to_parquet(f"{OUT}/xwalk_tsic_isic4.parquet", index=False)

# ---------- 2. xwalk_isic4_naics ----------
i2n_clean = i2n[i2n['naics2012'].str.match(r'^\d+$', na=False)].copy()
i2n_clean['naics3'] = i2n_clean['naics2012'].str[:3]
i2n_clean = i2n_clean[['isic4', 'naics2012', 'naics3', 'detail']]
i2n_clean.to_parquet(f"{OUT}/xwalk_isic4_naics.parquet", index=False)

# ---------- 3. bls_nem ----------
nem2 = nem.rename(columns={
    'Occupation type': 'occ_type', 'Industry type': 'ind_type',
    'Occupation code': 'soc_code', 'Occupation title': 'soc_title',
    'Industry code': 'nem_industry_code', 'Industry title': 'nem_industry_title',
    '2024 Employment': 'emp_2024', '2024 Percent of Industry': 'pct_of_industry',
    '2024 Percent of Occupation': 'pct_of_occupation', '2034 Employment': 'emp_2034',
}).copy()
nem2['nem_industry_code'] = nem2['nem_industry_code'].astype(str)
nem2['soc_code'] = nem2['soc_code'].astype(str)
# NAICS 3-digit prefix from the NEM industry code (digit-led codes only; TE totals -> None)
nem2['naics3'] = nem2['nem_industry_code'].apply(lambda c: c[:3] if c[:1].isdigit() else None)
nem_keep = nem2[['occ_type', 'ind_type', 'soc_code', 'soc_title', 'nem_industry_code',
                 'nem_industry_title', 'naics3', 'emp_2024', 'pct_of_industry',
                 'pct_of_occupation', 'emp_2034']]
nem_keep.to_parquet(f"{OUT}/bls_nem.parquet", index=False)

# ---------- 4. tsic_occupation_flat (end-to-end, joined at NAICS 3-digit) ----------
con = duckdb.connect()
con.register('xti', xw_tsic_isic)
con.register('xin', i2n_clean)
con.register('nem', nem_keep)
con.register('onet', onet)
flat = con.execute("""
WITH tsic_naics3 AS (
  SELECT DISTINCT xti.tsic_code, xti.tsic_level, xti.tsic_name_th, xti.tsic_name_en, xin.naics3
  FROM xti JOIN xin ON xti.isic4_code = xin.isic4
  WHERE xti.isic4_code IS NOT NULL
),
nem_li AS (
  SELECT soc_code, soc_title, naics3, SUM(emp_2024) AS emp_2024_k
  FROM nem
  WHERE occ_type = 'Line item' AND ind_type = 'Line item' AND naics3 IS NOT NULL
  GROUP BY soc_code, soc_title, naics3
)
SELECT t.tsic_code, t.tsic_level, t.tsic_name_th, t.tsic_name_en, t.naics3,
       n.soc_code, n.soc_title,
       o.onet_soc AS onet_soc_code, o.onet_title AS onet_soc_title,
       n.emp_2024_k
FROM tsic_naics3 t
JOIN nem_li n ON t.naics3 = n.naics3
LEFT JOIN onet o ON SUBSTR(o.onet_soc, 1, 7) = n.soc_code
ORDER BY t.tsic_code, n.emp_2024_k DESC
""").fetchdf()
flat.to_parquet(f"{OUT}/tsic_occupation_flat.parquet", index=False)

# ---------- summary ----------
print("xwalk_tsic_isic4    :", len(xw_tsic_isic), "rows,",
      xw_tsic_isic[xw_tsic_isic.isic4_code.notna()]['tsic_code'].nunique(), "/ 1892 TSIC mapped")
print("xwalk_isic4_naics   :", len(i2n_clean), "rows,", i2n_clean['isic4'].nunique(), "ISIC4 codes")
print("bls_nem             :", len(nem_keep), "rows")
print("tsic_occupation_flat:", len(flat), "rows,",
      flat['tsic_code'].nunique(), "TSIC ->", flat['onet_soc_code'].nunique(), "O*NET-SOC")
