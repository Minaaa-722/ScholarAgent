"""
Mechanism Demo — ScholarAgent Harness
======================================

Deterministically demonstrates three core harness mechanisms under MockLLM,
with no real LLM or network dependency.

  Demo 1 — Guardrail Interception
    OpSafety blocks a dangerous shell command (rm -rf /) with REQUIRE_APPROVAL.

  Demo 2 — Feedback Loop State Transition
    Inject a failing validation result → Harness transitions from VALIDATION
    back to WRITING, increments retry_count, and stops after max_retries.

  Demo 3 — Deterministic Validators (Key Dimension: Feedback)
    All 5 validators (citation, hallucination, word count, language, coherence)
    produce deterministic, repeatable results on known inputs.

Run:
    python -m pytest tests/test_demo.py -v
"""

# ---------------------------------------------------------------------------
# Demo 1: Guardrail Interception
# ---------------------------------------------------------------------------
def test_demo_guardrail_intercepts_dangerous_action():
    """OpSafety guardrail intercepts 'rm -rf /' and returns REQUIRE_APPROVAL."""
    from agent.guardrails.op_safety import OpSafety
    from agent.guardrails.base import GuardrailVerdict

    guard = OpSafety()

    # Dangerous command — should be intercepted
    dangerous = guard.check({"action": "shell_exec", "params": {"command": "rm -rf /"}})
    assert dangerous.verdict == GuardrailVerdict.REQUIRE_APPROVAL, (
        f"Expected REQUIRE_APPROVAL, got {dangerous.verdict}"
    )

    # Safe command — should pass
    safe = guard.check({"action": "shell_exec", "params": {"command": "ls -la"}})
    assert safe.verdict == GuardrailVerdict.PASS, (
        f"Expected PASS, got {safe.verdict}"
    )

    # Multiple dangerous patterns
    for cmd in ["rm -rf /var", "drop table users", "format c: /q"]:
        result = guard.check({"action": "shell_exec", "params": {"command": cmd}})
        assert result.verdict == GuardrailVerdict.REQUIRE_APPROVAL, (
            f"Expected REQUIRE_APPROVAL for '{cmd}', got {result.verdict}"
        )


def test_demo_guardrail_rate_limit_blocks_excessive_calls():
    """RateLimit guardrail blocks after exceeding max calls in a window."""
    from agent.guardrails.rate_limit import RateLimit
    from agent.guardrails.base import GuardrailVerdict

    guard = RateLimit(max_calls=2, window_seconds=60)
    ctx = {"action": "arxiv_search"}

    # First two calls pass
    assert guard.check(ctx).verdict == GuardrailVerdict.PASS
    assert guard.check(ctx).verdict == GuardrailVerdict.PASS
    # Third call is blocked
    assert guard.check(ctx).verdict == GuardrailVerdict.BLOCK


# ---------------------------------------------------------------------------
# Demo 2: Feedback Loop — Agent Receives Feedback and Changes Next Action
# ---------------------------------------------------------------------------
def test_demo_feedback_loop_transitions_back_to_writing():
    """Harness transitions VALIDATION -> WRITING when feedback score is low."""
    from agent.core.harness import Harness, HarnessConfig
    from agent.core.llm import MockLLM
    from agent.core.state import AgentState
    from agent.feedback.base import ValidationResult

    llm = MockLLM(fixed_response="Survey content")
    h = Harness(config=HarnessConfig(max_retries=3, quality_threshold=0.7), llm=llm)
    h.start(topic="Test Topic")
    # Advance through pipeline states to VALIDATION
    h.state.transition_to(AgentState.RETRIEVAL)
    h.state.transition_to(AgentState.ANALYSIS)
    h.state.transition_to(AgentState.WRITING)
    h.state.transition_to(AgentState.VALIDATION)
    assert h.state.current_state == AgentState.VALIDATION
    assert h.retry_count == 0

    # Inject failing feedback — should bounce back to WRITING
    bad_result = ValidationResult(
        validator_name="check_citations",
        passed=False,
        score=0.3,
        issues=["Missing citations for 3 claims"],
        repair_instructions="Add [@ref] citations for each claim",
    )
    h.inject_feedback([bad_result])

    assert h.state.current_state == AgentState.WRITING, (
        f"Expected WRITING after feedback, got {h.state.current_state}"
    )
    assert h.retry_count == 1, (
        f"Expected retry_count=1, got {h.retry_count}"
    )


def test_demo_feedback_loop_stops_after_max_retries():
    """Harness stops retrying and enters COMPLETE with warnings after max_retries."""
    from agent.core.harness import Harness, HarnessConfig
    from agent.core.llm import MockLLM
    from agent.core.state import AgentState
    from agent.feedback.base import ValidationResult

    llm = MockLLM(fixed_response="Content")
    h = Harness(config=HarnessConfig(max_retries=2, quality_threshold=0.7), llm=llm)
    h.start(topic="Test")
    h.state.transition_to(AgentState.RETRIEVAL)
    h.state.transition_to(AgentState.ANALYSIS)
    h.state.transition_to(AgentState.WRITING)
    h.state.transition_to(AgentState.VALIDATION)
    # Set retry_count to max so one more failure forces COMPLETE with warnings
    h.retry_count = 2

    bad_result = ValidationResult(
        validator_name="check_citations",
        passed=False,
        score=0.3,
        issues=["Still missing citations"],
        repair_instructions="Add citations",
    )
    h.inject_feedback([bad_result])

    assert h.state.current_state == AgentState.COMPLETE, (
        f"Expected COMPLETE after max retries, got {h.state.current_state}"
    )
    assert h.has_warnings is True, "Expected has_warnings=True after max retries"


# ---------------------------------------------------------------------------
# Demo 3: Deterministic Validators (Key Dimension: Feedback)
# ---------------------------------------------------------------------------
def test_demo_all_five_validators_deterministic():
    """All 5 feedback validators produce deterministic results on known inputs."""
    from agent.feedback.check_citations import CitationChecker
    from agent.feedback.detect_hallucination import HallucinationDetector
    from agent.feedback.check_word_count import WordCountChecker
    from agent.feedback.polish_language import LanguagePolisher
    from agent.feedback.check_coherence import CoherenceChecker

    # --- CitationChecker ---
    cc = CitationChecker()
    # Good case: all citations match paper IDs
    good = cc.validate({
        "content": "Transformers [@vaswani2017] are effective. BERT [@devlin2019] improves it.",
        "paper_ids": ["vaswani2017", "devlin2019"],
    })
    assert good.passed is True
    assert good.score == 1.0
    # Bad case: citation with no matching paper ID
    bad = cc.validate({
        "content": "This method [@unknown2020] is great.",
        "paper_ids": ["vaswani2017"],
    })
    assert bad.passed is False
    assert bad.score < 0.7

    # --- HallucinationDetector ---
    hd = HallucinationDetector()
    good = hd.validate({
        "content": "Transformers [@v2017] achieve SOTA. BERT [@d2019] uses pretraining.",
        "paper_ids": ["v2017", "d2019"],
    })
    assert good.passed is True
    bad = hd.validate({
        "content": "This method achieves 75% accuracy improvement. [citation-needed]",
        "paper_ids": [],
    })
    assert bad.passed is False

    # --- WordCountChecker ---
    wc = WordCountChecker(min_words=5, max_words=50)
    good = wc.validate({"content": "This sentence has enough words to pass."})
    assert good.passed is True
    bad = wc.validate({"content": "Too short."})
    assert bad.passed is False

    # --- LanguagePolisher ---
    lp = LanguagePolisher()
    good = lp.validate({"content": "This paper presents a novel approach to the problem."})
    assert good.passed is True
    bad = lp.validate({"content": "This paper is super cool and does amazing stuff."})
    assert bad.passed is False

    # --- CoherenceChecker ---
    cc2 = CoherenceChecker()
    good = cc2.validate({
        "content": "First, we introduce. Subsequently, we review. Finally, we discuss."
    })
    assert good.passed is True
    bad = cc2.validate({
        "content": "This is a. This is b. This is c. This is d. This is e."
    })
    assert bad.passed is False


def test_demo_aggregator_and_repair_generator():
    """FeedbackAggregator + RepairGenerator produce deterministic combined results."""
    from agent.feedback.aggregator import FeedbackAggregator
    from agent.feedback.repair_generator import RepairGenerator
    from agent.feedback.base import ValidationResult

    agg = FeedbackAggregator(pass_threshold=0.7)
    gen = RepairGenerator()

    # Mixed results: one pass, one fail
    results = [
        ValidationResult(
            validator_name="check_citations", passed=True, score=0.9,
        ),
        ValidationResult(
            validator_name="check_word_count", passed=False, score=0.3,
            issues=["Too short"],
            repair_instructions="Expand to at least 100 words",
        ),
    ]

    report = agg.aggregate(results)
    assert report.overall_passed is False, "Expected overall FAIL for mixed results"
    assert report.overall_score == 0.6, f"Expected score 0.6, got {report.overall_score}"
    assert "check_word_count" in report.failed_validators

    instructions = gen.generate(results)
    assert "check_word_count" in instructions
    assert "Expand to at least 100 words" in instructions


def test_demo_end_to_end_feedback_iteration():
    """Full iteration: validate -> detect failure -> aggregate -> generate repair."""
    from agent.feedback.check_citations import CitationChecker
    from agent.feedback.check_word_count import WordCountChecker
    from agent.feedback.aggregator import FeedbackAggregator
    from agent.feedback.repair_generator import RepairGenerator

    chapter = {
        "content": "This paper is super cool. [citation-needed]",
        "paper_ids": ["ref2020"],
    }

    # Step 1: Run validators
    results = [
        CitationChecker().validate(chapter),
        WordCountChecker(min_words=10, max_words=100).validate(chapter),
    ]

    # Step 2: Aggregate
    report = FeedbackAggregator(pass_threshold=0.7).aggregate(results)
    assert report.overall_passed is False, "Expected FAIL for poor chapter"

    # Step 3: Generate repair instructions
    instructions = RepairGenerator().generate(results)
    assert len(instructions) > 0, "Expected repair instructions for failing validators"