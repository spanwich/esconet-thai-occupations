"""Pass 2: build esconet_flat.parquet via DuckDB SQL on Parquet star schema."""
import duckdb
from pathlib import Path

OUT = Path("/home/claude/esconet_build")
con = duckdb.connect(":memory:")

# Register all Pass 1 tables
for name in ["occupations_onet", "occupations_esco", "isco_groups", "crosswalk",
             "occupation_wask", "occupation_esco_skills", "esco_skill_hierarchy",
             "occupation_tasks"]:
    con.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet('{OUT}/{name}.parquet')")

print("Star-schema views registered. Building flat table...")

# Pass 2: fan-out crosswalk × elements
# Two row types unioned: WASK (O*NET side) and ESCO_S/ESCO_K (ESCO side)
flat_sql = """
WITH cw AS (
    SELECT
        c.pair_id, c.onet_soc, c.esco_uri, c.match_type,
        o.onet_title, o.soc_major_group, o.soc_major_group_label,
        e.label_preferred AS esco_label, e.isco_code, e.nace_codes
    FROM crosswalk c
    LEFT JOIN occupations_onet o ON c.onet_soc = o.onet_soc
    LEFT JOIN occupations_esco e ON c.esco_uri = e.esco_uri
),
isco_dim AS (
    SELECT isco_code, isco_label,
           isco_major_code, isco_submajor_code
    FROM isco_groups
    WHERE isco_level = '4'
),
cw_enriched AS (
    SELECT cw.*,
           id.isco_label,
           id.isco_major_code,
           id.isco_submajor_code
    FROM cw LEFT JOIN isco_dim id USING (isco_code)
),
-- WASK rows: O*NET side, replicated per crosswalk pair
wask_rows AS (
    SELECT
        cw.pair_id, cw.onet_soc, cw.esco_uri, cw.match_type,
        cw.onet_title, cw.esco_label,
        cw.isco_code, cw.isco_label, cw.isco_major_code, cw.isco_submajor_code,
        cw.soc_major_group, cw.soc_major_group_label,
        cw.nace_codes,
        'onet' AS source,
        w.dimension,
        w.element_id, w.element_label, w.parent_category,
        w.importance_im, w.level_lv,
        CAST(NULL AS VARCHAR) AS relation_type,
        CAST(NULL AS VARCHAR) AS skill_type,
        w.recommend_suppress, w.not_relevant
    FROM cw_enriched cw
    JOIN occupation_wask w ON cw.onet_soc = w.onet_soc
),
-- ESCO skill rows: ESCO side, replicated per crosswalk pair
esco_rows AS (
    SELECT
        cw.pair_id, cw.onet_soc, cw.esco_uri, cw.match_type,
        cw.onet_title, cw.esco_label,
        cw.isco_code, cw.isco_label, cw.isco_major_code, cw.isco_submajor_code,
        cw.soc_major_group, cw.soc_major_group_label,
        cw.nace_codes,
        'esco' AS source,
        CASE
            WHEN es.skill_type = 'knowledge' THEN 'ESCO_K'
            ELSE 'ESCO_S'
        END AS dimension,
        es.skill_uri AS element_id,
        es.skill_label_preferred AS element_label,
        CAST(NULL AS VARCHAR) AS parent_category,
        CAST(NULL AS DOUBLE) AS importance_im,
        CAST(NULL AS DOUBLE) AS level_lv,
        es.relation_type,
        es.skill_type,
        false AS recommend_suppress,
        false AS not_relevant
    FROM cw_enriched cw
    JOIN occupation_esco_skills es ON cw.esco_uri = es.esco_uri
)
SELECT * FROM wask_rows
UNION ALL
SELECT * FROM esco_rows
"""

con.execute(f"COPY ({flat_sql}) TO '{OUT}/esconet_flat.parquet' (FORMAT PARQUET, COMPRESSION SNAPPY)")
size_kb = (OUT / "esconet_flat.parquet").stat().st_size // 1024

# Stats
stats = con.execute(f"""
    SELECT
        source,
        dimension,
        COUNT(*) AS rows,
        COUNT(DISTINCT pair_id) AS distinct_pairs,
        COUNT(DISTINCT element_id) AS distinct_elements
    FROM read_parquet('{OUT}/esconet_flat.parquet')
    GROUP BY 1, 2
    ORDER BY 1, 2
""").fetchdf()

total = con.execute(f"SELECT COUNT(*) FROM read_parquet('{OUT}/esconet_flat.parquet')").fetchone()[0]
distinct_pairs = con.execute(f"SELECT COUNT(DISTINCT pair_id) FROM read_parquet('{OUT}/esconet_flat.parquet')").fetchone()[0]

print(f"\n✓ esconet_flat.parquet  rows={total:>9,}  pairs={distinct_pairs:,}  size={size_kb:,} KB\n")
print("Row breakdown by source × dimension:")
print(stats.to_string(index=False))
