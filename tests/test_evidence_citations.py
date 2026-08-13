"""Tests for CitationStore, CitationAnchorStore, CitationInjector, and BenchmarkTableGenerator.

Covers:
  - CitationStore: register, lookup, key generation, collision handling, bulk access, clear
  - CitationAnchorStore: build, query, get_evidence_map, clear, edge cases
  - CitationInjector: inject [CITE:key] markers, validate, missing keys, helper methods
  - BenchmarkTableGenerator: generate_benchmark_table, generate_summary_table, replace_tables
  - Edge cases: empty inputs, missing fields, invalid keys, None values
"""
import pytest
from agent.evidence.citation_store import (
    CitationStore, CitationEntry, _extract_first_keyword,
    _extract_model_name_from_title,
)
from agent.evidence.citation_anchor_store import CitationAnchor, CitationAnchorStore
from agent.evidence.citation_injector import CitationInjector
from agent.evidence.evidence_store import Claim
from agent.evidence.evidence_reference import KnowledgeField
from agent.evidence.benchmark_store import BenchmarkRecord, BenchmarkStore
from agent.evidence.paper_knowledge import (
    ArchitectureKnowledge, PaperKnowledge, PaperKnowledgeBase,
)
from agent.evidence.table_generator import BenchmarkTableGenerator, _parse_score


# =========================================================================
# CitationStore
# =========================================================================

class TestCitationStore:
    """Test CitationStore: register, lookup, key generation, bulk access, clear."""

    def _make_paper(self, **overrides) -> dict:
        defaults = {
            "title": "Qwen2-VL: Better Vision-Language Model",
            "authors": ["Wang", "Zhang", "Li"],
            "year": 2024,
            "arxiv_id": "2405.12345",
            "venue": "arXiv",
        }
        defaults.update(overrides)
        return defaults

    # --- Register ---

    def test_register_minimal(self):
        store = CitationStore()
        key = store.register(self._make_paper())
        assert key.startswith("wang2024qwen2")
        assert store.entry_count() == 1

    def test_register_returns_key(self):
        store = CitationStore()
        key = store.register(self._make_paper())
        entry = store.lookup_by_key(key)
        assert entry is not None
        assert entry.citation_key == key
        assert entry.title == "Qwen2-VL: Better Vision-Language Model"
        assert entry.authors == ["Wang", "Zhang", "Li"]
        assert entry.year == 2024

    def test_register_multiple_entries(self):
        store = CitationStore()
        k1 = store.register(self._make_paper(title="Paper A", authors=["Smith"], year=2023, arxiv_id="2301.1"))
        k2 = store.register(self._make_paper(title="Paper B", authors=["Jones"], year=2024, arxiv_id="2401.1"))
        assert store.entry_count() == 2
        assert k1 != k2

    def test_register_with_model_names(self):
        store = CitationStore()
        key = store.register(self._make_paper(), model_names=["qwen2-vl"])
        entries = store.lookup_by_model("qwen2-vl")
        assert len(entries) == 1
        assert entries[0].citation_key == key

    def test_register_with_venue(self):
        store = CitationStore()
        key = store.register(self._make_paper(venue="ICLR", journal="ICLR"))
        entry = store.lookup_by_key(key)
        assert entry.venue == "ICLR"

    # --- Register error cases ---

    def test_register_missing_title_raises(self):
        store = CitationStore()
        with pytest.raises(ValueError, match="title"):
            store.register(self._make_paper(title=""))

    def test_register_missing_authors_raises(self):
        store = CitationStore()
        with pytest.raises(ValueError, match="authors"):
            store.register(self._make_paper(authors=[]))

    def test_register_missing_year_raises(self):
        store = CitationStore()
        with pytest.raises(ValueError, match="year"):
            store.register(self._make_paper(year=0))

    def test_register_fallback_paper_id(self):
        store = CitationStore()
        key = store.register(self._make_paper(arxiv_id="", paper_id=""))
        # Should generate a fallback paper_id from the title
        entry = store.lookup_by_key(key)
        assert entry.paper_id.startswith("paper_")

    # --- Key collision handling ---

    def test_register_collision_appends_suffix(self):
        store = CitationStore()
        # Same title and authors → same base key → collision handling
        k1 = store.register(self._make_paper(title="Test Paper", authors=["Zhang"], year=2024, arxiv_id="2401.1"))
        k2 = store.register(self._make_paper(title="Test Paper", authors=["Zhang"], year=2024, arxiv_id="2401.2"))
        assert k1 != k2
        assert k2.endswith("a") or len(k2) > len(k1)

    # --- Lookup ---

    def test_lookup_by_key_exists(self):
        store = CitationStore()
        key = store.register(self._make_paper())
        entry = store.lookup_by_key(key)
        assert isinstance(entry, CitationEntry)
        assert entry.citation_key == key

    def test_lookup_by_key_missing(self):
        store = CitationStore()
        assert store.lookup_by_key("nonexistent") is None

    def test_lookup_by_key_empty_string(self):
        store = CitationStore()
        assert store.lookup_by_key("") is None

    def test_lookup_by_paper_id_exists(self):
        store = CitationStore()
        store.register(self._make_paper(arxiv_id="2405.12345"))
        entry = store.lookup_by_paper_id("2405.12345")
        assert entry is not None
        assert entry.paper_id == "2405.12345"

    def test_lookup_by_paper_id_missing(self):
        store = CitationStore()
        assert store.lookup_by_paper_id("nonexistent") is None

    def test_lookup_by_model_empty(self):
        store = CitationStore()
        results = store.lookup_by_model("nonexistent_model")
        assert results == []

    def test_lookup_by_model_case_insensitive(self):
        store = CitationStore()
        store.register(self._make_paper(), model_names=["Qwen2-VL"])
        results = store.lookup_by_model("qwen2-vl")
        assert len(results) == 1
        results = store.lookup_by_model("QWEN2-VL")
        assert len(results) == 1

    # --- Bulk access ---

    def test_get_all_keys(self):
        store = CitationStore()
        k1 = store.register(self._make_paper(title="Paper A", authors=["Smith"], year=2023, arxiv_id="2301.1"))
        k2 = store.register(self._make_paper(title="Paper B", authors=["Jones"], year=2024, arxiv_id="2401.1"))
        keys = store.get_all_keys()
        assert len(keys) == 2
        assert k1 in keys
        assert k2 in keys

    def test_get_all_entries(self):
        store = CitationStore()
        store.register(self._make_paper())
        entries = store.get_all_entries()
        assert len(entries) == 1
        assert isinstance(entries[0], CitationEntry)

    def test_entry_count_empty(self):
        store = CitationStore()
        assert store.entry_count() == 0

    def test_entry_count_after_register(self):
        store = CitationStore()
        store.register(self._make_paper())
        assert store.entry_count() == 1

    # --- BibTeX generation ---

    def test_generate_references_bib_empty(self):
        store = CitationStore()
        assert store.generate_references_bib() == ""

    def test_generate_references_bib(self):
        store = CitationStore()
        store.register(self._make_paper())
        bib = store.generate_references_bib()
        assert bib.startswith("@")
        assert "wang2024qwen2" in bib
        assert bib.endswith("\n")

    # --- Clear ---

    def test_clear(self):
        store = CitationStore()
        store.register(self._make_paper())
        store.clear()
        assert store.entry_count() == 0
        assert store.get_all_keys() == []

    def test_clear_and_reregister(self):
        store = CitationStore()
        store.register(self._make_paper(arxiv_id="2405.1"))
        store.clear()
        key = store.register(self._make_paper(arxiv_id="2405.2"))
        assert store.entry_count() == 1
        entry = store.lookup_by_key(key)
        assert entry.paper_id == "2405.2"


# =========================================================================
# CitationAnchorStore
# =========================================================================

class TestCitationAnchorStore:
    """Test CitationAnchorStore: build, query, evidence map, clear, edge cases."""

    @pytest.fixture
    def store(self):
        return CitationAnchorStore()

    @pytest.fixture
    def citation_store(self):
        cs = CitationStore()
        cs.register({
            "title": "Qwen2-VL: Better Vision-Language Model",
            "authors": ["Wang"],
            "year": 2024,
            "arxiv_id": "qwen2024",
        })
        return cs

    @pytest.fixture
    def sample_claims(self):
        return [
            Claim(claim="Qwen2-VL uses dynamic resolution", category="architecture",
                  paper_id="qwen2024", confidence=0.9, source_excerpt="Dynamic resolution enables..."),
            Claim(claim="MMLU benchmark results", category="benchmark",
                  paper_id="qwen2024", confidence=0.8),
        ]

    def test_build_creates_anchors(self, store, citation_store, sample_claims):
        store.build(sample_claims, citation_store)
        anchors = store.get_anchors()
        assert len(anchors) == 2
        assert all(isinstance(a, CitationAnchor) for a in anchors)

    def test_build_anchor_fields(self, store, citation_store, sample_claims):
        store.build(sample_claims, citation_store)
        anchor = store.get_anchor_for_claim("Qwen2-VL uses dynamic resolution")
        assert anchor is not None
        assert anchor.claim_text == "Qwen2-VL uses dynamic resolution"
        assert anchor.category == "architecture"
        assert anchor.paper_id == "qwen2024"
        assert anchor.citation_key is not None
        assert anchor.confidence == 0.9
        assert anchor.evidence_excerpt == "Dynamic resolution enables..."

    def test_build_empty_claims(self, store, citation_store):
        store.build([], citation_store)
        assert store.anchor_count() == 0

    def test_build_claim_without_paper_id(self, store, citation_store):
        claims = [Claim(claim="No paper", category="architecture", paper_id="")]
        store.build(claims, citation_store)
        # Claim without paper_id should be skipped
        assert store.anchor_count() == 0

    def test_build_claim_unresolved_paper_id(self, store, citation_store):
        claims = [Claim(claim="Unknown paper", category="architecture", paper_id="nonexistent")]
        store.build(claims, citation_store)
        # Unresolved paper_id should be skipped
        assert store.anchor_count() == 0

    def test_build_multiple_claims_same_paper(self, store, citation_store):
        claims = [
            Claim(claim="Claim 1", category="architecture", paper_id="qwen2024"),
            Claim(claim="Claim 2", category="benchmark", paper_id="qwen2024"),
        ]
        store.build(claims, citation_store)
        assert store.anchor_count() == 2

    # --- Query methods ---

    def test_get_anchors_by_category(self, store, citation_store, sample_claims):
        store.build(sample_claims, citation_store)
        arch_anchors = store.get_anchors_by_category("architecture")
        assert len(arch_anchors) == 1
        assert arch_anchors[0].category == "architecture"

    def test_get_anchors_by_category_empty(self, store, citation_store, sample_claims):
        store.build(sample_claims, citation_store)
        empty = store.get_anchors_by_category("dataset")
        assert empty == []

    def test_get_anchors_by_category_no_match(self, store):
        assert store.get_anchors_by_category("architecture") == []

    def test_get_anchor_for_claim_case_insensitive(self, store, citation_store, sample_claims):
        store.build(sample_claims, citation_store)
        anchor = store.get_anchor_for_claim("qwen2-vl uses dynamic resolution")
        assert anchor is not None

    def test_get_anchor_for_claim_missing(self, store, citation_store, sample_claims):
        store.build(sample_claims, citation_store)
        assert store.get_anchor_for_claim("nonexistent claim") is None

    def test_get_anchor_for_claim_empty(self, store):
        assert store.get_anchor_for_claim("") is None

    # --- Evidence map ---

    def test_evidence_map(self, store, citation_store, sample_claims):
        store.build(sample_claims, citation_store)
        ev_map = store.get_evidence_map()
        assert len(ev_map) == 2
        key = "qwen2-vl uses dynamic resolution"
        assert key in ev_map
        assert len(ev_map[key]) >= 1

    def test_evidence_map_empty(self, store):
        assert store.get_evidence_map() == {}

    # --- Clear ---

    def test_clear(self, store, citation_store, sample_claims):
        store.build(sample_claims, citation_store)
        store.clear()
        assert store.anchor_count() == 0
        assert store.get_evidence_map() == {}

    def test_build_after_clear(self, store, citation_store, sample_claims):
        store.build(sample_claims, citation_store)
        store.clear()
        store.build(sample_claims[:1], citation_store)
        assert store.anchor_count() == 1


# =========================================================================
# CitationInjector
# =========================================================================

class TestCitationInjector:
    """Test CitationInjector: inject, validate, helper methods, edge cases."""

    @pytest.fixture
    def citation_store(self):
        cs = CitationStore()
        cs.register({
            "title": "Qwen2-VL: Better Vision-Language Model",
            "authors": ["Wang"],
            "year": 2024,
            "arxiv_id": "qwen2024",
        })
        cs.register({
            "title": "LLaVA-NeXT: Improved Reasoning",
            "authors": ["Li"],
            "year": 2024,
            "arxiv_id": "llava2024",
        })
        return cs

    @pytest.fixture
    def injector(self, citation_store):
        return CitationInjector(citation_store)

    # --- inject ---

    def test_inject_single_cite(self, injector):
        result = injector.inject("Qwen2-VL achieves SOTA [CITE:wang2024qwen2].")
        assert "~\\cite{wang2024qwen2}" in result
        assert "[CITE:" not in result

    def test_inject_multiple_cites(self, injector):
        result = injector.inject(
            "Qwen2-VL [CITE:wang2024qwen2] improves over LLaVA [CITE:li2024llava]."
        )
        assert "~\\cite{wang2024qwen2}" in result
        assert "~\\cite{li2024llava}" in result

    def test_inject_no_markers(self, injector):
        text = "Plain text without any citation markers."
        result = injector.inject(text)
        assert result == text

    def test_inject_empty_string(self, injector):
        assert injector.inject("") == ""

    def test_inject_invalid_key_keeps_marker(self, injector):
        result = injector.inject("Some claim [CITE:INVALID_KEY].")
        assert "[CITE:INVALID_KEY]" in result
        assert "~\\cite" not in result

    def test_inject_mixed_valid_invalid(self, injector):
        result = injector.inject(
            "Valid [CITE:wang2024qwen2] and invalid [CITE:INVALID]."
        )
        assert "~\\cite{wang2024qwen2}" in result
        assert "[CITE:INVALID]" in result

    def test_inject_multiple_whitespace_variants(self, injector):
        result = injector.inject("[CITE:wang2024qwen2] [CITE:  wang2024qwen2  ]")
        count = result.count("~\\cite{wang2024qwen2}")
        assert count == 2

    # --- validate_all ---

    def test_validate_all_valid(self, injector):
        draft = "Valid [CITE:wang2024qwen2] key."
        invalid = injector.validate_all(draft)
        assert invalid == []

    def test_validate_all_invalid(self, injector):
        draft = "Invalid [CITE:INVALID] key."
        invalid = injector.validate_all(draft)
        assert invalid == ["INVALID"]

    def test_validate_all_mixed(self, injector):
        draft = "Valid [CITE:wang2024qwen2] and invalid [CITE:INVALID]."
        invalid = injector.validate_all(draft)
        assert invalid == ["INVALID"]

    def test_validate_all_empty(self, injector):
        assert injector.validate_all("") == []

    def test_validate_all_no_markers(self, injector):
        assert injector.validate_all("Plain text") == []

    def test_validate_all_dedup(self, injector):
        draft = "[CITE:INVALID] and [CITE:INVALID] again"
        invalid = injector.validate_all(draft)
        assert invalid == ["INVALID"]
        assert len(invalid) == 1

    # --- get_used_keys ---

    def test_get_used_keys(self, injector):
        draft = "A [CITE:wang2024qwen2] and B [CITE:li2024llava]."
        keys = injector.get_used_keys(draft)
        assert keys == sorted(["wang2024qwen2", "li2024llava"])

    def test_get_used_keys_empty(self, injector):
        assert injector.get_used_keys("") == []

    def test_get_used_keys_dedup(self, injector):
        draft = "[CITE:wang2024qwen2] and [CITE:wang2024qwen2] again"
        keys = injector.get_used_keys(draft)
        assert keys == ["wang2024qwen2"]

    # --- get_missing_keys ---

    def test_get_missing_keys(self, injector):
        draft = "Valid [CITE:wang2024qwen2] and invalid [CITE:MISSING]."
        missing = injector.get_missing_keys(draft)
        assert missing == ["MISSING"]

    def test_get_missing_keys_all_valid(self, injector):
        draft = "[CITE:wang2024qwen2]."
        assert injector.get_missing_keys(draft) == []

    def test_get_missing_keys_all_invalid(self, injector):
        draft = "[CITE:X] [CITE:Y]"
        missing = injector.get_missing_keys(draft)
        assert missing == ["X", "Y"]


# =========================================================================
# BenchmarkTableGenerator
# =========================================================================

class TestBenchmarkTableGenerator:
    """Test BenchmarkTableGenerator: generate tables, replace markers, edge cases."""

    @pytest.fixture
    def benchmark_store(self):
        bs = BenchmarkStore()
        bs.add_records([
            BenchmarkRecord(model_name="ModelA", benchmark_name="MMLU",
                            score="85.3", citation_key="citeA", verified=True),
            BenchmarkRecord(model_name="ModelB", benchmark_name="MMLU",
                            score="82.1", citation_key="citeB", verified=True),
            BenchmarkRecord(model_name="ModelC", benchmark_name="MMLU",
                            score="88.0", citation_key="citeC", verified=True),
        ])
        return bs

    @pytest.fixture
    def citation_store(self):
        return CitationStore()

    @pytest.fixture
    def generator(self, benchmark_store, citation_store):
        return BenchmarkTableGenerator(benchmark_store, citation_store)

    # --- generate_benchmark_table ---

    def test_generate_benchmark_table(self, generator):
        table = generator.generate_benchmark_table("MMLU")
        assert table.startswith(r"\begin{table}")
        assert "MMLU" in table
        assert "ModelA" in table
        assert "ModelB" in table
        assert "ModelC" in table
        assert "\\cite{citeA}" in table
        assert "\\toprule" in table
        assert "\\bottomrule" in table

    def test_generate_benchmark_table_sorted_desc(self, generator):
        table = generator.generate_benchmark_table("MMLU")
        # Find positions of models
        idx_a = table.index("ModelA")
        idx_b = table.index("ModelB")
        idx_c = table.index("ModelC")
        # ModelC (88.0) should come before ModelA (85.3) before ModelB (82.1)
        assert idx_c < idx_a < idx_b

    def test_generate_benchmark_table_no_data(self, generator):
        result = generator.generate_benchmark_table("NONEXISTENT")
        assert result == ""

    def test_generate_benchmark_table_empty_store(self):
        generator = BenchmarkTableGenerator(BenchmarkStore(), CitationStore())
        assert generator.generate_benchmark_table("MMLU") == ""

    def test_generate_benchmark_table_only_unverified(self):
        bs = BenchmarkStore()
        bs.add_records([
            BenchmarkRecord(model_name="ModelX", benchmark_name="MMLU",
                            score="90.0", verified=False),
        ])
        generator = BenchmarkTableGenerator(bs, CitationStore())
        # Only verified records are included
        assert generator.generate_benchmark_table("MMLU") == ""

    # --- generate_summary_table ---

    @pytest.fixture
    def knowledge_base(self):
        kb = PaperKnowledgeBase()
        arch = ArchitectureKnowledge(
            vision_encoder=KnowledgeField(value="ViT-L"),
            language_model=KnowledgeField(value="Qwen2-7B"),
            connector=KnowledgeField(value="MLP"),
        )
        kb.add(PaperKnowledge(
            paper_id="p1", title="Qwen2-VL: A Model",
            architecture=arch,
        ))
        return kb

    def test_generate_summary_table(self, generator, knowledge_base):
        table = generator.generate_summary_table(knowledge_base)
        assert table.startswith(r"\begin{table}")
        assert "Vision Encoder" in table
        assert "Language Model" in table
        assert "ViT-L" in table
        assert "Qwen2-7B" in table

    def test_generate_summary_table_empty_kb(self, generator):
        assert generator.generate_summary_table(PaperKnowledgeBase()) == ""

    def test_generate_summary_table_no_architecture(self, generator):
        kb = PaperKnowledgeBase()
        kb.add(PaperKnowledge(paper_id="p1", title="No Arch Paper"))
        assert generator.generate_summary_table(kb) == ""

    def test_generate_summary_table_partial_architecture(self, generator):
        kb = PaperKnowledgeBase()
        arch = ArchitectureKnowledge(vision_encoder=KnowledgeField(value="ViT-L"))
        kb.add(PaperKnowledge(paper_id="p1", title="Partial", architecture=arch))
        table = generator.generate_summary_table(kb)
        assert "ViT-L" in table
        # Only non-empty columns should appear
        assert "Language Model" not in table

    # --- replace_tables ---

    def test_replace_tables_benchmark_marker(self, generator):
        draft = "Performance comparison: [TABLE:benchmark_MMLU]"
        result = generator.replace_tables(draft)
        assert "[TABLE:benchmark_MMLU]" not in result
        assert r"\begin{table}" in result

    def test_replace_tables_empty_draft(self, generator):
        assert generator.replace_tables("") == ""

    def test_replace_tables_no_markers(self, generator):
        draft = "Plain text without markers."
        assert generator.replace_tables(draft) == draft

    def test_replace_tables_unknown_marker_kept(self, generator):
        draft = "Unknown [TABLE:unknown_marker]"
        result = generator.replace_tables(draft)
        assert "[TABLE:unknown_marker]" in result

    def test_replace_tables_multiple_markers(self, generator, knowledge_base):
        draft = "MMLU: [TABLE:benchmark_MMLU] and taxonomy: [TABLE:model_taxonomy]"
        result = generator.replace_tables(draft, knowledge_base)
        assert "[TABLE:benchmark_MMLU]" not in result
        assert "[TABLE:model_taxonomy]" not in result
        assert r"\begin{table}" in result

    def test_replace_tables_model_taxonomy_no_kb(self, generator):
        draft = "Taxonomy: [TABLE:model_taxonomy]"
        result = generator.replace_tables(draft)
        # Without knowledge_base, keep marker
        assert "[TABLE:model_taxonomy]" in result

    # --- get_stale_markers ---

    def test_get_stale_markers(self, generator):
        draft = "[TABLE:unknown] and [TABLE:also_unknown]"
        result = generator.replace_tables(draft)
        stale = generator.get_stale_markers(result)
        assert "unknown" in stale
        assert "also_unknown" in stale

    def test_get_stale_markers_none(self, generator):
        draft = "No markers"
        assert generator.get_stale_markers(draft) == []


# =========================================================================
# _parse_score helper
# =========================================================================

class TestParseScore:
    def test_parse_simple_float(self):
        assert _parse_score("85.3") == 85.3

    def test_parse_integer_string(self):
        assert _parse_score("90") == 90.0

    def test_parse_with_range(self):
        assert _parse_score("83.2 (+2.4)") == 83.2

    def test_parse_fractional(self):
        assert _parse_score("4.5/5") == 4.5

    def test_parse_empty_string(self):
        assert _parse_score("") == 0.0

    def test_parse_non_numeric(self):
        assert _parse_score("N/A") == 0.0

    def test_parse_negative(self):
        assert _parse_score("-5.0") == -5.0


# =========================================================================
# _extract_first_keyword helper
# =========================================================================

class TestExtractFirstKeyword:
    def test_normal_title(self):
        assert _extract_first_keyword("Qwen2-VL: Better Vision-Language Model") == "qwen2"

    def test_title_starts_with_stop_word(self):
        assert _extract_first_keyword("A Survey of Transformers") == "survey"

    def test_title_with_parentheses(self):
        kw = _extract_first_keyword("CLIP (Contrastive Language-Image Pre-training)")
        assert kw == "clip"

    def test_title_with_brackets(self):
        assert _extract_first_keyword("[NeurIPS] Attention is All You Need") == "attention"

    def test_empty_title(self):
        assert _extract_first_keyword("") == ""

    def test_title_only_stop_words(self):
        assert _extract_first_keyword("A An The") == ""

    def test_title_with_hyphen(self):
        assert _extract_first_keyword("Qwen2-VL Architecture") == "qwen2"


# =========================================================================
# _extract_model_name_from_title helper
# =========================================================================

class TestExtractModelName:
    def test_normal_model_name(self):
        assert _extract_model_name_from_title("Qwen2-VL: Better Model") == "Qwen2-VL"

    def test_no_colon(self):
        assert _extract_model_name_from_title("Just a Title") is None

    def test_stop_word_prefix(self):
        assert _extract_model_name_from_title("A Survey of: Transformers") is None

    def test_short_prefix(self):
        assert _extract_model_name_from_title("X: Single Letter") is None

    def test_no_uppercase_or_hyphen(self):
        assert _extract_model_name_from_title("lowercase: Prefix") is None

    def test_multi_word_prefix(self):
        result = _extract_model_name_from_title("LLaVA-NeXT: Improved Reasoning")
        assert result == "LLaVA-NeXT"
