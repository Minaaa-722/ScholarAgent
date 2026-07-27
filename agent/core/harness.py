import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from agent.core.state import AgentState, StateMachine
from agent.core.llm import LLMBase
from agent.core.pipeline import HarnessConfig, PipelineOrchestrator, PipelineResult, TaskInfo, ProgressCallback
from agent.feedback.base import ValidationResult
from agent.feedback.aggregator import FeedbackAggregator
from agent.feedback.check_citations import CitationChecker
from agent.feedback.check_coherence import CoherenceChecker
from agent.feedback.check_word_count import WordCountChecker
from agent.feedback.detect_hallucination import HallucinationDetector
from agent.feedback.polish_language import LanguagePolisher
from agent.guardrails.manager import GuardrailManager
from agent.memory.integration import MemoryIntegration
from agent.tools.registry import ToolRegistry
from agent.tools.retrieval import ArxivSearch, SemanticScholarSearch, MergeResults
from agent.tools.processing import SortByCitation, FormatBibtex

# Re-export for backward compatibility
from agent.core.pipeline import HarnessConfig, TaskInfo, ProgressCallback  # noqa: F401

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Harness — public API facade
# ---------------------------------------------------------------------------
class Harness:
    """Public API facade for the survey-generation pipeline.

    Owns config, state, and lifecycle control.  Delegates pipeline execution
    to PipelineOrchestrator.
    """

    def __init__(self, config: HarnessConfig, llm: LLMBase):
        self.config = config
        self.llm = llm
        self.state = StateMachine()
        self.task: Optional[TaskInfo] = None
        self.retry_count: int = 0
        self.has_warnings: bool = False
        self._pipeline_running: bool = False
        self.current_stage: str = ""
        self.current_message: str = ""
        self.task_started_at: str = ""
        self.last_result: Optional[dict] = None
        self._interrupt_event = threading.Event()

        # Tools
        self._registry = ToolRegistry()
        self._registry.register(ArxivSearch())
        self._registry.register(SemanticScholarSearch())
        self._registry.register(MergeResults())
        self._registry.register(SortByCitation())
        self._registry.register(FormatBibtex())

        # Validators
        self._validators = [
            CitationChecker(),
            CoherenceChecker(),
            WordCountChecker(min_words=200, max_words=8000),
            HallucinationDetector(),
            LanguagePolisher(),
        ]

        # Guardrails
        self._guardrails = GuardrailManager()

        # Memory
        self._memory = MemoryIntegration()

        # Latex repair (optional - LatexFormatRepair may not be available)
        try:
            from agent.feedback.latex_repair import LatexFormatRepair
            self._latex_repair = LatexFormatRepair()
        except ImportError:
            self._latex_repair = None
            logger.info("LatexFormatRepair not available — format repair disabled")

        # Pipeline orchestrator
        self._orchestrator = PipelineOrchestrator(
            llm=self.llm,
            tools=self._registry,
            validators=self._validators,
            guardrails=self._guardrails,
            config=self.config,
            latex_repair=self._latex_repair,
        )
        self._orchestrator.set_interrupt_event(self._interrupt_event)

        # Feedback
        self.feedback_queue: list[dict] = []
        self.feedback_history: list[dict] = []
        self._feedback_lock = threading.Lock()

        # Aggregator for inject_feedback
        self._aggregator = FeedbackAggregator(pass_threshold=config.quality_threshold)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def start(self, topic: str, keywords: str = "", goal: str = "") -> None:
        self.task = TaskInfo(
            topic=topic,
            keywords=[k.strip() for k in keywords.split(",") if k.strip()],
            goal=goal,
            max_papers=self.config.max_papers,
        )
        self.retry_count = 0
        self.has_warnings = False
        self.last_result = None
        self.task_started_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        self.current_stage = ""
        self.current_message = ""
        # Reset feedback
        self.feedback_queue = []
        self.feedback_history = []

        # Auto-load preferences from memory
        prefs = self._memory.load_preferences(
            ["year_start", "year_end", "max_papers"]
        )
        if prefs.get("year_start"):
            self.config.year_start = int(prefs["year_start"])
        if prefs.get("year_end"):
            self.config.year_end = int(prefs["year_end"])
        if prefs.get("max_papers"):
            self.config.max_papers = int(prefs["max_papers"])

        # Reset state machine if in terminal state
        if self.state.is_terminal():
            self.state = StateMachine()
        self.state.transition_to(AgentState.PLANNING)

    def get_task_info(self) -> dict:
        error_info = self._orchestrator.get_error_info()
        base = {
            "pipeline_running": self._pipeline_running,
            "current_stage": self.current_stage,
            "current_message": self.current_message,
            "feedback_queue": self.feedback_queue,
            "feedback_history": self.feedback_history,
            **error_info,
        }
        if not self.task:
            base["status"] = self.state.current_state.name
            return base
        return {
            "topic": self.task.topic,
            "keywords": self.task.keywords,
            "goal": self.task.goal,
            "max_papers": self.task.max_papers,
            "status": self.state.current_state.name,
            "retry_count": self.retry_count,
            "has_warnings": self.has_warnings,
            "task_started_at": self.task_started_at,
            **base,
        }

    def get_paper(self) -> dict:
        """Return the final pipeline result or empty dict."""
        return self.last_result or {}

    def get_execution_log(self) -> list[dict]:
        """Return the execution log from the last pipeline run."""
        if self.last_result:
            return self.last_result.get("execution_log", [])
        return []

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
        """Interrupt the running pipeline."""
        self.state.interrupt()
        self._interrupt_event.set()
        logger.info("Pipeline interrupt requested")

    def resume(self) -> None:
        """Resume from interrupted state."""
        if self.state.current_state != AgentState.INTERRUPTED:
            raise ValueError(
                f"Not in interrupted state: {self.state.current_state.name}"
            )
        self.state.resume()
        self._interrupt_event.clear()
        logger.info("Pipeline resume requested — re-launching from %s", self.state.current_state.name)

        # Re-launch the pipeline if we have a task
        if self.task:
            self.run_async(
                topic=self.task.topic,
                keywords=", ".join(self.task.keywords),
                goal=self.task.goal,
            )

    def restart(self) -> None:
        """Re-launch the pipeline with the same task parameters from ERROR state."""
        if self.state.current_state != AgentState.ERROR:
            raise ValueError("Can only restart from ERROR state")
        if not self.task:
            raise ValueError("No task to restart")

        self._orchestrator.reset_error_state()

        self.run_async(
            topic=self.task.topic,
            keywords=", ".join(self.task.keywords),
            goal=self.task.goal,
        )

    def submit_human_feedback(self, category: str, content: str) -> dict:
        """External API to inject human feedback."""
        import uuid
        feedback = {
            "id": str(uuid.uuid4())[:8],
            "category": category,
            "content": content,
            "status": "pending",
            "received_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        with self._feedback_lock:
            self.feedback_queue.append(feedback)
        # Persist feedback history
        self._memory.save_feedback_history(self.feedback_history)
        return feedback

    # ------------------------------------------------------------------
    # Full pipeline run
    # ------------------------------------------------------------------
    def run(
        self,
        topic: str,
        keywords: str = "",
        goal: str = "",
        on_progress: Optional[ProgressCallback] = None,
    ) -> dict:
        """Run the full survey-generation pipeline end-to-end.

        Returns a result dict with keys:
          - status: "complete" | "complete_with_warnings" | "error" | "interrupted"
          - paper: full survey text (CVPR format)
          - execution_log: list of stage records
          - rounds: number of writing-validation rounds
          - error: error message if status is "error"
        """
        self.start(topic, keywords, goal)

        try:
            pipeline_result = self._orchestrator.run_pipeline(
                task=self.task,
                state=self.state,
                feedback_queue=self.feedback_queue,
                feedback_lock=self._feedback_lock,
                on_progress=on_progress,
            )
            result = self._pipeline_result_to_dict(pipeline_result)
            self.last_result = result
            # Save task history
            self._memory.save_task_history(self.task, result)
            return result
        except Exception as e:
            logger.exception("Pipeline failed with fatal error")
            self._safe_transition(AgentState.ERROR)
            result = {
                "status": "error",
                "error": str(e),
                "execution_log": [],
            }
            self.last_result = result
            return result

    def run_async(
        self,
        topic: str,
        keywords: str = "",
        goal: str = "",
        on_progress: Optional[ProgressCallback] = None,
    ) -> None:
        """Run the pipeline in a background thread."""
        self._pipeline_running = True
        self.current_stage = "starting"
        self.current_message = "Starting pipeline…"

        def _target():
            try:
                # Wrap on_progress to update harness fields
                def _wrapped_progress(stage: str, msg: str, detail: Optional[dict] = None):
                    self.current_stage = stage
                    self.current_message = msg
                    if on_progress:
                        on_progress(stage, msg, detail or self.get_task_info())

                self.last_result = self.run(topic, keywords, goal, _wrapped_progress)
            except Exception:
                logger.exception("Background pipeline thread failed")
            finally:
                self._pipeline_running = False

        thread = threading.Thread(target=_target, daemon=True)
        thread.start()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _pipeline_result_to_dict(self, pr: PipelineResult) -> dict:
        """Convert PipelineResult to the old-style dict format."""
        result = {
            "status": pr.status,
            "paper": pr.paper,
            "rounds": pr.rounds,
            "retry_count": self.retry_count,
            "has_warnings": self.has_warnings or (pr.status == "complete_with_warnings"),
            "task": self.get_task_info(),
            "execution_log": pr.execution_log,
        }
        if pr.latex_repair_log is not None:
            result["latex_repair_log"] = pr.latex_repair_log
        if pr.validation_scores:
            result["validation_scores"] = pr.validation_scores
        return result

    def _safe_transition(self, target: AgentState) -> None:
        """Attempt a state transition; log and swallow if invalid."""
        try:
            self.state.transition_to(target)
        except ValueError as e:
            logger.warning("State transition skipped: %s", e)