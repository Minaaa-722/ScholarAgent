# Execution Page 阶段成果展示优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve Execution page stage artifacts — show full content, strip markdown for readability, make paper titles clickable links

**Architecture:** Two-file incremental change: backend `harness.py` sends full analysis text + paper URLs, frontend `StageTimeline.tsx` converts markdown to readable HTML and renders paper titles as hyperlinks.

**Tech Stack:** Python 3.10+ (backend), React 18 + TypeScript (frontend), no new dependencies

## Global Constraints

- No new npm/PyPI dependencies
- All changes backward-compatible: old `execution_details` without `url` field still renders correctly
- Markdown conversion uses simple regex (no AST parser) — sufficient for LLM output patterns
- Paper `url` derived from existing backend fields (`arxiv_id`, `url`)

---

### Task 1: Backend — unlock full analysis text and paper URLs

**Files:**
- Modify: `agent/core/harness.py` — `get_task_info()` method, lines 260-277

**Interfaces:**
- Consumes: `self._analysis` (string), `self._papers` (list of dicts with `url`, `arxiv_id`, `title`, `authors`, `year`, `citation_count`)
- Produces: `execution_details["analysis"]["preview"]` (full text, no truncation), `execution_details["papers"]["list"][]["url"]` (string, may be empty)

- [ ] **Step 1: Remove analysis truncation**

  Change line 283 from:
  ```python
  "preview": self._analysis[:300],
  ```
  to:
  ```python
  "preview": self._analysis,
  ```

- [ ] **Step 2: Remove paper count limit**

  Change line 262 from:
  ```python
  for p in self._papers[:10]:
  ```
  to:
  ```python
  for p in self._papers:
  ```

- [ ] **Step 3: Add URL field to paper items**

  After line 272 (`"source": "arxiv" if p.get("arxiv_id") else "semantic_scholar",`), add:
  ```python
                      "url": p.get("url", ""),
  ```

- [ ] **Step 4: Verify changes**

  Run: `python -c "import ast; ast.parse(open('agent/core/harness.py').read()); print('Syntax OK')"`
  Expected: Syntax OK

- [ ] **Step 5: Commit**

  ```bash
  git add agent/core/harness.py
  git commit -m "feat: send full analysis text and paper URLs to frontend"
  ```

---

### Task 2: Frontend — readable markdown rendering, paper links, full content

**Files:**
- Modify: `web/src/components/StageTimeline.tsx`

**Interfaces:**
- Consumes: `execution_details` (JSON with `plan`, `papers`, `analysis`, `sections`, `validation`)
- Produces: Rendered React components with improved readability

- [ ] **Step 1: Add `markdownToHtml` utility function**

  Insert this function at the top of `StageTimeline.tsx`, after the imports (before line 1):

  ```typescript
  /** Convert simple markdown patterns to readable HTML for display */
  function markdownToHtml(text: string): string {
    const escaped = text
      // Escape HTML entities first to prevent XSS
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");

    return escaped
      // Headings
      .replace(/^#### (.+)$/gm, '<h5>$1</h5>')
      .replace(/^### (.+)$/gm, '<h4>$1</h4>')
      .replace(/^## (.+)$/gm, '<h3>$1</h3>')
      .replace(/^# (.+)$/gm, '<h2>$1</h2>')
      // Bold and italic
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      // Inline code
      .replace(/`(.+?)`/g, '<code>$1</code>')
      // Unordered lists
      .replace(/^- (.+)$/gm, '• $1')
      // Paragraph breaks (double newline)
      .replace(/\n\n/g, '</p><p>')
      // Single newlines within paragraphs
      .replace(/\n/g, '<br/>')
      // Wrap in paragraph tags
      .replace(/^(.+)$/, '<p>$1</p>');
  }
  ```

- [ ] **Step 2: Add `url` field to `PaperInfo` interface**

  Add `url?: string;` to the `PaperInfo` interface after `source` (line 11):

  ```typescript
  export interface PaperInfo {
    title: string;
    authors: string;
    year: string | number;
    citations: number;
    source: string;
    url?: string;       // optional link to the paper
  }
  ```

- [ ] **Step 3: Update Plan rendering — strip markdown artifacts**

  Replace the Plan section's preview rendering (lines 84-96) so it strips markdown syntax:

  ```tsx
      case "planning":
        return details.plan ? (
          <Card title="📋 研究计划">
            <p className="text-secondary mb-sm">
              共 {details.plan.section_count} 个章节/要点
            </p>
            {details.plan.preview.map((line, i) => (
              <p
                key={i}
                style={{
                  margin: "0.2rem 0",
                  paddingLeft: "0.5rem",
                  borderLeft: "2px solid var(--color-primary)",
                  fontSize: "var(--font-size-sm)",
                }}
              >
                {line
                  .replace(/^\*\*(.+)\*\*$/, '$1')
                  .replace(/^###\s*/, '')
                  .replace(/^##\s*/, '')
                  .replace(/^#\s*/, '')
                  .replace(/^- /, '• ')}
              </p>
            ))}
          </Card>
        ) : (
          <p className="text-disabled" style={{ fontSize: "var(--font-size-sm)" }}>
            暂无计划数据
          </p>
        );
  ```

- [ ] **Step 4: Update Analysis rendering — full content + HTML**

  Replace the Analysis case (lines 185-204) with:

  ```tsx
      case "analysis":
        return details.analysis ? (
          <Card title="🔬 论文分析">
            <div
              className="artifact-content"
              style={{
                color: "var(--color-text-secondary)",
                fontSize: "var(--font-size-sm)",
                lineHeight: 1.7,
                margin: 0,
                overflowX: "auto",
              }}
              dangerouslySetInnerHTML={{
                __html: markdownToHtml(details.analysis.preview),
              }}
            />
          </Card>
        ) : (
          <p className="text-disabled" style={{ fontSize: "var(--font-size-sm)" }}>
            暂无分析数据
          </p>
        );
  ```

- [ ] **Step 5: Update Papers rendering — clickable links + full list**

  Replace the paper list rendering inside the `retrieval` case (lines 133-175) with:

  ```tsx
          {details.papers && (
            <Card
              title={`📄 检索到的论文（共 ${details.papers.total} 篇）`}
            >
              <div>
                {details.papers.list.map((p, i) => (
                  <div
                    key={i}
                    style={{
                      padding: "0.6rem",
                      marginBottom: "0.4rem",
                      background: "#fafafa",
                      borderRadius: "var(--radius-md)",
                      border: "1px solid var(--color-border-light)",
                    }}
                  >
                    <div style={{ fontWeight: 600, fontSize: "var(--font-size-sm)" }}>
                      {p.url ? (
                        <a
                          href={p.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          style={{
                            color: "var(--color-primary)",
                            textDecoration: "none",
                          }}
                          title={p.url}
                        >
                          {p.title} ↗
                        </a>
                      ) : (
                        p.title
                      )}
                    </div>
                    <div
                      style={{
                        fontSize: "var(--font-size-xs)",
                        color: "var(--color-text-secondary)",
                        marginTop: "0.2rem",
                      }}
                    >
                      {p.authors} · {p.year} · 引用: {p.citations}
                      {p.source && <span> · 来源: {p.source}</span>}
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          )}
  ```

  Note: Removed `maxHeight: 300, overflowY: "auto"` and the `total > 10` truncation notice.

- [ ] **Step 6: TypeScript check**

  Run: `cd web && npx tsc --noEmit --pretty 2>&1 | head -30`
  Expected: No type errors (the `url?` is optional, so existing data without it still works)

- [ ] **Step 7: Commit**

  ```bash
  git add web/src/components/StageTimeline.tsx
  git commit -m "feat: strip markdown, show full content, add paper link"
  ```

---

### Task 3: Integration verification

**Files:**
- Read: `agent/core/harness.py` — verify all three changes are in place
- Read: `web/src/components/StageTimeline.tsx` — verify all four changes are in place

- [ ] **Step 1: Verify backend changes**

  ```bash
  grep -n "preview.*self._analysis" agent/core/harness.py | grep -v "\[:300\]"
  ```
  Expected: Shows `"preview": self._analysis,` (no `[:300]`)

  ```bash
  grep -n "for p in self._papers" agent/core/harness.py
  ```
  Expected: Shows `for p in self._papers:` (no `[:10]`)

  ```bash
  grep -n '"url"' agent/core/harness.py
  ```
  Expected: Shows `"url": p.get("url", ""),` in the paper list builder

- [ ] **Step 2: Verify frontend changes**

  ```bash
  grep -n "markdownToHtml" web/src/components/StageTimeline.tsx
  ```
  Expected: Shows function definition and usage

  ```bash
  grep -n "url?" web/src/components/StageTimeline.tsx
  ```
  Expected: Shows `url?: string` in PaperInfo and `href={p.url}` in the link

  ```bash
  grep -n "maxHeight.*300" web/src/components/StageTimeline.tsx
  ```
  Expected: No matches (limitation removed)

- [ ] **Step 3: Final commit summary**

  ```bash
  git log --oneline -3
  ```
  Expected: Shows both commits with proper messages