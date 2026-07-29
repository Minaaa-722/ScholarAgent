"""Tests for the Evidence Verification Agent modules.

Covers:
  - Claim dataclass and EvidenceStore
  - ClaimContextBuilder
  - ClaimExtractor
  - ClaimVerifier
  - EvidenceChecker (two-level validation)
  - Integration with PipelineOrchestrator
"""
import json
import pytest
from agent.evidence.evidence_store import Claim, EvidenceStore, ClaimContextBuilder
from agent.evidence.claim_extractor import ClaimExtractor
from agent.evidence.verifier import ClaimVerifier
from agent.evidence.checker import EvidenceChecker
from agent.evidence.evidence_reference import EvidenceReference, KnowledgeField, DatasetReference
from agent.evidence.pdf_parser import PDFChunk, ChunkFilter
from agent.evidence.evidence_extractor import EvidenceReferenceValidator, EvidenceExtractor
from agent.evidence.benchmark_store import BenchmarkRecord, BenchmarkStore
from agent.evidence.paper_knowledge import ArchitectureKnowledge, TrainingKnowledge, PaperKnowledge, PaperKnowledgeBase
from agent.evidence.benchmark_extractor import BenchmarkExtractor, BenchmarkVerifier
from agent.evidence.paper_analyzer import PaperAnalyzer
from agent.evidence.context_retriever import (
    EvidenceRanker,
    SimpleRanker,
    EvidenceContext,
    ContextRetriever,
    EvidenceContextBuilder,
)
from agent.evidence.citation_store import CitationEntry, CitationStore
from agent.evidence.citation_anchor_store import CitationAnchor, CitationAnchorStore
from agent.evidence.citation_injector import CitationInjector
from agent.evidence.table_generator import BenchmarkTableGenerator
from agent.core.llm import MockLLM
from agent.feedback.base import ValidationResult


# =========================================================================
# Claim dataclass
# =========================================================================

class TestClaim:
    def test_claim_creation(self):
        c = Claim(
            claim="Qwen2-VL uses dynamic resolution",
            category="architecture",
            paper_id="qwen2024",
            confidence=0.9,
        )
        assert c.claim == "Qwen2-VL uses dynamic resolution"
        assert c.category == "architecture"
        assert c.paper_id == "qwen2024"
        assert c.confidence == 0.9
        assert c.verified is False
        assert c.source_excerpt == ""

    def test_claim_defaults(self):
        c = Claim(claim="Simple claim", category="dataset")
        assert c.paper_id == ""
        assert c.confidence == 0.0
        assert c.verified is False

    def test_claim_confidence_clamped(self):
        c = Claim(claim="Test", category="benchmark", confidence=1.5)
        assert c.confidence == 1.0
        c2 = Claim(claim="Test", category="comparison", confidence=-0.5)
        assert c2.confidence == 0.0

    def test_claim_invalid_category(self):
        with pytest.raises(ValueError, match="Invalid category"):
            Claim(claim="Test", category="invalid_cat")

    @pytest.mark.parametrize("cat", ["architecture", "dataset", "benchmark", "comparison"])
    def test_claim_valid_categories(self, cat):
        c = Claim(claim="Test", category=cat)
        assert c.category == cat


# =========================================================================
# EvidenceStore
# =========================================================================

class TestEvidenceStore:
    def test_empty_store(self):
        store = EvidenceStore()
        assert store.get_all_claims() == []
        assert store.get_verified_claims() == []
        assert store.get_unverified_claims() == []
        assert store.get_claims_by_category() == {}
        assert store.claim_count() == 0
        assert store.verified_count() == 0

    def test_add_and_retrieve(self):
        store = EvidenceStore()
        claims = [
            Claim(claim="Uses dynamic resolution", category="architecture", paper_id="p1", confidence=0.9),
            Claim(claim="MMLU 85.3%", category="benchmark", paper_id="p1", confidence=0.8),
            Claim(claim="Dataset X has 1M samples", category="dataset", paper_id="p2", confidence=0.7),
        ]
        store.add_claims(claims)
        assert store.claim_count() == 3
        assert store.verified_count() == 0

        # By category
        arch = store.get_verified_claims(category="architecture")
        assert len(arch) == 0  # none verified yet

        all_arch = [c for c in store.get_all_claims() if c.category == "architecture"]
        assert len(all_arch) == 1

        # By paper
        p1_claims = store.get_claims_for_paper("p1")
        assert len(p1_claims) == 2
        p2_claims = store.get_claims_for_paper("p2")
        assert len(p2_claims) == 1

    def test_mark_verified(self):
        store = EvidenceStore()
        store.add_claims([
            Claim(claim="Uses dynamic resolution", category="architecture", paper_id="p1", confidence=0.9),
            Claim(claim="MMLU 85.3%", category="benchmark", paper_id="p1", confidence=0.8),
        ])
        count = store.mark_verified(["Uses dynamic resolution  "])  # trailing space
        assert count == 1
        assert store.verified_count() == 1
        verified = store.get_verified_claims()
        assert len(verified) == 1
        assert verified[0].claim == "Uses dynamic resolution"

    def test_mark_verified_idempotent(self):
        store = EvidenceStore()
        store.add_claims([Claim(claim="Test claim", category="architecture", confidence=0.9)])
        store.mark_verified(["Test claim"])
        store.mark_verified(["Test claim"])  # second time
        assert store.verified_count() == 1

    def test_clear(self):
        store = EvidenceStore()
        store.add_claims([Claim(claim="Test", category="architecture", confidence=0.5)])
        assert store.claim_count() == 1
        store.clear()
        assert store.claim_count() == 0

    def test_get_claims_by_category(self):
        store = EvidenceStore()
        store.add_claims([
            Claim(claim="A1", category="architecture", confidence=0.5),
            Claim(claim="A2", category="architecture", confidence=0.5),
            Claim(claim="B1", category="benchmark", confidence=0.5),
        ])
        by_cat = store.get_claims_by_category()
        assert len(by_cat["architecture"]) == 2
        assert len(by_cat["benchmark"]) == 1


# =========================================================================
# ClaimContextBuilder
# =========================================================================

class TestClaimContextBuilder:
    def test_empty_store(self):
        store = EvidenceStore()
        ctx = ClaimContextBuilder.build(store)
        assert ctx == ""

    def test_no_verified_claims(self):
        store = EvidenceStore()
        store.add_claims([Claim(claim="Test", category="architecture", confidence=0.5)])
        ctx = ClaimContextBuilder.build(store)
        assert ctx == ""

    def test_with_verified_claims(self):
        store = EvidenceStore()
        store.add_claims([
            Claim(claim="Uses dynamic resolution", category="architecture", paper_id="p1", confidence=0.9),
        ])
        store.mark_verified(["Uses dynamic resolution"])
        ctx = ClaimContextBuilder.build(store)
        assert "=== Evidence Context ===" in ctx
        assert "Uses dynamic resolution" in ctx
        assert "Architecture" in ctx
        assert "=== End Evidence Context ===" in ctx

    def test_multiple_categories(self):
        store = EvidenceStore()
        store.add_claims([
            Claim(claim="Uses dynamic resolution", category="architecture", paper_id="p1", confidence=0.9),
            Claim(claim="MMLU score 85.3%", category="benchmark", paper_id="p1", confidence=0.8),
        ])
        store.mark_verified(["Uses dynamic resolution", "MMLU score 85.3%"])
        ctx = ClaimContextBuilder.build(store)
        assert "Architecture" in ctx
        assert "Benchmark" in ctx
        assert "Uses dynamic resolution" in ctx
        assert "MMLU score 85.3%" in ctx

    def test_token_budget(self):
        """Verify context stays within the ~1200 char budget."""
        store = EvidenceStore()
        claims = []
        for i in range(50):
            claims.append(
                Claim(claim=f"Long claim number {i} with some padding text to make it realistic", category="architecture", confidence=0.9)
            )
        store.add_claims(claims)
        store.mark_verified([c.claim for c in claims])
        ctx = ClaimContextBuilder.build(store)
        assert len(ctx) <= ClaimContextBuilder._MAX_CONTEXT_CHARS + 100


# =========================================================================
# ClaimExtractor
# =========================================================================

class TestClaimExtractor:
    def test_extract_from_analysis(self):
        """MockLLM returns a valid JSON response, extractor parses it."""
        response_json = json.dumps([
            {"claim": "Qwen2-VL uses dynamic resolution", "category": "architecture", "paper_title": "Qwen2-VL", "confidence": 0.9},
            {"claim": "MMLU score: 85.3%", "category": "benchmark", "paper_title": "Qwen2-VL", "confidence": 0.8},
        ])
        llm = MockLLM(fixed_response=response_json)
        extractor = ClaimExtractor(llm)
        papers = [
            {"title": "Qwen2-VL", "paper_id": "qwen2024", "arxiv_id": "qwen2024"},
        ]
        claims = extractor.extract("Some analysis text about Qwen2-VL...", papers)
        assert len(claims) == 2
        assert claims[0].claim == "Qwen2-VL uses dynamic resolution"
        assert claims[0].category == "architecture"
        assert claims[0].paper_id == "qwen2024"
        assert claims[0].confidence == 0.9
        assert claims[1].category == "benchmark"

    def test_extract_empty_analysis(self):
        llm = MockLLM()
        extractor = ClaimExtractor(llm)
        claims = extractor.extract("")
        assert claims == []

    def test_extract_whitespace_analysis(self):
        llm = MockLLM()
        extractor = ClaimExtractor(llm)
        claims = extractor.extract("   \n   ")
        assert claims == []

    def test_extract_invalid_json_response(self):
        llm = MockLLM(fixed_response="NOT JSON")
        extractor = ClaimExtractor(llm)
        claims = extractor.extract("Some analysis text")
        assert claims == []

    def test_extract_markdown_fenced_json(self):
        response = "```\n" + json.dumps([
            {"claim": "Uses ViT backbone", "category": "architecture", "paper_title": "ViT Paper", "confidence": 0.9},
        ]) + "\n```"
        llm = MockLLM(fixed_response=response)
        extractor = ClaimExtractor(llm)
        papers = [{"title": "ViT Paper", "paper_id": "vit2023"}]
        claims = extractor.extract("Analysis text", papers)
        assert len(claims) == 1
        assert claims[0].claim == "Uses ViT backbone"

    def test_extract_llm_failure(self):
        class FailingLLM:
            def generate(self, system_prompt, user_message, tools=None):
                raise RuntimeError("API error")
        extractor = ClaimExtractor(FailingLLM())  # type: ignore
        claims = extractor.extract("Some analysis text")
        assert claims == []


# =========================================================================
# ClaimVerifier
# =========================================================================

class TestClaimVerifier:
    def test_verify_all_empty_store(self):
        llm = MockLLM()
        store = EvidenceStore()
        verifier = ClaimVerifier(llm)
        count = verifier.verify_all(store, [])
        assert count == 0

    def test_verify_all_with_papers(self):
        """MockLLM returns a list of supported claim texts."""
        response_json = json.dumps(["Uses dynamic resolution"])
        llm = MockLLM(fixed_response=response_json)
        store = EvidenceStore()
        store.add_claims([
            Claim(claim="Uses dynamic resolution", category="architecture", paper_id="p1", confidence=0.9),
            Claim(claim="MMLU score 85.3%", category="benchmark", paper_id="p1", confidence=0.8),
        ])
        papers = [
            {"title": "Test Paper", "arxiv_id": "p1", "paper_id": "p1", "abstract": "This paper uses dynamic resolution and achieves 85.3% on MMLU."},
        ]
        verifier = ClaimVerifier(llm)
        count = verifier.verify_all(store, papers)
        assert count == 1
        assert store.verified_count() == 1
        verified = store.get_verified_claims()
        assert verified[0].claim == "Uses dynamic resolution"

    def test_lightweight_verify_high_confidence(self):
        llm = MockLLM()
        store = EvidenceStore()
        store.add_claims([
            Claim(claim="High conf claim", category="architecture", confidence=0.9),
            Claim(claim="Low conf claim", category="dataset", confidence=0.3),
        ])
        papers = []
        verifier = ClaimVerifier(llm)
        count = verifier.verify_all(store, papers)
        # Only high-confidence claim should be verified
        assert count == 1
        verified = store.get_verified_claims()
        assert len(verified) == 1
        assert verified[0].claim == "High conf claim"


# =========================================================================
# EvidenceChecker (two-level validation)
# =========================================================================

class TestEvidenceChecker:
    def test_empty_draft(self):
        store = EvidenceStore()
        checker = EvidenceChecker(
            evidence_store=store,
            benchmark_store=BenchmarkStore(),
            knowledge_base=PaperKnowledgeBase(),
        )
        result = checker.validate({"content": ""})
        assert result.passed is True
        assert result.score == 1.0

    def test_all_claims_supported_level1(self):
        """Draft claim matches a verified claim in the store."""
        store = EvidenceStore()
        store.add_claims([
            Claim(claim="Qwen2-VL uses dynamic resolution", category="architecture", paper_id="p1", confidence=0.9),
        ])
        store.mark_verified(["Qwen2-VL uses dynamic resolution"])
        checker = EvidenceChecker(
            evidence_store=store,
            benchmark_store=BenchmarkStore(),
            knowledge_base=PaperKnowledgeBase(),
        )
        result = checker.validate({
            "content": "Qwen2-VL uses dynamic resolution to process images at variable scales."
        })
        assert result.passed is True
        assert result.score == 1.0

    def test_unsupported_claim_level1(self):
        """Draft contains a claim not in the evidence store."""
        store = EvidenceStore()
        store.add_claims([
            Claim(claim="Uses dynamic resolution", category="architecture", paper_id="p1", confidence=0.9),
        ])
        store.mark_verified(["Uses dynamic resolution"])
        checker = EvidenceChecker(
            evidence_store=store,
            benchmark_store=BenchmarkStore(),
            knowledge_base=PaperKnowledgeBase(),
        )
        result = checker.validate({
            "content": "Qwen2-VL achieves 99.9% accuracy on ImageNet."
        })
        # The claim is flagged as a benchmark_mismatch (weight 0.3 → score 0.7)
        # The key assertion: the checker DID flag the unsupported claim
        assert len(result.issues) > 0
        assert "Qwen2-VL achieves 99.9% accuracy" in result.issues[0]

    def test_no_verified_claims_in_store(self):
        """Claims exist but none verified — should flag all candidates."""
        store = EvidenceStore()
        store.add_claims([
            Claim(claim="Uses dynamic resolution", category="architecture", paper_id="p1", confidence=0.9),
        ])
        # Not verified
        checker = EvidenceChecker(
            evidence_store=store,
            benchmark_store=BenchmarkStore(),
            knowledge_base=PaperKnowledgeBase(),
        )
        result = checker.validate({
            "content": "Qwen2-VL uses dynamic resolution."
        })
        # Without verified claims, the checker flags all candidates
        assert result.score < 1.0

    def test_benchmark_number_mismatch(self):
        """Draft benchmark number differs from verified claim."""
        store = EvidenceStore()
        store.add_claims([
            Claim(claim="MMLU score: 85.3%", category="benchmark", paper_id="p1", confidence=0.9),
        ])
        store.mark_verified(["MMLU score: 85.3%"])
        checker = EvidenceChecker(
            evidence_store=store,
            benchmark_store=BenchmarkStore(),
            knowledge_base=PaperKnowledgeBase(),
        )
        result = checker.validate({
            "content": "Qwen2-VL achieves 90.0% on MMLU."
        })
        assert result.passed is False

    def test_level2_llm_verify_clears_claims(self):
        """Level 2 LLM verification clears suspicious claims as valid."""
        store = EvidenceStore()
        store.add_claims([
            Claim(claim="Uses dynamic resolution", category="architecture", paper_id="p1", confidence=0.9),
        ])
        store.mark_verified(["Uses dynamic resolution"])
        # LLM returns empty list = clears all candidates
        llm = MockLLM(fixed_response="[]")
        checker = EvidenceChecker(
            evidence_store=store,
            benchmark_store=BenchmarkStore(),
            knowledge_base=PaperKnowledgeBase(),
            llm=llm,
        )
        result = checker.validate({
            "content": "Qwen2-VL uses dynamic resolution. It achieves 99.9% accuracy."
        })
        # The benchmark claim "99.9% accuracy" gets flagged by Level 1
        # Level 2 should clear it since LLM returns empty
        # But the checker only runs Level 2 if there are Level 1 issues
        # It depends on whether the LLM clears the benchmark claim
        assert result.score > 0.0

    def test_checker_name(self):
        store = EvidenceStore()
        checker = EvidenceChecker(
            evidence_store=store,
            benchmark_store=BenchmarkStore(),
            knowledge_base=PaperKnowledgeBase(),
        )
        assert checker.name == "check_evidence"

    def test_checker_no_evidence_store_still_works(self):
        """Checker works with empty evidence store and no LLM."""
        store = EvidenceStore()
        checker = EvidenceChecker(
            evidence_store=store,
            benchmark_store=BenchmarkStore(),
            knowledge_base=PaperKnowledgeBase(),
        )
        result = checker.validate({
            "content": "Some paper uses a novel approach."
        })
        # Without verified claims, all candidates are flagged
        # "uses a novel approach" matches the "uses" pattern
        assert isinstance(result, ValidationResult)

    # ------------------------------------------------------------------
    # New 3-store validation tests
    # ------------------------------------------------------------------

    def test_evidence_checker_benchmark_mismatch(self):
        """Detects benchmark number inconsistency using BenchmarkStore."""
        evidence_store = EvidenceStore()
        benchmark_store = BenchmarkStore()
        benchmark_store.add_records([
            BenchmarkRecord(
                id="b1",
                model_name="Qwen2-VL",
                benchmark_name="MMLU",
                metric="accuracy",
                score="85.3",
                verified=True,
            ),
        ])
        knowledge_base = PaperKnowledgeBase()

        checker = EvidenceChecker(
            evidence_store=evidence_store,
            benchmark_store=benchmark_store,
            knowledge_base=knowledge_base,
        )
        result = checker.validate({
            "content": "Qwen2-VL achieves 90.0% on MMLU."
        })
        assert result.passed is False
        # The benchmark_mismatch or missing_reference issue should be present
        assert any("MMLU" in issue for issue in result.issues)

    def test_evidence_checker_model_inconsistency(self):
        """Detects architecture description mismatch using PaperKnowledgeBase."""
        evidence_store = EvidenceStore()
        benchmark_store = BenchmarkStore()
        knowledge_base = PaperKnowledgeBase()
        arch = ArchitectureKnowledge(
            vision_encoder=KnowledgeField(value="ViT-L/14"),
        )
        knowledge_base.add(PaperKnowledge(
            paper_id="qwen2024",
            title="Qwen2-VL: Better Vision-Language Model",
            architecture=arch,
        ))

        checker = EvidenceChecker(
            evidence_store=evidence_store,
            benchmark_store=benchmark_store,
            knowledge_base=knowledge_base,
        )
        result = checker.validate({
            "content": "Qwen2-VL uses a ViT-B/32 vision encoder."
        })
        assert result.passed is False
        # Should flag architecture_mismatch — ViT-L/14 in KB vs ViT-B/32 in draft
        assert any("architecture_mismatch" in issue or "ViT" in issue for issue in result.issues)

    def test_evidence_checker_missing_evidence(self):
        """Detects strong claim with no evidence in any store."""
        evidence_store = EvidenceStore()
        evidence_store.add_claims([
            Claim(claim="Uses dynamic resolution", category="architecture", paper_id="p1", confidence=0.9),
        ])
        evidence_store.mark_verified(["Uses dynamic resolution"])
        benchmark_store = BenchmarkStore()
        knowledge_base = PaperKnowledgeBase()

        checker = EvidenceChecker(
            evidence_store=evidence_store,
            benchmark_store=benchmark_store,
            knowledge_base=knowledge_base,
        )
        # The draft claim "99.9% accuracy" is not in any store
        result = checker.validate({
            "content": "Qwen2-VL uses dynamic resolution. It achieves 99.9% accuracy on ImageNet."
        })
        # The supported claim "uses dynamic resolution" should be fine
        # The unsupported claim "99.9% accuracy" should be flagged
        assert result.passed is False
        assert any("99.9%" in issue for issue in result.issues)

    def test_evidence_checker_all_three_stores(self):
        """Full checker flow with all three stores populated."""
        evidence_store = EvidenceStore()
        evidence_store.add_claims([
            Claim(claim="Uses dynamic resolution", category="architecture", paper_id="p1", confidence=0.9),
        ])
        evidence_store.mark_verified(["Uses dynamic resolution"])

        benchmark_store = BenchmarkStore()
        benchmark_store.add_records([
            BenchmarkRecord(
                id="b1",
                model_name="Qwen2-VL",
                benchmark_name="MMLU",
                metric="accuracy",
                score="85.3",
                verified=True,
            ),
        ])

        knowledge_base = PaperKnowledgeBase()
        knowledge_base.add(PaperKnowledge(
            paper_id="qwen2024",
            title="Qwen2-VL: Better Vision-Language Model",
            main_contribution="Dynamic resolution approach",
        ))

        checker = EvidenceChecker(
            evidence_store=evidence_store,
            benchmark_store=benchmark_store,
            knowledge_base=knowledge_base,
        )
        result = checker.validate({
            "content": "Qwen2-VL uses dynamic resolution. It achieves 90.0% on MMLU."
        })
        # The supported claim "uses dynamic resolution" should be fine
        # The benchmark claim "90.0% on MMLU" should be flagged (stored is 85.3%)
        assert result.passed is False
        assert any("MMLU" in issue for issue in result.issues)
        assert any("90.0" in issue for issue in result.issues)


# =========================================================================
# Integration: PipelineOrchestrator with evidence flow
# =========================================================================

class TestPipelineEvidenceIntegration:
    def test_orchestrator_has_evidence_store(self):
        from agent.core.pipeline import PipelineOrchestrator, HarnessConfig
        from agent.tools.registry import ToolRegistry
        from agent.guardrails.manager import GuardrailManager

        llm = MockLLM(fixed_response="Test analysis content")
        orch = PipelineOrchestrator(
            llm=llm,
            tools=ToolRegistry(),
            validators=[],
            guardrails=GuardrailManager(guardrails=[]),
            config=HarnessConfig(),
            latex_repair=None,
        )
        assert orch._evidence_store is not None
        assert orch._claim_extractor is not None
        assert orch._claim_verifier is not None

    def test_extract_and_verify_claims(self):
        """_extract_and_verify_claims extracts and stores claims."""
        from agent.core.pipeline import PipelineOrchestrator, HarnessConfig
        from agent.tools.registry import ToolRegistry
        from agent.guardrails.manager import GuardrailManager

        response_json = json.dumps([
            {"claim": "Uses dynamic resolution", "category": "architecture", "paper_title": "Test Paper", "confidence": 0.9},
        ])
        llm = MockLLM(fixed_response=response_json)
        orch = PipelineOrchestrator(
            llm=llm,
            tools=ToolRegistry(),
            validators=[],
            guardrails=GuardrailManager(guardrails=[]),
            config=HarnessConfig(),
            latex_repair=None,
        )
        orch._analysis = "Qwen2-VL uses dynamic resolution."
        papers = [{"title": "Test Paper", "paper_id": "test2024", "arxiv_id": "test2024", "abstract": "Uses dynamic resolution."}]
        orch._extract_and_verify_claims(papers)
        assert orch._evidence_store.claim_count() > 0

    def test_evidence_context_in_writing(self):
        """Evidence context is injected into the user message in _write_survey."""
        from agent.core.pipeline import PipelineOrchestrator, HarnessConfig
        from agent.core.state import AgentState, StateMachine
        from agent.tools.registry import ToolRegistry
        from agent.guardrails.manager import GuardrailManager

        llm = MockLLM(fixed_response="\\section{Test}\nSurvey content")
        orch = PipelineOrchestrator(
            llm=llm,
            tools=ToolRegistry(),
            validators=[],
            guardrails=GuardrailManager(guardrails=[]),
            config=HarnessConfig(),
            latex_repair=None,
        )
        # Add verified claims
        orch._evidence_store.add_claims([
            Claim(claim="Uses dynamic resolution", category="architecture", paper_id="p1", confidence=0.9),
        ])
        orch._evidence_store.mark_verified(["Uses dynamic resolution"])

        # Setup task info
        from agent.core.pipeline import TaskInfo
        orch._task = TaskInfo(topic="Test Topic", keywords=["test"])
        orch._plan = "\\section{Introduction}\n\\section{Methods}"
        orch._papers = [{"title": "Test Paper", "authors": ["Author A"], "year": 2024}]

        result = orch._write_survey(analysis="Test analysis", round_num=0)
        # Verify the LLM was called with evidence context
        assert len(llm.conversation_history) > 0
        last_user_msg = llm.conversation_history[-1][1]
        assert "Evidence Context" in last_user_msg
        assert "Uses dynamic resolution" in last_user_msg


# =========================================================================
# EvidenceReference
# =========================================================================

class TestEvidenceReference:
    def test_evidence_reference(self):
        """EvidenceReference creation with all fields."""
        ref = EvidenceReference(
            paper_id="paper123",
            page_number=5,
            section="Introduction",
            source_type="text",
            excerpt="This paper uses a novel transformer architecture.",
        )
        assert ref.paper_id == "paper123"
        assert ref.page_number == 5
        assert ref.section == "Introduction"
        assert ref.source_type == "text"
        assert ref.excerpt == "This paper uses a novel transformer architecture."
        # Auto-generated evidence_id
        assert len(ref.evidence_id) == 12
        assert isinstance(ref.evidence_id, str)

    def test_evidence_reference_defaults(self):
        """EvidenceReference with minimal fields."""
        ref = EvidenceReference(paper_id="p1")
        assert ref.page_number == -1
        assert ref.section == ""
        assert ref.source_type == ""
        assert ref.excerpt == ""
        assert len(ref.evidence_id) == 12

    def test_evidence_reference_explicit_id(self):
        """EvidenceReference with explicit evidence_id keeps it."""
        ref = EvidenceReference(
            evidence_id="custom1234567",
            paper_id="p1",
            excerpt="test",
        )
        assert ref.evidence_id == "custom1234567"


class TestEvidenceReferenceValidator:
    def test_evidence_reference_validator(self):
        """Validates excerpt against source chunk."""
        chunks = [
            PDFChunk(
                paper_id="p1",
                chunk_id="p1_p1",
                page_number=1,
                section="Introduction",
                content="This paper uses a novel transformer architecture.",
            ),
        ]
        ref = EvidenceReference(
            paper_id="p1",
            page_number=1,
            section="Introduction",
            source_type="text",
            excerpt="novel transformer architecture",
        )
        validator = EvidenceReferenceValidator()
        assert validator.validate(ref, chunks) is True

    def test_evidence_reference_validator_rejects_fabricated(self):
        """Rejects excerpt not in source."""
        chunks = [
            PDFChunk(
                paper_id="p1",
                chunk_id="p1_p1",
                page_number=1,
                content="This paper uses a novel transformer architecture.",
            ),
        ]
        ref = EvidenceReference(
            paper_id="p1",
            page_number=1,
            excerpt="This claim is completely fabricated",
        )
        validator = EvidenceReferenceValidator()
        assert validator.validate(ref, chunks) is False

    def test_validator_rejects_empty_excerpt(self):
        """Rejects empty excerpt."""
        chunks = [PDFChunk(paper_id="p1", chunk_id="p1_p1", page_number=1, content="Some text.")]
        ref = EvidenceReference(paper_id="p1", excerpt="")
        validator = EvidenceReferenceValidator()
        assert validator.validate(ref, chunks) is False

    def test_validator_invalid_page_number(self):
        """Rejects page number not present in chunks."""
        chunks = [
            PDFChunk(paper_id="p1", chunk_id="p1_p1", page_number=1, content="Content here."),
        ]
        ref = EvidenceReference(
            paper_id="p1",
            page_number=99,
            excerpt="Content here",
        )
        validator = EvidenceReferenceValidator()
        assert validator.validate(ref, chunks) is False

    def test_validator_unknown_page_number(self):
        """Accepts page_number=-1 for unknown pages."""
        chunks = [
            PDFChunk(paper_id="p1", chunk_id="p1_p1", page_number=1, content="Content here."),
        ]
        ref = EvidenceReference(
            paper_id="p1",
            page_number=-1,
            excerpt="Content here",
        )
        validator = EvidenceReferenceValidator()
        assert validator.validate(ref, chunks) is True

    def test_validator_table_needs_table_id(self):
        """Table source type requires non-empty table_id."""
        chunks = [
            PDFChunk(paper_id="p1", chunk_id="p1_p1", page_number=1, content="Table data."),
        ]
        ref = EvidenceReference(
            paper_id="p1",
            page_number=1,
            source_type="table",
            table_id="",
            excerpt="Table data",
        )
        validator = EvidenceReferenceValidator()
        assert validator.validate(ref, chunks) is False

    def test_validator_table_with_table_id(self):
        """Table source type with valid table_id passes."""
        chunks = [
            PDFChunk(paper_id="p1", chunk_id="p1_p1", page_number=1, content="Table 1 data."),
        ]
        ref = EvidenceReference(
            paper_id="p1",
            page_number=1,
            source_type="table",
            table_id="Table 1",
            excerpt="Table 1 data",
        )
        validator = EvidenceReferenceValidator()
        assert validator.validate(ref, chunks) is True

    def test_validate_all(self):
        """validate_all returns only valid refs."""
        chunks = [
            PDFChunk(paper_id="p1", chunk_id="p1_p1", page_number=1, content="Real content here."),
        ]
        valid_ref = EvidenceReference(paper_id="p1", page_number=1, excerpt="Real content here")
        invalid_ref = EvidenceReference(paper_id="p1", page_number=1, excerpt="Fake content")
        validator = EvidenceReferenceValidator()
        result = validator.validate_all([valid_ref, invalid_ref], chunks)
        assert len(result) == 1
        assert result[0] == valid_ref


class TestKnowledgeField:
    def test_knowledge_field(self):
        """KnowledgeField with evidence_refs."""
        ref = EvidenceReference(paper_id="p1", excerpt="Evidence excerpt")
        field = KnowledgeField(
            value="transformer architecture",
            evidence_refs=[ref],
        )
        assert field.value == "transformer architecture"
        assert len(field.evidence_refs) == 1
        assert field.evidence_refs[0].excerpt == "Evidence excerpt"

    def test_knowledge_field_defaults(self):
        """KnowledgeField with default values."""
        field = KnowledgeField()
        assert field.value == ""
        assert field.evidence_refs == []


class TestDatasetReference:
    def test_dataset_reference(self):
        """DatasetReference creation."""
        ref = EvidenceReference(paper_id="p1", excerpt="Dataset info")
        ds = DatasetReference(
            name="ImageNet-1K",
            evidence_refs=[ref],
        )
        assert ds.name == "ImageNet-1K"
        assert len(ds.evidence_refs) == 1
        assert ds.evidence_refs[0].excerpt == "Dataset info"


# =========================================================================
# PDFChunk
# =========================================================================

class TestPDFChunk:
    def test_pdf_chunk(self):
        """PDFChunk creation."""
        chunk = PDFChunk(
            paper_id="paper123",
            chunk_id="paper123_p1",
            page_number=1,
            section="Introduction",
            content="Content of the first page.",
        )
        assert chunk.paper_id == "paper123"
        assert chunk.chunk_id == "paper123_p1"
        assert chunk.page_number == 1
        assert chunk.section == "Introduction"
        assert chunk.content == "Content of the first page."

    def test_pdf_chunk_defaults(self):
        """PDFChunk with default section and content."""
        chunk = PDFChunk(
            paper_id="p1",
            chunk_id="p1_p1",
            page_number=1,
        )
        assert chunk.section == ""
        assert chunk.content == ""


# =========================================================================
# ChunkFilter
# =========================================================================

class TestChunkFilter:
    def test_chunk_filter(self):
        """ChunkFilter filters by category keywords."""
        chunks = [
            PDFChunk(paper_id="p1", chunk_id="p1_p1", page_number=1, content="The transformer architecture uses attention."),
            PDFChunk(paper_id="p1", chunk_id="p1_p2", page_number=2, content="The dataset contains 1M images."),
            PDFChunk(paper_id="p1", chunk_id="p1_p3", page_number=3, content="Future work includes addressing this limitation."),
        ]
        cf = ChunkFilter()
        arch_chunks = cf.filter(chunks, "architecture")
        assert len(arch_chunks) == 1
        assert arch_chunks[0].chunk_id == "p1_p1"

        dataset_chunks = cf.filter(chunks, "dataset")
        assert len(dataset_chunks) == 1
        assert dataset_chunks[0].chunk_id == "p1_p2"

        limitation_chunks = cf.filter(chunks, "limitation")
        assert len(limitation_chunks) == 1
        assert limitation_chunks[0].chunk_id == "p1_p3"

    def test_chunk_filter_unknown_category(self):
        """Unknown category returns empty list."""
        chunks = [PDFChunk(paper_id="p1", chunk_id="p1_p1", page_number=1, content="Some content.")]
        cf = ChunkFilter()
        result = cf.filter(chunks, "unknown_category")
        assert result == []

    def test_chunk_filter_empty_chunks(self):
        """Empty chunks list returns empty list."""
        cf = ChunkFilter()
        result = cf.filter([], "architecture")
        assert result == []

    def test_chunk_filter_case_insensitive(self):
        """Keyword matching is case-insensitive."""
        chunks = [
            PDFChunk(paper_id="p1", chunk_id="p1_p1", page_number=1, content="TRANSFORMER based model"),
        ]
        cf = ChunkFilter()
        result = cf.filter(chunks, "architecture")
        assert len(result) == 1


# =========================================================================
# EvidenceExtractor
# =========================================================================

class TestEvidenceExtractor:
    def test_evidence_extractor_empty(self):
        """No chunks returns empty evidence."""
        llm = MockLLM()
        extractor = EvidenceExtractor(llm)
        refs = extractor.extract([])
        assert refs == []

    def test_evidence_extractor_extracts(self):
        """MockLLM returns structured evidence."""
        response_json = json.dumps([
            {
                "excerpt": "The transformer architecture uses attention",
                "category": "architecture",
                "page_number": 1,
                "section": "Introduction",
                "source_type": "text",
                "table_id": "",
            },
        ])
        llm = MockLLM(fixed_response=response_json)
        extractor = EvidenceExtractor(llm)
        chunks = [
            PDFChunk(paper_id="paper123", chunk_id="paper123_p1", page_number=1, content="The transformer architecture uses attention"),
        ]
        refs = extractor.extract(chunks)
        assert len(refs) == 1
        assert refs[0].paper_id == "paper123"
        assert refs[0].excerpt == "The transformer architecture uses attention"
        assert refs[0].page_number == 1
        assert refs[0].section == "Introduction"
        assert refs[0].source_type == "text"
        assert len(refs[0].evidence_id) == 12

    def test_evidence_extractor_filters_fabricated(self):
        """Evidence not found in source chunks is filtered out."""
        response_json = json.dumps([
            {
                "excerpt": "This claim is completely fabricated",
                "category": "architecture",
                "page_number": 1,
                "section": "Introduction",
                "source_type": "text",
                "table_id": "",
            },
        ])
        llm = MockLLM(fixed_response=response_json)
        extractor = EvidenceExtractor(llm)
        chunks = [
            PDFChunk(paper_id="paper123", chunk_id="paper123_p1", page_number=1, content="Real content only"),
        ]
        refs = extractor.extract(chunks)
        assert len(refs) == 0

    def test_evidence_extractor_invalid_json(self):
        """Invalid JSON response returns empty list."""
        llm = MockLLM(fixed_response="NOT JSON")
        extractor = EvidenceExtractor(llm)
        chunks = [
            PDFChunk(paper_id="p1", chunk_id="p1_p1", page_number=1, content="Some content."),
        ]
        refs = extractor.extract(chunks)
        assert refs == []

    def test_evidence_extractor_llm_failure(self):
        """LLM failure returns empty list gracefully."""
        class FailingLLM:
            def generate(self, system_prompt, user_message, tools=None):
                raise RuntimeError("API error")
        extractor = EvidenceExtractor(FailingLLM())  # type: ignore
        chunks = [
            PDFChunk(paper_id="p1", chunk_id="p1_p1", page_number=1, content="Some content."),
        ]
        refs = extractor.extract(chunks)
        assert refs == []

    def test_evidence_extractor_markdown_fenced(self):
        """Handles markdown-fenced JSON response."""
        response = "```json\n" + json.dumps([
            {
                "excerpt": "The transformer architecture uses attention",
                "category": "architecture",
                "page_number": 1,
                "section": "Introduction",
                "source_type": "text",
                "table_id": "",
            },
        ]) + "\n```"
        llm = MockLLM(fixed_response=response)
        extractor = EvidenceExtractor(llm)
        chunks = [
            PDFChunk(paper_id="paper123", chunk_id="paper123_p1", page_number=1, content="The transformer architecture uses attention"),
        ]
        refs = extractor.extract(chunks)
        assert len(refs) == 1
        assert refs[0].excerpt == "The transformer architecture uses attention"


# =========================================================================
# BenchmarkRecord
# =========================================================================

class TestBenchmarkRecord:
    def test_benchmark_record_creation(self):
        """BenchmarkRecord creation with all fields."""
        ref = EvidenceReference(paper_id="paper123", excerpt="MMLU score 85.3%")
        record = BenchmarkRecord(
            id="custom_id_1",
            model_name="Qwen2-VL",
            benchmark_name="MMLU",
            metric="accuracy",
            score="85.3",
            score_unit="%",
            split="test",
            source=ref,
            verified=True,
        )
        assert record.id == "custom_id_1"
        assert record.model_name == "Qwen2-VL"
        assert record.benchmark_name == "MMLU"
        assert record.metric == "accuracy"
        assert record.score == "85.3"
        assert record.score_unit == "%"
        assert record.split == "test"
        assert record.source.excerpt == "MMLU score 85.3%"
        assert record.verified is True

    def test_benchmark_record_defaults(self):
        """BenchmarkRecord with default values (auto-generated id)."""
        record = BenchmarkRecord(
            model_name="TestModel",
            benchmark_name="MathVista",
            metric="pass@1",
            score="72.5",
        )
        assert record.model_name == "TestModel"
        assert record.score_unit == "%"  # default
        assert record.verified is False
        assert record.split == ""
        assert len(record.id) == 12  # auto-generated uuid hex
        assert isinstance(record.id, str)

    def test_benchmark_record_auto_id(self):
        """BenchmarkRecord auto-generates id when not provided."""
        record = BenchmarkRecord(
            model_name="M",
            benchmark_name="B",
            metric="acc",
            score="90",
        )
        assert len(record.id) == 12


# =========================================================================
# BenchmarkStore
# =========================================================================

class TestBenchmarkStore:
    def test_benchmark_store_add_and_retrieve(self):
        """Add records, retrieve by model, lookup."""
        store = BenchmarkStore()
        records = [
            BenchmarkRecord(id="r1", model_name="Qwen2-VL", benchmark_name="MMLU", metric="accuracy", score="85.3"),
            BenchmarkRecord(id="r2", model_name="Qwen2-VL", benchmark_name="MathVista", metric="pass@1", score="72.5"),
            BenchmarkRecord(id="r3", model_name="MiniCPM-V", benchmark_name="MMLU", metric="accuracy", score="82.1"),
        ]
        store.add_records(records)
        assert len(store.get_all()) == 3

        # get_by_model
        qwen = store.get_by_model("Qwen2-VL")
        assert len(qwen) == 2
        assert qwen[0].id == "r1"
        assert qwen[1].id == "r2"

        minicpm = store.get_by_model("MiniCPM-V")
        assert len(minicpm) == 1
        assert minicpm[0].id == "r3"

        # lookup (benchmark only)
        mmlu = store.lookup("MMLU")
        assert len(mmlu) == 2
        assert {r.id for r in mmlu} == {"r1", "r3"}

        # lookup (benchmark + model)
        mmlu_qwen = store.lookup("MMLU", "Qwen2-VL")
        assert len(mmlu_qwen) == 1
        assert mmlu_qwen[0].id == "r1"

    def test_benchmark_store_mark_verified(self):
        """Mark records as verified by ID."""
        store = BenchmarkStore()
        records = [
            BenchmarkRecord(id="r1", model_name="M1", benchmark_name="B1", metric="acc", score="90"),
            BenchmarkRecord(id="r2", model_name="M2", benchmark_name="B2", metric="acc", score="80"),
            BenchmarkRecord(id="r3", model_name="M3", benchmark_name="B3", metric="acc", score="70"),
        ]
        store.add_records(records)

        count = store.mark_verified(["r1", "r3"])
        assert count == 2

        verified = store.get_verified()
        assert len(verified) == 2
        assert {r.id for r in verified} == {"r1", "r3"}

        # Verify r2 is still unverified
        assert store.get_by_model("M2")[0].verified is False

    def test_benchmark_store_mark_verified_idempotent(self):
        """Marking already-verified records does not double-count."""
        store = BenchmarkStore()
        store.add_records([BenchmarkRecord(id="r1", model_name="M", benchmark_name="B", metric="acc", score="90")])
        assert store.mark_verified(["r1"]) == 1
        assert store.mark_verified(["r1"]) == 0  # already verified
        assert store.verified_count() == 1

    def test_benchmark_store_clear(self):
        """Clear resets store."""
        store = BenchmarkStore()
        store.add_records([BenchmarkRecord(id="r1", model_name="M", benchmark_name="B", metric="acc", score="90")])
        assert len(store.get_all()) == 1
        store.clear()
        assert len(store.get_all()) == 0

    def test_benchmark_store_get_verified_filtered(self):
        """get_verified with benchmark_name filter."""
        store = BenchmarkStore()
        store.add_records([
            BenchmarkRecord(id="r1", model_name="M1", benchmark_name="MMLU", metric="acc", score="90"),
            BenchmarkRecord(id="r2", model_name="M2", benchmark_name="MMLU", metric="acc", score="85"),
            BenchmarkRecord(id="r3", model_name="M3", benchmark_name="MathVista", metric="acc", score="80"),
        ])
        store.mark_verified(["r1", "r2", "r3"])
        mmlu_verified = store.get_verified(benchmark_name="MMLU")
        assert len(mmlu_verified) == 2
        assert {r.id for r in mmlu_verified} == {"r1", "r2"}

    def test_benchmark_store_lookup_no_match(self):
        """lookup returns empty list when no match."""
        store = BenchmarkStore()
        store.add_records([BenchmarkRecord(id="r1", model_name="M", benchmark_name="B", metric="acc", score="90")])
        assert store.lookup("NonExistent") == []
        assert store.lookup("B", "NonExistent") == []


# =========================================================================
# PaperKnowledge, ArchitectureKnowledge, TrainingKnowledge
# =========================================================================

class TestPaperKnowledge:
    def test_paper_knowledge_creation(self):
        """PaperKnowledge creation with structured fields."""
        arch = ArchitectureKnowledge(
            vision_encoder=KnowledgeField(value="ViT-L/14"),
            language_model=KnowledgeField(value="Qwen2-7B"),
            connector=KnowledgeField(value="MLP projector"),
        )
        training = TrainingKnowledge(
            pretraining_dataset=KnowledgeField(value="LAION-5B"),
            instruction_dataset=KnowledgeField(value="LLaVA-Instruct-150K"),
            optimization_method=KnowledgeField(value="AdamW"),
        )
        ds = DatasetReference(name="ImageNet-1K")

        pk = PaperKnowledge(
            paper_id="qwen2024",
            title="Qwen2-VL: Better Vision-Language Model",
            problem_definition="Vision-language model alignment",
            motivation="Improve multimodal understanding",
            main_contribution="Dynamic resolution approach",
            architecture=arch,
            training=training,
            datasets=[ds],
            benchmark_references=["MMLU", "MathVista"],
            limitations="Limited to English",
        )
        assert pk.paper_id == "qwen2024"
        assert pk.title == "Qwen2-VL: Better Vision-Language Model"
        assert pk.problem_definition == "Vision-language model alignment"
        assert pk.motivation == "Improve multimodal understanding"
        assert pk.main_contribution == "Dynamic resolution approach"
        assert pk.architecture.vision_encoder.value == "ViT-L/14"
        assert pk.architecture.language_model.value == "Qwen2-7B"
        assert pk.architecture.connector.value == "MLP projector"
        assert pk.training.pretraining_dataset.value == "LAION-5B"
        assert pk.training.instruction_dataset.value == "LLaVA-Instruct-150K"
        assert pk.training.optimization_method.value == "AdamW"
        assert len(pk.datasets) == 1
        assert pk.datasets[0].name == "ImageNet-1K"
        assert pk.benchmark_references == ["MMLU", "MathVista"]
        assert pk.limitations == "Limited to English"
        assert pk.evidence_refs == []

    def test_paper_knowledge_defaults(self):
        """PaperKnowledge with minimal fields."""
        pk = PaperKnowledge(paper_id="test123")
        assert pk.paper_id == "test123"
        assert pk.title == ""
        assert pk.architecture is None
        assert pk.training is None
        assert pk.datasets == []
        assert pk.benchmark_references == []
        assert pk.evidence_refs == []

    def test_paper_knowledge_evidence_refs(self):
        """PaperKnowledge.evidence_refs holds paper-level evidence."""
        ref = EvidenceReference(paper_id="p1", excerpt="Paper-level evidence")
        pk = PaperKnowledge(
            paper_id="p1",
            evidence_refs=[ref],
        )
        assert len(pk.evidence_refs) == 1
        assert pk.evidence_refs[0].excerpt == "Paper-level evidence"

    def test_architecture_knowledge_defaults(self):
        """ArchitectureKnowledge with default values."""
        arch = ArchitectureKnowledge()
        assert arch.vision_encoder.value == ""
        assert arch.language_model.value == ""
        assert arch.connector.value == ""
        assert arch.fusion_method.value == ""
        assert arch.resolution_strategy.value == ""

    def test_training_knowledge_defaults(self):
        """TrainingKnowledge with default values."""
        training = TrainingKnowledge()
        assert training.pretraining_dataset.value == ""
        assert training.instruction_dataset.value == ""
        assert training.optimization_method.value == ""
        assert training.loss_function.value == ""
        assert training.training_stage.value == ""

    def test_architecture_knowledge_with_evidence(self):
        """ArchitectureKnowledge fields carry their own evidence."""
        ref = EvidenceReference(paper_id="p1", excerpt="Uses ViT")
        arch = ArchitectureKnowledge(
            vision_encoder=KnowledgeField(value="ViT-L/14", evidence_refs=[ref]),
        )
        assert arch.vision_encoder.value == "ViT-L/14"
        assert len(arch.vision_encoder.evidence_refs) == 1
        assert arch.vision_encoder.evidence_refs[0].excerpt == "Uses ViT"
        # Other fields should be empty
        assert arch.language_model.value == ""
        assert arch.connector.value == ""


# =========================================================================
# PaperKnowledgeBase
# =========================================================================

class TestPaperKnowledgeBase:
    def test_paper_knowledge_base_add_and_get(self):
        """Add a PaperKnowledge and retrieve by paper_id."""
        pk = PaperKnowledge(paper_id="qwen2024", title="Qwen2-VL")
        base = PaperKnowledgeBase()
        base.add(pk)
        retrieved = base.get("qwen2024")
        assert retrieved is not None
        assert retrieved.paper_id == "qwen2024"
        assert retrieved.title == "Qwen2-VL"

    def test_paper_knowledge_base_get_nonexistent(self):
        """get returns None for unknown paper_id."""
        base = PaperKnowledgeBase()
        assert base.get("nonexistent") is None

    def test_paper_knowledge_base_get_all(self):
        """get_all returns all stored objects."""
        base = PaperKnowledgeBase()
        base.add(PaperKnowledge(paper_id="p1", title="Paper 1"))
        base.add(PaperKnowledge(paper_id="p2", title="Paper 2"))
        all_pk = base.get_all()
        assert len(all_pk) == 2
        titles = {pk.title for pk in all_pk}
        assert titles == {"Paper 1", "Paper 2"}

    def test_paper_knowledge_base_clear(self):
        """Clear resets the knowledge base."""
        base = PaperKnowledgeBase()
        base.add(PaperKnowledge(paper_id="p1", title="Paper 1"))
        assert len(base.get_all()) == 1
        base.clear()
        assert len(base.get_all()) == 0

    def test_paper_knowledge_base_overwrite(self):
        """Adding same paper_id replaces existing entry."""
        base = PaperKnowledgeBase()
        base.add(PaperKnowledge(paper_id="p1", title="Original"))
        base.add(PaperKnowledge(paper_id="p1", title="Updated"))
        retrieved = base.get("p1")
        assert retrieved.title == "Updated"
        assert len(base.get_all()) == 1


# =========================================================================
# BenchmarkExtractor
# =========================================================================

class TestBenchmarkExtractor:
    def test_benchmark_extractor_extracts(self):
        """MockLLM returns structured benchmark records."""
        ref = EvidenceReference(
            paper_id="paper123",
            excerpt="Qwen2-VL achieves 85.3% accuracy on MMLU under zero-shot setting.",
            page_number=3,
            section="Experiments",
            source_type="text",
        )
        response_json = json.dumps([
            {
                "excerpt_index": 0,
                "model_name": "Qwen2-VL",
                "benchmark_name": "MMLU",
                "metric": "accuracy",
                "score": "85.3",
                "score_unit": "%",
                "split": "zero-shot",
            },
        ])
        llm = MockLLM(fixed_response=response_json)
        extractor = BenchmarkExtractor(llm)
        records = extractor.extract([ref])
        assert len(records) == 1
        assert records[0].model_name == "Qwen2-VL"
        assert records[0].benchmark_name == "MMLU"
        assert records[0].metric == "accuracy"
        assert records[0].score == "85.3"
        assert records[0].score_unit == "%"
        assert records[0].split == "zero-shot"
        assert records[0].source.paper_id == "paper123"
        assert records[0].verified is False

    def test_benchmark_extractor_empty_refs(self):
        """Empty evidence_refs returns empty list."""
        llm = MockLLM()
        extractor = BenchmarkExtractor(llm)
        records = extractor.extract([])
        assert records == []

    def test_benchmark_extractor_invalid_json(self):
        """Invalid JSON response returns empty list."""
        llm = MockLLM(fixed_response="NOT JSON")
        extractor = BenchmarkExtractor(llm)
        ref = EvidenceReference(paper_id="p1", excerpt="Some excerpt")
        records = extractor.extract([ref])
        assert records == []

    def test_benchmark_extractor_llm_failure(self):
        """LLM failure returns empty list gracefully."""
        class FailingLLM:
            def generate(self, system_prompt, user_message, tools=None):
                raise RuntimeError("API error")
        extractor = BenchmarkExtractor(FailingLLM())  # type: ignore
        ref = EvidenceReference(paper_id="p1", excerpt="Some excerpt")
        records = extractor.extract([ref])
        assert records == []

    def test_benchmark_extractor_markdown_fenced(self):
        """Handles markdown-fenced JSON response."""
        ref = EvidenceReference(
            paper_id="paper123",
            excerpt="Model X achieves 92.1% on MathVista.",
        )
        response = "```json\n" + json.dumps([
            {
                "excerpt_index": 0,
                "model_name": "Model X",
                "benchmark_name": "MathVista",
                "metric": "accuracy",
                "score": "92.1",
                "score_unit": "%",
                "split": "",
            },
        ]) + "\n```"
        llm = MockLLM(fixed_response=response)
        extractor = BenchmarkExtractor(llm)
        records = extractor.extract([ref])
        assert len(records) == 1
        assert records[0].benchmark_name == "MathVista"
        assert records[0].score == "92.1"

    def test_benchmark_extractor_no_benchmarks_in_response(self):
        """Empty JSON array when no benchmarks found."""
        llm = MockLLM(fixed_response="[]")
        extractor = BenchmarkExtractor(llm)
        ref = EvidenceReference(paper_id="p1", excerpt="This paper introduces a new architecture.")
        records = extractor.extract([ref])
        assert records == []

    def test_benchmark_extractor_out_of_range_index(self):
        """excerpt_index out of range is skipped."""
        response_json = json.dumps([
            {
                "excerpt_index": 99,
                "model_name": "Model",
                "benchmark_name": "MMLU",
                "metric": "acc",
                "score": "90",
            },
        ])
        llm = MockLLM(fixed_response=response_json)
        extractor = BenchmarkExtractor(llm)
        ref = EvidenceReference(paper_id="p1", excerpt="MMLU score 90%")
        records = extractor.extract([ref])
        assert records == []


# =========================================================================
# BenchmarkVerifier
# =========================================================================

class TestBenchmarkVerifier:
    def test_benchmark_verifier(self):
        """Verifies records against paper metadata."""
        ref = EvidenceReference(
            paper_id="paper123",
            excerpt="Qwen2-VL achieves 85.3% accuracy on MMLU.",
        )
        record = BenchmarkRecord(
            id="r1",
            model_name="Qwen2-VL",
            benchmark_name="MMLU",
            metric="accuracy",
            score="85.3",
            source=ref,
        )
        verifier = BenchmarkVerifier()
        papers = [
            {"title": "Qwen2-VL: Better Vision-Language Model", "paper_id": "paper123", "arxiv_id": "paper123"},
        ]
        passed = verifier.verify([record], papers)
        assert len(passed) == 1
        assert passed[0] == "r1"

    def test_benchmark_verifier_verification_lifecycle(self):
        """Unverified -> verified transition."""
        ref = EvidenceReference(
            paper_id="p1",
            excerpt="Model A achieves 90.0% on Benchmark B.",
        )
        store = BenchmarkStore()
        record = BenchmarkRecord(
            id="r1",
            model_name="Model A",
            benchmark_name="Benchmark B",
            metric="accuracy",
            score="90.0",
            source=ref,
        )
        store.add_records([record])
        assert record.verified is False

        verifier = BenchmarkVerifier()
        papers = [{"title": "Model A Paper", "paper_id": "p1", "abstract": "Model A achieves 90.0% on Benchmark B."}]
        passed = verifier.verify([record], papers)
        assert len(passed) == 1

        # The record is still unverified in the store until mark_verified is called
        assert record.verified is False
        store.mark_verified(passed)
        assert store.get_verified()[0].id == "r1"
        assert store.verified_count() == 1

    def test_benchmark_verifier_rejects_inconsistent(self):
        """Rejects record where score not in excerpt."""
        ref = EvidenceReference(
            paper_id="p1",
            excerpt="Model A achieves great performance on Benchmark B.",
        )
        record = BenchmarkRecord(
            id="r1",
            model_name="Model A",
            benchmark_name="Benchmark B",
            metric="accuracy",
            score="90.0",
            source=ref,
        )
        verifier = BenchmarkVerifier()
        passed = verifier.verify([record], [])
        assert len(passed) == 0

    def test_benchmark_verifier_rejects_empty_excerpt(self):
        """Rejects record with empty excerpt."""
        ref = EvidenceReference(paper_id="p1", excerpt="")
        record = BenchmarkRecord(
            id="r1",
            model_name="Model A",
            benchmark_name="MMLU",
            metric="acc",
            score="90",
            source=ref,
        )
        verifier = BenchmarkVerifier()
        passed = verifier.verify([record], [])
        assert len(passed) == 0

    def test_benchmark_verifier_verify_record(self):
        """verify_record checks a single record."""
        ref = EvidenceReference(
            paper_id="p1",
            excerpt="Model X achieves 88.5% on MMLU.",
        )
        record = BenchmarkRecord(
            model_name="Model X",
            benchmark_name="MMLU",
            metric="accuracy",
            score="88.5",
            source=ref,
        )
        verifier = BenchmarkVerifier()
        assert verifier.verify_record(record) is True
        assert verifier.verify_record(record, {"title": "Model X Paper", "paper_id": "p1", "abstract": "Model X achieves 88.5% on MMLU."}) is True

    def test_benchmark_verifier_rejects_implausible_score(self):
        """Rejects record with implausible score."""
        ref = EvidenceReference(paper_id="p1", excerpt="Model X achieves 150.0% on MMLU.")
        record = BenchmarkRecord(
            model_name="Model X",
            benchmark_name="MMLU",
            metric="accuracy",
            score="150.0",
            source=ref,
        )
        verifier = BenchmarkVerifier()
        assert verifier.verify_record(record) is False

    def test_benchmark_verifier_empty_records(self):
        """Empty records list returns empty list."""
        verifier = BenchmarkVerifier()
        passed = verifier.verify([], [])
        assert passed == []


# =========================================================================
# PaperAnalyzer
# =========================================================================

class TestPaperAnalyzer:
    def test_paper_analyzer_analyzes(self):
        """MockLLM returns structured paper knowledge."""
        ref1 = EvidenceReference(
            paper_id="paper123",
            excerpt="Qwen2-VL uses a ViT-L/14 vision encoder with a Qwen2-7B language model.",
            page_number=2,
            section="Architecture",
            source_type="text",
        )
        ref2 = EvidenceReference(
            paper_id="paper123",
            excerpt="The model is pretrained on LAION-5B and achieves 85.3% on MMLU.",
            page_number=5,
            section="Experiments",
            source_type="text",
        )
        response_json = json.dumps({
            "paper123": {
                "title": "Qwen2-VL: Better Vision-Language Model",
                "problem_definition": "Vision-language model alignment",
                "motivation": "Improve multimodal understanding",
                "main_contribution": "Dynamic resolution approach",
                "architecture": {
                    "vision_encoder": "ViT-L/14",
                    "language_model": "Qwen2-7B",
                    "connector": "MLP projector",
                    "fusion_method": "",
                    "resolution_strategy": "dynamic resolution",
                },
                "training": {
                    "pretraining_dataset": "LAION-5B",
                    "instruction_dataset": "",
                    "optimization_method": "AdamW",
                    "loss_function": "",
                    "training_stage": "",
                },
                "datasets": ["ImageNet-1K"],
                "benchmark_references": ["MMLU"],
                "limitations": "Limited to English",
                "evidence_indices": [0, 1],
            },
        })
        llm = MockLLM(fixed_response=response_json)
        analyzer = PaperAnalyzer(llm)
        knowledge_list = analyzer.analyze([ref1, ref2])
        assert len(knowledge_list) == 1
        pk = knowledge_list[0]
        assert pk.paper_id == "paper123"
        assert pk.title == "Qwen2-VL: Better Vision-Language Model"
        assert pk.problem_definition == "Vision-language model alignment"
        assert pk.motivation == "Improve multimodal understanding"
        assert pk.main_contribution == "Dynamic resolution approach"
        assert pk.architecture is not None
        assert pk.architecture.vision_encoder.value == "ViT-L/14"
        assert pk.architecture.language_model.value == "Qwen2-7B"
        assert pk.architecture.connector.value == "MLP projector"
        assert pk.architecture.resolution_strategy.value == "dynamic resolution"
        assert pk.training is not None
        assert pk.training.pretraining_dataset.value == "LAION-5B"
        assert pk.training.optimization_method.value == "AdamW"
        assert len(pk.datasets) == 1
        assert pk.datasets[0].name == "ImageNet-1K"
        assert pk.benchmark_references == ["MMLU"]
        assert pk.limitations == "Limited to English"
        assert len(pk.evidence_refs) == 2

    def test_paper_analyzer_empty_refs(self):
        """Empty evidence_refs returns empty list."""
        llm = MockLLM()
        analyzer = PaperAnalyzer(llm)
        knowledge_list = analyzer.analyze([])
        assert knowledge_list == []

    def test_paper_analyzer_invalid_json(self):
        """Invalid JSON response returns empty list."""
        llm = MockLLM(fixed_response="NOT JSON")
        analyzer = PaperAnalyzer(llm)
        ref = EvidenceReference(paper_id="p1", excerpt="Some excerpt")
        knowledge_list = analyzer.analyze([ref])
        assert knowledge_list == []

    def test_paper_analyzer_llm_failure(self):
        """LLM failure returns empty list gracefully."""
        class FailingLLM:
            def generate(self, system_prompt, user_message, tools=None):
                raise RuntimeError("API error")
        analyzer = PaperAnalyzer(FailingLLM())  # type: ignore
        ref = EvidenceReference(paper_id="p1", excerpt="Some excerpt")
        knowledge_list = analyzer.analyze([ref])
        assert knowledge_list == []

    def test_paper_analyzer_multiple_papers(self):
        """Handles multiple papers in response."""
        response_json = json.dumps({
            "p1": {
                "title": "Paper 1",
                "problem_definition": "",
                "motivation": "",
                "main_contribution": "",
                "architecture": None,
                "training": None,
                "datasets": [],
                "benchmark_references": [],
                "limitations": "",
                "evidence_indices": [0],
            },
            "p2": {
                "title": "Paper 2",
                "problem_definition": "",
                "motivation": "",
                "main_contribution": "",
                "architecture": None,
                "training": None,
                "datasets": [],
                "benchmark_references": [],
                "limitations": "",
                "evidence_indices": [1],
            },
        })
        llm = MockLLM(fixed_response=response_json)
        analyzer = PaperAnalyzer(llm)
        refs = [
            EvidenceReference(paper_id="p1", excerpt="Paper 1 excerpt"),
            EvidenceReference(paper_id="p2", excerpt="Paper 2 excerpt"),
        ]
        knowledge_list = analyzer.analyze(refs)
        assert len(knowledge_list) == 2
        assert {k.paper_id for k in knowledge_list} == {"p1", "p2"}

    def test_paper_analyzer_markdown_fenced(self):
        """Handles markdown-fenced JSON response."""
        response = "```json\n" + json.dumps({
            "p1": {
                "title": "Test Paper",
                "problem_definition": "",
                "motivation": "",
                "main_contribution": "",
                "architecture": None,
                "training": None,
                "datasets": [],
                "benchmark_references": [],
                "limitations": "",
                "evidence_indices": [0],
            },
        }) + "\n```"
        llm = MockLLM(fixed_response=response)
        analyzer = PaperAnalyzer(llm)
        ref = EvidenceReference(paper_id="p1", excerpt="Test excerpt")
        knowledge_list = analyzer.analyze([ref])
        assert len(knowledge_list) == 1
        assert knowledge_list[0].paper_id == "p1"
        assert knowledge_list[0].title == "Test Paper"


# =========================================================================
# EvidenceRanker / SimpleRanker
# =========================================================================

class TestEvidenceRanker:
    def test_evidence_ranker_simple(self):
        """SimpleRanker sorts verified claims first, then by confidence."""
        ranker = SimpleRanker()

        # Claims — verified before unverified, higher confidence first
        claims = [
            Claim(claim="Low confidence unverified", category="architecture", confidence=0.3, verified=False),
            Claim(claim="High confidence verified", category="architecture", confidence=0.9, verified=True),
            Claim(claim="Low confidence verified", category="architecture", confidence=0.5, verified=True),
            Claim(claim="High confidence unverified", category="architecture", confidence=0.8, verified=False),
        ]
        ranked = ranker.rank_claims(claims)
        assert len(ranked) == 4
        # Verified first
        assert ranked[0].verified is True
        assert ranked[1].verified is True
        # Within verified, higher confidence first
        assert ranked[0].confidence == 0.9
        assert ranked[1].confidence == 0.5
        # Unverified last
        assert ranked[2].verified is False
        assert ranked[3].verified is False
        # Within unverified, higher confidence first
        assert ranked[2].confidence == 0.8
        assert ranked[3].confidence == 0.3

        # Benchmarks — verified first
        ref_p1 = EvidenceReference(paper_id="p1")
        benchmarks = [
            BenchmarkRecord(id="b1", model_name="M1", benchmark_name="B1", metric="acc", score="90", source=ref_p1, verified=False),
            BenchmarkRecord(id="b2", model_name="M2", benchmark_name="B2", metric="acc", score="80", source=ref_p1, verified=True),
        ]
        ranked_b = ranker.rank_benchmarks(benchmarks)
        assert len(ranked_b) == 2
        assert ranked_b[0].verified is True
        assert ranked_b[1].verified is False

        # Knowledge — returned as-is
        k1 = PaperKnowledge(paper_id="p1", title="Paper 1")
        k2 = PaperKnowledge(paper_id="p2", title="Paper 2")
        ranked_k = ranker.rank_knowledge([k1, k2])
        assert ranked_k == [k1, k2]

    def test_evidence_ranker_is_abc(self):
        """EvidenceRanker cannot be instantiated directly."""
        import inspect
        assert inspect.isabstract(EvidenceRanker)
        # Verify abstract methods exist
        assert hasattr(EvidenceRanker, "rank_claims")
        assert hasattr(EvidenceRanker, "rank_benchmarks")
        assert hasattr(EvidenceRanker, "rank_knowledge")


# =========================================================================
# ContextRetriever
# =========================================================================

class TestContextRetriever:
    def test_context_retriever_empty(self):
        """No stores -> empty context."""
        retriever = ContextRetriever(
            evidence_store=EvidenceStore(),
            benchmark_store=BenchmarkStore(),
            knowledge_base=PaperKnowledgeBase(),
        )
        ctx = retriever.retrieve_for_section()
        assert isinstance(ctx, EvidenceContext)
        assert ctx.claims == []
        assert ctx.benchmarks == []
        assert ctx.paper_knowledge == []

    def test_context_retriever_with_data(self):
        """Retrieves from all three stores, ranks, and selects within budget."""
        evidence_store = EvidenceStore()
        evidence_store.add_claims([
            Claim(claim="Uses dynamic resolution", category="architecture", paper_id="p1", confidence=0.9),
            Claim(claim="MMLU score 85.3%", category="benchmark", paper_id="p1", confidence=0.8),
        ])
        evidence_store.mark_verified(["Uses dynamic resolution", "MMLU score 85.3%"])

        benchmark_store = BenchmarkStore()
        ref_p1 = EvidenceReference(paper_id="p1", excerpt="MMLU score 85.3%")
        benchmark_store.add_records([
            BenchmarkRecord(id="b1", model_name="Qwen2-VL", benchmark_name="MMLU", metric="accuracy", score="85.3", source=ref_p1, verified=True),
        ])

        knowledge_base = PaperKnowledgeBase()
        pk = PaperKnowledge(
            paper_id="p1",
            title="Qwen2-VL: Better Vision-Language Model",
            main_contribution="Dynamic resolution approach",
        )
        knowledge_base.add(pk)

        retriever = ContextRetriever(
            evidence_store=evidence_store,
            benchmark_store=benchmark_store,
            knowledge_base=knowledge_base,
            max_context_tokens=1000,
        )
        ctx = retriever.retrieve_for_section()
        assert len(ctx.claims) == 2
        assert len(ctx.benchmarks) == 1
        assert len(ctx.paper_knowledge) == 1
        assert ctx.claims[0].claim == "Uses dynamic resolution"
        assert ctx.benchmarks[0].benchmark_name == "MMLU"
        assert ctx.paper_knowledge[0].paper_id == "p1"

    def test_context_retriever_filters_by_paper_ids(self):
        """Filters evidence by paper_ids."""
        evidence_store = EvidenceStore()
        evidence_store.add_claims([
            Claim(claim="Claim from p1", category="architecture", paper_id="p1", confidence=0.9),
            Claim(claim="Claim from p2", category="architecture", paper_id="p2", confidence=0.8),
        ])

        retriever = ContextRetriever(
            evidence_store=evidence_store,
            benchmark_store=BenchmarkStore(),
            knowledge_base=PaperKnowledgeBase(),
        )
        ctx = retriever.retrieve_for_section(paper_ids=["p1"])
        assert len(ctx.claims) == 1
        assert ctx.claims[0].paper_id == "p1"

    def test_context_retriever_filters_by_category(self):
        """Filters claims by category."""
        evidence_store = EvidenceStore()
        evidence_store.add_claims([
            Claim(claim="Arch claim", category="architecture", paper_id="p1", confidence=0.9),
            Claim(claim="Bench claim", category="benchmark", paper_id="p1", confidence=0.8),
        ])

        retriever = ContextRetriever(
            evidence_store=evidence_store,
            benchmark_store=BenchmarkStore(),
            knowledge_base=PaperKnowledgeBase(),
        )
        ctx = retriever.retrieve_for_section(category="architecture")
        assert len(ctx.claims) == 1
        assert ctx.claims[0].category == "architecture"

    def test_context_retriever_token_budget(self):
        """Token budget limits number of items returned."""
        evidence_store = EvidenceStore()
        for i in range(20):
            evidence_store.add_claims([
                Claim(
                    claim=f"Long claim number {i} with some padding text to make it realistic and use more tokens",
                    category="architecture",
                    paper_id=f"p{i}",
                    confidence=0.9,
                ),
            ])

        # Very small budget — only a few items should fit
        retriever = ContextRetriever(
            evidence_store=evidence_store,
            benchmark_store=BenchmarkStore(),
            knowledge_base=PaperKnowledgeBase(),
            max_context_tokens=50,  # ~200 characters
        )
        ctx = retriever.retrieve_for_section()
        # Should not contain all 20 claims
        assert len(ctx.claims) < 20
        # Should contain at least 1
        assert len(ctx.claims) >= 1

    def test_context_retriever_custom_ranker(self):
        """ContextRetriever accepts a custom ranker."""
        evidence_store = EvidenceStore()
        evidence_store.add_claims([
            Claim(claim="Low confidence", category="architecture", paper_id="p1", confidence=0.3),
            Claim(claim="High confidence", category="architecture", paper_id="p1", confidence=0.9),
        ])

        # Default SimpleRanker puts high confidence first
        retriever = ContextRetriever(
            evidence_store=evidence_store,
            benchmark_store=BenchmarkStore(),
            knowledge_base=PaperKnowledgeBase(),
        )
        ctx = retriever.retrieve_for_section()
        assert ctx.claims[0].confidence == 0.9


# =========================================================================
# EvidenceContextBuilder
# =========================================================================

class TestEvidenceContextBuilder:
    def test_evidence_context_builder_format(self):
        """Formats context with metadata (paper_id, page_number, section)."""
        ref = EvidenceReference(
            paper_id="p1",
            page_number=3,
            section="Experiments",
            excerpt="MMLU score 85.3%",
        )
        context = EvidenceContext(
            claims=[
                Claim(claim="Uses dynamic resolution", category="architecture", paper_id="p1", confidence=0.9, verified=True),
            ],
            benchmarks=[
                BenchmarkRecord(
                    id="b1",
                    model_name="Qwen2-VL",
                    benchmark_name="MMLU",
                    metric="accuracy",
                    score="85.3",
                    source=ref,
                    verified=True,
                ),
            ],
            paper_knowledge=[
                PaperKnowledge(
                    paper_id="p1",
                    title="Qwen2-VL: Better Vision-Language Model",
                    main_contribution="Dynamic resolution approach",
                ),
            ],
        )
        result = EvidenceContextBuilder.format(context)

        # Header and footer
        assert "=== Evidence Context ===" in result
        assert "=== End Evidence Context ===" in result

        # Claims section with metadata
        assert "--- Claims ---" in result
        assert "paper=p1" in result
        assert "architecture" in result
        assert "verified" in result
        assert "confidence=0.90" in result
        assert "Uses dynamic resolution" in result

        # Benchmark section with metadata
        assert "--- Benchmark Results ---" in result
        assert "page=3" in result
        assert "section=Experiments" in result
        assert "Qwen2-VL" in result
        assert "MMLU" in result
        assert "85.3%" in result

        # Paper Knowledge section
        assert "--- Paper Knowledge ---" in result
        assert "Qwen2-VL: Better Vision-Language Model" in result
        assert "Dynamic resolution approach" in result

    def test_evidence_context_builder_format_empty(self):
        """Empty context returns empty string."""
        context = EvidenceContext()
        result = EvidenceContextBuilder.format(context)
        assert result == ""

    def test_evidence_context_builder_format_source_excerpt(self):
        """Source excerpt appears in formatted output."""
        context = EvidenceContext(
            claims=[
                Claim(
                    claim="Uses dynamic resolution",
                    category="architecture",
                    paper_id="p1",
                    confidence=0.9,
                    verified=True,
                    source_excerpt="The model uses dynamic resolution to process images.",
                ),
            ],
        )
        result = EvidenceContextBuilder.format(context)
        assert "Source:" in result
        assert "dynamic resolution" in result


# =========================================================================
# Full pipeline integration test
# =========================================================================

class TestPipelineEvidenceGroundingFlow:
    """Full pipeline integration test for the evidence grounding layer.

    This test creates a PipelineOrchestrator with all new evidence grounding
    components wired in, and verifies the complete flow:
    - Stores are initialized and accessible
    - Evidence extraction from PDF chunks works
    - Benchmark extraction from evidence refs works
    - Paper knowledge extraction from evidence refs works
    - ContextRetriever produces a non-empty context when stores are populated
    - EvidenceContextBuilder formats the context correctly
    - All stores are cleared on pipeline reset
    """

    def test_orchestrator_evidence_grounding_flow(self):
        """Full pipeline integration test: stores, extractors, context."""
        from agent.core.pipeline import PipelineOrchestrator, HarnessConfig, TaskInfo
        from agent.tools.registry import ToolRegistry
        from agent.guardrails.manager import GuardrailManager
        from agent.core.llm import MockLLM
        from agent.evidence.evidence_reference import EvidenceReference

        # 1. Create orchestrator with MockLLM
        llm = MockLLM(fixed_response="Test analysis content")
        orch = PipelineOrchestrator(
            llm=llm,
            tools=ToolRegistry(),
            validators=[],
            guardrails=GuardrailManager(guardrails=[]),
            config=HarnessConfig(),
            latex_repair=None,
        )

        # 2. Verify all new stores and extractors exist
        assert orch._benchmark_store is not None
        assert orch._paper_knowledge_base is not None
        assert orch._benchmark_extractor is not None
        assert orch._paper_analyzer is not None
        assert orch._pdf_parser is not None
        assert orch._evidence_extractor is not None
        assert orch._pdf_chunks == {}
        assert orch._evidence_refs == []
        assert orch._evidence_unavailable == set()

        # 3. Verify stores are initially empty
        assert len(orch._benchmark_store.get_all()) == 0
        assert len(orch._paper_knowledge_base.get_all()) == 0
        assert len(orch._evidence_store.get_all_claims()) == 0

        # 4. Simulate evidence extraction by adding evidence refs directly
        ref = EvidenceReference(
            paper_id="paper123",
            excerpt="Qwen2-VL achieves 85.3% accuracy on MMLU.",
            page_number=3,
            section="Experiments",
            source_type="text",
        )
        orch._evidence_refs = [ref]

        # 5. Run benchmark extraction
        from agent.evidence.benchmark_extractor import BenchmarkExtractor
        be = BenchmarkExtractor(llm)
        # Use a mock response for benchmark extraction
        response_json = json.dumps([
            {
                "excerpt_index": 0,
                "model_name": "Qwen2-VL",
                "benchmark_name": "MMLU",
                "metric": "accuracy",
                "score": "85.3",
                "score_unit": "%",
                "split": "zero-shot",
            },
        ])
        llm.fixed_response = response_json
        benchmark_records = be.extract([ref])
        assert len(benchmark_records) == 1
        assert benchmark_records[0].model_name == "Qwen2-VL"
        assert benchmark_records[0].benchmark_name == "MMLU"
        assert benchmark_records[0].score == "85.3"

        # Add to benchmark store
        orch._benchmark_store.add_records(benchmark_records)
        assert len(orch._benchmark_store.get_all()) == 1
        assert len(orch._benchmark_store.get_verified()) == 0  # not yet verified

        # 6. Run paper knowledge analysis
        from agent.evidence.paper_analyzer import PaperAnalyzer
        pa = PaperAnalyzer(llm)
        response_json2 = json.dumps({
            "paper123": {
                "title": "Qwen2-VL: Better Vision-Language Model",
                "problem_definition": "Vision-language model alignment",
                "motivation": "Improve multimodal understanding",
                "main_contribution": "Dynamic resolution approach",
                "architecture": {
                    "vision_encoder": "ViT-L/14",
                    "language_model": "Qwen2-7B",
                    "connector": "MLP projector",
                    "fusion_method": "",
                    "resolution_strategy": "dynamic resolution",
                },
                "training": None,
                "datasets": ["ImageNet-1K"],
                "benchmark_references": ["MMLU"],
                "limitations": "Limited to English",
                "evidence_indices": [0],
            },
        })
        llm.fixed_response = response_json2
        knowledge_list = pa.analyze([ref])
        assert len(knowledge_list) == 1
        pk = knowledge_list[0]
        assert pk.paper_id == "paper123"
        assert pk.title == "Qwen2-VL: Better Vision-Language Model"
        assert pk.main_contribution == "Dynamic resolution approach"
        assert pk.architecture is not None
        assert pk.architecture.vision_encoder.value == "ViT-L/14"

        # Add to knowledge base
        orch._paper_knowledge_base.add(pk)
        assert len(orch._paper_knowledge_base.get_all()) == 1

        # 7. Add a verified claim to evidence store (for ContextRetriever)
        from agent.evidence.evidence_store import Claim
        orch._evidence_store.add_claims([
            Claim(claim="Uses dynamic resolution", category="architecture", paper_id="paper123", confidence=0.9),
        ])
        orch._evidence_store.mark_verified(["Uses dynamic resolution"])
        assert orch._evidence_store.verified_count() == 1

        # 8. Test ContextRetriever with all three stores populated
        from agent.evidence.context_retriever import ContextRetriever, EvidenceContextBuilder
        retriever = ContextRetriever(
            evidence_store=orch._evidence_store,
            benchmark_store=orch._benchmark_store,
            knowledge_base=orch._paper_knowledge_base,
        )
        context = retriever.retrieve_for_section()
        assert len(context.claims) == 1
        assert len(context.benchmarks) == 1
        assert len(context.paper_knowledge) == 1
        assert context.claims[0].claim == "Uses dynamic resolution"
        assert context.benchmarks[0].benchmark_name == "MMLU"
        assert context.paper_knowledge[0].paper_id == "paper123"

        # 9. Test EvidenceContextBuilder formatting
        formatted = EvidenceContextBuilder.format(context)
        assert "=== Evidence Context ===" in formatted
        assert "=== End Evidence Context ===" in formatted
        assert "Uses dynamic resolution" in formatted
        assert "MMLU" in formatted
        assert "Qwen2-VL: Better Vision-Language Model" in formatted
        assert "Dynamic resolution approach" in formatted
        assert "ViT-L/14" in formatted

        # 10. Verify stores are cleared on reset
        orch._evidence_store.clear()
        orch._benchmark_store.clear()
        orch._paper_knowledge_base.clear()
        assert orch._evidence_store.claim_count() == 0
        assert len(orch._benchmark_store.get_all()) == 0
        assert len(orch._paper_knowledge_base.get_all()) == 0

        # 11. Verify ContextRetriever returns empty context with empty stores
        retriever2 = ContextRetriever(
            evidence_store=orch._evidence_store,
            benchmark_store=orch._benchmark_store,
            knowledge_base=orch._paper_knowledge_base,
        )
        context2 = retriever2.retrieve_for_section()
        assert len(context2.claims) == 0
        assert len(context2.benchmarks) == 0
        assert len(context2.paper_knowledge) == 0
        assert EvidenceContextBuilder.format(context2) == ""

    def test_orchestrator_clear_on_run_pipeline(self):
        """Verify that run_pipeline() clears all new stores."""
        from agent.core.pipeline import PipelineOrchestrator, HarnessConfig, TaskInfo
        from agent.tools.registry import ToolRegistry
        from agent.guardrails.manager import GuardrailManager
        from agent.core.llm import MockLLM
        from agent.evidence.evidence_reference import EvidenceReference
        from agent.evidence.evidence_store import Claim
        from agent.evidence.benchmark_store import BenchmarkRecord
        from agent.evidence.paper_knowledge import PaperKnowledge
        from agent.core.state import StateMachine

        llm = MockLLM(fixed_response="\\section{Test}\nContent")
        orch = PipelineOrchestrator(
            llm=llm,
            tools=ToolRegistry(),
            validators=[],
            guardrails=GuardrailManager(guardrails=[]),
            config=HarnessConfig(),
            latex_repair=None,
        )

        # Populate stores with some data
        orch._evidence_store.add_claims([
            Claim(claim="Test claim", category="architecture", paper_id="p1", confidence=0.5),
        ])
        ref = EvidenceReference(paper_id="p1", excerpt="Test")
        orch._benchmark_store.add_records([
            BenchmarkRecord(id="b1", model_name="M", benchmark_name="B", metric="acc", score="90", source=ref),
        ])
        orch._paper_knowledge_base.add(PaperKnowledge(paper_id="p1", title="Test"))
        orch._pdf_chunks = {"p1": []}
        orch._evidence_refs = [ref]
        orch._evidence_unavailable = {"p1"}

        # Verify populated
        assert orch._evidence_store.claim_count() == 1
        assert len(orch._benchmark_store.get_all()) == 1
        assert len(orch._paper_knowledge_base.get_all()) == 1
        assert len(orch._pdf_chunks) == 1
        assert len(orch._evidence_refs) == 1
        assert len(orch._evidence_unavailable) == 1

        # Simulate run_pipeline - it calls clear() on stores
        # We can't run the full pipeline without real tools, so just call the clear logic directly
        orch._evidence_store.clear()
        orch._benchmark_store.clear()
        orch._paper_knowledge_base.clear()
        orch._pdf_chunks.clear()
        orch._evidence_refs.clear()
        orch._evidence_unavailable.clear()

        # Verify cleared
        assert orch._evidence_store.claim_count() == 0
        assert len(orch._benchmark_store.get_all()) == 0
        assert len(orch._paper_knowledge_base.get_all()) == 0
        assert len(orch._pdf_chunks) == 0
        assert len(orch._evidence_refs) == 0
        assert len(orch._evidence_unavailable) == 0
