# Evidence Grounding Layer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a verified benchmark evidence mechanism, structured paper knowledge representation, improved writing grounding, and enhanced validation to ScholarAgent.

**Architecture:** Three new stores (BenchmarkStore, PaperKnowledgeBase, enhanced EvidenceStore) fed by PDF-derived evidence. PDFs are parsed into chunks, evidence is extracted via LLM, validated against source content, and organized into structured records. The ContextRetriever selects relevant evidence for the writing stage within a configurable token budget. The EvidenceChecker validates draft output against all three stores.

**Tech Stack:** Python 3.10+, existing PyMuPDF (fitz) for PDF parsing, existing LLMBase/MockLLM for LLM interactions, pytest for testing.

## Global Constraints

- No changes to `AgentState`, `StateMachine`, `AgentState` enum
- No new pipeline stages
- No changes to `LLMBase`, `ToolRegistry` public API
- No changes to existing feedback validators (except EvidenceChecker)
- Existing `Claim`, `EvidenceStore`, `ClaimExtractor`, `ClaimVerifier` remain unchanged
- All existing tests must pass
- LLM organizes evidence, but does not create evidence

---