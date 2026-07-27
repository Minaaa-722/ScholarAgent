import React from "react";
import Card from "./Card";
import Badge from "./Badge";
import LoadingSkeleton from "./LoadingSkeleton";
import EmptyState from "./EmptyState";
import type { PaperItem } from "../api/client";

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