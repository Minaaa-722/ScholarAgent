import pytest
from agent.feedback.base import Validator, ValidationResult
from agent.feedback.check_citations import CitationChecker
from agent.feedback.detect_hallucination import HallucinationDetector
from agent.feedback.check_word_count import WordCountChecker
from agent.feedback.polish_language import LanguagePolisher
from agent.feedback.check_coherence import CoherenceChecker


def test_validator_base_cannot_be_instantiated():
    with pytest.raises(TypeError):
        Validator()


def test_citation_checker_all_valid():
    checker = CitationChecker()
    chapter = {
        "content": "Transformers [@vaswani2017] are effective. BERT [@devlin2019] improves it.",
        "paper_ids": ["vaswani2017", "devlin2019"],
    }
    result = checker.validate(chapter)
    assert result.passed is True
    assert result.score == 1.0


def test_citation_checker_with_missing_refs():
    checker = CitationChecker()
    chapter = {
        "content": "Transformers [@vaswani2017] are effective. [@unknown2020] is missing.",
        "paper_ids": ["vaswani2017"],
    }
    result = checker.validate(chapter)
    assert result.passed is False
    assert result.score < 0.7
    assert len(result.issues) > 0
    assert "unknown2020" in result.issues[0]


def test_citation_checker_no_citations():
    checker = CitationChecker()
    chapter = {
        "content": "This is a statement without any citation.",
        "paper_ids": [],
    }
    result = checker.validate(chapter)
    assert result.passed is False


def test_hallucination_detector_no_hallucination():
    detector = HallucinationDetector()
    chapter = {
        "content": "Transformers [@v2017] achieve SOTA. BERT [@d2019] uses pretraining.",
        "paper_ids": ["v2017", "d2019"],
    }
    result = detector.validate(chapter)
    assert result.passed is True


def test_hallucination_detector_unsupported_claim():
    detector = HallucinationDetector()
    chapter = {
        "content": "This method achieves 75% accuracy improvement. [citation-needed]",
        "paper_ids": [],
    }
    result = detector.validate(chapter)
    assert result.passed is False
    assert len(result.issues) > 0


def test_word_count_checker_within_range():
    checker = WordCountChecker(min_words=10, max_words=100)
    chapter = {"content": "This is a test chapter with enough words to pass the minimum threshold."}
    result = checker.validate(chapter)
    assert result.passed is True


def test_word_count_checker_too_short():
    checker = WordCountChecker(min_words=50, max_words=100)
    chapter = {"content": "Too short."}
    result = checker.validate(chapter)
    assert result.passed is False
    assert "too short" in result.issues[0].lower()


def test_word_count_checker_too_long():
    checker = WordCountChecker(min_words=10, max_words=20)
    chapter = {"content": "This is a very long chapter that definitely exceeds the maximum word limit and should be flagged as too long by the word count checker because it has way more than twenty words."}
    result = checker.validate(chapter)
    assert result.passed is False
    assert "too long" in result.issues[0].lower()


def test_language_polisher_detects_informal():
    polisher = LanguagePolisher()
    text = "This paper is super cool and does amazing stuff."
    result = polisher.validate({"content": text})
    assert result.passed is False
    assert len(result.issues) > 0


def test_language_polisher_accepts_formal():
    polisher = LanguagePolisher()
    text = "This paper presents a novel approach to the problem."
    result = polisher.validate({"content": text})
    assert result.passed is True


def test_coherence_checker_has_transitions():
    checker = CoherenceChecker()
    chapter = {
        "content": "First, we introduce the problem. Subsequently, we review related work. Finally, we discuss future directions."
    }
    result = checker.validate(chapter)
    assert result.passed is True


def test_coherence_checker_no_transitions():
    checker = CoherenceChecker()
    chapter = {
        "content": "This is a. This is b. This is c. This is d. This is e."
    }
    result = checker.validate(chapter)
    assert result.passed is False


def test_validation_result_dataclass():
    result = ValidationResult(
        validator_name="test",
        passed=True,
        score=0.95,
        issues=[],
        repair_instructions="",
    )
    assert result.validator_name == "test"
    assert result.passed is True