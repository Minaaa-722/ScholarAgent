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

const CLOSE_BTN_STYLE: React.CSSProperties = {
  background: "none", border: "none", cursor: "pointer",
  fontSize: "1.3rem", color: "var(--color-text-tertiary)",
  padding: "0.2rem", lineHeight: 1, borderRadius: "var(--radius-sm)",
  transition: "color var(--transition-fast)",
};

export default function PaperDetail({ paper, loading, error, onClose }: PaperDetailProps) {
  if (loading) {
    return (
      <Card title="Paper Details" headerRight={
        <button onClick={onClose} style={CLOSE_BTN_STYLE}>×</button>
      }>
        <LoadingSkeleton variant="card" lines={6} />
      </Card>
    );
  }

  if (error) {
    return (
      <Card title="Paper Details" borderColor="var(--color-danger)" headerRight={
        <button onClick={onClose} style={CLOSE_BTN_STYLE}>×</button>
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
        <button onClick={onClose} style={CLOSE_BTN_STYLE}>×</button>
      }
      borderColor="var(--color-primary)"
    >
      <div className="flex flex-col" style={{ gap: "var(--space-md)" }}>
        <div>
          <h4 style={{ margin: "0 0 var(--space-xs)", fontSize: "var(--font-size-md)", lineHeight: 1.4 }}>
            {paper.title}
          </h4>
        </div>

        <div className="grid-2" style={{ gap: "var(--space-sm)" }}>
          <div>
            <div className="text-tertiary" style={{ fontSize: "var(--font-size-xs)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "0.15rem" }}>Authors</div>
            <div style={{ fontSize: "var(--font-size-sm)" }}>{paper.authors}</div>
          </div>
          <div>
            <div className="text-tertiary" style={{ fontSize: "var(--font-size-xs)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "0.15rem" }}>Year</div>
            <div style={{ fontSize: "var(--font-size-sm)" }}>{paper.year || "—"}</div>
          </div>
          <div>
            <div className="text-tertiary" style={{ fontSize: "var(--font-size-xs)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "0.15rem" }}>Citations</div>
            <div style={{ fontSize: "var(--font-size-sm)", fontWeight: "var(--font-weight-semibold)" }}>{paper.citations}</div>
          </div>
          <div>
            <div className="text-tertiary" style={{ fontSize: "var(--font-size-xs)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "0.15rem" }}>Source</div>
            <Badge color={sourceColor}>{paper.source}</Badge>
          </div>
        </div>

        {paper.paper_index != null && (
          <div className="text-tertiary" style={{ fontSize: "var(--font-size-xs)" }}>
            Paper #{paper.paper_index + 1} of the retrieved set
          </div>
        )}
      </div>
    </Card>
  );
}