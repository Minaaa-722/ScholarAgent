"""Tests for paper types (PaperStatus, EvidenceLevel, PaperAvailability, ClaimType, EvidenceSource)."""

import pytest
from agent.evidence.paper_types import (
    PaperStatus,
    EvidenceLevel,
    PaperAvailability,
    ClaimType,
    EvidenceSource,
    MIN_EVIDENCE_LEVEL,
)


class TestPaperStatus:
    def test_enum_values(self):
        assert PaperStatus.AVAILABLE.value == "AVAILABLE"
        assert PaperStatus.PDF_AVAILABLE.value == "PDF_AVAILABLE"
        assert PaperStatus.PDF_UNAVAILABLE.value == "PDF_UNAVAILABLE"
        assert PaperStatus.WITHDRAWN.value == "WITHDRAWN"
        assert PaperStatus.RETRACTED.value == "RETRACTED"
        assert PaperStatus.UNKNOWN.value == "UNKNOWN"


class TestEvidenceLevel:
    def test_enum_values(self):
        assert EvidenceLevel.NONE.value == 0
        assert EvidenceLevel.METADATA.value == 1
        assert EvidenceLevel.ABSTRACT.value == 2
        assert EvidenceLevel.HTML.value == 3
        assert EvidenceLevel.FULL_TEXT.value == 4

    def test_ordering(self):
        assert EvidenceLevel.NONE < EvidenceLevel.METADATA
        assert EvidenceLevel.METADATA < EvidenceLevel.ABSTRACT
        assert EvidenceLevel.ABSTRACT < EvidenceLevel.HTML
        assert EvidenceLevel.HTML < EvidenceLevel.FULL_TEXT

    def test_ge_le(self):
        assert EvidenceLevel.FULL_TEXT >= EvidenceLevel.HTML
        assert EvidenceLevel.ABSTRACT >= EvidenceLevel.ABSTRACT
        assert EvidenceLevel.METADATA <= EvidenceLevel.ABSTRACT


class TestPaperAvailability:
    def test_default_creation(self):
        pa = PaperAvailability(paper_id="test123")
        assert pa.paper_id == "test123"
        assert pa.metadata_available is False
        assert pa.abstract_available is False
        assert pa.fulltext_available is False
        assert pa.status == PaperStatus.UNKNOWN
        assert pa.reason == ""
        assert pa.evidence_level == EvidenceLevel.NONE

    def test_full_creation(self):
        pa = PaperAvailability(
            paper_id="paper123",
            metadata_available=True,
            abstract_available=True,
            fulltext_available=True,
            status=PaperStatus.PDF_AVAILABLE,
            reason="Found at arxiv.org",
            evidence_level=EvidenceLevel.FULL_TEXT,
        )
        assert pa.paper_id == "paper123"
        assert pa.metadata_available is True
        assert pa.abstract_available is True
        assert pa.fulltext_available is True
        assert pa.status == PaperStatus.PDF_AVAILABLE
        assert pa.reason == "Found at arxiv.org"
        assert pa.evidence_level == EvidenceLevel.FULL_TEXT

    def test_pdf_unavailable(self):
        pa = PaperAvailability(
            paper_id="paper456",
            metadata_available=True,
            abstract_available=True,
            fulltext_available=False,
            status=PaperStatus.PDF_UNAVAILABLE,
            reason="PDF URL returned 404",
            evidence_level=EvidenceLevel.ABSTRACT,
        )
        assert pa.paper_id == "paper456"
        assert pa.status == PaperStatus.PDF_UNAVAILABLE
        assert pa.evidence_level == EvidenceLevel.ABSTRACT

    def test_withdrawn(self):
        pa = PaperAvailability(
            paper_id="paper789",
            metadata_available=True,
            abstract_available=False,
            fulltext_available=False,
            status=PaperStatus.WITHDRAWN,
            reason="Paper was withdrawn from arXiv",
            evidence_level=EvidenceLevel.METADATA,
        )
        assert pa.paper_id == "paper789"
        assert pa.status == PaperStatus.WITHDRAWN
        assert pa.evidence_level == EvidenceLevel.METADATA


class TestEvidenceSource:
    def test_default_creation(self):
        es = EvidenceSource(paper_id="test123")
        assert es.paper_id == "test123"
        assert es.source_type == ""
        assert es.content == ""
        assert es.evidence_level == EvidenceLevel.NONE

    def test_full_creation_pdf(self):
        es = EvidenceSource(
            paper_id="paper123",
            source_type="PDF",
            content="Full text content...",
            evidence_level=EvidenceLevel.FULL_TEXT,
        )
        assert es.paper_id == "paper123"
        assert es.source_type == "PDF"
        assert es.content == "Full text content..."
        assert es.evidence_level == EvidenceLevel.FULL_TEXT

    def test_abstract_source(self):
        es = EvidenceSource(
            paper_id="paper456",
            source_type="ABSTRACT",
            content="Abstract content...",
            evidence_level=EvidenceLevel.ABSTRACT,
        )
        assert es.paper_id == "paper456"
        assert es.source_type == "ABSTRACT"
        assert es.evidence_level == EvidenceLevel.ABSTRACT

    def test_metadata_source(self):
        es = EvidenceSource(
            paper_id="paper789",
            source_type="METADATA",
            content="",
            evidence_level=EvidenceLevel.METADATA,
        )
        assert es.source_type == "METADATA"
        assert es.evidence_level == EvidenceLevel.METADATA


class TestClaimType:
    def test_enum_values(self):
        assert ClaimType.PAPER_DESCRIPTION.value == "paper_description"
        assert ClaimType.ARCHITECTURE.value == "architecture"
        assert ClaimType.TRAINING_DETAIL.value == "training_detail"
        assert ClaimType.BENCHMARK_RESULT.value == "benchmark_result"
        assert ClaimType.LIMITATION.value == "limitation"

    def test_min_evidence_level(self):
        assert MIN_EVIDENCE_LEVEL[ClaimType.PAPER_DESCRIPTION] == EvidenceLevel.ABSTRACT
        assert MIN_EVIDENCE_LEVEL[ClaimType.ARCHITECTURE] == EvidenceLevel.HTML
        assert MIN_EVIDENCE_LEVEL[ClaimType.TRAINING_DETAIL] == EvidenceLevel.FULL_TEXT
        assert MIN_EVIDENCE_LEVEL[ClaimType.BENCHMARK_RESULT] == EvidenceLevel.FULL_TEXT
        assert MIN_EVIDENCE_LEVEL[ClaimType.LIMITATION] == EvidenceLevel.ABSTRACT

    def test_min_level_contains_all_types(self):
        for ct in ClaimType:
            assert ct in MIN_EVIDENCE_LEVEL, f"Missing min level for {ct}"