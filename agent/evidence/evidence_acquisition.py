"""Evidence Acquisition Router for the evidence acquisition layer.

Responsible for deciding the best evidence source for each paper.
Tries sources in order: PDF → abstract → metadata.
Never falls back to unconstrained LLM generation.
"""

import logging
from typing import Optional

import requests

from agent.evidence.paper_types import (
    EvidenceLevel,
    EvidenceSource,
    PaperAvailability,
    PaperStatus,
)

logger = logging.getLogger(__name__)


class EvidenceAcquisitionRouter:
    """Routes evidence acquisition for a paper based on availability.

    Acquisition priority:
      1. PDF (FULL_TEXT) — if PDF URL is available
      2. ABSTRACT (ABSTRACT) — if abstract text is available
      3. METADATA (METADATA) — metadata only (bibliography use)
      4. NONE (NONE) — no evidence available

    PDF download failures are handled gracefully by falling back to
    the next available source. The pipeline never blocks on a single
    paper's PDF failure.
    """

    def acquire(
        self,
        paper: dict,
        availability: PaperAvailability,
    ) -> EvidenceSource:
        """Acquire the best available evidence for a paper.

        Args:
            paper: Paper metadata dict.
            availability: PaperAvailability from PaperValidator.

        Returns:
            EvidenceSource with the best available evidence.
        """
        if not paper or not availability.paper_id:
            return EvidenceSource(
                paper_id="",
                source_type="NONE",
                content="",
                evidence_level=EvidenceLevel.NONE,
            )

        paper_id = availability.paper_id

        # Withdrawn papers: no evidence acquisition possible
        if availability.status == PaperStatus.WITHDRAWN:
            logger.info(
                "[EVIDENCE_ACQUISITION] paper_id=%s source_attempted=NONE "
                "source_selected=NONE evidence_level=NONE reason=withdrawn",
                paper_id,
            )
            return EvidenceSource(
                paper_id=paper_id,
                source_type="NONE",
                content="",
                evidence_level=EvidenceLevel.NONE,
            )

        # 1. Try PDF
        if availability.fulltext_available:
            result = self._try_pdf(paper, availability)
            if result.evidence_level >= EvidenceLevel.FULL_TEXT:
                logger.info(
                    "[EVIDENCE_ACQUISITION] paper_id=%s source_attempted=PDF "
                    "source_selected=PDF evidence_level=FULL_TEXT",
                    paper_id,
                )
                return result

        # 2. Try abstract
        if availability.abstract_available:
            abstract = paper.get("abstract", "")
            if abstract and abstract.strip():
                logger.info(
                    "[EVIDENCE_ACQUISITION] paper_id=%s source_attempted=PDF "
                    "source_selected=ABSTRACT evidence_level=ABSTRACT",
                    paper_id,
                )
                return EvidenceSource(
                    paper_id=paper_id,
                    source_type="ABSTRACT",
                    content=abstract.strip(),
                    evidence_level=EvidenceLevel.ABSTRACT,
                )

        # 3. Metadata only
        if availability.metadata_available:
            logger.info(
                "[EVIDENCE_ACQUISITION] paper_id=%s source_attempted=PDF,ABSTRACT "
                "source_selected=METADATA evidence_level=METADATA",
                paper_id,
            )
            return EvidenceSource(
                paper_id=paper_id,
                source_type="METADATA",
                content="",
                evidence_level=EvidenceLevel.METADATA,
            )

        # 4. Nothing available
        logger.info(
            "[EVIDENCE_ACQUISITION] paper_id=%s source_attempted=PDF,ABSTRACT,METADATA "
            "source_selected=NONE evidence_level=NONE",
            paper_id,
        )
        return EvidenceSource(
            paper_id=paper_id,
            source_type="NONE",
            content="",
            evidence_level=EvidenceLevel.NONE,
        )

    def acquire_many(
        self,
        papers: list[dict],
        availabilities: list[PaperAvailability],
    ) -> list[EvidenceSource]:
        """Acquire evidence for multiple papers.

        Args:
            papers: List of paper metadata dicts.
            availabilities: List of PaperAvailability objects.

        Returns:
            List of EvidenceSource objects.
        """
        if not papers or not availabilities:
            return []

        # Zip by index, ignoring mismatched lengths
        results = []
        for i, paper in enumerate(papers):
            if i >= len(availabilities):
                break
            results.append(self.acquire(paper, availabilities[i]))
        return results

    # ------------------------------------------------------------------
    # PDF acquisition
    # ------------------------------------------------------------------

    def _try_pdf(
        self,
        paper: dict,
        availability: PaperAvailability,
    ) -> EvidenceSource:
        """Attempt to download a PDF.

        Args:
            paper: Paper metadata dict.
            availability: PaperAvailability (provides PDF URL).

        Returns:
            EvidenceSource with PDF content if successful, or
            EvidenceSource with lower level if download fails.
        """
        pdf_url = paper.get("pdf_url", "")
        arxiv_id = paper.get("arxiv_id", "")

        # Normalize URL
        if arxiv_id:
            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

        if not pdf_url:
            return EvidenceSource(
                paper_id=availability.paper_id,
                source_type="",
                content="",
                evidence_level=EvidenceLevel.NONE,
            )

        try:
            resp = requests.get(
                pdf_url,
                timeout=15,
                allow_redirects=True,
                headers={"User-Agent": "ScholarAgent/1.0"},
            )
            resp.raise_for_status()
            content = resp.content

            if isinstance(content, bytes):
                try:
                    content = content.decode("utf-8", errors="replace")
                except Exception:
                    content = str(content)

            return EvidenceSource(
                paper_id=availability.paper_id,
                source_type="PDF",
                content=content,
                evidence_level=EvidenceLevel.FULL_TEXT,
            )

        except requests.exceptions.Timeout as e:
            logger.warning(
                "PDF download timed out for %s: %s", pdf_url, e
            )
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response is not None else "unknown"
            logger.warning(
                "PDF download HTTP error for %s: HTTP %s", pdf_url, status_code,
            )
        except Exception as e:
            logger.warning(
                "PDF download failed for %s: %s", pdf_url, e,
            )

        # PDF failed — return empty source so caller falls back
        return EvidenceSource(
            paper_id=availability.paper_id,
            source_type="",
            content="",
            evidence_level=EvidenceLevel.NONE,
        )