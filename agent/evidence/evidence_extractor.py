"""Evidence extraction and validation for the evidence grounding layer.

Provides EvidenceReferenceValidator for validating evidence references
against source PDF chunks, and EvidenceExtractor for using an LLM to
extract evidence references from chunks.
"""

import json
import logging
import re
from typing import Optional

from agent.core.llm import LLMBase
from agent.evidence.evidence_reference import EvidenceReference
from agent.evidence.pdf_parser import ChunkFilter, PDFChunk

logger = logging.getLogger(__name__)

# Evidence categories the extractor can produce
EVIDENCE_CATEGORIES = [
    "architecture", "benchmark", "dataset", "training", "limitation",
]

# System prompt for the LLM evidence extraction
_EVIDENCE_SYSTEM_PROMPT = """You are an evidence extraction assistant. Given text chunks from a research paper, extract evidence references that support claims about the paper.

For each piece of evidence, output a JSON object with:
- "excerpt": The exact text serving as evidence (copy verbatim from the chunk)
- "category": One of: architecture, benchmark, dataset, training, limitation
- "page_number": The page number the evidence appears on (integer)
- "section": The section heading where the evidence appears (string)
- "source_type": "text", "table", or "figure"
- "table_id": The table/figure identifier if source_type is table or figure, otherwise ""

Respond with a JSON array of evidence objects. If no evidence is found, respond with an empty array [].

Categories:
- architecture: model architecture, components, layers, modules
- benchmark: evaluation results, scores, comparisons
- dataset: dataset descriptions, statistics, collection methods
- training: training procedures, hyperparameters, optimization
- limitation: limitations, drawbacks, failure cases"""


class EvidenceReferenceValidator:
    """Validate evidence references against source PDF chunks."""

    def validate(
        self,
        ref: EvidenceReference,
        chunks: list[PDFChunk],
    ) -> bool:
        """Validate a single evidence reference against source chunks.

        Rules:
        1. Excerpt must be a substring of at least one chunk (whitespace-normalized).
        2. page_number must be valid for the paper (-1 is allowed for unknown).
        3. Source type consistency: "table" requires non-empty table_id;
           "figure" requires non-empty table_id.

        Args:
            ref: The evidence reference to validate.
            chunks: Source PDF chunks to validate against.

        Returns:
            True if the reference passes all validation rules.
        """
        # Rule 1: excerpt must exist in at least one chunk
        if not self._excerpt_in_chunks(ref.excerpt, chunks):
            logger.debug("Excerpt not found in any chunk: %s", ref.excerpt[:50])
            return False

        # Rule 2: page_number must be valid (allow -1 for unknown)
        if ref.page_number != -1:
            valid_pages = {c.page_number for c in chunks}
            if ref.page_number not in valid_pages:
                logger.debug(
                    "Page number %d not in valid pages %s",
                    ref.page_number, valid_pages,
                )
                return False

        # Rule 3: source type consistency
        if ref.source_type == "table" and not ref.table_id:
            logger.debug("Table source type requires non-empty table_id")
            return False
        if ref.source_type == "figure" and not ref.table_id:
            logger.debug("Figure source type requires non-empty table_id")
            return False

        return True

    def validate_all(
        self,
        refs: list[EvidenceReference],
        chunks: list[PDFChunk],
    ) -> list[EvidenceReference]:
        """Validate all references and return only valid ones.

        Args:
            refs: List of evidence references to validate.
            chunks: Source PDF chunks to validate against.

        Returns:
            List of references that passed validation.
        """
        return [ref for ref in refs if self.validate(ref, chunks)]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _excerpt_in_chunks(excerpt: str, chunks: list[PDFChunk]) -> bool:
        """Check if excerpt (whitespace-normalized) appears in any chunk."""
        if not excerpt:
            return False

        normalized = re.sub(r"\s+", " ", excerpt).strip()
        for chunk in chunks:
            chunk_normalized = re.sub(r"\s+", " ", chunk.content).strip()
            if normalized in chunk_normalized:
                return True
        return False


class EvidenceExtractor:
    """Extract evidence references from PDF chunks using an LLM.

    Uses ChunkFilter to pre-filter chunks by category before sending
    them to the LLM for extraction.
    """

    def __init__(
        self,
        llm: LLMBase,
        chunk_filter: Optional[ChunkFilter] = None,
    ):
        self._llm = llm
        self._chunk_filter = chunk_filter or ChunkFilter()

    def extract(self, chunks: list[PDFChunk]) -> list[EvidenceReference]:
        """Extract evidence references from PDF chunks.

        Pre-filters chunks using ChunkFilter for each evidence category,
        then sends the filtered chunks to the LLM for extraction.

        Args:
            chunks: PDF chunks to extract evidence from.

        Returns:
            List of extracted and validated EvidenceReference objects.
        """
        if not chunks:
            return []

        # Collect all filtered chunks across categories
        filtered_chunks: set[str] = set()
        for category in EVIDENCE_CATEGORIES:
            for c in self._chunk_filter.filter(chunks, category):
                filtered_chunks.add(c.chunk_id)

        # Build the user message from filtered chunks
        chunks_to_process = [c for c in chunks if c.chunk_id in filtered_chunks]
        if not chunks_to_process:
            chunks_to_process = chunks  # fallback: use all chunks

        # Group chunks into a text block for the LLM
        chunk_texts = []
        for c in chunks_to_process:
            chunk_texts.append(
                f"[Page {c.page_number} | Section: {c.section or '(unknown)'}]\n"
                f"{c.content}"
            )

        user_message = "\n\n---\n\n".join(chunk_texts)

        try:
            response = self._llm.generate(
                system_prompt=_EVIDENCE_SYSTEM_PROMPT,
                user_message=user_message,
            )
        except Exception as e:
            logger.warning("LLM evidence extraction failed: %s", e)
            return []

        refs = self._parse_response(response.text, chunks)
        return refs

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_response(
        self,
        text: str,
        chunks: list[PDFChunk],
    ) -> list[EvidenceReference]:
        """Parse LLM response JSON into validated EvidenceReference objects."""
        # Strip markdown fences
        cleaned = text.strip()
        if cleaned.startswith("```"):
            # Remove opening fence (possibly with "json")
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            # Remove closing fence
            cleaned = re.sub(r"\s*```$", "", cleaned)

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning("Failed to parse LLM response as JSON: %.200s", text)
            return []

        if not isinstance(data, list):
            logger.warning("LLM response is not a JSON array: %s", type(data))
            return []

        refs: list[EvidenceReference] = []
        for item in data:
            if not isinstance(item, dict):
                continue

            excerpt = item.get("excerpt", "")
            category = item.get("category", "")
            page_number = item.get("page_number", -1)
            section = item.get("section", "")
            source_type = item.get("source_type", "text")
            table_id = item.get("table_id", "")

            ref = EvidenceReference(
                paper_id=chunks[0].paper_id if chunks else "",
                page_number=page_number,
                section=section,
                source_type=source_type,
                table_id=table_id,
                excerpt=excerpt,
            )
            refs.append(ref)

        # Validate against source chunks
        validator = EvidenceReferenceValidator()
        refs = validator.validate_all(refs, chunks)

        return refs