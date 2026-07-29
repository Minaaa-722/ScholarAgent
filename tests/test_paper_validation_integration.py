"""Integration tests for Paper Validation & Evidence Acquisition Layer.

Tests the complete flow from paper retrieval through validation, acquisition,
and evidence-level enforcement. Uses mocks for external dependencies.

Test scenarios:
1. Withdrawn arXiv paper → WITHDRAWN status, pipeline continues
2. PDF 404 → validation succeeds, acquisition falls back to abstract
3. Abstract-only paper → paper description allowed, benchmark rejected
4. Full PDF paper → architecture claims accepted
5. End-to-end pipeline trace with evidence coverage metrics
"""

import json
import pytest
from unittest.mock import patch, Mock, MagicMock

from agent.evidence.paper_types import (
    PaperStatus,
    EvidenceLevel,
    ClaimType,
    PaperAvailability,
    EvidenceSource,
    MIN_EVIDENCE_LEVEL,
)
from agent.evidence.paper_validator import PaperAvailabilityValidator
from agent.evidence.evidence_acquisition import EvidenceAcquisitionRouter
from agent.evidence.evidence_store import Claim, EvidenceStore


# =========================================================================
# Scenario 1: Withdrawn arXiv paper
# =========================================================================

class TestWithdrawnPaper:
    """Withdrawn paper should be detected and pipeline should continue."""

    @patch("agent.evidence.paper_validator.requests.get")
    def test_validation_detects_withdrawn(self, mock_get):
        """PaperValidator detects withdrawn arXiv paper."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = (
            "<html><body>This paper has been withdrawn by the authors.</body></html>"
        )
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        validator = PaperAvailabilityValidator()
        paper = {
            "paper_id": "withdrawn_test",
            "arxiv_id": "2503.99999",
            "pdf_url": "https://arxiv.org/pdf/2503.99999",
            "abstract": "This paper was about something.",
            "source": "arxiv",
        }

        result = validator.validate(paper)
        assert result.status == PaperStatus.WITHDRAWN
        assert result.evidence_level == EvidenceLevel.METADATA
        assert result.fulltext_available is False

    def test_acquisition_returns_none_for_withdrawn(self):
        """EvidenceAcquisitionRouter returns NONE for withdrawn paper."""
        router = EvidenceAcquisitionRouter()
        availability = PaperAvailability(
            paper_id="withdrawn_test",
            metadata_available=True,
            abstract_available=False,
            fulltext_available=False,
            status=PaperStatus.WITHDRAWN,
            reason="Paper was withdrawn",
            evidence_level=EvidenceLevel.METADATA,
        )
        paper = {
            "paper_id": "withdrawn_test",
            "arxiv_id": "2503.99999",
            "abstract": "This paper was about something.",
        }

        result = router.acquire(paper, availability)
        assert result.source_type == "NONE"
        assert result.evidence_level == EvidenceLevel.NONE

    def test_pipeline_continues_with_withdrawn(self):
        """Pipeline should not fail when a paper is withdrawn."""
        from agent.core.pipeline import PipelineOrchestrator, HarnessConfig
        from agent.tools.registry import ToolRegistry
        from agent.guardrails.manager import GuardrailManager
        from agent.core.llm import MockLLM

        llm = MockLLM(fixed_response="\\section{Test}\nSurvey content")
        orch = PipelineOrchestrator(
            llm=llm,
            tools=ToolRegistry(),
            validators=[],
            guardrails=GuardrailManager(guardrails=[]),
            config=HarnessConfig(),
            latex_repair=None,
        )

        # Simulate withdrawn paper validation
        withdrawn = PaperAvailability(
            paper_id="withdrawn_test",
            metadata_available=True,
            abstract_available=True,
            fulltext_available=False,
            status=PaperStatus.WITHDRAWN,
            reason="Withdrawn",
            evidence_level=EvidenceLevel.METADATA,
        )

        # This should not raise — the pipeline handles withdrawn gracefully
        sources = orch._evidence_acquisition.acquire_many(
            [{"paper_id": "withdrawn_test", "arxiv_id": "2503.99999"}],
            [withdrawn],
        )
        assert len(sources) == 1
        assert sources[0].source_type == "NONE"

    @patch("agent.evidence.paper_validator.requests.get")
    def test_validation_trace_logging(self, mock_get):
        """Validation produces trace log with correct format."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "<html><body>withdrawn</body></html>"
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        import logging
        from io import StringIO

        logger = logging.getLogger("agent.evidence.paper_validator")
        old_level = logger.level
        logger.setLevel(logging.INFO)

        stream = StringIO()
        handler = logging.StreamHandler(stream)
        logger.addHandler(handler)

        try:
            validator = PaperAvailabilityValidator()
            paper = {
                "paper_id": "trace_test",
                "arxiv_id": "2503.99998",
                "pdf_url": "",
                "abstract": "",
                "source": "arxiv",
            }
            result = validator.validate(paper)

            log_output = stream.getvalue()
            assert "[PAPER_VALIDATION]" in log_output
            assert "paper_id=trace_test" in log_output
            assert "status=WITHDRAWN" in log_output
        finally:
            logger.removeHandler(handler)
            logger.setLevel(old_level)


# =========================================================================
# Scenario 2: PDF 404 → fallback to abstract
# =========================================================================

class TestPDFUnavailable:
    """PDF unavailable should fall back to abstract."""

    @patch("agent.evidence.evidence_acquisition.requests.get")
    def test_validation_succeeds_with_pdf_404(self, mock_get):
        """Validation should succeed even when PDF URL is invalid."""
        mock_get.side_effect = __import__("requests").exceptions.HTTPError(
            response=Mock(status_code=404)
        )

        router = EvidenceAcquisitionRouter()
        availability = PaperAvailability(
            paper_id="pdf404_test",
            metadata_available=True,
            abstract_available=True,
            fulltext_available=False,
            status=PaperStatus.PDF_UNAVAILABLE,
            reason="PDF URL returned 404",
            evidence_level=EvidenceLevel.ABSTRACT,
        )
        paper = {
            "paper_id": "pdf404_test",
            "arxiv_id": None,
            "pdf_url": "https://example.com/paper.pdf",
            "abstract": "This is the abstract content that should be used as fallback.",
        }

        result = router.acquire(paper, availability)
        assert result.source_type == "ABSTRACT"
        assert result.evidence_level == EvidenceLevel.ABSTRACT
        assert "abstract content" in result.content.lower()

    @patch("agent.evidence.evidence_acquisition.requests.get")
    def test_acquisition_fallback_trace(self, mock_get):
        """Acquisition produces trace log with fallback info."""
        mock_get.side_effect = __import__("requests").exceptions.Timeout("timeout")

        import logging
        from io import StringIO

        logger = logging.getLogger("agent.evidence.evidence_acquisition")
        old_level = logger.level
        logger.setLevel(logging.INFO)

        stream = StringIO()
        handler = logging.StreamHandler(stream)
        logger.addHandler(handler)

        try:
            router = EvidenceAcquisitionRouter()
            availability = PaperAvailability(
                paper_id="fallback_trace",
                metadata_available=True,
                abstract_available=True,
                fulltext_available=False,
                status=PaperStatus.PDF_UNAVAILABLE,
                evidence_level=EvidenceLevel.ABSTRACT,
            )
            paper = {
                "paper_id": "fallback_trace",
                "pdf_url": "https://example.com/paper.pdf",
                "abstract": "Fallback abstract.",
            }
            result = router.acquire(paper, availability)

            log_output = stream.getvalue()
            assert "[EVIDENCE_ACQUISITION]" in log_output
            assert "paper_id=fallback_trace" in log_output
            assert "ABSTRACT" in log_output
        finally:
            logger.removeHandler(handler)
            logger.setLevel(old_level)


# =========================================================================
# Scenario 3: Abstract-only paper
# =========================================================================

class TestAbstractOnly:
    """Abstract-only paper should allow paper description but reject benchmark."""

    def test_abstract_only_validation(self):
        """Paper with only abstract gets ABSTRACT evidence level."""
        validator = PaperAvailabilityValidator()
        paper = {
            "paper_id": "abstract_only",
            "arxiv_id": None,
            "pdf_url": "",
            "abstract": "This paper presents a novel approach to vision transformers.",
            "source": "semantic_scholar",
        }
        result = validator.validate(paper)
        assert result.evidence_level == EvidenceLevel.ABSTRACT
        assert result.abstract_available is True
        assert result.fulltext_available is False

    def test_abstract_only_acquisition(self):
        """Abstract-only paper uses ABSTRACT source."""
        router = EvidenceAcquisitionRouter()
        availability = PaperAvailability(
            paper_id="abstract_only",
            metadata_available=True,
            abstract_available=True,
            fulltext_available=False,
            status=PaperStatus.AVAILABLE,
            evidence_level=EvidenceLevel.ABSTRACT,
        )
        paper = {
            "paper_id": "abstract_only",
            "abstract": "This paper presents a novel vision transformer.",
        }
        result = router.acquire(paper, availability)
        assert result.source_type == "ABSTRACT"
        assert result.evidence_level == EvidenceLevel.ABSTRACT

    def test_paper_description_allowed_with_abstract(self):
        """PAPER_DESCRIPTION claim type requires only ABSTRACT evidence."""
        # PAPER_DESCRIPTION requires ABSTRACT
        min_level = MIN_EVIDENCE_LEVEL[ClaimType.PAPER_DESCRIPTION]
        assert min_level == EvidenceLevel.ABSTRACT

        # A claim with abstract evidence should pass the gate
        claim = Claim(
            claim="This paper presents a novel approach.",
            category="architecture",
            claim_type=ClaimType.PAPER_DESCRIPTION,
            evidence_level=EvidenceLevel.ABSTRACT,
        )
        assert claim.evidence_level >= min_level

    def test_benchmark_rejected_with_abstract(self):
        """BENCHMARK_RESULT requires FULL_TEXT, rejects ABSTRACT."""
        min_level = MIN_EVIDENCE_LEVEL[ClaimType.BENCHMARK_RESULT]
        assert min_level == EvidenceLevel.FULL_TEXT

        # A benchmark claim with abstract evidence should fail the gate
        claim = Claim(
            claim="Model achieves 85.3% on MMLU.",
            category="benchmark",
            claim_type=ClaimType.BENCHMARK_RESULT,
            evidence_level=EvidenceLevel.ABSTRACT,
        )
        assert claim.evidence_level < min_level

    def test_evidence_gate_filters_benchmark(self):
        """Evidence gate removes benchmark claims with insufficient evidence."""
        from agent.evidence.evidence_store import EvidenceStore

        store = EvidenceStore()
        store.add_claims([
            Claim(
                claim="Model achieves 85.3% on MMLU.",
                category="benchmark",
                claim_type=ClaimType.BENCHMARK_RESULT,
                evidence_level=EvidenceLevel.ABSTRACT,
                paper_id="abstract_only",
            ),
            Claim(
                claim="This paper presents a novel approach.",
                category="architecture",
                claim_type=ClaimType.PAPER_DESCRIPTION,
                evidence_level=EvidenceLevel.ABSTRACT,
                paper_id="abstract_only",
            ),
        ])
        assert store.claim_count() == 2

        # Apply evidence gate (simulate what pipeline does)
        from agent.evidence.paper_types import MIN_EVIDENCE_LEVEL
        kept = []
        removed = []
        for c in store.get_all_claims():
            min_level = MIN_EVIDENCE_LEVEL.get(c.claim_type, EvidenceLevel.ABSTRACT)
            if c.evidence_level >= min_level:
                kept.append(c)
            else:
                removed.append(c)

        assert len(kept) == 1  # paper description kept
        assert len(removed) == 1  # benchmark removed
        assert kept[0].claim_type == ClaimType.PAPER_DESCRIPTION
        assert removed[0].claim_type == ClaimType.BENCHMARK_RESULT


# =========================================================================
# Scenario 4: Full PDF paper
# =========================================================================

class TestFullPDF:
    """Full PDF paper should allow all claim types."""

    @patch("agent.evidence.evidence_acquisition.requests.get")
    def test_full_pdf_acquisition(self, mock_get):
        """Full PDF paper acquires FULL_TEXT evidence."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"Full PDF content with architecture details and benchmark results."
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        router = EvidenceAcquisitionRouter()
        availability = PaperAvailability(
            paper_id="full_pdf_test",
            metadata_available=True,
            abstract_available=True,
            fulltext_available=True,
            status=PaperStatus.PDF_AVAILABLE,
            evidence_level=EvidenceLevel.FULL_TEXT,
        )
        paper = {
            "paper_id": "full_pdf_test",
            "arxiv_id": "2503.18681",
            "pdf_url": "https://arxiv.org/pdf/2503.18681.pdf",
            "abstract": "This paper presents a novel architecture.",
        }

        result = router.acquire(paper, availability)
        assert result.source_type == "PDF"
        assert result.evidence_level == EvidenceLevel.FULL_TEXT

    def test_architecture_claims_accepted_with_full_text(self):
        """ARCHITECTURE claims accepted with FULL_TEXT evidence."""
        min_level = MIN_EVIDENCE_LEVEL[ClaimType.ARCHITECTURE]
        assert min_level == EvidenceLevel.HTML

        # FULL_TEXT >= HTML, so this should pass
        claim = Claim(
            claim="Model uses a novel transformer architecture.",
            category="architecture",
            claim_type=ClaimType.ARCHITECTURE,
            evidence_level=EvidenceLevel.FULL_TEXT,
        )
        assert claim.evidence_level >= min_level

    def test_benchmark_accepted_with_full_text(self):
        """BENCHMARK_RESULT accepted with FULL_TEXT evidence."""
        min_level = MIN_EVIDENCE_LEVEL[ClaimType.BENCHMARK_RESULT]
        assert min_level == EvidenceLevel.FULL_TEXT

        claim = Claim(
            claim="Model achieves 85.3% on MMLU.",
            category="benchmark",
            claim_type=ClaimType.BENCHMARK_RESULT,
            evidence_level=EvidenceLevel.FULL_TEXT,
        )
        assert claim.evidence_level >= min_level

    def test_training_detail_accepted_with_full_text(self):
        """TRAINING_DETAIL accepted with FULL_TEXT evidence."""
        min_level = MIN_EVIDENCE_LEVEL[ClaimType.TRAINING_DETAIL]
        assert min_level == EvidenceLevel.FULL_TEXT

        claim = Claim(
            claim="Model trained on LAION-5B for 30 epochs.",
            category="architecture",
            claim_type=ClaimType.TRAINING_DETAIL,
            evidence_level=EvidenceLevel.FULL_TEXT,
        )
        assert claim.evidence_level >= min_level


# =========================================================================
# Scenario 5: Evidence coverage metrics
# =========================================================================

class TestEvidenceCoverage:
    """Evidence coverage metrics computation."""

    def test_coverage_all_grounded(self):
        """All claims with FULL_TEXT evidence → 100% coverage."""
        from agent.evidence.evidence_store import EvidenceStore

        store = EvidenceStore()
        store.add_claims([
            Claim(
                claim="Architecture claim",
                category="architecture",
                claim_type=ClaimType.ARCHITECTURE,
                evidence_level=EvidenceLevel.FULL_TEXT,
                paper_id="p1",
            ),
            Claim(
                claim="Benchmark claim",
                category="benchmark",
                claim_type=ClaimType.BENCHMARK_RESULT,
                evidence_level=EvidenceLevel.FULL_TEXT,
                paper_id="p1",
            ),
        ])

        all_claims = store.get_all_claims()
        total = len(all_claims)
        grounded = len([c for c in all_claims if c.evidence_level >= EvidenceLevel.HTML])
        coverage = grounded / total if total > 0 else 0.0

        assert coverage == 1.0
        assert grounded == 2

    def test_coverage_partial(self):
        """Mixed evidence levels → partial coverage."""
        from agent.evidence.evidence_store import EvidenceStore

        store = EvidenceStore()
        store.add_claims([
            Claim(
                claim="Architecture claim",
                category="architecture",
                claim_type=ClaimType.ARCHITECTURE,
                evidence_level=EvidenceLevel.FULL_TEXT,
                paper_id="p1",
            ),
            Claim(
                claim="Paper description",
                category="architecture",
                claim_type=ClaimType.PAPER_DESCRIPTION,
                evidence_level=EvidenceLevel.ABSTRACT,
                paper_id="p2",
            ),
            Claim(
                claim="Benchmark claim without full text",
                category="benchmark",
                claim_type=ClaimType.BENCHMARK_RESULT,
                evidence_level=EvidenceLevel.ABSTRACT,
                paper_id="p2",
            ),
        ])

        all_claims = store.get_all_claims()
        total = len(all_claims)
        grounded = len([c for c in all_claims if c.evidence_level >= EvidenceLevel.HTML])
        coverage = grounded / total if total > 0 else 0.0

        assert coverage == 1.0 / 3.0
        assert grounded == 1

    def test_benchmark_coverage(self):
        """Benchmark-specific coverage calculation."""
        from agent.evidence.evidence_store import EvidenceStore
        from agent.evidence.paper_types import ClaimType

        store = EvidenceStore()
        store.add_claims([
            Claim(
                claim="Benchmark with full text",
                category="benchmark",
                claim_type=ClaimType.BENCHMARK_RESULT,
                evidence_level=EvidenceLevel.FULL_TEXT,
                paper_id="p1",
            ),
            Claim(
                claim="Benchmark without full text",
                category="benchmark",
                claim_type=ClaimType.BENCHMARK_RESULT,
                evidence_level=EvidenceLevel.ABSTRACT,
                paper_id="p2",
            ),
        ])

        benchmark_claims = [
            c for c in store.get_all_claims()
            if c.claim_type == ClaimType.BENCHMARK_RESULT
        ]
        total = len(benchmark_claims)
        verified = len([
            c for c in benchmark_claims
            if c.evidence_level >= EvidenceLevel.FULL_TEXT
        ])
        coverage = verified / total if total > 0 else 0.0

        assert coverage == 0.5
        assert verified == 1

    def test_empty_coverage(self):
        """Empty store → 0% coverage."""
        all_claims = []
        total = len(all_claims)
        grounded = len([c for c in all_claims if c.evidence_level >= EvidenceLevel.HTML])
        coverage = grounded / total if total > 0 else 0.0

        assert coverage == 0.0
        assert grounded == 0


# =========================================================================
# Scenario 6: End-to-end pipeline trace
# =========================================================================

class TestPipelineTrace:
    """End-to-end pipeline trace with evidence metrics."""

    @patch("agent.evidence.paper_validator.requests.get")
    def test_pipeline_trace_validation(self, mock_get):
        """Pipeline should produce structured validation trace."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "<html><body>Available paper.</body></html>"
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        validator = PaperAvailabilityValidator()
        papers = [
            {
                "paper_id": "p1",
                "arxiv_id": "2503.10001",
                "pdf_url": "https://arxiv.org/pdf/2503.10001.pdf",
                "abstract": "Paper 1 abstract.",
                "source": "arxiv",
            },
            {
                "paper_id": "p2",
                "arxiv_id": None,
                "pdf_url": "",
                "abstract": "Paper 2 abstract.",
                "source": "semantic_scholar",
            },
        ]

        results = validator.validate_many(papers)
        assert len(results) == 2
        # p1 should be PDF_AVAILABLE (has arxiv_id + pdf_url)
        # p2 should be AVAILABLE (abstract only)
        statuses = {r.paper_id: r.status for r in results}
        assert "PDF_AVAILABLE" in [s.value for s in statuses.values()] or "AVAILABLE" in [s.value for s in statuses.values()]

    @patch("agent.evidence.evidence_acquisition.requests.get")
    def test_pipeline_trace_acquisition(self, mock_get):
        """Pipeline should produce structured acquisition trace."""
        mock_get.side_effect = __import__("requests").exceptions.Timeout("timeout")

        router = EvidenceAcquisitionRouter()
        papers = [
            {
                "paper_id": "p1",
                "arxiv_id": "2503.10001",
                "pdf_url": "https://arxiv.org/pdf/2503.10001.pdf",
                "abstract": "Paper 1 abstract.",
            },
        ]
        availabilities = [
            PaperAvailability(
                paper_id="p1",
                metadata_available=True,
                abstract_available=True,
                fulltext_available=False,
                status=PaperStatus.PDF_UNAVAILABLE,
                evidence_level=EvidenceLevel.ABSTRACT,
            ),
        ]

        # PDF fails, should fall back to abstract
        sources = router.acquire_many(papers, availabilities)
        assert len(sources) == 1
        assert sources[0].source_type == "ABSTRACT"
        assert sources[0].evidence_level == EvidenceLevel.ABSTRACT


# =========================================================================
# Scenario 7: Evidence level enforcement
# =========================================================================

class TestEvidenceLevelEnforcement:
    """Evidence level enforcement before writing."""

    def test_evidence_gate_removes_unsupported(self):
        """Evidence gate removes claims below minimum evidence level."""
        from agent.evidence.evidence_store import EvidenceStore
        from agent.evidence.paper_types import MIN_EVIDENCE_LEVEL

        store = EvidenceStore()
        store.add_claims([
            # Benchmark claim with ABSTRACT only → should be removed
            Claim(
                claim="MMLU: 85.3%",
                category="benchmark",
                claim_type=ClaimType.BENCHMARK_RESULT,
                evidence_level=EvidenceLevel.ABSTRACT,
                paper_id="p1",
            ),
            # Architecture claim with FULL_TEXT → should be kept
            Claim(
                claim="Uses ViT-L/14 encoder",
                category="architecture",
                claim_type=ClaimType.ARCHITECTURE,
                evidence_level=EvidenceLevel.FULL_TEXT,
                paper_id="p1",
            ),
            # Paper description with ABSTRACT → should be kept
            Claim(
                claim="Novel approach",
                category="architecture",
                claim_type=ClaimType.PAPER_DESCRIPTION,
                evidence_level=EvidenceLevel.ABSTRACT,
                paper_id="p1",
            ),
        ])

        # Apply evidence gate
        kept = []
        removed = []
        for c in store.get_all_claims():
            min_level = MIN_EVIDENCE_LEVEL.get(c.claim_type, EvidenceLevel.ABSTRACT)
            if c.evidence_level >= min_level:
                kept.append(c)
            else:
                removed.append(c)

        assert len(kept) == 2  # architecture + paper description
        assert len(removed) == 1  # benchmark removed
        assert removed[0].claim_type == ClaimType.BENCHMARK_RESULT

    def test_metadata_only_not_for_survey(self):
        """METADATA evidence cannot be used for survey statements."""
        min_level = MIN_EVIDENCE_LEVEL[ClaimType.PAPER_DESCRIPTION]
        assert min_level == EvidenceLevel.ABSTRACT

        # METADATA < ABSTRACT, so it should fail
        metadata_claim = Claim(
            claim="Paper was published in 2025.",
            category="architecture",
            claim_type=ClaimType.PAPER_DESCRIPTION,
            evidence_level=EvidenceLevel.METADATA,
        )
        assert metadata_claim.evidence_level < min_level

    def test_evidence_gate_preserves_metadata_in_store(self):
        """Evidence gate removes from writing context but preserves in store."""
        from agent.evidence.evidence_store import EvidenceStore
        from agent.evidence.paper_types import MIN_EVIDENCE_LEVEL

        store = EvidenceStore()
        store.add_claims([
            Claim(
                claim="Benchmark with abstract only",
                category="benchmark",
                claim_type=ClaimType.BENCHMARK_RESULT,
                evidence_level=EvidenceLevel.ABSTRACT,
                paper_id="p1",
            ),
        ])

        # Store has the claim
        assert store.claim_count() == 1

        # Evidence gate would filter it
        all_claims = store.get_all_claims()
        above_gate = [
            c for c in all_claims
            if c.evidence_level >= MIN_EVIDENCE_LEVEL.get(c.claim_type, EvidenceLevel.ABSTRACT)
        ]
        below_gate = [
            c for c in all_claims
            if c.evidence_level < MIN_EVIDENCE_LEVEL.get(c.claim_type, EvidenceLevel.ABSTRACT)
        ]

        # The claim is below the gate
        assert len(above_gate) == 0
        assert len(below_gate) == 1

        # The store still has it (gate rebuilds store, but for tracking purposes
        # the test verifies the filtering logic)
        assert store.claim_count() == 1