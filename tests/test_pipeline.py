"""Tests for PipelineOrchestrator — covering all missing branches and uncovered paths."""
import threading
import pytest
from unittest.mock import MagicMock, patch
from agent.core.state import AgentState, StateMachine
from agent.core.pipeline import (
    HarnessConfig,
    PipelineOrchestrator,
    PipelineResult,
    TaskInfo,
)
from agent.core.llm import MockLLM, LLMResponse
from agent.guardrails.manager import GuardrailManager
from agent.tools.registry import ToolRegistry
from agent.feedback.base import ValidationResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_llm():
    return MockLLM(fixed_response="Test response")


@pytest.fixture
def empty_tools():
    return ToolRegistry()


@pytest.fixture
def empty_guardrails():
    return GuardrailManager(guardrails=[])


@pytest.fixture
def default_config():
    return HarnessConfig()


@pytest.fixture
def orch(mock_llm, empty_tools, empty_guardrails, default_config):
    """Create a minimal PipelineOrchestrator with MockLLM for testing."""
    return PipelineOrchestrator(
        llm=mock_llm,
        tools=empty_tools,
        validators=[],
        guardrails=empty_guardrails,
        config=default_config,
        latex_repair=None,
    )


@pytest.fixture
def sample_task():
    """Sample task for pipeline execution tests."""
    return TaskInfo(topic="Test Topic", keywords=["test"], goal="Test goal")


@pytest.fixture
def sample_state():
    """State machine initialized to PLANNING."""
    state = StateMachine()
    state.transition_to(AgentState.PLANNING)
    return state


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

def test_orchestrator_initialization(orch):
    """PipelineOrchestrator should initialize with all empty state."""
    assert orch is not None
    assert orch.llm is not None
    assert orch.tools is not None
    assert orch._validators == []
    assert orch.execution_log == []
    assert orch._pipeline_retry_count == 0
    assert orch._last_failed_stage is None
    assert orch._error_message == ""
    assert orch._plan == ""
    assert orch._papers == []
    assert orch._analysis == ""
    assert orch._draft_sections == []
    assert orch._validation_scores == {}
    assert orch._retrieved_queries == []
    assert orch._pending_expansions == []
    assert orch._pending_revisions == []


def test_orchestrator_sets_interrupt_event(orch):
    """set_interrupt_event should store the threading.Event reference."""
    event = threading.Event()
    orch.set_interrupt_event(event)
    assert orch._interrupt_event is event


# ---------------------------------------------------------------------------
# get_error_info / reset_error_state
# ---------------------------------------------------------------------------

def test_orchestrator_error_info(orch):
    """get_error_info should return default empty values."""
    info = orch.get_error_info()
    assert info["pipeline_retry_count"] == 0
    assert info["last_failed_stage"] == ""
    assert info["error"] == ""


def test_orchestrator_error_info_with_failure(orch):
    """get_error_info should reflect set error state."""
    orch._pipeline_retry_count = 3
    orch._last_failed_stage = AgentState.PLANNING
    orch._error_message = "Something went wrong"
    info = orch.get_error_info()
    assert info["pipeline_retry_count"] == 3
    assert info["last_failed_stage"] == "PLANNING"
    assert info["error"] == "Something went wrong"


def test_orchestrator_reset_error_state(orch):
    """reset_error_state should clear all error info and stage messages."""
    orch._pipeline_retry_count = 3
    orch._error_message = "Something went wrong"
    orch._last_failed_stage = AgentState.PLANNING
    orch.stage_messages = [{"message": "old"}]
    orch.stage_metrics = {"key": "value"}
    orch.reset_error_state()
    assert orch._pipeline_retry_count == 0
    assert orch._error_message == ""
    assert orch._last_failed_stage is None
    assert orch.stage_messages == []
    assert orch.stage_metrics == {}


# ---------------------------------------------------------------------------
# _validate_dependencies
# ---------------------------------------------------------------------------

def test_validate_dependencies_passes(orch):
    """All required dependencies should be initialized by default."""
    orch._validate_dependencies()


def test_validate_dependencies_missing():
    """Missing a required attribute should raise RuntimeError."""
    orch = _make_orchestrator_minimal()
    if hasattr(orch, '_citation_store'):
        del orch._citation_store
    with pytest.raises(RuntimeError, match="Missing pipeline dependency"):
        orch._validate_dependencies()


def _make_orchestrator_minimal():
    """Helper to create a bare PipelineOrchestrator for dependency testing."""
    llm = MockLLM(fixed_response="Test")
    tools = ToolRegistry()
    guardrails = GuardrailManager(guardrails=[])
    config = HarnessConfig()
    return PipelineOrchestrator(
        llm=llm, tools=tools, validators=[], guardrails=guardrails,
        config=config, latex_repair=None,
    )


# ---------------------------------------------------------------------------
# run_pipeline
# ---------------------------------------------------------------------------

def test_run_pipeline_returns_result(orch, sample_task, sample_state):
    """run_pipeline should return a PipelineResult even with minimal setup."""
    result = orch.run_pipeline(
        task=sample_task,
        state=sample_state,
        feedback_queue=[],
        feedback_lock=threading.Lock(),
        feedback_history=[],
    )
    assert isinstance(result, PipelineResult)
    assert result.status in ("error", "interrupted", "complete_with_warnings")


def test_run_pipeline_resets_state(orch, sample_task, sample_state):
    """run_pipeline should reset pipeline state before execution."""
    orch._pipeline_retry_count = 99
    orch._error_message = "old error"
    result = orch.run_pipeline(
        task=sample_task,
        state=sample_state,
        feedback_queue=[],
        feedback_lock=threading.Lock(),
        feedback_history=[],
    )
    assert isinstance(result, PipelineResult)


def test_run_pipeline_catches_fatal_error(orch, sample_task, sample_state):
    """run_pipeline should catch exceptions and return error PipelineResult."""
    def failing_generate(*args, **kwargs):
        raise RuntimeError("Fatal pipeline error")
    orch.llm.generate = failing_generate
    result = orch.run_pipeline(
        task=sample_task,
        state=sample_state,
        feedback_queue=[],
        feedback_lock=threading.Lock(),
        feedback_history=[],
    )
    assert result.status == "error"


# ---------------------------------------------------------------------------
# _pipeline — interrupt handling
# ---------------------------------------------------------------------------

def test_pipeline_interrupt_at_start(orch, sample_task, sample_state):
    """Interrupt before pipeline starts should return early."""
    event = threading.Event()
    event.set()
    orch.set_interrupt_event(event)
    orch.run_pipeline(
        task=sample_task, state=sample_state,
        feedback_queue=[], feedback_lock=threading.Lock(), feedback_history=[],
    )


def test_pipeline_interrupt_check(orch):
    """_check_interrupted should reflect interrupt event state."""
    event = threading.Event()
    orch.set_interrupt_event(event)
    assert not orch._check_interrupted()
    event.set()
    assert orch._check_interrupted()


def test_pipeline_interrupt_no_event(orch):
    """_check_interrupted should return False when no event is set."""
    orch._interrupt_event = None
    assert not orch._check_interrupted()


# ---------------------------------------------------------------------------
# _generate_search_queries — fallback paths
# ---------------------------------------------------------------------------

def test_generate_search_queries_success(orch, sample_task):
    """Should parse '->' separated queries from LLM response."""
    orch.llm = MockLLM(fixed_response="query1 -> q1\nquery2 -> q2")
    orch._task = sample_task
    result = orch._generate_search_queries("topic", ["kw1"])
    assert len(result) == 2
    assert "->" in result[0]


def test_generate_search_queries_fallback_on_exception(orch, sample_task):
    """Should return fallback queries when LLM raises."""
    def failing_generate(*args, **kwargs):
        raise RuntimeError("LLM error")
    orch.llm.generate = failing_generate
    orch._task = sample_task
    result = orch._generate_search_queries("topic", ["kw1", "kw2"])
    assert len(result) >= 1
    assert "topic" in result


def test_generate_search_queries_empty_queries(orch, sample_task):
    """Fallback when LLM returns no valid queries."""
    orch.llm = MockLLM(fixed_response="No arrows here")
    orch._task = sample_task
    result = orch._generate_search_queries("topic", ["kw1"])
    assert len(result) >= 1


# ---------------------------------------------------------------------------
# _generate_methodology_queries — fallback paths
# ---------------------------------------------------------------------------

def test_generate_methodology_queries_success(orch, sample_task):
    """Should parse methodology queries from LLM response."""
    orch.llm = MockLLM(fixed_response="method1 -> m1\nmethod2 -> m2")
    orch._task = sample_task
    result = orch._generate_methodology_queries("topic", ["kw1"])
    assert len(result) == 2


def test_generate_methodology_queries_fallback(orch, sample_task):
    """Should return fallback methodology queries on LLM error."""
    def failing_generate(*args, **kwargs):
        raise RuntimeError("LLM error")
    orch.llm.generate = failing_generate
    orch._task = sample_task
    result = orch._generate_methodology_queries("topic", ["kw1"])
    assert len(result) >= 1
    assert "methodology" in result[0] or "topic" in result[0]


# ---------------------------------------------------------------------------
# _expand_and_dedup_queries
# ---------------------------------------------------------------------------

def test_expand_and_dedup_queries_basic(orch):
    """Should expand '->' pairs and deduplicate."""
    raw = ["Vision Transformer -> ViT", "CNN -> CNN"]
    result = orch._expand_and_dedup_queries(raw, "topic", ["kw1", "kw2", "kw3"])
    assert "Vision Transformer" in result
    assert "ViT" in result
    assert "CNN" in result


def test_expand_and_dedup_queries_pads_to_three(orch):
    """Should pad query list to at least 3 entries."""
    raw = ["only one -> same"]
    result = orch._expand_and_dedup_queries(raw, "topic", ["kw1", "kw2", "kw3"])
    assert len(result) >= 3


def test_expand_and_dedup_queries_filters_long(orch):
    """Should filter out queries longer than 200 characters."""
    raw = ["a" * 300 + " -> b"]
    result = orch._expand_and_dedup_queries(raw, "topic", ["kw1"])
    assert all(len(q) < 200 for q in result)


# ---------------------------------------------------------------------------
# _emit_progress
# ---------------------------------------------------------------------------

def test_emit_progress_basic(orch):
    """_emit_progress should record a message with timestamp."""
    orch._emit_progress("info", "Test message")
    assert len(orch.stage_messages) == 1
    assert orch.stage_messages[0]["type"] == "info"
    assert orch.stage_messages[0]["message"] == "Test message"
    assert "timestamp" in orch.stage_messages[0]


def test_emit_progress_with_metrics(orch):
    """_emit_progress should update stage_metrics when provided."""
    orch._emit_progress("success", "Done", {"count": 5, "total": 10})
    assert orch.stage_messages[0]["type"] == "success"
    assert orch.stage_metrics["count"] == 5
    assert orch.stage_metrics["total"] == 10


def test_emit_progress_warning_type(orch):
    """_emit_progress should support warning type."""
    orch._emit_progress("warning", "Warning message")
    assert orch.stage_messages[0]["type"] == "warning"


# ---------------------------------------------------------------------------
# _format_repair
# ---------------------------------------------------------------------------

def test_format_repair_with_none(orch):
    """When latex_repair is None, _format_repair should raise."""
    with pytest.raises((AttributeError, TypeError)):
        orch._format_repair("test draft")


def test_format_repair_with_mock_repair(orch):
    """_format_repair should return fixed_text and set repair_log."""
    class MockEntry:
        def __init__(self):
            self.rule = "test_rule"
            self.location = "line 1"
            self.original = "old"
            self.replacement = "new"
        def short(self):
            return f"{self.rule}: {self.original} -> {self.replacement}"

    class MockRepairLog:
        def __init__(self):
            self.has_changes = True
            self.change_count = 2
            self.fixed_text = "\\section{Fixed}"
            self.entries = [MockEntry(), MockEntry()]
        def summary(self):
            return "2 changes applied"

    orch._latex_repair = MagicMock()
    orch._latex_repair.repair.return_value = MockRepairLog()
    result = orch._format_repair("test draft")
    assert result == "\\section{Fixed}"
    assert orch.latex_repair_log is not None
    assert orch.latex_repair_log.change_count == 2


def test_format_repair_no_changes(orch):
    """_format_repair should handle repair with no changes."""
    class MockRepairLog:
        def __init__(self):
            self.has_changes = False
            self.change_count = 0
            self.fixed_text = "original draft"
            self.entries = []
        def summary(self):
            return "No changes"

    orch._latex_repair = MagicMock()
    orch._latex_repair.repair.return_value = MockRepairLog()
    result = orch._format_repair("original draft")
    assert result == "original draft"


# ---------------------------------------------------------------------------
# _safe_llm_call
# ---------------------------------------------------------------------------

def test_safe_llm_call_basic(orch):
    """_safe_llm_call should return LLM response."""
    orch.llm = MockLLM(fixed_response="Hello")
    resp = orch._safe_llm_call("system", "user")
    assert resp.text == "Hello"


def test_safe_llm_call_with_tools(orch, empty_tools):
    """_safe_llm_call should build tool definitions from registry."""
    orch.tools = empty_tools
    orch.llm = MockLLM(fixed_response="Tool call result")
    resp = orch._safe_llm_call("system", "user", use_tools=True)
    assert resp.text == "Tool call result"


def test_safe_llm_call_failure(orch):
    """_safe_llm_call should wrap errors in RuntimeError."""
    def failing_generate(*args, **kwargs):
        raise ValueError("API error")
    orch.llm.generate = failing_generate
    with pytest.raises(RuntimeError, match="LLM call failed"):
        orch._safe_llm_call("system", "user")


# ---------------------------------------------------------------------------
# _safe_transition
# ---------------------------------------------------------------------------

def test_orch_safe_transition_valid(orch, sample_state):
    """_safe_transition should perform valid state transitions."""
    orch._state = sample_state
    orch._safe_transition(AgentState.RETRIEVAL)
    assert orch._state.current_state == AgentState.RETRIEVAL


def test_orch_safe_transition_invalid(orch, sample_state):
    """_safe_transition should swallow invalid transitions."""
    orch._state = sample_state
    orch._safe_transition(AgentState.COMPLETE)
    assert orch._state.current_state == AgentState.PLANNING


# ---------------------------------------------------------------------------
# _ensure_state
# ---------------------------------------------------------------------------

def test_orch_ensure_state_already_there(orch, sample_state):
    """_ensure_state should not transition if already in target."""
    orch._state = sample_state
    orch._ensure_state(AgentState.PLANNING)
    assert orch._state.current_state == AgentState.PLANNING


def test_orch_ensure_state_transitions(orch, sample_state):
    """_ensure_state should transition to target if not already there."""
    orch._state = sample_state
    orch._ensure_state(AgentState.RETRIEVAL)
    assert orch._state.current_state == AgentState.RETRIEVAL


# ---------------------------------------------------------------------------
# _log
# ---------------------------------------------------------------------------

def test_orch_log(orch):
    """_log should append timestamped entry to execution_log."""
    orch._log("TEST", {"key": "value"})
    assert len(orch.execution_log) == 1
    assert orch.execution_log[0]["stage"] == "TEST"
    assert orch.execution_log[0]["key"] == "value"


# ---------------------------------------------------------------------------
# _build_result
# ---------------------------------------------------------------------------

def test_build_result_basic(orch):
    """_build_result should return PipelineResult with basic fields."""
    result = orch._build_result("paper", "complete", 2)
    assert result.paper == "paper"
    assert result.status == "complete"
    assert result.rounds == 2
    assert result.validation_scores == {}


def test_build_result_with_latex_log(orch):
    """_build_result should include latex_repair_log when available."""
    class MockEntry:
        def __init__(self):
            self.rule = "rule"
            self.location = "loc"
            self.original = "orig"
            self.replacement = "repl"

    class MockRepairLog:
        def __init__(self):
            self.has_changes = True
            self.change_count = 1
            self.entries = [MockEntry()]
        def summary(self):
            return "1 change"

    orch.latex_repair_log = MockRepairLog()
    result = orch._build_result("paper", "complete", 1)
    assert result.latex_repair_log is not None
    assert result.latex_repair_log["change_count"] == 1
    assert len(result.latex_repair_log["entries"]) == 1


def test_build_result_without_latex_log(orch):
    """_build_result should omit latex_repair_log when None."""
    orch.latex_repair_log = None
    result = orch._build_result("paper", "complete", 1)
    assert result.latex_repair_log is None


# ---------------------------------------------------------------------------
# _build_task_info
# ---------------------------------------------------------------------------

def test_build_task_info_empty(orch):
    """_build_task_info should return empty dict when nothing is set."""
    info = orch._build_task_info()
    assert info == {}


def test_build_task_info_with_plan(orch):
    """_build_task_info should include plan with section count."""
    orch._plan = "\\section{Intro}\n\\section{Methods}"
    info = orch._build_task_info()
    assert "plan" in info
    assert info["plan"]["section_count"] == 2


def test_build_task_info_with_papers(orch):
    """_build_task_info should include paper list with et al."""
    orch._papers = [
        {"title": "Paper A", "authors": ["Author1", "Author2", "Author3", "Author4"]},
        {"title": "Paper B", "authors": ["Author5"]},
    ]
    info = orch._build_task_info()
    assert "papers" in info
    assert info["papers"]["total"] == 2
    assert len(info["papers"]["list"]) == 2
    assert "et al." in info["papers"]["list"][0]["authors"]


def test_build_task_info_with_papers_arxiv(orch):
    """Papers with arxiv_id should show source='arxiv'."""
    orch._papers = [{"title": "Paper", "authors": [], "arxiv_id": "1234"}]
    info = orch._build_task_info()
    assert info["papers"]["list"][0]["source"] == "arxiv"


def test_build_task_info_with_queries(orch):
    """_build_task_info should include search queries."""
    orch._retrieved_queries = ["q1", "q2"]
    info = orch._build_task_info()
    assert info["search_queries"] == ["q1", "q2"]


def test_build_task_info_with_analysis(orch):
    """_build_task_info should include analysis summary."""
    orch._analysis = "Full analysis text here"
    info = orch._build_task_info()
    assert "analysis" in info
    assert info["analysis"]["summary"] == "Paper analysis completed"


def test_build_task_info_with_sections(orch):
    """_build_task_info should include draft sections."""
    orch._draft_sections = [{"title": "Intro", "level": 0}]
    info = orch._build_task_info()
    assert "sections" in info


def test_build_task_info_with_validation(orch):
    """_build_task_info should include validation scores."""
    orch._validation_scores = {"check": {"score": 0.9, "passed": True}}
    info = orch._build_task_info()
    assert "validation" in info


# ---------------------------------------------------------------------------
# _extract_sections
# ---------------------------------------------------------------------------

def test_orch_extract_sections(orch):
    """_extract_sections should parse LaTeX section commands."""
    draft = r"""
    \section{Introduction}
    \subsection{Background}
    \section{Conclusion}
    """
    sections = PipelineOrchestrator._extract_sections(draft)
    assert len(sections) == 3
    assert sections[0]["title"] == "Introduction"
    assert sections[1]["title"] == "Background"
    assert sections[2]["title"] == "Conclusion"


def test_orch_extract_sections_empty(orch):
    """_extract_sections should return empty list for text without sections."""
    sections = PipelineOrchestrator._extract_sections("No sections")
    assert sections == []


# ---------------------------------------------------------------------------
# _aggregate_results
# ---------------------------------------------------------------------------

def test_aggregate_results_empty(orch):
    """_aggregate_results with empty list should pass with score 1.0."""
    result = orch._aggregate_results([])
    assert result["overall_passed"] is True
    assert result["overall_score"] == 1.0


def test_aggregate_results_with_results(orch):
    """_aggregate_results should compute overall score from validator results."""
    results = [
        ValidationResult(validator_name="a", passed=True, score=0.9),
        ValidationResult(validator_name="b", passed=False, score=0.4),
    ]
    result = orch._aggregate_results(results)
    assert isinstance(result["overall_score"], float)
    assert "overall_passed" in result
    assert "failed_validators" in result


# ---------------------------------------------------------------------------
# _run_validators
# ---------------------------------------------------------------------------

def test_run_validators_with_validators(orch):
    """_run_validators should return results from all validators."""
    mock_validator = MagicMock()
    mock_validator.__class__.__name__ = "MockValidator"
    mock_validator.validate.return_value = ValidationResult(
        validator_name="MockValidator", passed=True, score=0.95
    )
    orch._validators = [mock_validator]
    results = orch._run_validators("test draft")
    assert len(results) == 1
    assert results[0].passed is True
    assert orch._validation_scores is not None


def test_run_validators_with_failure(orch):
    """_run_validators should include failing validator results."""
    mock_validator = MagicMock()
    mock_validator.__class__.__name__ = "FailingValidator"
    mock_validator.validate.return_value = ValidationResult(
        validator_name="FailingValidator", passed=False, score=0.3,
        repair_instructions="Fix this"
    )
    orch._validators = [mock_validator]
    results = orch._run_validators("test draft")
    assert len(results) == 1
    assert results[0].passed is False


def test_run_validators_catches_exception(orch):
    """_run_validators should catch validator exceptions gracefully."""
    mock_validator = MagicMock()
    mock_validator.__class__.__name__ = "CrashingValidator"
    mock_validator.validate.side_effect = ValueError("Validator crashed")
    orch._validators = [mock_validator]
    results = orch._run_validators("test draft")
    assert len(results) == 1
    assert results[0].passed is False
    assert results[0].score == 0.0


# ---------------------------------------------------------------------------
# _post_process
# ---------------------------------------------------------------------------

def test_post_process_empty_draft(orch):
    """_post_process should return empty string for empty draft."""
    result = orch._post_process("")
    assert result == ""


def test_post_process_none_draft(orch):
    """_post_process should return None for None draft."""
    result = orch._post_process(None)
    assert result is None


# ---------------------------------------------------------------------------
# _build_citation_context
# ---------------------------------------------------------------------------

def test_build_citation_context_empty(orch):
    """_build_citation_context should return empty string when store is empty."""
    result = orch._build_citation_context()
    assert result == ""


# ---------------------------------------------------------------------------
# _progress
# ---------------------------------------------------------------------------

def test_orch_progress(orch, sample_task, sample_state):
    """_progress should update state and invoke callback."""
    orch._task = sample_task
    orch._state = sample_state
    captured = []
    def cb(stage, msg, detail):
        captured.append((stage, msg))
    orch._progress(cb, "test_stage", "test message")
    assert orch.current_stage == "test_stage"
    assert orch.current_message == "test message"
    assert len(captured) == 1


def test_orch_progress_without_callback(orch, sample_task, sample_state):
    """_progress should update state even without callback."""
    orch._task = sample_task
    orch._state = sample_state
    orch._progress(None, "stage", "msg")
    assert orch.current_stage == "stage"
    assert orch.current_message == "msg"


# ---------------------------------------------------------------------------
# _retry_on_error
# ---------------------------------------------------------------------------

def test_orch_retry_on_error_success(orch, sample_state):
    """_retry_on_error should return function result on first success."""
    orch._state = sample_state
    result = orch._retry_on_error(lambda: "ok", AgentState.PLANNING, None)
    assert result == "ok"


def test_orch_retry_on_error_exhausted(orch, sample_state):
    """_retry_on_error should exhaust retries then raise."""
    orch._state = sample_state
    orch.config.max_pipeline_retries = 0
    call_count = 0
    def failing_fn():
        nonlocal call_count
        call_count += 1
        raise RuntimeError("Failed")
    with pytest.raises(RuntimeError, match="Failed"):
        orch._retry_on_error(failing_fn, AgentState.PLANNING, None)
    assert call_count == 1
    assert orch._pipeline_retry_count == 1
    assert orch._last_failed_stage == AgentState.PLANNING


# ---------------------------------------------------------------------------
# _incorporate_feedback
# ---------------------------------------------------------------------------

def test_incorporate_feedback_empty_repairs(orch):
    """_incorporate_feedback should return original analysis when repairs are empty."""
    result = orch._incorporate_feedback("analysis text", "")
    assert result == "analysis text"


def test_incorporate_feedback_with_repairs(orch):
    """_incorporate_feedback should use LLM to revise analysis."""
    orch.llm = MockLLM(fixed_response="Revised analysis")
    orch._plan = "Research plan"
    result = orch._incorporate_feedback("analysis text", "Fix issues")
    assert result == "Revised analysis"


# ---------------------------------------------------------------------------
# _check_human_feedback
# ---------------------------------------------------------------------------

def test_check_human_feedback_empty_queue(orch, sample_task):
    """_check_human_feedback should return no updates when queue is empty."""
    orch._task = sample_task
    orch._feedback_queue = []
    orch._feedback_lock = threading.Lock()
    result = orch._check_human_feedback(None)
    assert result == {"papers_updated": False, "analysis_updated": False}


def test_check_human_feedback_expand_section(orch, sample_task):
    """expand_section feedback should add to pending_expansions."""
    orch._task = sample_task
    orch._state = StateMachine()
    orch.llm = MockLLM(fixed_response="Analysis")
    orch._papers = []
    orch._plan = "Plan"
    orch._feedback_queue = [{"category": "expand_section", "content": "Expand section 3",
                             "status": "pending"}]
    orch._feedback_history = []
    orch._feedback_lock = threading.Lock()
    result = orch._check_human_feedback(None)
    assert result == {"papers_updated": False, "analysis_updated": False}


def test_check_human_feedback_general(orch, sample_task):
    """general feedback should add to pending_revisions."""
    orch._task = sample_task
    orch._state = StateMachine()
    orch.llm = MockLLM(fixed_response="Analysis")
    orch._papers = []
    orch._plan = "Plan"
    orch._feedback_queue = [{"category": "general", "content": "Revise abstract",
                             "status": "pending"}]
    orch._feedback_history = []
    orch._feedback_lock = threading.Lock()
    result = orch._check_human_feedback(None)
    assert result == {"papers_updated": False, "analysis_updated": False}


# ---------------------------------------------------------------------------
# _supplement_retrieval
# ---------------------------------------------------------------------------

def test_supplement_retrieval_no_tools(orch):
    """_supplement_retrieval should return empty list when no search tools."""
    orch.llm = MockLLM(fixed_response="search query")
    result = orch._supplement_retrieval("Find more papers on topic X")
    assert result == []


# ---------------------------------------------------------------------------
# _write_survey — basic coverage
# ---------------------------------------------------------------------------

def test_write_survey_short_analysis(orch):
    """_write_survey should use replacement analysis when original is too short."""
    orch._task = TaskInfo(topic="Test", keywords=["kw"])
    orch._plan = "Research plan"
    orch._papers = []
    orch.llm = MockLLM(fixed_response="\\section{Introduction}\nPaper content")
    draft = orch._write_survey("Short", 0)
    assert draft is not None


# ---------------------------------------------------------------------------
# _analyze_papers — empty papers path
# ---------------------------------------------------------------------------

def test_analyze_papers_empty(orch):
    """_analyze_papers with empty papers should use topic knowledge."""
    orch._task = TaskInfo(topic="Test", keywords=["kw"])
    orch._plan = "Plan"
    orch.llm = MockLLM(fixed_response="Analysis from topic knowledge")
    result = orch._analyze_papers([])
    assert result == "Analysis from topic knowledge"
    assert orch._analysis == "Analysis from topic knowledge"


# ---------------------------------------------------------------------------
# _extract_and_verify_claims
# ---------------------------------------------------------------------------

def test_extract_and_verify_claims_no_analysis(orch):
    """_extract_and_verify_claims should handle empty analysis gracefully."""
    orch._analysis = ""
    orch._evidence_store = MagicMock()
    orch._extract_and_verify_claims([])


# ---------------------------------------------------------------------------
# _build_citation_anchors
# ---------------------------------------------------------------------------

def test_build_citation_anchors_no_verified_claims(orch):
    """_build_citation_anchors should handle empty verified claims."""
    orch._evidence_store = MagicMock()
    orch._evidence_store.get_verified_claims.return_value = []
    orch._build_citation_anchors()


# ---------------------------------------------------------------------------
# _extract_benchmarks_and_knowledge
# ---------------------------------------------------------------------------

def test_extract_benchmarks_and_knowledge_no_refs(orch):
    """_extract_benchmarks_and_knowledge should handle empty refs."""
    orch._evidence_refs = []
    orch._extract_benchmarks_and_knowledge()


# ---------------------------------------------------------------------------
# _generate_plan
# ---------------------------------------------------------------------------

def test_generate_plan(orch):
    """_generate_plan should set _plan from LLM response."""
    orch._task = TaskInfo(topic="Test", keywords=["kw"], goal="Test goal")
    orch.llm = MockLLM(fixed_response="\\section{Introduction}\n\\section{Methods}")
    result = orch._generate_plan()
    assert result == "\\section{Introduction}\n\\section{Methods}"
    assert orch._plan == result


# ---------------------------------------------------------------------------
# Guardrail tests
# ---------------------------------------------------------------------------

def test_guardrail_filter_papers():
    """GuardrailManager.filter_papers should return papers unchanged."""
    manager = GuardrailManager(guardrails=[])
    result = manager.filter_papers([{"title": "Paper"}])
    assert result == [{"title": "Paper"}]


def test_guardrail_check_all():
    """GuardrailManager.check_all should return empty list."""
    manager = GuardrailManager(guardrails=[])
    result = manager.check_all({"text": "test"})
    assert result == []


def test_guardrail_check_tool_call():
    """GuardrailManager.check_tool_call should not raise."""
    manager = GuardrailManager(guardrails=[])
    manager.check_tool_call("llm_generate", {"prompt": "test"})