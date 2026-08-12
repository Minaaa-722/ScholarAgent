import React, { useEffect, useRef } from "react";
import Card from "./Card";

/** Convert simple markdown patterns to readable HTML for display */
function markdownToHtml(text: string | undefined | null): string {
  if (!text) return "";
  // Escape HTML entities first to prevent XSS
  const escapeHtml = (s: string) =>
    s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

  // Process inline formatting within a line
  const renderInline = (s: string): string =>
    escapeHtml(s)
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\*(.+?)\*/g, "<em>$1</em>")
      .replace(/`(.+?)`/g, "<code>$1</code>")
      .replace(/\[(.+?)\]\((.+?)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');

  const lines = text.split("\n");
  const blocks: string[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Code block (```)
    if (/^```/.test(line)) {
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && !/^```/.test(lines[i])) {
        codeLines.push(escapeHtml(lines[i]));
        i++;
      }
      i++; // skip closing ```
      blocks.push(`<pre><code>${codeLines.join("\n")}</code></pre>`);
      continue;
    }

    // Headings
    const headingMatch = line.match(/^(#{1,4})\s+(.+)$/);
    if (headingMatch) {
      const level = headingMatch[1].length;
      const tag = `h${Math.min(level + 1, 5)}` as const;
      blocks.push(`<${tag}>${renderInline(headingMatch[2])}</${tag}>`);
      i++;
      continue;
    }

    // Unordered list
    if (/^[-*]\s/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^[-*]\s/.test(lines[i])) {
        items.push(`<li>${renderInline(lines[i].replace(/^[-*]\s/, ""))}</li>`);
        i++;
      }
      blocks.push(`<ul>${items.join("")}</ul>`);
      continue;
    }

    // Ordered list
    if (/^\d+\.\s/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\d+\.\s/.test(lines[i])) {
        items.push(`<li>${renderInline(lines[i].replace(/^\d+\.\s/, ""))}</li>`);
        i++;
      }
      blocks.push(`<ol>${items.join("")}</ol>`);
      continue;
    }

    // Horizontal rule
    if (/^---+\s*$/.test(line)) {
      blocks.push("<hr/>");
      i++;
      continue;
    }

    // Paragraph (collect blank-line-separated lines)
    if (line.trim() === "") {
      i++;
      continue;
    }

    const paraLines: string[] = [];
    while (i < lines.length && lines[i].trim() !== "" && !/^(#{1,4}\s|```|[-*]\s|\d+\.\s|---+\s*$)/.test(lines[i])) {
      paraLines.push(renderInline(lines[i]));
      i++;
    }
    blocks.push(`<p>${paraLines.join("<br/>")}</p>`);
  }

  return blocks.join("\n");
}

/** Shared style for scrollable card content areas */
const SCROLLABLE_CONTENT_STYLE: React.CSSProperties = {
  maxHeight: "350px",
  overflowY: "auto",
  overflowX: "hidden",
  paddingRight: "8px",
};

export interface PaperInfo {
  title: string;
  authors: string;
  year: string | number;
  citations: number;
  source: string;
  url?: string;       // optional link to the paper
}

export interface SectionInfo {
  level: number;
  title: string;
}

export interface ExecutionDetails {
  plan?: { summary: string; full_text: string; section_count: number };
  search_queries?: string[];
  papers?: { total: number; list: PaperInfo[] };
  analysis?: { summary: string; preview: string };
  sections?: SectionInfo[];
  validation?: Record<string, { score: number; passed: boolean; message: string }>;
}

export interface StageMessage {
  type: "info" | "success" | "warning" | "error";
  message: string;
  timestamp: string;
}

export interface StageMetrics {
  queries_total?: number;
  queries_completed?: number;
  papers_found?: number;
  papers_downloaded?: number;
  papers_total?: number;
  sections_count?: number;
  papers_analyzed?: number;
  total_papers?: number;
  claims_extracted?: number;
  claims_verified?: number;
  benchmark_records?: number;
  round?: number;
  total_rounds?: number;
  word_count?: number;
  citations_injected?: number;
  changes_count?: number;
  validators_passed?: number;
  validators_total?: number;
  overall_score?: number;
}

export interface StageTimelineProps {
  currentStage: string;
  stageOrder: string[];
  stageLabels: Record<string, string>;
  executionDetails: ExecutionDetails | null;
  currentMessage: string;
  pipelineRunning: boolean;
  stageMessages: StageMessage[];
  stageMetrics: StageMetrics;
}

type StageStatus = "completed" | "active" | "pending";

function getStageStatus(
  stage: string,
  currentStage: string,
  stageOrder: string[],
): StageStatus {
  const currentIdx = stageOrder.indexOf(currentStage);
  const stageIdx = stageOrder.indexOf(stage);
  if (currentIdx < 0 || stageIdx < 0) return "pending";
  if (stageIdx < currentIdx) return "completed";
  if (stageIdx === currentIdx) return "active";
  return "pending";
}

/** Check if the execution details contain data for a given stage */
function stageHasData(stage: string, details: ExecutionDetails | null): boolean {
  if (!details) return false;
  switch (stage) {
    case "planning":      return !!details.plan;
    case "retrieval":     return !!(details.search_queries?.length || details.papers);
    case "analysis":      return !!details.analysis;
    case "writing":       return !!(details.sections?.length);
    case "validation":    return !!(details.validation && Object.keys(details.validation).length > 0);
    case "format_repair": return true; // static text, always show
    default:              return false;
  }
}

// ---------------------------------------------------------------------------
// StageArtifact — renders the correct artifact card for each stage
// ---------------------------------------------------------------------------
function StageArtifact({
  stage,
  details,
}: {
  stage: string;
  details: ExecutionDetails | null;
}) {
  if (!details) return null;

  switch (stage) {
    case "planning":
      return details.plan ? (
        <Card title="📋 研究计划">
          <p className="text-secondary mb-sm">
            共 {details.plan.section_count} 个章节/要点
          </p>
          <div
            className="artifact-content"
            style={{
              ...SCROLLABLE_CONTENT_STYLE,
              color: "var(--color-text-secondary)",
              fontSize: "var(--font-size-sm)",
              lineHeight: 1.7,
              margin: 0,
              overflowX: "auto",
            }}
            dangerouslySetInnerHTML={{
              __html: markdownToHtml(details.plan.full_text),
            }}
          />
        </Card>
      ) : (
        <p className="text-disabled" style={{ fontSize: "var(--font-size-sm)" }}>
          暂无计划数据
        </p>
      );

    case "retrieval":
      return (
        <>
          {details.search_queries && details.search_queries.length > 0 && (
            <Card title="🔍 搜索查询">
              <div
                style={{
                  display: "flex",
                  gap: "0.5rem",
                  flexWrap: "wrap",
                }}
              >
                {details.search_queries.map((q, i) => (
                  <span
                    key={i}
                    style={{
                      background: "var(--color-primary-light)",
                      padding: "0.3rem 0.8rem",
                      borderRadius: "var(--radius-full)",
                      fontSize: "var(--font-size-sm)",
                      color: "var(--color-primary-dark)",
                    }}
                  >
                    {q}
                  </span>
                ))}
              </div>
            </Card>
          )}
          {details.papers && (
            <Card
              title={`📄 检索到的论文（共 ${details.papers.total} 篇）`}
            >
              <div style={SCROLLABLE_CONTENT_STYLE}>
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
          {!details.search_queries && !details.papers && (
            <p className="text-disabled" style={{ fontSize: "var(--font-size-sm)" }}>
              暂无检索数据
            </p>
          )}
        </>
      );

    case "analysis":
      return details.analysis ? (
        <Card title="🔬 论文分析">
          <div
            className="artifact-content"
            style={{
              ...SCROLLABLE_CONTENT_STYLE,
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

    case "writing":
      return details.sections && details.sections.length > 0 ? (
        <Card title="📑 论文结构">
          <div style={SCROLLABLE_CONTENT_STYLE}>
            {details.sections.map((s, i) => (
              <div
                key={i}
                style={{
                  padding: "0.3rem 0",
                  paddingLeft: s.level === 0 ? "0" : "1.5rem",
                  fontWeight: s.level === 0 ? 600 : 400,
                  fontSize: "var(--font-size-sm)",
                }}
              >
                {s.level === 0 ? "▸ " : "  ◦ "}
                {s.title}
              </div>
            ))}
          </div>
        </Card>
      ) : (
        <p className="text-disabled" style={{ fontSize: "var(--font-size-sm)" }}>
          暂无章节数据
        </p>
      );

    case "validation":
      return details.validation &&
        Object.keys(details.validation).length > 0 ? (
        <Card title="✅ 质量验证">
          <div style={SCROLLABLE_CONTENT_STYLE}>
            {Object.entries(details.validation).map(([name, v]) => (
            <div
              key={name}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.5rem",
                padding: "0.3rem 0",
                borderBottom: "1px solid var(--color-border-light)",
              }}
            >
              <span
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  background: v.passed
                    ? "var(--color-success)"
                    : "var(--color-danger)",
                  display: "inline-block",
                  flexShrink: 0,
                }}
              />
              <span
                style={{
                  fontWeight: 500,
                  minWidth: 140,
                  fontSize: "var(--font-size-sm)",
                }}
              >
                {name}
              </span>
              <span
                style={{
                  fontSize: "var(--font-size-xs)",
                  padding: "0.1rem 0.4rem",
                  borderRadius: "var(--radius-full)",
                  background: v.passed
                    ? "var(--color-success-light)"
                    : "var(--color-danger-light)",
                  color: v.passed
                    ? "var(--color-success-dark)"
                    : "var(--color-danger-dark)",
                }}
              >
                {v.passed ? "通过" : "需改进"}
              </span>
              {v.message && (
                <span
                  className="text-secondary"
                  style={{
                    fontSize: "var(--font-size-xs)",
                    marginLeft: "0.3rem",
                  }}
                >
                  — {v.message}
                </span>
              )}
            </div>
          ))}
          </div>
        </Card>
      ) : (
        <p className="text-disabled" style={{ fontSize: "var(--font-size-sm)" }}>
          暂无验证数据
        </p>
      );

    case "format_repair":
      return (
        <p className="text-disabled" style={{ fontSize: "var(--font-size-sm)" }}>
          格式修复已完成
        </p>
      );

    default:
      return null;
  }
}

// ---------------------------------------------------------------------------
// StageProgressView — rich progress display for active stages
// ---------------------------------------------------------------------------

const MESSAGE_ICONS: Record<string, string> = {
  info: "⏳",
  success: "✅",
  warning: "⚠️",
  error: "❌",
};

const MESSAGE_COLORS: Record<string, string> = {
  info: "var(--color-primary)",
  success: "var(--color-success)",
  warning: "var(--color-warning)",
  error: "var(--color-danger)",
};

interface MetricBadgeProps {
  label: string;
  value: string;
  color: "blue" | "green" | "orange" | "red";
}

function MetricBadge({ label, value, color }: MetricBadgeProps) {
  const colorMap: Record<string, { bg: string; text: string }> = {
    blue: { bg: "var(--color-primary-light)", text: "var(--color-primary-dark)" },
    green: { bg: "var(--color-success-light)", text: "var(--color-success-dark)" },
    orange: { bg: "var(--color-warning-light)", text: "var(--color-warning-dark)" },
    red: { bg: "var(--color-danger-light)", text: "var(--color-danger-dark)" },
  };
  const c = colorMap[color] || colorMap.blue;
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "0.3rem",
        background: c.bg,
        color: c.text,
        padding: "0.2rem 0.6rem",
        borderRadius: "var(--radius-full)",
        fontSize: "var(--font-size-xs)",
        fontWeight: 500,
      }}
    >
      <strong>{value}</strong>
      <span style={{ opacity: 0.8 }}>{label}</span>
    </span>
  );
}

function MetricProgress({
  label,
  current,
  total,
}: {
  label: string;
  current: number;
  total: number;
}) {
  const pct = Math.min(100, Math.round((current / total) * 100));
  return (
    <div
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "0.4rem",
        background: "var(--color-primary-light)",
        padding: "0.2rem 0.6rem",
        borderRadius: "var(--radius-full)",
        fontSize: "var(--font-size-xs)",
      }}
    >
      <span style={{ color: "var(--color-primary-dark)", fontWeight: 500, whiteSpace: "nowrap" }}>
        {label}: {current}/{total}
      </span>
      <div
        style={{
          width: 60,
          height: 6,
          background: "var(--color-border-light)",
          borderRadius: 3,
          overflow: "hidden",
        }}
      >
        <div
          style={{
            width: `${pct}%`,
            height: "100%",
            background: "var(--color-primary)",
            borderRadius: 3,
            transition: "width 0.3s ease",
          }}
        />
      </div>
    </div>
  );
}

function renderStageMetrics(stage: string, metrics: StageMetrics): React.ReactNode {
  if (!metrics || Object.keys(metrics).length === 0) return null;

  switch (stage) {
    case "retrieval": {
      const { papers_downloaded, papers_total, papers_found } = metrics;
      return (
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginBottom: "0.5rem" }}>
          {papers_found != null && (
            <MetricBadge label="Papers found" value={String(papers_found)} color="blue" />
          )}
          {papers_downloaded != null && papers_total != null && papers_total > 0 && (
            <MetricProgress label="PDFs" current={papers_downloaded} total={papers_total} />
          )}
        </div>
      );
    }
    case "analysis": {
      const { papers_analyzed, total_papers, claims_extracted, claims_verified } = metrics;
      return (
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginBottom: "0.5rem" }}>
          {papers_analyzed != null && total_papers != null && total_papers > 0 && (
            <MetricProgress label="Analyzed" current={papers_analyzed} total={total_papers} />
          )}
          {claims_extracted != null && <MetricBadge label="Claims" value={String(claims_extracted)} color="blue" />}
          {claims_verified != null && <MetricBadge label="Verified" value={String(claims_verified)} color="green" />}
        </div>
      );
    }
    case "writing": {
      const { round, total_rounds, word_count } = metrics;
      return (
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginBottom: "0.5rem" }}>
          {round != null && total_rounds != null && total_rounds > 0 && (
            <MetricProgress label="Round" current={round} total={total_rounds} />
          )}
          {word_count != null && <MetricBadge label="Words" value={String(word_count)} color="blue" />}
        </div>
      );
    }
    case "validation": {
      const { validators_passed, validators_total, overall_score } = metrics;
      return (
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginBottom: "0.5rem" }}>
          {validators_passed != null && validators_total != null && validators_total > 0 && (
            <MetricProgress label="Passed" current={validators_passed} total={validators_total} />
          )}
          {overall_score != null && (
            <MetricBadge
              label="Score"
              value={`${(overall_score * 100).toFixed(0)}%`}
              color={overall_score >= 0.7 ? "green" : "orange"}
            />
          )}
        </div>
      );
    }
    case "planning": {
      const { sections_count } = metrics;
      return sections_count != null ? (
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginBottom: "0.5rem" }}>
          <MetricBadge label="Sections" value={String(sections_count)} color="blue" />
        </div>
      ) : null;
    }
    case "format_repair": {
      const { changes_count } = metrics;
      return changes_count != null ? (
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginBottom: "0.5rem" }}>
          <MetricBadge
            label="Fixes"
            value={String(changes_count)}
            color={changes_count > 0 ? "orange" : "green"}
          />
        </div>
      ) : null;
    }
    default:
      return null;
  }
}

function StageProgressView({
  stage,
  messages,
  metrics,
  currentMessage,
}: {
  stage: string;
  messages: StageMessage[];
  metrics: StageMetrics;
  currentMessage: string;
}) {
  // Auto-scroll to bottom
  const listRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [messages]);

  return (
    <div
      style={{
        background: "var(--color-primary-light)",
        borderRadius: "var(--radius-lg)",
        padding: "1rem",
        borderLeft: "3px solid var(--color-primary)",
      }}
    >
      {/* Metrics card */}
      {renderStageMetrics(stage, metrics)}

      {/* Message list */}
      <div
        ref={listRef}
        style={{
          maxHeight: "240px",
          overflowY: "auto",
          background: "var(--color-bg-card)",
          borderRadius: "var(--radius-md)",
          border: "1px solid var(--color-border-light)",
          padding: "0.5rem",
        }}
      >
        {messages.length === 0 && currentMessage && (
          <div
            style={{
              padding: "0.4rem 0.6rem",
              fontSize: "var(--font-size-sm)",
              color: "var(--color-text-secondary)",
              fontStyle: "italic",
            }}
          >
            {currentMessage}
          </div>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            style={{
              display: "flex",
              alignItems: "flex-start",
              gap: "0.4rem",
              padding: "0.25rem 0.4rem",
              fontSize: "var(--font-size-xs)",
              color: "var(--color-text-secondary)",
              animation: "message-fade-in 0.3s ease-out",
              borderBottom: i < messages.length - 1
                ? "1px solid var(--color-border-light)"
                : "none",
            }}
          >
            <span style={{ flexShrink: 0, fontSize: "0.85rem" }}>
              {MESSAGE_ICONS[m.type] || "•"}
            </span>
            <span style={{ color: MESSAGE_COLORS[m.type] || "inherit" }}>
              {m.message}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// StageEntry — one row in the timeline: dot + connection line + card
// ---------------------------------------------------------------------------
interface StageEntryProps {
  stage: string;
  label: string;
  status: StageStatus;
  isLast: boolean;
  executionDetails: ExecutionDetails | null;
  currentMessage: string;
  pipelineRunning: boolean;
  stageMessages: StageMessage[];
  stageMetrics: StageMetrics;
}

function StageEntry({
  stage,
  label,
  status,
  isLast,
  executionDetails,
  currentMessage,
  pipelineRunning,
  stageMessages,
  stageMetrics,
}: StageEntryProps) {
  const dotColor =
    status === "completed"
      ? "var(--color-success)"
      : status === "active"
        ? "var(--color-primary)"
        : "#ccc";

  const dotIcon =
    status === "completed" ? "✓" : status === "active" ? "▶" : "○";

  const lineColor =
    status === "completed"
      ? "var(--color-success)"
      : status === "active"
        ? "var(--color-primary)"
        : "#e0e0e0";

  return (
    <div
      style={{
        display: "flex",
        marginBottom: isLast ? 0 : "1rem",
        position: "relative",
      }}
    >
      {/* Left column: dot + connection line */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          width: 32,
          flexShrink: 0,
        }}
      >
        <div
          style={{
            width: 28,
            height: 28,
            borderRadius: "50%",
            background: dotColor,
            color: "#fff",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: "var(--font-size-xs)",
            fontWeight: 700,
            zIndex: 1,
            transition: "all 0.3s",
            animation:
              status === "active" && pipelineRunning
                ? "stage-timeline-pulse 1.5s infinite"
                : "none",
          }}
        >
          {dotIcon}
        </div>
        {!isLast && (
          <div
            style={{
              width: 2,
              flex: 1,
              background: lineColor,
              marginTop: 4,
              transition: "background 0.3s",
              minHeight: 16,
            }}
          />
        )}
      </div>

      {/* Right column: stage label + artifact card */}
      <div
        style={{
          flex: 1,
          marginLeft: "0.8rem",
          paddingBottom: isLast ? 0 : "0.5rem",
        }}
      >
        {/* Stage header */}
        <div
          style={{
            fontWeight: status === "active" ? 700 : 500,
            fontSize: "var(--font-size-sm)",
            color:
              status === "completed"
                ? "var(--color-success-dark)"
                : status === "active"
                  ? "var(--color-primary)"
                  : "var(--color-text-disabled)",
            marginBottom:
              status === "completed" || status === "active" ? "0.5rem" : 0,
            transition: "color 0.3s",
          }}
        >
          {label}
        </div>

        {/* Artifact card for completed / active-but-finished stages */}
        {status === "completed" && (
          <StageArtifact stage={stage} details={executionDetails} />
        )}
        {status === "active" && pipelineRunning && (
          stageHasData(stage, executionDetails) ? (
            <StageArtifact stage={stage} details={executionDetails} />
          ) : (
            <StageProgressView
              stage={stage}
              messages={stageMessages}
              metrics={stageMetrics}
              currentMessage={currentMessage}
            />
          )
        )}
        {status === "active" && !pipelineRunning && (
          <StageArtifact stage={stage} details={executionDetails} />
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Pulse keyframes for the active dot
// ---------------------------------------------------------------------------
const PULSE_KEYFRAMES = `
@keyframes stage-timeline-pulse {
  0% { box-shadow: 0 0 0 0 rgba(59, 130, 246, 0.4); }
  70% { box-shadow: 0 0 0 8px rgba(59, 130, 246, 0); }
  100% { box-shadow: 0 0 0 0 rgba(59, 130, 246, 0); }
}
@keyframes message-fade-in {
  from { opacity: 0; transform: translateY(-4px); }
  to { opacity: 1; transform: translateY(0); }
}
`;

if (
  typeof document !== "undefined" &&
  !document.getElementById("stage-timeline-keyframes")
) {
  const style = document.createElement("style");
  style.id = "stage-timeline-keyframes";
  style.textContent = PULSE_KEYFRAMES;
  document.head.appendChild(style);
}

// ---------------------------------------------------------------------------
// StageTimeline — main component
// ---------------------------------------------------------------------------
export default function StageTimeline(props: StageTimelineProps) {
  const {
    currentStage,
    stageOrder,
    stageLabels,
    executionDetails,
    currentMessage,
    pipelineRunning,
    stageMessages,
    stageMetrics,
  } = props;

  // Only show stages up to "retrying" (ignore "complete", "error" — handled by other panels)
  const displayStages = stageOrder.filter(
    (s) => !["complete", "error", "retrying"].includes(s),
  );

  return (
    <div style={{ position: "relative" }}>
      {displayStages.map((stage, index) => {
        const status = getStageStatus(stage, currentStage, stageOrder);
        const label = stageLabels[stage] || stage;
        return (
          <StageEntry
            key={stage}
            stage={stage}
            label={label}
            status={status}
            isLast={index === displayStages.length - 1}
            executionDetails={executionDetails}
            currentMessage={currentMessage}
            pipelineRunning={pipelineRunning}
            stageMessages={stageMessages}
            stageMetrics={stageMetrics}
          />
        );
      })}
    </div>
  );
}