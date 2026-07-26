import pytest
from agent.core.state import AgentState, StateMachine


def test_state_machine_initial_state():
    sm = StateMachine()
    assert sm.current_state == AgentState.IDLE


def test_state_machine_valid_transition():
    sm = StateMachine()
    sm.transition_to(AgentState.PLANNING)
    assert sm.current_state == AgentState.PLANNING


def test_state_machine_invalid_transition():
    sm = StateMachine()
    with pytest.raises(ValueError, match="Invalid transition"):
        sm.transition_to(AgentState.COMPLETE)  # Cannot go from IDLE to COMPLETE


def test_state_machine_full_cycle():
    sm = StateMachine()
    expected = [
        AgentState.PLANNING,
        AgentState.RETRIEVAL,
        AgentState.ANALYSIS,
        AgentState.WRITING,
        AgentState.VALIDATION,
        AgentState.COMPLETE,
    ]
    for state in expected:
        sm.transition_to(state)
    assert sm.current_state == AgentState.COMPLETE


def test_state_machine_can_interrupt():
    sm = StateMachine()
    sm.transition_to(AgentState.PLANNING)
    sm.transition_to(AgentState.RETRIEVAL)
    sm.interrupt()
    assert sm.current_state == AgentState.INTERRUPTED
    sm.resume()
    assert sm.current_state == AgentState.RETRIEVAL


def test_state_machine_is_terminal():
    sm = StateMachine()
    for s in [AgentState.PLANNING, AgentState.RETRIEVAL, AgentState.ANALYSIS,
              AgentState.WRITING, AgentState.VALIDATION, AgentState.COMPLETE]:
        sm.transition_to(s)
    assert sm.is_terminal() is True