# ESCONET v0.1 — Data Dictionary

> Inventory ของทุก field + relation ใน ESCONET v0.1 สำหรับใช้เป็น reference เลือก parameter ที่จะใช้ในการ design recommendation engine

**Version:** ESCONET v0.1 (build 2026-05-13)
**Sources:** O*NET-SOC v30.2 (US DoL) + ESCO v1.2.1 EN (EU) + ESCO-O*NET crosswalk v1 (Sep 2022)
**Files:** 9 Parquet tables, ~18 MB compressed
**Top-level row counts:** 943,201 (sum) — 836,571 of which are the denormalized `esconet_flat`

---

## ภาพรวม schema

ESCONET เป็น **star schema 2 ระบบ** ที่เชื่อมกันด้วย crosswalk:

```
                       crosswalk
                  (4,253 SOC↔ESCO pairs)
                         │
        ┌────────────────┴────────────────┐
        │                                 │
   O*NET side                        ESCO side
   ─────────                         ─────────
   occupations_onet      ←→        occupations_esco
        ↓                                ↓
   occupation_wask                  occupation_esco_skills
   (W/A/S/K, IM/LV)                 (essential/optional, reuse_level)
        ↓                                ↓
   occupation_tasks               esco_skill_hierarchy
   (task statements)              (4-level skill tree)

                  Side-table:
                  isco_groups (4-level ISCO hierarchy)
```

`esconet_flat` คือ denormalized join ของทุก table — สำหรับ query ตรงๆ ไม่ต้อง join เอง

---

## 1. occupations_onet (1,016 rows · O*NET occupation dimension)

| Field | Type | Distinct | Description |
|---|---|---|---|
| `onet_soc` | VARCHAR | 1,016 (**PK**) | O*NET-SOC code e.g. `15-1252.00` — รหัสอาชีพมาตรฐาน US BLS |
| `onet_title` | VARCHAR | 1,016 | ชื่ออาชีพภาษาอังกฤษ ("Software Developers") |
| `onet_description` | VARCHAR | 1,016 | คำบรรยายอาชีพ (free text, ~2-4 ประโยค) |
| `soc_major_group` | VARCHAR | 23 | รหัส 2 หลักแรกของ SOC (เช่น `15` = Computer & Mathematical) |
| `soc_major_group_label` | VARCHAR | 23 | ชื่อกลุ่ม SOC ใหญ่ — categorical 23 ค่า |

**SOC major groups ทั้ง 23 ค่า:** 11 Management · 13 Business & Financial · 15 Computer & Math · 17 Architecture & Engineering · 19 Life/Physical/Social Science · 21 Community/Social Service · 23 Legal · 25 Education · 27 Arts/Design/Sports/Media · 29 Healthcare Practitioners · 31 Healthcare Support · 33 Protective Service · 35 Food Service · 37 Building Maintenance · 39 Personal Care · 41 Sales · 43 Office Admin · 45 Farming/Fishing/Forestry · 47 Construction · 49 Maintenance & Repair · 51 Production · 53 Transportation · 55 Military

---

## 2. occupations_esco (3,043 rows · ESCO occupation dimension)

| Field | Type | Distinct | Description |
|---|---|---|---|
| `esco_uri` | VARCHAR | 3,039 (**PK**) | ESCO occupation URI — `http://data.europa.eu/esco/occupation/...` |
| `label_preferred` | VARCHAR | 3,039 | ชื่ออาชีพ canonical EN |
| `alt_labels` | VARCHAR[] | 3,039 | array ของชื่อเรียกอื่น (synonyms) — ใช้ทำ title matching ได้ |
| `esco_description` | VARCHAR | 3,039 | คำบรรยายอาชีพ EN |
| `isco_code` | VARCHAR | 426 | ISCO-08 unit 4 หลัก — **FK → isco_groups.isco_code** |
| `nace_codes` | VARCHAR[] | 1,121 | array ของ NACE industry codes — **อาชีพอาจอยู่ในหลาย industry** เช่น สถิติ ∈ {finance, healthcare} |
| `status` | VARCHAR | 1 | ทั้งหมดเป็น `released` — **ไม่มี information value** |
| `modified_date` | VARCHAR | 2,902 | YYYY-MM-DD ของการแก้ไขล่าสุดใน ESCO (2016 – 2025) |

---

## 3. isco_groups (619 rows · ISCO-08 4-level hierarchy)

| Field | Type | Distinct | Description |
|---|---|---|---|
| `isco_uri` | VARCHAR | 619 (**PK**) | ISCO group URI |
| `isco_code` | VARCHAR | 619 | รหัส ISCO 1-4 หลัก (เช่น `2`, `21`, `213`, `2131`) |
| `isco_label` | VARCHAR | 582 | ชื่อกลุ่มอาชีพ EN |
| `isco_description` | VARCHAR | 619 | คำบรรยาย (free text) |
| `isco_level` | BIGINT | 4 | **ระดับใน hierarchy (ไม่ใช่ระดับทักษะ)** — 1=major, 2=sub-major, 3=minor, 4=unit |
| `isco_major_code` | VARCHAR | 10 | หลักแรก (1-9, +0 = Armed forces) — **นี่คือ proxy ระดับทักษะของอาชีพ** |
| `isco_submajor_code` | VARCHAR | 53 | 2 หลักแรก |
| `isco_minor_code` | VARCHAR | 183 | 3 หลักแรก |

**isco_level distribution:** L1=10 · L2=43 · L3=130 · L4=436

**isco_major_code distribution (อาชีพในแต่ละระดับทักษะ):** M2 (Professionals)=126 · M3 (Associate prof)=110 · M7 (Craft)=86 · M5 (Service/Sales)=58 · M8 (Plant operators)=58 · M9 (Elementary)=51 · M1 (Managers)=47 · M4 (Clerical)=42 · M6 (Agriculture)=31 · M0 (Armed forces)=10

---

## 4. crosswalk (4,253 rows · SOC ↔ ESCO bridge)

| Field | Type | Distinct | Description |
|---|---|---|---|
| `pair_id` | VARCHAR | 4,253 (**PK**) | stable hash ของ `onet_soc \| esco_uri` |
| `onet_soc` | VARCHAR | 940 | **FK → occupations_onet.onet_soc** |
| `esco_uri` | VARCHAR | 2,652 | **FK → occupations_esco.esco_uri** (43 rows ชี้ ISCO URIs แทน) |
| `match_type` | VARCHAR | 5 | **strength ของการ map — สำคัญที่สุดใน table นี้** |

**match_type distribution (asymmetric quality):**

| match_type | rows | meaning | usage |
|---|---|---|---|
| `broadMatch` | 2,053 (48%) | SOC ครอบคลุม ESCO กว้างกว่า | known false positives, ใช้ระวัง |
| `closeMatch` | 1,432 (34%) | ใกล้กันแต่ไม่ตรง 100% | ใช้ได้ |
| `exactMatch` | 498 (12%) | ตรงกัน | ใช้ได้ดีสุด |
| `narrowMatch` | 227 (5%) | SOC แคบกว่า ESCO | ใช้ได้แต่ระวัง |
| `exactISCO` | 43 (1%) | ชี้ ISCO group ไม่ใช่ ESCO occupation | join ไม่ได้กับ occupations_esco |

ที่ scenario เราใช้: `exactMatch + closeMatch` (45% ของ rows)

---

## 5. occupation_wask (143,934 rows · O*NET WASK ratings)

**Long format:** 1 row per (occupation × element). 894 occupations × ~161 elements = ~143k.

| Field | Type | Distinct | Description |
|---|---|---|---|
| `onet_soc` | VARCHAR | 894 | **FK → occupations_onet** |
| `dimension` | VARCHAR | 4 | `W` Work Activities (41 elements) · `A` Abilities (52) · `S` Skills (35) · `K` Knowledge (33) |
| `element_id` | VARCHAR | 161 | O*NET hierarchical ID เช่น `4.A.1.a.1` |
| `element_label` | VARCHAR | 160 | ชื่อ element EN เช่น "Mathematics" |
| `parent_category` | VARCHAR | 25 | sub-grouping ภายใน dimension (ดูตารางด้านล่าง) |
| `importance_im` | DOUBLE | 401 | **IM 1.0–5.0** — ความสำคัญต่ออาชีพ (avg ผู้ตอบ) |
| `level_lv` | DOUBLE | 687 | **LV 0.0–7.0** — ระดับที่อาชีพต้องการ (avg ผู้ตอบ) |
| `recommend_suppress` | BOOLEAN | 2 | True 4.3% — O*NET แนะนำให้ filter ออก (N ตอบน้อยเกินไป) |
| `not_relevant` | BOOLEAN | 2 | True 12.5% — element ไม่ relevant กับอาชีพนี้เลย |
| `domain_source` | VARCHAR | 4 | source ของการ rate — Analyst 54% · Incumbent 34% · Occupational Expert 11% · Analyst-Transition 1% |

**parent_category × dimension** (25 หมวด — ใช้ roll up):

| dim | parent_category |
|---|---|
| **A** | Cognitive · Sensory · Psychomotor · Physical Abilities |
| **K** | Mathematics & Science · Business & Management · Arts & Humanities · Engineering & Technology · Law & Public Safety · **Health Services** · Manufacturing & Production · Communications · Education & Training · Transportation |
| **S** | Technical · Content · Social · Process · Resource Management · Systems · Complex Problem Solving |
| **W** | Interacting With Others · Mental Processes · Work Output · Information Input |

---

## 6. occupation_esco_skills (126,281 rows · ESCO skill relations)

**Long format:** 1 row per (occupation × skill). 3,039 occupations × ~40 skills avg = ~126k.

| Field | Type | Distinct | Description |
|---|---|---|---|
| `esco_uri` | VARCHAR | 3,039 | **FK → occupations_esco** |
| `skill_uri` | VARCHAR | 13,475 | ESCO skill URI (**FK → esco_skill_hierarchy via any level URI**) |
| `skill_label_preferred` | VARCHAR | 13,475 | ชื่อ skill canonical EN |
| `skill_alt_labels` | VARCHAR[] | 13,457 | array ของ synonyms |
| `skill_type` | VARCHAR | 3 | `skill/competence` 73% · **`knowledge`** 27% · `''` 59 rows (data quality) |
| `relation_type` | VARCHAR | 2 | **`essential` 54%** vs `optional` 46% — ESCO บอกว่า skill นี้สำคัญแค่ไหนต่ออาชีพ |
| `skill_reuse_level` | VARCHAR | 4 | **transferability tag — สำคัญสุดสำหรับ recommendation** |

**skill_reuse_level distribution:**
- `cross-sector` (56%) = พกข้ามอุตสาหกรรมได้ — transferable
- `sector-specific` (41%) = ใช้ในกลุ่ม sector เดียวกัน
- `occupation-specific` (3%) = เฉพาะอาชีพนั้นโดยตรง
- `''` (<0.1%) = data quality

**skill_type × skill_reuse_level (cross-tab):**

| | cross-sector | sector-specific | occupation-specific |
|---|---|---|---|
| **knowledge** (34k) | 17,391 (51%) | 16,425 (48%) | 576 (2%) |
| **skill/competence** (92k) | 53,210 (58%) | 35,527 (39%) | 3,093 (3%) |

→ knowledge มีสัดส่วน sector-specific สูงกว่า — ตรงกับสามัญสำนึก (domain knowledge ส่วนใหญ่ผูกกับ sector)

---

## 7. esco_skill_hierarchy (640 rows · ESCO skill tree 4 ชั้น)

**ผังต้นไม้ของ ESCO skills/knowledge แบ่งเป็น 4 ระดับ:**

| Field | Type | Distinct | Description |
|---|---|---|---|
| `level_0_uri/label/code` | VARCHAR | 4 | top — 4 กลุ่มหลัก |
| `level_1_uri/label/code` | VARCHAR | 29 | กลุ่มย่อย level 2 |
| `level_2_uri/label/code` | VARCHAR | 157 | กลุ่มย่อย level 3 |
| `level_3_uri/label/code` | VARCHAR | 453 | leaf categories (= skill_uri ใน occupation_esco_skills ที่ลึกสุด) |
| `description` | VARCHAR | 426 | คำอธิบายแต่ละ leaf |

**level_0 (4 ตัว):**
- `skills` (S) — 385 rows
- `knowledge` (K) — 221 rows
- `transversal skills and competences` (T) — 31 rows
- `language skills and knowledge` (L) — 3 rows

**level_1 ภายใต้ knowledge (13 หัวข้อ):** services · engineering/manufacturing/construction · natural sciences/math/statistics · arts and humanities · **health and welfare** · business/administration/law · social sciences · agriculture · generic · education · ICT · ...

**level_1 ภายใต้ skills (9 หัวข้อ):** communication/collaboration/creativity · handling and moving · information skills · working with machinery · management · assisting/caring · constructing · **working with computers** · ...

→ ใช้ roll up: "human anatomy" (level 3) → "health and welfare" (level 1) → "knowledge" (level 0)

---

## 8. occupation_tasks (18,796 rows · O*NET task statements)

| Field | Type | Distinct | Description |
|---|---|---|---|
| `onet_soc` | VARCHAR | 923 | **FK → occupations_onet** |
| `task_id` | VARCHAR | 18,796 (**PK**) | unique ID |
| `task_statement` | VARCHAR | 17,537 | free text ของ task เช่น *"Review accounts for discrepancies and reconcile differences"* |
| `task_type` | VARCHAR | 3 | **`Core` 73%** · `Supplemental` 23% · `''` 4% |
| `incumbents_responding` | VARCHAR | 164 | จำนวน % ผู้ตอบที่ระบุว่าทำ task นี้ (stored as string) |

→ Free text — เปิดทาง embedding-based matching ที่ taxonomy จับไม่ได้ (เช่น "stock reconcile" ↔ "account reconcile")

---

## 9. esconet_flat (836,571 rows · denormalized join)

**1 row per (pair_id × source × element)** — ทุก crosswalk pair × ทุก WASK element หรือ ESCO skill

ไม่เป็น schema ใหม่ — รวม column จาก table อื่นมาวางเรียงกัน:
- จาก crosswalk: `pair_id`, `onet_soc`, `esco_uri`, `match_type`
- จาก occupations_onet: `onet_title`, `soc_major_group`, `soc_major_group_label`
- จาก occupations_esco: `esco_label`, `isco_code`, `isco_label`, `isco_major_code`, `isco_submajor_code`, `nace_codes`
- จาก WASK side: `dimension` (W/A/S/K), `element_id`, `element_label`, `parent_category`, `importance_im`, `level_lv`, `recommend_suppress`, `not_relevant`
- จาก ESCO skills side: `dimension` (ESCO_S/ESCO_K), `element_id` (=skill_uri), `element_label` (=skill label), `relation_type`, `skill_type`
- column ใหม่: `source` — `onet` หรือ `esco`

**Trade-off:** ใช้ง่ายเพราะไม่ต้อง join แต่ row count บานเพราะ crosswalk fan-out (1 SOC ↔ หลาย ESCO → WASK ของ SOC ถูก duplicate)

**dimension column ใน flat มี 6 ค่า** (vs 4 ใน occupation_wask): `A` `K` `S` `W` (O*NET) · `ESCO_S` `ESCO_K` (ESCO) — เพราะ ESCO ไม่มี W/A

---

## Relations / Join paths

### Primary keys
- `occupations_onet.onet_soc`
- `occupations_esco.esco_uri`
- `isco_groups.isco_uri` (or `isco_code` for direct join)
- `crosswalk.pair_id`
- `occupation_tasks.task_id`

### Join paths ที่ใช้บ่อย

**1. O*NET → ESCO (cross-source query):**
`occupations_onet → crosswalk → occupations_esco`
join keys: `onet_soc` · `esco_uri`
filter: `match_type IN ('exactMatch','closeMatch')` สำหรับ high-confidence

**2. ISCO unit → O*NET-SOC (Thai title → US occupation):**
`(Thai title → ISCO unit ผ่าน mapping ของเรา) → occupations_esco (filter isco_code) → crosswalk → onet_soc`
ที่เราใช้ทุก scenario

**3. Occupation → WASK profile:**
`occupations_onet → occupation_wask` on `onet_soc`
ผลลัพธ์ ~161 rows ต่ออาชีพ (W/A/S/K × element)

**4. Occupation → ESCO skills:**
`occupations_esco → occupation_esco_skills` on `esco_uri`
ผลลัพธ์ ~40 rows ต่ออาชีพ

**5. ESCO skill → category roll-up:**
`occupation_esco_skills.skill_uri → esco_skill_hierarchy (any level URI)`
ใช้ roll up granular skill เป็น domain category

**6. Occupation → tasks (free text):**
`occupations_onet → occupation_tasks` on `onet_soc`
~20 task statements ต่ออาชีพ

**7. ISCO hierarchy walk:**
`occupations_esco.isco_code → isco_groups.isco_code` (level 4 → up via major/sub-major/minor codes)

### หลุม / Data quality issues
- 46 crosswalk rows ชี้ ISCO URIs ไม่ใช่ ESCO occupation → orphan against `occupations_esco`
- 122 rows ใน WASK เป็น `''` (empty) ใน `relation_type` / `skill_type` — data quality artifact
- `status='released'` ทั้งหมดใน occupations_esco → ไม่มี value
- `recommend_suppress=True` (4.3%) + `not_relevant=True` (12.5%) ต้อง filter ก่อนใช้
- `match_type='broadMatch'` (48%) มี false positives known

---

## Summary — ทุก field ใน ESCONET (เรียงตาม "ใช้แล้วหรือยัง")

### ที่ใช้แล้วใน Viz / scenario ปัจจุบัน
- `onet_soc`, `esco_uri`, `isco_code`, `isco_major_code` (join keys + level proxy)
- `match_type` (filter exact/close)
- `importance_im`, `level_lv` (WASK numeric)
- `dimension` (เลือก W/A/S/K)
- `skill_label_preferred`, `skill_reuse_level`, `relation_type` (ESCO skill scoring)
- `recommend_suppress`, `not_relevant` (filter)

### ที่มีใน ESCONET แต่ยังไม่ใช้
- **`skill_type`** (knowledge vs skill/competence) — สิ่งที่ Ford จับมาในรอบที่แล้ว
- **`parent_category`** (WASK roll-up 25 หมวด — รวม "Health Services")
- **`esco_skill_hierarchy`** ทั้ง table (4 ชั้น roll-up)
- **`nace_codes`** (industry — สำคัญสำหรับเคสนักสถิติประกัน vs เทคนิคการแพทย์)
- **`task_statement`, `task_type`** (free text task — สะพานที่ taxonomy จับไม่ได้)
- `domain_source` (Analyst vs Incumbent — quality signal)
- `alt_labels`, `skill_alt_labels` (synonyms — ทำ title bridging)
- `onet_description`, `esco_description`, `isco_description` (free text)
- `soc_major_group` (SOC grouping — ไม่ใช่ ISCO)

### ที่ไม่มี value ทาง analytical
- `status` (ค่าเดียว `released`)
- `modified_date` (metadata)
- `task_id`, `pair_id` (technical keys)
- `incumbents_responding` (% ผู้ตอบ — usable แต่ stored as string, ต้อง parse)

---

*Source: ESCONET_README.md + DuckDB inspection. Inventory compiled 2026-05-15.*
