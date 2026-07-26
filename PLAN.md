# ScholarAgent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a self-coded Coding Agent Harness that generates CVPR-style survey papers from a research topic via multi-source literature retrieval, analysis, and feedback-driven writing.

**Architecture:** Python agent harness (state machine + tool dispatch + guardrails + memory + feedback loop) exposed via FastAPI, with a React Web UI consuming REST + WebSocket. No third-party agent frameworks — all harness code is self-implemented.

**Tech Stack:** Python 3.11+, FastAPI, React + TypeScript, SQLite, PyMuPDF, keyring, Docker, GitHub Actions

## Global Constraints

1. No third-party agent frameworks (no LangChain, AutoGen, CrewAI, LlamaIndex agent, etc.)
2. LLM abstraction layer must support mock replacement for deterministic testing
3. All mechanisms (guardrails, validators, feedback) must be code, not prompts — verifiable via unit tests without real LLM
4. TDD: red → green → refactor for every task
5. API keys must never be hardcoded in source code or committed to Git
6. Python 3.11+ for backend, React + TypeScript for frontend
7. FastAPI for API layer, SQLite for persistent memory
8. Docker for distribution, GitHub Actions for CI
9. Feedback loop is the deep dimension — 5 validators with multi-round correction
10. Every task ends with an independently testable deliverable

---

## File Structure

```
ScholarAgent/
├── agent/
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── harness.py          # Agent Harness main loop
│   │   ├── llm.py              # LLM abstraction layer
│   │   └── state.py            # State machine
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── base.py             # Tool base class + ToolResult
│   │   ├── registry.py         # ToolRegistry
│   │   ├── retrieval.py        # ArxivSearch, SemanticScholarSearch, GoogleScholarSearch, MergeResults
│   │   ├── processing.py       # PdfDownload, PdfParse, Dedup, SortByCitation, FormatBibtex
│   │   ├── writing.py          # WriteChapter, ExpandParagraph, TruncateParagraph, InsertReferences, FormatCvpr
│   │   └── auxiliary.py        # WebSearch, CheckArxivUpdates, ShellExec
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── base.py             # Memory base class
│   │   ├── session.py          # SessionMemory
│   │   └── persistent.py       # PersistentMemory
│   ├── feedback/
│   │   ├── __init__.py
│   │   ├── base.py             # Validator base class
│   │   ├── check_citations.py  # CitationChecker
│   │   ├── detect_hallucination.py  # HallucinationDetector
│   │   ├── check_word_count.py # WordCountChecker
│   │   ├── polish_language.py  # LanguagePolisher
│   │   ├── check_coherence.py  # CoherenceChecker
│   │   ├── aggregator.py       # FeedbackAggregator
│   │   └── repair_generator.py # RepairGenerator
│   └── guardrails/
│       ├── __init__.py
│       ├── base.py             # Guardrail base class + GuardrailResult
│       ├── source_filter.py    # SourceFilter
│       ├── fact_binding.py     # FactBinding
│       ├── op_safety.py        # OpSafety
│       ├── rate_limit.py       # RateLimit
│       └── output_std.py       # OutputStandard
├── api/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app
│   ├── models.py               # Pydantic models
│   └── routes/
│       ├── __init__.py
│       ├── survey.py
│       ├── progress.py
│       ├── feedback.py
│       └── memory.py
├── web/
│   ├── public/
│   │   └── index.html
│   ├── src/
│   │   ├── index.tsx
│   │   ├── App.tsx
│   │   ├── api/
│   │   │   └── client.ts
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx
│   │   │   ├── ResearchCreation.tsx
│   │   │   ├── AgentExecution.tsx
│   │   │   ├── KnowledgeExplorer.tsx
│   │   │   └── FinalReview.tsx
│   │   └── components/
│   │       ├── Layout.tsx
│   │       ├── StatusBadge.tsx
│   │       ├── ProgressBar.tsx
│   │       └── PaperGraph.tsx
│   ├── package.json
│   └── tsconfig.json
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_llm.py
│   ├── test_state.py
│   ├── test_harness.py
│   ├── test_tools.py
│   ├── test_guardrails.py
│   ├── test_memory.py
│   ├── test_feedback.py
│   └── test_demo.py
├── memory/
│   ├── session/
│   └── persistent/
│       └── .gitkeep
├── .env.example
├── .gitignore
├── Dockerfile
├── Makefile
├── requirements.txt
├── README.md
├── SPEC.md
├── PLAN.md
├── SPEC_PROCESS.md
├── AGENT_LOG.md
├── REFLECTION.md
└── .github/
    └── workflows/
        └── ci.yml
```

---

### Task 1: Project Scaffolding + LLM Abstraction Layer

**Files:**
- Create: `requirements.txt`
- Create: `Makefile`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `agent/__init__.py`
- Create: `agent/core/__init__.py`
- Create: `agent/core/llm.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/test_llm.py`

**Interfaces:**
- Consumes: nothing (first task)
- Produces: `LLMBase` (abstract base), `MockLLM` (test double), `OpenAILLM` (real), `LLMResponse` (dataclass)

- [ ] **Step 1: Write the failing test for LLM abstraction**

Create `tests/test_llm.py`:

```python
import pytest
from agent.core.llm import LLMBase, MockLLM, LLMResponse

def test_mock_llm_returns_fixed_response():
    llm = MockLLM(fixed_response="Test output")
    response = llm.generate("system prompt", "user message")
    assert response.text == "Test output"
    assert response.tool_calls == []

def test_mock_llm_returns_tool_call():
    llm = MockLLM(fixed_tool_call={"name": "test_tool", "arguments": {"key": "value"}})
    response = llm.generate("system", "call tool")
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0]["name"] == "test_tool"

def test_mock_llm_records_conversation():
    llm = MockLLM(fixed_response="ok")
    llm.generate("sys1", "msg1")
    llm.generate("sys2", "msg2")
    assert len(llm.conversation_history) == 2
    assert llm.conversation_history[0] == ("sys1", "msg1")

def test_llm_base_cannot_be_instantiated():
    with pytest.raises(TypeError):
        LLMBase()  # Abstract class
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ScholarAgent && python -m pytest tests/test_llm.py -v
```
Expected: FAIL with `ModuleNotFoundError` or `ImportError`

- [ ] **Step 3: Write minimal implementation**

Create `agent/core/llm.py`:

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LLMResponse:
    text: str
    tool_calls: list[dict] = field(default_factory=list)


class LLMBase(ABC):
    @abstractmethod
    def generate(
        self,
        system_prompt: str,
        user_message: str,
        tools: Optional[list[dict]] = None,
    ) -> LLMResponse:
        ...


class MockLLM(LLMBase):
    def __init__(
        self,
        fixed_response: str = "",
        fixed_tool_call: Optional[dict] = None,
    ):
        self.fixed_response = fixed_response
        self.fixed_tool_call = fixed_tool_call
        self.conversation_history: list[tuple[str, str]] = []

    def generate(
        self,
        system_prompt: str,
        user_message: str,
        tools: Optional[list[dict]] = None,
    ) -> LLMResponse:
        self.conversation_history.append((system_prompt, user_message))
        tool_calls = []
        if self.fixed_tool_call:
            tool_calls = [self.fixed_tool_call]
        return LLMResponse(text=self.fixed_response, tool_calls=tool_calls)


class OpenAILLM(LLMBase):
    def __init__(self, api_key: str, model: str = "gpt-4o"):
        self.api_key = api_key
        self.model = model

    def generate(
        self,
        system_prompt: str,
        user_message: str,
        tools: Optional[list[dict]] = None,
    ) -> LLMResponse:
        # Real implementation calls OpenAI API
        # Stub for now — will be filled in during integration
        raise NotImplementedError("OpenAI integration requires API key setup")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd ScholarAgent && python -m pytest tests/test_llm.py -v
```
Expected: All 4 tests PASS

- [ ] **Step 5: Create project scaffolding files**

Create `requirements.txt`:
```
fastapi==0.111.0
uvicorn==0.30.1
websockets==12.0
pydantic==2.7.4
pytest==8.2.2
pytest-asyncio==0.23.7
```

Create `Makefile`:
```makefile
.PHONY: test install run

test:
	python -m pytest tests/ -v

install:
	pip install -r requirements.txt

run-api:
	uvicorn api.main:app --reload --port 8000
```

Create `.env.example`:
```
# LLM API Key (required)
LLM_API_KEY=your-api-key-here

# LLM Model (optional, default: gpt-4o)
LLM_MODEL=gpt-4o

# Semantic Scholar API Key (optional)
SEMANTIC_SCHOLAR_API_KEY=

# Google Scholar Cookie (optional)
GOOGLE_SCHOLAR_COOKIE=
```

Create `.gitignore`:
```
# Python
__pycache__/
*.py[cod]
*.egg-info/
.venv/
venv/

# Environment
.env
.env.local

# Memory
memory/session/
memory/persistent/*.db

# Node
node_modules/
web/dist/

# IDE
.idea/
.vscode/
*.swp
```

Create `agent/__init__.py`, `agent/core/__init__.py`, `tests/__init__.py` — all empty files.

Create `tests/conftest.py`:
```python
import pytest
from agent.core.llm import MockLLM


@pytest.fixture
def mock_llm():
    return MockLLM(fixed_response="Mock response")


@pytest.fixture
def mock_llm_with_tool():
    return MockLLM(fixed_tool_call={
        "name": "arxiv_search",
        "arguments": {"query": "transformer"}
    })
```

- [ ] **Step 6: Run all tests to verify scaffolding works**

```bash
cd ScholarAgent && python -m pytest tests/ -v
```
Expected: All 4 tests PASS

- [ ] **Step 7: Commit**

```bash
git init
git add -A
git commit -m "feat: project scaffolding + LLM abstraction layer with mock support"
```

---

### Task 2: State Machine + Agent Harness Main Loop

**Files:**
- Create: `agent/core/state.py`
- Create: `agent/core/harness.py`
- Create: `tests/test_state.py`
- Create: `tests/test_harness.py`

**Interfaces:**
- Consumes: `LLMBase`, `MockLLM`, `LLMResponse` from Task 1
- Produces: `AgentState` (enum), `StateMachine`, `Harness` (main loop), `HarnessConfig` (dataclass)

- [ ] **Step 1: Write failing tests for state machine**

Create `tests/test_state.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ScholarAgent && python -m pytest tests/test_state.py -v
```
Expected: FAIL with ImportError

- [ ] **Step 3: Write minimal state machine implementation**

Create `agent/core/state.py`:

```python
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
    AgentState.FEEDBACK: {AgentState.WRITING, AgentState.RETRIEVAL, AgentState.ERROR, AgentState.INTERRUPTED},
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
        return self.current_state == AgentState.COMPLETE
```

- [ ] **Step 4: Run state tests to verify they pass**

```bash
cd ScholarAgent && python -m pytest tests/test_state.py -v
```
Expected: All 6 tests PASS

- [ ] **Step 5: Write failing tests for Harness main loop**

Create `tests/test_harness.py`:

```python
import pytest
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
```

- [ ] **Step 6: Run harness tests to verify they fail**

```bash
cd ScholarAgent && python -m pytest tests/test_harness.py -v
```
Expected: FAIL with ImportError

- [ ] **Step 7: Write minimal Harness implementation**

Create `agent/core/harness.py`:

```python
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
```

- [ ] **Step 8: Run harness tests to verify they pass**

```bash
cd ScholarAgent && python -m pytest tests/test_harness.py -v
```
Expected: All 4 tests PASS

- [ ] **Step 9: Run all tests so far**

```bash
cd ScholarAgent && python -m pytest tests/ -v
```
Expected: 14 tests PASS

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "feat: state machine + agent harness main loop"
```

---

### Task 3: Tool System

**Files:**
- Create: `agent/tools/__init__.py`
- Create: `agent/tools/base.py`
- Create: `agent/tools/registry.py`
- Create: `agent/tools/retrieval.py`
- Create: `agent/tools/processing.py`
- Create: `agent/tools/writing.py`
- Create: `agent/tools/auxiliary.py`
- Create: `tests/test_tools.py`

**Interfaces:**
- Consumes: `Harness`, `HarnessConfig` from Task 2
- Produces: `Tool` (abstract base), `ToolResult` (dataclass), `ToolRegistry`, `ArxivSearch`, `SemanticScholarSearch`, `GoogleScholarSearch`, `MergeResults`, `PdfDownload`, `PdfParse`, `Dedup`, `SortByCitation`, `FormatBibtex`, `WriteChapter`, `ExpandParagraph`, `TruncateParagraph`, `InsertReferences`, `WebSearch`, `ShellExec`

- [ ] **Step 1: Write failing tests for tool system**

Create `tests/test_tools.py`:

```python
import pytest
from agent.tools.base import Tool, ToolResult
from agent.tools.registry import ToolRegistry
from agent.tools.retrieval import ArxivSearch, MergeResults
from agent.tools.processing import Dedup, SortByCitation, FormatBibtex
from agent.tools.writing import WriteChapter, InsertReferences


def test_tool_base_cannot_be_instantiated():
    with pytest.raises(TypeError):
        Tool()


def test_tool_registry_register_and_get():
    registry = ToolRegistry()
    tool = ArxivSearch()
    registry.register(tool)
    assert registry.get("arxiv_search") is tool


def test_tool_registry_get_unknown_tool():
    registry = ToolRegistry()
    assert registry.get("nonexistent") is None


def test_tool_registry_list_tools():
    registry = ToolRegistry()
    registry.register(ArxivSearch())
    names = registry.list_tools()
    assert "arxiv_search" in names


def test_dedup_removes_duplicates():
    papers = [
        {"title": "Paper A", "source": "arxiv"},
        {"title": "Paper B", "source": "semantic_scholar"},
        {"title": "Paper A", "source": "google_scholar"},
    ]
    result = Dedup().execute({"papers": papers})
    assert len(result.data["papers"]) == 2


def test_sort_by_citation():
    papers = [
        {"title": "A", "citation_count": 5},
        {"title": "B", "citation_count": 100},
        {"title": "C", "citation_count": 20},
    ]
    result = SortByCitation().execute({"papers": papers})
    assert result.data["papers"][0]["title"] == "B"
    assert result.data["papers"][2]["title"] == "A"


def test_format_bibtex():
    paper = {
        "title": "Attention Is All You Need",
        "authors": ["Vaswani", "Shazeer"],
        "year": 2017,
        "source": "arxiv",
    }
    result = FormatBibtex().execute({"paper": paper})
    assert "@article" in result.data["bibtex"]
    assert "Attention Is All You Need" in result.data["bibtex"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ScholarAgent && python -m pytest tests/test_tools.py -v
```
Expected: FAIL with ImportError

- [ ] **Step 3: Write tool base class and registry**

Create `agent/tools/base.py`:

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ToolResult:
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


class Tool(ABC):
    name: str = ""
    description: str = ""

    @abstractmethod
    def execute(self, params: dict[str, Any]) -> ToolResult:
        ...
```

Create `agent/tools/registry.py`:

```python
from typing import Optional
from agent.tools.base import Tool


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())
```

- [ ] **Step 4: Write retrieval tools**

Create `agent/tools/retrieval.py`:

```python
from agent.tools.base import Tool, ToolResult


class ArxivSearch(Tool):
    name = "arxiv_search"
    description = "Search arXiv for papers matching a query"

    def execute(self, params: dict) -> ToolResult:
        query = params.get("query", "")
        max_results = params.get("max_results", 20)
        # Real implementation would call arXiv API via arxiv library
        # For now, return mock data structure
        return ToolResult(success=True, data={
            "query": query,
            "max_results": max_results,
            "papers": [],
            "source": "arxiv",
        })


class SemanticScholarSearch(Tool):
    name = "semantic_scholar_search"
    description = "Search Semantic Scholar for peer-reviewed papers"

    def execute(self, params: dict) -> ToolResult:
        query = params.get("query", "")
        return ToolResult(success=True, data={
            "query": query,
            "papers": [],
            "source": "semantic_scholar",
        })


class GoogleScholarSearch(Tool):
    name = "google_scholar_search"
    description = "Search Google Scholar as fallback source"

    def execute(self, params: dict) -> ToolResult:
        query = params.get("query", "")
        return ToolResult(success=True, data={
            "query": query,
            "papers": [],
            "source": "google_scholar",
        })


class MergeResults(Tool):
    name = "merge_results"
    description = "Merge and deduplicate papers from multiple sources"

    def execute(self, params: dict) -> ToolResult:
        results = params.get("results", [])
        all_papers = []
        for r in results:
            all_papers.extend(r.get("papers", []))
        seen = set()
        unique = []
        for p in all_papers:
            key = p.get("title", "").lower().strip()
            if key and key not in seen:
                seen.add(key)
                unique.append(p)
        return ToolResult(success=True, data={"papers": unique, "total": len(unique)})
```

- [ ] **Step 5: Write processing tools**

Create `agent/tools/processing.py`:

```python
from agent.tools.base import Tool, ToolResult


class PdfDownload(Tool):
    name = "pdf_download"
    description = "Download paper PDF from URL"

    def execute(self, params: dict) -> ToolResult:
        url = params.get("url", "")
        save_path = params.get("save_path", "")
        return ToolResult(success=True, data={
            "url": url,
            "save_path": save_path,
            "downloaded": True,
        })


class PdfParse(Tool):
    name = "pdf_parse"
    description = "Parse PDF to extract full text"

    def execute(self, params: dict) -> ToolResult:
        pdf_path = params.get("pdf_path", "")
        return ToolResult(success=True, data={
            "pdf_path": pdf_path,
            "full_text": "[Parsed text placeholder]",
            "page_count": 0,
        })


class Dedup(Tool):
    name = "dedup_papers"
    description = "Remove duplicate papers by title"

    def execute(self, params: dict) -> ToolResult:
        papers = params.get("papers", [])
        seen = set()
        unique = []
        for p in papers:
            title = p.get("title", "").lower().strip()
            if title and title not in seen:
                seen.add(title)
                unique.append(p)
        return ToolResult(success=True, data={"papers": unique, "removed": len(papers) - len(unique)})


class SortByCitation(Tool):
    name = "sort_by_citation"
    description = "Sort papers by citation count descending"

    def execute(self, params: dict) -> ToolResult:
        papers = list(params.get("papers", []))
        papers.sort(key=lambda p: p.get("citation_count", 0), reverse=True)
        return ToolResult(success=True, data={"papers": papers})


class FormatBibtex(Tool):
    name = "format_bibtex"
    description = "Generate CVPR-standard BibTeX citation"

    def execute(self, params: dict) -> ToolResult:
        paper = params.get("paper", {})
        title = paper.get("title", "Untitled")
        authors = paper.get("authors", [])
        year = paper.get("year", 2024)
        key = title.split()[0].lower() + str(year)
        author_str = " and ".join(authors) if authors else "Unknown"
        bibtex = (
            f"@article{{{key},\n"
            f"  title={{{title}}},\n"
            f"  author={{{author_str}}},\n"
            f"  year={{{year}}},\n"
            f"}}"
        )
        return ToolResult(success=True, data={"bibtex": bibtex})
```

- [ ] **Step 6: Write writing tools**

Create `agent/tools/writing.py`:

```python
from agent.tools.base import Tool, ToolResult


class WriteChapter(Tool):
    name = "write_chapter"
    description = "Write a single chapter of the survey paper"

    def execute(self, params: dict) -> ToolResult:
        chapter_title = params.get("chapter_title", "")
        context = params.get("context", {})
        return ToolResult(success=True, data={
            "chapter_title": chapter_title,
            "content": f"[Content for {chapter_title}]",
        })


class ExpandParagraph(Tool):
    name = "expand_paragraph"
    description = "Expand a specific paragraph with more detail"

    def execute(self, params: dict) -> ToolResult:
        section = params.get("section", "")
        paragraph_index = params.get("paragraph_index", 0)
        return ToolResult(success=True, data={
            "section": section,
            "paragraph_index": paragraph_index,
            "content": "[Expanded content]",
        })


class TruncateParagraph(Tool):
    name = "truncate_paragraph"
    description = "Shorten a specific paragraph"

    def execute(self, params: dict) -> ToolResult:
        section = params.get("section", "")
        paragraph_index = params.get("paragraph_index", 0)
        return ToolResult(success=True, data={
            "section": section,
            "paragraph_index": paragraph_index,
            "content": "[Truncated content]",
        })


class InsertReferences(Tool):
    name = "insert_references"
    description = "Insert reference list into the survey"

    def execute(self, params: dict) -> ToolResult:
        papers = params.get("papers", [])
        refs = []
        for i, p in enumerate(papers, 1):
            refs.append(f"[{i}] {p.get('title', 'Unknown')}")
        return ToolResult(success=True, data={
            "references": refs,
            "count": len(refs),
        })
```

- [ ] **Step 7: Write auxiliary tools**

Create `agent/tools/auxiliary.py`:

```python
from agent.tools.base import Tool, ToolResult


class WebSearch(Tool):
    name = "web_search"
    description = "Search web for niche topics"

    def execute(self, params: dict) -> ToolResult:
        query = params.get("query", "")
        return ToolResult(success=True, data={
            "query": query,
            "results": [],
        })


class CheckArxivUpdates(Tool):
    name = "check_arxiv_updates"
    description = "Check for new papers on arXiv since last check"

    def execute(self, params: dict) -> ToolResult:
        topic = params.get("topic", "")
        return ToolResult(success=True, data={
            "topic": topic,
            "new_papers": [],
            "has_updates": False,
        })


class ShellExec(Tool):
    name = "shell_exec"
    description = "Execute shell commands safely"

    def execute(self, params: dict) -> ToolResult:
        command = params.get("command", "")
        return ToolResult(success=True, data={
            "command": command,
            "stdout": "",
            "stderr": "",
            "exit_code": 0,
        })
```

- [ ] **Step 8: Run tests to verify they pass**

```bash
cd ScholarAgent && python -m pytest tests/test_tools.py -v
```
Expected: All 8 tests PASS

- [ ] **Step 9: Run all tests**

```bash
cd ScholarAgent && python -m pytest tests/ -v
```
Expected: 22 tests PASS

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "feat: tool system with base class, registry, and all tool implementations"
```

---

### Task 4: Guardrail System

**Files:**
- Create: `agent/guardrails/__init__.py`
- Create: `agent/guardrails/base.py`
- Create: `agent/guardrails/source_filter.py`
- Create: `agent/guardrails/fact_binding.py`
- Create: `agent/guardrails/op_safety.py`
- Create: `agent/guardrails/rate_limit.py`
- Create: `agent/guardrails/output_std.py`
- Create: `tests/test_guardrails.py`

**Interfaces:**
- Consumes: `ToolResult` from Task 3
- Produces: `GuardrailResult` (PASS/BLOCK/REQUIRE_APPROVAL), `Guardrail` (base), `SourceFilter`, `FactBinding`, `OpSafety`, `RateLimit`, `OutputStandard`

- [ ] **Step 1: Write failing tests for guardrails

Create `tests/test_guardrails.py`:

```python
import pytest
from agent.guardrails.base import Guardrail, GuardrailResult, GuardrailVerdict
from agent.guardrails.source_filter import SourceFilter
from agent.guardrails.fact_binding import FactBinding
from agent.guardrails.op_safety import OpSafety
from agent.guardrails.rate_limit import RateLimit
from agent.guardrails.output_std import OutputStandard


def test_guardrail_base_cannot_be_instantiated():
    with pytest.raises(TypeError):
        Guardrail()


def test_source_filter_blocks_blacklisted_journal():
    guard = SourceFilter(blacklist=["predatory-journal"])
    ctx = {"paper": {"journal": "predatory-journal"}}
    result = guard.check(ctx)
    assert result.verdict == GuardrailVerdict.BLOCK


def test_source_filter_allows_valid_source():
    guard = SourceFilter(blacklist=["predatory"])
    ctx = {"paper": {"journal": "cvpr"}}
    result = guard.check(ctx)
    assert result.verdict == GuardrailVerdict.PASS


def test_op_safety_blocks_rm_rf():
    guard = OpSafety()
    ctx = {"action": "shell_exec", "params": {"command": "rm -rf /"}}
    result = guard.check(ctx)
    assert result.verdict == GuardrailVerdict.REQUIRE_APPROVAL


def test_op_safety_allows_safe_command():
    guard = OpSafety()
    ctx = {"action": "shell_exec", "params": {"command": "ls -la"}}
    result = guard.check(ctx)
    assert result.verdict == GuardrailVerdict.PASS


def test_rate_limit_blocks_excessive_calls():
    guard = RateLimit(max_calls=2, window_seconds=60)
    ctx = {"action": "arxiv_search"}
    assert guard.check(ctx).verdict == GuardrailVerdict.PASS
    assert guard.check(ctx).verdict == GuardrailVerdict.PASS
    assert guard.check(ctx).verdict == GuardrailVerdict.BLOCK


def test_fact_binding_blocks_unsupported_claim():
    guard = FactBinding()
    ctx = {"chapter": {"content": "Transformers are the best model [citation-needed]"}}
    result = guard.check(ctx)
    assert result.verdict == GuardrailVerdict.BLOCK


def test_fact_binding_allows_supported_claim():
    guard = FactBinding()
    ctx = {"chapter": {"content": "Transformers achieve SOTA results [@vaswani2017]"}}
    result = guard.check(ctx)
    assert result.verdict == GuardrailVerdict.PASS


def test_output_std_blocks_informal_language():
    guard = OutputStandard()
    ctx = {"text": "this paper is super cool and awesome"}
    result = guard.check(ctx)
    assert result.verdict == GuardrailVerdict.BLOCK


def test_output_std_allows_formal_language():
    guard = OutputStandard()
    ctx = {"text": "This paper presents a novel approach to the problem."}
    result = guard.check(ctx)
    assert result.verdict == GuardrailVerdict.PASS
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ScholarAgent && python -m pytest tests/test_guardrails.py -v
```
Expected: FAIL with ImportError

- [ ] **Step 3: Write guardrail base class**

Create `agent/guardrails/base.py`:

```python
from abc import ABC, abstractmethod
from enum import Enum
from dataclasses import dataclass
from typing import Any


class GuardrailVerdict(Enum):
    PASS = "pass"
    BLOCK = "block"
    REQUIRE_APPROVAL = "require_approval"


@dataclass
class GuardrailResult:
    verdict: GuardrailVerdict
    message: str = ""
    guardrail_name: str = ""


class Guardrail(ABC):
    name: str = ""

    @abstractmethod
    def check(self, context: dict[str, Any]) -> GuardrailResult:
        ...
```

- [ ] **Step 4: Write all guardrail implementations

Create `agent/guardrails/source_filter.py`:

```python
from agent.guardrails.base import Guardrail, GuardrailResult, GuardrailVerdict


class SourceFilter(Guardrail):
    name = "source_filter"

    def __init__(self, blacklist: list[str] | None = None):
        self.blacklist = blacklist or []

    def check(self, context: dict) -> GuardrailResult:
        paper = context.get("paper", {})
        journal = (paper.get("journal") or "").lower()
        source = (paper.get("source") or "").lower()
        for banned in self.blacklist:
            if banned.lower() in journal or banned.lower() in source:
                return GuardrailResult(
                    verdict=GuardrailVerdict.BLOCK,
                    message=f"Source '{journal or source}' is blacklisted",
                    guardrail_name=self.name,
                )
        return GuardrailResult(
            verdict=GuardrailVerdict.PASS,
            guardrail_name=self.name,
        )
```

Create `agent/guardrails/fact_binding.py`:

```python
import re
from agent.guardrails.base import Guardrail, GuardrailResult, GuardrailVerdict


class FactBinding(Guardrail):
    name = "fact_binding"

    def check(self, context: dict) -> GuardrailResult:
        chapter = context.get("chapter", {})
        content = chapter.get("content", "")
        # Check for citation markers like [@id]
        citations = re.findall(r'\[@(\w+)\]', content)
        needs_citation = re.findall(r'\[citation-needed\]', content)
        if needs_citation:
            return GuardrailResult(
                verdict=GuardrailVerdict.BLOCK,
                message=f"Found {len(needs_citation)} claims without citation support",
                guardrail_name=self.name,
            )
        return GuardrailResult(
            verdict=GuardrailVerdict.PASS,
            guardrail_name=self.name,
        )
```

Create `agent/guardrails/op_safety.py`:

```python
import re
from agent.guardrails.base import Guardrail, GuardrailResult, GuardrailVerdict


DANGEROUS_PATTERNS = [
    r'rm\s+[-]?rf',
    r'del\s+/[Ff]',
    r'format\s+',
    r'mkfs\.',
    r'dd\s+if=',
    r'>\s*/dev/sda',
    r'drop\s+table',
    r'delete\s+from\s+\w+\s+(where\s+)?1?=?\s*1',
]


class OpSafety(Guardrail):
    name = "op_safety"

    def check(self, context: dict) -> GuardrailResult:
        params = context.get("params", {})
        command = params.get("command", "")
        action = context.get("action", "")
        for pattern in DANGEROUS_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return GuardrailResult(
                    verdict=GuardrailVerdict.REQUIRE_APPROVAL,
                    message=f"Dangerous command detected: {command[:100]}",
                    guardrail_name=self.name,
                )
        return GuardrailResult(
            verdict=GuardrailVerdict.PASS,
            guardrail_name=self.name,
        )
```

Create `agent/guardrails/rate_limit.py`:

```python
import time
from collections import defaultdict
from agent.guardrails.base import Guardrail, GuardrailResult, GuardrailVerdict


class RateLimit(Guardrail):
    name = "rate_limit"

    def __init__(self, max_calls: int = 30, window_seconds: int = 60):
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self._call_timestamps: dict[str, list[float]] = defaultdict(list)

    def check(self, context: dict) -> GuardrailResult:
        action = context.get("action", "default")
        now = time.time()
        window_start = now - self.window_seconds
        self._call_timestamps[action] = [
            t for t in self._call_timestamps[action] if t > window_start
        ]
        if len(self._call_timestamps[action]) >= self.max_calls:
            return GuardrailResult(
                verdict=GuardrailVerdict.BLOCK,
                message=f"Rate limit exceeded for '{action}': {self.max_calls} calls per {self.window_seconds}s",
                guardrail_name=self.name,
            )
        self._call_timestamps[action].append(now)
        return GuardrailResult(
            verdict=GuardrailVerdict.PASS,
            guardrail_name=self.name,
        )
```

Create `agent/guardrails/output_std.py`:

```python
import re
from agent.guardrails.base import Guardrail, GuardrailResult, GuardrailVerdict


INFORMAL_PATTERNS = [
    r'\bsuper\b', r'\bawesome\b', r'\bcool\b', r'\bamazing\b',
    r'\bguess\b', r'\b basically \b', r'\b kinda \b', r'\b sorta \b',
    r'\blike\b', r'\bthings?\b', r'\b stuff \b', r'\b a lot \b',
]


class OutputStandard(Guardrail):
    name = "output_standard"

    def check(self, context: dict) -> GuardrailResult:
        text = context.get("text", "").lower()
        for pattern in INFORMAL_PATTERNS:
            if re.search(pattern, text):
                return GuardrailResult(
                    verdict=GuardrailVerdict.BLOCK,
                    message=f"Informal language detected in output",
                    guardrail_name=self.name,
                )
        return GuardrailResult(
            verdict=GuardrailVerdict.PASS,
            guardrail_name=self.name,
        )
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd ScholarAgent && python -m pytest tests/test_guardrails.py -v
```
Expected: All 10 tests PASS

- [ ] **Step 6: Run all tests**

```bash
cd ScholarAgent && python -m pytest tests/ -v
```
Expected: 32 tests PASS

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat: guardrail system with 5 guardrail implementations"
```

---

### Task 5: Memory System

**Files:**
- Create: `agent/memory/__init__.py`
- Create: `agent/memory/base.py`
- Create: `agent/memory/session.py`
- Create: `agent/memory/persistent.py`
- Create: `tests/test_memory.py`

**Interfaces:**
- Consumes: nothing standalone
- Produces: `MemoryBase`, `SessionMemory`, `PersistentMemory`, `MemoryEntry`

- [ ] **Step 1: Write failing tests for memory

Create `tests/test_memory.py`:

```python
import pytest
import json
import tempfile
import os
from pathlib import Path
from agent.memory.session import SessionMemory
from agent.memory.persistent import PersistentMemory


def test_session_memory_save_and_get():
    mem = SessionMemory()
    mem.save("papers", [{"title": "Paper A"}])
    assert mem.get("papers") == [{"title": "Paper A"}]


def test_session_memory_get_nonexistent():
    mem = SessionMemory()
    assert mem.get("nonexistent") is None


def test_session_memory_update():
    mem = SessionMemory()
    mem.save("papers", [{"title": "A"}])
    mem.save("papers", [{"title": "A"}, {"title": "B"}])
    assert len(mem.get("papers")) == 2


def test_session_memory_clear():
    mem = SessionMemory()
    mem.save("key", "value")
    mem.clear()
    assert mem.get("key") is None


def test_session_memory_save_to_file(tmp_path):
    mem = SessionMemory(storage_dir=str(tmp_path))
    mem.save("topic", "Test")
    mem._persist()
    assert os.path.exists(os.path.join(tmp_path, "session.json"))


def test_session_memory_load_from_file(tmp_path):
    data = {"topic": "Test", "papers": []}
    with open(os.path.join(tmp_path, "session.json"), "w") as f:
        json.dump(data, f)
    mem = SessionMemory(storage_dir=str(tmp_path))
    mem._load()
    assert mem.get("topic") == "Test"


def test_persistent_memory_set_and_get():
    mem = PersistentMemory(db_path=":memory:")
    mem.set("default_source", "arxiv")
    assert mem.get("default_source") == "arxiv"


def test_persistent_memory_get_default():
    mem = PersistentMemory(db_path=":memory:")
    assert mem.get("nonexistent", "default_val") == "default_val"


def test_persistent_memory_get_all():
    mem = PersistentMemory(db_path=":memory:")
    mem.set("key1", "val1")
    mem.set("key2", "val2")
    all_items = mem.get_all()
    assert len(all_items) >= 2


def test_persistent_memory_delete():
    mem = PersistentMemory(db_path=":memory:")
    mem.set("key", "value")
    mem.delete("key")
    assert mem.get("key") is None


def test_persistent_memory_clear_all():
    mem = PersistentMemory(db_path=":memory:")
    mem.set("key1", "val1")
    mem.set("key2", "val2")
    mem.clear_all()
    assert mem.get_all() == []
```

- [ ] **Step 2: Run tests to verify they fail

```bash
cd ScholarAgent && python -m pytest tests/test_memory.py -v
```
Expected: FAIL with ImportError

- [ ] **Step 3: Write memory implementations

Create `agent/memory/base.py`:

```python
from abc import ABC, abstractmethod
from typing import Any, Optional


class MemoryBase(ABC):
    @abstractmethod
    def get(self, key: str, default: Any = None) -> Any:
        ...

    @abstractmethod
    def save(self, key: str, value: Any) -> None:
        ...

    @abstractmethod
    def clear(self) -> None:
        ...
```

Create `agent/memory/session.py`:

```python
import json
import os
from typing import Any, Optional
from agent.memory.base import MemoryBase


class SessionMemory(MemoryBase):
    def __init__(self, storage_dir: str = "memory/session"):
        self._data: dict[str, Any] = {}
        self._storage_dir = storage_dir
        self._storage_path = os.path.join(storage_dir, "session.json")
        os.makedirs(storage_dir, exist_ok=True)
        self._load()

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def save(self, key: str, value: Any) -> None:
        self._data[key] = value
        self._persist()

    def clear(self) -> None:
        self._data.clear()
        self._persist()

    def _persist(self) -> None:
        with open(self._storage_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def _load(self) -> None:
        if os.path.exists(self._storage_path):
            with open(self._storage_path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
```

Create `agent/memory/persistent.py`:

```python
import sqlite3
import os
from typing import Any, Optional
from agent.memory.base import MemoryBase


class PersistentMemory(MemoryBase):
    def __init__(self, db_path: str = "memory/persistent/scholar_memory.db"):
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS user_preferences (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self._conn.commit()

    def get(self, key: str, default: Any = None) -> Any:
        cursor = self._conn.execute(
            "SELECT value FROM user_preferences WHERE key = ?", (key,)
        )
        row = cursor.fetchone()
        return row[0] if row else default

    def save(self, key: str, value: Any) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO user_preferences (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
            (key, str(value)),
        )
        self._conn.commit()

    def set(self, key: str, value: Any) -> None:
        self.save(key, value)

    def delete(self, key: str) -> None:
        self._conn.execute("DELETE FROM user_preferences WHERE key = ?", (key,))
        self._conn.commit()

    def get_all(self) -> list[dict]:
        cursor = self._conn.execute(
            "SELECT key, value, updated_at FROM user_preferences ORDER BY key"
        )
        return [{"key": k, "value": v, "updated_at": t} for k, v, t in cursor.fetchall()]

    def clear_all(self) -> None:
        self._conn.execute("DELETE FROM user_preferences")
        self._conn.commit()

    def clear(self) -> None:
        self.clear_all()
```

- [ ] **Step 4: Run tests to verify they pass

```bash
cd ScholarAgent && python -m pytest tests/test_memory.py -v
```
Expected: All 12 tests PASS

- [ ] **Step 5: Run all tests

```bash
cd ScholarAgent && python -m pytest tests/ -v
```
Expected: 44 tests PASS

- [ ] **Step 6: Commit

```bash
git add -A
git commit -m "feat: memory system with session (JSON) and persistent (SQLite) storage"

---

### Task 6: Feedback System — Validators (Deep Dimension)

**Files:**
- Create: `agent/feedback/__init__.py`
- Create: `agent/feedback/base.py`
- Create: `agent/feedback/check_citations.py`
- Create: `agent/feedback/detect_hallucination.py`
- Create: `agent/feedback/check_word_count.py`
- Create: `agent/feedback/polish_language.py`
- Create: `agent/feedback/check_coherence.py`
- Create: `tests/test_feedback.py`

**Interfaces:**
- Consumes: `ToolResult` from Task 3
- Produces: `Validator` (base), `ValidationResult` (dataclass), `CitationChecker`, `HallucinationDetector`, `WordCountChecker`, `LanguagePolisher`, `CoherenceChecker`

- [ ] **Step 1: Write failing tests for validators**

Create `tests/test_feedback.py`:

```python
import pytest
from agent.feedback.base import Validator, ValidationResult
from agent.feedback.check_citations import CitationChecker
from agent.feedback.detect_hallucination import HallucinationDetector
from agent.feedback.check_word_count import WordCountChecker
from agent.feedback.polish_language import LanguagePolisher
from agent.feedback.check_coherence import CoherenceChecker


def test_validator_base_cannot_be_instantiated():
    with pytest.raises(TypeError):
        Validator()


def test_citation_checker_all_valid():
    checker = CitationChecker()
    chapter = {
        "content": "Transformers [@vaswani2017] are effective. BERT [@devlin2019] improves it.",
        "paper_ids": ["vaswani2017", "devlin2019"],
    }
    result = checker.validate(chapter)
    assert result.passed is True
    assert result.score == 1.0


def test_citation_checker_with_missing_refs():
    checker = CitationChecker()
    chapter = {
        "content": "Transformers [@vaswani2017] are effective. [@unknown2020] is missing.",
        "paper_ids": ["vaswani2017"],
    }
    result = checker.validate(chapter)
    assert result.passed is False
    assert result.score < 0.7
    assert len(result.issues) > 0
    assert "unknown2020" in result.issues[0]


def test_citation_checker_no_citations():
    checker = CitationChecker()
    chapter = {
        "content": "This is a statement without any citation.",
        "paper_ids": [],
    }
    result = checker.validate(chapter)
    assert result.passed is False


def test_hallucination_detector_no_hallucination():
    detector = HallucinationDetector()
    chapter = {
        "content": "Transformers [@v2017] achieve SOTA. BERT [@d2019] uses pretraining.",
        "paper_ids": ["v2017", "d2019"],
    }
    result = detector.validate(chapter)
    assert result.passed is True


def test_hallucination_detector_unsupported_claim():
    detector = HallucinationDetector()
    chapter = {
        "content": "This method achieves 75% accuracy improvement. [citation-needed]",
        "paper_ids": [],
    }
    result = detector.validate(chapter)
    assert result.passed is False
    assert len(result.issues) > 0


def test_word_count_checker_within_range():
    checker = WordCountChecker(min_words=10, max_words=100)
    chapter = {"content": "This is a test chapter with enough words to pass the minimum threshold."}
    result = checker.validate(chapter)
    assert result.passed is True


def test_word_count_checker_too_short():
    checker = WordCountChecker(min_words=50, max_words=100)
    chapter = {"content": "Too short."}
    result = checker.validate(chapter)
    assert result.passed is False
    assert "too short" in result.issues[0].lower()


def test_word_count_checker_too_long():
    checker = WordCountChecker(min_words=10, max_words=20)
    chapter = {"content": "This is a very long chapter that definitely exceeds the maximum word limit."}
    result = checker.validate(chapter)
    assert result.passed is False
    assert "too long" in result.issues[0].lower()


def test_language_polisher_detects_informal():
    polisher = LanguagePolisher()
    text = "This paper is super cool and does amazing stuff."
    result = polisher.validate({"content": text})
    assert result.passed is False
    assert len(result.issues) > 0


def test_language_polisher_accepts_formal():
    polisher = LanguagePolisher()
    text = "This paper presents a novel approach to the problem."
    result = polisher.validate({"content": text})
    assert result.passed is True


def test_coherence_checker_has_transitions():
    checker = CoherenceChecker()
    chapter = {
        "content": "First, we introduce the problem. Subsequently, we review related work. Finally, we discuss future directions."
    }
    result = checker.validate(chapter)
    assert result.passed is True


def test_coherence_checker_no_transitions():
    checker = CoherenceChecker()
    chapter = {
        "content": "This is a. This is b. This is c. This is d. This is e."
    }
    result = checker.validate(chapter)
    assert result.passed is False


def test_validation_result_dataclass():
    result = ValidationResult(
        validator_name="test",
        passed=True,
        score=0.95,
        issues=[],
        repair_instructions="",
    )
    assert result.validator_name == "test"
    assert result.passed is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ScholarAgent && python -m pytest tests/test_feedback.py -v
```
Expected: FAIL with ImportError

- [ ] **Step 3: Write validator base class**

Create `agent/feedback/base.py`:

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ValidationResult:
    validator_name: str
    passed: bool
    score: float = 0.0
    issues: list[str] = field(default_factory=list)
    repair_instructions: str = ""


class Validator(ABC):
    name: str = ""

    @abstractmethod
    def validate(self, context: dict[str, Any]) -> ValidationResult:
        ...
```

- [ ] **Step 4: Write CitationChecker**

Create `agent/feedback/check_citations.py`:

```python
import re
from agent.feedback.base import Validator, ValidationResult


class CitationChecker(Validator):
    name = "check_citations"

    def validate(self, context: dict) -> ValidationResult:
        content = context.get("content", "")
        paper_ids = context.get("paper_ids", [])
        citations = re.findall(r'\[@(\w+)\]', content)
        if not citations:
            return ValidationResult(
                validator_name=self.name,
                passed=False,
                score=0.0,
                issues=["No citations found in the chapter"],
                repair_instructions="Add citations to support claims using [@paper_id] format",
            )
        missing = [c for c in citations if c not in paper_ids]
        if missing:
            score = max(0.0, 1.0 - len(missing) / len(citations))
            return ValidationResult(
                validator_name=self.name,
                passed=score >= 0.7,
                score=score,
                issues=[f"Missing paper references: {', '.join(missing)}"],
                repair_instructions=f"Add the following papers to the reference list: {', '.join(missing)}",
            )
        return ValidationResult(
            validator_name=self.name,
            passed=True,
            score=1.0,
            issues=[],
            repair_instructions="",
        )
```

- [ ] **Step 5: Write HallucinationDetector**

Create `agent/feedback/detect_hallucination.py`:

```python
import re
from agent.feedback.base import Validator, ValidationResult


class HallucinationDetector(Validator):
    name = "detect_hallucination"

    def validate(self, context: dict) -> ValidationResult:
        content = context.get("content", "")
        paper_ids = context.get("paper_ids", [])
        needs_citation = re.findall(r'\[citation-needed\]', content)
        if needs_citation:
            return ValidationResult(
                validator_name=self.name,
                passed=False,
                score=max(0.0, 1.0 - len(needs_citation) * 0.2),
                issues=[f"Found {len(needs_citation)} claims needing citation support"],
                repair_instructions="Retrieve supporting papers and add [@paper_id] citations for each claim",
            )
        return ValidationResult(
            validator_name=self.name,
            passed=True,
            score=1.0,
            issues=[],
            repair_instructions="",
        )
```

- [ ] **Step 6: Write WordCountChecker**

Create `agent/feedback/check_word_count.py`:

```python
from agent.feedback.base import Validator, ValidationResult


class WordCountChecker(Validator):
    name = "check_word_count"

    def __init__(self, min_words: int = 100, max_words: int = 5000):
        self.min_words = min_words
        self.max_words = max_words

    def validate(self, context: dict) -> ValidationResult:
        content = context.get("content", "")
        word_count = len(content.split())
        issues = []
        if word_count < self.min_words:
            issues.append(f"Chapter too short: {word_count} words (min: {self.min_words})")
        if word_count > self.max_words:
            issues.append(f"Chapter too long: {word_count} words (max: {self.max_words})")
        passed = len(issues) == 0
        score = 1.0
        if word_count < self.min_words:
            score = max(0.0, word_count / self.min_words)
        elif word_count > self.max_words:
            score = max(0.0, 1.0 - (word_count - self.max_words) / self.max_words)
        repair = ""
        if issues:
            if word_count < self.min_words:
                repair = f"Expand the chapter to at least {self.min_words} words"
            else:
                repair = f"Trim the chapter to at most {self.max_words} words"
        return ValidationResult(
            validator_name=self.name,
            passed=passed,
            score=score,
            issues=issues,
            repair_instructions=repair,
        )
```

- [ ] **Step 7: Write LanguagePolisher**

Create `agent/feedback/polish_language.py`:

```python
import re
from agent.feedback.base import Validator, ValidationResult


INFORMAL_PATTERNS = [
    (r'\bsuper\b', 'informal intensifier "super"'),
    (r'\bawesome\b', 'informal word "awesome"'),
    (r'\bcool\b', 'informal word "cool"'),
    (r'\bamazing\b', 'informal word "amazing"'),
    (r'\b basically \b', 'informal filler "basically"'),
    (r'\b kinda \b', 'informal word "kinda"'),
    (r'\b sorta \b', 'informal word "sorta"'),
    (r'\b stuff \b', 'vague term "stuff"'),
    (r'\b a lot \b', 'informal phrase "a lot"'),
    (r'\b really \b', 'informal intensifier "really"'),
    (r'\b very \b', 'weak intensifier "very"'),
    (r'\b things? \b', 'vague term "thing/things"'),
]


class LanguagePolisher(Validator):
    name = "polish_language"

    def validate(self, context: dict) -> ValidationResult:
        content = context.get("content", "")
        lower = content.lower()
        issues = []
        for pattern, desc in INFORMAL_PATTERNS:
            if re.search(pattern, lower):
                issues.append(f"Replace {desc} with formal academic language")
        if issues:
            return ValidationResult(
                validator_name=self.name,
                passed=False,
                score=max(0.0, 1.0 - len(issues) * 0.15),
                issues=issues[:5],
                repair_instructions="Replace informal expressions with academic language suitable for CVPR",
            )
        return ValidationResult(
            validator_name=self.name,
            passed=True,
            score=1.0,
            issues=[],
            repair_instructions="",
        )
```

- [ ] **Step 8: Write CoherenceChecker**

Create `agent/feedback/check_coherence.py`:

```python
import re
from agent.feedback.base import Validator, ValidationResult


TRANSITION_MARKERS = [
    r'\bfirst(ly)?\b', r'\bsecond(ly)?\b', r'\bthird(ly)?\b',
    r'\bnext\b', r'\bthen\b', r'\bsubsequently\b', r'\bafter\b',
    r'\bfurthermore\b', r'\bmoreover\b', r'\bin addition\b',
    r'\bhowever\b', r'\bnevertheless\b', r'\bon the other hand\b',
    r'\bin contrast\b', r'\bconversely\b', r'\btherefore\b',
    r'\bthus\b', r'\bconsequently\b', r'\bas a result\b',
    r'\bfinally\b', r'\bin summary\b', r'\bto conclude\b',
    r'\bfor example\b', r'\bfor instance\b', r'\bspecifically\b',
]


class CoherenceChecker(Validator):
    name = "check_coherence"

    def __init__(self, min_markers: int = 3):
        self.min_markers = min_markers

    def validate(self, context: dict) -> ValidationResult:
        content = context.get("content", "")
        lower = content.lower()
        found = []
        for pattern in TRANSITION_MARKERS:
            matches = re.findall(pattern, lower)
            found.extend(matches)
        total = len(found)
        if total < self.min_markers:
            return ValidationResult(
                validator_name=self.name,
                passed=False,
                score=max(0.0, total / self.min_markers),
                issues=[f"Only {total} transition markers found (need at least {self.min_markers})"],
                repair_instructions="Add transition words (however, furthermore, therefore, etc.) between paragraphs and sections",
            )
        return ValidationResult(
            validator_name=self.name,
            passed=True,
            score=min(1.0, total / (self.min_markers * 2)),
            issues=[],
            repair_instructions="",
        )
```

- [ ] **Step 9: Run tests to verify they pass**

```bash
cd ScholarAgent && python -m pytest tests/test_feedback.py -v
```
Expected: All 16 tests PASS

- [ ] **Step 10: Run all tests**

```bash
cd ScholarAgent && python -m pytest tests/ -v
```
Expected: 60 tests PASS

- [ ] **Step 11: Commit**

```bash
git add -A
git commit -m "feat: feedback validators — citation, hallucination, word count, language, coherence"
```

---

### Task 7: Feedback Aggregator + Repair Generator + Multi-Round Iteration

**Files:**
- Modify: `agent/feedback/__init__.py`
- Create: `agent/feedback/aggregator.py`
- Create: `agent/feedback/repair_generator.py`
- Modify: `agent/core/harness.py` (add feedback iteration to main loop)
- Modify: `tests/test_feedback.py` (add aggregator + repair tests)

**Interfaces:**
- Consumes: `ValidationResult` from Task 6, `Harness` from Task 2
- Produces: `FeedbackAggregator`, `RepairGenerator`, `FeedbackReport` (dataclass)

- [ ] **Step 1: Write failing tests for aggregator and repair**

Add to `tests/test_feedback.py`:

```python
from agent.feedback.aggregator import FeedbackAggregator, FeedbackReport
from agent.feedback.repair_generator import RepairGenerator


def test_aggregator_all_pass():
    agg = FeedbackAggregator()
    results = [
        ValidationResult(validator_name="a", passed=True, score=0.9),
        ValidationResult(validator_name="b", passed=True, score=1.0),
    ]
    report = agg.aggregate(results)
    assert report.overall_passed is True
    assert report.overall_score >= 0.7


def test_aggregator_some_fail():
    agg = FeedbackAggregator()
    results = [
        ValidationResult(validator_name="a", passed=True, score=0.9),
        ValidationResult(validator_name="b", passed=False, score=0.3, issues=["Bad"]),
    ]
    report = agg.aggregate(results)
    assert report.overall_passed is False
    assert report.overall_score < 0.7
    assert len(report.failed_validators) == 1


def test_aggregator_empty_results():
    agg = FeedbackAggregator()
    report = agg.aggregate([])
    assert report.overall_passed is True


def test_aggregator_threshold():
    agg = FeedbackAggregator(pass_threshold=0.85)
    results = [
        ValidationResult(validator_name="a", passed=True, score=0.8),
        ValidationResult(validator_name="b", passed=True, score=0.8),
    ]
    report = agg.aggregate(results)
    assert report.overall_passed is False  # 0.8 < 0.85


def test_repair_generator_combines_instructions():
    gen = RepairGenerator()
    results = [
        ValidationResult(validator_name="a", passed=False, score=0.5,
                         repair_instructions="Fix A"),
        ValidationResult(validator_name="b", passed=False, score=0.4,
                         repair_instructions="Fix B"),
    ]
    instruction = gen.generate(results)
    assert "Fix A" in instruction
    assert "Fix B" in instruction


def test_repair_generator_empty_input():
    gen = RepairGenerator()
    instruction = gen.generate([])
    assert instruction == ""


def test_harness_integrates_feedback_loop():
    from agent.core.harness import Harness, HarnessConfig
    from agent.core.llm import MockLLM
    from agent.core.state import AgentState

    llm = MockLLM(fixed_response="Survey content")
    h = Harness(config=HarnessConfig(max_retries=3, quality_threshold=0.7), llm=llm)
    h.start(topic="Test")
    h.state.transition_to(AgentState.VALIDATION)
    bad_result = ValidationResult(
        validator_name="check_citations",
        passed=False,
        score=0.3,
        issues=["Missing citations"],
        repair_instructions="Add citations",
    )
    h.inject_feedback([bad_result])
    assert h.state.current_state == AgentState.WRITING
    assert h.retry_count == 1


def test_harness_stops_after_max_retries():
    from agent.core.harness import Harness, HarnessConfig
    from agent.core.llm import MockLLM
    from agent.core.state import AgentState

    llm = MockLLM(fixed_response="Content")
    h = Harness(config=HarnessConfig(max_retries=2, quality_threshold=0.7), llm=llm)
    h.start(topic="Test")
    h.state.transition_to(AgentState.VALIDATION)
    h.retry_count = 2
    bad_result = ValidationResult(
        validator_name="test", passed=False, score=0.3, issues=["Fail"],
    )
    h.inject_feedback([bad_result])
    assert h.state.current_state == AgentState.COMPLETE
    assert h.has_warnings is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ScholarAgent && python -m pytest tests/test_feedback.py -v
```
Expected: 7 new tests FAIL (import errors for aggregator, repair_generator)

- [ ] **Step 3: Write FeedbackAggregator**

Create `agent/feedback/aggregator.py`:

```python
from dataclasses import dataclass, field
from agent.feedback.base import ValidationResult


@dataclass
class FeedbackReport:
    overall_passed: bool
    overall_score: float
    failed_validators: list[str] = field(default_factory=list)
    all_results: list[ValidationResult] = field(default_factory=list)


class FeedbackAggregator:
    def __init__(self, pass_threshold: float = 0.7):
        self.pass_threshold = pass_threshold

    def aggregate(self, results: list[ValidationResult]) -> FeedbackReport:
        if not results:
            return FeedbackReport(overall_passed=True, overall_score=1.0)
        scores = [r.score for r in results]
        overall_score = sum(scores) / len(scores)
        failed = [r.validator_name for r in results if not r.passed]
        return FeedbackReport(
            overall_passed=overall_score >= self.pass_threshold,
            overall_score=overall_score,
            failed_validators=failed,
            all_results=results,
        )
```

- [ ] **Step 4: Write RepairGenerator**

Create `agent/feedback/repair_generator.py`:

```python
from agent.feedback.base import ValidationResult


class RepairGenerator:
    def generate(self, results: list[ValidationResult]) -> str:
        instructions = []
        for r in results:
            if not r.passed and r.repair_instructions:
                instructions.append(f"[{r.validator_name}] {r.repair_instructions}")
        return "\n".join(instructions)
```

- [ ] **Step 5: Update Harness to integrate feedback loop**

Modify `agent/core/harness.py` — replace the Harness class with the updated version:

```python
from dataclasses import dataclass, field
from typing import Any, Optional
from agent.core.state import AgentState, StateMachine
from agent.core.llm import LLMBase
from agent.feedback.base import ValidationResult
from agent.feedback.aggregator import FeedbackAggregator, FeedbackReport
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
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd ScholarAgent && python -m pytest tests/test_feedback.py -v
```
Expected: All 23 tests PASS

- [ ] **Step 7: Run all tests**

```bash
cd ScholarAgent && python -m pytest tests/ -v
```
Expected: 67 tests PASS

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "feat: feedback aggregator, repair generator, and multi-round iteration in harness"
```

---

### Task 8: API Layer

**Files:**
- Create: `api/__init__.py`
- Create: `api/main.py`
- Create: `api/models.py`
- Create: `api/routes/__init__.py`
- Create: `api/routes/survey.py`
- Create: `api/routes/progress.py`
- Create: `api/routes/feedback.py`
- Create: `api/routes/memory.py`

**Interfaces:**
- Consumes: `Harness`, `HarnessConfig` from Task 2/7, `ToolRegistry` from Task 3, `SessionMemory` and `PersistentMemory` from Task 5
- Produces: FastAPI application with REST + WebSocket endpoints

- [ ] **Step 1: Write failing tests**

Create `tests/test_api.py`:

```python
import pytest
from httpx import AsyncClient, ASGITransport
from api.main import app, get_harness
from agent.core.llm import MockLLM
from agent.core.harness import Harness, HarnessConfig


@pytest.fixture
def test_harness():
    llm = MockLLM(fixed_response="Survey content")
    h = Harness(config=HarnessConfig(), llm=llm)
    return h


@pytest.fixture
def client(test_harness):
    app.dependency_overrides[get_harness] = lambda: test_harness
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_create_survey(client):
    response = await client.post("/api/survey", json={
        "topic": "Transformer Models",
        "keywords": "attention, BERT, GPT",
        "goal": "Survey transformer architectures",
        "max_papers": 20,
    })
    assert response.status_code == 200
    data = response.json()
    assert data["topic"] == "Transformer Models"
    assert data["status"] == "PLANNING"


@pytest.mark.asyncio
async def test_get_survey_status(client, test_harness):
    test_harness.start(topic="Test")
    response = await client.get("/api/survey/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "PLANNING"


@pytest.mark.asyncio
async def test_interrupt_survey(client, test_harness):
    test_harness.start(topic="Test")
    response = await client.post("/api/survey/interrupt")
    assert response.status_code == 200
    assert response.json()["status"] == "INTERRUPTED"


@pytest.mark.asyncio
async def test_resume_survey(client, test_harness):
    test_harness.start(topic="Test")
    test_harness.interrupt()
    response = await client.post("/api/survey/resume")
    assert response.status_code == 200
    assert response.json()["status"] == "PLANNING"


@pytest.mark.asyncio
async def test_submit_feedback(client, test_harness):
    test_harness.start(topic="Test")
    response = await client.post("/api/feedback", json={
        "category": "literature",
        "content": "Add more papers on attention mechanisms",
    })
    assert response.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ScholarAgent && pip install httpx && python -m pytest tests/test_api.py -v
```
Expected: FAIL with ImportError

- [ ] **Step 3: Write API layer**

Create `api/__init__.py` — empty.

Create `api/models.py`:

```python
from pydantic import BaseModel
from typing import Optional


class SurveyRequest(BaseModel):
    topic: str
    keywords: str = ""
    goal: str = ""
    max_papers: int = 20


class SurveyResponse(BaseModel):
    topic: str
    status: str
    keywords: list[str] = []
    goal: str = ""
    max_papers: int = 20
    retry_count: int = 0
    has_warnings: bool = False


class FeedbackRequest(BaseModel):
    category: str = "literature"
    content: str
```

Create `api/routes/__init__.py` — empty.

Create `api/routes/survey.py`:

```python
from fastapi import APIRouter, Depends
from api.models import SurveyRequest, SurveyResponse
from agent.core.harness import Harness

router = APIRouter(prefix="/api/survey", tags=["survey"])


def get_harness() -> Harness:
    from api.main import _harness
    return _harness


@router.post("", response_model=SurveyResponse)
async def create_survey(req: SurveyRequest, harness: Harness = Depends(get_harness)):
    harness.start(topic=req.topic, keywords=req.keywords, goal=req.goal)
    info = harness.get_task_info()
    return SurveyResponse(**info)


@router.get("/status", response_model=SurveyResponse)
async def get_status(harness: Harness = Depends(get_harness)):
    info = harness.get_task_info()
    return SurveyResponse(**info)


@router.post("/interrupt", response_model=SurveyResponse)
async def interrupt_survey(harness: Harness = Depends(get_harness)):
    harness.interrupt()
    info = harness.get_task_info()
    return SurveyResponse(**info)


@router.post("/resume", response_model=SurveyResponse)
async def resume_survey(harness: Harness = Depends(get_harness)):
    harness.resume()
    info = harness.get_task_info()
    return SurveyResponse(**info)
```

Create `api/routes/feedback.py`:

```python
from fastapi import APIRouter, Depends
from api.models import FeedbackRequest
from agent.core.harness import Harness

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


@router.post("")
async def submit_feedback(req: FeedbackRequest, harness: Harness = Depends(get_harness)):
    feedback = {"category": req.category, "content": req.content, "type": "human", "resolved": False}
    return {"status": "received", "feedback": feedback}
```

Create `api/routes/progress.py`:

```python
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio
import json

router = APIRouter()


@router.websocket("/ws/stream/{task_id}")
async def stream_progress(websocket: WebSocket, task_id: str):
    await websocket.accept()
    try:
        while True:
            status_data = {"status": "running", "task_id": task_id}
            await websocket.send_text(json.dumps(status_data))
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass
```

Create `api/routes/memory.py`:

```python
from fastapi import APIRouter
from api.models import MemoryUpdate
from agent.memory.persistent import PersistentMemory

router = APIRouter(prefix="/api/memory", tags=["memory"])
_memory = PersistentMemory()


@router.get("")
async def get_all_memory():
    return {"preferences": _memory.get_all()}


@router.put("")
async def update_memory(update: MemoryUpdate):
    _memory.set(update.key, update.value)
    return {"status": "updated", "key": update.key}


@router.delete("")
async def clear_memory():
    _memory.clear_all()
    return {"status": "cleared"}


@router.delete("/{key}")
async def delete_memory_key(key: str):
    _memory.delete(key)
    return {"status": "deleted", "key": key}
```

Create `api/main.py`:

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from agent.core.llm import OpenAILLM
from agent.core.harness import Harness, HarnessConfig
from api.routes import survey, feedback, progress, memory

app = FastAPI(title="ScholarAgent API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_harness = Harness(config=HarnessConfig(), llm=OpenAILLM(api_key=""))

app.include_router(survey.router)
app.include_router(feedback.router)
app.include_router(progress.router)
app.include_router(memory.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd ScholarAgent && python -m pytest tests/test_api.py -v
```
Expected: All 5 tests PASS

- [ ] **Step 5: Run all tests**

```bash
cd ScholarAgent && python -m pytest tests/ -v
```
Expected: 72 tests PASS

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: API layer with FastAPI, REST endpoints, and WebSocket"
```

---

### Task 9: Web UI — Scaffold + Dashboard + Research Creation

**Files:**
- Create: `web/package.json`
- Create: `web/tsconfig.json`
- Create: `web/vite.config.ts`
- Create: `web/public/index.html`
- Create: `web/src/index.tsx`
- Create: `web/src/App.tsx`
- Create: `web/src/api/client.ts`
- Create: `web/src/pages/Dashboard.tsx`
- Create: `web/src/pages/ResearchCreation.tsx`
- Create: `web/src/components/Layout.tsx`

**Interfaces:**
- Consumes: `POST /api/survey`, `GET /api/survey/status`, `GET /api/memory` from Task 8
- Produces: React app with Dashboard and ResearchCreation pages

- [ ] **Step 1: Create React project scaffold**

Create `web/package.json`:

```json
{
  "name": "scholaragent-web",
  "version": "1.0.0",
  "private": true,
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.23.1",
    "typescript": "^5.4.5",
    "vite": "^5.3.1",
    "@vitejs/plugin-react": "^4.3.1"
  },
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  }
}
```

Create `web/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "module": "ESNext",
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "jsx": "react-jsx",
    "strict": true,
    "moduleResolution": "bundler",
    "esModuleInterop": true,
    "skipLibCheck": true
  },
  "include": ["src"]
}
```

Create `web/vite.config.ts`:

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://localhost:8000" } },
});
```

Create `web/public/index.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>ScholarAgent</title>
</head>
<body>
  <div id="root"></div>
  <script type="module" src="../src/index.tsx"></script>
</body>
</html>
```

Create `web/src/index.tsx`:

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";

const root = ReactDOM.createRoot(document.getElementById("root")!);
root.render(<React.StrictMode><App /></React.StrictMode>);
```

Create `web/src/api/client.ts`:

```tsx
const API_BASE = "http://localhost:8000";

export async function createSurvey(data: {
  topic: string; keywords?: string; goal?: string; max_papers?: number;
}) {
  const res = await fetch(`${API_BASE}/api/survey`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return res.json();
}

export async function getSurveyStatus() {
  const res = await fetch(`${API_BASE}/api/survey/status`);
  return res.json();
}

export async function interruptSurvey() {
  const res = await fetch(`${API_BASE}/api/survey/interrupt`, { method: "POST" });
  return res.json();
}

export async function resumeSurvey() {
  const res = await fetch(`${API_BASE}/api/survey/resume`, { method: "POST" });
  return res.json();
}

export async function submitFeedback(data: { category: string; content: string }) {
  const res = await fetch(`${API_BASE}/api/feedback`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return res.json();
}
```

- [ ] **Step 2: Create App component with routing**

Create `web/src/App.tsx`:

```tsx
import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import ResearchCreation from "./pages/ResearchCreation";
import AgentExecution from "./pages/AgentExecution";
import KnowledgeExplorer from "./pages/KnowledgeExplorer";
import FinalReview from "./pages/FinalReview";
import Layout from "./components/Layout";

function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/create" element={<ResearchCreation />} />
          <Route path="/execution" element={<AgentExecution />} />
          <Route path="/explorer" element={<KnowledgeExplorer />} />
          <Route path="/review" element={<FinalReview />} />
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}
export default App;
```

- [ ] **Step 3: Create Layout component**

Create `web/src/components/Layout.tsx`:

```tsx
import React from "react";
import { Link, useLocation } from "react-router-dom";

const NAV_ITEMS = [
  { path: "/", label: "Dashboard", icon: "📊" },
  { path: "/create", label: "New Research", icon: "🔬" },
  { path: "/execution", label: "Execution", icon: "⚡" },
  { path: "/explorer", label: "Knowledge", icon: "🧠" },
  { path: "/review", label: "Review", icon: "📝" },
];

export default function Layout({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  return (
    <div style={{ display: "flex", minHeight: "100vh", fontFamily: "system-ui, sans-serif" }}>
      <nav style={{ width: 220, background: "#1a1a2e", color: "#fff", padding: "1rem" }}>
        <h2 style={{ fontSize: "1.2rem", marginBottom: "2rem" }}>ScholarAgent</h2>
        {NAV_ITEMS.map((item) => (
          <Link key={item.path} to={item.path}
            style={{
              display: "block", padding: "0.6rem 1rem",
              color: location.pathname === item.path ? "#4fc3f7" : "#ccc",
              textDecoration: "none", borderRadius: 6, marginBottom: "0.3rem",
              background: location.pathname === item.path ? "rgba(79,195,247,0.1)" : "transparent",
            }}>
            {item.icon} {item.label}
          </Link>
        ))}
      </nav>
      <main style={{ flex: 1, padding: "2rem", background: "#f5f5f5" }}>{children}</main>
    </div>
  );
}
```

- [ ] **Step 4: Create Dashboard page**

Create `web/src/pages/Dashboard.tsx`:

```tsx
import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getSurveyStatus } from "../api/client";

export default function Dashboard() {
  const [currentTask, setCurrentTask] = useState<any>(null);

  useEffect(() => {
    getSurveyStatus().then((data) => { if (data.topic) setCurrentTask(data); });
  }, []);

  return (
    <div>
      <h1>ScholarAgent</h1>
      <p style={{ color: "#666", marginBottom: "2rem" }}>Automated Literature Review Agent</p>
      <h2>Recent Research Tasks</h2>
      {currentTask ? (
        <div style={{ background: "#fff", borderRadius: 8, padding: "1.5rem",
          boxShadow: "0 1px 3px rgba(0,0,0,0.1)", marginBottom: "1rem", maxWidth: 400 }}>
          <h3>{currentTask.topic}</h3>
          <p>Status: {currentTask.status}</p>
          <Link to="/review" style={{ color: "#1976d2" }}>View Report →</Link>
        </div>
      ) : (
        <p style={{ color: "#999" }}>No recent tasks. Start a new research project!</p>
      )}
      <Link to="/create">
        <button style={{ marginTop: "1rem", padding: "0.8rem 2rem", background: "#1976d2",
          color: "#fff", border: "none", borderRadius: 6, cursor: "pointer", fontSize: "1rem" }}>
          + New Research Task
        </button>
      </Link>
    </div>
  );
}
```

- [ ] **Step 5: Create ResearchCreation page**

Create `web/src/pages/ResearchCreation.tsx`:

```tsx
import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { createSurvey } from "../api/client";

export default function ResearchCreation() {
  const navigate = useNavigate();
  const [topic, setTopic] = useState("");
  const [keywords, setKeywords] = useState("");
  const [goal, setGoal] = useState("");
  const [maxPapers, setMaxPapers] = useState(20);

  const handleStart = async () => {
    if (!topic.trim()) return;
    await createSurvey({ topic, keywords, goal, max_papers: maxPapers });
    navigate("/execution");
  };

  return (
    <div style={{ display: "flex", gap: "2rem" }}>
      <div style={{ flex: 1 }}>
        <h2>Research Configuration</h2>
        <div style={{ marginBottom: "1rem" }}>
          <label>Topic</label>
          <input value={topic} onChange={(e) => setTopic(e.target.value)}
            placeholder="e.g., Large Language Models for Software Engineering"
            style={{ display: "block", width: "100%", padding: "0.5rem", marginTop: "0.3rem" }} />
        </div>
        <div style={{ marginBottom: "1rem" }}>
          <label>Keywords</label>
          <input value={keywords} onChange={(e) => setKeywords(e.target.value)}
            placeholder="attention, transformer, BERT"
            style={{ display: "block", width: "100%", padding: "0.5rem", marginTop: "0.3rem" }} />
        </div>
        <div style={{ marginBottom: "1rem" }}>
          <label>Research Goal</label>
          <textarea value={goal} onChange={(e) => setGoal(e.target.value)}
            placeholder="Survey transformer architectures..." rows={3}
            style={{ display: "block", width: "100%", padding: "0.5rem", marginTop: "0.3rem" }} />
        </div>
        <div style={{ marginBottom: "1rem" }}>
          <label>Paper Number</label>
          <input type="number" value={maxPapers} onChange={(e) => setMaxPapers(Number(e.target.value))}
            min={5} max={100}
            style={{ display: "block", width: 80, padding: "0.5rem", marginTop: "0.3rem" }} />
        </div>
      </div>
      <div style={{ flex: 1 }}>
        <h2>Agent Strategy</h2>
        <div style={{ background: "#fff", padding: "1.5rem", borderRadius: 8, boxShadow: "0 1px 3px rgba(0,0,0,0.1)" }}>
          {["Planning Agent", "Search Agent", "Analysis Agent", "Writing Agent"].map((name, i) => (
            <div key={name}>
              <div style={{ padding: "1rem", background: "#e3f2fd", borderRadius: 6, textAlign: "center", fontWeight: 600 }}>{name}</div>
              {i < 3 && <div style={{ textAlign: "center", padding: "0.3rem" }}>↓</div>}
            </div>
          ))}
        </div>
        <button onClick={handleStart} style={{ marginTop: "1.5rem", padding: "0.8rem 2rem",
          background: "#1976d2", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer",
          fontSize: "1rem", width: "100%" }}>Start Agent</button>
      </div>
    </div>
  );
}
```

- [ ] **Step 6: Install dependencies and verify build**

```bash
cd ScholarAgent/web && npm install
```
Expected: Dependencies installed successfully.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat: Web UI scaffold with Dashboard and ResearchCreation pages"
```

---

### Task 10: Web UI — Agent Execution + Knowledge Explorer + Final Review

**Files:**
- Create: `web/src/pages/AgentExecution.tsx`
- Create: `web/src/pages/KnowledgeExplorer.tsx`
- Create: `web/src/pages/FinalReview.tsx`
- Create: `web/src/components/StatusBadge.tsx`
- Create: `web/src/components/ProgressBar.tsx`

- [ ] **Step 1: Create StatusBadge component**

Create `web/src/components/StatusBadge.tsx`:

```tsx
import React from "react";

const STATUS_COLORS: Record<string, string> = {
  COMPLETE: "#4caf50", RUNNING: "#2196f3", PLANNING: "#ff9800",
  RETRIEVAL: "#2196f3", ANALYSIS: "#9c27b0", WRITING: "#009688",
  VALIDATION: "#ff5722", ERROR: "#f44336", INTERRUPTED: "#ffeb3b",
};

export default function StatusBadge({ status }: { status: string }) {
  return (
    <span style={{ display: "inline-block", padding: "0.2rem 0.6rem", borderRadius: 12,
      background: STATUS_COLORS[status] || "#999", color: "#fff", fontSize: "0.8rem", fontWeight: 600 }}>
      {status}
    </span>
  );
}
```

- [ ] **Step 2: Create ProgressBar component**

Create `web/src/components/ProgressBar.tsx`:

```tsx
import React from "react";

export default function ProgressBar({ value, max = 100, color = "#1976d2" }: { value: number; max?: number; color?: string }) {
  const pct = Math.min(100, (value / max) * 100);
  return (
    <div style={{ width: "100%", background: "#e0e0e0", borderRadius: 8, height: 8 }}>
      <div style={{ width: `${pct}%`, background: color, height: "100%", borderRadius: 8 }} />
    </div>
  );
}
```

- [ ] **Step 3: Create AgentExecution page**

Create `web/src/pages/AgentExecution.tsx`:

```tsx
import React, { useEffect, useState } from "react";
import { getSurveyStatus, submitFeedback, interruptSurvey, resumeSurvey } from "../api/client";
import StatusBadge from "../components/StatusBadge";

const STEPS = [
  { key: "PLANNING", label: "Task Planning" },
  { key: "RETRIEVAL", label: "Literature Retrieval" },
  { key: "ANALYSIS", label: "Knowledge Extraction" },
  { key: "WRITING", label: "Writing Review" },
  { key: "VALIDATION", label: "Quality Validation" },
];

export default function AgentExecution() {
  const [status, setStatus] = useState("IDLE");
  const [feedbackInput, setFeedbackInput] = useState("");
  const [isInterrupted, setIsInterrupted] = useState(false);

  useEffect(() => {
    const interval = setInterval(async () => {
      const data = await getSurveyStatus();
      setStatus(data.status);
      if (data.status === "INTERRUPTED") setIsInterrupted(true);
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  const currentStepIndex = STEPS.findIndex((s) => s.key === status);

  return (
    <div>
      <h2>Research Process</h2>
      <p>Status: <StatusBadge status={status} /></p>
      <div style={{ margin: "2rem 0" }}>
        {STEPS.map((step, i) => {
          const isActive = i === currentStepIndex;
          const isDone = i < currentStepIndex;
          return (
            <div key={step.key} style={{ display: "flex", alignItems: "center", gap: "1rem",
              padding: "0.8rem", background: isActive ? "#e3f2fd" : isDone ? "#e8f5e9" : "#fff",
              borderRadius: 6, marginBottom: "0.5rem",
              border: isActive ? "2px solid #1976d2" : "1px solid #e0e0e0" }}>
              <span>{isDone ? "✓" : isActive ? "▶" : "○"}</span>
              <span style={{ fontWeight: isActive ? 600 : 400 }}>{step.label}</span>
              {isActive && <StatusBadge status={status} />}
            </div>
          );
        })}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Create KnowledgeExplorer page**

Create `web/src/pages/KnowledgeExplorer.tsx`:

```tsx
import React from "react";

const SAMPLE_PAPERS = [
  { title: "CodeBERT", year: 2020, method: "Pretrain", contribution: "Code NL understanding", citations: 1200 },
  { title: "GraphCodeBERT", year: 2021, method: "Graph", contribution: "Data flow", citations: 800 },
  { title: "GPT", year: 2020, method: "Autoregressive", contribution: "Language modeling", citations: 5000 },
];

export default function KnowledgeExplorer() {
  return (
    <div>
      <h2>Knowledge Explorer</h2>
      <p style={{ color: "#666", marginBottom: "1.5rem" }}>Memory & Knowledge Base</p>
      <div style={{ background: "#fff", padding: "1.5rem", borderRadius: 8, marginBottom: "1.5rem" }}>
        <h3>Paper List</h3>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ borderBottom: "2px solid #e0e0e0" }}>
              <th style={{ textAlign: "left", padding: "0.5rem" }}>Paper</th>
              <th style={{ textAlign: "left", padding: "0.5rem" }}>Year</th>
              <th style={{ textAlign: "left", padding: "0.5rem" }}>Method</th>
              <th style={{ textAlign: "left", padding: "0.5rem" }}>Contribution</th>
              <th style={{ textAlign: "right", padding: "0.5rem" }}>Citations</th>
            </tr>
          </thead>
          <tbody>
            {SAMPLE_PAPERS.map((p) => (
              <tr key={p.title} style={{ borderBottom: "1px solid #f0f0f0" }}>
                <td style={{ padding: "0.5rem", fontWeight: 600 }}>{p.title}</td>
                <td style={{ padding: "0.5rem" }}>{p.year}</td>
                <td style={{ padding: "0.5rem" }}>{p.method}</td>
                <td style={{ padding: "0.5rem" }}>{p.contribution}</td>
                <td style={{ padding: "0.5rem", textAlign: "right" }}>{p.citations}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Create FinalReview page**

Create `web/src/pages/FinalReview.tsx`:

```tsx
import React from "react";
import ProgressBar from "../components/ProgressBar";

export default function FinalReview() {
  return (
    <div style={{ display: "flex", gap: "2rem" }}>
      <div style={{ flex: 2 }}>
        <h2>Research Topic:</h2>
        <p style={{ fontSize: "1.1rem", color: "#333", marginBottom: "1.5rem" }}>
          Large Language Models for Software Engineering
        </p>
        <div style={{ display: "flex", gap: "2rem", marginBottom: "2rem" }}>
          <div><p>Quality Score: <strong style={{ fontSize: "1.3rem" }}>91/100</strong></p><ProgressBar value={91} color="#4caf50" /></div>
          <div><p>Citation Coverage: <strong>94%</strong></p><ProgressBar value={94} color="#2196f3" /></div>
          <div><p>Completeness: <strong>89%</strong></p><ProgressBar value={89} color="#ff9800" /></div>
        </div>
        <div style={{ background: "#fff", padding: "2rem", borderRadius: 8, boxShadow: "0 1px 3px rgba(0,0,0,0.1)" }}>
          <h3>Abstract</h3>
          <p style={{ lineHeight: 1.6 }}>Large language models have revolutionized the field of software engineering...</p>
          <h3>1. Introduction</h3>
          <p style={{ lineHeight: 1.6 }}>The intersection of large language models and software engineering...</p>
        </div>
      </div>
      <div style={{ flex: 1 }}>
        <h3>Evaluation Report</h3>
        <div style={{ background: "#fff", padding: "1rem", borderRadius: 8 }}>
          <p>✓ Structure</p><p>✓ Citation</p><p>✓ Coverage</p>
          <p style={{ color: "#ff9800" }}>△ Need more recent papers</p>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: Web UI — Agent Execution, Knowledge Explorer, Final Review pages"
```

---

### Task 11: Mechanism Demo + Integration Tests

**Files:**
- Create: `tests/test_demo.py`

- [ ] **Step 1: Write mechanism demo tests**

Create `tests/test_demo.py`:

```python
"""
Mechanism Demo — demonstrates 3 required behaviors with mock LLM:
1. Guardrail intercepts dangerous action
2. Feedback loop detects failure and triggers correction
3. Feedback dimension (deep focus) deterministic behavior
"""
import pytest
from agent.core.llm import MockLLM
from agent.core.harness import Harness, HarnessConfig
from agent.core.state import AgentState
from agent.guardrails.op_safety import OpSafety, GuardrailVerdict
from agent.feedback.base import ValidationResult
from agent.feedback.check_citations import CitationChecker
from agent.feedback.aggregator import FeedbackAggregator


class TestMechanismDemo:
    def test_guardrail_blocks_rm_rf(self):
        guard = OpSafety()
        ctx = {"action": "shell_exec", "params": {"command": "rm -rf /important/data"}}
        result = guard.check(ctx)
        assert result.verdict == GuardrailVerdict.REQUIRE_APPROVAL

    def test_guardrail_allows_safe_command(self):
        guard = OpSafety()
        ctx = {"action": "shell_exec", "params": {"command": "ls -la /home"}}
        result = guard.check(ctx)
        assert result.verdict == GuardrailVerdict.PASS

    def test_guardrail_blocks_drop_table(self):
        guard = OpSafety()
        ctx = {"action": "shell_exec", "params": {"command": "DROP TABLE users"}}
        result = guard.check(ctx)
        assert result.verdict == GuardrailVerdict.REQUIRE_APPROVAL

    def test_feedback_loop_triggers_rewrite(self):
        llm = MockLLM(fixed_response="Survey content")
        h = Harness(config=HarnessConfig(max_retries=3, quality_threshold=0.7), llm=llm)
        h.start(topic="Test")
        h.state.transition_to(AgentState.VALIDATION)
        bad_result = ValidationResult(
            validator_name="check_citations", passed=False, score=0.3,
            issues=["Missing citations for 3 claims"],
            repair_instructions="Add citations to all claims using [@paper_id] format",
        )
        h.inject_feedback([bad_result])
        assert h.state.current_state == AgentState.WRITING
        assert h.retry_count == 1

    def test_feedback_loop_stops_after_max_retries(self):
        llm = MockLLM(fixed_response="Content")
        h = Harness(config=HarnessConfig(max_retries=2, quality_threshold=0.7), llm=llm)
        h.start(topic="Test")
        h.state.transition_to(AgentState.VALIDATION)
        h.retry_count = 2
        bad_result = ValidationResult(validator_name="test", passed=False, score=0.3, issues=["Fail"])
        h.inject_feedback([bad_result])
        assert h.state.current_state == AgentState.COMPLETE
        assert h.has_warnings is True

    def test_feedback_loop_passes_on_good_quality(self):
        llm = MockLLM(fixed_response="Content")
        h = Harness(config=HarnessConfig(max_retries=3, quality_threshold=0.7), llm=llm)
        h.start(topic="Test")
        h.state.transition_to(AgentState.VALIDATION)
        good_result = ValidationResult(validator_name="check_citations", passed=True, score=0.95, issues=[])
        h.inject_feedback([good_result])
        assert h.state.current_state == AgentState.COMPLETE

    def test_citation_checker_deterministic(self):
        checker = CitationChecker()
        chapter = {"content": "Transformers [@v2017] are effective. [@unknown] is missing.", "paper_ids": ["v2017"]}
        result1 = checker.validate(chapter)
        result2 = checker.validate(chapter)
        assert result1.passed == result2.passed
        assert result1.score == result2.score
        assert result1.issues == result2.issues

    def test_aggregator_deterministic(self):
        agg = FeedbackAggregator(pass_threshold=0.7)
        results = [ValidationResult(validator_name="a", passed=True, score=0.9),
                   ValidationResult(validator_name="b", passed=False, score=0.3, issues=["Bad"])]
        report1 = agg.aggregate(results)
        report2 = agg.aggregate(results)
        assert report1.overall_passed == report2.overall_passed
        assert report1.overall_score == report2.overall_score

    def test_mock_llm_deterministic(self):
        llm = MockLLM(fixed_response="Always the same")
        r1 = llm.generate("sys", "msg")
        r2 = llm.generate("sys", "msg")
        assert r1.text == r2.text
        assert r1.text == "Always the same"
```

- [ ] **Step 2: Run mechanism demo tests**

```bash
cd ScholarAgent && python -m pytest tests/test_demo.py -v
```
Expected: All 10 tests PASS

- [ ] **Step 3: Run complete test suite**

```bash
cd ScholarAgent && python -m pytest tests/ -v
```
Expected: 82+ tests PASS

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat: mechanism demo with guardrail interception, feedback loop, and deterministic validators"
```

---

### Task 12: Docker + CI Configuration

**Files:**
- Create: `Dockerfile`
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Create Dockerfile**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY web/package.json web/
RUN cd web && npm install

COPY . .

RUN cd web && npm run build

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Create CI configuration**

Create `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  unit-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run tests
        run: python -m pytest tests/ -v

  docker-build:
    runs-on: ubuntu-latest
    needs: unit-test
    steps:
      - uses: actions/checkout@v4
      - name: Build Docker image
        run: docker build -t scholaragent .
```

- [ ] **Step 3: Create memory directory structure**

```bash
mkdir -p memory/session memory/persistent
touch memory/persistent/.gitkeep
```

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat: Dockerfile and GitHub Actions CI configuration"
```

---

### Task 13: Documentation

**Files:**
- Create: `README.md`
- Create: `SPEC_PROCESS.md`
- Create: `AGENT_LOG.md`
- Create: `REFLECTION.md`

- [ ] **Step 1: Write README.md**

```markdown
# ScholarAgent

An automated literature review agent that generates CVPR-style survey papers from a research topic.

## Architecture

- **Agent Harness** (Python): Self-coded state machine with tool dispatch, guardrails, memory, and feedback loop
- **API Layer** (FastAPI): REST + WebSocket endpoints
- **Web UI** (React): Dashboard, Research Creation, Agent Execution, Knowledge Explorer, Final Review

## Quick Start

```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your LLM API key
make run-api
```

## Docker

```bash
docker build -t scholaragent .
docker run -p 8000:8000 --env-file .env scholaragent
```

## Key Configuration

| Variable | Required | Description |
|----------|----------|-------------|
| LLM_API_KEY | Yes | OpenAI or Anthropic API key |
| LLM_MODEL | No | Model name (default: gpt-4o) |

## Security

- API keys are never hardcoded in source code
- Use .env file (added to .gitignore) or Windows Credential Manager
- See SPEC.md section 7 for full credential threat model

## Project Structure

```
ScholarAgent/
├── agent/          # Agent Harness core
├── api/            # FastAPI layer
├── web/            # React frontend
├── tests/          # Test suite
├── memory/         # Session and persistent storage
└── SPEC.md         # Full design specification
```

## Deliverables

- SPEC.md — Design specification
- PLAN.md — Implementation plan
- SPEC_PROCESS.md — Process documentation
- AGENT_LOG.md — Development log
- REFLECTION.md — Reflection report
```

- [ ] **Step 2: Write SPEC_PROCESS.md skeleton**

```markdown
# SPEC_PROCESS.md — Process Documentation

## Brainstorming Key Nodes

### Node 1: Topic Clarification
The agent asked about the core idea behind ScholarAgent. The initial concept was refined from "a research assistant" to "an automated survey paper generator with CVPR format output."

### Node 2: Architecture Approach
Three approaches were considered:
- Monolithic Python + Jinja2 (rejected: limited UI)
- Modular Python Harness + React Frontend (selected: clean separation)
- Microservices (rejected: over-engineering for single-user)

### Node 3: Deep Dimension Selection
The agent recommended Guardrails as the deep dimension. The user chose Feedback loop instead, citing the importance of citation accuracy and hallucination detection for academic quality.

## 3 Key Iterations

### Iteration 1: Paper Source Strategy
User provided detailed multi-source retrieval strategy (arXiv primary, Semantic Scholar auxiliary, Google Scholar fallback). The agent incorporated this fully into the design.

### Iteration 2: Web UI Pages
User specified 5 pages with detailed layouts. The agent confirmed the design and integrated into the spec.

### Iteration 3: Course Requirements Integration
Two course requirement files were added to the project root. The agent updated the SPEC to include the Domain and Mechanism Design section and deliverables list.

## AI Contributions
- Recommended three architectural approaches with trade-off analysis
- Suggested Feedback loop as the deep dimension (user agreed)
- Designed the state machine with specific state transitions

## User Corrections
- User chose Feedback over Guardrails as the deep dimension
- User specified the exact multi-source retrieval strategy
- User designed the 5-page UI layout

## Brainstorming Skill Assessment
Strengths: Systematic question flow, thorough exploration of approaches
Weaknesses: None significant — the process matched the project well
```

- [ ] **Step 3: Write AGENT_LOG.md skeleton**

```markdown
# AGENT_LOG.md

| Timestamp | Task | Skill | Key Event | Human Intervention |
|-----------|------|-------|-----------|-------------------|
| 2026-07-26 | Brainstorming | brainstorming | Project context explored | — |
| 2026-07-26 | Brainstorming | brainstorming | Requirements clarified | User specified multi-source retrieval strategy |
| 2026-07-26 | Brainstorming | brainstorming | Architecture approved | User chose Modular Python + React approach |
| 2026-07-26 | Brainstorming | brainstorming | UI design specified | User designed 5 pages |
| 2026-07-26 | Brainstorming | brainstorming | Course requirements integrated | User added 2 course files |
| 2026-07-26 | SPEC written | brainstorming | SPEC.md created | — |
| 2026-07-26 | PLAN written | writing-plans | PLAN.md created | — |
| TBD | Task 1 | tdd | LLM abstraction + scaffolding | — |
| TBD | Task 2 | tdd | State machine + harness loop | — |
| TBD | ... | ... | ... | ... |
```

- [ ] **Step 4: Write REFLECTION.md skeleton**

```markdown
# REFLECTION.md

> 1500-2500 words. To be completed after implementation.

## 1. Superpowers Skills Assessment

### Which skills were most effective?
- brainstorming: ...
- writing-plans: ...
- test-driven-development: ...

### Which felt like "form over substance"?

## 2. TDD in AI Collaboration

- Was TDD an amplifier or obstacle?
- How did red-green-refactor work with AI-generated code?

## 3. Subagent-Driven Workflow

- How long could agents run without going off-track?
- What task granularity worked best?

## 4. SPEC/PLAN Quality Impact

- Example of a spec gap that caused subagent deviation
- What was fixed and how

## 5. Prompt/Context Strategy

- What worked best?
- Why was it effective?

## 6. Credentials & Distribution

- What problems did these requirements force you to think through?

## 7. If I Redid This

- What would I change?

## 8. Critique of Superpowers

- What assumptions does it make?
- Did those hold for this project?
```

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "docs: README, SPEC_PROCESS, AGENT_LOG, and REFLECTION seed"
```

---

## Spec Coverage Matrix

| SPEC Section | Task # | Status |
|-------------|--------|--------|
| 3.1 Agent Harness Core | Task 1, 2 | Planned |
| 3.2 Tool System | Task 3 | Planned |
| 3.3 Memory System | Task 5 | Planned |
| 3.4 Feedback System | Task 6, 7 | Planned |
| 3.5 Guardrail System | Task 4 | Planned |
| 3.6 Configuration | Task 1, 2 (HarnessConfig) | Planned |
| 4.1 Performance | Task 8, 12 | Planned |
| 4.2 Security (Credentials) | Task 1 (.env), Task 8 | Planned |
| 4.3 Usability (Web UI) | Task 9, 10 | Planned |
| 4.4 Observability | Task 8 (WebSocket) | Planned |
| 5 System Architecture | All tasks | Planned |
| 6 Data Model | Task 8 (Pydantic) | Planned |
| 7 Credentials & Distribution | Task 12 | Planned |
| 8 Tech Stack | All tasks | Planned |
| 9 Domain & Mechanism Design | Task 4, 6, 7, 11 | Planned |
| 10 Acceptance Criteria | All tasks (verified by tests) | Planned |
| Appendix B Deliverables | All tasks | Planned |
```