from dataclasses import dataclass, field
from typing import Optional
from agent.core.state import AgentState, StateMachine
from agent.core.llm import LLMBase


@dataclass
class HarnessConfig:
    max_papers: int = 20
    max_retries: int = 3
    quality_threshold: float = 0.7
    year_start: int = 2020
    year_end: int = 2026


@dataclass
class TaskInfo:
    topic: str
    keywords: list[str] = field(default_factory=list)
    goal: str = ""
    max_papers: int = 20


class Harness:
    def __init__(self, config: HarnessConfig, llm: LLMBase):
        self.config = config
        self.llm = llm
        self.state = StateMachine()
        self.task: Optional[TaskInfo] = None
        self._iteration_count: int = 0

    def start(self, topic: str, keywords: str = "", goal: str = "") -> None:
        self.task = TaskInfo(
            topic=topic,
            keywords=[k.strip() for k in keywords.split(",") if k.strip()],
            goal=goal,
            max_papers=self.config.max_papers,
        )
        self.state.transition_to(AgentState.PLANNING)

    def get_task_info(self) -> dict:
        if not self.task:
            return {"status": self.state.current_state.name}
        return {
            "topic": self.task.topic,
            "keywords": self.task.keywords,
            "goal": self.task.goal,
            "max_papers": self.task.max_papers,
            "status": self.state.current_state.name,
        }

    def interrupt(self) -> None:
        self.state.interrupt()

    def resume(self) -> None:
        self.state.resume()