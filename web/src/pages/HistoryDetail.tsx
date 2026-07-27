import React, { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { getHistoryDetail } from "../api/client";
import type { HistoryDetail as HistoryDetailType } from "../api/client";
import Card from "../components/Card";
import Button from "../components/Button";
import Badge from "../components/Badge";
import LoadingSkeleton from "../components/LoadingSkeleton";

function extractSections(tex: string): { title: string; content: string }[] {
  const sections: { title: string; content: string }[] = [];
  const lines = tex.split("\n");
  let currentTitle = "Preamble";
  let currentContent: string[] = [];
  for (const line of lines) {
    const match = line.match(/\\(?:sub)*section\{([^}]+)\}/);
    if (match) {
      if (currentContent.length > 0) {
        sections.push({ title: currentTitle, content: currentContent.join("\n") });
      }
      currentTitle = match[1];
      currentContent = [line];
    } else {
      currentContent.push(line);
    }
  }
  if (currentContent.length > 0) {
    sections.push({ title: currentTitle, content: currentContent.join("\n") });
  }
  return sections;
}

export default function HistoryDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [entry, setEntry] = useState<HistoryDetailType | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set());
  const [allExpanded, setAllExpanded] = useState(false);

  useEffect(() => {
    if (!id) {
      setError("No history entry ID provided");
      setLoading(false);
      return;
    }
    getHistoryDetail(id)
      .then((data) => setEntry(data))
      .catch(() => setError("History entry not found"))
      .finally(() => setLoading(false));
  }, [id]);

  const toggleSection = (title: string) => {
    setExpandedSections((prev) => {
      const next = new Set(prev);
      if (next.has(title)) next.delete(title);
      else next.add(title);
      return next;
    });
  };

  const toggleAll = () => {
    if (allExpanded) {
      setExpandedSections(new Set());
    } else {
      setExpandedSections(new Set((sections || []).map((s) => s.title)));
    }
    setAllExpanded(!allExpanded);
  };

  const handleExportTex = () => {
    if (!entry?.final_paper) return;
    const blob = new Blob([entry.final_paper], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `survey_${(entry.topic || "paper").replace(/\s+/g, "_")}.tex`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleExportBibtex = () => {
    if (!entry?.papers?.length) return;
    const bibtexEntries = entry.papers.map((p) => {
      const key = ((p.title || "paper").split(" ")[0].toLowerCase() + (p.year || "2024")).replace(/[^a-z0-9]/g, "");
      return `@article{${key},\n  title={${p.title}},\n  author={${p.authors}},\n  year={${p.year || 2024}},\n}`;
    });
    const bibContent = bibtexEntries.join("\n\n");
    const blob = new Blob([bibContent], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `references_${(entry.topic || "paper").replace(/\s+/g, "_")}.bib`;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (loading) {
    return (
      <div>
        <h2 className="page-title">History Detail</h2>
        <LoadingSkeleton variant="card" lines={5} />
      </div>
    );
  }

  if (error || !entry) {
    return (
      <div>
        <h2 className="page-title">History Detail</h2>
        <Card borderColor="var(--color-danger)">
          <p style={{ color: "var(--color-danger-dark)" }}>{error || "Entry not found"}</p>
          <Button variant="ghost" onClick={() => navigate("/")} style={{ marginTop: "1rem" }}>
            ← Back to Dashboard
          </Button>
        </Card>
      </div>
    );
  }

  const sections = entry.final_paper ? extractSections(entry.final_paper) : [];

  return (
    <div>
      <Button variant="ghost" onClick={() => navigate("/")} style={{ marginBottom: "1rem" }}>
        ← Back to Dashboard
      </Button>

      <h2 className="page-title">{entry.topic}</h2>

      {/* Summary card */}
      <Card
        borderColor={entry.has_warnings ? "var(--color-warning)" : "var(--color-success)"}
        title={
          <span style={{ fontWeight: 600 }}>
            Status: {entry.status === "complete" ? "Completed" : entry.status}
            {entry.has_warnings && " (with warnings)"}
          </span>
        }
        headerRight={
          <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
            <Badge color={entry.has_warnings ? "orange" : "green"} dot>
              {entry.has_warnings ? "Warnings" : "Passed"}
            </Badge>
            <Badge color="gray">Rounds: {entry.rounds}</Badge>
          </div>
        }
      >
        {entry.goal && (
          <p className="text-secondary" style={{ fontSize: "var(--font-size-sm)" }}>
            <strong>Goal:</strong> {entry.goal}
          </p>
        )}
        {entry.keywords.length > 0 && (
          <p className="text-secondary" style={{ fontSize: "var(--font-size-sm)" }}>
            <strong>Keywords:</strong> {entry.keywords.join(", ")}
          </p>
        )}
        <p className="text-secondary" style={{ fontSize: "var(--font-size-sm)" }}>
          <strong>Completed:</strong> {entry.timestamp}
          {" | "}
          <strong>Papers retrieved:</strong> {entry.paper_count}
        </p>
      </Card>

      {/* Paper list */}
      {entry.papers.length > 0 && (
        <Card title="📚 Retrieved Papers">
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "var(--font-size-sm)" }}>
              <thead>
                <tr style={{ borderBottom: "2px solid var(--color-border)" }}>
                  <th style={{ textAlign: "left", padding: "0.5rem" }}>#</th>
                  <th style={{ textAlign: "left", padding: "0.5rem" }}>Title</th>
                  <th style={{ textAlign: "left", padding: "0.5rem" }}>Authors</th>
                  <th style={{ textAlign: "center", padding: "0.5rem" }}>Year</th>
                  <th style={{ textAlign: "center", padding: "0.5rem" }}>Citations</th>
                  <th style={{ textAlign: "center", padding: "0.5rem" }}>Source</th>
                </tr>
              </thead>
              <tbody>
                {entry.papers.map((p, i) => (
                  <tr key={i} style={{ borderBottom: "1px solid var(--color-border-light)" }}>
                    <td style={{ padding: "0.5rem", color: "var(--color-text-tertiary)" }}>{i + 1}</td>
                    <td style={{ padding: "0.5rem", fontWeight: 500 }}>{p.title}</td>
                    <td style={{ padding: "0.5rem" }}>{p.authors}</td>
                    <td style={{ textAlign: "center", padding: "0.5rem" }}>{p.year}</td>
                    <td style={{ textAlign: "center", padding: "0.5rem" }}>{p.citations}</td>
                    <td style={{ textAlign: "center", padding: "0.5rem" }}>
                      <Badge color={p.source === "arxiv" ? "blue" : "gray"}>{p.source}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Final paper section viewer */}
      {sections.length > 0 && (
        <Card
          title="📄 Final Paper"
          headerRight={
            <Button variant="ghost" size="sm" onClick={toggleAll}>
              {allExpanded ? "Collapse All" : "Expand All"}
            </Button>
          }
        >
          {sections.map((s) => (
            <div key={s.title} style={{ marginBottom: "0.5rem" }}>
              <div
                onClick={() => toggleSection(s.title)}
                style={{
                  padding: "0.6rem 0.8rem",
                  borderRadius: "var(--radius-md)",
                  background: expandedSections.has(s.title) ? "var(--color-primary-light)" : "#fafafa",
                  border: "1px solid var(--color-border-light)",
                  cursor: "pointer",
                  fontWeight: 600,
                  fontSize: "var(--font-size-sm)",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  transition: "all var(--transition-fast)",
                }}
              >
                <span>{expandedSections.has(s.title) ? "▼" : "▶"} {s.title}</span>
                <Badge color="gray">{(s.content.length / 100).toFixed(0)}00 chars</Badge>
              </div>
              {expandedSections.has(s.title) && (
                <div
                  style={{
                    padding: "0.8rem",
                    marginTop: "0.3rem",
                    borderRadius: "var(--radius-md)",
                    background: "#fafafa",
                    border: "1px solid var(--color-border-light)",
                    fontFamily: "'Times New Roman', Times, serif",
                    fontSize: "var(--font-size-sm)",
                    lineHeight: 1.6,
                    whiteSpace: "pre-wrap",
                    maxHeight: 400,
                    overflowY: "auto",
                  }}
                >
                  {s.content}
                </div>
              )}
            </div>
          ))}
        </Card>
      )}

      {/* Fallback full paper view */}
      {sections.length === 0 && entry.final_paper && (
        <Card title="📄 Full Paper">
          <div
            style={{
              fontFamily: "'Times New Roman', Times, serif",
              lineHeight: 1.6,
              fontSize: "var(--font-size-sm)",
              whiteSpace: "pre-wrap",
              overflowX: "auto",
              maxHeight: 600,
              overflowY: "auto",
            }}
          >
            {entry.final_paper}
          </div>
        </Card>
      )}

      {/* Export buttons */}
      {entry.final_paper && (
        <div style={{ display: "flex", gap: "1rem", marginTop: "1rem" }}>
          <Button onClick={handleExportTex} icon="📥">
            Download .tex
          </Button>
          <Button variant="ghost" onClick={handleExportBibtex} icon="📚">
            Export BibTeX
          </Button>
        </div>
      )}
    </div>
  );
}