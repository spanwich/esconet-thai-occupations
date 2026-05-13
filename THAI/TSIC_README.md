# TSIC Pass 3 — LLM-validated name_th cleanup

**Status:** 🟢 Pass 3 — name_th cleaned via DBD overlay + rule-based Pattern A + LLM (Claude Opus 4.7) review. **Description column still untouched.**

**Files:**
- `tsic_pass3.csv` (UTF-8 with BOM)
- `tsic_pass3.parquet` (Snappy compressed)
- (Previous passes kept for diff: `tsic_pass1.*`, `tsic_pass2.*`)

## Why Pass 3 was needed

Pass 2 used `pythainlp` dictionary scoring + Pattern B regex flagging, but discovered two failure modes:

1. **Dict false-positives** — corrupted tokens like `กำร` (broken `การ`) and `รท` (random 2-letter substring of "ผลิตรท") happen to exist in the dictionary as valid Thai words. So a heavily-corrupted name like `กำรท ำเหมืองแร่และเหมืองหิน` scored 0.857 (dict says 6/7 tokens valid) despite being clearly broken.

2. **Token-level spell-correct introduced garbage** — abandoned because it made 22 records worse vs 4 better on the 157 DBD ground-truth records.

Pass 3 uses **LLM review** (Claude Opus 4.7 reading each name in-context) — solves both: an LLM reads Thai correctly at the morpheme level and won't be fooled by accidental dictionary hits.

## What Pass 3 did

Reviewed all **324 `pattern_b_suspected` records** from Pass 2 (records flagged with Pattern B corruption signatures like `กำร`, `อำหำร`, `ทำง`, etc.) and produced clean corrected names with per-record confidence scores.

For each record, the LLM:
1. Identified Pattern A corruption (consonant + space + tone? + sara aa → sara am)
2. Identified Pattern B corruption (sara am where sara aa belongs, vice versa)
3. Stripped leaked code prefixes (e.g. `"30200 การผลิต..."` → `"การผลิต..."`)
4. Stitched truncated names from description continuation lines (e.g. when name wraps to next line)
5. Assigned confidence ∈ [0,1] based on certainty

DBD-authoritative names (157 records) and rule-corrected names from Pass 2 (115 records) were preserved unchanged.

## Pass 3 schema (additions on top of Pass 2)

| New column | Type | Description |
|---|---|---|
| `name_th_pre_llm` | string | Pass 2 `name_th` value (preserved for diff/audit) |
| `llm_validated` | bool | True if name was processed through LLM review |
| `llm_confidence` | float32 | LLM-assigned confidence ∈ [0,1] |
| `llm_notes` | string | Brief rationale when special handling applied (e.g. "appended continuation from description") |

`name_th_source` now has 4 values: `dbd` / `rule_corrected` / `pdf_original` / **`llm_corrected`** (new)

`name_quality` now has 8 values: `clean_authoritative` / `clean` / **`llm_clean`** (LLM conf ≥ 0.9) / `mostly_clean` / **`llm_review`** (LLM conf < 0.9) / `pattern_b_suspected` (none after Pass 3) / `partial_corruption` / `heavy_corruption` / `no_name`

## Pass 3 outcome

**Source of `name_th`:**

| Source | Count | % |
|---|---|---|
| `pdf_original` | 1,296 | 68.5% |
| `llm_corrected` | 324 | 17.1% |
| `dbd` | 157 | 8.3% |
| `rule_corrected` | 115 | 6.1% |
| **Total** | **1,892** | |

**Name quality distribution:**

| Quality | Count | % | Trust |
|---|---|---|---|
| `clean` (dict-validated) | 1,095 | 57.9% | High |
| `llm_clean` (LLM conf ≥ 0.9) | 297 | 15.7% | High |
| `clean_authoritative` (DBD) | 157 | 8.3% | **Highest** |
| `no_name` | 263 | 13.9% | None |
| `mostly_clean` | 41 | 2.2% | Medium |
| `llm_review` (LLM conf < 0.9) | 27 | 1.4% | **Medium — flagged for human review** |
| `partial_corruption` | 11 | 0.6% | Low |
| `heavy_corruption` | 1 | 0.05% | Lowest |

**Aggregate trustworthy (`clean` + `llm_clean` + `clean_authoritative`):** 1,549 / 1,892 = **81.9%**

(Pass 2: 66.2% → Pass 3: 81.9% — **+15.7 points**)

## Records flagged for human review (`llm_review`, 27 records)

These are records where the LLM applied corrections with confidence below 0.9, usually because the name was truncated mid-word at a page boundary and the LLM had to stitch in continuation text from the description. While the joined text appears correct, the original name boundary is uncertain.

Query: `df[df['name_quality'] == 'llm_review']`

Common pattern: `notes = "appended continuation from description"`. Examples include codes 50122, 52221, 58111, 58112, 84131–84137, etc.

A Thai speaker should verify these 27 records match the official DBD canonical names. They're correct in meaning but the exact wording boundary may differ from authoritative source.

## LLM review limitations

1. **No DBD ground-truth overlap available for in-pass validation.** DBD overlay covered 157 records; LLM targets were the 324 `pattern_b_suspected` records — these sets do NOT overlap (DBD records were never flagged as pattern_b_suspected because they had been replaced with clean DBD text in Pass 2). So we cannot measure LLM accuracy against DBD ground truth in this pass.

2. **LLM trained on broad Thai text** — not specialized in TSIC industrial terminology. Common business/industrial nouns handled confidently; rare specialized terminology (e.g. specific mineral types, chemical processes) may have lower precision.

3. **Stitched continuations are best-effort** — when name wraps across PDF page boundary, the LLM inferred where the name ends and description begins. This boundary may differ from official source.

4. **`description` column NOT processed by LLM.** Same Pattern A/B/C corruption applies. Out of scope for this pass.

5. **263 `no_name` records still empty** — these are parent codes (Division/Group/Class) for which Pass 1 extraction produced no name. LLM cannot recover names that were never extracted. Pass 4 options:
   - Find expanded DBD source covering Division/Group/Class codes
   - Synthesize from child Activity codes' name semantics
   - Manual fill from authoritative TSIC publication

## Remaining cleanup paths (Pass 4+)

| Target | Records | Path |
|---|---|---|
| 263 `no_name` parents | 263 | DBD expanded source / manual / structural inference |
| 27 `llm_review` | 27 | Thai speaker verification |
| 41 `mostly_clean` (dict 0.70-0.95) | 41 | LLM review (next batch) |
| 11 `partial_corruption` (dict 0.40-0.70) | 11 | LLM review |
| 1 `heavy_corruption` | 1 | LLM review |
| All descriptions | 1,629 with desc | Same multi-strategy approach as name_th in future pass |

## Extraction method history

- **Pass 1** (`tsic_pass1.*`): 5-pass extraction from PDF with zone-aware anchoring. Output: 1,892 records, 19.6% clean.
- **Pass 2** (`tsic_pass2.*`): DBD overlay (157) + Pattern A rule (115) + pythainlp scoring. Output: 66.2% trustworthy. Dict-correction approach tested and abandoned (22 worse vs 4 better).
- **Pass 3** (this): LLM review of 324 `pattern_b_suspected` records (Claude Opus 4.7). Output: 81.9% trustworthy.

**Source scripts:** `extract_tsic_v3.py` → `pass2_clean_names.py` → `pass3_llm_corrections.py`

## Files

- `tsic_pass3.parquet` / `tsic_pass3.csv` — current deliverable
- `tsic_pass2.parquet` / `tsic_pass2.csv` — previous pass for diff
- `tsic_pass1.parquet` / `tsic_pass1.csv` — initial baseline
