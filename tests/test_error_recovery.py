"""Tests for error recovery in the Agent harness."""
import pytest
from agent.core.state import AgentState
from agent.core.harness import Harness, HarnessConfig
from agent.core.llm import MockLLM


class TestRetryOnError:
    """Phase-level retry logic."""

    def test_retry_eventually_succeeds(self):
        """Retry after transient failure, then succeed."""
        llm = MockLLM(fixed_response="plan content")
        h = Harness(HarnessConfig(max_pipeline_retries=2), llm)
        h.task = type("Task", (), {"topic": "test", "keywords": [], "goal": "", "max_papers": 20})()
        h.state.current_state = AgentState.PLANNING

        call_count = [0]

        def flaky_fn():
            call_count[0] += 1
            if call_count[0] < 2:  # Fail first call
                raise ConnectionError("API timeout")
            return "success"

        result = h._retry_on_error(flaky_fn, AgentState.PLANNING, None)
        assert result == "success"
        assert call_count[0] == 2  # 1 fail + 1 success

    def test_retry_exhausted_raises(self):
        """All retries exhausted should raise the original exception."""
        llm = MockLLM(fixed_response="plan content")
        h = Harness(HarnessConfig(max_pipeline_retries=1), llm)
        h.task = type("Task", (), {"topic": "test", "keywords": [], "goal": "", "max_papers": 20})()
        h.state.current_state = AgentState.PLANNING

        def always_fails():
            raise RuntimeError("API unreachable")

        with pytest.raises(RuntimeError, match="API unreachable"):
            h._retry_on_error(always_fails, AgentState.PLANNING, None)

        assert h._pipeline_retry_count == 2  # 2 attempts (1 initial + 1 retry)
        assert h._last_failed_stage == AgentState.PLANNING
        assert h.state.current_state == AgentState.ERROR

    def test_retry_succeeds_first_try(self):
        """No retry needed when stage succeeds immediately."""
        llm = MockLLM(fixed_response="plan content")
        h = Harness(HarnessConfig(max_pipeline_retries=2), llm)
        h.task = type("Task", (), {"topic": "test", "keywords": [], "goal": "", "max_papers": 20})()
        h.state.current_state = AgentState.PLANNING

        def works_first_time():
            return "immediate success"

        result = h._retry_on_error(works_first_time, AgentState.PLANNING, None)
        assert result == "immediate success"
        assert h._pipeline_retry_count == 0  # Never failed
        assert h._error_message == ""

    def test_retry_transitions_to_error(self):
        """Each failure transitions state to ERROR."""
        llm = MockLLM(fixed_response="plan content")
        h = Harness(HarnessConfig(max_pipeline_retries=1), llm)
        h.task = type("Task", (), {"topic": "test", "keywords": [], "goal": "", "max_papers": 20})()
        h.state.current_state = AgentState.PLANNING
        call_count = [0]

        def fails_twice():
            call_count[0] += 1
            raise ValueError("bad data")

        with pytest.raises(ValueError):
            h._retry_on_error(fails_twice, AgentState.PLANNING, None)

        assert h.state.current_state == AgentState.ERROR


class TestRestart:
    """One-click restart from ERROR state."""

    def test_restart_from_error(self):
        """Restart should re-launch with saved task params."""
        llm = MockLLM(fixed_response="plan content")
        h = Harness(HarnessConfig(), llm)
        h.task = type("Task", (), {"topic": "test_topic", "keywords": ["kw1"], "goal": "test goal"})()
        h.state.current_state = AgentState.ERROR
        h._error_message = "something broke"

        h.restart()

        # After restart, should have started a new pipeline
        assert h._pipeline_running is True
        assert h._error_message == ""  # Reset

    def test_restart_not_error_raises(self):
        """Restart from non-ERROR state should raise."""
        llm = MockLLM(fixed_response="plan content")
        h = Harness(HarnessConfig(), llm)
        h.state.current_state = AgentState.COMPLETE

        with pytest.raises(ValueError, match="ERROR"):
            h.restart()

    def test_restart_no_task_raises(self):
        """Restart with no saved task should raise."""
        llm = MockLLM(fixed_response="plan content")
        h = Harness(HarnessConfig(), llm)
        h.task = None
        h.state.current_state = AgentState.ERROR

        with pytest.raises(ValueError, match="No task"):
            h.restart()


class TestGetTaskInfo:
    """Error fields in task info."""

    def test_error_fields_in_info(self):
        """get_task_info should include error, retry count, and failed stage."""
        llm = MockLLM(fixed_response="plan content")
        h = Harness(HarnessConfig(), llm)
        h.task = type("Task", (), {"topic": "test", "keywords": [], "goal": "", "max_papers": 20})()
        h.state.current_state = AgentState.ERROR
        h._error_message = "connection failed"
        h._pipeline_retry_count = 2
        h._last_failed_stage = AgentState.WRITING

        info = h.get_task_info()
        assert info["error"] == "connection failed"
        assert info["pipeline_retry_count"] == 2
        assert info["last_failed_stage"] == "WRITING"

    def test_error_fields_empty_when_no_error(self):
        """Error fields should be empty/default when no error."""
        llm = MockLLM(fixed_response="plan content")
        h = Harness(HarnessConfig(), llm)
        h.task = type("Task", (), {"topic": "test", "keywords": [], "goal": "", "max_papers": 20})()

        info = h.get_task_info()
        assert info["error"] == ""
        assert info["pipeline_retry_count"] == 0
        assert info["last_failed_stage"] == ""
