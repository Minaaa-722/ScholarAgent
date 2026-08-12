import React, { useEffect, useState, useRef } from "react";
import { getPaper, getSurveyStatus, restartSurvey } from "../api/client";
import Card from "../components/Card";
import Button from "../components/Button";
import Badge from "../components/Badge";
import LoadingSkeleton from "../components/LoadingSkeleton";
import EmptyState from "../components/EmptyState";
import { useToast } from "../components/Toast";

interface PaperResult {
  status?: string;
  paper?: string;
  rounds?: number;
  retry_count?: number;
  has_warnings?: boolean;
  error?: string;
  task?: {
    topic: string;
    keywords: string[];
    goal: string;
  };
  execution_log?: Array<{
    stage: string;
    timestamp: string;
    [key: string]: unknown;
  }>;
  latex_repair_log?: {
    change_count: number;
    summary: string;
    entries: Array<{ rule: string; location: string; original: string; replacement: string }>;
  };
}

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

export default function FinalReview() {
  const [result, setResult] = useState<PaperResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [taskInfo, setTaskInfo] = useState<any>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [restarting, setRestarting] = useState(false);
  const [restartError, setRestartError] = useState<string | null>(null);

  // Section expand state
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set());
  const [allExpanded, setAllExpanded] = useState(false);

  const { showToast } = useToast();

  const handleRestart = async () => {
    setRestarting(true);
    setRestartError(null);
    try {
      await restartSurvey();
      setResult(null);
      setLoading(true);
      const [paperData, statusData] = await Promise.all([getPaper(), getSurveyStatus()]);
      setResult(paperData);
      setTaskInfo(statusData);
      setLoading(false);
    } catch {
      setRestartError("重启失败，请稍后重试");
    } finally {
      setRestarting(false);
    }
  };

  const fetchData = async () => {
    try {
      const [paperData, statusData] = await Promise.all([getPaper(), getSurveyStatus()]);
      setResult(paperData);
      setTaskInfo(statusData);
      setLoading(false);

      if (paperData?.paper && !statusData?.pipeline_running) {
        if (timerRef.current) {
          clearInterval(timerRef.current);
          timerRef.current = null;
        }
      }
    } catch { /* ignore */ }
  };

  useEffect(() => {
    fetchData();
    timerRef.current = setInterval(fetchData, 3000);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  const handleExportBibtex = async () => {
    try {
      const statusData = await getSurveyStatus();
      const papers = statusData?.execution_details?.papers?.list || [];
      const bibtexEntries = papers.map((p: any) => {
        const key = ((p.title || "paper").split(" ")[0].toLowerCase() + (p.year || 2024)).replace(/[^a-z0-9]/g, "");
        const authors = p.authors || "Unknown";
        return `@article{${key},\n  title={${p.title}},\n  author={${authors}},\n  year={${p.year || 2024}},\n}`;
      });
      const bibContent = bibtexEntries.join("\n\n");
      const blob = new Blob([bibContent], { type: "text/plain;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `references_${(result?.task?.topic || "paper").replace(/\s+/g, "_")}.bib`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      showToast("error", "BibTeX export failed");
    }
  };

  const sections = result?.paper ? extractSections(result.paper) : [];

  const toggleSection = (title: string) => {
    setExpandedSections(prev => {
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
      setExpandedSections(new Set(sections.map(s => s.title)));
    }
    setAllExpanded(!allExpanded);
  };

  if (loading) {
    return (
      <div>
        <h2 className="page-title">Final Review</h2>
        <LoadingSkeleton variant="card" lines={5} />
      </div>
    );
  }

  if (!result || !result.paper) {
    const topic = taskInfo?.topic;
    return (
      <div>
        <h2 className="page-title">Final Review</h2>
        {topic ? (
          <div>
            <Card borderColor="var(--color-warning)">
              <p style={{ color: "var(--color-warning-dark)" }}>
                The pipeline for <strong>"{topic}"</strong> is still running or has not produced a paper yet.
                {taskInfo?.pipeline_running ? " Auto-refreshing…" : ""}
              </p>
            </Card>
            {taskInfo?.pipeline_running && (
              <p className="text-secondary" style={{ textAlign: "center", marginTop: "1rem" }}>
                Current stage: <strong>{taskInfo.current_stage}</strong> — {taskInfo.current_message}
              </p>
            )}
          </div>
        ) : (
          <EmptyState icon="📝" title="No Research Task" description="No research task has been started yet." />
        )}
      </div>
    );
  }

  if (result.status === "error") {
    return (
      <div>
        <h2 className="page-title">Final Review</h2>
        <Card borderColor="var(--color-danger)" title="Pipeline Error">
          <p style={{ color: "var(--color-danger-dark)" }}>{result.error}</p>
          <div style={{ display: "flex", gap: "1rem", alignItems: "center", marginTop: "1rem" }}>
            <Button variant="danger" onClick={handleRestart} loading={restarting} size="lg">
              🔄 一键重启
            </Button>
            {restartError && <span style={{ color: "var(--color-danger-dark)", fontSize: "var(--font-size-sm)" }}>{restartError}</span>}
          </div>
        </Card>
      </div>
    );
  }

  // Compute quality scores from execution log
  const validationEntries = (result.execution_log || []).filter(e => e.stage === "VALIDATION");
  const latestValidation = validationEntries[validationEntries.length - 1];
  const qualityScore = latestValidation?.score as number | undefined;
  const qualityPassed = latestValidation?.passed as boolean | undefined;
  const qualityScorePercent = qualityScore != null ? Math.round(qualityScore * 100) : undefined;

  return (
    <div>
      <h2 className="page-title">Final Review</h2>

      {/* Summary banner */}
      <Card borderColor={result.has_warnings ? "var(--color-warning)" : "var(--color-success)"}
        title={
          <span style={{ fontWeight: 600 }}>
            Status: {result.status === "complete" ? "Completed" : result.status}
            {result.has_warnings && " (with warnings)"}
          </span>
        }
        headerRight={
          <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
            {qualityScorePercent != null && (
              <Badge color={qualityPassed ? "green" : qualityScorePercent >= 70 ? "orange" : "red"} dot>
                Quality: {qualityScorePercent}%
              </Badge>
            )}
            <Badge color="gray">Rounds: {result.rounds ?? "—"}</Badge>
            <Badge color="gray">Retries: {result.retry_count ?? "—"}</Badge>
          </div>
        }
      >
        <p className="text-secondary" style={{ fontSize: "var(--font-size-sm)" }}>
          Paper length: {(result.paper.length / 1000).toFixed(1)}k chars
          {result.latex_repair_log && ` | LaTeX repairs: ${result.latex_repair_log.change_count}`}
        </p>
      </Card>

      {/* Quality score detail */}
      {latestValidation && (
        <Card title="✅ 质量评估" borderColor={qualityPassed ? "var(--color-success)" : "var(--color-warning)"}>
          <div style={{ display: "flex", gap: "1rem", alignItems: "center", marginBottom: "0.5rem" }}>
            <span style={{ fontWeight: 600 }}>综合评分: </span>
            <Badge color={qualityPassed ? "green" : qualityScorePercent && qualityScorePercent >= 70 ? "orange" : "red"}>
              {qualityScorePercent}%
            </Badge>
            {qualityPassed ? (
              <span style={{ color: "var(--color-success-dark)", fontSize: "var(--font-size-sm)" }}>✓ 所有检查通过</span>
            ) : (
              <span style={{ color: "var(--color-warning-dark)", fontSize: "var(--font-size-sm)" }}>⚠ 部分检查需改进</span>
            )}
          </div>
          {result.execution_log?.filter(e => e.stage === "VALIDATION" && e.failures).map((entry, i) => {
            const failures = (entry as any).failures as string[] | undefined;
            return failures && failures.length > 0 ? (
              <p key={i} className="text-secondary" style={{ fontSize: "var(--font-size-sm)" }}>
                需改进: {failures.join(", ")}
              </p>
            ) : null;
          })}
        </Card>
      )}

      {/* Section-by-section paper viewer */}
      {sections.length > 0 && (
        <Card
          title="📑 论文章节"
          headerRight={
            <Button variant="ghost" size="sm" onClick={toggleAll}>
              {allExpanded ? "Collapse All" : "Expand All"}
            </Button>
          }
        >
          {sections.map(s => (
            <div key={s.title} style={{ marginBottom: "0.5rem" }}>
              <div
                onClick={() => toggleSection(s.title)}
                style={{
                  padding: "0.6rem 0.8rem", borderRadius: "var(--radius-md)",
                  background: expandedSections.has(s.title) ? "var(--color-primary-light)" : "var(--color-bg-card)",
                  border: "1px solid var(--color-border-light)",
                  cursor: "pointer", fontWeight: 600, fontSize: "var(--font-size-sm)",
                  display: "flex", justifyContent: "space-between", alignItems: "center",
                  transition: "all var(--transition-fast)",
                }}
              >
                <span>{expandedSections.has(s.title) ? "▼" : "▶"} {s.title}</span>
                <Badge color="gray">{(s.content.length / 100).toFixed(0)}00 chars</Badge>
              </div>
              {expandedSections.has(s.title) && (
                <div style={{
                  padding: "0.8rem", marginTop: "0.3rem", borderRadius: "var(--radius-md)",
                  background: "var(--color-bg-card)", border: "1px solid var(--color-border-light)",
                  fontFamily: "'Times New Roman', Times, serif",
                  fontSize: "var(--font-size-sm)", lineHeight: 1.6, whiteSpace: "pre-wrap",
                  maxHeight: 400, overflowY: "auto",
                }}>
                  {s.content}
                </div>
              )}
            </div>
          ))}
        </Card>
      )}

      {/* Full paper view (as fallback) */}
      {sections.length === 0 && result.paper && (
        <Card title="📄 论文全文">
          <div style={{
            fontFamily: "'Times New Roman', Times, serif",
            lineHeight: 1.6, fontSize: "var(--font-size-sm)", whiteSpace: "pre-wrap",
            overflowX: "auto", maxHeight: 600, overflowY: "auto",
          }}>
            {result.paper}
          </div>
        </Card>
      )}

      {/* Export buttons */}
      <div style={{ display: "flex", gap: "1rem", marginTop: "1rem" }}>
        <Button
          onClick={() => {
            const blob = new Blob([result.paper || ""], { type: "text/plain;charset=utf-8" });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `survey_${(result.task?.topic || "paper").replace(/\s+/g, "_")}.tex`;
            a.click();
            URL.revokeObjectURL(url);
          }}
          icon="📥"
        >
          Download .tex
        </Button>
        <Button variant="ghost" onClick={handleExportBibtex} icon="📚">
          Export BibTeX
        </Button>
      </div>
    </div>
  );
}