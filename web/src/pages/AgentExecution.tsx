import React, { useEffect, useState, useRef } from "react";
import { getSurveyStatus, submitFeedback, restartSurvey } from "../api/client";

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

function DetailCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{
      background: "#fff", borderRadius: 8, padding: "1rem 1.2rem",
      boxShadow: "0 1px 3px rgba(0,0,0,0.1)", marginBottom: "1rem",
    }}>
      <h4 style={{ margin: "0 0 0.8rem", fontSize: "0.95rem", color: "#333" }}>{title}</h4>
      {children}
    </div>
  );
}

export default function AgentExecution() {
  const [progress, setProgress] = useState<ProgressInfo | null>(null);
  const [connected, setConnected] = useState(false);
  const [taskStartedAt, setTaskStartedAt] = useState<string>("");
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
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

  // Poll HTTP status to detect new tasks (even when WebSocket is not connected)
  useEffect(() => {
    const checkStatus = async () => {
      try {
        const info = await getSurveyStatus();
        if (info.task_started_at && info.task_started_at !== taskStartedAt) {
          setTaskStartedAt(info.task_started_at);
          // New task detected — reset and reconnect WebSocket
          setProgress(null);
          setConnected(false);
          if (wsRef.current) {
            wsRef.current.close();
            wsRef.current = null;
          }
        }
      } catch {
        // ignore
      }
    };
    checkStatus();
    pollTimerRef.current = setInterval(checkStatus, 3000);
    return () => {
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    };
  }, [taskStartedAt]);

  // WebSocket connection — always reconnect on close
  useEffect(() => {
    let ws: WebSocket | null = null;

    function connect() {
      ws = new WebSocket(`${API_BASE.replace("http", "ws")}/ws/stream/current`);
      wsRef.current = ws;

      ws.onopen = () => setConnected(true);
      ws.onmessage = (event) => {
        try {
          const data: ProgressInfo & { task_id: string } = JSON.parse(event.data);
          setProgress(data);
          if (data.task_started_at) {
            setTaskStartedAt(data.task_started_at);
          }
          // Sync feedback history from server
          if (data.feedback_history) {
            setFeedbackHistory(data.feedback_history);
          }
        } catch {
          // ignore parse errors
        }
      };
      ws.onclose = () => {
        setConnected(false);
        wsRef.current = null;
        // Always reconnect after 2s
        reconnectTimerRef.current = setTimeout(connect, 2000);
      };
      ws.onerror = () => {
        ws?.close();
      };
    }

    connect();

    return () => {
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      if (ws) ws.close();
    };
  }, []);

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
      setConnected(false);
    } catch {
      setRestartError("重启失败，请稍后重试");
    } finally {
      setRestarting(false);
    }
  };

  const currentStage = progress?.current_stage || "";
  const stageIndex = STAGE_ORDER.indexOf(currentStage);
  const pipelineFinished = !connected && progress?.pipeline_running === false;
  const pipelineRunning = progress?.pipeline_running === true;

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
          bg = "#1976d2";
          color = "#fff";
        } else if (isPast) {
          bg = "#4caf50";
          color = "#fff";
        }

        return (
          <React.Fragment key={stage}>
            <div style={{
              padding: "0.5rem 1rem",
              borderRadius: 20,
              background: bg,
              color: color,
              fontWeight: isActive ? 700 : 400,
              fontSize: "0.85rem",
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
        background: pipelineRunning ? "#e3f2fd" : "#f5f5f5",
        borderRadius: 8, padding: "1rem 1.5rem",
        marginBottom: "1.5rem",
        borderLeft: `4px solid ${pipelineRunning ? "#1976d2" : progress?.has_warnings ? "#ff9800" : "#4caf50"}`,
      }}>
        <p style={{ margin: 0, color: "#333" }}>{progress?.current_message}</p>
      </div>
    ) : null
  );

  const renderExecutionDetails = () => {
    const details = progress?.execution_details;
    if (!details) return null;

    return (
      <div style={{ display: "flex", flexDirection: "column", marginBottom: "1.5rem" }}>
        {/* 研究计划 */}
        {details.plan && (
          <DetailCard title="📋 研究计划">
            <p style={{ color: "#666", margin: "0 0 0.5rem" }}>
              共 {details.plan.section_count} 个章节/要点
            </p>
            {details.plan.preview.map((line, i) => (
              <p key={i} style={{ margin: "0.2rem 0", paddingLeft: "0.5rem",
                borderLeft: "2px solid #1976d2", fontSize: "0.9rem" }}>
                {line}
              </p>
            ))}
          </DetailCard>
        )}

        {/* 搜索查询 */}
        {details.search_queries && (
          <DetailCard title="🔍 搜索查询">
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
              {details.search_queries.map((q, i) => (
                <span key={i} style={{
                  background: "#e3f2fd", padding: "0.3rem 0.8rem",
                  borderRadius: 12, fontSize: "0.85rem", color: "#1565c0",
                }}>
                  {q}
                </span>
              ))}
            </div>
          </DetailCard>
        )}

        {/* 检索到的论文 */}
        {details.papers && (
          <DetailCard title={`📄 检索到的论文（共 ${details.papers.total} 篇）`}>
            <div style={{ maxHeight: 300, overflowY: "auto" }}>
              {details.papers.list.map((p, i) => (
                <div key={i} style={{
                  padding: "0.5rem", marginBottom: "0.3rem",
                  background: "#fafafa", borderRadius: 6, border: "1px solid #eee",
                }}>
                  <div style={{ fontWeight: 600, fontSize: "0.9rem" }}>{p.title}</div>
                  <div style={{ fontSize: "0.8rem", color: "#666", marginTop: "0.2rem" }}>
                    {p.authors} · {p.year} · 引用: {p.citations}
                    <span style={{
                      marginLeft: "0.5rem", background: "#e8eaf6",
                      padding: "0.1rem 0.4rem", borderRadius: 4, fontSize: "0.75rem",
                    }}>
                      {p.source}
                    </span>
                  </div>
                </div>
              ))}
              {details.papers.total > 10 && (
                <p style={{ color: "#999", fontSize: "0.85rem", textAlign: "center" }}>
                  … 还有 {details.papers.total - 10} 篇
                </p>
              )}
            </div>
          </DetailCard>
        )}

        {/* 分析结果 */}
        {details.analysis && (
          <DetailCard title="🔬 论文分析">
            <p style={{ color: "#666", fontSize: "0.9rem", whiteSpace: "pre-wrap",
              margin: 0, lineHeight: 1.5 }}>
              {details.analysis.preview}
            </p>
          </DetailCard>
        )}

        {/* 论文结构 */}
        {details.sections && (
          <DetailCard title="📑 论文结构">
            {details.sections.map((s, i) => (
              <div key={i} style={{
                padding: "0.3rem 0", paddingLeft: s.level === 0 ? "0" : "1.5rem",
                fontWeight: s.level === 0 ? 600 : 400, fontSize: "0.9rem",
              }}>
                {s.level === 0 ? "▸ " : "  ◦ "}{s.title}
              </div>
            ))}
          </DetailCard>
        )}

        {/* 验证评分 */}
        {details.validation && (
          <DetailCard title="✅ 质量验证">
            {Object.entries(details.validation).map(([name, v]) => (
              <div key={name} style={{
                display: "flex", alignItems: "center", gap: "0.5rem",
                padding: "0.3rem 0", borderBottom: "1px solid #f0f0f0",
              }}>
                <span style={{
                  width: 8, height: 8, borderRadius: "50%",
                  background: v.passed ? "#4caf50" : "#f44336",
                  display: "inline-block", flexShrink: 0,
                }} />
                <span style={{ fontWeight: 500, minWidth: 140, fontSize: "0.9rem" }}>{name}</span>
                <span style={{ color: v.passed ? "#2e7d32" : "#c62828", fontSize: "0.85rem" }}>
                  {v.passed ? "✓ 通过" : "✗ 需改进"}
                </span>
                {v.message && (
                  <span style={{ color: "#666", fontSize: "0.8rem", marginLeft: "0.3rem" }}>
                    — {v.message}
                  </span>
                )}
              </div>
            ))}
          </DetailCard>
        )}

        {/* 无内容时显示原始 keywords/goal */}
        {!details.plan && !details.search_queries && !details.papers &&
         !details.analysis && !details.sections && !details.validation && (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
            <div style={{ background: "#fff", borderRadius: 8, padding: "1rem", boxShadow: "0 1px 3px rgba(0,0,0,0.1)" }}>
              <strong>Keywords</strong>
              <p style={{ color: "#666", margin: "0.3rem 0 0" }}>
                {progress?.keywords?.length ? progress.keywords.join(", ") : "—"}
              </p>
            </div>
            <div style={{ background: "#fff", borderRadius: 8, padding: "1rem", boxShadow: "0 1px 3px rgba(0,0,0,0.1)" }}>
              <strong>Research Goal</strong>
              <p style={{ color: "#666", margin: "0.3rem 0 0", whiteSpace: "pre-wrap" }}>
                {progress?.goal || "—"}
              </p>
            </div>
          </div>
        )}
      </div>
    );
  };

  const renderFeedbackPanel = () => (
    <div style={{
      background: "#fff", borderRadius: 8, padding: "1rem 1.5rem",
      marginBottom: "1.5rem", boxShadow: "0 1px 3px rgba(0,0,0,0.1)",
      border: "1px solid #e0e0e0",
    }}>
      <h4 style={{ margin: "0 0 0.8rem", color: "#333" }}>向 Agent 提供反馈</h4>

      {/* 类别选择 */}
      <div style={{ marginBottom: "0.5rem" }}>
        {FEEDBACK_CATEGORIES.map(c => (
          <label key={c.value} style={{
            display: "inline-flex", alignItems: "center", gap: "0.3rem",
            marginRight: "1rem", cursor: "pointer", fontSize: "0.9rem",
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

      {/* 类别描述提示 */}
      <p style={{ fontSize: "0.8rem", color: "#666", margin: "0 0 0.5rem" }}>
        {FEEDBACK_CATEGORIES.find(c => c.value === feedbackCategory)?.desc}
      </p>

      {/* 输入框 */}
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
          width: "100%", padding: "0.6rem", borderRadius: 6,
          border: "1px solid #ccc", fontSize: "0.9rem",
          resize: "vertical", boxSizing: "border-box",
        }}
      />

      {/* 发送按钮和错误提示 */}
      <div style={{ display: "flex", alignItems: "center", gap: "1rem", marginTop: "0.5rem" }}>
        <button
          onClick={handleSendFeedback}
          disabled={feedbackSending || !feedbackContent.trim()}
          style={{
            padding: "0.5rem 1.5rem",
            background: feedbackSending || !feedbackContent.trim() ? "#ccc" : "#1976d2",
            color: "#fff", border: "none", borderRadius: 6,
            cursor: feedbackSending || !feedbackContent.trim() ? "not-allowed" : "pointer",
            fontSize: "0.9rem",
          }}
        >
          {feedbackSending ? "发送中…" : "发送反馈"}
        </button>
        {feedbackError && <span style={{ color: "#f44336", fontSize: "0.85rem" }}>{feedbackError}</span>}
      </div>

      {/* 反馈历史 */}
      {feedbackHistory.length > 0 && (
        <div style={{ marginTop: "1rem", borderTop: "1px solid #eee", paddingTop: "0.8rem" }}>
          <h5 style={{ margin: "0 0 0.5rem", color: "#555", fontSize: "0.85rem" }}>反馈历史</h5>
          {feedbackHistory.map(fb => (
            <div key={fb.id} style={{
              padding: "0.5rem 0.8rem", marginBottom: "0.3rem", borderRadius: 6,
              borderLeft: `3px solid ${
                fb.status === "applied" ? "#4caf50" :
                fb.status === "processing" ? "#ff9800" : "#1976d2"
              }`,
              background: fb.status === "applied" ? "#f1f8e9" : "#fafafa",
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: "0.75rem", color: "#999" }}>
                  {FEEDBACK_CATEGORIES.find(c => c.value === fb.category)?.label || fb.category}
                  {" — "}{fb.received_at}
                </span>
                <span style={{ fontSize: "0.75rem", fontWeight: 600,
                  color: fb.status === "applied" ? "#2e7d32" :
                         fb.status === "processing" ? "#e65100" : "#1976d2",
                }}>
                  {fb.status === "applied" ? "✓ 已处理" :
                   fb.status === "processing" ? "⟳ 处理中…" : "◷ 排队中"}
                </span>
              </div>
              <p style={{ margin: "0.2rem 0 0", fontSize: "0.85rem", color: "#333" }}>
                {fb.content}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );

  const renderErrorPanel = () => {
    if (progress?.status !== "ERROR" || pipelineRunning) return null;

    return (
      <div style={{
        background: "#ffebee", borderRadius: 8, padding: "1.5rem",
        borderLeft: "4px solid #f44336", marginBottom: "1.5rem",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem" }}>
          <span style={{ fontSize: "1.5rem" }}>⚠</span>
          <h3 style={{ margin: 0, color: "#c62828" }}>Pipeline Error</h3>
        </div>

        {progress.last_failed_stage && (
          <p style={{ margin: "0.3rem 0", color: "#b71c1c", fontSize: "0.9rem" }}>
            Failed at stage: <strong>{progress.last_failed_stage}</strong>
            {progress.pipeline_retry_count > 0 && (
              <span> (after {progress.pipeline_retry_count} attempt{progress.pipeline_retry_count > 1 ? "s" : ""})</span>
            )}
          </p>
        )}

        {progress.error && (
          <div style={{
            background: "#fff", borderRadius: 6, padding: "0.8rem", marginTop: "0.5rem",
            fontFamily: "monospace", fontSize: "0.85rem", color: "#c62828",
            whiteSpace: "pre-wrap", wordBreak: "break-all",
          }}>
            {progress.error}
          </div>
        )}

        <div style={{ display: "flex", gap: "1rem", alignItems: "center", marginTop: "1rem" }}>
          <button
            onClick={handleRestart}
            disabled={restarting}
            style={{
              padding: "0.7rem 2rem",
              background: restarting ? "#ccc" : "#f44336",
              color: "#fff", border: "none", borderRadius: 6,
              cursor: restarting ? "not-allowed" : "pointer",
              fontSize: "1rem", fontWeight: 600,
              display: "flex", alignItems: "center", gap: "0.5rem",
            }}
          >
            {restarting ? "重启中…" : "🔄 一键重启"}
          </button>
          {restartError && <span style={{ color: "#b71c1c", fontSize: "0.85rem" }}>{restartError}</span>}
        </div>
      </div>
    );
  };

  return (
    <div>
      <h2>Agent Execution</h2>
      {!connected && !progress && (
        <p style={{ color: "#999" }}>Connecting to execution stream…</p>
      )}

      {progress && (
        <div>
          {/* Topic banner */}
          {progress.topic && (
            <div style={{
              background: "linear-gradient(135deg, #1a1a2e, #16213e)",
              color: "#fff", borderRadius: 8, padding: "1.2rem 1.5rem", marginBottom: "1.5rem",
            }}>
              <h3 style={{ margin: 0 }}>{progress.topic}</h3>
              <p style={{ margin: "0.3rem 0 0", opacity: 0.8, fontSize: "0.9rem" }}>
                Status: {progress.status} | Retry: {progress.retry_count}
                {pipelineRunning && <span style={{ color: "#64b5f6" }}> | Running</span>}
                {progress.has_warnings && <span style={{ color: "#ffa726" }}> | Has Warnings</span>}
              </p>
            </div>
          )}

          {/* Pipeline stage chain */}
          {renderStageChain()}

          {/* Current message */}
          {renderCurrentMessage()}

          {/* Two-column layout when running */}
          {pipelineRunning ? (
            <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: "1.5rem" }}>
              {/* Left: execution details */}
              <div>
                {renderExecutionDetails()}
              </div>
              {/* Right: feedback panel */}
              <div>
                {renderFeedbackPanel()}
              </div>
            </div>
          ) : (
            <div>
              {/* Full-width execution details */}
              {renderExecutionDetails()}

              {/* Error panel */}
              {renderErrorPanel()}

              {/* Pipeline finished (success) */}
              {pipelineFinished && progress?.status !== "ERROR" && (
                <div style={{
                  background: "#e8f5e9", borderRadius: 8, padding: "1rem 1.5rem",
                  borderLeft: "4px solid #4caf50",
                }}>
                  <p style={{ margin: 0, color: "#2e7d32", fontWeight: 600 }}>
                    ✓ Pipeline completed. {progress.has_warnings && "Completed with warnings."}
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {!progress && connected && (
        <p style={{ color: "#999" }}>Waiting for execution data…</p>
      )}
    </div>
  );
}