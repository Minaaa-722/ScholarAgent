"""Tests for EvidenceAcquisitionRouter.

Covers:
- PDF acquisition from full-text available paper
- Abstract fallback when PDF unavailable
- Metadata-only fallback
- Withdrawn paper (no acquisition possible)
- Edge cases: empty paper, missing fields
"""

import pytest
from unittest.mock import patch, Mock, MagicMock

from agent.evidence.evidence_acquisition import EvidenceAcquisitionRouter
from agent.evidence.paper_types import (
    EvidenceLevel,
    EvidenceSource,
    PaperAvailability,
    PaperStatus,
)


class TestEvidenceAcquisitionRouter:
    """Tests for EvidenceAcquisitionRouter."""

    # ------------------------------------------------------------------
    # PDF Acquisition
    # ------------------------------------------------------------------

    @patch("agent.evidence.evidence_acquisition.requests.get")
    def test_acquire_pdf_success(self, mock_get):
        """PDF download succeeds, returns FULL_TEXT evidence."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"PDF content here"
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        router = EvidenceAcquisitionRouter()
        availability = PaperAvailability(
            paper_id="paper123",
            metadata_available=True,
            abstract_available=True,
            fulltext_available=True,
            status=PaperStatus.PDF_AVAILABLE,
            evidence_level=EvidenceLevel.FULL_TEXT,
        )
        paper = {
            "paper_id": "paper123",
            "arxiv_id": "2503.18681",
            "pdf_url": "https://arxiv.org/pdf/2503.18681.pdf",
            "abstract": "Test abstract.",
        }

        result = router.acquire(paper, availability)
        assert result.paper_id == "paper123"
        assert result.source_type == "PDF"
        assert result.evidence_level == EvidenceLevel.FULL_TEXT
        assert result.content == "PDF content here"

    @patch("agent.evidence.evidence_acquisition.requests.get")
    def test_acquire_pdf_http_error(self, mock_get):
        """PDF download fails with HTTP error, falls back to abstract."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = __import__("requests").exceptions.HTTPError(
            response=Mock(status_code=404)
        )
        mock_get.return_value = mock_response

        router = EvidenceAcquisitionRouter()
        availability = PaperAvailability(
            paper_id="paper456",
            metadata_available=True,
            abstract_available=True,
            fulltext_available=False,
            status=PaperStatus.PDF_UNAVAILABLE,
            evidence_level=EvidenceLevel.ABSTRACT,
        )
        paper = {
            "paper_id": "paper456",
            "arxiv_id": None,
            "pdf_url": "https://example.com/paper.pdf",
            "abstract": "This is the abstract content.",
        }

        result = router.acquire(paper, availability)
        assert result.paper_id == "paper456"
        assert result.source_type == "ABSTRACT"
        assert result.evidence_level == EvidenceLevel.ABSTRACT
        assert result.content == "This is the abstract content."

    @patch("agent.evidence.evidence_acquisition.requests.get")
    def test_acquire_pdf_timeout(self, mock_get):
        """PDF download times out, falls back to abstract."""
        mock_get.side_effect = __import__("requests").exceptions.Timeout("timeout")

        router = EvidenceAcquisitionRouter()
        availability = PaperAvailability(
            paper_id="paper456",
            metadata_available=True,
            abstract_available=True,
            fulltext_available=False,
            status=PaperStatus.PDF_UNAVAILABLE,
            evidence_level=EvidenceLevel.ABSTRACT,
        )
        paper = {
            "paper_id": "paper456",
            "arxiv_id": None,
            "pdf_url": "https://example.com/paper.pdf",
            "abstract": "Abstract content.",
        }

        result = router.acquire(paper, availability)
        assert result.source_type == "ABSTRACT"
        assert result.evidence_level == EvidenceLevel.ABSTRACT

    # ------------------------------------------------------------------
    # Abstract-only paper
    # ------------------------------------------------------------------

    def test_acquire_abstract_only(self):
        """No PDF URL, abstract available."""
        router = EvidenceAcquisitionRouter()
        availability = PaperAvailability(
            paper_id="paper789",
            metadata_available=True,
            abstract_available=True,
            fulltext_available=False,
            status=PaperStatus.AVAILABLE,
            evidence_level=EvidenceLevel.ABSTRACT,
        )
        paper = {
            "paper_id": "paper789",
            "arxiv_id": None,
            "pdf_url": "",
            "abstract": "Abstract content here.",
        }

        result = router.acquire(paper, availability)
        assert result.source_type == "ABSTRACT"
        assert result.evidence_level == EvidenceLevel.ABSTRACT
        assert result.content == "Abstract content here."

    # ------------------------------------------------------------------
    # Metadata-only paper
    # ------------------------------------------------------------------

    def test_acquire_metadata_only(self):
        """No PDF URL and no abstract."""
        router = EvidenceAcquisitionRouter()
        availability = PaperAvailability(
            paper_id="paper000",
            metadata_available=True,
            abstract_available=False,
            fulltext_available=False,
            status=PaperStatus.UNKNOWN,
            evidence_level=EvidenceLevel.METADATA,
        )
        paper = {
            "paper_id": "paper000",
            "arxiv_id": None,
            "pdf_url": "",
            "abstract": "",
        }

        result = router.acquire(paper, availability)
        assert result.source_type == "METADATA"
        assert result.evidence_level == EvidenceLevel.METADATA

    # ------------------------------------------------------------------
    # Withdrawn paper
    # ------------------------------------------------------------------

    def test_acquire_withdrawn(self):
        """Withdrawn paper returns NONE evidence."""
        router = EvidenceAcquisitionRouter()
        availability = PaperAvailability(
            paper_id="paper999",
            metadata_available=True,
            abstract_available=False,
            fulltext_available=False,
            status=PaperStatus.WITHDRAWN,
            reason="Paper was withdrawn",
            evidence_level=EvidenceLevel.METADATA,
        )
        paper = {
            "paper_id": "paper999",
            "arxiv_id": "2503.99999",
            "pdf_url": "",
            "abstract": "",
        }

        result = router.acquire(paper, availability)
        assert result.source_type == "NONE"
        assert result.evidence_level == EvidenceLevel.NONE

    # ------------------------------------------------------------------
    # Edge cases
    # ------------------------------------------------------------------

    def test_acquire_empty_paper(self):
        """Empty paper returns NONE."""
        router = EvidenceAcquisitionRouter()
        result = router.acquire({}, PaperAvailability())
        assert result.source_type == "NONE"
        assert result.evidence_level == EvidenceLevel.NONE

    def test_acquire_many(self):
        """acquire_many processes multiple papers."""
        router = EvidenceAcquisitionRouter()
        papers = [
            {"paper_id": "p1", "pdf_url": "", "abstract": "Abstract 1."},
            {"paper_id": "p2", "pdf_url": "", "abstract": "Abstract 2."},
        ]
        availabilities = [
            PaperAvailability(
                paper_id="p1", metadata_available=True, abstract_available=True,
                status=PaperStatus.AVAILABLE, evidence_level=EvidenceLevel.ABSTRACT,
            ),
            PaperAvailability(
                paper_id="p2", metadata_available=True, abstract_available=True,
                status=PaperStatus.AVAILABLE, evidence_level=EvidenceLevel.ABSTRACT,
            ),
        ]
        results = router.acquire_many(papers, availabilities)
        assert len(results) == 2
        assert results[0].paper_id == "p1"
        assert results[1].paper_id == "p2"

    def test_acquire_many_empty(self):
        """acquire_many with empty lists returns empty list."""
        router = EvidenceAcquisitionRouter()
        assert router.acquire_many([], []) == []

    def test_acquire_many_mismatched_lengths(self):
        """Mismatched lists handled gracefully."""
        router = EvidenceAcquisitionRouter()
        results = router.acquire_many(
            [{"paper_id": "p1"}],
            []
        )
        assert len(results) == 0

    def test_acquire_returns_none_for_unknown(self):
        """Paper with no content sources returns NONE."""
        router = EvidenceAcquisitionRouter()
        availability = PaperAvailability(
            paper_id="unknown",
            metadata_available=False,
            abstract_available=False,
            fulltext_available=False,
            status=PaperStatus.UNKNOWN,
            evidence_level=EvidenceLevel.NONE,
        )
        result = router.acquire({}, availability)
        assert result.source_type == "NONE"
        assert result.evidence_level == EvidenceLevel.NONE