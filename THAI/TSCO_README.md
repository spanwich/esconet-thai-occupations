# TSCO Dataset (Thailand Standard Classification of Occupations 2544)

**File:** `tsco.csv` (UTF-8 with BOM), `tsco.parquet` (Snappy compressed)

## Source

- **Document:** `20190826-tsco.pdf` (594 pages)
- **Publisher:** กรมการจัดหางาน (Department of Employment), กระทรวงแรงงาน
- **Edition:** TSCO 2544 (B.E. 2544 = A.D. 2001)
- **Detail pages used:** 30–594 (pages 1–29 = preface, intro, abbreviations, structural overview)
- **Extraction date:** 2026-05-12

## Hierarchy

TSCO 2544 is based on ISCO-88 (International Standard Classification of Occupations 1988) with Thailand-specific extensions at the Occupation level.

| Level | Thai term | Code format | Records | ISCO-88 target | Notes |
|---|---|---|---|---|---|
| Major | หมวดใหญ่ | 1-digit | 10 | 10 | ✓ match |
| SubMajor | หมวดย่อย | 2-digit | 27 | 27 | ✓ match (Major 0 has no SubMajor in TSCO) |
| Minor | หมู่ | 3-digit | 116 | 116 | ✓ match |
| Unit | หน่วย | 4-digit | 393 | ~390 | 3 extra = TSCO extensions |
| Occupation | (รหัสอาชีพ) | NNNN.NN | 1,708 | n/a | Thailand-specific occupations |
| **Total** | | | **2,254** | | |

## Schema

| Column | Type | Description |
|---|---|---|
| `source` | string | Always `"TSCO 2544"` |
| `code` | string | Classification code (varies by level; see Hierarchy) |
| `level` | string | One of: `Major`, `SubMajor`, `Minor`, `Unit`, `Occupation` |
| `name_th` | string | Thai name of the occupation/class |
| `name_en` | string | English name (empty when not available in source) |
| `description` | string | Thai description text from the source PDF |
| `parent_code` | string | Code of the parent in the hierarchy (empty for Major) |
| `page` | int32 | Source page number where the anchor was found |

## Quality metrics

| Level | Records | name_th | name_en | description |
|---|---|---|---|---|
| Major | 10 | 100.0% | 90.0% | 100.0% |
| SubMajor | 27 | 100.0% | 88.9% | 100.0% |
| Minor | 116 | 100.0% | 89.7% | 100.0% |
| Unit | 393 | 100.0% | 87.8% | 100.0% |
| Occupation | 1708 | 100.0% | 84.2% | 100.0% |

- **Duplicates:** 0
- **Orphans (parent_code missing from dataset):** 0
- **Referential integrity:** 100%

## Known quirks

- **Major 0 ("ทหาร" / Military)** — description contains a Thailand-specific placeholder code system (T = Trainee, X = New entrance) inherited directly from the source PDF. This is not an extraction artifact; it reflects raw source content.
- **name_en coverage 84–90%** — gaps are mostly Thailand-specific occupations without an English-language equivalent in the source.

## Extraction method

Three-pass extraction over PyMuPDF spans:

1. **Anchor discovery** — identify hierarchy anchors using explicit keyword markers (`หมวดใหญ่ N`, `หมวดย่อย NN`, `หมู่ NNN`, `หน่วย NNNN`, and `NNNN.NN` at line start), with span-line merging at `y_tolerance=5.0` to handle Calibri/Cordia baseline differences.
2. **Chunk slicing** — order anchors by `(page, y)`; each anchor's chunk = lines from its position through the line before the next anchor, walking across page boundaries.
3. **Field extraction** — strip code+keyword prefix to get `name_th`; parse trailing parenthetical for `name_en`; remaining lines become `description`. Sub-listing intros (e.g. `กลุ่มอาชีพในหมู่นี้`) are filtered out.

Source script: `extract_tsco_v2.py` (522 lines)
