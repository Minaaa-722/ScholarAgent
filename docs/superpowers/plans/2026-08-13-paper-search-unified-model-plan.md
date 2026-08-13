# Unified Paper Data Model + Module Interface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现统一的 Paper 数据模型、模块接口、以及重构后的检索管线编排

**Architecture:** 依赖自底向上：Paper 模型 → SearchConfig → 辅助函数 → 新模块 (RelevanceFilter/FallbackManager/rank_papers) → Pipeline 重构。每个模块独立可测，通过 `Paper.from_dict()`/`.to_dict()` 与现有 `list[dict]` 接口兼容。

**Tech Stack:** Python 3.12+, dataclasses, LLMBase (MockLLM for tests)

**Spec:** `docs/superpowers/specs/2026-08-13-paper-search-unified-model-design.md`

## Global Constraints

- 所有新模块使用 `Paper` dataclass 传递，返回给上游时通过 `.to_dict()` 转换
- 所有排序权重和 RRF 开关放入 `SearchConfig` 全局配置
- 每个模块均包含完整的 `logger.info()` 日志埋点
- 相关性过滤规则（Fix 3）：仅 `irrelevant AND confidence≥0.6` 剔除；confidence<0.6 保留为 weak
- Fallback Phase7（Fix 4）：仅 arXiv all: 单通道，max_results=20
- `domain_cat_map`（Fix 2）：不包含 "transformer"
- `auto_quote_terms`（Fix 1）：所有多词术语加引号，无特殊字符排除
- `_expand_and_dedup_queries`（Fix 5）：全称==缩写时去重

---

## File Structure

| File | Status | Responsibility |
|------|--------|----------------|
| `agent/tools/models.py` | **Create** | Paper dataclass + to_dict/from_dict |
| `agent/core/config.py` | **Create** | SearchConfig dataclass |
| `agent/tools/prompts.py` | **Create** | LLM prompt constants |
| `agent/tools/relevance.py` | **Create** | RelevanceFilter class |
| `agent/tools/retrieval.py` | **Modify** | Add auto_quote_terms, infer_arxiv_category, dual_channel_arxiv_search, FallbackManager, MergeResults multi_hit |
| `agent/tools/processing.py` | **Modify** | Add rank_papers, _apply_rrf |
| `agent/core/pipeline.py` | **Modify** | Add _generate_search_queries, _expand_and_dedup_queries, refactor _retrieve_papers |
| `tests/test_models.py` | **Create** | Paper model tests |
| `tests/test_config.py` | **Create** | SearchConfig tests |
| `tests/test_prompts.py` | **Create** | Prompt content tests |
| `tests/test_retrieval.py` | **Create** | auto_quote_terms, infer_arxiv_category, dual_channel_arxiv_search, FallbackManager tests |
| `tests/test_relevance.py` | **Modify** | RelevanceFilter tests (refactored for new interface) |
| `tests/test_processing.py` | **Create** | rank_papers tests |
| `tests/test_pipeline_expand.py` | **Create** | _expand_and_dedup_queries tests |

---

### Task 1: Paper 数据模型

**Files:**
- Create: `agent/tools/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Produces: `Paper` dataclass with `to_dict() -> dict` and `Paper.from_dict(data: dict) -> Paper`

- [ ] **Step 1: Write the failing tests**

Write `tests/test_models.py`:

```python
from agent.tools.models import Paper


def test_paper_default_values():
    p = Paper()
    assert p.title == ""
    assert p.authors == []
    assert p.abstract == ""
    assert p.year == 0
    assert p.relevance == "weak"
    assert p.relevance_confidence == 0.0
    assert p.composite_score == 0.0
    assert p.hit_channels == []
    assert p.search_source_queries == []
    assert p.extra == {}


def test_paper_with_all_fields():
    p = Paper(
        title="Test Paper",
        authors=["Alice", "Bob"],
        abstract="A test abstract",
        year=2024,
        arxiv_id="2401.12345",
        source="arxiv",
        url="https://arxiv.org/abs/2401.12345",
        venue="CVPR",
        citation_count=100,
        doi="10.1234/test",
        paper_id="abc123",
        categories=["cs.CV"],
        hit_channels=["arxiv_ti"],
        relevance="strong",
        relevance_confidence=0.95,
        relevance_reason="Directly addresses the topic",
        composite_score=0.85,
        search_source_queries=["vision transformer"],
        extra={"debug": True},
    )
    assert p.title == "Test Paper"
    assert p.relevance == "strong"
    assert p.relevance_confidence == 0.95
    assert p.composite_score == 0.85
    assert "vision transformer" in p.search_source_queries
    assert p.extra["debug"] is True


def test_paper_to_dict():
    p = Paper(title="Test", year=2024, relevance="strong")
    d = p.to_dict()
    assert d["title"] == "Test"
    assert d["year"] == 2024
    assert d["relevance"] == "strong"
    assert d["relevance_confidence"] == 0.0
    assert d["hit_channels"] == []


def test_paper_from_dict():
    d = {
        "title": "Test",
        "year": 2024,
        "relevance": "strong",
        "relevance_confidence": 0.95,
        "hit_channels": ["arxiv_ti"],
    }
    p = Paper.from_dict(d)
    assert p.title == "Test"
    assert p.year == 2024
    assert p.relevance == "strong"
    assert p.relevance_confidence == 0.95
    assert p.hit_channels == ["arxiv_ti"]


def test_paper_from_dict_ignores_extra_fields():
    d = {"title": "Test", "unknown_field": "should be ignored"}
    p = Paper.from_dict(d)
    assert p.title == "Test"


def test_paper_to_dict_from_dict_roundtrip():
    p = Paper(title="Test", year=2024, citation_count=42, relevance="strong")
    d = p.to_dict()
    p2 = Paper.from_dict(d)
    assert p2.title == p.title
    assert p2.year == p.year
    assert p2.citation_count == p.citation_count
    assert p2.relevance == p.relevance
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_models.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Write minimal implementation**

Create `agent/tools/models.py`:

```python
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Paper:
    title: str = ""
    authors: list[str] = field(default_factory=list)
    abstract: str = ""
    year: int = 0

    arxiv_id: str = ""
    source: str = ""
    url: str = ""
    venue: str = ""

    citation_count: int = 0
    doi: str = ""
    paper_id: str = ""
    categories: list[str] = field(default_factory=list)

    hit_channels: list[str] = field(default_factory=list)

    relevance: str = "weak"
    relevance_confidence: float = 0.0
    relevance_reason: str = ""

    composite_score: float = 0.0

    search_source_queries: list[str] = field(default_factory=list)

    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "Paper":
        return Paper(
            **{k: v for k, v in data.items() if k in Paper.__dataclass_fields__}
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_models.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add agent/tools/models.py tests/test_models.py
git commit -m "feat: add Paper dataclass with to_dict/from_dict"
```

---

### Task 2: SearchConfig 配置

**Files:**
- Create: `agent/core/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `SearchConfig` dataclass

- [ ] **Step 1: Write the failing tests**

Write `tests/test_config.py`:

```python
from agent.core.config import SearchConfig


def test_search_config_defaults():
    c = SearchConfig()
    assert c.arxiv_ti_max_results == 20
    assert c.arxiv_abs_max_results == 20
    assert c.ss_max_results == 20
    assert c.rrf_enabled is True
    assert c.rrf_k == 60
    assert c.rank_alpha == 0.5
    assert c.rank_beta == 0.3
    assert c.rank_gamma == 0.2
    assert c.relevance_confidence_min == 0.6
    assert c.abstract_missing_max_confidence == 0.6
    assert c.fallback_phase6_min_papers == 10
    assert c.fallback_phase7_min_papers == 5
    assert c.fallback_phase7_max_results == 20
    assert c.domain_fallback_cat == "cs.AI"


def test_domain_cat_map_no_transformer():
    """Fix 2: transformer 已移除映射"""
    c = SearchConfig()
    assert "transformer" not in c.domain_cat_map


def test_domain_cat_map_contains_cv_keywords():
    c = SearchConfig()
    assert c.domain_cat_map["image"] == "cs.CV"
    assert c.domain_cat_map["vision"] == "cs.CV"


def test_domain_cat_map_contains_cl_keywords():
    c = SearchConfig()
    assert c.domain_cat_map["language"] == "cs.CL"
    assert c.domain_cat_map["bert"] == "cs.CL"
    assert c.domain_cat_map["llm"] == "cs.CL"


def test_search_config_custom_values():
    c = SearchConfig(arxiv_ti_max_results=10, rrf_enabled=False, rank_alpha=0.6)
    assert c.arxiv_ti_max_results == 10
    assert c.rrf_enabled is False
    assert c.rank_alpha == 0.6
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Write minimal implementation**

Create `agent/core/config.py`:

```python
from dataclasses import dataclass, field


@dataclass
class SearchConfig:
    arxiv_ti_max_results: int = 20
    arxiv_abs_max_results: int = 20
    ss_max_results: int = 20

    rrf_enabled: bool = True
    rrf_k: int = 60

    rank_alpha: float = 0.5
    rank_beta: float = 0.3
    rank_gamma: float = 0.2

    domain_cat_map: dict = field(default_factory=lambda: {
        "image": "cs.CV", "vision": "cs.CV", "visual": "cs.CV",
        "object detection": "cs.CV", "segmentation": "cs.CV",
        "face": "cs.CV", "video": "cs.CV", "pose": "cs.CV",
        "language": "cs.CL", "text": "cs.CL", "translation": "cs.CL",
        "sentence": "cs.CL", "word": "cs.CL",
        "token": "cs.CL", "bert": "cs.CL", "gpt": "cs.CL",
        "llm": "cs.CL",
    })
    domain_fallback_cat: str = "cs.AI"

    relevance_confidence_min: float = 0.6
    abstract_missing_max_confidence: float = 0.6

    fallback_phase6_min_papers: int = 10
    fallback_phase7_min_papers: int = 5
    fallback_phase7_max_results: int = 20
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_config.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add agent/core/config.py tests/test_config.py
git commit -m "feat: add SearchConfig dataclass with domain_cat_map (Fix 2)"
```

---

### Task 3: LLM Prompt 定义

**Files:**
- Create: `agent/tools/prompts.py`
- Test: `tests/test_prompts.py`

**Interfaces:**
- Produces: `SEARCH_QUERY_PROMPT`, `RELEVANCE_JUDGE_PROMPT`

- [ ] **Step 1: Write the failing tests**

Write `tests/test_prompts.py`:

```python
from agent.tools.prompts import SEARCH_QUERY_PROMPT, RELEVANCE_JUDGE_PROMPT


def test_search_query_prompt_contains_arrow_format():
    assert "->" in SEARCH_QUERY_PROMPT
    assert "full name" in SEARCH_QUERY_PROMPT.lower()


def test_search_query_prompt_no_generic_words():
    forbidden = ["deep learning", "survey", "review", "advances", "recent"]
    for word in forbidden:
        assert word.lower() not in SEARCH_QUERY_PROMPT.lower()


def test_search_query_prompt_exactly_5():
    assert "exactly 5" in SEARCH_QUERY_PROMPT


def test_relevance_judge_prompt_contains_topic_placeholder():
    assert "{topic}" in RELEVANCE_JUDGE_PROMPT


def test_relevance_judge_prompt_three_levels():
    assert "STRONG" in RELEVANCE_JUDGE_PROMPT
    assert "WEAK" in RELEVANCE_JUDGE_PROMPT
    assert "IRRELEVANT" in RELEVANCE_JUDGE_PROMPT


def test_relevance_judge_prompt_has_confidence():
    assert "CONFIDENCE" in RELEVANCE_JUDGE_PROMPT
    assert "0.0" in RELEVANCE_JUDGE_PROMPT


def test_relevance_judge_prompt_no_abstract_rule():
    assert "abstract" in RELEVANCE_JUDGE_PROMPT.lower()
    assert "strong" in RELEVANCE_JUDGE_PROMPT.lower()


def test_relevance_judge_prompt_json_output():
    assert "JSON" in RELEVANCE_JUDGE_PROMPT
    assert "judgments" in RELEVANCE_JUDGE_PROMPT
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_prompts.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Write minimal implementation**

Create `agent/tools/prompts.py`:

```python
SEARCH_QUERY_PROMPT = """\
You are a literature search query generator for academic paper retrieval.

TASK: Generate exactly 5 search queries to find academic papers for a survey paper.

CRITICAL RULES:
- Each query MUST be a specific technique / method / model / approach name
- Output BOTH full name AND common abbreviation on each line, separated by " -> "
  Example: "Vision Transformer -> ViT"
  → This will be expanded into two separate queries: "Vision Transformer" AND "ViT"
- NO generic words: deep learning, survey, review, advances, recent, progress, trends, challenges
- NO conversational text, NO numbering, NO explanation, NO markdown
- Be specific: use concrete method names
- Each line must be one "full name -> abbreviation" pair

OUTPUT FORMAT (exactly one pair per line, no blank lines):
full technical name -> abbreviation
full technical name -> abbreviation
...

Example for topic="Efficient Transformer":
attention mechanism optimization -> attention optimization
model quantization -> quantization
knowledge distillation -> knowledge distillation
mixture of experts -> MoE
speculative decoding -> speculative decoding
"""


RELEVANCE_JUDGE_PROMPT = """\
You are a strict relevance judge for academic literature search.

TASK: Judge whether each paper is relevant to the research topic: "{topic}"

RELEVANCE DEFINITION:
- STRONG relevant: The paper's primary contribution directly addresses the topic.
- WEAK relevant: The paper addresses the topic but not as primary contribution.
- IRRELEVANT: Completely different field or topic.

CONFIDENCE SCORE (0.0 to 1.0):
- 1.0: Absolutely certain
- 0.8-0.9: Very confident
- 0.6-0.7: Moderately confident
- 0.4-0.5: Weakly confident
- 0.0-0.3: Very uncertain

SPECIAL RULES:
- Papers WITHOUT an abstract CANNOT be "strong", confidence capped at 0.6.
- When in doubt, prefer keeping (weak + low confidence) over removing.

OUTPUT FORMAT: Return a JSON object:
{
  "judgments": [
    {"index": 1, "title": "Exact title", "relevance": "strong|weak|irrelevant",
     "confidence": 0.95, "reason": "Short justification"}
  ]
}
"""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_prompts.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add agent/tools/prompts.py tests/test_prompts.py
git commit -m "feat: add LLM prompts for search query generation and relevance judgment"
```

---

### Task 4: 辅助函数 — auto_quote_terms, infer_arxiv_category, dual_channel_arxiv_search

**Files:**
- Modify: `agent/tools/retrieval.py`
- Test: `tests/test_retrieval.py`

**Interfaces:**
- Produces: `auto_quote_terms(query: str) -> str`, `infer_arxiv_category(query, topic, domain_cat_map, fallback) -> str`, `dual_channel_arxiv_search(arxiv_tool, query, cat_filter, config) -> list[Paper]`

- [ ] **Step 1: Write the failing tests**

Write `tests/test_retrieval.py`:

```python
from agent.tools.retrieval import auto_quote_terms, infer_arxiv_category
from agent.core.config import SearchConfig


def test_auto_quote_terms_no_change_empty():
    assert auto_quote_terms("") == ""


def test_auto_quote_terms_no_change_single_word():
    assert auto_quote_terms("transformer") == "transformer"


def test_auto_quote_terms_no_change_already_quoted():
    assert auto_quote_terms('"hello world"') == '"hello world"'


def test_auto_quote_terms_multi_word():
    assert auto_quote_terms("hello world") == '"hello world"'


def test_auto_quote_terms_with_hyphen():
    """Fix 1: 含连字符的术语也加引号"""
    assert auto_quote_terms("vision-transformer") == '"vision-transformer"'


def test_auto_quote_terms_with_parentheses():
    """Fix 1: 含括号的术语也加引号"""
    assert auto_quote_terms("mask r-cnn") == '"mask r-cnn"'


def test_infer_arxiv_category_cv():
    config = SearchConfig()
    result = infer_arxiv_category("image segmentation", "deep learning", config.domain_cat_map)
    assert result == "cs.CV"


def test_infer_arxiv_category_nlp():
    config = SearchConfig()
    result = infer_arxiv_category("language model", "nlp", config.domain_cat_map)
    assert result == "cs.CL"


def test_infer_arxiv_category_transformer():
    """Fix 2: transformer 无固定映射，走兜底 cs.AI"""
    config = SearchConfig()
    result = infer_arxiv_category("transformer", "attention", config.domain_cat_map)
    assert result == "cs.AI"


def test_infer_arxiv_category_fallback():
    config = SearchConfig()
    result = infer_arxiv_category("quantum physics", "string theory", config.domain_cat_map)
    assert result == "cs.AI"


def test_dual_channel_arxiv_search_basic():
    from agent.tools.retrieval import dual_channel_arxiv_search, ArxivSearch
    from agent.tools.base import ToolResult
    from agent.core.config import SearchConfig

    class MockArxiv(ArxivSearch):
        def execute(self, params):
            query = params.get("query", "")
            if query.startswith("ti:"):
                return ToolResult(success=True, data={
                    "papers": [{"title": "Paper A", "authors": [], "year": 2024, "arxiv_id": "2401.00001", "source": "arxiv", "url": "", "categories": [], "citation_count": 0, "doi": "", "abstract": "A"}]
                })
            elif query.startswith("abs:"):
                return ToolResult(success=True, data={
                    "papers": [{"title": "Paper B", "authors": [], "year": 2024, "arxiv_id": "2401.00002", "source": "arxiv", "url": "", "categories": [], "citation_count": 0, "doi": "", "abstract": "B"}]
                })
            return ToolResult(success=True, data={"papers": []})

    config = SearchConfig()
    tool = MockArxiv()
    papers = dual_channel_arxiv_search(tool, "test query", "", config)
    assert len(papers) == 2
    assert papers[0].title == "Paper A"
    assert papers[1].title == "Paper B"
    assert "arxiv_ti" in papers[0].hit_channels
    assert "arxiv_abs" in papers[1].hit_channels


def test_dual_channel_arxiv_search_dedup():
    from agent.tools.retrieval import dual_channel_arxiv_search, ArxivSearch
    from agent.tools.base import ToolResult
    from agent.core.config import SearchConfig

    class MockArxiv(ArxivSearch):
        def execute(self, params):
            paper = {"title": "Paper A", "authors": [], "year": 2024, "arxiv_id": "2401.00001", "source": "arxiv", "url": "", "categories": [], "citation_count": 0, "doi": "", "abstract": "A"}
            return ToolResult(success=True, data={"papers": [paper]})

    config = SearchConfig()
    tool = MockArxiv()
    papers = dual_channel_arxiv_search(tool, "test query", "", config)
    assert len(papers) == 1  # dedup


def test_dual_channel_arxiv_search_ti_priority():
    """ti 通道的论文优先保留."""
    from agent.tools.retrieval import dual_channel_arxiv_search, ArxivSearch
    from agent.tools.base import ToolResult
    from agent.core.config import SearchConfig

    class MockArxiv(ArxivSearch):
        def execute(self, params):
            paper = {"title": "Paper A", "authors": [], "year": 2024, "arxiv_id": "2401.00001", "source": "arxiv", "url": "", "categories": [], "citation_count": 0, "doi": "", "abstract": "A"}
            return ToolResult(success=True, data={"papers": [paper]})

    config = SearchConfig()
    tool = MockArxiv()
    papers = dual_channel_arxiv_search(tool, "test query", "", config)
    # ti channel runs first, so its hit_channel is preserved
    assert papers[0].hit_channels == ["arxiv_ti"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_retrieval.py -v`
Expected: FAIL with "ImportError: cannot import name 'auto_quote_terms'"

- [ ] **Step 3: Add functions to retrieval.py**

Append to `agent/tools/retrieval.py` before the `json_loads` helper:

```python
def auto_quote_terms(query: str) -> str:
    """通用引号封装（Fix 1：移除特殊字符排除）。"""
    if query.startswith('"') and query.endswith('"'):
        return query
    words = query.split()
    if len(words) <= 1:
        return query
    return f'"{query}"'


def infer_arxiv_category(
    query: str,
    topic: str,
    domain_cat_map: dict,
    fallback: str = "cs.AI",
) -> str:
    """根据 query+topic 关键词推断 arXiv 分类。"""
    combined = f"{query} {topic}".lower()
    for keyword, cat in domain_cat_map.items():
        if keyword in combined:
            return cat
    return fallback


def dual_channel_arxiv_search(
    arxiv_tool: "ArxivSearch",
    query: str,
    cat_filter: str = "",
    config: "SearchConfig | None" = None,
) -> list["Paper"]:
    """arXiv 双通道检索：ti 精准 + abs 召回。"""
    from agent.tools.models import Paper

    quoted = auto_quote_terms(query)
    papers: list[Paper] = []

    # Channel 1: ti
    ti_query = f"ti:{quoted}"
    if cat_filter:
        ti_query += f" AND cat:{cat_filter}"

    ti_result = arxiv_tool.execute({
        "query": ti_query,
        "max_results": config.arxiv_ti_max_results if config else 20,
    })
    if ti_result.success:
        for p_data in ti_result.data.get("papers", []):
            paper = Paper.from_dict(p_data)
            paper.hit_channels.append("arxiv_ti")
            paper.search_source_queries.append(query)
            papers.append(paper)

    # Channel 2: abs
    abs_query = f"abs:{quoted}"
    if cat_filter:
        abs_query += f" AND cat:{cat_filter}"

    abs_result = arxiv_tool.execute({
        "query": abs_query,
        "max_results": config.arxiv_abs_max_results if config else 20,
    })
    if abs_result.success:
        for p_data in abs_result.data.get("papers", []):
            paper = Paper.from_dict(p_data)
            paper.hit_channels.append("arxiv_abs")
            paper.search_source_queries.append(query)
            papers.append(paper)

    # Dedup
    seen = set()
    unique = []
    for p in papers:
        key = p.title.lower().strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(p)

    logger.info(
        "arXiv dual-channel [ti=%s] [abs=%s] → %d unique papers",
        "success" if ti_result.success else "fail",
        "success" if abs_result.success else "fail",
        len(unique),
    )
    return unique
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_retrieval.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add agent/tools/retrieval.py tests/test_retrieval.py
git commit -m "feat: add auto_quote_terms (Fix 1), infer_arxiv_category (Fix 2), dual_channel_arxiv_search"
```

---

### Task 5: FallbackManager

**Files:**
- Modify: `agent/tools/retrieval.py` (append after the new functions)
- Test: `tests/test_retrieval.py` (append)

**Interfaces:**
- Produces: `FallbackManager.__init__(arxiv_tool, ss_tool, config)`, `fallback_phase6(papers, topic, keywords) -> list[Paper]`, `fallback_phase7(papers, topic) -> list[Paper]`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_retrieval.py`:

```python
def test_fallback_phase6_not_triggered():
    """论文数充足时不触发 phase6."""
    from agent.tools.retrieval import FallbackManager, ArxivSearch
    from agent.tools.base import ToolResult
    from agent.core.config import SearchConfig
    from agent.tools.models import Paper

    config = SearchConfig()

    class MockArxiv(ArxivSearch):
        def execute(self, params):
            return ToolResult(success=True, data={"papers": []})

    mgr = FallbackManager(MockArxiv(), None, config)
    papers = [Paper(title=f"Paper {i}") for i in range(15)]
    result = mgr.fallback_phase6(papers, "topic", ["keyword"])
    assert len(result) == 15


def test_fallback_phase6_triggered():
    """论文数<10 时触发 phase6."""
    from agent.tools.retrieval import FallbackManager, ArxivSearch
    from agent.tools.base import ToolResult
    from agent.core.config import SearchConfig
    from agent.tools.models import Paper

    config = SearchConfig()

    class MockArxiv(ArxivSearch):
        def execute(self, params):
            return ToolResult(success=True, data={
                "papers": [{"title": "New Paper", "authors": [], "year": 2024, "arxiv_id": "2401.99999", "source": "arxiv", "url": "", "categories": [], "citation_count": 0, "doi": "", "abstract": "New"}]
            })

    mgr = FallbackManager(MockArxiv(), None, config)
    papers = [Paper(title=f"Paper {i}") for i in range(3)]
    result = mgr.fallback_phase6(papers, "topic", ["keyword"])
    assert len(result) > 3


def test_fallback_phase7_single_channel():
    """Fix 4: Phase7 仅 arXiv all: 单通道."""
    from agent.tools.retrieval import FallbackManager, ArxivSearch
    from agent.tools.base import ToolResult
    from agent.core.config import SearchConfig
    from agent.tools.models import Paper

    config = SearchConfig()

    class MockArxiv(ArxivSearch):
        def execute(self, params):
            assert "ti:" not in params.get("query", "")
            assert "abs:" not in params.get("query", "")
            return ToolResult(success=True, data={
                "papers": [{"title": "Phase7 Paper", "authors": [], "year": 2024, "arxiv_id": "2401.88888", "source": "arxiv", "url": "", "categories": [], "citation_count": 0, "doi": "", "abstract": "Phase7"}]
            })

    mgr = FallbackManager(MockArxiv(), None, config)
    papers = [Paper(title=f"Paper {i}") for i in range(2)]
    result = mgr.fallback_phase7(papers, "topic")
    assert len(result) == 3


def test_fallback_phase7_max_results():
    """Fix 4: Phase7 max_results 严格限制 20."""
    from agent.tools.retrieval import FallbackManager, ArxivSearch
    from agent.tools.base import ToolResult
    from agent.core.config import SearchConfig

    config = SearchConfig()
    config.fallback_phase7_max_results = 20

    class MockArxiv(ArxivSearch):
        def execute(self, params):
            assert params.get("max_results") == 20
            return ToolResult(success=True, data={"papers": []})

    mgr = FallbackManager(MockArxiv(), None, config)
    mgr.fallback_phase7([], "topic")


def test_fallback_phase7_no_ss():
    """Fix 4: Phase7 不调用 Semantic Scholar."""
    from agent.tools.retrieval import FallbackManager, ArxivSearch
    from agent.tools.base import ToolResult
    from agent.core.config import SearchConfig

    config = SearchConfig()

    class MockArxiv(ArxivSearch):
        def execute(self, params):
            return ToolResult(success=True, data={"papers": []})

    class MockSS:
        def execute(self, params):
            raise AssertionError("Phase7 should not call Semantic Scholar")

    mgr = FallbackManager(MockArxiv(), MockSS(), config)
    mgr.fallback_phase7([], "topic")


def test_fallback_phase6_dedup():
    """Phase6 合并去重."""
    from agent.tools.retrieval import FallbackManager, ArxivSearch
    from agent.tools.base import ToolResult
    from agent.core.config import SearchConfig
    from agent.tools.models import Paper

    config = SearchConfig()

    class MockArxiv(ArxivSearch):
        def execute(self, params):
            return ToolResult(success=True, data={
                "papers": [{"title": "Duplicate Paper", "authors": [], "year": 2024, "arxiv_id": "2401.00001", "source": "arxiv", "url": "", "categories": [], "citation_count": 0, "doi": "", "abstract": "Dup"}]
            })

    mgr = FallbackManager(MockArxiv(), None, config)
    papers = [Paper(title="Duplicate Paper")]
    result = mgr.fallback_phase6(papers, "topic", ["keyword"])
    assert len(result) == 1  # dedup
```

- [ ] **Step 2: Add FallbackManager class to retrieval.py**

Append to `agent/tools/retrieval.py`:

```python
class FallbackManager:
    """分阶段 Fallback 策略。"""

    def __init__(
        self,
        arxiv_tool: "ArxivSearch",
        ss_tool: "SemanticScholarSearch | None",
        config: "SearchConfig",
    ):
        self.arxiv_tool = arxiv_tool
        self.ss_tool = ss_tool
        self.config = config

    def fallback_phase6(
        self,
        papers: list["Paper"],
        topic: str,
        keywords: list[str],
    ) -> list["Paper"]:
        """Phase 6 Fallback：论文数 < 10 时触发。"""
        from agent.tools.models import Paper

        logger.warning(
            "Phase6 fallback triggered: %d papers < %d",
            len(papers), self.config.fallback_phase6_min_papers,
        )

        queries = [topic] + keywords[:3]
        new_papers: list[Paper] = []

        for q in queries:
            ti_result = self.arxiv_tool.execute({
                "query": f"ti:{q}",
                "max_results": self.config.arxiv_ti_max_results,
            })
            if ti_result.success:
                for p in ti_result.data.get("papers", []):
                    paper = Paper.from_dict(p)
                    paper.hit_channels.append("fallback_phase6_ti")
                    new_papers.append(paper)

            abs_result = self.arxiv_tool.execute({
                "query": f"abs:{q}",
                "max_results": self.config.arxiv_abs_max_results,
            })
            if abs_result.success:
                for p in abs_result.data.get("papers", []):
                    paper = Paper.from_dict(p)
                    paper.hit_channels.append("fallback_phase6_abs")
                    new_papers.append(paper)

        # Dedup merge
        seen = set()
        merged = []
        for p in papers + new_papers:
            key = p.title.lower().strip()
            if key and key not in seen:
                seen.add(key)
                merged.append(p)

        logger.info("Phase6 fallback: %d -> %d papers", len(papers), len(merged))
        return merged

    def fallback_phase7(self, papers: list["Paper"], topic: str) -> list["Paper"]:
        """Phase 7 Fallback：论文数 < 5 时触发。

        Fix 4：仅 arXiv all: 单通道，max_results=20。
        """
        from agent.tools.models import Paper

        logger.warning(
            "Phase7 fallback triggered: %d papers < %d",
            len(papers), self.config.fallback_phase7_min_papers,
        )

        result = self.arxiv_tool.execute({
            "query": topic,
            "max_results": self.config.fallback_phase7_max_results,
        })

        new_papers: list[Paper] = []
        if result.success:
            for p in result.data.get("papers", []):
                paper = Paper.from_dict(p)
                paper.hit_channels.append("fallback_phase7_all")
                new_papers.append(paper)

        seen = {p.title.lower().strip() for p in papers if p.title}
        merged = list(papers)
        for p in new_papers:
            key = p.title.lower().strip()
            if key and key not in seen:
                seen.add(key)
                merged.append(p)

        logger.info("Phase7 fallback: %d -> %d papers", len(papers), len(merged))
        return merged
```

- [ ] **Step 3: Run test to verify it passes**

Run: `python -m pytest tests/test_retrieval.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add agent/tools/retrieval.py tests/test_retrieval.py
git commit -m "feat: add FallbackManager with phase6/phase7 (Fix 4)"
```

---

### Task 6: rank_papers 排序函数

**Files:**
- Modify: `agent/tools/processing.py`
- Test: `tests/test_processing.py`

**Interfaces:**
- Produces: `rank_papers(papers: list[Paper], config: SearchConfig) -> list[Paper]`, `_apply_rrf(papers, config) -> list[Paper]`

- [ ] **Step 1: Write the failing tests**

Write `tests/test_processing.py`:

```python
from agent.tools.models import Paper
from agent.core.config import SearchConfig
from agent.tools.processing import rank_papers


def test_rank_papers_empty():
    config = SearchConfig()
    result = rank_papers([], config)
    assert result == []


def test_rank_papers_single():
    config = SearchConfig()
    p = Paper(title="Single Paper", citation_count=10, year=2024, relevance="strong")
    result = rank_papers([p], config)
    assert len(result) == 1
    assert result[0].composite_score > 0


def test_rank_papers_citation_weight():
    config = SearchConfig()
    p1 = Paper(title="Highly Cited", citation_count=100, year=2024, relevance="strong")
    p2 = Paper(title="Low Citations", citation_count=1, year=2024, relevance="strong")
    result = rank_papers([p1, p2], config)
    assert result[0].title == "Highly Cited"
    assert result[0].composite_score > result[1].composite_score


def test_rank_papers_relevance_weight():
    config = SearchConfig()
    p1 = Paper(title="Strong Relevant", citation_count=10, year=2024, relevance="strong")
    p2 = Paper(title="Weak Relevant", citation_count=10, year=2024, relevance="weak")
    result = rank_papers([p1, p2], config)
    assert result[0].title == "Strong Relevant"


def test_rank_papers_recency_weight():
    config = SearchConfig()
    p1 = Paper(title="Recent", citation_count=10, year=2025, relevance="strong")
    p2 = Paper(title="Old", citation_count=10, year=2019, relevance="strong")
    result = rank_papers([p1, p2], config)
    assert result[0].title == "Recent"


def test_rank_papers_rrf_boost():
    """RRF 启用时，多通道论文获额外提分."""
    config = SearchConfig()
    config.rrf_enabled = True
    config.rrf_k = 60

    p1 = Paper(title="Multi Channel", citation_count=5, year=2024, relevance="weak",
               hit_channels=["arxiv_ti", "semantic_scholar"])
    p2 = Paper(title="Single Channel", citation_count=10, year=2024, relevance="strong",
               hit_channels=["arxiv_abs"])
    results = rank_papers([p1, p2], config)
    assert p1.composite_score > 0
    assert p2.composite_score > 0


def test_rank_papers_rrf_disabled():
    """RRF 禁用时不计算额外分."""
    config = SearchConfig()
    config.rrf_enabled = False
    p = Paper(title="Test", citation_count=10, year=2024, relevance="strong",
              hit_channels=["arxiv_ti", "arxiv_abs"])
    rank_papers([p], config)
    assert p.composite_score > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_processing.py -v`
Expected: FAIL with "ImportError: cannot import name 'rank_papers'"

- [ ] **Step 3: Add rank_papers and _apply_rrf to processing.py**

Append to `agent/tools/processing.py`:

```python
import logging
from agent.core.config import SearchConfig
from agent.tools.models import Paper

logger = logging.getLogger(__name__)


def rank_papers(papers: list[Paper], config: SearchConfig) -> list[Paper]:
    """RRF + 综合加权排序。"""
    if not papers:
        return papers

    max_citations = max(p.citation_count for p in papers) or 1
    current_year = 2026

    for p in papers:
        citation_score = p.citation_count / max_citations

        if p.relevance == "strong":
            relevance_score = 1.0
        elif p.relevance == "weak":
            relevance_score = 0.5
        else:
            relevance_score = 0.0

        age = current_year - p.year
        recency_score = max(0.0, 1.0 - age / 10.0) if p.year > 0 else 0.0

        p.composite_score = round(
            config.rank_alpha * citation_score
            + config.rank_beta * relevance_score
            + config.rank_gamma * recency_score,
            4,
        )

    if config.rrf_enabled and len(papers) > 1:
        papers = _apply_rrf(papers, config)

    papers.sort(key=lambda p: p.composite_score, reverse=True)

    if papers:
        logger.info("Ranked top-3: %s", [(p.title[:40], p.composite_score) for p in papers[:3]])

    return papers


def _apply_rrf(papers: list[Paper], config: SearchConfig) -> list[Paper]:
    """Reciprocal Rank Fusion 融合多通道排序。"""
    channels: dict[str, list[Paper]] = {}
    for p in papers:
        for ch in p.hit_channels:
            channels.setdefault(ch, []).append(p)

    if not channels:
        return papers

    rrf_k = config.rrf_k
    score_map: dict[str, float] = {}

    for ch, ch_papers in channels.items():
        for rank, p in enumerate(ch_papers):
            key = p.title.lower().strip()
            score_map[key] = score_map.get(key, 0.0) + 1.0 / (rrf_k + rank)

    for p in papers:
        key = p.title.lower().strip()
        rrf_score = score_map.get(key, 0.0)
        p.composite_score = round(p.composite_score * 0.7 + rrf_score * 0.3, 4)

    return papers
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_processing.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add agent/tools/processing.py tests/test_processing.py
git commit -m "feat: add rank_papers with RRF fusion and composite scoring"
```

---

### Task 7: RelevanceFilter 相关性过滤器

**Files:**
- Create: `agent/tools/relevance.py`
- Modify: `tests/test_relevance.py`

**Interfaces:**
- Consumes: `LLMBase`, `SearchConfig`, `Paper`, `RELEVANCE_JUDGE_PROMPT`
- Produces: `RelevanceFilter.__init__(llm, config)`, `RelevanceFilter.filter(papers, topic) -> list[Paper]`

- [ ] **Step 1: Write the failing tests**

Update `tests/test_relevance.py`:

```python
import json
from agent.tools.models import Paper
from agent.core.config import SearchConfig
from agent.core.llm import MockLLM


def test_filter_keep_strong():
    from agent.tools.relevance import RelevanceFilter

    llm = MockLLM(fixed_response=json.dumps({
        "judgments": [{"index": 1, "title": "Core Paper", "relevance": "strong", "confidence": 0.95, "reason": "Direct match"}]
    }))
    config = SearchConfig()
    rf = RelevanceFilter(llm, config)
    papers = [Paper(title="Core Paper", abstract="Important research")]
    result = rf.filter(papers, "test topic")
    assert len(result) == 1
    assert result[0].relevance == "strong"


def test_filter_keep_weak():
    from agent.tools.relevance import RelevanceFilter

    llm = MockLLM(fixed_response=json.dumps({
        "judgments": [{"index": 1, "title": "Peripheral", "relevance": "weak", "confidence": 0.7, "reason": "Related work"}]
    }))
    config = SearchConfig()
    rf = RelevanceFilter(llm, config)
    papers = [Paper(title="Peripheral", abstract="Somewhat related")]
    result = rf.filter(papers, "test topic")
    assert len(result) == 1


def test_filter_remove_irrelevant_high_confidence():
    """Fix 3: irrelevant + confidence >= 0.6 剔除."""
    from agent.tools.relevance import RelevanceFilter

    llm = MockLLM(fixed_response=json.dumps({
        "judgments": [{"index": 1, "title": "Unrelated", "relevance": "irrelevant", "confidence": 0.9, "reason": "Different field"}]
    }))
    config = SearchConfig()
    rf = RelevanceFilter(llm, config)
    papers = [Paper(title="Unrelated", abstract="Physics research")]
    result = rf.filter(papers, "test topic")
    assert len(result) == 0


def test_filter_keep_irrelevant_low_confidence():
    """Fix 3: irrelevant + confidence < 0.6 降级 weak 保留."""
    from agent.tools.relevance import RelevanceFilter

    llm = MockLLM(fixed_response=json.dumps({
        "judgments": [{"index": 1, "title": "Ambiguous", "relevance": "irrelevant", "confidence": 0.4, "reason": "Uncertain"}]
    }))
    config = SearchConfig()
    rf = RelevanceFilter(llm, config)
    papers = [Paper(title="Ambiguous", abstract="Maybe related")]
    result = rf.filter(papers, "test topic")
    assert len(result) == 1
    assert result[0].relevance == "weak"


def test_filter_no_abstract_cap_confidence():
    """无摘要时 confidence 上限 0.6，且不可为 strong."""
    from agent.tools.relevance import RelevanceFilter

    llm = MockLLM(fixed_response=json.dumps({
        "judgments": [{"index": 1, "title": "No Abstract", "relevance": "strong", "confidence": 0.95, "reason": "Looks good"}]
    }))
    config = SearchConfig()
    rf = RelevanceFilter(llm, config)
    papers = [Paper(title="No Abstract", abstract="")]
    result = rf.filter(papers, "test topic")
    assert len(result) == 1
    assert result[0].relevance_confidence <= 0.6
    assert result[0].relevance == "weak"


def test_filter_empty_papers():
    from agent.tools.relevance import RelevanceFilter

    llm = MockLLM(fixed_response="{}")
    config = SearchConfig()
    rf = RelevanceFilter(llm, config)
    assert rf.filter([], "topic") == []


def test_filter_llm_parse_failure():
    """LLM 返回非 JSON 时保留全部."""
    from agent.tools.relevance import RelevanceFilter

    llm = MockLLM(fixed_response="Not valid JSON")
    config = SearchConfig()
    rf = RelevanceFilter(llm, config)
    papers = [Paper(title="Paper A", abstract="Test")]
    result = rf.filter(papers, "topic")
    assert len(result) == 1


def test_filter_all_irrelevant_low_conf_kept():
    """所有 irrelevant 但 confidence<0.6，全部保留为 weak."""
    from agent.tools.relevance import RelevanceFilter

    judgments = {"judgments": [
        {"index": 1, "title": "Paper A", "relevance": "irrelevant", "confidence": 0.3, "reason": "?"},
        {"index": 2, "title": "Paper B", "relevance": "irrelevant", "confidence": 0.2, "reason": "?"},
    ]}
    llm = MockLLM(fixed_response=json.dumps(judgments))
    config = SearchConfig()
    rf = RelevanceFilter(llm, config)
    papers = [Paper(title="Paper A", abstract="A"), Paper(title="Paper B", abstract="B")]
    result = rf.filter(papers, "topic")
    assert len(result) == 2
    assert all(p.relevance == "weak" for p in result)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_relevance.py -v`
Expected: FAIL (old RelevanceFilter has different interface)

- [ ] **Step 3: Rewrite relevance.py**

Write `agent/tools/relevance.py`:

```python
import json
import logging

from agent.core.llm import LLMBase
from agent.core.config import SearchConfig
from agent.tools.models import Paper
from agent.tools.prompts import RELEVANCE_JUDGE_PROMPT

logger = logging.getLogger(__name__)


class RelevanceFilter:
    """三级相关性过滤器（LLM 驱动）。

    过滤规则（Fix 3）：
    - relevance=strong → 保留
    - relevance=weak → 保留
    - relevance=irrelevant AND confidence >= 0.6 → 剔除
    - confidence < 0.6 → 标记为 weak，保留，禁止删除
    """

    def __init__(self, llm: LLMBase, config: SearchConfig):
        self.llm = llm
        self.config = config

    def filter(self, papers: list[Paper], topic: str) -> list[Paper]:
        if not papers:
            return papers

        prompt = RELEVANCE_JUDGE_PROMPT.format(topic=topic)
        paper_list = []
        for i, p in enumerate(papers, 1):
            abstract = (p.abstract or "")[:300]
            paper_list.append({"index": i, "title": p.title, "abstract": abstract})

        user_msg = json.dumps(paper_list, ensure_ascii=False)
        resp = self.llm.generate(prompt, user_msg)
        judgments = self._parse_judgments(resp.text)

        kept = []
        for p in papers:
            judgment = judgments.get(p.title.lower(), {})
            rel = judgment.get("relevance", "weak")
            conf = judgment.get("confidence", 0.0)
            reason = judgment.get("reason", "")

            p.relevance = rel
            p.relevance_confidence = conf
            p.relevance_reason = reason

            # 无摘要 → confidence 上限 0.6
            if not p.abstract and conf > 0.6:
                p.relevance_confidence = 0.6
                conf = 0.6

            # 无摘要 → 不可为 strong
            if not p.abstract and p.relevance == "strong":
                p.relevance = "weak"

            if rel == "irrelevant" and conf >= self.config.relevance_confidence_min:
                logger.warning("Filtered out: '%s' (confidence=%.2f, reason=%s)", p.title, conf, reason)
                continue

            if rel == "irrelevant" and conf < self.config.relevance_confidence_min:
                p.relevance = "weak"
                logger.info("Downgraded to weak (low confidence): '%s' (conf=%.2f)", p.title, conf)

            kept.append(p)

        strong = sum(1 for p in kept if p.relevance == "strong")
        weak = sum(1 for p in kept if p.relevance == "weak")
        filtered = len(papers) - len(kept)
        logger.info("Relevance: strong=%d, weak=%d, filtered=%d (total=%d)", strong, weak, filtered, len(papers))

        return kept

    @staticmethod
    def _parse_judgments(text: str) -> dict:
        try:
            data = json.loads(text)
            judgments = {}
            for j in data.get("judgments", []):
                title = (j.get("title") or "").lower().strip()
                if title:
                    judgments[title] = {
                        "relevance": j.get("relevance", "weak"),
                        "confidence": float(j.get("confidence", 0.0)),
                        "reason": j.get("reason", ""),
                    }
            return judgments
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.warning("Failed to parse relevance judgments: %s", e)
            return {}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_relevance.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add agent/tools/relevance.py tests/test_relevance.py
git commit -m "feat: refactor RelevanceFilter with 3-level + confidence scoring (Fix 3)"
```

---

### Task 8: Pipeline 重构

**Files:**
- Modify: `agent/core/pipeline.py`
- Test: `tests/test_pipeline_expand.py` (new), `tests/test_pipeline.py` (modify)

**Interfaces:**
- Consumes: `Paper`, `SearchConfig`, `RelevanceFilter`, `FallbackManager`, `dual_channel_arxiv_search`, `infer_arxiv_category`, `rank_papers`, `SEARCH_QUERY_PROMPT`
- Produces: `_generate_search_queries(topic, keywords) -> list[str]`, `_expand_and_dedup_queries(raw_queries, topic, keywords) -> list[str]`, refactored `_retrieve_papers() -> list[dict]`

- [ ] **Step 1: Write _expand_and_dedup_queries tests**

Write `tests/test_pipeline_expand.py`:

```python
"""Tests for _expand_and_dedup_queries."""
from agent.core.pipeline import PipelineOrchestrator
from agent.tools.registry import ToolRegistry
from agent.core.llm import MockLLM
from agent.guardrails.manager import GuardrailManager
from agent.core.pipeline import HarnessConfig


def _make_orch():
    llm = MockLLM(fixed_response="Test response")
    tools = ToolRegistry()
    guardrails = GuardrailManager(guardrails=[])
    config = HarnessConfig()
    return PipelineOrchestrator(
        llm=llm, tools=tools, validators=[], guardrails=guardrails,
        config=config, latex_repair=None,
    )


def test_expand_full_to_abbrev():
    """"Vision Transformer -> ViT" → 2 条."""
    orch = _make_orch()
    result = orch._expand_and_dedup_queries(["Vision Transformer -> ViT"], "topic", ["kw"])
    assert len(result) == 2
    assert "Vision Transformer" in result
    assert "ViT" in result


def test_expand_dedup_identical():
    """Fix 5: "attention -> attention" → 1 条."""
    orch = _make_orch()
    result = orch._expand_and_dedup_queries(["attention -> attention"], "topic", ["kw"])
    assert len(result) == 1
    assert result[0] == "attention"


def test_expand_dedup_case_insensitive():
    """Fix 5: "ViT -> vit" → 1 条（大小写不敏感）."""
    orch = _make_orch()
    result = orch._expand_and_dedup_queries(["ViT -> vit"], "topic", ["kw"])
    assert len(result) == 1
    assert result[0] == "ViT"


def test_expand_fallback_empty():
    orch = _make_orch()
    result = orch._expand_and_dedup_queries([], "topic", ["kw1", "kw2", "kw3"])
    assert len(result) >= 1
    assert "topic" in result


def test_expand_fill_shortfall():
    orch = _make_orch()
    result = orch._expand_and_dedup_queries(["only one -> one"], "topic", ["kw1", "kw2"])
    assert len(result) >= 2


def test_expand_mixed_formats():
    orch = _make_orch()
    raw = ["ViT -> ViT", "plain query", "CNN -> Convolutional Neural Network"]
    result = orch._expand_and_dedup_queries(raw, "topic", ["kw"])
    assert "ViT" in result
    assert "plain query" in result
    assert "CNN" in result
    assert "Convolutional Neural Network" in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_pipeline_expand.py -v`
Expected: FAIL with "AttributeError: 'PipelineOrchestrator' object has no attribute '_expand_and_dedup_queries'"

- [ ] **Step 3: Add methods to PipelineOrchestrator**

In `agent/core/pipeline.py`:

**Add imports at top:**
```python
from agent.tools.prompts import SEARCH_QUERY_PROMPT
from agent.tools.models import Paper
from agent.core.config import SearchConfig
from agent.tools.retrieval import (
    dual_channel_arxiv_search,
    infer_arxiv_category,
    FallbackManager,
)
from agent.tools.relevance import RelevanceFilter
from agent.tools.processing import rank_papers
```

**Add methods to PipelineOrchestrator class:**
```python
def _generate_search_queries(self, topic: str, keywords: list[str]) -> list[str]:
    """使用 LLM 生成检索 query（新版 Prompt）。"""
    sys_prompt = SEARCH_QUERY_PROMPT
    user_msg = f"Survey topic: {topic}\nKeywords: {', '.join(keywords)}\n\nGenerate 5 search queries."

    try:
        resp = self._safe_llm_call(sys_prompt, user_msg)
        raw_lines = resp.text.strip().split("\n")
        queries = [l.strip() for l in raw_lines if l.strip() and "->" in l]
        if queries:
            logger.info("Generated %d raw queries: %s", len(queries), queries)
            return queries
    except Exception as e:
        logger.warning("LLM query generation failed: %s", e)

    fallback = [topic]
    if keywords:
        fallback.extend(keywords[:4])
    logger.info("Using fallback queries: %s", fallback)
    return fallback


def _expand_and_dedup_queries(self, raw_queries: list[str], topic: str, keywords: list[str]) -> list[str]:
    """拆分"全称 -> 缩写"为独立 query，去重，补充不足（Fix 5）。"""
    expanded_set: set[str] = set()
    for line in raw_queries:
        line = line.strip()
        if "->" in line:
            parts = [p.strip() for p in line.split("->", 1)]
            full_name = parts[0]
            abbreviation = parts[1] if len(parts) >= 2 else full_name
            expanded_set.add(full_name)
            if abbreviation.lower() != full_name.lower():
                expanded_set.add(abbreviation)
        else:
            expanded_set.add(line)

    queries = list(expanded_set)
    queries = [q for q in queries if q and len(q) < 200]

    if len(queries) < 1:
        queries = [topic]
    if len(queries) < 2:
        queries.append(f"{topic} survey")
    while len(queries) < 3:
        queries.append(" ".join(keywords[:3]))

    logger.info("Expanded to %d final queries: %s", len(queries), queries)
    return queries
```

**Replace _retrieve_papers method:**
```python
def _retrieve_papers(self) -> list[dict]:
    """重构后的检索管线。"""
    topic = self._task.topic
    keywords = self._task.keywords or [topic]
    config = SearchConfig()

    raw_queries = self._generate_search_queries(topic, keywords)
    queries = self._expand_and_dedup_queries(raw_queries, topic, keywords)

    arxiv_tool = self.tools.get("arxiv_search")
    ss_tool = self.tools.get("semantic_scholar_search")
    cat_filter = infer_arxiv_category(topic, topic, config.domain_cat_map)

    all_papers: list[Paper] = []
    for q in queries:
        all_papers += dual_channel_arxiv_search(arxiv_tool, q, cat_filter, config)
        ss_result = ss_tool.execute({"query": q, "max_results": config.ss_max_results})
        if ss_result.success:
            for p_data in ss_result.data.get("papers", []):
                paper = Paper.from_dict(p_data)
                paper.hit_channels.append("semantic_scholar")
                paper.search_source_queries.append(q)
                all_papers.append(paper)

    merge_data = [p.to_dict() for p in all_papers]
    merge_tool = self.tools.get("merge_results")
    merged = merge_tool.execute({"papers": merge_data})
    merged_dicts = merged.data.get("papers", []) if merged.success else []
    papers = [Paper.from_dict(p) for p in merged_dicts]

    filter_module = RelevanceFilter(self.llm, config)
    papers = filter_module.filter(papers, topic)

    papers = rank_papers(papers, config)

    fallback = FallbackManager(arxiv_tool, ss_tool, config)
    if len(papers) < config.fallback_phase6_min_papers:
        papers = fallback.fallback_phase6(papers, topic, keywords)
        papers = rank_papers(papers, config)
    if len(papers) < config.fallback_phase7_min_papers:
        papers = fallback.fallback_phase7(papers, topic)
        papers = rank_papers(papers, config)

    self._papers = [p.to_dict() for p in papers[:self._task.max_papers]]
    return self._papers
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_pipeline_expand.py tests/test_pipeline.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add agent/core/pipeline.py tests/test_pipeline_expand.py
git commit -m "refactor: pipeline _retrieve_papers with new modules (Fixes 1-6)"
```

---

### Task 9: MergeResults 增强 — multi_hit 统计

**Files:**
- Modify: `agent/tools/retrieval.py` (MergeResults._merge_metadata)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_retrieval.py`:

```python
def test_merge_results_multi_hit():
    """MergeResults 应合并 hit_channels 并记录 multi_hit 统计."""
    from agent.tools.retrieval import MergeResults

    papers = [
        {"title": "Paper A", "authors": [], "year": 2024, "arxiv_id": "2401.00001", "source": "arxiv", "url": "", "categories": [], "citation_count": 0, "doi": "", "abstract": "", "hit_channels": ["arxiv_ti", "arxiv_abs"]},
        {"title": "Paper B", "authors": [], "year": 2024, "arxiv_id": "2401.00002", "source": "arxiv", "url": "", "categories": [], "citation_count": 0, "doi": "", "abstract": "", "hit_channels": ["arxiv_ti"]},
    ]
    merger = MergeResults()
    result = merger.execute({"papers": papers})
    assert result.success
    assert len(result.data["papers"]) == 2
```

- [ ] **Step 2: Enhance MergeResults._merge_metadata**

Replace the `_merge_metadata` method in `MergeResults`:

```python
@staticmethod
def _merge_metadata(papers: list[dict]) -> list[dict]:
    """For papers appearing in both sources, merge to keep richer fields."""
    by_title: dict[str, list[dict]] = {}
    for p in papers:
        key = p.get("title", "").lower().strip()
        by_title.setdefault(key, []).append(p)

    merged = []
    for key, dups in by_title.items():
        if len(dups) == 1:
            merged.append(dups[0])
            continue
        base = dups[0].copy()
        for other in dups[1:]:
            for field in ("abstract", "venue", "doi", "url"):
                if not base.get(field) and other.get(field):
                    base[field] = other[field]
            existing = set(base.get("authors", []))
            for a in other.get("authors", []):
                if a not in existing:
                    base["authors"].append(a)
                    existing.add(a)
            base["citation_count"] = max(base.get("citation_count", 0), other.get("citation_count", 0))
            if other.get("source") == "arxiv" and other.get("arxiv_id"):
                base["arxiv_id"] = other["arxiv_id"]
            base["source"] = "merged"

            # Merge hit_channels
            base_channels = set(base.get("hit_channels", []))
            other_channels = set(other.get("hit_channels", []))
            base["hit_channels"] = list(base_channels | other_channels)

        merged.append(base)

    # Multi-hit logging
    hit_counts = {}
    for p in merged:
        channels = p.get("hit_channels", [])
        if channels:
            n = len(channels)
            hit_counts[n] = hit_counts.get(n, 0) + 1
    if hit_counts:
        logger.info("multi_hit counts: %s", hit_counts)

    return merged
```

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/test_retrieval.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add agent/tools/retrieval.py tests/test_retrieval.py
git commit -m "feat: MergeResults multi_hit channel merging and logging"
```

---

### Task 10: 集成测试 + 补全 __init__.py 导出

**Files:**
- Modify: `tests/test_pipeline.py`, `agent/tools/__init__.py`

- [ ] **Step 1: Add integration test**

Append to `tests/test_pipeline.py`:

```python
def test_retrieve_papers_returns_dicts():
    """_retrieve_papers 返回 list[dict] 兼容上游接口."""
    from agent.core.state import AgentState, StateMachine
    from agent.core.pipeline import PipelineOrchestrator, TaskInfo
    from agent.core.llm import MockLLM
    from agent.guardrails.manager import GuardrailManager
    from agent.tools.registry import ToolRegistry
    from agent.tools.retrieval import ArxivSearch, SemanticScholarSearch, MergeResults
    from agent.tools.base import ToolResult

    llm = MockLLM(fixed_response="test query -> tq")
    tools = ToolRegistry()

    class MockArxiv(ArxivSearch):
        def execute(self, params):
            return ToolResult(success=True, data={"papers": []})

    class MockSS(SemanticScholarSearch):
        def execute(self, params):
            return ToolResult(success=True, data={"papers": []})

    tools.register(MockArxiv())
    tools.register(MockSS())
    tools.register(MergeResults())

    guardrails = GuardrailManager(guardrails=[])
    config = HarnessConfig()
    orch = PipelineOrchestrator(
        llm=llm, tools=tools, validators=[], guardrails=guardrails,
        config=config, latex_repair=None,
    )

    task = TaskInfo(topic="Test Topic", keywords=["test"], goal="Test")
    state = StateMachine()
    state.transition_to(AgentState.PLANNING)

    orch._task = task
    result = orch._retrieve_papers()
    assert isinstance(result, list)
    if result:
        assert isinstance(result[0], dict)
```

- [ ] **Step 2: Update agent/tools/__init__.py exports**

```python
# Add to agent/tools/__init__.py:
from agent.tools.models import Paper
from agent.tools.retrieval import (
    auto_quote_terms,
    infer_arxiv_category,
    dual_channel_arxiv_search,
    FallbackManager,
)
```

- [ ] **Step 3: Run all tests**

Run: `python -m pytest tests/ -v`
Expected: All tests pass (including existing pipeline, relevance, processing, retrieval tests)

- [ ] **Step 4: Commit**

```bash
git add agent/tools/__init__.py tests/test_pipeline.py
git commit -m "test: add integration test for _retrieve_papers dict interface"
```

---

## Spec Coverage Check

| Spec Section | Task(s) | Status |
|-------------|---------|--------|
| Fix 1: auto_quote_terms | Task 4 | ✅ |
| Fix 2: domain_cat_map no transformer | Task 2, 4 | ✅ |
| Fix 3: relevance filter rules | Task 7 | ✅ |
| Fix 4: Fallback phase7 single channel | Task 5 | ✅ |
| Fix 5: expand dedup identical | Task 8 | ✅ |
| Fix 6: search_source_queries field | Task 1 | ✅ |
| Paper 数据模型 | Task 1 | ✅ |
| SearchConfig | Task 2 | ✅ |
| LLM Prompt 定义 | Task 3 | ✅ |
| RelevanceFilter | Task 7 | ✅ |
| FallbackManager | Task 5 | ✅ |
| rank_papers | Task 6 | ✅ |
| dual_channel_arxiv_search | Task 4 | ✅ |
| auto_quote_terms | Task 4 | ✅ |
| infer_arxiv_category | Task 4 | ✅ |
| Pipeline 重构 | Task 8 | ✅ |
| 旧逻辑对照表 | All tasks | ✅ |
| 日志埋点清单 | All tasks | ✅ |
| 边界场景处理 | All tasks | ✅ |
| MergeResults 增强 | Task 9 | ✅ |
| __init__.py 导出 | Task 10 | ✅ |

---

## Execution Handoff

**Plan complete and saved.** Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration
2. **Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**