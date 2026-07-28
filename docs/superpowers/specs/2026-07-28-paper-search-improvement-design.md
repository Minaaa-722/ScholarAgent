# Paper Search Agent 改进设计

## 概述

提升论文搜索 Agent 的 **查准率（相关性）** 和 **权威性（高引/顶会论文）**，使得后续生成的综述论文对该主题的了解更全面、深入。

## 当前系统分析

### 现有检索流程

```
用户输入 (topic, keywords, goal)
  → LLM 生成 3 条搜索 query
  → arXiv API 搜索（按相关性排序）
  → Semantic Scholar API 搜索（按默认排序）
  → 合并、去重（DOI → 标题）
  → 按引用数降序排序 → 取 top-N（默认 20 篇）
  → 进入 Analysis / Writing 阶段
```

### 现有不足

| 维度 | 问题 |
|------|------|
| **查准率** | 搜索依赖 API 内置的文本匹配，topic 偏差的论文可能混入 |
| **权威性** | 引用数排序是粗糙的代理指标，没有区分 venue 质量；arXiv 论文缺少 venue 信息 |
| **查全率** | 单次搜索只能发现直接匹配的论文，引文网络中的相关工作未被发掘 |

### 不加新搜索源的理由

Semantic Scholar 已经索引了 IEEE、ACM、Springer、Elsevier 等几乎所有出版商的论文。增加新源会带来显著的 API 适配复杂度，但对覆盖范围的提升非常有限。DBLP 不作为搜索源，而是作为**元数据补充层**。

## 改进方案

### 架构图

```
用户输入 (topic, keywords, goal)
    │
    ▼
┌───────────────────────┐
│ 1. 种子搜索            │  arXiv + Semantic Scholar（基本不变）
│ (Seed Retrieval)      │
└─────────┬─────────────┘
          │ 原始论文列表
          ▼
┌───────────────────────┐
│ 2. 相关性验证          │  LLM 批量判断每篇论文与 topic 的相关性 (1-5)
│ (Relevance Filter)    │  过滤掉 < threshold 的低相关论文
└─────────┬─────────────┘
          │ 高相关种子论文
          ▼
┌───────────────────────┐
│ 3. 引文扩展            │  对 top-K 篇种子论文，通过 S2 API 拉取其
│ (Citation Expansion)  │  references / citations，发现更多权威论文
└─────────┬─────────────┘
          │ 种子 + 扩展论文
          ▼
┌───────────────────────┐
│ 4. DBLP Venue 查询    │  查询 DBLP 获取论文的正式发表 venue
│ (Venue Lookup)        │  判断是否顶会，用于权威性打分
└─────────┬─────────────┘
          │ 带 venue 标注的论文
          ▼
┌───────────────────────┐
│ 5. 复合排序 + 截断     │  score = α·citation + β·venue + γ·relevance
│ (Composite Ranking)   │  取 top-N 篇进入写作阶段
└───────────────────────┘
```

### 新增模块

#### 1. 相关性验证模块

**文件**: `agent/tools/relevance.py`

**类**: `RelevanceFilter(Tool)`

**逻辑**:
- 接收论文列表 + topic + threshold
- 构造批量 prompt，一次 LLM 调用判断所有论文（最多 50 篇/批）
- 每篇论文输出：相关性评分 (1-5) + 简短理由
- 过滤 < threshold 的论文
- 评分理由存入论文 dict 的 `_relevance_note` 字段

**Prompt 设计**:
```
You are a relevance judge for academic papers.
Given the research topic: "{topic}"
Rate each paper's relevance on a scale of 1-5:
5 = directly addressing the core topic
4 = highly related, covers a key sub-topic
3 = somewhat related, but peripheral
2 = marginally related, tangentially connected
1 = not relevant

For each paper, output: "TITLE | SCORE | BRIEF_REASON"
```

**安全降级**: LLM 调用失败 → 跳过过滤，保留所有论文

#### 2. 引文扩展模块

**文件**: `agent/tools/citation.py`

**类**: `CitationExpander(Tool)`

**逻辑**:
- 输入：已过滤的高相关种子论文
- 从种子论文中选出 top-K 篇（综合引用数 + 相关性排序）
- 对每篇调用 Semantic Scholar 引用 API:
  - `GET /graph/v1/paper/{paperId}/references?limit=N`
  - `GET /graph/v1/paper/{paperId}/citations?limit=N`
- 合并、去重、排除已在种子集合中的论文
- 对扩展出的论文做一轮相关性验证（复用 RelevanceFilter）
- 扩展论文的 `_expanded_from` 字段记录来源种子论文

**API 注意事项**:
- 只有 Semantic Scholar 返回的 `paperId` 可用于引用 API
- arXiv-only 论文先通过 S2 搜索接口获取 `paperId`
- 限流：请求间隔 1s，失败重试 2 次

**安全降级**: 某篇论文扩展失败 → 跳过，继续其他篇；所有扩展失败 → 回退到纯种子搜索

#### 3. DBLP Venue 查询模块

**文件**: `agent/tools/venue.py`

**类**: `VenueLookup(Tool)`

**逻辑**:
- 输入：论文列表
- 对每篇论文：
  - 如果已有 venue 且已知是顶会 → 直接标记，跳过 DBLP 查询
  - 否则查询 DBLP: `GET https://dblp.org/search/publ/api?q={title}&format=json`
  - 解析返回的 venue 名称
  - 匹配顶会白名单
- 输出：更新了 `venue`、`is_top_venue`、`venue_type`（conference/journal）字段的论文

**顶会白名单**（可配置）:
```python
TOP_VENUES = {
    # Computer Vision
    "cvpr", "iccv", "eccv", "bmvc", "wacv",
    # Machine Learning
    "neurips", "icml", "iclr", "jmlr", "mlsys", "aistats", "uai",
    # NLP
    "acl", "emnlp", "naacl", "eacl", "coling", "tacl",
    # AI
    "aaai", "ijcai", "ecai",
    # Software Engineering
    "icse", "fse", "ase", "issta", "tse", "tosem", "ist",
    # Systems & Networking
    "osdi", "sosp", "sigcomm", "mobicom", "nsdi", "eurosys", "atc",
    # PL & Theory
    "pldi", "popl", "cav", "stoc", "focs", "soda", "icalp",
    # Databases
    "sigmod", "vldb", "pods", "icde", "sigir",
    # Security
    "sp", "ccs", "usenix", "ndss",
}
```

**安全降级**: DBLP 查询失败 → 跳过该篇，venue 分为 0；DBLP 未收录 → venue 分为 0

#### 4. 复合排序模块

**文件**: 修改 `agent/tools/processing.py`，新增 `CompositeRanker` 类

**公式**:
```
score = α × norm_citation + β × venue_bonus + γ × relevance_score
```

| 权重 | 默认值 | 说明 |
|------|--------|------|
| α | 0.4 | 引用数归一化（除以当前列表最大引用数，0-1） |
| β | 0.3 | Venue 加分：顶会=1.0，知名期刊=0.7，有venue=0.3，无=0 |
| γ | 0.3 | LLM 相关性评分归一化（除以 5，0-1） |

**安全降级**: 某个维度分缺失 → 使用 0，其他维度正常加权

### 配置变更

**`agent/core/harness.py`** — `HarnessConfig` 新增字段:

```python
@dataclass
class HarnessConfig:
    # ... 现有字段 ...
    relevance_threshold: float = 3.0
    citation_expand_top_k: int = 5
    citation_expand_per_paper: int = 10
    composite_weights: dict = field(default_factory=lambda: {
        "citation": 0.4, "venue": 0.3, "relevance": 0.3,
    })
    enable_dblp_lookup: bool = True
```

### Pipeline 变更

**`agent/core/pipeline.py`** — `_retrieve_papers()` 方法修改:

```python
def _retrieve_papers(self) -> list[dict]:
    # 1. 现有搜索逻辑（arXiv + S2，不变）
    seeds = self._search_seeds()

    # 2. 新增：相关性过滤
    relevance_filter = self.tools.get("relevance_filter")
    if relevance_filter:
        filtered = relevance_filter.execute({
            "papers": seeds, "topic": self._task.topic,
            "threshold": self.config.relevance_threshold,
        })
        seeds = filtered.data.get("papers", seeds)

    # 3. 新增：引文扩展
    citation_expander = self.tools.get("citation_expand")
    if citation_expander and seeds:
        expanded = citation_expander.execute({
            "papers": seeds, "top_k": self.config.citation_expand_top_k,
            "per_paper": self.config.citation_expand_per_paper,
        })
        expanded_papers = expanded.data.get("papers", [])
        seeds.extend(expanded_papers)
        seeds, _ = _dedup_by_title(seeds)

    # 4. 新增：DBLP venue 查询
    if self.config.enable_dblp_lookup:
        venue_lookup = self.tools.get("venue_lookup")
        if venue_lookup:
            result = venue_lookup.execute({"papers": seeds})
            seeds = result.data.get("papers", seeds)

    # 5. 替换：复合排序替代纯引用排序
    ranker = self.tools.get("composite_rank")
    if ranker:
        ranked = ranker.execute({"papers": seeds})
        seeds = ranked.data.get("papers", seeds)

    # 6. 截断
    self._papers = seeds[:self.config.max_papers]
    return self._papers
```

### 工具注册

**`agent/core/harness.py`** 的 `__init__` 方法中注册新工具:

```python
self._tool_registry.register(RelevanceFilter())
self._tool_registry.register(CitationExpander())
self._tool_registry.register(VenueLookup())
self._tool_registry.register(CompositeRanker())
```

### 错误处理策略

| 模块 | 失败时的行为 |
|------|------------|
| 相关性过滤 | LLM 调用失败 → 跳过过滤，保留所有论文 |
| 引文扩展 | S2 API 失败 → 跳过该篇的扩展，继续其他篇 |
| DBLP 查询 | 查询失败 → 跳过该篇的 venue 查询，venue 分 = 0 |
| 复合排序 | 维度分缺失 → 使用 0，其他维度正常加权 |

每个模块通过配置开关控制，失败时安全降级，不影响整体流程。

### 测试策略

1. **单元测试**:
   - `test_relevance_filter.py`: 测试 LLM 响应的解析、阈值过滤、空输入
   - `test_citation_expander.py`: 测试 S2 响应解析、去重、种子论文选择
   - `test_venue_lookup.py`: 测试 DBLP 响应解析、顶会匹配、查询失败处理
   - `test_composite_ranker.py`: 测试权重计算、归一化、缺失值处理

2. **集成测试**:
   - `test_pipeline_search.py`: 测试完整的检索-过滤-扩展-排序流程

### 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `agent/tools/relevance.py` | **新增** | 相关性验证模块 |
| `agent/tools/citation.py` | **新增** | 引文扩展模块 |
| `agent/tools/venue.py` | **新增** | DBLP Venue 查询模块 |
| `agent/tools/processing.py` | **修改** | 新增 `CompositeRanker` 类 |
| `agent/tools/__init__.py` | **修改** | 导出新模块 |
| `agent/core/harness.py` | **修改** | 注册新工具，配置新增字段 |
| `agent/core/pipeline.py` | **修改** | `_retrieve_papers()` 新增中间步骤 |
| `tests/test_relevance.py` | **新增** | 单元测试 |
| `tests/test_citation.py` | **新增** | 单元测试 |
| `tests/test_venue.py` | **新增** | 单元测试 |
| `tests/test_pipeline.py` | **修改** | 新增集成测试 |

## 不采用的做法

### 不加新搜索源的理由

考虑过增加的源：IEEE Xplore、ACM DL、DBLP Search、Google Scholar、Crossref。

决策：**不加新搜索源**。Semantic Scholar 已经索引了 IEEE、ACM、Springer、Elsevier 等几乎所有出版商的论文。加新源会带来显著的 API 适配复杂度，但对覆盖范围的提升非常有限。DBLP 不作为搜索源，而是作为元数据补充层。

### 不采用迭代式检索的理由

多轮检索-分析-补全的迭代式方案理论上效果最好，但需要多次 LLM 调用，成本高、延迟长（从 ~10s 延长到 ~120s+）。当前方案通过引文扩展实现类似效果，只增加一次额外 API 调用，延迟可控。