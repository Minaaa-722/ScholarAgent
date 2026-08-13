"""Citation injector for deterministic post-processing.

Replaces ``[CITE:key]`` markers in the draft with LaTeX ``\\cite{}`` commands.
All citation formatting is handled programmatically — the LLM must never
generate raw ``\\cite{}``.
"""

import logging
import re

from agent.evidence.citation_store import CitationStore

logger = logging.getLogger(__name__)

# Regex to match [CITE:key] markers
_CITE_PATTERN = re.compile(r"\[CITE:([^\]]+)\]")

# Regex to match raw \cite{} (should not appear after injection)
_RAW_CITE_PATTERN = re.compile(r"\\cite\{[^}]*\}")


class CitationInjector:
    """Post-process prose: ``[CITE:key]`` → ``\\cite{key}`` with validation.

    Steps:
      1. Extract all ``[CITE:key]`` markers from the draft.
      2. Validate each key exists in ``CitationStore``.
      3. Replace: ``[CITE:key]`` → ``~\\cite{key}``.
      4. Log warnings for invalid keys (keep marker as-is for visibility).
      5. Return cleaned draft.

    Typical usage::

        injector = CitationInjector(citation_store)
        cleaned = injector.inject(draft)
        invalid = injector.validate_all(draft)
    """

    def __init__(self, citation_store: CitationStore) -> None:
        self._store = citation_store

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def inject(self, draft: str) -> str:
        """Replace all ``[CITE:key]`` markers with ``~\\cite{key}``.

        Args:
            draft: Draft text containing ``[CITE:key]`` markers.

        Returns:
            Draft with ``\\cite{}`` commands inserted.  Invalid keys are
            left as-is (``[CITE:INVALID_KEY]``) and a warning is logged.
        """
        if not draft:
            return draft

        def _replacer(match: re.Match) -> str:
            key = match.group(1).strip()
            entry = self._store.lookup_by_key(key)
            if not entry:
                logger.warning(
                    "Invalid citation key '[CITE:%s]' — keeping marker as-is", key
                )
                return match.group(0)  # keep original marker
            return f"~\\cite{{{key}}}"

        result = _CITE_PATTERN.sub(_replacer, draft)

        # Log a warning if raw \cite{} still exists (shouldn't happen, but
        # guards against LLM-generated \cite{} that bypassed the marker system)
        if _RAW_CITE_PATTERN.search(result):
            logger.warning(
                "Draft contains raw \\cite{} commands — these should have been "
                "[CITE:key] markers.  Consider re-running the injector."
            )

        return result

    def validate_all(self, draft: str) -> list[str]:
        """Extract and validate all citation keys in the draft.

        Returns:
            List of invalid keys (empty if all valid).
        """
        invalid: list[str] = []
        seen: set[str] = set()

        for match in _CITE_PATTERN.finditer(draft):
            key = match.group(1).strip()
            if key in seen:
                continue
            seen.add(key)

            if not self._store.lookup_by_key(key):
                invalid.append(key)

        return invalid

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def get_used_keys(self, draft: str) -> list[str]:
        """Extract all unique citation keys referenced in the draft.

        Returns:
            Sorted list of unique keys.
        """
        keys: set[str] = set()
        for match in _CITE_PATTERN.finditer(draft):
            keys.add(match.group(1).strip())
        return sorted(keys)

    def get_missing_keys(self, draft: str) -> list[str]:
        """Return citation keys referenced in the draft but not in the store.

        Returns:
            Sorted list of missing keys.
        """
        return sorted(
            k for k in self.get_used_keys(draft)
            if not self._store.lookup_by_key(k)
        )
