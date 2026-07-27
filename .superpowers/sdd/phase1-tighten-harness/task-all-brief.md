# Phase 1: Tighten the Harness — Task Brief (All 4 Tasks)

## Context

This is Phase 1 of a gap-analysis refactoring. The Harness class (`agent/core/harness.py`) is a 993-line monolith. Three subsystems exist as code but are never invoked:
- 5 guardrail classes in `agent/guardrails/`
- 2 memory classes in `agent/memory/`
- `ToolRegistry` in `agent/tools/registry.py`

## Task 1: Extract PipelineOrchestrator

### What

Create `agent/core/pipeline.py` with `PipelineOrchestrator`. Move ALL pipeline orchestration logic out of Harness.

### Move FROM Harness → PipelineOrchestrator

These methods and state fields move exactly as-is (just rehomed):

**Methods:**
- `_pipeline()` — the main stage orchestration loop
- `_generate_plan()` — LLM-based research plan generation
- `_retrieve_papers()` — arXiv + Semantic Scholar search, merge, dedup
- `_analyze_papers()` — LLM-based paper analysis
- `_write_survey()` — LLM-based survey writing with CVPR format
- `_incorporate_feedback()` — LLM-based analysis revision
- `_run_validators()` — run 5 validators on draft
- `_format_repair()` — CVPR LaTeX post-processing
- `_check_human_feedback()` — process feedback queue at stage boundaries
- `_supplement_retrieval()` — additional paper search from feedback
- `_retry_on_error()` — phase-level retry with exponential backoff
- `_ensure_state()` — safe state transition helper
- `_progress()`, `_log()`, `_result()`, `_extract_sections()` — helpers

**State fields:**
- `execution_log`
- `_pipeline_retry_count`, `_last_failed_stage`, `_error_message`
- `_plan`, `_papers`, `_analysis`, `_draft_sections`, `_validation_scores`
- `_retrieved_queries`, `_pending_expansions`, `_pending_revisions`
- `latex_repair_log`

### Keep in Harness

- `HarnessConfig`, `TaskInfo`, `TOOL_DEFINITIONS`
- `__init__()` — now creates ToolRegistry, GuardrailManager, MemoryIntegration, PipelineOrchestrator
- `start()`, `run()`, `run_async()` — delegate to orchestrator
- `get_task_info()`, `get_paper()`, `get_execution_log()` — query methods
- `inject_feedback()`, `submit_human_feedback()` — feedback injection
- `interrupt()`, `resume()`, `restart()` — lifecycle
- `state`, `task`, `retry_count`, `has_warnings`, `feedback_queue`, `feedback_history`
- `current_stage`, `current_message`, `_pipeline_running`, `task_started_at`
- `_safe_llm_call()`, `_safe_transition()`

### PipelineOrchestrator Interface

```python
@dataclass
class PipelineResult:
    paper: str
    status: str  # "complete" | "complete_with_warnings" | "error"
    rounds: int
    execution_log: list[dict]
    latex_repair_log: Optional[dict] = None
    validation_scores: dict = field(default_factory=dict)

class PipelineOrchestrator:
    def __init__(
        self,
        llm: LLMBase,
        tools: ToolRegistry,
        validators: list[Validator],
        guardrails: GuardrailManager,
        config: HarnessConfig,
        latex_repair: LatexFormatRepair,
    ):
        ...

    def run_pipeline(
        self,
        task: TaskInfo,
        feedback_queue: list,
        feedback_lock: threading.Lock,
        on_progress: Optional[ProgressCallback] = None,
    ) -> PipelineResult:
        """Run the full survey-generation pipeline end-to-end."""
        ...
```

### Harness.__init__() changes

```python
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

    # Latex repair
    self._latex_repair = LatexFormatRepair()

    # Orchestrator
    self._orchestrator = PipelineOrchestrator(
        llm=self.llm,
        tools=self._registry,
        validators=self._validators,
        guardrails=self._guardrails,
        config=self.config,
        latex_repair=self._latex_repair,
    )

    # Feedback
    self.feedback_queue: list[dict] = []
    self.feedback_history: list[dict] = []
    self._feedback_lock = threading.Lock()
```

### Harness.run() changes

```python
def run(self, topic, keywords="", goal="", on_progress=None):
    self.start(topic, keywords, goal)
    try:
        result = self._orchestrator.run_pipeline(
            task=self.task,
            feedback_queue=self.feedback_queue,
            feedback_lock=self._feedback_lock,
            on_progress=on_progress,
        )
        # Reconstruct old-style result dict from PipelineResult
        ...
    except Exception as e:
        ...
```

### Harness.start() changes

```python
def start(self, topic, keywords="", goal=""):
    # ... existing reset logic ...
    # Auto-load preferences from memory
    prefs = self._memory.load_preferences(["year_start", "year_end", "max_papers"])
    if prefs.get("year_start"):
        self.config.year_start = int(prefs["year_start"])
    if prefs.get("year_end"):
        self.config.year_end = int(prefs["year_end"])
    if prefs.get("max_papers"):
        self.config.max_papers = int(prefs["max_papers"])
    # ... existing transition logic ...
```

## Task 2: Wire Guardrails via GuardrailManager

### What

Create `agent/guardrails/manager.py` with `GuardrailManager` that wraps all 5 guardrails.

### GuardrailManager Interface

```python
class GuardrailManager:
    def __init__(self, guardrails: Optional[list[Guardrail]] = None):
        self._guardrails = guardrails or [
            OpSafety(),
            RateLimit(),
            SourceFilter(),
            FactBinding(),
            OutputStandard(),
        ]

    def check_all(self, context: dict) -> list[GuardrailResult]:
        """Run all guardrails and return all results."""
        return [g.check(context) for g in self._guardrails]

    def check_tool_call(self, tool_name: str, params: dict) -> GuardrailResult:
        """Check a tool call against OpSafety and RateLimit."""
        for g in self._guardrails:
            if isinstance(g, (OpSafety, RateLimit)):
                result = g.check({"action": tool_name, "params": params})
                if result.verdict != GuardrailVerdict.PASS:
                    return result
        return GuardrailResult(verdict=GuardrailVerdict.PASS, guardrail_name="tool_call")

    def filter_papers(self, papers: list[dict]) -> list[dict]:
        """Filter papers through SourceFilter, return only passing papers."""
        filtered = []
        for p in papers:
            result = self._check_source(p)
            if result.verdict == GuardrailVerdict.PASS:
                filtered.append(p)
        return filtered

    def _check_source(self, paper: dict) -> GuardrailResult:
        for g in self._guardrails:
            if isinstance(g, SourceFilter):
                return g.check({"paper": paper})
        return GuardrailResult(verdict=GuardrailVerdict.PASS, guardrail_name="source")
```

### Integration Points in PipelineOrchestrator

In the moved methods, add guardrail calls:

1. **After paper retrieval** (in `_retrieve_papers` or after it returns): call `self._guardrails.filter_papers(papers)` to filter blacklisted sources
2. **After writing** (in `_run_validators` or after `_write_survey`): call `self._guardrails.check_all({"text": draft})` for FactBinding and OutputStandard checks
3. **Before LLM calls**: call `self._guardrails.check_tool_call("llm_generate", {...})` for RateLimit

### Update `agent/guardrails/__init__.py`:

```python
from agent.guardrails.base import Guardrail, GuardrailResult, GuardrailVerdict
from agent.guardrails.op_safety import OpSafety
from agent.guardrails.rate_limit import RateLimit
from agent.guardrails.source_filter import SourceFilter
from agent.guardrails.fact_binding import FactBinding
from agent.guardrails.output_std import OutputStandard
from agent.guardrails.manager import GuardrailManager

__all__ = [
    "Guardrail", "GuardrailResult", "GuardrailVerdict",
    "OpSafety", "RateLimit", "SourceFilter", "FactBinding", "OutputStandard",
    "GuardrailManager",
]
```

## Task 3: Wire Memory via MemoryIntegration

### What

Create `agent/memory/integration.py` with `MemoryIntegration` that wraps SessionMemory and PersistentMemory.

### MemoryIntegration Interface

```python
class MemoryIntegration:
    def __init__(self):
        self.session = SessionMemory()
        self.persistent = PersistentMemory()

    def load_preferences(self, keys: list[str]) -> dict:
        """Load user preferences from persistent memory."""
        prefs = {}
        for key in keys:
            val = self.persistent.get(key)
            if val is not None:
                prefs[key] = val
        return prefs

    def save_task_history(self, task: TaskInfo, result: dict) -> None:
        """Save task info and result to session memory."""
        history = self.session.get("task_history", [])
        entry = {
            "topic": task.topic,
            "keywords": task.keywords,
            "goal": task.goal,
            "status": result.get("status", ""),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        history.append(entry)
        # Keep last 20 tasks
        if len(history) > 20:
            history = history[-20:]
        self.session.save("task_history", history)

    def save_feedback_history(self, history: list[dict]) -> None:
        """Persist feedback history."""
        self.session.save("feedback_history", history)

    def get_task_history(self) -> list[dict]:
        """Retrieve recent task history from session memory."""
        return self.session.get("task_history", [])
```

### Update `agent/memory/__init__.py`:

```python
from agent.memory.base import MemoryBase
from agent.memory.session import SessionMemory
from agent.memory.persistent import PersistentMemory
from agent.memory.integration import MemoryIntegration

__all__ = ["MemoryBase", "SessionMemory", "PersistentMemory", "MemoryIntegration"]
```

### Integration Points in Harness

1. `__init__()`: Create `self._memory = MemoryIntegration()`
2. `start()`: Auto-load preferences from persistent memory
3. `run()`: After pipeline completes, call `self._memory.save_task_history(self.task, result)`
4. `submit_human_feedback()`: After adding feedback, call `self._memory.save_feedback_history(self.feedback_history)`

## Task 4: Human Feedback Resume Mechanism

### What

Enhance interrupt/resume to actually work with the pipeline loop.

### Changes to PipelineOrchestrator

Add interrupt awareness:

```python
def run_pipeline(self, task, feedback_queue, feedback_lock, on_progress=None):
    # Create a local state reference
    # Check interrupt event before each stage
    if self._is_interrupted():
        return self._interrupted_result()
    
    # At each stage boundary:
    for stage_name, stage_fn in self._stages:
        if self._is_interrupted():
            return self._interrupted_result()
        # run stage...
```

### Changes to Harness

```python
def interrupt(self):
    """Interrupt the running pipeline."""
    self.state.interrupt()
    self._interrupt_event.set()

def resume(self):
    """Resume from interrupted state."""
    if self.state.current_state != AgentState.INTERRUPTED:
        raise ValueError(f"Not in interrupted state: {self.state.current_state.name}")
    prev = self.state.current_state  # will be INTERRUPTED
    self.state.resume()
    self._interrupt_event.clear()
    # If pipeline was running, restart from interrupted stage
    if self.task:
        self.run_async(
            topic=self.task.topic,
            keywords=", ".join(self.task.keywords),
            goal=self.task.goal,
        )
```

### Flow

1. User clicks "Interrupt" → `Harness.interrupt()` → sets threading.Event + state transition
2. PipelineOrchestrator checks event at each stage boundary → if set, returns early
3. User submits feedback → queued (works in any state)
4. User clicks "Resume" → `Harness.resume()` → clears event, restores state, re-launches pipeline
5. On re-launch, task info is already populated, pipeline continues from saved state

## Tests

### New File: `tests/test_pipeline.py`

```python
def test_pipeline_orchestrator_initialization():
    # Test PipelineOrchestrator can be created

def test_pipeline_orchestrator_run_with_mock():
    # Test full pipeline run with MockLLM returns PipelineResult

def test_pipeline_orchestrator_empty_topic():
    # Test edge case
```

### Updates to existing tests

- `tests/test_harness.py` — update imports, verify Harness still works with new architecture
- `tests/test_guardrails.py` — add GuardrailManager tests
- `tests/test_memory.py` — add MemoryIntegration tests

## API Compatibility

The public API must remain unchanged:
- `POST /api/survey` — still works
- `GET /api/survey/status` — still works
- `POST /api/survey/interrupt` — still works
- `POST /api/survey/resume` — now actually works
- `POST /api/survey/restart` — still works
- `GET /api/survey/paper` — still works
- `GET /api/survey/log` — still works
- `/ws/stream/{task_id}` — still works
- `POST /api/feedback` — still works
- `GET /api/feedback/pending` — still works

## Implementation Order

1. Create `agent/guardrails/manager.py` + update `agent/guardrails/__init__.py`
2. Create `agent/memory/integration.py` + update `agent/memory/__init__.py`
3. Create `agent/core/pipeline.py` with PipelineOrchestrator
4. Refactor `agent/core/harness.py` — strip orchestration, wire new subsystems
5. Update tests
6. Run full test suite