# ISCO-08 Dataset (Thai translation, National Statistical Office)

**File:** `isco08.csv` (UTF-8 with BOM), `isco08.parquet` (Snappy compressed)

## Source

- **Document:** `SD08_08_50_9.pdf` (549 pages)
- **Publisher:** สำนักงานสถิติแห่งชาติ (National Statistical Office), Thailand
- **Edition:** ISCO-08 Thai translation (International Standard Classification of Occupations 2008)
- **Detail pages used:** 40–498 (pages 1–17 = front matter, 18–37 = TOC, 38–39 = section divider, 499+ = ISCO-88↔ISCO-08 crosswalk appendix)
- **Extraction date:** 2026-05-12

## Hierarchy

ISCO-08 has 4 levels — no 5-digit Thailand-specific extensions in this PDF.

| Level | Thai term | Code format | Records | ISCO-08 target | Notes |
|---|---|---|---|---|---|
| Major | หมวดใหญ่ | 1-digit (0–9) | 10 | 10 | ✓ match |
| SubMajor | หมวดย่อย | 2-digit | 43 | 43 | ✓ match |
| Minor | หมู่ | 3-digit | 130 | 130 | ✓ match |
| Unit | หน่วย | 4-digit | 436 | 436 | ✓ match |
| **Total** | | | **619** | **619** | **100% match** |

## Schema

| Column | Type | Description |
|---|---|---|
| `source` | string | Always `"ISCO-08"` |
| `code` | string | Classification code (1-, 2-, 3-, or 4-digit) |
| `level` | string | One of: `Major`, `SubMajor`, `Minor`, `Unit` |
| `name_th` | string | Thai name of the occupation/class |
| `name_en` | string | Always empty — this PDF has no inline English names |
| `description` | string | Thai description text from the source PDF |
| `parent_code` | string | Code of parent (`""` for Major; 1-digit for SubMajor; 2-digit for Minor; 3-digit for Unit) |
| `page` | int32 | Source page number where the anchor was found |

## Quality metrics

| Level | Records | name_th | name_en | description |
|---|---|---|---|---|
| Major | 10 | 100.0% | 0.0% | 100.0% |
| SubMajor | 43 | 100.0% | 0.0% | 93.0% |
| Minor | 130 | 100.0% | 0.0% | 100.0% |
| Unit | 436 | 100.0% | 0.0% | 100.0% |

- **Duplicates:** 0
- **Orphans (parent_code missing from dataset):** 0
- **Referential integrity:** 100%

## Known quirks

- **`name_en` is empty for all 619 records.** The Thai ISCO-08 publication by NSO does not include English names inline. For English ISCO-08 names, refer to the official ILO ISCO-08 publication.
- **3 SubMajors lack description** (`01` ทหารชั้นสัญญาบัตร, `02` ทหารชั้นประทวน, `03` ทหารยศอื่นๆ — all in military Major `0`). The source PDF provides these as short-form anchors with detail moved entirely to the Unit level. Description coverage drops from 100% to 93% only at SubMajor level for this reason.
- **Page 498 PDF typo**: SubMajor `03` is anchored as `"หมวด 03"` instead of the standard `"หมวดย่อย 03"`. Handled with a fallback regex pattern.
- **Inline Unit anchors**: 2 Units (`2211` แพทย์ทั่วไป, `3139` ช่างเทคนิคควบคุมกระบวนการอื่นๆ) use a non-standard inline format (code + name on same line) rather than separate lines. Handled with an inline pattern.
- **Minor with single Unit**: 30 Minors have only 1 Unit child. In these cases the PDF lists Minor code immediately followed by Unit code, with name/description applying to both. Minor entries inherit name/description from the corresponding Unit.
- **Military codes**: Major `0` (ทหาร) appears last in the document (page 496+), after Major `9`. Ordering in the dataset is by document-traversal order, not by code value.

## Extraction method

Four-pass extraction with zone-aware anchor discovery:

1. **Pass 0 — Zone classification** (root cause v2 fix):
   - `front` (1–17): preface and abbreviations — SKIPPED
   - `toc` (18–37): table of contents — SKIPPED (TOC has same column-position pattern as body; v2 failed because it included TOC, producing false anchors with empty chunks)
   - `divider` (38–39): section dividers — SKIPPED
   - `body` (40–498): detail content — EXTRACTED
   - `appendix` (499+): ISCO-88↔ISCO-08 crosswalk — SKIPPED

2. **Pass 1 — Anchor discovery** in body pages only:
   - Major: `^หมวดใหญ่\s+(\d)\s*$` (1-digit, keyword required)
   - SubMajor: `^หมวดย่อย\s+(\d{2})\s*(.*)$` (2-digit, name often inline)
   - SubMajor (alt): `^หมวด\s+(\d{2})\s*$` (typo fallback)
   - Minor: `^(\d{3})\s*$` (bare 3-digit on own line)
   - Unit: `^(\d{4})\s*$` (bare 4-digit on own line)
   - Unit (inline): `^(\d{4})\s+(\S.*)$` (code + name on same line, rare)
   - Page headers (1–3 digit numeric at start of page) are filtered out.

3. **Pass 2 — Chunk slicing**: for each anchor, collect lines from end of name through start of next anchor.

4. **Pass 3 — Field extraction with PUA decoding**:
   - Decode 19 Adobe Thai PUA codepoints (U+F700–U+F715) used by AngsanaUPC/AngsanaNew fonts: tone marks, vowels above, special characters.
   - Strip code/keyword prefix to get `name_th`; remaining lines become `description`.
   - parent_code derived structurally from code length.

5. **Post-processing**:
   - **Step 1** — Minor inheritance: for any Minor with empty content followed by a Unit with matching 3-digit prefix, inherit name/description from the Unit.
   - **Step 2** — Dedupe: for any `(code, level)` appearing multiple times, prefer the occurrence with non-empty content (cross-references in body text produce empty-content false-positive anchors).
   - **Step 3** — Structural validation: drop any Minor that has no Unit children with matching prefix. Real ISCO-08 Minors always have ≥1 Unit; orphan Minors are false positives from inline cross-reference text.

**Source script:** `extract_isco08_v3.py`

## Differences from v2

The previous v2 extractor failed quality at all levels due to including TOC pages 18–37 in anchor discovery. TOC pages have the same column-position pattern as body pages, so SubMajor/Minor/Unit codes from TOC were captured as anchors with empty chunks (slicing between adjacent TOC anchors produced no text). v3 fixes this by explicit zone classification with TOC excluded.

Additional fixes in v3:
- PUA decoder applied (v2 had it but only partial coverage; v3 has 100% body coverage with 19 codepoints)
- SubMajor inline name pattern (`หมวดย่อย NN <name>`)
- Unit inline name pattern (`NNNN <name>`)
- SubMajor typo fallback (`หมวด NN` for page 498)
- Minor inheritance from single-child Unit
- Structural validation of Minor→Unit relationships
- Duplicate dedup preferring non-empty content
