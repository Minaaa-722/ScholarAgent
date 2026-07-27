# Phase 2: Knowledge Explorer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the Knowledge Explorer from a basic log viewer into a full paper explorer with sortable paper table, D3.js citation graph, and paper detail panel.

**Architecture:** Add 3 new API endpoints on the backend (`/papers`, `/papers/graph`, `/papers/{index}`) that expose the existing paper data from `Harness._papers`. Build 3 new frontend components (PaperTable, PaperGraph, PaperDetail) and integrate them into the existing KnowledgeExplorer page with a three-column layout, all using the existing design system (Card, Badge, LoadingSkeleton, EmptyState).

**Tech Stack:** FastAPI (backend), React 18 + TypeScript + Vite (frontend), D3.js v7 (force-directed graph), CSS custom properties (design tokens)

## Global Constraints

- All API endpoints must use the existing `APIRouter` prefix `/api/survey` and `Depends(get_harness)` pattern
- All frontend components must use the existing design system components (`Card`, `Badge`, `LoadingSkeleton`, `EmptyState`, `Button`, `ErrorBoundary`) from `web/src/components/`
- CSV export must produce valid UTF-8 CSV with BOM for Excel compatibility
- D3.js must be installed via npm (`d3@^7`), no other graph library
- All API tests must use the existing `test_harness` fixture pattern from `tests/test_api.py`
- No frontend test framework exists yet — verify manually via dev server
- Follow existing patterns: inline styles using CSS custom properties (`var(--color-*)`, `var(--space-*)`, `var(--font-size-*)`, `var(--radius-*)`, `var(--shadow-*)`)

---

### Task 1: Paper List API Endpoint

**Files:**
- Modify: `api/routes/survey.py:52-54` (add new endpoints after `get_execution_log`)
- Modify: `api/models.py` (add `PaperResponse` and `GraphResponse` models)
- Test: `tests/test_api.py` (add paper endpoint tests)

**Interfaces:**
- Consumes: `Harness.get_task_info()` (returns `{"execution_details": {"papers": {"total": int, "list": [{"title": str, "authors": str, "year": str, "citations": int, "source": str}]}}}`) and `Harness._papers` (internal list of raw paper dicts)
- Produces: `GET /api/survey/papers` → `{"papers": [PaperItem], "total": int}`, `GET /api/survey/papers/graph` → `{"nodes": [GraphNode], "links": [GraphLink]}`, `GET /api/survey/papers/{index}` → `PaperItem` with full metadata

- [ ] **Step 1: Add PaperListResponse and GraphResponse models to api/models.py**

```python
class PaperItem(BaseModel):
    title: str
    authors: str
    year: str = ""
    citations: int = 0
    source: str = ""
    paper_index: int = 0  # position in the papers list

class PaperListResponse(BaseModel):
    papers: list[PaperItem]
    total: int

class GraphNode(BaseModel):
    id: int
    label: str
    group: str  # source: "arxiv" | "semantic_scholar" | "unknown"
    size: int  # citation count (clamped)

class GraphLink(BaseModel):
    source: int
    target: int
    weight: int = 1

class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    links: list[GraphLink]
```

- [ ] **Step 2: Write failing tests for paper endpoints**

```python
# Add to tests/test_api.py

@pytest.mark.asyncio
async def test_get_papers_empty(client, test_harness):
    """Returns empty list when no papers exist."""
    response = await client.get("/api/survey/papers")
    assert response.status_code == 200
    data = response.json()
    assert data["papers"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_get_papers_with_data(client, test_harness):
    """Returns paper list when papers exist."""
    # Inject papers into harness
    test_harness._papers = [
        {"title": "Paper One", "authors": ["Alice"], "year": "2023", "citation_count": 10, "arxiv_id": "2301.001"},
        {"title": "Paper Two", "authors": ["Bob", "Charlie"], "year": "2024", "citation_count": 5, "source": "semantic_scholar"},
    ]
    response = await client.get("/api/survey/papers")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert data["papers"][0]["title"] == "Paper One"
    assert data["papers"][0]["authors"] == "Alice"
    assert data["papers"][0]["source"] == "arxiv"
    assert data["papers"][1]["title"] == "Paper Two"
    assert data["papers"][1]["source"] == "semantic_scholar"


@pytest.mark.asyncio
async def test_get_papers_graph(client, test_harness):
    """Returns graph nodes and links."""
    test_harness._papers = [
        {"title": "Paper A", "authors": ["Alice"], "year": "2023", "citation_count": 15, "arxiv_id": "123"},
        {"title": "Paper B", "authors": ["Bob"], "year": "2024", "citation_count": 3, "source": "semantic_scholar"},
    ]
    response = await client.get("/api/survey/papers/graph")
    assert response.status_code == 200
    data = response.json()
    assert len(data["nodes"]) == 2
    assert data["nodes"][0]["label"] == "Paper A"
    assert data["nodes"][0]["size"] == 15
    assert data["nodes"][0]["group"] == "arxiv"
    # Links should connect papers with shared authors
    assert isinstance(data["links"], list)


@pytest.mark.asyncio
async def test_get_paper_by_index(client, test_harness):
    """Returns a single paper by index."""
    test_harness._papers = [
        {"title": "Paper One", "authors": ["Alice"], "year": "2023", "citation_count": 10, "arxiv_id": "2301.001"},
    ]
    response = await client.get("/api/survey/papers/0")
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Paper One"
    assert data["paper_index"] == 0


@pytest.mark.asyncio
async def test_get_paper_not_found(client, test_harness):
    """Returns 404 for out-of-range index."""
    response = await client.get("/api/survey/papers/999")
    assert response.status_code == 404
    assert "detail" in response.json()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_api.py -v -k "paper" 2>&1 | head -40`
Expected: FAIL with "No module" or "route not found" errors

- [ ] **Step 4: Add paper API endpoints to api/routes/survey.py**

Add after the existing `get_execution_log` function (line 54):

```python
@router.get("/papers", response_model=PaperListResponse)
async def get_papers(harness: Harness = Depends(get_harness)):
    """Return the list of retrieved papers."""
    info = harness.get_task_info()
    papers_data = info.get("execution_details", {}).get("papers", {})
    raw_list = papers_data.get("list", [])
    items = []
    for idx, p in enumerate(raw_list):
        items.append(PaperItem(
            title=p.get("title", "Untitled"),
            authors=p.get("authors", "Unknown"),
            year=str(p.get("year", "")),
            citations=p.get("citations", 0),
            source=p.get("source", "unknown"),
            paper_index=idx,
        ))
    return PaperListResponse(papers=items, total=papers_data.get("total", len(items)))


@router.get("/papers/graph", response_model=GraphResponse)
async def get_papers_graph(harness: Harness = Depends(get_harness)):
    """Build a citation/co-authorship graph from the paper list."""
    raw_papers = harness._papers if hasattr(harness, '_papers') else []
    nodes = []
    links = []
    for idx, p in enumerate(raw_papers):
        title = p.get("title", "Untitled")
        source = "arxiv" if p.get("arxiv_id") else "semantic_scholar" if p.get("source") == "semantic_scholar" else "unknown"
        citations = p.get("citation_count", 0) or 0
        nodes.append(GraphNode(
            id=idx,
            label=title[:60],
            group=source,
            size=max(1, min(citations, 100)),
        ))
    # Create links between papers that share authors
    for i, p1 in enumerate(raw_papers):
        authors1 = set(a.lower() for a in p1.get("authors", []) if a)
        if not authors1:
            continue
        for j in range(i + 1, len(raw_papers)):
            p2 = raw_papers[j]
            authors2 = set(a.lower() for a in p2.get("authors", []) if a)
            shared = authors1 & authors2
            if shared:
                links.append(GraphLink(source=i, target=j, weight=len(shared)))
    return GraphResponse(nodes=nodes, links=links)


@router.get("/papers/{index:int}")
async def get_paper_detail(index: int, harness: Harness = Depends(get_harness)):
    """Return full metadata for a single paper by index."""
    raw_papers = harness._papers if hasattr(harness, '_papers') else []
    if index < 0 or index >= len(raw_papers):
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Paper index {index} not found")
    p = raw_papers[index]
    return PaperItem(
        title=p.get("title", "Untitled"),
        authors=", ".join(p.get("authors", [])) if isinstance(p.get("authors"), list) else str(p.get("authors", "Unknown")),
        year=str(p.get("year", "")),
        citations=p.get("citation_count", 0) or 0,
        source="arxiv" if p.get("arxiv_id") else p.get("source", "unknown"),
        paper_index=index,
    )
```

- [ ] **Step 5: Add imports to api/routes/survey.py**

```python
# Add at the top imports section
from api.models import SurveyRequest, SurveyResponse, PaperItem, PaperListResponse, GraphNode, GraphLink, GraphResponse
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_api.py -v -k "paper" 2>&1`
Expected: All 5 paper tests PASS

- [ ] **Step 7: Commit**

```bash
git add api/routes/survey.py api/models.py tests/test_api.py
git commit -m "feat: add paper list, graph, and detail API endpoints"
```

---

### Task 2: PaperTable Component

**Files:**
- Create: `web/src/components/PaperTable.tsx`
- Modify: `web/src/api/client.ts` (add `getPapers` function)

**Interfaces:**
- Consumes: `getPapers()` → `{papers: Array<{title, authors, year, citations, source, paper_index}>, total: number}`
- Produces: `<PaperTable papers={PaperItem[]} onSelect={(index) => void} selectedIndex={number | null} />` component

- [ ] **Step 1: Add API client function to web/src/api/client.ts**

```typescript
export interface PaperItem {
  title: string;
  authors: string;
  year: string;
  citations: number;
  source: string;
  paper_index: number;
}

export interface PaperListResponse {
  papers: PaperItem[];
  total: number;
}

export async function getPapers(): Promise<PaperListResponse> {
  const res = await fetch(`${API_BASE}/api/survey/papers`);
  if (!res.ok) throw new Error("Failed to fetch papers");
  return res.json();
}

export async function getPaperGraph(): Promise<{ nodes: GraphNode[]; links: GraphLink[] }> {
  const res = await fetch(`${API_BASE}/api/survey/papers/graph`);
  if (!res.ok) throw new Error("Failed to fetch paper graph");
  return res.json();
}

export interface GraphNode {
  id: number;
  label: string;
  group: string;
  size: number;
}

export interface GraphLink {
  source: number;
  target: number;
  weight: number;
}

export async function getPaperDetail(index: number): Promise<PaperItem> {
  const res = await fetch(`${API_BASE}/api/survey/papers/${index}`);
  if (!res.ok) throw new Error("Paper not found");
  return res.json();
}
```

- [ ] **Step 2: Create PaperTable component**

```tsx
import React, { useMemo, useState } from "react";
import Card from "./Card";
import Badge from "./Badge";
import EmptyState from "./EmptyState";
import LoadingSkeleton from "./LoadingSkeleton";

interface PaperItem {
  title: string;
  authors: string;
  year: string;
  citations: number;
  source: string;
  paper_index: number;
}

interface PaperTableProps {
  papers: PaperItem[];
  loading: boolean;
  error: string | null;
  onSelect: (index: number) => void;
  selectedIndex: number | null;
}

type SortKey = "title" | "year" | "citations" | "source";
type SortDir = "asc" | "desc";

const SORT_LABELS: Record<SortKey, string> = {
  title: "Title",
  year: "Year",
  citations: "Citations",
  source: "Source",
};

const SOURCE_BADGE_COLOR: Record<string, "blue" | "green" | "gray"> = {
  arxiv: "blue",
  semantic_scholar: "green",
};

export default function PaperTable({ papers, loading, error, onSelect, selectedIndex }: PaperTableProps) {
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("citations");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir(d => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir(key === "year" || key === "citations" ? "desc" : "asc");
    }
  };

  const filtered = useMemo(() => {
    if (!search.trim()) return papers;
    const q = search.toLowerCase();
    return papers.filter(p =>
      p.title.toLowerCase().includes(q) ||
      p.authors.toLowerCase().includes(q)
    );
  }, [papers, search]);

  const sorted = useMemo(() => {
    const arr = [...filtered];
    arr.sort((a, b) => {
      let cmp = 0;
      if (sortKey === "citations") {
        cmp = (a.citations || 0) - (b.citations || 0);
      } else if (sortKey === "year") {
        cmp = (a.year || "").localeCompare(b.year || "");
      } else if (sortKey === "source") {
        cmp = (a.source || "").localeCompare(b.source || "");
      } else {
        cmp = (a.title || "").localeCompare(b.title || "");
      }
      return sortDir === "asc" ? cmp : -cmp;
    });
    return arr;
  }, [filtered, sortKey, sortDir]);

  if (loading) {
    return <LoadingSkeleton variant="card" lines={5} />;
  }

  if (error) {
    return (
      <Card title="Papers" borderColor="var(--color-danger)">
        <p style={{ color: "var(--color-danger)" }}>Failed to load papers: {error}</p>
      </Card>
    );
  }

  if (papers.length === 0) {
    return (
      <EmptyState
        icon="📄"
        title="No Papers Yet"
        description="Start a research task to retrieve papers."
      />
    );
  }

  return (
    <Card title={`Papers (${papers.length})`}>
      {/* Search bar */}
      <div style={{ marginBottom: "var(--space-md)" }}>
        <input
          type="text"
          placeholder="Search by title or author…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{
            width: "100%",
            padding: "var(--space-sm) var(--space-md)",
            border: "1px solid var(--color-border)",
            borderRadius: "var(--radius-md)",
            fontSize: "var(--font-size-sm)",
            boxSizing: "border-box",
            outline: "none",
          }}
        />
      </div>

      {/* Sortable column headers */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "3fr 1fr 1fr 1fr",
        gap: "var(--space-sm)",
        padding: "var(--space-sm) var(--space-md)",
        borderBottom: "2px solid var(--color-border)",
        fontSize: "var(--font-size-xs)",
        fontWeight: "var(--font-weight-semibold)",
        color: "var(--color-text-secondary)",
        textTransform: "uppercase",
        letterSpacing: "0.05em",
      }}>
        {(Object.keys(SORT_LABELS) as SortKey[]).map(key => (
          <div
            key={key}
            onClick={() => handleSort(key)}
            style={{
              cursor: "pointer",
              userSelect: "none",
              display: "flex",
              alignItems: "center",
              gap: "0.25rem",
              color: sortKey === key ? "var(--color-primary)" : undefined,
            }}
          >
            {SORT_LABELS[key]}
            {sortKey === key && (
              <span>{sortDir === "asc" ? "▲" : "▼"}</span>
            )}
          </div>
        ))}
      </div>

      {/* Paper rows */}
      <div style={{ maxHeight: 400, overflowY: "auto" }}>
        {sorted.length === 0 ? (
          <p style={{ padding: "var(--space-md)", color: "var(--color-text-disabled)", textAlign: "center" }}>
            No papers match "{search}"
          </p>
        ) : (
          sorted.map((p, i) => {
            const isSelected = selectedIndex === p.paper_index;
            const color = SOURCE_BADGE_COLOR[p.source] || "gray";
            return (
              <div
                key={p.paper_index}
                onClick={() => onSelect(p.paper_index)}
                style={{
                  display: "grid",
                  gridTemplateColumns: "3fr 1fr 1fr 1fr",
                  gap: "var(--space-sm)",
                  padding: "var(--space-sm) var(--space-md)",
                  borderBottom: "1px solid var(--color-border-light)",
                  cursor: "pointer",
                  background: isSelected ? "var(--color-primary-light)" : undefined,
                  transition: "background var(--transition-fast)",
                  fontSize: "var(--font-size-sm)",
                }}
                onMouseEnter={e => { if (!isSelected) e.currentTarget.style.background = "#fafafa"; }}
                onMouseLeave={e => { if (!isSelected) e.currentTarget.style.background = ""; }}
              >
                <div>
                  <div style={{ fontWeight: "var(--font-weight-semibold)", color: "var(--color-text-primary)", marginBottom: "0.15rem" }}>
                    {p.title}
                  </div>
                  <div style={{ color: "var(--color-text-secondary)", fontSize: "var(--font-size-xs)" }}>
                    {p.authors}
                  </div>
                </div>
                <div style={{ color: "var(--color-text-secondary)", alignSelf: "center" }}>{p.year}</div>
                <div style={{ color: "var(--color-text-secondary)", alignSelf: "center" }}>{p.citations}</div>
                <div style={{ alignSelf: "center" }}>
                  <Badge color={color}>{p.source}</Badge>
                </div>
              </div>
            );
          })
        )}
      </div>
    </Card>
  );
}
```

- [ ] **Step 3: Verify the component builds**

Run: `cd web && npx tsc --noEmit src/components/PaperTable.tsx 2>&1`
Expected: No type errors (or only type errors from unrelated files)

- [ ] **Step 4: Commit**

```bash
git add web/src/components/PaperTable.tsx web/src/api/client.ts
git commit -m "feat: add PaperTable component with sort/search"
```

---

### Task 3: PaperGraph Component (D3.js Force-Directed Graph)

**Files:**
- Create: `web/src/components/PaperGraph.tsx`
- Modify: `web/package.json` (add `d3` dependency)

**Interfaces:**
- Consumes: `getPaperGraph()` → `{nodes: GraphNode[], links: GraphLink[]}`
- Produces: `<PaperGraph nodes={GraphNode[]} links={GraphLink[]} onSelect={(id) => void} selectedId={number | null} />` component

- [ ] **Step 1: Install d3 dependency**

```bash
cd web && npm install d3@^7 && npm install -D @types/d3@^7
```

- [ ] **Step 2: Create PaperGraph component**

```tsx
import React, { useEffect, useRef, useCallback } from "react";
import Card from "./Card";
import LoadingSkeleton from "./LoadingSkeleton";
import EmptyState from "./EmptyState";
import * as d3 from "d3";

interface GraphNode {
  id: number;
  label: string;
  group: string;
  size: number;
}

interface GraphLink {
  source: number;
  target: number;
  weight: number;
}

interface PaperGraphProps {
  nodes: GraphNode[];
  links: GraphLink[];
  loading: boolean;
  error: string | null;
  onSelect: (id: number) => void;
  selectedId: number | null;
}

const GROUP_COLORS: Record<string, string> = {
  arxiv: "#1976d2",
  semantic_scholar: "#4caf50",
  unknown: "#999",
};

export default function PaperGraph({ nodes, links, loading, error, onSelect, selectedId }: PaperGraphProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 500, height: 400 });
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null);

  // Track dimensions on resize
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver(entries => {
      for (const entry of entries) {
        const { width } = entry.contentRect;
        setDimensions({ width: Math.max(300, width), height: Math.max(300, Math.min(500, width * 0.7)) });
      }
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // Draw graph
  useEffect(() => {
    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    if (nodes.length === 0) return;

    const { width, height } = dimensions;
    const color = (d: GraphNode) => GROUP_COLORS[d.group] || GROUP_COLORS.unknown;

    // Zoom behavior
    const g = svg.append("g");
    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.3, 3])
      .on("zoom", (event) => {
        g.attr("transform", event.transform);
      });
    svg.call(zoom);

    // Simulation
    const simulation = d3.forceSimulation<GraphNode>(nodes)
      .force("link", d3.forceLink<GraphNode, GraphLink>(links)
        .id(d => d.id)
        .distance(d => 150 - d.weight * 20)
        .strength(0.3))
      .force("charge", d3.forceManyBody().strength(-200))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collision", d3.forceCollide().radius(d => d.size * 0.5 + 10));

    // Links
    const link = g.append("g")
      .selectAll("line")
      .data(links)
      .join("line")
      .attr("stroke", "#ccc")
      .attr("stroke-width", d => Math.max(1, d.weight))
      .attr("stroke-opacity", 0.6);

    // Nodes
    const node = g.append("g")
      .selectAll("circle")
      .data(nodes)
      .join("circle")
      .attr("r", d => Math.max(5, Math.min(d.size * 0.5 + 5, 30)))
      .attr("fill", d => color(d))
      .attr("stroke", d => d.id === selectedId ? "#fff" : "none")
      .attr("stroke-width", d => d.id === selectedId ? 3 : 0)
      .attr("cursor", "pointer")
      .on("click", (_event, d) => onSelect(d.id))
      .on("mouseenter", (_event, d) => setHoveredNode(d))
      .on("mouseleave", () => setHoveredNode(null))
      // @ts-expect-error d3 types
      .call(d3.drag<SVGCircleElement, GraphNode>()
        .on("start", (event, d) => {
          if (!event.active) simulation.alphaTarget(0.3).restart();
          d.fx = d.x;
          d.fy = d.y;
        })
        .on("drag", (event, d) => {
          d.fx = event.x;
          d.fy = event.y;
        })
        .on("end", (event, d) => {
          if (!event.active) simulation.alphaTarget(0);
          d.fx = null;
          d.fy = null;
        }));

    // Labels
    const label = g.append("g")
      .selectAll("text")
      .data(nodes)
      .join("text")
      .text(d => d.label.length > 20 ? d.label.slice(0, 18) + "…" : d.label)
      .attr("font-size", "10px")
      .attr("dx", d => Math.max(5, Math.min(d.size * 0.5 + 5, 30)) + 3)
      .attr("dy", "0.35em")
      .attr("fill", "var(--color-text-secondary)")
      .attr("pointer-events", "none");

    // Tick
    simulation.on("tick", () => {
      link
        .attr("x1", d => (d.source as any).x)
        .attr("y1", d => (d.source as any).y)
        .attr("x2", d => (d.target as any).x)
        .attr("y2", d => (d.target as any).y);
      node
        .attr("cx", d => d.x!)
        .attr("cy", d => d.y!);
      label
        .attr("x", d => d.x!)
        .attr("y", d => d.y!);
    });

    // Cleanup
    return () => { simulation.stop(); };
  }, [nodes, links, dimensions, selectedId, onSelect]);

  if (loading) {
    return <LoadingSkeleton variant="card" lines={5} />;
  }

  if (error) {
    return (
      <Card title="Citation Graph" borderColor="var(--color-danger)">
        <p style={{ color: "var(--color-danger)" }}>Failed to load graph: {error}</p>
      </Card>
    );
  }

  if (nodes.length === 0) {
    return (
      <EmptyState
        icon="🔗"
        title="No Graph Data"
        description="Papers will appear here as a citation network once retrieved."
      />
    );
  }

  return (
    <Card title="Citation Network">
      <div ref={containerRef} style={{ position: "relative", width: "100%" }}>
        <svg
          ref={svgRef}
          width={dimensions.width}
          height={dimensions.height}
          style={{ display: "block", background: "#fafafa", borderRadius: "var(--radius-md)" }}
        />
        {/* Tooltip */}
        {hoveredNode && (
          <div style={{
            position: "absolute",
            bottom: "var(--space-sm)",
            left: "var(--space-sm)",
            background: "rgba(0,0,0,0.8)",
            color: "#fff",
            padding: "var(--space-xs) var(--space-sm)",
            borderRadius: "var(--radius-sm)",
            fontSize: "var(--font-size-xs)",
            maxWidth: "80%",
            pointerEvents: "none",
          }}>
            {hoveredNode.label}
            <span style={{ opacity: 0.7 }}> — {hoveredNode.group}</span>
          </div>
        )}
        {/* Legend */}
        <div style={{
          position: "absolute",
          top: "var(--space-sm)",
          right: "var(--space-sm)",
          background: "rgba(255,255,255,0.9)",
          padding: "var(--space-xs) var(--space-sm)",
          borderRadius: "var(--radius-sm)",
          fontSize: "var(--font-size-xs)",
          display: "flex",
          flexDirection: "column",
          gap: "0.15rem",
        }}>
          {Object.entries(GROUP_COLORS).map(([key, color]) => (
            <div key={key} style={{ display: "flex", alignItems: "center", gap: "0.3rem" }}>
              <span style={{ width: 8, height: 8, borderRadius: "50%", background: color, display: "inline-block" }} />
              {key === "semantic_scholar" ? "Semantic Scholar" : key.charAt(0).toUpperCase() + key.slice(1)}
            </div>
          ))}
        </div>
        {/* Instructions */}
        <div style={{
          position: "absolute",
          bottom: "var(--space-sm)",
          right: "var(--space-sm)",
          color: "var(--color-text-disabled)",
          fontSize: "var(--font-size-xs)",
        }}>
          Scroll to zoom · Drag to pan
        </div>
      </div>
    </Card>
  );
}

function useState<T>(initial: T): [T, React.Dispatch<React.SetStateAction<T>>] {
  const [state, setState] = React.useState<T>(initial);
  return [state, setState];
}
```

Wait — the `useState` at the bottom is wrong. Let me fix that — I should import it from React at the top. Let me rewrite properly.

- [ ] **Step 2 (corrected): Create PaperGraph component**

```tsx
import React, { useEffect, useRef, useState } from "react";
import Card from "./Card";
import LoadingSkeleton from "./LoadingSkeleton";
import EmptyState from "./EmptyState";
import * as d3 from "d3";

interface GraphNode {
  id: number;
  label: string;
  group: string;
  size: number;
}

interface GraphLink {
  source: number;
  target: number;
  weight: number;
}

interface PaperGraphProps {
  nodes: GraphNode[];
  links: GraphLink[];
  loading: boolean;
  error: string | null;
  onSelect: (id: number) => void;
  selectedId: number | null;
}

const GROUP_COLORS: Record<string, string> = {
  arxiv: "#1976d2",
  semantic_scholar: "#4caf50",
  unknown: "#999",
};

export default function PaperGraph({ nodes, links, loading, error, onSelect, selectedId }: PaperGraphProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 500, height: 400 });
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null);

  // Track dimensions on resize
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver(entries => {
      for (const entry of entries) {
        const { width } = entry.contentRect;
        setDimensions({ width: Math.max(300, width), height: Math.max(300, Math.min(500, width * 0.7)) });
      }
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // Draw graph
  useEffect(() => {
    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();
    if (nodes.length === 0) return;

    const { width, height } = dimensions;
    const color = (d: GraphNode) => GROUP_COLORS[d.group] || GROUP_COLORS.unknown;

    const g = svg.append("g");
    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.3, 3])
      .on("zoom", (event) => { g.attr("transform", event.transform); });
    svg.call(zoom);

    const simulation = d3.forceSimulation<GraphNode>(nodes)
      .force("link", d3.forceLink<GraphNode, GraphLink>(links)
        .id(d => d.id)
        .distance(d => 150 - d.weight * 20)
        .strength(0.3))
      .force("charge", d3.forceManyBody().strength(-200))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collision", d3.forceCollide().radius(d => d.size * 0.5 + 10));

    const link = g.append("g").selectAll("line").data(links).join("line")
      .attr("stroke", "#ccc")
      .attr("stroke-width", d => Math.max(1, d.weight))
      .attr("stroke-opacity", 0.6);

    const node = g.append("g").selectAll("circle").data(nodes).join("circle")
      .attr("r", d => Math.max(5, Math.min(d.size * 0.5 + 5, 30)))
      .attr("fill", d => color(d))
      .attr("stroke", d => d.id === selectedId ? "#fff" : "none")
      .attr("stroke-width", d => d.id === selectedId ? 3 : 0)
      .attr("cursor", "pointer")
      .on("click", (_event, d) => onSelect(d.id))
      .on("mouseenter", (_event, d) => setHoveredNode(d))
      .on("mouseleave", () => setHoveredNode(null))
      // @ts-expect-error d3 drag types
      .call(d3.drag<SVGCircleElement, GraphNode>()
        .on("start", (event, d) => {
          if (!event.active) simulation.alphaTarget(0.3).restart();
          d.fx = d.x; d.fy = d.y;
        })
        .on("drag", (event, d) => { d.fx = event.x; d.fy = event.y; })
        .on("end", (event, d) => {
          if (!event.active) simulation.alphaTarget(0);
          d.fx = null; d.fy = null;
        }));

    const label = g.append("g").selectAll("text").data(nodes).join("text")
      .text(d => d.label.length > 20 ? d.label.slice(0, 18) + "…" : d.label)
      .attr("font-size", "10px")
      .attr("dx", d => Math.max(5, Math.min(d.size * 0.5 + 5, 30)) + 3)
      .attr("dy", "0.35em")
      .attr("fill", "var(--color-text-secondary)")
      .attr("pointer-events", "none");

    simulation.on("tick", () => {
      link
        .attr("x1", d => (d.source as any).x)
        .attr("y1", d => (d.source as any).y)
        .attr("x2", d => (d.target as any).x)
        .attr("y2", d => (d.target as any).y);
      node.attr("cx", d => d.x!).attr("cy", d => d.y!);
      label.attr("x", d => d.x!).attr("y", d => d.y!);
    });

    return () => { simulation.stop(); };
  }, [nodes, links, dimensions, selectedId, onSelect]);

  if (loading) {
    return <LoadingSkeleton variant="card" lines={5} />;
  }

  if (error) {
    return (
      <Card title="Citation Network" borderColor="var(--color-danger)">
        <p style={{ color: "var(--color-danger)" }}>Failed to load graph: {error}</p>
      </Card>
    );
  }

  if (nodes.length === 0) {
    return (
      <EmptyState icon="🔗" title="No Graph Data" description="Papers will appear here as a citation network once retrieved." />
    );
  }

  return (
    <Card title="Citation Network">
      <div ref={containerRef} style={{ position: "relative", width: "100%" }}>
        <svg
          ref={svgRef}
          width={dimensions.width}
          height={dimensions.height}
          style={{ display: "block", background: "#fafafa", borderRadius: "var(--radius-md)" }}
        />
        {hoveredNode && (
          <div style={{
            position: "absolute", bottom: "var(--space-sm)", left: "var(--space-sm)",
            background: "rgba(0,0,0,0.8)", color: "#fff",
            padding: "var(--space-xs) var(--space-sm)", borderRadius: "var(--radius-sm)",
            fontSize: "var(--font-size-xs)", maxWidth: "80%", pointerEvents: "none",
          }}>
            {hoveredNode.label}
            <span style={{ opacity: 0.7 }}> — {hoveredNode.group}</span>
          </div>
        )}
        <div style={{
          position: "absolute", top: "var(--space-sm)", right: "var(--space-sm)",
          background: "rgba(255,255,255,0.9)", padding: "var(--space-xs) var(--space-sm)",
          borderRadius: "var(--radius-sm)", fontSize: "var(--font-size-xs)",
          display: "flex", flexDirection: "column", gap: "0.15rem",
        }}>
          {Object.entries(GROUP_COLORS).map(([key, color]) => (
            <div key={key} style={{ display: "flex", alignItems: "center", gap: "0.3rem" }}>
              <span style={{ width: 8, height: 8, borderRadius: "50%", background: color, display: "inline-block" }} />
              {key === "semantic_scholar" ? "Semantic Scholar" : key.charAt(0).toUpperCase() + key.slice(1)}
            </div>
          ))}
        </div>
        <div style={{
          position: "absolute", bottom: "var(--space-sm)", right: "var(--space-sm)",
          color: "var(--color-text-disabled)", fontSize: "var(--font-size-xs)",
        }}>
          Scroll to zoom · Drag to pan
        </div>
      </div>
    </Card>
  );
}
```

- [ ] **Step 3: Verify the build**

Run: `cd web && npx tsc --noEmit 2>&1`
Expected: No type errors

- [ ] **Step 4: Commit**

```bash
git add web/package.json web/package-lock.json web/src/components/PaperGraph.tsx
git commit -m "feat: add PaperGraph D3.js force-directed citation graph"
```

---

### Task 4: PaperDetail Component

**Files:**
- Create: `web/src/components/PaperDetail.tsx`

**Interfaces:**
- Consumes: `<PaperDetail paper={PaperItem | null} loading={boolean} error={string | null} onClose={() => void} />`
- Produces: Paper detail panel showing full metadata for a selected paper

- [ ] **Step 1: Create PaperDetail component**

```tsx
import React from "react";
import Card from "./Card";
import Badge from "./Badge";
import LoadingSkeleton from "./LoadingSkeleton";
import EmptyState from "./EmptyState";

interface PaperItem {
  title: string;
  authors: string;
  year: string;
  citations: number;
  source: string;
  paper_index: number;
}

interface PaperDetailProps {
  paper: PaperItem | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
}

const SOURCE_BADGE_COLOR: Record<string, "blue" | "green" | "gray"> = {
  arxiv: "blue",
  semantic_scholar: "green",
};

export default function PaperDetail({ paper, loading, error, onClose }: PaperDetailProps) {
  if (loading) {
    return (
      <Card title="Paper Details" headerRight={
        <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", fontSize: "1.2rem", color: "var(--color-text-disabled)" }}>×</button>
      }>
        <LoadingSkeleton variant="card" lines={6} />
      </Card>
    );
  }

  if (error) {
    return (
      <Card title="Paper Details" borderColor="var(--color-danger)" headerRight={
        <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", fontSize: "1.2rem", color: "var(--color-text-disabled)" }}>×</button>
      }>
        <p style={{ color: "var(--color-danger)" }}>Error: {error}</p>
      </Card>
    );
  }

  if (!paper) {
    return (
      <Card title="Paper Details">
        <EmptyState icon="📖" title="No Paper Selected" description="Click a paper in the table or graph to see its details." />
      </Card>
    );
  }

  const sourceColor = SOURCE_BADGE_COLOR[paper.source] || "gray";

  return (
    <Card
      title="Paper Details"
      headerRight={
        <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", fontSize: "1.2rem", color: "var(--color-text-disabled)" }}>
          ×
        </button>
      }
      borderColor="var(--color-primary)"
    >
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-md)" }}>
        {/* Title */}
        <div>
          <h4 style={{ margin: "0 0 var(--space-xs)", fontSize: "var(--font-size-md)", color: "var(--color-text-primary)", lineHeight: 1.4 }}>
            {paper.title}
          </h4>
        </div>

        {/* Metadata grid */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-sm)" }}>
          <div>
            <div style={{ fontSize: "var(--font-size-xs)", color: "var(--color-text-disabled)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "0.15rem" }}>Authors</div>
            <div style={{ fontSize: "var(--font-size-sm)", color: "var(--color-text-primary)" }}>{paper.authors}</div>
          </div>
          <div>
            <div style={{ fontSize: "var(--font-size-xs)", color: "var(--color-text-disabled)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "0.15rem" }}>Year</div>
            <div style={{ fontSize: "var(--font-size-sm)", color: "var(--color-text-primary)" }}>{paper.year || "—"}</div>
          </div>
          <div>
            <div style={{ fontSize: "var(--font-size-xs)", color: "var(--color-text-disabled)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "0.15rem" }}>Citations</div>
            <div style={{ fontSize: "var(--font-size-sm)", color: "var(--color-text-primary)", fontWeight: "var(--font-weight-semibold)" }}>{paper.citations}</div>
          </div>
          <div>
            <div style={{ fontSize: "var(--font-size-xs)", color: "var(--color-text-disabled)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "0.15rem" }}>Source</div>
            <Badge color={sourceColor}>{paper.source}</Badge>
          </div>
        </div>

        {/* Index reference */}
        {paper.paper_index != null && (
          <div style={{ fontSize: "var(--font-size-xs)", color: "var(--color-text-disabled)" }}>
            Paper #{paper.paper_index + 1} of the retrieved set
          </div>
        )}
      </div>
    </Card>
  );
}
```

- [ ] **Step 2: Verify the build**

Run: `cd web && npx tsc --noEmit 2>&1`
Expected: No type errors

- [ ] **Step 3: Commit**

```bash
git add web/src/components/PaperDetail.tsx
git commit -m "feat: add PaperDetail component with metadata display"
```

---

### Task 5: KnowledgeExplorer Page Integration

**Files:**
- Modify: `web/src/pages/KnowledgeExplorer.tsx` (full rewrite to three-column layout)
- Modify: `web/src/api/client.ts` (already done in Task 2 — verify imports)

**Interfaces:**
- Consumes: `PaperTable`, `PaperGraph`, `PaperDetail` components, `getPapers()`, `getPaperGraph()`, `getPaperDetail()` from API client
- Produces: Integrated Knowledge Explorer page with three-column layout

- [ ] **Step 1: Rewrite KnowledgeExplorer.tsx**

```tsx
import React, { useEffect, useState, useCallback } from "react";
import { getPapers, getPaperGraph, getPaperDetail, PaperItem, GraphNode, GraphLink } from "../api/client";
import PaperTable from "../components/PaperTable";
import PaperGraph from "../components/PaperGraph";
import PaperDetail from "../components/PaperDetail";
import Card from "../components/Card";
import Badge from "../components/Badge";

export default function KnowledgeExplorer() {
  // Papers state
  const [papers, setPapers] = useState<PaperItem[]>([]);
  const [papersLoading, setPapersLoading] = useState(true);
  const [papersError, setPapersError] = useState<string | null>(null);

  // Graph state
  const [graphNodes, setGraphNodes] = useState<GraphNode[]>([]);
  const [graphLinks, setGraphLinks] = useState<GraphLink[]>([]);
  const [graphLoading, setGraphLoading] = useState(true);
  const [graphError, setGraphError] = useState<string | null>(null);

  // Selection state
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [detailPaper, setDetailPaper] = useState<PaperItem | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  // Initial load
  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const [paperResp, graphResp] = await Promise.all([
          getPapers(),
          getPaperGraph(),
        ]);
        if (cancelled) return;
        setPapers(paperResp.papers);
        setPapersLoading(false);
        setGraphNodes(graphResp.nodes);
        setGraphLinks(graphResp.links);
        setGraphLoading(false);
      } catch (err) {
        if (cancelled) return;
        setPapersError("Failed to load papers");
        setPapersLoading(false);
        setGraphError("Failed to load graph");
        setGraphLoading(false);
      }
    }

    load();
    return () => { cancelled = true; };
  }, []);

  // Handle paper selection
  const handleSelect = useCallback(async (index: number) => {
    setSelectedIndex(index);
    setDetailLoading(true);
    setDetailError(null);
    try {
      const paper = await getPaperDetail(index);
      setDetailPaper(paper);
    } catch {
      setDetailError("Failed to load paper details");
      setDetailPaper(null);
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const handleCloseDetail = useCallback(() => {
    setSelectedIndex(null);
    setDetailPaper(null);
    setDetailError(null);
  }, []);

  return (
    <div>
      <h2>Knowledge Explorer</h2>
      <p style={{ color: "var(--color-text-secondary)", marginBottom: "var(--space-lg)", fontSize: "var(--font-size-sm)" }}>
        Browse retrieved papers, explore the citation network, and view paper metadata.
      </p>

      {/* Summary bar */}
      {!papersLoading && papers.length > 0 && (
        <div style={{ display: "flex", gap: "var(--space-md)", marginBottom: "var(--space-lg)" }}>
          <Card padding="var(--space-sm) var(--space-md)" style={{ flex: 1, textAlign: "center" }}>
            <div style={{ fontSize: "var(--font-size-xl)", fontWeight: "var(--font-weight-bold)", color: "var(--color-primary)" }}>{papers.length}</div>
            <div style={{ fontSize: "var(--font-size-xs)", color: "var(--color-text-secondary)" }}>Papers</div>
          </Card>
          <Card padding="var(--space-sm) var(--space-md)" style={{ flex: 1, textAlign: "center" }}>
            <div style={{ fontSize: "var(--font-size-xl)", fontWeight: "var(--font-weight-bold)", color: "var(--color-success)" }}>{graphNodes.length}</div>
            <div style={{ fontSize: "var(--font-size-xs)", color: "var(--color-text-secondary)" }}>Graph Nodes</div>
          </Card>
          <Card padding="var(--space-sm) var(--space-md)" style={{ flex: 1, textAlign: "center" }}>
            <div style={{ fontSize: "var(--font-size-xl)", fontWeight: "var(--font-weight-bold)", color: "var(--color-warning)" }}>{graphLinks.length}</div>
            <div style={{ fontSize: "var(--font-size-xs)", color: "var(--color-text-secondary)" }}>Connections</div>
          </Card>
        </div>
      )}

      {/* Three-column layout */}
      <div style={{ display: "grid", gridTemplateColumns: "2fr 2fr 1.5fr", gap: "var(--space-lg)", alignItems: "start" }}>
        {/* Left: Paper Table */}
        <PaperTable
          papers={papers}
          loading={papersLoading}
          error={papersError}
          onSelect={handleSelect}
          selectedIndex={selectedIndex}
        />

        {/* Center: Citation Graph */}
        <PaperGraph
          nodes={graphNodes}
          links={graphLinks}
          loading={graphLoading}
          error={graphError}
          onSelect={handleSelect}
          selectedId={selectedIndex}
        />

        {/* Right: Paper Detail */}
        <PaperDetail
          paper={detailPaper}
          loading={detailLoading}
          error={detailError}
          onClose={handleCloseDetail}
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify the build**

Run: `cd web && npx tsc --noEmit 2>&1`
Expected: No type errors

- [ ] **Step 3: Verify the dev server starts**

Run: `cd web && npx vite build 2>&1 | tail -10`
Expected: Build succeeds with no errors

- [ ] **Step 4: Commit**

```bash
git add web/src/pages/KnowledgeExplorer.tsx
git commit -m "feat: integrate Knowledge Explorer with three-column layout"
```

---

### Task 6: CSV Export for Papers (Bonus)

**Files:**
- Modify: `web/src/pages/KnowledgeExplorer.tsx` (add CSV export button)
- Modify: `api/routes/survey.py` (add CSV export endpoint)

**Interfaces:**
- Consumes: `GET /api/survey/papers/export` → CSV file download
- Produces: CSV download button in the Knowledge Explorer header

- [ ] **Step 1: Add CSV export endpoint to api/routes/survey.py**

```python
@router.get("/papers/export")
async def export_papers_csv(harness: Harness = Depends(get_harness)):
    """Export papers as a CSV file (UTF-8 with BOM for Excel compatibility)."""
    import csv, io
    from fastapi.responses import StreamingResponse

    info = harness.get_task_info()
    papers_data = info.get("execution_details", {}).get("papers", {})
    raw_list = papers_data.get("list", [])

    output = io.StringIO()
    output.write("﻿")  # BOM for Excel
    writer = csv.writer(output)
    writer.writerow(["Title", "Authors", "Year", "Citations", "Source"])

    for p in raw_list:
        writer.writerow([
            p.get("title", ""),
            p.get("authors", ""),
            p.get("year", ""),
            p.get("citations", 0),
            p.get("source", ""),
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=papers.csv"},
    )
```

- [ ] **Step 2: Add CSV export button test to tests/test_api.py**

```python
@pytest.mark.asyncio
async def test_export_papers_csv(client, test_harness):
    """Returns CSV file with paper data."""
    test_harness._papers = [
        {"title": "Paper One", "authors": ["Alice"], "year": "2023", "citation_count": 10, "arxiv_id": "2301.001"},
    ]
    response = await client.get("/api/survey/papers/export")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv"
    body = response.text
    assert "Title" in body
    assert "Paper One" in body
    assert "Alice" in body
```

- [ ] **Step 3: Add CSV download button to KnowledgeExplorer.tsx**

Add after the `<h2>` in the KnowledgeExplorer component:

```tsx
import Button from "../components/Button";

// Add inside the component, after the summary bar:
<div style={{ display: "flex", justifyContent: "flex-end", marginBottom: "var(--space-md)" }}>
  {papers.length > 0 && (
    <Button onClick={() => window.open("/api/survey/papers/export", "_blank")}>
      ⬇ Export CSV
    </Button>
  )}
</div>
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_api.py -v -k "csv" 2>&1`
Expected: PASS

- [ ] **Step 5: Verify build**

Run: `cd web && npx tsc --noEmit 2>&1`
Expected: No type errors

- [ ] **Step 6: Commit**

```bash
git add api/routes/survey.py tests/test_api.py web/src/pages/KnowledgeExplorer.tsx
git commit -m "feat: add CSV export for papers"
```