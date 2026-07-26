from dataclasses import dataclass, field
from typing import Optional
from agent.core.state import AgentState, StateMachine
from agent.core.llm import LLMBase
from agent.feedback.base import ValidationResult
from agent.feedback.aggregator import FeedbackAggregator
from agent.feedback.repair_generator import RepairGenerator


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
        self.retry_count: int = 0
        self.has_warnings: bool = False
        self._aggregator = FeedbackAggregator(pass_threshold=config.quality_threshold)
        self._repair_generator = RepairGenerator()

    def start(self, topic: str, keywords: str = "", goal: str = "") -> None:
        self.task = TaskInfo(
            topic=topic,
            keywords=[k.strip() for k in keywords.split(",") if k.strip()],
            goal=goal,
            max_papers=self.config.max_papers,
        )
        self.retry_count = 0
        self.has_warnings = False
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
            "retry_count": self.retry_count,
            "has_warnings": self.has_warnings,
        }

    def inject_feedback(self, results: list[ValidationResult]) -> None:
        report = self._aggregator.aggregate(results)
        if report.overall_passed:
            self.state.transition_to(AgentState.COMPLETE)
            return
        if self.retry_count >= self.config.max_retries:
            self.has_warnings = True
            self.state.transition_to(AgentState.COMPLETE)
            return
        self.retry_count += 1
        self.state.transition_to(AgentState.WRITING)

    def interrupt(self) -> None:
        self.state.interrupt()

    def resume(self) -> None:
        self.state.resume()