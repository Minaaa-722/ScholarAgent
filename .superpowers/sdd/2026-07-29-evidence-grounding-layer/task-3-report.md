# Task 3 Report: Extractors — BenchmarkExtractor, BenchmarkVerifier, PaperAnalyzer

## Status
DONE

## Commits
- `4b4b00a` feat: add evidence extractors (BenchmarkExtractor, BenchmarkVerifier, PaperAnalyzer)

## Files Created
- `agent/evidence/benchmark_extractor.py` — BenchmarkExtractor and BenchmarkVerifier classes
- `agent/evidence/paper_analyzer.py` — PaperAnalyzer class

## Files Modified
- `agent/evidence/__init__.py` — Added exports for BenchmarkExtractor, BenchmarkVerifier, PaperAnalyzer
- `tests/test_evidence.py` — Added test classes for all three new components

## Implementation Summary

### BenchmarkExtractor
- Extracts structured `BenchmarkRecord` objects from `EvidenceReference` objects
- Uses LLM with focused prompts to parse benchmark results (model_name, benchmark_name, metric, score, split) from evidence excerpts
- Prompt instructs model to only extract from existing evidence, not generate new facts (no create)
- Follows the same pattern as `ClaimExtractor` (system prompt, build prompt, parse response)
- Handles markdown-fenced JSON, invalid JSON, LLM failures, and empty evidence gracefully

### BenchmarkVerifier
- Verifies benchmark records against source evidence and paper metadata
- Checks: non-empty excerpt, semantic consistency (model_name, benchmark_name, and score all appear in excerpt), plausible score range, model-paper link
- `verify()` returns list of record IDs that passed
- `verify_record()` checks a single record against optional paper metadata
- Score plausibility check handles: "x/y" format, "(+y)" modifiers, percentage suffix, and 0-100 range

### PaperAnalyzer
- Extracts structured `PaperKnowledge` from `EvidenceReference` objects
- LLM returns JSON keyed by paper_id with architecture, training, datasets, benchmarks, and limitations
- Each `KnowledgeField` gets evidence_refs for traceability
- Supports multiple papers per response
- Architecture and Training sections are optional (null)

## Test Summary
- 105 total tests in `tests/test_evidence.py` — all passing
- 7 new tests for `TestBenchmarkExtractor`
- 7 new tests for `TestBenchmarkVerifier`
- 6 new tests for `TestPaperAnalyzer`

## Concerns
- Worktree isolation: The agent was launched in worktree `agent-a4b1dc446ded4c070` instead of the intended `evidence-grounding-layer`. Both worktrees are on the same commit (`8e3b2f0`), so the implementation is functionally identical. The report file and commit exist in the launched worktree.