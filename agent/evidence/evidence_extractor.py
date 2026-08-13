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

# System prompt for the LLM evidence extraction (single paper)
_EVIDENCE_SYSTEM_PROMPT = (
    "You are an evidence extraction assistant. "
    "Given text chunks from a research paper, "
    "extract evidence references that support claims about the paper.\n\n"
    "For each piece of evidence, output a JSON object with:\n"
    '- "excerpt": The exact text serving as evidence (copy verbatim from the chunk)\n'
    '- "category": One of: architecture, benchmark, dataset, training, limitation\n'
    '- "page_number": The page number the evidence appears on (integer)\n'
    '- "section": The section heading where the evidence appears (string)\n'
    '- "source_type": "text", "table", or "figure"\n'
    '- "table_id": The table/figure identifier if source_type is table or figure, '
    'otherwise ""\n\n'
    "Respond with a JSON array of evidence objects. "
    "If no evidence is found, respond with an empty array [].\n\n"
    "Categories:\n"
    "- architecture: model architecture, components, layers, modules\n"
    "- benchmark: evaluation results, scores, comparisons\n"
    "- dataset: dataset descriptions, statistics, collection methods\n"
    "- training: training procedures, hyperparameters, optimization\n"
    "- limitation: limitations, drawbacks, failure cases"
)

# System prompt for batch extraction (multiple papers)
_BATCH_EVIDENCE_SYSTEM_PROMPT = (
    "You are an evidence extraction assistant. "
    "Given text chunks from multiple research papers, "
    "extract evidence references that support claims about the papers.\n\n"
    "Each chunk is tagged with [Paper: paper_id] to identify its source paper.\n\n"
    "For each piece of evidence, output a JSON object with:\n"
    '- "paper_id": The paper_id of the source paper '
    "(must match one of the paper_ids in the input tags)\n"
    '- "excerpt": The exact text serving as evidence (copy verbatim from the chunk)\n'
    '- "category": One of: architecture, benchmark, dataset, training, limitation\n'
    '- "page_number": The page number the evidence appears on (integer)\n'
    '- "section": The section heading where the evidence appears (string)\n'
    '- "source_type": "text", "table", or "figure"\n'
    '- "table_id": The table/figure identifier if source_type is table or figure, '
    'otherwise ""\n\n'
    "Respond with a JSON array of evidence objects. "
    "If no evidence is found, respond with an empty array [].\n\n"
    "Categories:\n"
    "- architecture: model architecture, components, layers, modules\n"
    "- benchmark: evaluation results, scores, comparisons\n"
    "- dataset: dataset descriptions, statistics, collection methods\n"
    "- training: training procedures, hyperparameters, optimization\n"
    "- limitation: limitations, drawbacks, failure cases"
)


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
    them to the LLM for extraction. Supports both single-paper and
    batch (multi-paper) extraction.
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
    # Batch extraction (multiple papers, single LLM call)
    # ------------------------------------------------------------------

    def extract_batch(
        self,
        paper_chunks: dict[str, list[PDFChunk]],
        batch_size: int = 5,
    ) -> dict[str, list[EvidenceReference]]:
        """Extract evidence from multiple papers in batches.

        Processes papers in batches of `batch_size`, each batch using a
        single LLM call.  Reduces N LLM calls to ceil(N / batch_size).

        Args:
            paper_chunks: dict mapping paper_id -> list of PDFChunks.
            batch_size: Number of papers per LLM call (default 5).

        Returns:
            dict mapping paper_id -> list of extracted EvidenceReference objects.
        """
        if not paper_chunks:
            return {}

        paper_ids = list(paper_chunks.keys())
        result: dict[str, list[EvidenceReference]] = {pid: [] for pid in paper_ids}

        # Process in batches
        for batch_start in range(0, len(paper_ids), batch_size):
            batch_ids = paper_ids[batch_start:batch_start + batch_size]
            batch_chunks = {pid: paper_chunks[pid] for pid in batch_ids}

            try:
                batch_result = self._extract_batch_single(batch_chunks)
                for pid, refs in batch_result.items():
                    result[pid] = refs
            except Exception as e:
                logger.warning("Batch evidence extraction failed for batch %s: %s", batch_ids, e)

        return result

    def _extract_batch_single(
        self,
        paper_chunks: dict[str, list[PDFChunk]],
    ) -> dict[str, list[EvidenceReference]]:
        """Run a single batch LLM call for a group of papers."""
        all_chunk_texts = []
        for paper_id, chunks in paper_chunks.items():
            # Filter chunks per paper
            filtered_ids: set[str] = set()
            for category in EVIDENCE_CATEGORIES:
                for c in self._chunk_filter.filter(chunks, category):
                    filtered_ids.add(c.chunk_id)

            chunks_to_process = [c for c in chunks if c.chunk_id in filtered_ids]
            if not chunks_to_process:
                chunks_to_process = chunks  # fallback

            chunk_texts = []
            for c in chunks_to_process:
                chunk_texts.append(
                    f"[Paper: {paper_id} | Page {c.page_number} | Section: {c.section or '(unknown)'}]\n"
                    f"{c.content[:2000]}"
                )
            all_chunk_texts.append("\n\n".join(chunk_texts))

        user_message = "\n\n=======\n\n".join(all_chunk_texts)

        response = self._llm.generate(
            system_prompt=_BATCH_EVIDENCE_SYSTEM_PROMPT,
            user_message=user_message,
        )

        return self._parse_batch_response(response.text, paper_chunks)

    def _parse_batch_response(
        self,
        text: str,
        paper_chunks: dict[str, list[PDFChunk]],
    ) -> dict[str, list[EvidenceReference]]:
        """Parse LLM batch response into per-paper EvidenceReference lists."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning("Failed to parse batch evidence JSON: %.200s", text)
            return {pid: [] for pid in paper_chunks}

        if not isinstance(data, list):
            return {pid: [] for pid in paper_chunks}

        # Group by paper_id
        raw_by_paper: dict[str, list[dict]] = {}
        for item in data:
            if not isinstance(item, dict):
                continue
            pid = item.get("paper_id", "")
            if not pid or pid not in paper_chunks:
                continue
            raw_by_paper.setdefault(pid, []).append(item)

        # Build EvidenceReference objects per paper and validate
        validator = EvidenceReferenceValidator()
        result: dict[str, list[EvidenceReference]] = {}
        for pid, items in raw_by_paper.items():
            chunks = paper_chunks.get(pid, [])
            refs: list[EvidenceReference] = []
            for item in items:
                ref = EvidenceReference(
                    paper_id=pid,
                    page_number=item.get("page_number", -1),
                    section=item.get("section", ""),
                    source_type=item.get("source_type", "text"),
                    table_id=item.get("table_id", ""),
                    excerpt=item.get("excerpt", ""),
                )
                refs.append(ref)
            refs = validator.validate_all(refs, chunks)
            result[pid] = refs

        # Ensure all paper_ids are present
        for pid in paper_chunks:
            if pid not in result:
                result[pid] = []

        logger.info(
            "Batch parsed: %d papers, %d total refs",
            len(result), sum(len(r) for r in result.values()),
        )
        return result

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
