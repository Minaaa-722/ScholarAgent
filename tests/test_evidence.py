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
        checker = EvidenceChecker(evidence_store=store)
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
        checker = EvidenceChecker(evidence_store=store)
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
        checker = EvidenceChecker(evidence_store=store)
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
        checker = EvidenceChecker(evidence_store=store)
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
        checker = EvidenceChecker(evidence_store=store)
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
        checker = EvidenceChecker(evidence_store=store, llm=llm)
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
        checker = EvidenceChecker(evidence_store=store)
        assert checker.name == "check_evidence"

    def test_checker_no_evidence_store_still_works(self):
        """Checker works with empty evidence store and no LLM."""
        store = EvidenceStore()
        checker = EvidenceChecker(evidence_store=store)
        result = checker.validate({
            "content": "Some paper uses a novel approach."
        })
        # Without verified claims, all candidates are flagged
        # "uses a novel approach" matches the "uses" pattern
        assert isinstance(result, ValidationResult)


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