import React from "react";
import Card from "./Card";
import LoadingSkeleton from "./LoadingSkeleton";

/** Convert simple markdown patterns to readable HTML for display */
function markdownToHtml(text: string): string {
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
  plan?: { summary: string; preview: string[]; section_count: number };
  search_queries?: string[];
  papers?: { total: number; list: PaperInfo[] };
  analysis?: { summary: string; preview: string };
  sections?: SectionInfo[];
  validation?: Record<string, { score: number; passed: boolean; message: string }>;
}

export interface StageTimelineProps {
  currentStage: string;
  stageOrder: string[];
  stageLabels: Record<string, string>;
  executionDetails: ExecutionDetails | null;
  currentMessage: string;
  pipelineRunning: boolean;
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
}

function StageEntry({
  stage,
  label,
  status,
  isLast,
  executionDetails,
  currentMessage,
  pipelineRunning,
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
            <div
              style={{
                background: "var(--color-primary-light)",
                borderRadius: "var(--radius-lg)",
                padding: "1rem",
                borderLeft: "3px solid var(--color-primary)",
              }}
            >
              <LoadingSkeleton variant="card" />
              {currentMessage && (
                <p
                  style={{
                    margin: "0.5rem 0 0",
                    fontSize: "var(--font-size-sm)",
                    color: "var(--color-text-secondary)",
                    fontStyle: "italic",
                  }}
                >
                  {currentMessage}
                </p>
              )}
            </div>
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
          />
        );
      })}
    </div>
  );
}