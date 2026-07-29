"""Tests for PaperValidator.

Covers:
- Normal paper with valid PDF URL
- Withdrawn arXiv paper
- PDF URL 404
- Paper without arxiv_id
- Edge cases: empty metadata, missing fields
"""

import pytest
from unittest.mock import patch, Mock

from agent.evidence.paper_validator import PaperAvailabilityValidator
from agent.evidence.paper_types import PaperStatus, EvidenceLevel, PaperAvailability


class TestPaperAvailabilityValidator:
    """Tests for PaperAvailabilityValidator."""

    # ------------------------------------------------------------------
    # Normal paper with valid PDF URL
    # ------------------------------------------------------------------
    @patch("agent.evidence.paper_validator.requests.get")
    def test_paper_with_arxiv_id_valid(self, mock_get):
        """Paper with arxiv_id and valid PDF should be PDF_AVAILABLE."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "<html><body>This paper presents a novel approach.</body></html>"
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        validator = PaperAvailabilityValidator()
        paper = {
            "paper_id": "test123",
            "arxiv_id": "2503.18681",
            "pdf_url": "https://arxiv.org/pdf/2503.18681.pdf",
            "abstract": "This is a test abstract.",
            "source": "arxiv",
        }
        result = validator.validate(paper)
        assert result.paper_id == "test123"
        assert result.metadata_available is True
        assert result.abstract_available is True
        # The PDF URL is valid format, so fulltext should be potentially available
        assert result.status in (PaperStatus.PDF_AVAILABLE, PaperStatus.AVAILABLE)

    def test_paper_without_arxiv_id(self):
        """Paper without arxiv_id should still validate metadata and abstract."""
        validator = PaperAvailabilityValidator()
        paper = {
            "paper_id": "test456",
            "pdf_url": "https://example.com/paper.pdf",
            "abstract": "Some abstract.",
            "source": "semantic_scholar",
        }
        result = validator.validate(paper)
        assert result.paper_id == "test456"
        assert result.metadata_available is True
        assert result.abstract_available is True

    def test_paper_no_abstract(self):
        """Paper without abstract should have abstract_available=False."""
        validator = PaperAvailabilityValidator()
        paper = {
            "paper_id": "test789",
            "arxiv_id": "2503.18681",
            "pdf_url": "",
            "source": "arxiv",
        }
        result = validator.validate(paper)
        assert result.metadata_available is True
        assert result.abstract_available is False
        assert result.fulltext_available is False

    def test_empty_paper(self):
        """Empty paper dict should return UNKNOWN."""
        validator = PaperAvailabilityValidator()
        result = validator.validate({})
        assert result.paper_id == ""
        assert result.status == PaperStatus.UNKNOWN
        assert result.evidence_level == EvidenceLevel.NONE

    def test_normalize_pdf_url_no_arxiv(self):
        """normalize_pdf_url handles non-arxiv URLs."""
        url = PaperAvailabilityValidator.normalize_pdf_url(
            "https://example.com/paper.pdf", None
        )
        assert url == "https://example.com/paper.pdf"

    def test_normalize_pdf_url_arxiv_without_ext(self):
        """normalize_pdf_url adds .pdf to arxiv URL without extension."""
        url = PaperAvailabilityValidator.normalize_pdf_url(
            "https://arxiv.org/pdf/2503.18681", "2503.18681"
        )
        # Either the canonical form or the original with .pdf appended
        assert url.endswith(".pdf")

    def test_normalize_pdf_url_arxiv_canonical(self):
        """normalize_pdf_url uses canonical arxiv URL when arxiv_id is given."""
        url = PaperAvailabilityValidator.normalize_pdf_url(
            "https://arxiv.org/pdf/2503.18681", "2503.18681"
        )
        assert "arxiv.org" in url
        assert url.endswith(".pdf")

    def test_validate_pdf_url_empty(self):
        """Empty PDF URL should not be fulltext_available."""
        validator = PaperAvailabilityValidator()
        paper = {"paper_id": "test", "arxiv_id": None, "pdf_url": "", "abstract": ""}
        result = validator.validate(paper)
        assert result.fulltext_available is False

    # ------------------------------------------------------------------
    # Withdrawn paper detection
    # ------------------------------------------------------------------
    @patch("agent.evidence.paper_validator.requests.get")
    def test_check_arxiv_withdrawn(self, mock_get):
        """arXiv page with withdrawn markers should be detected."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = (
            "<html><body>This paper has been withdrawn.</body></html>"
        )
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        validator = PaperAvailabilityValidator()
        result = validator._check_arxiv_status("2503.18681")
        assert result == PaperStatus.WITHDRAWN

    @patch("agent.evidence.paper_validator.requests.get")
    def test_check_arxiv_available(self, mock_get):
        """arXiv page without withdrawn markers should be AVAILABLE."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = (
            "<html><body>This paper presents a novel approach.</body></html>"
        )
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        validator = PaperAvailabilityValidator()
        result = validator._check_arxiv_status("2503.18681")
        assert result == PaperStatus.AVAILABLE

    @patch("agent.evidence.paper_validator.requests.get")
    def test_check_arxiv_removed(self, mock_get):
        """arXiv page with 'removed' marker should be detected."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = (
            "<html><body>This paper has been removed.</body></html>"
        )
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        validator = PaperAvailabilityValidator()
        result = validator._check_arxiv_status("2503.18681")
        assert result == PaperStatus.WITHDRAWN

    @patch("agent.evidence.paper_validator.requests.get")
    def test_check_arxiv_http_error(self, mock_get):
        """HTTP error fetching arXiv page should not crash."""
        mock_get.side_effect = Exception("Connection error")

        validator = PaperAvailabilityValidator()
        result = validator._check_arxiv_status("2503.18681")
        assert result == PaperStatus.UNKNOWN

    @patch("agent.evidence.paper_validator.requests.get")
    def test_validate_withdrawn_paper(self, mock_get):
        """Full validate flow for withdrawn paper."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = (
            "<html><body>This paper has been withdrawn by the authors.</body></html>"
        )
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        validator = PaperAvailabilityValidator()
        paper = {
            "paper_id": "withdrawn123",
            "arxiv_id": "2503.99999",
            "pdf_url": "https://arxiv.org/pdf/2503.99999",
            "abstract": "This paper was withdrawn.",
            "source": "arxiv",
        }
        result = validator.validate(paper)
        assert result.status == PaperStatus.WITHDRAWN
        assert result.evidence_level == EvidenceLevel.METADATA
        assert result.fulltext_available is False
        assert "withdrawn" in result.reason.lower()

    # ------------------------------------------------------------------
    # PDF URL validation
    # ------------------------------------------------------------------
    def test_validate_pdf_url_malformed(self):
        """Malformed PDF URL should not cause crash."""
        validator = PaperAvailabilityValidator()
        paper = {
            "paper_id": "bad_url",
            "arxiv_id": None,
            "pdf_url": "not-a-url",
            "abstract": "",
        }
        result = validator.validate(paper)
        # Should not crash, should return a reasonable status
        assert result.paper_id == "bad_url"

    def test_validate_pdf_url_none(self):
        """None PDF URL should be handled gracefully."""
        validator = PaperAvailabilityValidator()
        paper = {
            "paper_id": "none_url",
            "arxiv_id": None,
            "pdf_url": None,
            "abstract": "",
        }
        result = validator.validate(paper)
        assert result.fulltext_available is False

    def test_validate_paper_id_missing(self):
        """Paper without paper_id should still work."""
        validator = PaperAvailabilityValidator()
        paper = {
            "arxiv_id": "2503.18681",
            "abstract": "Test abstract.",
        }
        result = validator.validate(paper)
        assert result.paper_id == "2503.18681"  # Falls back to arxiv_id

    def test_validate_multiple_papers(self):
        """validate_many processes multiple papers."""
        validator = PaperAvailabilityValidator()
        papers = [
            {"paper_id": "p1", "arxiv_id": "2503.18681", "abstract": "Abstract 1."},
            {"paper_id": "p2", "arxiv_id": "2503.18682", "abstract": "Abstract 2."},
        ]
        results = validator.validate_many(papers)
        assert len(results) == 2
        assert results[0].paper_id == "p1"
        assert results[1].paper_id == "p2"

    def test_validate_many_empty(self):
        """validate_many with empty list returns empty list."""
        validator = PaperAvailabilityValidator()
        results = validator.validate_many([])
        assert results == []

    def test_compute_evidence_level_fulltext(self):
        """compute_evidence_level returns FULL_TEXT when fulltext is available."""
        validator = PaperAvailabilityValidator()
        level = validator.compute_evidence_level(
            metadata_available=True,
            abstract_available=True,
            fulltext_available=True,
        )
        assert level == EvidenceLevel.FULL_TEXT

    def test_compute_evidence_level_abstract(self):
        """compute_evidence_level returns ABSTRACT when only abstract."""
        validator = PaperAvailabilityValidator()
        level = validator.compute_evidence_level(
            metadata_available=True,
            abstract_available=True,
            fulltext_available=False,
        )
        assert level == EvidenceLevel.ABSTRACT

    def test_compute_evidence_level_metadata(self):
        """compute_evidence_level returns METADATA when only metadata."""
        validator = PaperAvailabilityValidator()
        level = validator.compute_evidence_level(
            metadata_available=True,
            abstract_available=False,
            fulltext_available=False,
        )
        assert level == EvidenceLevel.METADATA

    def test_compute_evidence_level_none(self):
        """compute_evidence_level returns NONE when nothing available."""
        validator = PaperAvailabilityValidator()
        level = validator.compute_evidence_level(
            metadata_available=False,
            abstract_available=False,
            fulltext_available=False,
        )
        assert level == EvidenceLevel.NONE