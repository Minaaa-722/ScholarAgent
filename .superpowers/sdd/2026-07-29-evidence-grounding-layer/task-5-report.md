# Task 5 Report: Enhanced EvidenceChecker — 3-store Validation

## Summary

Enhanced the `EvidenceChecker` to validate draft paper claims against all three stores: EvidenceStore, BenchmarkStore, and PaperKnowledgeBase.

## Changes Made

### `agent/evidence/checker.py` — Enhanced EvidenceChecker

- **Constructor**: Added `benchmark_store: BenchmarkStore` and `knowledge_base: PaperKnowledgeBase` as new required parameters
- **New check — `_check_benchmarks()`**: Extracts benchmark names from draft claims and compares against verified records in BenchmarkStore. Detects:
  - Benchmark mismatch: different score than stored record
  - Missing benchmark: benchmark name in draft but no matching record
- **New check — `_check_model_consistency()`**: Extracts architecture claims from draft and compares against PaperKnowledgeBase. Detects architecture/training detail contradictions.
- **New check — `_check_missing_evidence()`**: Gathers evidence texts from all three stores and flags claims with no supporting evidence in any store.
- **Updated `validate()`**: Runs all four checks (EvidenceStore, BenchmarkStore, PaperKnowledgeBase, missing evidence) and merges results.
- **Added extraction helpers**: `_extract_benchmark_name()`, `_extract_score()`, `_extract_model_name()` for parsing claims.
- **Updated severity weights**: Added `"missing_benchmark": 0.3` to the severity weights dict.

### `agent/core/harness.py` — Backward Compatibility

- Updated `EvidenceChecker` instantiation to pass `benchmark_store=BenchmarkStore()` and `knowledge_base=PaperKnowledgeBase()`
- Added imports for `BenchmarkStore` and `PaperKnowledgeBase`

### `tests/test_evidence.py` — Updated and New Tests

**Updated 8 existing tests** to pass `benchmark_store=BenchmarkStore()` and `knowledge_base=PaperKnowledgeBase()`:
- `test_empty_draft`
- `test_all_claims_supported_level1`
- `test_unsupported_claim_level1`
- `test_no_verified_claims_in_store`
- `test_benchmark_number_mismatch`
- `test_level2_llm_verify_clears_claims`
- `test_checker_name`
- `test_checker_no_evidence_store_still_works`

**Added 4 new tests**:
- `test_evidence_checker_benchmark_mismatch` — Detects benchmark number inconsistency using BenchmarkStore
- `test_evidence_checker_model_inconsistency` — Detects architecture description mismatch using PaperKnowledgeBase
- `test_evidence_checker_missing_evidence` — Detects strong claim with no evidence in any store
- `test_evidence_checker_all_three_stores` — Full checker flow with all three stores populated

## Test Results

All tests pass. The new constructor signature is backward compatible for all existing callers.

## Architecture

```
EvidenceChecker
├── EvidenceStore    → _check_against_store()       → unsupported claims
├── BenchmarkStore   → _check_benchmarks()           → benchmark_mismatch / missing_benchmark
├── PaperKnowledgeBase → _check_model_consistency()  → architecture_mismatch
└── All three        → _check_missing_evidence()     → missing_reference
```