"""Tests for PipelineOrchestrator."""
from agent.core.state import AgentState, StateMachine
from agent.core.pipeline import (
    HarnessConfig,
    PipelineOrchestrator,
    PipelineResult,
    TaskInfo,
)
from agent.core.llm import MockLLM
from agent.guardrails.manager import GuardrailManager
from agent.tools.registry import ToolRegistry


def _make_orchestrator():
    """Create a PipelineOrchestrator with MockLLM for testing."""
    llm = MockLLM(fixed_response="Test response")
    tools = ToolRegistry()
    guardrails = GuardrailManager(guardrails=[])  # No guardrails for tests
    config = HarnessConfig()
    return PipelineOrchestrator(
        llm=llm,
        tools=tools,
        validators=[],
        guardrails=guardrails,
        config=config,
        latex_repair=None,
    )


def test_orchestrator_initialization():
    """Test PipelineOrchestrator can be created with minimal config."""
    orch = _make_orchestrator()
    assert orch is not None
    assert orch.llm is not None
    assert orch.tools is not None


def test_orchestrator_run_pipeline_returns_result():
    """Test that run_pipeline returns a PipelineResult even with minimal setup."""
    orch = _make_orchestrator()
    task = TaskInfo(topic="Test Topic", keywords=["test"], goal="Test goal")
    state = StateMachine()
    state.transition_to(AgentState.PLANNING)

    result = orch.run_pipeline(
        task=task,
        state=state,
        feedback_queue=[],
        feedback_lock=__import__("threading").Lock(),
        feedback_history=[],
    )

    assert isinstance(result, PipelineResult)
    assert result.status in ("error", "interrupted", "complete_with_warnings")


def test_orchestrator_error_info():
    """Test get_error_info returns expected structure."""
    orch = _make_orchestrator()
    info = orch.get_error_info()
    assert "pipeline_retry_count" in info
    assert "last_failed_stage" in info
    assert "error" in info
    assert info["pipeline_retry_count"] == 0
    assert info["last_failed_stage"] == ""
    assert info["error"] == ""


def test_orchestrator_reset_error_state():
    """Test reset_error_state clears error info."""
    orch = _make_orchestrator()
    orch._pipeline_retry_count = 3
    orch._error_message = "Something went wrong"
    orch.reset_error_state()
    assert orch._pipeline_retry_count == 0
    assert orch._error_message == ""


def test_orchestrator_interrupt_handling():
    """Test that interrupt event is checked."""
    import threading
    orch = _make_orchestrator()
    event = threading.Event()
    orch.set_interrupt_event(event)
    assert not orch._check_interrupted()
    event.set()
    assert orch._check_interrupted()


def test_orchestrator_extract_sections():
    """Test LaTeX section extraction."""
    draft = r"""
    \section{Introduction}
    Some text.
    \subsection{Background}
    More text.
    \section{Conclusion}
    """
    sections = PipelineOrchestrator._extract_sections(draft)
    assert len(sections) == 3
    assert sections[0]["title"] == "Introduction"
    assert sections[1]["title"] == "Background"
    assert sections[2]["title"] == "Conclusion"


def test_orchestrator_build_task_info():
    """Test task info building (used by progress callbacks)."""
    orch = _make_orchestrator()
    orch._plan = "\\section{Introduction}\n\\section{Methods}"
    info = orch._build_task_info()
    assert "plan" in info
    assert info["plan"]["section_count"] == 2


def test_retry_on_error_resets_stage_after_success():
    """Test that _retry_on_error resets current_stage from 'retrying' back to the correct stage after a successful retry.

    This is the regression test for the bug where:
    1. _retry_on_error catches an error and calls _progress("retrying", ...)
       → sets current_stage = "retrying"
    2. When the retry succeeds, current_stage is never reset from "retrying"
    3. The frontend sees "retrying" (index 7) and shows ALL stages as "completed"
    """
    orch = _make_orchestrator()
    # Set max_pipeline_retries to 1 so we get 2 total attempts
    orch.config.max_pipeline_retries = 1
    # _retry_on_error needs _state to be set
    orch._state = StateMachine()
    orch._state.transition_to(AgentState.PLANNING)
    orch._state.transition_to(AgentState.RETRIEVAL)

    # Record progress calls
    progress_calls = []

    def on_progress(stage: str, msg: str, detail: dict | None):
        progress_calls.append(stage)

    call_count = [0]

    def fails_once():
        call_count[0] += 1
        if call_count[0] == 1:
            raise RuntimeError("First attempt fails")
        return "success"

    result = orch._retry_on_error(
        fn=fails_once,
        stage=AgentState.RETRIEVAL,
        on_progress=on_progress,
    )

    assert result == "success"
    assert call_count[0] == 2
    # After the retry succeeds, the LAST progress call should be "retrieval", not "retrying"
    assert progress_calls[-1] == "retrieval", (
        f"Expected last progress stage to be 'retrieval', got '{progress_calls[-1]}'. "
        f"All progress calls: {progress_calls}"
    )
    # The "retrying" call should be in the middle, followed by a reset to "retrieval"
    assert "retrying" in progress_calls, "Should have had a 'retrying' progress call"
    # Verify current_stage is reset to the correct stage for the frontend
    assert orch.current_stage == "retrieval", (
        f"current_stage should be 'retrieval' after retry succeeds, got '{orch.current_stage}'"
    )


def test_guardrail_manager_with_empty_guardrails():
    """Test GuardrailManager with empty guardrail list."""
    manager = GuardrailManager(guardrails=[])
    result = manager.check_all({"text": "test"})
    assert result == []


# ---------------------------------------------------------------------------
# Integration tests for new paper search tools
# ---------------------------------------------------------------------------


def test_all_search_tools_importable():
    """All new tools should be importable without errors."""
    from agent.tools.relevance import RelevanceFilter
    from agent.tools.citation import CitationExpander
    from agent.tools.venue import VenueLookup
    from agent.tools.processing import CompositeRanker

    assert RelevanceFilter().name == "relevance_filter"
    assert CitationExpander().name == "citation_expand"
    assert VenueLookup().name == "venue_lookup"
    assert CompositeRanker().name == "composite_rank"


def test_harness_config_new_fields():
    """HarnessConfig should include new paper search fields."""
    config = HarnessConfig()
    assert hasattr(config, "relevance_threshold")
    assert config.relevance_threshold == 3.0
    assert hasattr(config, "citation_expand_top_k")
    assert config.citation_expand_top_k == 5
    assert hasattr(config, "citation_expand_per_paper")
    assert config.citation_expand_per_paper == 10
    assert hasattr(config, "composite_weights")
    assert config.composite_weights["citation"] == 0.4
    assert hasattr(config, "enable_dblp_lookup")
    assert config.enable_dblp_lookup is True


def test_tool_registry_contains_new_tools():
    """ToolRegistry should have all new tools registered."""
    from agent.tools.registry import ToolRegistry
    from agent.tools.relevance import RelevanceFilter
    from agent.tools.citation import CitationExpander
    from agent.tools.venue import VenueLookup
    from agent.tools.processing import CompositeRanker

    registry = ToolRegistry()
    registry.register(RelevanceFilter())
    registry.register(CitationExpander())
    registry.register(VenueLookup())
    registry.register(CompositeRanker())

    assert registry.get("relevance_filter") is not None
    assert registry.get("citation_expand") is not None
    assert registry.get("venue_lookup") is not None
    assert registry.get("composite_rank") is not None


def test_integration_relevance_filter_composite_rank():
    """End-to-end: relevance filter followed by composite ranking."""
    from agent.tools.relevance import RelevanceFilter
    from agent.tools.processing import CompositeRanker

    papers = [
        {"title": "Deep Learning for Vision", "citation_count": 100, "venue": "CVPR"},
        {"title": "Database Systems", "citation_count": 200, "venue": "SIGMOD"},
        {"title": "Image Classification Methods", "citation_count": 50, "venue": ""},
    ]
    topic = "computer vision"

    # Step 1: Relevance filter
    llm_response = (
        "Deep Learning for Vision | 5 | Core CV topic\n"
        "Database Systems | 1 | Not related to vision\n"
        "Image Classification Methods | 4 | Related sub-topic\n"
    )
    filter_result = RelevanceFilter().execute({
        "papers": papers, "llm_response": llm_response, "threshold": 3.0,
    })
    assert filter_result.success
    filtered = filter_result.data["papers"]
    assert len(filtered) == 2  # Database Systems filtered out

    # Step 2: Mark venues (simulating VenueLookup)
    for p in filtered:
        v = (p.get("venue") or "").lower()
        if v in ("cvpr", "iccv", "eccv"):
            p["is_top_venue"] = True
        else:
            p["is_top_venue"] = False

    # Step 3: Composite ranking
    rank_result = CompositeRanker().execute({"papers": filtered})
    assert rank_result.success
    ranked = rank_result.data["papers"]
    assert len(ranked) == 2
    # Deep Learning for Vision (citation=100, venue=top, relevance=5) should be first
    assert ranked[0]["title"] == "Deep Learning for Vision"
    assert "_composite_score" in ranked[0]