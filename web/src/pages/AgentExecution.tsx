import React, { useEffect, useState, useRef } from "react";
import { getSurveyStatus, submitFeedback, restartSurvey, interruptSurvey, resumeSurvey } from "../api/client";
import Button from "../components/Button";
import Card from "../components/Card";
import Badge from "../components/Badge";
import LoadingSkeleton from "../components/LoadingSkeleton";
import ConfirmDialog from "../components/ConfirmDialog";
import { useToast } from "../components/Toast";
import { useWebSocket } from "../hooks/useWebSocket";

const API_BASE = "http://localhost:8000";

interface FeedbackItem {
  id: string;
  category: "supplement_papers" | "expand_section" | "general";
  content: string;
  status: "pending" | "processing" | "applied";
  received_at: string;
}

interface PaperInfo {
  title: string;
  authors: string;
  year: string | number;
  citations: number;
  source: string;
}

interface SectionInfo {
  level: number;
  title: string;
}

interface ExecutionDetails {
  plan?: { summary: string; preview: string[]; section_count: number };
  search_queries?: string[];
  papers?: { total: number; list: PaperInfo[] };
  analysis?: { summary: string; preview: string };
  sections?: SectionInfo[];
  validation?: Record<string, { score: number; passed: boolean; message: string }>;
}

interface ProgressInfo {
  topic: string;
  status: string;
  pipeline_running: boolean;
  current_stage: string;
  current_message: string;
  retry_count: number;
  has_warnings: boolean;
  keywords: string[];
  goal: string;
  task_started_at?: string;
  error?: string;
  pipeline_retry_count?: number;
  last_failed_stage?: string;
  feedback_queue: FeedbackItem[];
  feedback_history: FeedbackItem[];
  execution_details: ExecutionDetails;
}

const STAGE_LABELS: Record<string, string> = {
  starting: "Starting…",
  planning: "Planning Agent",
  retrieval: "Search Agent",
  analysis: "Analysis Agent",
  writing: "Writing Agent",
  validation: "Validation Agent",
  format_repair: "Format Repair",
  retrying: "Retrying…",
  complete: "Complete",
  error: "Error",
};

const STAGE_ORDER = ["starting", "planning", "retrieval", "analysis", "writing", "validation", "format_repair", "retrying", "complete", "error"];

const FEEDBACK_CATEGORIES = [
  { value: "supplement_papers", label: "📄 补充论文", desc: "补充某个子领域的相关论文" },
  { value: "expand_section", label: "📝 展开章节", desc: "要求对某个章节展开详细论述" },
  { value: "general", label: "💬 通用反馈", desc: "其他修改建议" },
];

function getStatusBadgeColor(status: string): "green" | "red" | "orange" | "blue" | "gray" {
  if (status === "COMPLETE") return "green";
  if (status === "ERROR") return "red";
  if (status === "INTERRUPTED") return "orange";
  if (status === "RUNNING") return "blue";
  return "gray";
}

function DetailCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card title={title}>
      {children}
    </Card>
  );
}

export default function AgentExecution() {
  const [progress, setProgress] = useState<ProgressInfo | null>(null);
  const [taskStartedAt, setTaskStartedAt] = useState<string>("");
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Feedback state
  const [feedbackCategory, setFeedbackCategory] = useState<string>("supplement_papers");
  const [feedbackContent, setFeedbackContent] = useState<string>("");
  const [feedbackSending, setFeedbackSending] = useState(false);
  const [feedbackError, setFeedbackError] = useState<string | null>(null);
  const [feedbackHistory, setFeedbackHistory] = useState<FeedbackItem[]>([]);

  // Restart state
  const [restarting, setRestarting] = useState(false);
  const [restartError, setRestartError] = useState<string | null>(null);

  // Interrupt/resume state
  const [interrupting, setInterrupting] = useState(false);
  const [showCancelDialog, setShowCancelDialog] = useState(false);

  const { showToast } = useToast();

  // WebSocket connection via hook
  const { connected } = useWebSocket({
    taskId: "current",
    onMessage: (data: ProgressInfo) => {
      setProgress(data);
      if (data.task_started_at) {
        setTaskStartedAt(data.task_started_at);
      }
      if (data.feedback_history) {
        setFeedbackHistory(data.feedback_history);
      }
    },
  });

  // Poll HTTP status to detect new tasks
  useEffect(() => {
    const checkStatus = async () => {
      try {
        const info = await getSurveyStatus();
        if (info.task_started_at && info.task_started_at !== taskStartedAt) {
          setTaskStartedAt(info.task_started_at);
          setProgress(null);
        }
      } catch { /* ignore */ }
    };
    checkStatus();
    pollTimerRef.current = setInterval(checkStatus, 3000);
    return () => {
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    };
  }, [taskStartedAt]);

  const handleSendFeedback = async () => {
    if (!feedbackContent.trim()) return;
    setFeedbackSending(true);
    setFeedbackError(null);
    try {
      const result = await submitFeedback({
        category: feedbackCategory,
        content: feedbackContent.trim(),
      });
      setFeedbackHistory(prev => [...prev, result.feedback]);
      setFeedbackContent("");
    } catch {
      setFeedbackError("发送失败，请重试");
    } finally {
      setFeedbackSending(false);
    }
  };

  const handleRestart = async () => {
    setRestarting(true);
    setRestartError(null);
    try {
      await restartSurvey();
      setProgress(null);
    } catch {
      setRestartError("重启失败，请稍后重试");
    } finally {
      setRestarting(false);
    }
  };

  const handleInterrupt = async () => {
    setInterrupting(true);
    try {
      await interruptSurvey();
      showToast("info", "Pipeline paused");
    } catch {
      showToast("error", "Interrupt failed");
    } finally {
      setInterrupting(false);
    }
  };

  const handleResume = async () => {
    try {
      await resumeSurvey();
      showToast("success", "Pipeline resumed");
    } catch {
      showToast("error", "Resume failed");
    }
  };

  const handleCancel = async () => {
    setShowCancelDialog(false);
    try {
      await interruptSurvey();
      showToast("info", "Task cancelled");
    } catch {
      showToast("error", "Cancel failed");
    }
  };

  const currentStage = progress?.current_stage || "";
  const stageIndex = STAGE_ORDER.indexOf(currentStage);
  const pipelineFinished = !connected && progress?.pipeline_running === false;
  const pipelineRunning = progress?.pipeline_running === true;
  const isInterrupted = progress?.status === "INTERRUPTED";

  const renderStageChain = () => (
    <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", flexWrap: "wrap", marginBottom: "1.5rem" }}>
      {STAGE_ORDER.map((stage, i) => {
        const idx = STAGE_ORDER.indexOf(stage);
        const isActive = stage === currentStage;
        const isPast = stageIndex >= 0 && idx < stageIndex;
        const isFuture = stageIndex >= 0 && idx > stageIndex;
        const isTerminal = stage === "complete" || stage === "error";

        let bg = "#e0e0e0";
        let color = "#666";
        if (isActive) {
          bg = "var(--color-primary)";
          color = "#fff";
        } else if (isPast) {
          bg = "var(--color-success)";
          color = "#fff";
        }

        return (
          <React.Fragment key={stage}>
            <div style={{
              padding: "0.5rem 1rem",
              borderRadius: "var(--radius-full)",
              background: bg,
              color: color,
              fontWeight: isActive ? 700 : 400,
              fontSize: "var(--font-size-sm)",
              whiteSpace: "nowrap",
              opacity: isFuture ? 0.4 : 1,
              transition: "all 0.3s",
            }}>
              {isPast ? "✓ " : isActive ? "▶ " : ""}
              {STAGE_LABELS[stage] || stage}
            </div>
            {i < STAGE_ORDER.length - 1 && !isTerminal && (
              <div style={{ color: "#ccc", fontSize: "1.2rem" }}>→</div>
            )}
          </React.Fragment>
        );
      })}
    </div>
  );

  const renderCurrentMessage = () => (
    progress?.current_message ? (
      <div style={{
        background: pipelineRunning ? "var(--color-primary-light)" : "#f5f5f5",
        borderRadius: "var(--radius-lg)", padding: "1rem 1.5rem",
        marginBottom: "1.5rem",
        borderLeft: `4px solid ${pipelineRunning ? "var(--color-primary)" : progress?.has_warnings ? "var(--color-warning)" : "var(--color-success)"}`,
      }}>
        <p style={{ margin: 0, color: "var(--color-text-primary)" }}>{progress?.current_message}</p>
      </div>
    ) : null
  );

  const renderExecutionDetails = () => {
    const details = progress?.execution_details;
    if (!details) return null;

    return (
      <div style={{ display: "flex", flexDirection: "column", marginBottom: "1.5rem" }}>
        {details.plan && (
          <DetailCard title="📋 研究计划">
            <p className="text-secondary mb-sm">共 {details.plan.section_count} 个章节/要点</p>
            {details.plan.preview.map((line, i) => (
              <p key={i} style={{ margin: "0.2rem 0", paddingLeft: "0.5rem",
                borderLeft: "2px solid var(--color-primary)", fontSize: "var(--font-size-sm)" }}>
                {line}
              </p>
            ))}
          </DetailCard>
        )}

        {details.search_queries && (
          <DetailCard title="🔍 搜索查询">
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
              {details.search_queries.map((q, i) => (
                <span key={i} style={{
                  background: "var(--color-primary-light)", padding: "0.3rem 0.8rem",
                  borderRadius: "var(--radius-full)", fontSize: "var(--font-size-sm)", color: "var(--color-primary-dark)",
                }}>
                  {q}
                </span>
              ))}
            </div>
          </DetailCard>
        )}

        {details.papers && (
          <DetailCard title={`📄 检索到的论文（共 ${details.papers.total} 篇）`}>
            <div style={{ maxHeight: 300, overflowY: "auto" }}>
              {details.papers.list.map((p, i) => (
                <div key={i} style={{
                  padding: "0.5rem", marginBottom: "0.3rem",
                  background: "#fafafa", borderRadius: "var(--radius-md)", border: "1px solid var(--color-border-light)",
                }}>
                  <div style={{ fontWeight: 600, fontSize: "var(--font-size-sm)" }}>{p.title}</div>
                  <div style={{ fontSize: "var(--font-size-xs)", color: "var(--color-text-secondary)", marginTop: "0.2rem" }}>
                    {p.authors} · {p.year} · 引用: {p.citations}
                    <Badge color="blue">{p.source}</Badge>
                  </div>
                </div>
              ))}
              {details.papers.total > 10 && (
                <p className="text-disabled" style={{ fontSize: "var(--font-size-sm)", textAlign: "center" }}>
                  … 还有 {details.papers.total - 10} 篇
                </p>
              )}
            </div>
          </DetailCard>
        )}

        {details.analysis && (
          <DetailCard title="🔬 论文分析">
            <p style={{ color: "var(--color-text-secondary)", fontSize: "var(--font-size-sm)", whiteSpace: "pre-wrap",
              margin: 0, lineHeight: 1.5 }}>
              {details.analysis.preview}
            </p>
          </DetailCard>
        )}

        {details.sections && (
          <DetailCard title="📑 论文结构">
            {details.sections.map((s, i) => (
              <div key={i} style={{
                padding: "0.3rem 0", paddingLeft: s.level === 0 ? "0" : "1.5rem",
                fontWeight: s.level === 0 ? 600 : 400, fontSize: "var(--font-size-sm)",
              }}>
                {s.level === 0 ? "▸ " : "  ◦ "}{s.title}
              </div>
            ))}
          </DetailCard>
        )}

        {details.validation && (
          <DetailCard title="✅ 质量验证">
            {Object.entries(details.validation).map(([name, v]) => (
              <div key={name} style={{
                display: "flex", alignItems: "center", gap: "0.5rem",
                padding: "0.3rem 0", borderBottom: "1px solid var(--color-border-light)",
              }}>
                <span style={{
                  width: 8, height: 8, borderRadius: "50%",
                  background: v.passed ? "var(--color-success)" : "var(--color-danger)",
                  display: "inline-block", flexShrink: 0,
                }} />
                <span style={{ fontWeight: 500, minWidth: 140, fontSize: "var(--font-size-sm)" }}>{name}</span>
                <Badge color={v.passed ? "green" : "red"}>{v.passed ? "通过" : "需改进"}</Badge>
                {v.message && (
                  <span className="text-secondary" style={{ fontSize: "var(--font-size-xs)", marginLeft: "0.3rem" }}>
                    — {v.message}
                  </span>
                )}
              </div>
            ))}
          </DetailCard>
        )}

        {!details.plan && !details.search_queries && !details.papers &&
         !details.analysis && !details.sections && !details.validation && (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
            <Card title="Keywords">
              <p className="text-secondary" style={{ margin: "0.3rem 0 0" }}>
                {progress?.keywords?.length ? progress.keywords.join(", ") : "—"}
              </p>
            </Card>
            <Card title="Research Goal">
              <p className="text-secondary" style={{ margin: "0.3rem 0 0", whiteSpace: "pre-wrap" }}>
                {progress?.goal || "—"}
              </p>
            </Card>
          </div>
        )}
      </div>
    );
  };

  const renderFeedbackPanel = () => (
    <Card title="向 Agent 提供反馈" style={{ border: "1px solid var(--color-border)" }}>
      <div style={{ marginBottom: "0.5rem" }}>
        {FEEDBACK_CATEGORIES.map(c => (
          <label key={c.value} style={{
            display: "inline-flex", alignItems: "center", gap: "0.3rem",
            marginRight: "1rem", cursor: "pointer", fontSize: "var(--font-size-sm)",
          }}>
            <input
              type="radio"
              name="feedbackCategory"
              value={c.value}
              checked={feedbackCategory === c.value}
              onChange={() => setFeedbackCategory(c.value)}
            />
            {c.label}
          </label>
        ))}
      </div>

      <p style={{ fontSize: "var(--font-size-xs)", color: "var(--color-text-secondary)", margin: "0 0 0.5rem" }}>
        {FEEDBACK_CATEGORIES.find(c => c.value === feedbackCategory)?.desc}
      </p>

      <textarea
        value={feedbackContent}
        onChange={e => setFeedbackContent(e.target.value)}
        placeholder={
          feedbackCategory === "supplement_papers" ? "例：请补充关于 Vision Transformer 高效的论文…" :
          feedbackCategory === "expand_section" ? "例：请在实验部分增加对消融实验的详细讨论…" :
          "例：请加强对对比方法的分析…"
        }
        rows={3}
        style={{
          width: "100%", padding: "0.6rem", borderRadius: "var(--radius-md)",
          border: "1px solid var(--color-border)", fontSize: "var(--font-size-sm)",
          resize: "vertical", boxSizing: "border-box",
        }}
      />

      <div style={{ display: "flex", alignItems: "center", gap: "1rem", marginTop: "0.5rem" }}>
        <Button
          onClick={handleSendFeedback}
          disabled={feedbackSending || !feedbackContent.trim()}
          loading={feedbackSending}
        >
          发送反馈
        </Button>
        {feedbackError && <span style={{ color: "var(--color-danger)", fontSize: "var(--font-size-sm)" }}>{feedbackError}</span>}
      </div>

      {feedbackHistory.length > 0 && (
        <div style={{ marginTop: "1rem", borderTop: "1px solid var(--color-border-light)", paddingTop: "0.8rem" }}>
          <h5 style={{ margin: "0 0 0.5rem", color: "#555", fontSize: "var(--font-size-sm)" }}>反馈历史</h5>
          {feedbackHistory.map(fb => (
            <div key={fb.id} style={{
              padding: "0.5rem 0.8rem", marginBottom: "0.3rem", borderRadius: "var(--radius-md)",
              borderLeft: `3px solid ${
                fb.status === "applied" ? "var(--color-success)" :
                fb.status === "processing" ? "var(--color-warning)" : "var(--color-primary)"
              }`,
              background: fb.status === "applied" ? "var(--color-success-light)" : "#fafafa",
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: "var(--font-size-xs)", color: "var(--color-text-disabled)" }}>
                  {FEEDBACK_CATEGORIES.find(c => c.value === fb.category)?.label || fb.category}
                  {" — "}{fb.received_at}
                </span>
                <Badge color={fb.status === "applied" ? "green" : fb.status === "processing" ? "orange" : "blue"}>
                  {fb.status === "applied" ? "✓ 已处理" :
                   fb.status === "processing" ? "⟳ 处理中…" : "◷ 排队中"}
                </Badge>
              </div>
              <p style={{ margin: "0.2rem 0 0", fontSize: "var(--font-size-sm)", color: "var(--color-text-primary)" }}>
                {fb.content}
              </p>
            </div>
          ))}
        </div>
      )}
    </Card>
  );

  const renderErrorPanel = () => {
    if (progress?.status !== "ERROR" || pipelineRunning) return null;

    return (
      <div style={{
        background: "var(--color-danger-light)", borderRadius: "var(--radius-lg)", padding: "1.5rem",
        borderLeft: "4px solid var(--color-danger)", marginBottom: "1.5rem",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem" }}>
          <span style={{ fontSize: "1.5rem" }}>⚠</span>
          <h3 style={{ margin: 0, color: "var(--color-danger-dark)" }}>Pipeline Error</h3>
        </div>

        {progress.last_failed_stage && (
          <p style={{ margin: "0.3rem 0", color: "var(--color-danger-dark)", fontSize: "var(--font-size-sm)" }}>
            Failed at stage: <strong>{progress.last_failed_stage}</strong>
            {progress.pipeline_retry_count != null && progress.pipeline_retry_count > 0 && (
              <span> (after {progress.pipeline_retry_count} attempt{progress.pipeline_retry_count > 1 ? "s" : ""})</span>
            )}
          </p>
        )}

        {progress.error && (
          <div style={{
            background: "#fff", borderRadius: "var(--radius-md)", padding: "0.8rem", marginTop: "0.5rem",
            fontFamily: "monospace", fontSize: "var(--font-size-sm)", color: "var(--color-danger-dark)",
            whiteSpace: "pre-wrap", wordBreak: "break-all",
          }}>
            {progress.error}
          </div>
        )}

        <div style={{ display: "flex", gap: "1rem", alignItems: "center", marginTop: "1rem" }}>
          <Button variant="danger" onClick={handleRestart} loading={restarting} size="lg">
            🔄 一键重启
          </Button>
          {restartError && <span style={{ color: "var(--color-danger-dark)", fontSize: "var(--font-size-sm)" }}>{restartError}</span>}
        </div>
      </div>
    );
  };

  return (
    <div>
      <h2 className="page-title">Agent Execution</h2>
      {!connected && !progress && (
        <LoadingSkeleton variant="card" />
      )}

      {progress && (
        <div>
          {/* Topic banner */}
          {progress.topic && (
            <div style={{
              background: "linear-gradient(135deg, var(--color-bg-dark), #16213e)",
              color: "#fff", borderRadius: "var(--radius-lg)", padding: "1.2rem 1.5rem", marginBottom: "1.5rem",
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                <div>
                  <h3 style={{ margin: 0 }}>{progress.topic}</h3>
                  <p style={{ margin: "0.3rem 0 0", opacity: 0.8, fontSize: "var(--font-size-sm)" }}>
                    <Badge color={getStatusBadgeColor(progress.status)}>{progress.status}</Badge>
                    {" 重试: "}{progress.retry_count}
                    {pipelineRunning && <Badge color="blue" dot>Running</Badge>}
                    {progress.has_warnings && <Badge color="orange" dot>Has Warnings</Badge>}
                  </p>
                </div>
                {/* Pipeline control buttons */}
                <div style={{ display: "flex", gap: "0.5rem", flexShrink: 0 }}>
                  {pipelineRunning && (
                    <>
                      <Button variant="ghost" size="sm" onClick={handleInterrupt} loading={interrupting}
                        style={{ color: "#fff", borderColor: "rgba(255,255,255,0.3)" }}>
                        ⏸ Pause
                      </Button>
                      <Button variant="danger" size="sm" onClick={() => setShowCancelDialog(true)}>
                        ⏹ Cancel
                      </Button>
                    </>
                  )}
                  {isInterrupted && (
                    <Button variant="primary" size="sm" onClick={handleResume}
                      style={{ background: "var(--color-success)", color: "#fff" }}>
                      ▶ Resume
                    </Button>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Stage chain */}
          {renderStageChain()}

          {/* Current message */}
          {renderCurrentMessage()}

          {/* Two-column layout when running */}
          {pipelineRunning ? (
            <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: "1.5rem" }}>
              <div>{renderExecutionDetails()}</div>
              <div>{renderFeedbackPanel()}</div>
            </div>
          ) : (
            <div>
              {renderExecutionDetails()}
              {renderErrorPanel()}
              {pipelineFinished && progress?.status !== "ERROR" && (
                <div style={{
                  background: "var(--color-success-light)", borderRadius: "var(--radius-lg)", padding: "1rem 1.5rem",
                  borderLeft: "4px solid var(--color-success)",
                }}>
                  <p style={{ margin: 0, color: "var(--color-success-dark)", fontWeight: 600 }}>
                    ✓ Pipeline completed. {progress.has_warnings && "Completed with warnings."}
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {!progress && connected && (
        <p className="text-secondary">Waiting for execution data…</p>
      )}

      {/* Cancel confirmation dialog */}
      <ConfirmDialog
        open={showCancelDialog}
        title="Cancel Task?"
        message="This will stop the current pipeline. You can start a new task from the Dashboard."
        confirmLabel="Cancel Task"
        danger
        onConfirm={handleCancel}
        onCancel={() => setShowCancelDialog(false)}
      />
    </div>
  );
}