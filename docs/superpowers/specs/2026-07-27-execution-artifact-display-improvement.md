# Execution Page 阶段成果展示优化设计

## 背景

当前 Execution 页面的阶段成果展示框存在三个问题：

1. **分析文本截断**：后端将 `analysis` 文本截断为 300 字符（`self._analysis[:300]`），用户无法看到完整内容
2. **Markdown 原始展示**：LLM 输出的 markdown 格式文本（`**bold**`、`*italic*`、列表等）以纯文本展示，可读性差
3. **论文列表不可点击**：论文标题为纯文本，且后端 `url` 字段未传递到前端，无法跳转到原文

## 方案

采用增量改进方案，在现有 `StageTimeline` 组件架构上做精确改动，不引入新依赖、不重构组件结构。

### 后端改动

**文件**: `agent/core/harness.py` — `get_task_info()` 方法

| 改动 | 位置 | 说明 |
|------|------|------|
| 去掉 `[:300]` 截断 | `details["analysis"]["preview"] = self._analysis` | 发送完整分析文本 |
| 去掉 `[:10]` 限制 | `for p in self._papers:` | 传递全部论文 |
| 增加 `url` 字段 | `"url": p.get("url", "")` | 论文链接传递到前端 |

### 前端改动

**文件**: `web/src/components/StageTimeline.tsx`

#### 1. Markdown 清理工具函数

新增 `markdownToHtml(text: string): string` 函数，将常见 markdown 语法转为 HTML 标签：

| Markdown | 输出 HTML |
|----------|-----------|
| `# Title` | `<h2>Title</h2>` |
| `## Title` | `<h3>Title</h3>` |
| `### Title` | `<h4>Title</h4>` |
| `**bold**` | `<strong>bold</strong>` |
| `*italic*` | `<em>italic</em>` |
| `` `code` `` | `<code>code</code>` |
| `- item` | `• item` |
| 双换行 | 段落分隔 |

#### 2. PaperInfo 类型

```typescript
export interface PaperInfo {
  title: string;
  authors: string;
  year: string | number;
  citations: number;
  source: string;
  url?: string;  // 新增
}
```

#### 3. Analysis 阶段 — 全量展示 + HTML 渲染

- 使用 `dangerouslySetInnerHTML` + `markdownToHtml` 渲染
- 移除截断，展示完整内容
- 设置 `lineHeight: 1.7` 提高可读性

#### 4. Papers 列表 — 可点击链接 + 完整列表

- 有 `url` 的论文标题渲染为 `<a href="..." target="_blank" rel="noopener noreferrer">` 链接
- 移除 `maxHeight: 300` 和 `overflow-y: auto` 滚动限制
- 移除 `total > 10` 截断提示
- 每篇论文增加来源（source）标注

#### 5. Plan 阶段 — Markdown 清理

- 对 `plan.preview` 中的每一行做 markdown 符号清理

### 未触及的模块

- 路由、API 端点、WebSocket 通信 — 无改动
- 数据流（后端 → WebSocket → 前端 `ProgressInfo`）— 不变
- `Card`、`LoadingSkeleton` 等基础组件 — 不变
- 其他阶段（Writing、Validation、Format Repair）— 不变

## 数据流

```
Backend (harness.py)
  └─ get_task_info() → execution_details 增加 url, 去掉截断
      └─ WebSocket → ProgressInfo
          └─ Frontend StageTimeline (StageTimeline.tsx)
              └─ StageArtifact(analysis) → markdownToHtml → 全量渲染
              └─ StageArtifact(retrieval) → <a href={url}> 跳转链接
```

## 注意事项

- `dangerouslySetInnerHTML` 的输入来自后端 LLM 输出，而非用户输入，XSS 风险可控
- 论文 `url` 字段后端已有（arXiv/Semantic Scholar 检索结果自带），仅需传递
- 本设计不影响已有测试和功能