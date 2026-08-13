from agent.core.state import AgentState
from agent.core.harness import Harness, HarnessConfig
from agent.core.llm import MockLLM


def test_harness_initial_state():
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    assert h.state.current_state == AgentState.IDLE


def test_harness_start_transitions_to_planning():
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    h.start(topic="Test Topic")
    assert h.state.current_state == AgentState.PLANNING


def test_harness_get_task_info():
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    h.start(topic="Test Topic")
    info = h.get_task_info()
    assert info["topic"] == "Test Topic"
    assert info["status"] == "PLANNING"


def test_harness_interrupt_and_resume():
    llm = MockLLM()
    h = Harness(config=HarnessConfig(), llm=llm)
    h.start(topic="Test")
    h.interrupt()
    assert h.state.current_state == AgentState.INTERRUPTED
    h.resume()
    assert h.state.current_state == AgentState.PLANNING
