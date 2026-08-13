"""Citation store for the evidence grounding layer.

Single source of truth for all citation-related data.
Maintains paper_id ↔ citation_key ↔ BibTeX mappings with
model alias resolution for reverse lookups.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Common stop words to skip when extracting the first keyword from a title
# ---------------------------------------------------------------------------
_TITLE_STOP_WORDS: frozenset[str] = frozenset({
    "a", "an", "the", "on", "in", "at", "to", "for", "of", "by", "with",
    "and", "or", "but", "not", "from", "towards", "toward", "based",
    "using", "via", "learning", "deep", "large", "scaling", "efficient",
})


def _extract_first_keyword(title: str) -> str:
    """Extract the first significant keyword from a paper title.

    Skips common stop words and returns the first alphanumeric token
    that is substantive.  Returns an empty string if no keyword is found.
    """
    # Remove content in parentheses/brackets and split on whitespace/punctuation
    cleaned = re.sub(r"\([^)]*\)", "", title)
    cleaned = re.sub(r"\[[^\]]*\]", "", cleaned)
    tokens = re.split(r"[\s,;:\-–—/]+", cleaned)

    for token in tokens:
        token = token.strip().lower()
        # Remove leading/trailing non-alphanumeric characters
        token = re.sub(r"^[^a-zA-Z0-9]+|[^a-zA-Z0-9]+$", "", token)
        if token and token not in _TITLE_STOP_WORDS and len(token) >= 2:
            return token
    return ""


def _generate_bibtex_entry(
    citation_key: str,
    title: str,
    authors: list[str],
    year: int,
    venue: str,
    arxiv_id: str,
) -> str:
    """Generate a BibTeX entry string for a paper.

    Produces ``@article`` for published papers and ``@misc`` for arXiv
    preprints, both compatible with IEEEtran / ieeenat bibliography styles.
    """
    # Format authors
    author_str = " and ".join(authors) if authors else "Unknown"

    # Escape special LaTeX characters in title
    safe_title = title.replace("&", "\\&").replace("%", "\\%").replace("#", "\\#")

    if venue and venue.lower() not in ("", "arxiv", "unknown"):
        entry_type = "article"
        journal = venue
        extra = f"  journal = {{{journal}}},\n"
    else:
        entry_type = "misc"
        extra = ""
        if arxiv_id:
            extra += f"  eprint = {{{arxiv_id}}},\n"
            extra += '  archivePrefix = {arXiv},\n'

    entry = (
        f"@{entry_type}{{{citation_key},\n"
        f"  author = {{{author_str}}},\n"
        f"  title = {{{safe_title}}},\n"
        f"  year = {{{year}}},\n"
        f"{extra}"
        f"}}"
    )
    return entry


def _extract_model_name_from_title(title: str) -> Optional[str]:
    """Extract a model name from the paper title prefix.

    Handles patterns like:
      "Qwen2-VL: Better Vision-Language Model" → "Qwen2-VL"
      "LLaVA-NeXT: Improved Reasoning" → "LLaVA-NeXT"
      "CLIP: Learning Transferable Visual Models" → "CLIP"

    Returns None if no clear model name prefix is found.
    """
    if ":" not in title:
        return None

    prefix = title.split(":", 1)[0].strip()
    # Require at least 2 characters and no common English phrases
    if len(prefix) < 2:
        return None
    lower = prefix.lower()
    if lower in _TITLE_STOP_WORDS or any(
        lower.startswith(w) for w in ("a ", "an ", "the ")
    ):
        return None
    # Check it looks like a model/system name (contains uppercase or hyphen)
    if re.search(r"[A-Z]", prefix) or "-" in prefix:
        return prefix
    return None


# ---------------------------------------------------------------------------
# CitationEntry
# ---------------------------------------------------------------------------

@dataclass
class CitationEntry:
    """A single citation record linking a paper to its BibTeX key.

    Attributes:
        citation_key: BibTeX citation key (e.g., "wang2024qwen2").
        paper_id: Paper identifier (matches ``EvidenceReference.paper_id``).
        bibtex_entry: Full BibTeX entry string.
        title: Paper title.
        authors: List of author names.
        year: Publication year.
        venue: Publication venue or journal (empty string if unknown).
        model_names: Model names mentioned in the paper (alias index).
    """

    citation_key: str
    paper_id: str
    bibtex_entry: str
    title: str
    authors: list[str] = field(default_factory=list)
    year: int = 0
    venue: str = ""
    model_names: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# CitationStore
# ---------------------------------------------------------------------------

class CitationStore:
    """Single source of truth for citation data.

    Maintains three indexes:
      - ``paper_id → CitationEntry``
      - ``citation_key → CitationEntry``
      - ``model_name → list[paper_id]`` (alias resolution)

    Typical usage::

        store = CitationStore()
        key = store.register(paper_dict)
        entry = store.lookup_by_key(key)
        bib = store.generate_references_bib()
    """

    def __init__(self) -> None:
        self._by_paper_id: dict[str, CitationEntry] = {}
        self._by_key: dict[str, CitationEntry] = {}
        self._model_alias: dict[str, list[str]] = {}  # model_name_lower → [paper_id, ...]

    # ------------------------------------------------------------------
    # Register
    # ------------------------------------------------------------------

    def register(
        self,
        paper: dict,
        model_names: Optional[list[str]] = None,
    ) -> str:
        """Register a paper dict from the RETRIEVAL stage.

        Generates a unique citation key, builds the BibTeX entry, and
        populates all three indexes.  Model names are extracted from
        both the title (heuristic) and the optional ``model_names``
        parameter.

        Args:
            paper: Paper dict with keys ``title``, ``authors``, ``year``,
                   ``arxiv_id``, ``venue`` / ``journal`` (optional).
            model_names: Optional list of model names from
                         ``PaperKnowledgeBase`` analysis.

        Returns:
            The generated citation_key.

        Raises:
            ValueError: If the paper dict lacks ``title``, ``authors``,
                        or ``year``.
        """
        title = (paper.get("title") or "").strip()
        authors = paper.get("authors") or []
        year = paper.get("year") or 0

        if not title:
            raise ValueError("Paper dict must have a non-empty 'title'")
        if not authors:
            raise ValueError("Paper dict must have a non-empty 'authors' list")
        if not year:
            raise ValueError("Paper dict must have a non-zero 'year'")

        # Resolve paper_id
        paper_id = paper.get("arxiv_id") or paper.get("paper_id", "")
        if not paper_id:
            # Fallback: generate a stable ID from title
            safe = re.sub(r"[^a-zA-Z0-9]", "", title.lower())[:40]
            paper_id = f"paper_{safe}"

        # Generate citation key
        citation_key = self._generate_key(title, authors, year)

        # Build BibTeX entry
        venue = paper.get("venue") or paper.get("journal", "")
        arxiv_id = paper.get("arxiv_id", "")
        bibtex_entry = _generate_bibtex_entry(
            citation_key, title, authors, year, venue, arxiv_id,
        )

        # Collect model names
        all_model_names: list[str] = list(model_names or [])
        title_model = _extract_model_name_from_title(title)
        if title_model and title_model not in all_model_names:
            all_model_names.append(title_model)

        # Build entry
        entry = CitationEntry(
            citation_key=citation_key,
            paper_id=paper_id,
            bibtex_entry=bibtex_entry,
            title=title,
            authors=authors,
            year=year,
            venue=venue,
            model_names=all_model_names,
        )

        # Store in indexes
        self._by_paper_id[paper_id] = entry
        self._by_key[citation_key] = entry

        for mn in all_model_names:
            key = mn.lower()
            if key not in self._model_alias:
                self._model_alias[key] = []
            if paper_id not in self._model_alias[key]:
                self._model_alias[key].append(paper_id)

        logger.info(
            "Registered citation key '%s' for paper '%s' (paper_id=%s)",
            citation_key, title[:60], paper_id,
        )
        return citation_key

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def lookup_by_key(self, key: str) -> Optional[CitationEntry]:
        """Look up a citation entry by its BibTeX key.

        Returns None if the key is not registered.
        """
        return self._by_key.get(key)

    def lookup_by_paper_id(self, paper_id: str) -> Optional[CitationEntry]:
        """Look up a citation entry by its paper_id.

        Returns None if the paper_id is not registered.
        """
        return self._by_paper_id.get(paper_id)

    def lookup_by_model(self, model_name: str) -> list[CitationEntry]:
        """Resolve a model name to its citation entries.

        A single model name may map to multiple papers (e.g., technical
        report and a follow-up).  Returns an empty list if no match is
        found.
        """
        key = model_name.strip().lower()
        paper_ids = self._model_alias.get(key, [])
        return [self._by_paper_id[pid] for pid in paper_ids if pid in self._by_paper_id]

    # ------------------------------------------------------------------
    # Bulk access
    # ------------------------------------------------------------------

    def get_all_keys(self) -> list[str]:
        """Return all registered citation keys (for validation)."""
        return list(self._by_key.keys())

    def get_all_entries(self) -> list[CitationEntry]:
        """Return all registered citation entries."""
        return list(self._by_key.values())

    def entry_count(self) -> int:
        """Return the number of registered entries."""
        return len(self._by_key)

    # ------------------------------------------------------------------
    # BibTeX generation
    # ------------------------------------------------------------------

    def generate_references_bib(self) -> str:
        """Generate the complete ``references.bib`` content.

        Entries are sorted alphabetically by citation_key.  Returns an
        empty string if no entries are registered.
        """
        if not self._by_key:
            return ""

        sorted_keys = sorted(self._by_key.keys())
        entries = [self._by_key[k].bibtex_entry for k in sorted_keys]
        return "\n\n".join(entries) + "\n"

    # ------------------------------------------------------------------
    # Clear
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """Reset the store (remove all entries)."""
        self._by_paper_id.clear()
        self._by_key.clear()
        self._model_alias.clear()

    # ------------------------------------------------------------------
    # Key generation (internal)
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_author_surname(authors: list[str]) -> str:
        """Extract the first author's surname, ASCII-safe and lowercased."""
        if not authors:
            return "unknown"
        surname = authors[0].strip().split()[-1]
        # Remove non-alpha characters
        surname = re.sub(r"[^a-zA-Z]", "", surname)
        return surname.lower() or "unknown"

    def _generate_key(self, title: str, authors: list[str], year: int) -> str:
        """Generate a unique citation key.

        Format: ``{first_author_surname}{year}{first_keyword}``

        Collision handling: if the key already exists, append a suffix
        ``a``, ``b``, ``c``, ... until a unique key is found.
        """
        surname = self._extract_author_surname(authors)
        year_str = str(year)
        keyword = _extract_first_keyword(title)

        if not keyword:
            keyword = "paper"

        base = f"{surname}{year_str}{keyword}"
        candidate = base
        suffix = ord("a")

        while candidate in self._by_key:
            candidate = f"{base}{chr(suffix)}"
            suffix += 1
            if suffix > ord("z"):
                # Extremely unlikely, but handle gracefully
                candidate = f"{base}_{suffix}"

        return candidate
