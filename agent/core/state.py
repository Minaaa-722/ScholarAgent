from enum import Enum, auto


class AgentState(Enum):
    IDLE = auto()
    PLANNING = auto()
    RETRIEVAL = auto()
    ANALYSIS = auto()
    WRITING = auto()
    VALIDATION = auto()
    FEEDBACK = auto()
    INTERRUPTED = auto()
    COMPLETE = auto()
    ERROR = auto()


# Valid transitions: current_state -> set of allowed next states
_TRANSITIONS = {
    AgentState.IDLE: {AgentState.PLANNING, AgentState.ERROR},
    AgentState.PLANNING: {AgentState.RETRIEVAL, AgentState.FEEDBACK, AgentState.ERROR, AgentState.INTERRUPTED},
    AgentState.RETRIEVAL: {AgentState.ANALYSIS, AgentState.FEEDBACK, AgentState.ERROR, AgentState.INTERRUPTED},
    AgentState.ANALYSIS: {AgentState.WRITING, AgentState.FEEDBACK, AgentState.ERROR, AgentState.INTERRUPTED},
    AgentState.WRITING: {AgentState.VALIDATION, AgentState.FEEDBACK, AgentState.ERROR, AgentState.INTERRUPTED},
    AgentState.VALIDATION: {AgentState.WRITING, AgentState.COMPLETE, AgentState.ERROR, AgentState.INTERRUPTED},
    AgentState.FEEDBACK: {AgentState.WRITING, AgentState.RETRIEVAL, AgentState.ANALYSIS, AgentState.ERROR, AgentState.INTERRUPTED},
    AgentState.INTERRUPTED: {AgentState.PLANNING, AgentState.RETRIEVAL, AgentState.ANALYSIS,
                             AgentState.WRITING, AgentState.VALIDATION, AgentState.COMPLETE, AgentState.ERROR},
    AgentState.COMPLETE: set(),
    AgentState.ERROR: {AgentState.IDLE},
}


class StateMachine:
    def __init__(self):
        self.current_state = AgentState.IDLE
        self._prev_state: AgentState | None = None

    def transition_to(self, target: AgentState) -> None:
        allowed = _TRANSITIONS.get(self.current_state, set())
        if target not in allowed:
            raise ValueError(
                f"Invalid transition: {self.current_state.name} -> {target.name}"
            )
        self._prev_state = self.current_state
        self.current_state = target

    def interrupt(self) -> None:
        if self.current_state in (AgentState.INTERRUPTED, AgentState.IDLE, AgentState.COMPLETE):
            raise ValueError(f"Cannot interrupt from {self.current_state.name}")
        self._prev_state = self.current_state
        self.current_state = AgentState.INTERRUPTED

    def resume(self) -> None:
        if self.current_state != AgentState.INTERRUPTED:
            raise ValueError(f"Not in interrupted state: {self.current_state.name}")
        self.current_state = self._prev_state
        self._prev_state = None

    def is_terminal(self) -> bool:
        return self.current_state in (AgentState.COMPLETE, AgentState.ERROR)