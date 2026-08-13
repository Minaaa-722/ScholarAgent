# Unified Paper Data Model + Module Interface Definition

## 1. Problem & Scope

当前论文检索管线存在以下问题：
- 各模块间用 `list[dict]` 传递，缺乏类型约束，字段名不统一
- 相关性过滤逻辑粗糙（1-5 分制，无置信度判断）
- 排序只有单一引用数排序，缺乏多因子加权
- 检索 Query 生成质量差，缺乏全称/缩写拆分机制
- 无 Fallback 机制，低召回场景下直接返回空结果

本 Spec 定义统一的 Paper 数据模型、各模块接口、以及 Pipeline 编排方式。

---

## 2. Fixes Applied (6 Corrections from Design Review)

### Fix 1: `auto_quote_terms` — 移除特殊字符排除

**原逻辑**：含 `-` `/` `(` `)` 的术语不加引号。
**修正**：移除该限制，所有多词术语统一加英文双引号。

```python
# 修正后：所有多词术语一律加引号
def auto_quote_terms(query: str) -> str:
    if query.startswith('"') and query.endswith('"'):
        return query
    words = query.split()
    if len(words) <= 1:
        return query
    return f'"{query}"'
```

**效果**：`vision-transformer` → `"vision-transformer"`，确保精确短语匹配。

### Fix 2: `domain_cat_map` — 移除 `transformer` 映射

**原因**：`transformer` 跨 CV/NLP 领域，无法仅靠关键词判定归属。
**修正**：移除 `transformer` 条目，交回兜底 `cs.AI`。

```python
domain_cat_map = {
    "image": "cs.CV", "vision": "cs.CV", "visual": "cs.CV",
    "object detection": "cs.CV", "segmentation": "cs.CV",
    "face": "cs.CV", "video": "cs.CV", "pose": "cs.CV",
    "language": "cs.CL", "text": "cs.CL", "translation": "cs.CL",
    "sentence": "cs.CL", "word": "cs.CL",
    "token": "cs.CL", "bert": "cs.CL", "gpt": "cs.CL",
    "llm": "cs.CL",
    # 注意：transformer 跨 CV/NLP，不移除固定映射，交由兜底 cs.AI
}
```

### Fix 3: 相关性过滤规则 — 仅 `irrelevant AND confidence ≥ 0.6` 才剔除

**修正后规则**：
- `relevance=strong` → 保留
- `relevance=weak` → 保留
- `relevance=irrelevant AND confidence ≥ 0.6` → 剔除
- `relevance=irrelevant AND confidence < 0.6` → 标记为 `weak`，**保留**，禁止删除

### Fix 4: Fallback Phase7 — arXiv `all:` 检索单通道，`max_results=20`

**修正后**：
- 仅执行单通道 `all:` 检索（不并行 ti/abs）
- `max_results` 严格限制为 20
- 不调用 Semantic Scholar（避免噪声）

### Fix 5: `_expand_and_dedup_queries` — 全称与缩写一致时去重

**修正后逻辑**：
```python
def _expand_and_dedup_queries(self, raw_queries, topic, keywords):
    expanded = set()
    for line in raw_queries:
        if "->" in line:
            parts = [p.strip() for p in line.split("->")]
            full_name = parts[0]
            abbreviation = parts[1] if len(parts) >= 2 else full_name
            # 去重：两条一致时只保留一条
            expanded.add(full_name)
            if abbreviation.lower() != full_name.lower():
                expanded.add(abbreviation)
        else:
            expanded.add(line.strip())
    # 补充不足...
    return list(expanded)
```

### Fix 6: Paper 模型增加 `search_source_queries` 字段

用于记录触发召回的原始检索词，便于后续效果分析。

```python
@dataclass
class Paper:
    ...
    search_source_queries: list[str] = field(default_factory=list)
```

---

## 3. Paper 数据模型

### 文件位置：`agent/tools/models.py`

```python
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Paper:
    # 标准字段
    title: str = ""
    authors: list[str] = field(default_factory=list)
    abstract: str = ""
    year: int = 0

    # 来源字段
    arxiv_id: str = ""
    source: str = ""          # "arxiv" | "semantic_scholar" | "merged"
    url: str = ""
    venue: str = ""

    # 元数据字段
    citation_count: int = 0
    doi: str = ""
    paper_id: str = ""
    categories: list[str] = field(default_factory=list)

    # 新增：命中通道
    hit_channels: list[str] = field(default_factory=list)

    # 新增：相关性判定
    relevance: str = "weak"          # "strong" | "weak" | "irrelevant"
    relevance_confidence: float = 0.0  # 0~1
    relevance_reason: str = ""

    # 新增：综合排序分
    composite_score: float = 0.0

    # 新增：触发召回的原始检索词（Fix 6）
    search_source_queries: list[str] = field(default_factory=list)

    # 新增：扩展字段（任意 key-value，用于工具间传递临时数据）
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "Paper":
        return Paper(
            **{k: v for k, v in data.items() if k in Paper.__dataclass_fields__}
        )
```

### 接口约定

- **内部模块间**：统一使用 `Paper` 对象传递
- **_retrieve_papers() 返回给上游**：保留 `list[dict]` 接口，通过 `.to_dict()` 转换
- **外部输入**：通过 `Paper.from_dict()` 解析

---

## 4. 模块接口定义

### 4.1 SearchConfig — `agent/core/config.py`

```python
from dataclasses import dataclass, field


@dataclass
class SearchConfig:
    # 检索通道上限
    arxiv_ti_max_results: int = 20
    arxiv_abs_max_results: int = 20
    ss_max_results: int = 20

    # RRF 融合
    rrf_enabled: bool = True
    rrf_k: int = 60

    # 综合排序权重
    rank_alpha: float = 0.5   # 引用数
    rank_beta: float = 0.3    # 相关性
    rank_gamma: float = 0.2   # 时效性

    # 分类映射（Fix 2：已移除 transformer）
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

    # 相关性过滤参数（Fix 3）
    relevance_confidence_min: float = 0.6
    abstract_missing_max_confidence: float = 0.6

    # Fallback 参数（Fix 4）
    fallback_phase6_min_papers: int = 10
    fallback_phase7_min_papers: int = 5
    fallback_phase7_max_results: int = 20
```

### 4.2 RelevanceFilter — `agent/tools/relevance.py`

```python
import json
import logging
from typing import Optional

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

        # 1. 构造 LLM 判定请求
        prompt = RELEVANCE_JUDGE_PROMPT.format(topic=topic)
        paper_list = []
        for i, p in enumerate(papers, 1):
            abstract = (p.abstract or "")[:300]
            paper_list.append({
                "index": i,
                "title": p.title,
                "abstract": abstract,
            })

        user_msg = json.dumps(paper_list, ensure_ascii=False)
        resp = self.llm.generate(prompt, user_msg)

        # 2. 解析 LLM 返回的 JSON
        judgments = self._parse_judgments(resp.text)

        # 3. 应用过滤规则
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

            if rel == "irrelevant" and conf >= self.config.relevance_confidence_min:
                logger.warning(
                    "Filtered out: '%s' (confidence=%.2f, reason=%s)",
                    p.title, conf, reason,
                )
                continue  # 剔除

            # confidence < 0.6 的 irrelevant → 降级为 weak，保留
            if rel == "irrelevant" and conf < self.config.relevance_confidence_min:
                p.relevance = "weak"
                logger.info(
                    "Downgraded to weak (low confidence): '%s' (conf=%.2f)",
                    p.title, conf,
                )

            kept.append(p)

        # 4. 日志
        strong = sum(1 for p in kept if p.relevance == "strong")
        weak = sum(1 for p in kept if p.relevance == "weak")
        filtered = len(papers) - len(kept)
        logger.info(
            "Relevance: strong=%d, weak=%d, filtered=%d (total=%d)",
            strong, weak, filtered, len(papers),
        )

        return kept

    def _parse_judgments(self, text: str) -> dict:
        """Parse LLM JSON response into {title_lower: judgment} dict."""
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

### 4.3 FallbackManager — `agent/tools/retrieval.py`

```python
import logging
from typing import Optional

from agent.core.config import SearchConfig
from agent.tools.models import Paper
from agent.tools.retrieval import ArxivSearch

logger = logging.getLogger(__name__)


class FallbackManager:
    """分阶段 Fallback 策略。"""

    def __init__(
        self,
        arxiv_tool: ArxivSearch,
        ss_tool: Optional["SemanticScholarSearch"],
        config: SearchConfig,
    ):
        self.arxiv_tool = arxiv_tool
        self.ss_tool = ss_tool
        self.config = config

    def fallback_phase6(
        self,
        papers: list[Paper],
        topic: str,
        keywords: list[str],
    ) -> list[Paper]:
        """Phase 6 Fallback：论文数 < 10 时触发。

        放宽条件检索 arXiv ti + abs 双通道，SS 补充。
        """
        logger.warning(
            "Phase6 fallback triggered: %d papers < %d",
            len(papers), self.config.fallback_phase6_min_papers,
        )

        # 使用 topic + keywords 直接检索
        queries = [topic] + keywords[:3]
        new_papers: list[Paper] = []

        for q in queries:
            # arXiv ti 通道
            ti_result = self.arxiv_tool.execute({
                "query": f"ti:{q}",
                "max_results": self.config.arxiv_ti_max_results,
            })
            if ti_result.success:
                for p in ti_result.data.get("papers", []):
                    paper = Paper.from_dict(p)
                    paper.hit_channels.append("fallback_phase6_ti")
                    new_papers.append(paper)

            # arXiv abs 通道
            abs_result = self.arxiv_tool.execute({
                "query": f"abs:{q}",
                "max_results": self.config.arxiv_abs_max_results,
            })
            if abs_result.success:
                for p in abs_result.data.get("papers", []):
                    paper = Paper.from_dict(p)
                    paper.hit_channels.append("fallback_phase6_abs")
                    new_papers.append(paper)

        # 合并去重
        seen = set()
        for p in papers + new_papers:
            key = p.title.lower().strip()
            if key and key not in seen:
                seen.add(key)

        merged = []
        seen.clear()
        for p in papers + new_papers:
            key = p.title.lower().strip()
            if key and key not in seen:
                seen.add(key)
                merged.append(p)

        logger.info("Phase6 fallback: %d -> %d papers", len(papers), len(merged))
        return merged

    def fallback_phase7(self, papers: list[Paper], topic: str) -> list[Paper]:
        """Phase 7 Fallback：论文数 < 5 时触发。

        Fix 4：仅 arXiv all: 单通道，max_results=20，不并行 ti/abs。
        """
        logger.warning(
            "Phase7 fallback triggered: %d papers < %d",
            len(papers), self.config.fallback_phase7_min_papers,
        )

        # 仅 arXiv all: 单通道，严格限制 max_results
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

        # 合并去重
        seen = set()
        for p in papers:
            key = p.title.lower().strip()
            if key:
                seen.add(key)

        merged = list(papers)
        for p in new_papers:
            key = p.title.lower().strip()
            if key and key not in seen:
                seen.add(key)
                merged.append(p)

        logger.info("Phase7 fallback: %d -> %d papers", len(papers), len(merged))
        return merged
```

### 4.4 `rank_papers` — `agent/tools/processing.py`

```python
import logging
import math
from typing import Optional

from agent.core.config import SearchConfig
from agent.tools.models import Paper

logger = logging.getLogger(__name__)


def rank_papers(papers: list[Paper], config: SearchConfig) -> list[Paper]:
    """RRF + 综合加权排序。

    排序因子：
    - 引用数（归一化）
    - 相关性权重（strong/weak）
    - 时效性（年份越近越高）
    """
    if not papers:
        return papers

    # 1. 计算各因子分数
    max_citations = max(p.citation_count for p in papers) or 1
    current_year = 2026

    for p in papers:
        # 引用分
        citation_score = p.citation_count / max_citations

        # 相关性分
        if p.relevance == "strong":
            relevance_score = 1.0
        elif p.relevance == "weak":
            relevance_score = 0.5
        else:
            relevance_score = 0.0

        # 时效分（越近越高）
        age = current_year - p.year
        recency_score = max(0.0, 1.0 - age / 10.0) if p.year > 0 else 0.0

        # 综合分
        p.composite_score = round(
            config.rank_alpha * citation_score
            + config.rank_beta * relevance_score
            + config.rank_gamma * recency_score,
            4,
        )

    # 2. RRF 融合（如果启用）
    if config.rrf_enabled and len(papers) > 1:
        papers = _apply_rrf(papers, config)

    # 3. 排序
    papers.sort(key=lambda p: p.composite_score, reverse=True)

    # 日志
    if papers:
        logger.info(
            "Ranked top-3: %s",
            [(p.title[:40], p.composite_score) for p in papers[:3]],
        )

    return papers


def _apply_rrf(
    papers: list[Paper],
    config: SearchConfig,
) -> list[Paper]:
    """Reciprocal Rank Fusion 融合多通道排序。"""
    # 按 hit_channels 分组
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

    # 融合原分数
    for p in papers:
        key = p.title.lower().strip()
        rrf_score = score_map.get(key, 0.0)
        p.composite_score = round(p.composite_score * 0.7 + rrf_score * 0.3, 4)

    return papers
```

### 4.5 `dual_channel_arxiv_search` — `agent/tools/retrieval.py`

```python
import logging
from typing import Optional

from agent.core.config import SearchConfig
from agent.tools.models import Paper
from agent.tools.retrieval import ArxivSearch

logger = logging.getLogger(__name__)


def dual_channel_arxiv_search(
    arxiv_tool: ArxivSearch,
    query: str,
    cat_filter: str = "",
    config: Optional[SearchConfig] = None,
) -> list[Paper]:
    """arXiv 双通道检索：ti 精准 + abs 召回。

    每个通道分别检索，结果合并去重。
    """
    quoted = auto_quote_terms(query)
    papers: list[Paper] = []

    # Channel 1: ti — 精准匹配标题
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

    # Channel 2: abs — 召回摘要
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

    # 去重（保留第一个出现的，即 ti 优先）
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

### 4.6 `auto_quote_terms` — 辅助函数（Fix 1）

```python
def auto_quote_terms(query: str) -> str:
    """通用引号封装（Fix 1：移除特殊字符排除）。

    所有多词术语统一加英文双引号，确保精确短语匹配。
    """
    if query.startswith('"') and query.endswith('"'):
        return query
    words = query.split()
    if len(words) <= 1:
        return query
    return f'"{query}"'
```

### 4.7 `infer_arxiv_category` — 辅助函数（Fix 2）

```python
def infer_arxiv_category(
    query: str,
    topic: str,
    domain_cat_map: dict,
    fallback: str = "cs.AI",
) -> str:
    """根据 query+topic 关键词推断 arXiv 分类。

    Fix 2：transformer 已移除映射，交由兜底 cs.AI。
    """
    combined = f"{query} {topic}".lower()
    for keyword, cat in domain_cat_map.items():
        if keyword in combined:
            return cat
    return fallback
```

---

## 5. LLM Prompt 定义 — `agent/tools/prompts.py`

### 5.1 阶段1：检索 Query 生成

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
```

### 5.2 阶段4：相关性判定

```python
RELEVANCE_JUDGE_PROMPT = """\
You are a strict relevance judge for academic literature search.

TASK: Judge whether each paper is relevant to the research topic: "{topic}"

RELEVANCE DEFINITION:
- STRONG relevant: The paper's primary contribution directly addresses the topic.
- WEAK relevant: The paper addresses the topic but not as primary contribution.
  (used as a component, compared against, discussed in related work)
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

---

## 6. Pipeline 编排 — `agent/core/pipeline.py`

### 6.1 `_retrieve_papers()` 顶层编排

```python
def _retrieve_papers(self) -> list[dict]:
    """重构后的检索管线。"""
    topic = self._task.topic
    keywords = self._task.keywords or [topic]
    config = self._search_config  # 注：需从 HarnessConfig 提取或独立配置

    # 1. LLM 生成 5 条 query（新版 Prompt：全称->缩写）
    raw_queries = self._generate_search_queries(topic, keywords)

    # 2. 拆分"全称->缩写"为独立 query，去重，补充不足（Fix 5）
    queries = self._expand_and_dedup_queries(raw_queries, topic, keywords)

    # 3. 多路并行检索
    arxiv_tool = self.tools.get("arxiv_search")
    ss_tool = self.tools.get("semantic_scholar_search")
    cat_filter = infer_arxiv_category(topic, topic, config.domain_cat_map)

    all_papers: list[Paper] = []
    for q in queries:
        # arXiv 双通道：ti + abs
        all_papers += dual_channel_arxiv_search(
            arxiv_tool, q, cat_filter, config,
        )
        # Semantic Scholar 单通道
        ss_result = ss_tool.execute({
            "query": q, "max_results": config.ss_max_results,
        })
        if ss_result.success:
            for p_data in ss_result.data.get("papers", []):
                paper = Paper.from_dict(p_data)
                paper.hit_channels.append("semantic_scholar")
                paper.search_source_queries.append(q)
                all_papers.append(paper)

    # 4. Merge + Dedup（增强 multi_hit 统计）
    # 注：MergeResults 仍处理 list[dict]，传入前转 dict
    merge_data = [p.to_dict() for p in all_papers]
    merge_tool = self.tools.get("merge_results")
    merged = merge_tool.execute({"papers": merge_data})
    merged_dicts = merged.data.get("papers", []) if merged.success else []
    papers = [Paper.from_dict(p) for p in merged_dicts]

    # 5. 三级相关性过滤（Fix 3）
    filter_module = RelevanceFilter(self.llm, config)
    papers = filter_module.filter(papers, topic)

    # 6. RRF + 综合加权排序
    papers = rank_papers(papers, config)

    # 7. Fallback（Fix 4）
    fallback = FallbackManager(arxiv_tool, ss_tool, config)
    if len(papers) < config.fallback_phase6_min_papers:
        papers = fallback.fallback_phase6(papers, topic, keywords)
        papers = rank_papers(papers, config)
    if len(papers) < config.fallback_phase7_min_papers:
        papers = fallback.fallback_phase7(papers, topic)
        papers = rank_papers(papers, config)

    # 8. 截断 + 转 dict 返回
    self._papers = [p.to_dict() for p in papers[:self._task.max_papers]]
    return self._papers
```

### 6.2 `_expand_and_dedup_queries()` 实现

```python
def _expand_and_dedup_queries(
    self,
    raw_queries: list[str],
    topic: str,
    keywords: list[str],
) -> list[str]:
    """拆分"全称 -> 缩写"为独立 query，去重，补充不足（Fix 5）。"""
    expanded_set: set[str] = set()
    for line in raw_queries:
        line = line.strip()
        if "->" in line:
            parts = [p.strip() for p in line.split("->", 1)]
            full_name = parts[0]
            abbreviation = parts[1] if len(parts) >= 2 else full_name
            # Fix 5: 去重，两条一致时只保留一条
            expanded_set.add(full_name)
            if abbreviation.lower() != full_name.lower():
                expanded_set.add(abbreviation)
        else:
            expanded_set.add(line)

    queries = list(expanded_set)
    # 过滤无效 query
    queries = [q for q in queries if q and len(q) < 200]

    # 补充不足
    if len(queries) < 1:
        queries = [topic]
    if len(queries) < 2:
        queries.append(f"{topic} survey")
    while len(queries) < 3:
        queries.append(" ".join(keywords[:3]))

    logger.info("Expanded to %d final queries: %s", len(queries), queries)
    return queries
```

### 6.3 `_generate_search_queries()` 实现

```python
def _generate_search_queries(
    self,
    topic: str,
    keywords: list[str],
) -> list[str]:
    """使用 LLM 生成检索 query（新版 Prompt）。

    Fallback：LLM 失败时使用 topic + keywords。
    """
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

    # Fallback：使用 topic + keywords
    fallback = [topic]
    if keywords:
        fallback.extend(keywords[:4])
    logger.info("Using fallback queries: %s", fallback)
    return fallback
```

---

## 7. 旧逻辑复用/删除/重构对照表

| 文件 | 函数 | 处理 |
|------|------|------|
| `retrieval.py` | `ArxivSearch.execute()` | 重构 — 增加 `search_field`, `cat_filter` 参数；返回 Paper 对象 |
| `retrieval.py` | `SemanticScholarSearch` | 复用 — 接口不变 |
| `retrieval.py` | `MergeResults` | 增强 — 增加 `multi_hit` 统计 |
| `processing.py` | `SortByCitation` | 废弃 — 被 `rank_papers()` 替代 |
| `pipeline.py` | `_filter_relevant_papers()` | 废弃 — 被 `RelevanceFilter` 替代 |
| `pipeline.py` | `_retrieve_papers()` fallback 逻辑 | 废弃 — 被 `FallbackManager` 替代 |
| `pipeline.py` | `_retrieve_papers()` PDF下载 | 复用 — 不变 |
| `pipeline.py` | `_retrieve_papers()` query 解析 | 重构 — 抽取为 `_expand_and_dedup_queries()` |
| `harness.py` | `SortByCitation` 注册 | 保留 — 向后兼容 |

---

## 8. 日志埋点清单

| 位置 | 事件 | 日志级别 | 内容 |
|------|------|----------|------|
| `_generate_search_queries()` | Query 生成 | INFO | `"Generated %d raw queries: %s"` |
| `_expand_and_dedup_queries()` | Query 扩展 | INFO | `"Expanded to %d final queries: %s"` |
| `dual_channel_arxiv_search()` | arXiv ti 检索 | INFO | `"arXiv [ti] → %d unique papers"` |
| `dual_channel_arxiv_search()` | arXiv abs 检索 | INFO | `"arXiv [abs] → %d unique papers"` |
| `RelevanceFilter.filter()` | 过滤统计 | INFO | `"Relevance: strong=%d, weak=%d, filtered=%d"` |
| `RelevanceFilter.filter()` | 剔除事件 | WARNING | `"Filtered out: '%s' (confidence=%.2f)"` |
| `RelevanceFilter.filter()` | 降级事件 | INFO | `"Downgraded to weak: '%s' (conf=%.2f)"` |
| `FallbackManager.fallback_phase6()` | Phase6 触发 | WARNING | `"Phase6 fallback triggered: %d < %d"` |
| `FallbackManager.fallback_phase7()` | Phase7 触发 | WARNING | `"Phase7 fallback triggered: %d < %d"` |
| `rank_papers()` | 排序结果 | INFO | `"Ranked top-3: %s"` |
| `MergeResults` | multi_hit 统计 | INFO | `"multi_hit counts: %s"` |
| 任意 LLM 调用失败 | LLM 异常 | WARNING | `"LLM query generation failed: %s"` |

---

## 9. 边界场景处理

| 场景 | 处理方式 |
|------|----------|
| LLM 生成 query 失败 | 使用 topic + keywords 作为 fallback query |
| arXiv API 返回空 | 空列表，不报错 |
| Semantic Scholar 限流 | 指数退避重试（已有） |
| 全部论文被过滤 | 跳过过滤，保留全部，标记为 `weak` |
| 所有论文 relevance=irrelevant | 保留 confidence<0.6 的，标记为 `weak`（Fix 3） |
| 无摘要论文 | 无法判定为 `strong`，confidence ≤ 0.6 |
| Fallback 两种都触发 | Phase6 先执行，再 Phase7（Fix 4） |
| RRF 降级 | 如 RRF 计算结果异常，回退到 citation 简单排序 |
| all: 检索噪声 | Phase7 仅单通道 20 条，限制噪声（Fix 4） |
| 全称==缩写 | 去重，只保留一条（Fix 5） |