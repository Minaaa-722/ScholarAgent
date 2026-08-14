"""Tests for Harness — covering all missing branches and uncovered paths."""
import threading
import pytest
from agent.core.state import AgentState, StateMachine
from agent.core.harness import Harness, HarnessConfig, TaskInfo
from agent.core.llm import MockLLM
from agent.feedback.base import ValidationResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_llm():
    return MockLLM(fixed_response="Mock response")


@pytest.fixture
def harness(mock_llm):
    h = Harness(config=HarnessConfig(), llm=mock_llm)
    return h


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

def test_harness_initial_state():
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    assert h.state.current_state == AgentState.IDLE
    assert h._pipeline_running is False
    assert h.retry_count == 0
    assert h.has_warnings is False
    assert h.execution_log == []
    assert h.last_result is None
    assert h.feedback_queue == []
    assert h.feedback_history == []


def test_harness_start_transitions_to_planning():
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    h.start(topic="Test Topic")
    assert h.state.current_state == AgentState.PLANNING
    assert h.task is not None
    assert h.task.topic == "Test Topic"


def test_harness_start_with_keywords():
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    h.start(topic="Test", keywords="kw1, kw2, kw3")
    assert h.task.keywords == ["kw1", "kw2", "kw3"]


def test_harness_start_with_year_range():
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    h.start(topic="Test", year_start=2019, year_end=2025)
    assert h.config.year_start == 2019
    assert h.config.year_end == 2025


def test_harness_start_with_empty_keywords():
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    h.start(topic="Test", keywords="")
    assert h.task.keywords == []


def test_harness_start_resets_state():
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    h.start(topic="First")
    h.start(topic="Second")
    info = h.get_task_info()
    assert info["topic"] == "Second"


# ---------------------------------------------------------------------------
# get_task_info — various branches
# ---------------------------------------------------------------------------

def test_harness_get_task_info_basic():
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    h.start(topic="Test Topic")
    info = h.get_task_info()
    assert info["topic"] == "Test Topic"
    assert info["status"] == "PLANNING"


def test_get_task_info_no_task():
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    info = h.get_task_info()
    assert "topic" not in info
    assert info["status"] == "IDLE"


def test_get_task_info_with_plan():
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    h.start(topic="Test")
    h._plan = "\\section{Introduction}\nSome text\n\\section{Methods}"
    info = h.get_task_info()
    assert "execution_details" in info
    details = info["execution_details"]
    assert "plan" in details
    assert details["plan"]["section_count"] == 2


def test_get_task_info_with_papers():
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    h.start(topic="Test")
    h._papers = [
        {"title": "Paper A", "authors": ["Author1", "Author2", "Author3", "Author4"],
         "year": 2023, "citation_count": 10, "arxiv_id": "1234", "url": "http://example.com"},
        {"title": "Paper B", "authors": ["Author5"],
         "year": 2024, "citation_count": 5, "url": "http://example.com"},
    ]
    info = h.get_task_info()
    details = info["execution_details"]
    assert "papers" in details
    assert details["papers"]["total"] == 2
    assert "et al." in details["papers"]["list"][0]["authors"]


def test_get_task_info_with_queries():
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    h.start(topic="Test")
    h._retrieved_queries = ["query1", "query2"]
    info = h.get_task_info()
    assert info["execution_details"]["search_queries"] == ["query1", "query2"]


def test_get_task_info_with_analysis():
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    h.start(topic="Test")
    h._analysis = "Analysis result"
    info = h.get_task_info()
    details = info["execution_details"]
    assert "analysis" in details
    assert details["analysis"]["summary"] == "Paper analysis completed"


def test_get_task_info_with_sections():
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    h.start(topic="Test")
    h._draft_sections = [{"title": "Intro", "level": 0}]
    info = h.get_task_info()
    assert info["execution_details"]["sections"] == [{"title": "Intro", "level": 0}]


def test_get_task_info_with_validation_scores():
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    h.start(topic="Test")
    h._validation_scores = {"check_citations": {"score": 0.9, "passed": True}}
    info = h.get_task_info()
    assert info["execution_details"]["validation"] == {"check_citations": {"score": 0.9, "passed": True}}


def test_get_task_info_paper_source_arxiv():
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    h.start(topic="Test")
    h._papers = [{"title": "Paper", "authors": [], "arxiv_id": "1234"}]
    info = h.get_task_info()
    paper = info["execution_details"]["papers"]["list"][0]
    assert paper["source"] == "arxiv"


# ---------------------------------------------------------------------------
# get_paper / get_execution_log
# ---------------------------------------------------------------------------

def test_get_paper_empty():
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    assert h.get_paper() == {}


def test_get_paper_with_result():
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    h.last_result = {"status": "complete", "paper": "full paper text"}
    assert h.get_paper()["status"] == "complete"


def test_get_execution_log_empty():
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    assert h.get_execution_log() == []


def test_get_execution_log_with_entries():
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    h.execution_log.append({"stage": "TEST", "data": "value"})
    assert len(h.get_execution_log()) == 1


# ---------------------------------------------------------------------------
# inject_feedback — all branches
# ---------------------------------------------------------------------------

def test_inject_feedback_passed():
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    h.start(topic="Test")
    # Walk through valid states to reach VALIDATION
    h.state.transition_to(AgentState.RETRIEVAL)
    h.state.transition_to(AgentState.ANALYSIS)
    h.state.transition_to(AgentState.WRITING)
    h.state.transition_to(AgentState.VALIDATION)
    results = [ValidationResult(validator_name="test", passed=True, score=0.95)]
    h.inject_feedback(results)
    # Overall passed → transition to COMPLETE
    assert h.state.current_state == AgentState.COMPLETE


def test_inject_feedback_max_retries():
    llm = MockLLM()
    config = HarnessConfig(max_retries=2)
    h = Harness(config=config, llm=llm)
    h.start(topic="Test")
    h.state.transition_to(AgentState.RETRIEVAL)
    h.state.transition_to(AgentState.ANALYSIS)
    h.state.transition_to(AgentState.WRITING)
    h.state.transition_to(AgentState.VALIDATION)
    h.retry_count = 2  # max_retries reached
    results = [ValidationResult(validator_name="test", passed=False, score=0.3)]
    h.inject_feedback(results)
    assert h.has_warnings is True
    assert h.state.current_state == AgentState.COMPLETE


def test_inject_feedback_retry():
    llm = MockLLM()
    config = HarnessConfig(max_retries=3)
    h = Harness(config=config, llm=llm)
    h.start(topic="Test")
    h.state.transition_to(AgentState.RETRIEVAL)
    h.state.transition_to(AgentState.ANALYSIS)
    h.state.transition_to(AgentState.WRITING)
    h.state.transition_to(AgentState.VALIDATION)
    results = [ValidationResult(validator_name="test", passed=False, score=0.3)]
    h.inject_feedback(results)
    assert h.retry_count == 1
    assert h.state.current_state == AgentState.WRITING


# ---------------------------------------------------------------------------
# interrupt / resume
# ---------------------------------------------------------------------------

def test_harness_interrupt_and_resume():
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    h.start(topic="Test")
    h.interrupt()
    assert h.state.current_state == AgentState.INTERRUPTED
    assert h._interrupt_event.is_set()
    h.resume()
    assert h.state.current_state == AgentState.PLANNING
    assert not h._interrupt_event.is_set()


# ---------------------------------------------------------------------------
# cancel — full reset
# ---------------------------------------------------------------------------

def test_cancel_resets_state():
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    h.start(topic="Test")
    h._pipeline_running = True
    h._papers = [{"title": "Paper"}]
    h.cancel()
    assert h.state.current_state == AgentState.IDLE
    assert h._pipeline_running is False
    assert h.task is None
    assert h._papers == []
    assert h._plan == ""
    assert h._analysis == ""
    assert h._draft_sections == []
    assert h._validation_scores == {}
    assert h._error_message == ""


def test_cancel_bumps_generation():
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    gen_before = h._pipeline_generation
    h.cancel()
    assert h._pipeline_generation == gen_before + 1


def test_cancel_creates_fresh_interrupt_event():
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    old_event = h._interrupt_event
    old_event.set()
    h.cancel()
    assert h._interrupt_event is not old_event
    assert not h._interrupt_event.is_set()


# ---------------------------------------------------------------------------
# submit_human_feedback
# ---------------------------------------------------------------------------

def test_submit_human_feedback():
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    result = h.submit_human_feedback("general", "Please improve the abstract")
    assert result["category"] == "general"
    assert result["content"] == "Please improve the abstract"
    assert result["status"] == "pending"
    assert len(h.feedback_queue) == 1


def test_submit_human_feedback_thread_safe():
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    # Simulate concurrent access
    lock = h._feedback_lock
    with lock:
        h.feedback_queue.append({"dummy": True})
    result = h.submit_human_feedback("expand_section", "Expand section 3")
    assert result["category"] == "expand_section"
    assert len(h.feedback_queue) == 2


# ---------------------------------------------------------------------------
# run — error handling
# ---------------------------------------------------------------------------

def test_run_catches_fatal_error():
    """run() should catch exceptions and return an error result."""
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    # Force _generate_plan to fail by making the LLM raise
    def failing_generate(*args, **kwargs):
        raise RuntimeError("LLM unavailable")
    h.llm.generate = failing_generate
    result = h.run(topic="Test", keywords="kw")
    # The orchestrator catches the error internally and returns PipelineResult(status="error")
    assert result["status"] == "error"


# ---------------------------------------------------------------------------
# run_async — background thread
# ---------------------------------------------------------------------------

def test_run_async_starts_background_thread():
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    h.run_async(topic="Test", keywords="kw")
    assert h._pipeline_running is True
    # Pipeline generation should be incremented
    assert h._pipeline_generation >= 1


def test_run_async_generation_tracking():
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    gen_before = h._pipeline_generation
    h.run_async(topic="Test", keywords="kw")
    assert h._pipeline_generation == gen_before + 1


# ---------------------------------------------------------------------------
# _safe_llm_call
# ---------------------------------------------------------------------------

def test_safe_llm_call_success():
    llm = MockLLM(fixed_response="Response text")
    h = Harness(config=HarnessConfig(), llm=llm)
    resp = h._safe_llm_call("system", "user")
    assert resp.text == "Response text"


def test_safe_llm_call_with_tools():
    llm = MockLLM(fixed_response="Response")
    h = Harness(config=HarnessConfig(), llm=llm)
    resp = h._safe_llm_call("system", "user", use_tools=True)
    assert resp.text == "Response"


def test_safe_llm_call_raises_runtime_error():
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    def failing_generate(*args, **kwargs):
        raise ValueError("API error")
    h.llm.generate = failing_generate
    with pytest.raises(RuntimeError, match="LLM call failed"):
        h._safe_llm_call("system", "user")


# ---------------------------------------------------------------------------
# _safe_transition
# ---------------------------------------------------------------------------

def test_safe_transition_valid():
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    h._safe_transition(AgentState.PLANNING)
    assert h.state.current_state == AgentState.PLANNING


def test_safe_transition_invalid():
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    # IDLE → WRITING is invalid, but _safe_transition should swallow
    h._safe_transition(AgentState.WRITING)
    # State should remain IDLE
    assert h.state.current_state == AgentState.IDLE


# ---------------------------------------------------------------------------
# _progress
# ---------------------------------------------------------------------------

def test_progress_updates_state():
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    h._progress(None, "test_stage", "Test message")
    assert h.current_stage == "test_stage"
    assert h.current_message == "Test message"


def test_progress_with_callback():
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    captured = []
    def cb(stage, msg, detail):
        captured.append((stage, msg))
    h._progress(cb, "stage1", "msg1")
    assert len(captured) == 1
    assert captured[0] == ("stage1", "msg1")


# ---------------------------------------------------------------------------
# _extract_sections
# ---------------------------------------------------------------------------

def test_extract_sections_basic():
    draft = r"""
    \section{Introduction}
    Text here.
    \subsection{Background}
    More text.
    \section{Conclusion}
    """
    sections = Harness._extract_sections(draft)
    assert len(sections) == 3
    assert sections[0] == {"level": 0, "title": "Introduction"}
    assert sections[1] == {"level": 1, "title": "Background"}
    assert sections[2] == {"level": 0, "title": "Conclusion"}


def test_extract_sections_empty():
    sections = Harness._extract_sections("No sections here")
    assert sections == []


def test_extract_sections_subsubsection():
    draft = r"""
    \section{Main}
    \subsection{Sub}
    \subsubsection{SubSub}
    """
    sections = Harness._extract_sections(draft)
    assert len(sections) == 3
    assert sections[2] == {"level": 2, "title": "SubSub"}


# ---------------------------------------------------------------------------
# _result
# ---------------------------------------------------------------------------

def test_result_basic():
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    result = h._result("paper text", "complete", 2)
    assert result["status"] == "complete"
    assert result["paper"] == "paper text"
    assert result["rounds"] == 2
    assert result["retry_count"] == 0
    assert result["has_warnings"] is False


def test_result_with_warnings():
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    h.has_warnings = True
    h.retry_count = 1
    result = h._result("paper", "complete_with_warnings", 3)
    assert result["has_warnings"] is True
    assert result["retry_count"] == 1


def test_result_with_latex_repair_log():
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    # Create a mock repair log
    class MockEntry:
        def __init__(self):
            self.rule = "test_rule"
            self.location = "line 1"
            self.original = "old"
            self.replacement = "new"
    class MockRepairLog:
        def __init__(self):
            self.has_changes = True
            self.change_count = 1
            self.entries = [MockEntry()]
        def summary(self):
            return "1 change applied"
    h.latex_repair_log = MockRepairLog()
    result = h._result("paper", "complete", 1)
    assert "latex_repair_log" in result
    assert result["latex_repair_log"]["change_count"] == 1


def test_result_without_latex_repair_log():
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    h.latex_repair_log = None
    result = h._result("paper", "complete", 1)
    assert "latex_repair_log" not in result


# ---------------------------------------------------------------------------
# _format_repair
# ---------------------------------------------------------------------------

def test_format_repair_runs():
    """_format_repair should run the LatexFormatRepair pipeline."""
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    draft = "\\section{Introduction}\nSome text."
    result = h._format_repair(draft)
    assert isinstance(result, str)
    # The repair should return the fixed draft
    assert result is not None


# ---------------------------------------------------------------------------
# restart
# ---------------------------------------------------------------------------

def test_restart_requires_error_state():
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    with pytest.raises(ValueError, match="Can only restart from ERROR state"):
        h.restart()


def test_restart_requires_task():
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    # Force state to ERROR
    h.state = StateMachine()
    h.state.transition_to(AgentState.PLANNING)
    h.state.transition_to(AgentState.ERROR)
    with pytest.raises(ValueError, match="No task to restart"):
        h.restart()


def test_restart_resets_and_launches():
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    h.start(topic="Test", keywords="kw")
    # Force state to ERROR
    h.state = StateMachine()
    h.state.transition_to(AgentState.PLANNING)
    h.state.transition_to(AgentState.RETRIEVAL)
    h.state.transition_to(AgentState.ERROR)
    h.restart()
    # After restart, should be running async
    assert h._pipeline_retry_count == 0
    assert h._last_failed_stage is None
    assert h._error_message == ""


# ---------------------------------------------------------------------------
# _ensure_state
# ---------------------------------------------------------------------------

def test_ensure_state_already_there():
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    h.state.transition_to(AgentState.PLANNING)
    h._ensure_state(AgentState.PLANNING)
    assert h.state.current_state == AgentState.PLANNING


def test_ensure_state_transitions():
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    h.state.transition_to(AgentState.PLANNING)
    h._ensure_state(AgentState.RETRIEVAL)
    assert h.state.current_state == AgentState.RETRIEVAL


# ---------------------------------------------------------------------------
# _log
# ---------------------------------------------------------------------------

def test_log_appends_entry():
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    h._log("TEST", {"key": "value"})
    assert len(h.execution_log) == 1
    assert h.execution_log[0]["stage"] == "TEST"
    assert h.execution_log[0]["key"] == "value"
    assert "timestamp" in h.execution_log[0]


# ---------------------------------------------------------------------------
# _run_validators (called via inject_feedback, but test the method directly)
# ---------------------------------------------------------------------------

def test_run_validators_with_citations():
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    draft = "Some text \\cite{ref1} and \\cite{ref2,ref3}."
    results = h._run_validators(draft)
    assert isinstance(results, list)
    assert len(results) > 0
    assert h._validation_scores is not None


def test_run_validators_empty_draft():
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    results = h._run_validators("")
    assert isinstance(results, list)


# ---------------------------------------------------------------------------
# _sync_orchestrator_state
# ---------------------------------------------------------------------------

def test_sync_orchestrator_state():
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    # Set orchestrator state
    h._orchestrator._papers = [{"title": "Synced"}]
    h._orchestrator._plan = "Synced plan"
    h._orchestrator._analysis = "Synced analysis"
    h._orchestrator._draft_sections = [{"title": "Synced Section"}]
    h._orchestrator._validation_scores = {"check": {"score": 0.8}}
    h._orchestrator._retrieved_queries = ["q1"]
    h._orchestrator._pipeline_retry_count = 2
    h._orchestrator._error_message = "sync error"
    h._sync_orchestrator_state()
    assert h._papers == [{"title": "Synced"}]
    assert h._plan == "Synced plan"
    assert h._analysis == "Synced analysis"
    assert h._draft_sections == [{"title": "Synced Section"}]
    assert h._validation_scores == {"check": {"score": 0.8}}
    assert h._retrieved_queries == ["q1"]
    assert h._pipeline_retry_count == 2
    assert h._error_message == "sync error"


# ---------------------------------------------------------------------------
# _retry_on_error
# ---------------------------------------------------------------------------

def test_retry_on_error_success_first_try():
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    h.start(topic="Test")
    result = h._retry_on_error(lambda: "success", AgentState.PLANNING, None)
    assert result == "success"


def test_retry_on_error_fails_then_raises():
    llm = MockLLM()
    config = HarnessConfig(max_pipeline_retries=0)
    h = Harness(config=config, llm=llm)
    h.start(topic="Test")
    call_count = 0
    def failing_fn():
        nonlocal call_count
        call_count += 1
        raise RuntimeError("Stage failed")
    with pytest.raises(RuntimeError, match="Stage failed"):
        h._retry_on_error(failing_fn, AgentState.PLANNING, None)
    assert call_count == 1  # Only 1 attempt since max_pipeline_retries = 0
    assert h._pipeline_retry_count == 1
    assert h._last_failed_stage == AgentState.PLANNING