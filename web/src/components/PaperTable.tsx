import React, { useMemo, useState } from "react";
import Card from "./Card";
import Badge from "./Badge";
import EmptyState from "./EmptyState";
import LoadingSkeleton from "./LoadingSkeleton";
import type { PaperItem } from "../api/client";

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
          sorted.map(p => {
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