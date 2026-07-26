import pytest
from agent.feedback.base import Validator, ValidationResult
from agent.feedback.check_citations import CitationChecker
from agent.feedback.detect_hallucination import HallucinationDetector
from agent.feedback.check_word_count import WordCountChecker
from agent.feedback.polish_language import LanguagePolisher
from agent.feedback.check_coherence import CoherenceChecker
from agent.feedback.aggregator import FeedbackAggregator
from agent.feedback.repair_generator import RepairGenerator


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
    chapter = {
        "content": (
            "This is a very long chapter that definitely exceeds the maximum "
            "word limit and should be flagged as too long by the word count "
            "checker because it has way more than twenty words."
        )
    }
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
        "content": (
            "First, we introduce the problem. Subsequently, we review "
            "related work. Finally, we discuss future directions."
        )
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


def test_aggregator_all_pass():
    agg = FeedbackAggregator()
    results = [
        ValidationResult(validator_name="a", passed=True, score=0.9),
        ValidationResult(validator_name="b", passed=True, score=1.0),
    ]
    report = agg.aggregate(results)
    assert report.overall_passed is True
    assert report.overall_score >= 0.7


def test_aggregator_some_fail():
    agg = FeedbackAggregator()
    results = [
        ValidationResult(validator_name="a", passed=True, score=0.9),
        ValidationResult(validator_name="b", passed=False, score=0.3, issues=["Bad"]),
    ]
    report = agg.aggregate(results)
    assert report.overall_passed is False
    assert report.overall_score < 0.7
    assert len(report.failed_validators) == 1


def test_aggregator_empty_results():
    agg = FeedbackAggregator()
    report = agg.aggregate([])
    assert report.overall_passed is True


def test_aggregator_threshold():
    agg = FeedbackAggregator(pass_threshold=0.85)
    results = [
        ValidationResult(validator_name="a", passed=True, score=0.8),
        ValidationResult(validator_name="b", passed=True, score=0.8),
    ]
    report = agg.aggregate(results)
    assert report.overall_passed is False  # 0.8 < 0.85


def test_repair_generator_combines_instructions():
    gen = RepairGenerator()
    results = [
        ValidationResult(validator_name="a", passed=False, score=0.5,
                         repair_instructions="Fix A"),
        ValidationResult(validator_name="b", passed=False, score=0.4,
                         repair_instructions="Fix B"),
    ]
    instruction = gen.generate(results)
    assert "Fix A" in instruction
    assert "Fix B" in instruction


def test_repair_generator_empty_input():
    gen = RepairGenerator()
    instruction = gen.generate([])
    assert instruction == ""


def test_harness_integrates_feedback_loop():
    from agent.core.harness import Harness, HarnessConfig
    from agent.core.llm import MockLLM
    from agent.core.state import AgentState

    llm = MockLLM(fixed_response="Survey content")
    h = Harness(config=HarnessConfig(max_retries=3, quality_threshold=0.7), llm=llm)
    h.start(topic="Test")
    h.state.transition_to(AgentState.RETRIEVAL)
    h.state.transition_to(AgentState.ANALYSIS)
    h.state.transition_to(AgentState.WRITING)
    h.state.transition_to(AgentState.VALIDATION)
    bad_result = ValidationResult(
        validator_name="check_citations",
        passed=False,
        score=0.3,
        issues=["Missing citations"],
        repair_instructions="Add citations",
    )
    h.inject_feedback([bad_result])
    assert h.state.current_state == AgentState.WRITING
    assert h.retry_count == 1


def test_harness_stops_after_max_retries():
    from agent.core.harness import Harness, HarnessConfig
    from agent.core.llm import MockLLM
    from agent.core.state import AgentState

    llm = MockLLM(fixed_response="Content")
    h = Harness(config=HarnessConfig(max_retries=2, quality_threshold=0.7), llm=llm)
    h.start(topic="Test")
    h.state.transition_to(AgentState.RETRIEVAL)
    h.state.transition_to(AgentState.ANALYSIS)
    h.state.transition_to(AgentState.WRITING)
    h.state.transition_to(AgentState.VALIDATION)
    h.retry_count = 2
    bad_result = ValidationResult(
        validator_name="test", passed=False, score=0.3, issues=["Fail"],
    )
    h.inject_feedback([bad_result])
    assert h.state.current_state == AgentState.COMPLETE
    assert h.has_warnings is True