# Evidence Verification Agent — Design Spec

## Overview

Add an Evidence Verification Agent to the ScholarAgent pipeline that extracts,
stores, and verifies technical claims from papers, then uses verified claims to
ground survey generation and detect unsupported statements during validation.

## Constraints

- Do **not** modify the existing pipeline state machine:
  `PLANNING → RETRIEVAL → ANALYSIS → WRITING → VALIDATION → FEEDBACK`
- Do **not** change the `AgentState` enum, `StateMachine` transitions, or
  `PipelineOrchestrator` public API.
- Do **not** modify system prompt dynamically in the writing stage.
- Do **not** pass raw claim database to the LLM.
- Keep token usage controlled.
- All existing tests must pass.
- Use existing `LLMBase` and `ToolRegistry`.

## Modules

### New: `agent/evidence/`

```
agent/evidence/
├── __init__.py
├── claim_extractor.py    # ClaimExtractor — extracts structured claims from analysis text
├── evidence_store.py     # EvidenceStore, Claim dataclass
└── verifier.py           # ClaimContextBuilder, EvidenceChecker
```

### `Claim` dataclass (in `evidence_store.py`)

```python
@dataclass
class Claim:
    claim: str                    # The technical claim text
    category: str                 # One of: architecture, dataset, benchmark, comparison
    paper_id: str                 # Paper identifier (e.g., "qwen2024")
    confidence: float             # 0.0–1.0
    verified: bool = False        # Whether this claim has been cross-checked
    source_excerpt: str = ""      # Brief supporting excerpt from the paper
```

### `EvidenceStore` (in `evidence_store.py`)

A pipeline-scoped store holding all extracted claims.

**Public API:**
- `add_claims(claims: list[Claim])` — batch insert new claims
- `get_verified_claims(category: str | None = None) -> list[Claim]` — get verified claims, optionally filtered by category
- `get_claims_by_category() -> dict[str, list[Claim]]` — group claims by category
- `get_claims_for_paper(paper_id: str) -> list[Claim]` — get claims linked to a specific paper
- `mark_verified(claim_texts: list[str])` — mark claims as verified
- `get_unverified_claims() -> list[Claim]` — get claims not yet verified
- `get_all_claims() -> list[Claim]` — get all claims
- `clear()` — reset store (called at pipeline start)

### `ClaimExtractor` (in `claim_extractor.py`)

Extracts structured technical claims from the analysis text produced by the
ANALYSIS stage.

**Behavior:**
- Called at the end of `_analyze_papers()`, after the LLM analysis is complete.
- Uses the existing `LLMBase` to send a focused extraction prompt.
- Prompt asks the LLM to identify technical claims in categories:
  `architecture`, `dataset`, `benchmark`, `comparison`.
- Returns structured `Claim` objects.
- Claims are stored into `EvidenceStore` immediately.

**Integration in `PipelineOrchestrator._analyze_papers()`:**

```python
def _analyze_papers(self, papers):
    # ... existing LLM call ...
    analysis = resp.text
    self._analysis = analysis

    # NEW: extract claims
    from agent.evidence.claim_extractor import ClaimExtractor
    extractor = ClaimExtractor(self.llm)
    claims = extractor.extract(analysis, self._papers)
    self._evidence_store.add_claims(claims)

    return analysis
```

### `ClaimContextBuilder` (in `verifier.py`)

Builds a compressed, section-relevant evidence context for the WRITING stage.

**Behavior:**
- Called in `_write_survey()` before the LLM call.
- Retrieves verified claims from `EvidenceStore`.
- Groups claims by category for the section being written.
- Formats as a concise "Evidence Context" block (aiming for ~300 tokens max).
- Does **not** include raw claim database — only a compressed summary.
- Injected into the **user message** (not system prompt) as:

```
=== Evidence Context ===
[Architecture] Qwen2-VL uses dynamic resolution.
[Benchmark] MMLU score: 85.3% (Qwen2-VL, 2024).
...
=== End Evidence Context ===
```

### `EvidenceChecker` (in `verifier.py`)

A two-level validator implementing the existing `Validator` ABC.

**Level 1 — Rule-based comparison against EvidenceStore:**
- Extract candidate claims from the draft using regex patterns:
  - "X uses Y", "X achieves Z%", "X outperforms Y"
  - Benchmark numbers (e.g., `\d+\.?\d*%`, `\d+\.?\d* accuracy`)
  - Model architecture descriptions
- Compare each candidate claim against `EvidenceStore.verified_claims`:
  - **Unsupported claim**: no matching claim in store
  - **Architecture mismatch**: model name matches but architecture description differs
  - **Benchmark inconsistency**: benchmark name matches but number differs
  - **Missing evidence reference**: claim exists but no citation nearby

**Level 2 — LLM semantic verification (only for suspicious claims):**
- Collect candidate claims flagged by Level 1.
- Send only the suspicious claims (not the full paper) to the LLM for semantic
  verification.
- LLM determines: is this claim contradicted by the evidence? Is it plausible?
- Produces a verification verdict.

**Integration as a Validator:**
- Inherits from `agent.feedback.base.Validator`
- Name: `check_evidence`
- Returns `ValidationResult` with issues, score, and repair instructions
- Registered in the `validators` list passed to `PipelineOrchestrator`

## Integration Points

### PipelineOrchestrator changes

| Location | Change |
|---|---|
| `__init__()` | Add `self._evidence_store = EvidenceStore()` |
| `run_pipeline()` | Call `self._evidence_store.clear()` at start |
| `_analyze_papers()` | After LLM call, extract claims and store them |
| `_write_survey()` | Retrieve evidence context via `ClaimContextBuilder` and inject into user prompt |
| `validators` list | Add `EvidenceChecker` to the validator list |

### No changes to

- `AgentState` / `StateMachine`
- `Harness` public API
- `LLMBase` / `ToolRegistry`
- `GuardrailManager`
- Any existing feedback validator

## Error Handling

- **Claim extraction failure**: If LLM extraction fails, log a warning and
  continue with empty claims. Analysis is not blocked.
- **Evidence store empty**: If no claims are available (extraction failed or
  analysis produced no claims), `ClaimContextBuilder` returns an empty string.
  Writing proceeds without evidence context.
- **EvidenceChecker with empty store**: If no verified claims exist, Level 1
  skips comparison and Level 2 falls back to a basic plausibility check.
  Produces a warning but does not fail validation.

## Testing

### New test file: `tests/test_evidence.py`

| Test | Description |
|---|---|
| `test_claim_dataclass` | Claim creation and field defaults |
| `test_evidence_store_add_and_retrieve` | Add claims, retrieve by category, verify |
| `test_evidence_store_empty` | Empty store returns empty lists |
| `test_evidence_store_clear` | Clear resets store |
| `test_claim_extractor_extracts_from_analysis` | MockLLM returns structured claims |
| `test_claim_extractor_empty_analysis` | Empty analysis produces no claims |
| `test_claim_context_builder_empty` | No claims → empty context |
| `test_claim_context_builder_with_verified_claims` | Builds compressed context |
| `test_evidence_checker_level1_unsupported_claim` | Detects unsupported claim in draft |
| `test_evidence_checker_level1_benchmark_mismatch` | Detects benchmark number inconsistency |
| `test_evidence_checker_level1_all_verified` | All claims supported → pass |
| `test_evidence_checker_level2_llm_verify` | Suspicious claim sent to LLM |
| `test_evidence_checker_integration` | Full checker flow with MockLLM |
| `test_evidence_checker_empty_draft` | Empty draft → no issues |
| `test_evidence_checker_no_evidence_store` | Works without evidence store |

### Integration test: `tests/test_pipeline.py`

- `test_orchestrator_evidence_flow` — Full pipeline with evidence extraction,
  context building, and evidence checking.

## File List (new)

```
agent/evidence/__init__.py
agent/evidence/claim_extractor.py
agent/evidence/evidence_store.py
agent/evidence/verifier.py
tests/test_evidence.py
```

## File List (modified)

```
agent/core/pipeline.py          # Add EvidenceStore, extraction, context injection, checker
agent/feedback/__init__.py      # Add EvidenceChecker to exports
```

## Token Budget

- Claim extraction prompt: ~500 tokens input, ~300 tokens output
- Evidence context: ~300 tokens max, injected into existing user prompt
- EvidenceChecker Level 2: only for suspicious claims, ~200 tokens per claim
- Total overhead per pipeline run: ~1500 tokens worst case