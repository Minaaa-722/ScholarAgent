import React, { useEffect, useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { getSurveyStatus, restartSurvey, cancelSurvey } from "../api/client";
import Button from "../components/Button";
import Card from "../components/Card";
import Badge from "../components/Badge";
import ConfirmDialog from "../components/ConfirmDialog";
import { useToast } from "../components/Toast";
import { useWebSocket } from "../hooks/useWebSocket";
import StageTimeline from "../components/StageTimeline";

const API_BASE = "http://localhost:8000";

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
  plan?: { summary: string; full_text: string; section_count: number };
  search_queries?: string[];
  papers?: { total: number; list: PaperInfo[] };
  analysis?: { summary: string; preview: string };
  sections?: SectionInfo[];
  validation?: Record<string, { score: number; passed: boolean; message: string }>;
}

interface StageMessage {
  type: "info" | "success" | "warning" | "error";
  message: string;
  timestamp: string;
}

interface StageMetrics {
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
  execution_details: ExecutionDetails;
  stage_messages: StageMessage[];
  stage_metrics: StageMetrics;
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

function getStatusBadgeColor(status: string): "green" | "red" | "orange" | "blue" | "gray" {
  if (status === "COMPLETE") return "green";
  if (status === "ERROR") return "red";
  if (status === "INTERRUPTED") return "orange";
  if (status === "RUNNING") return "blue";
  return "gray";
}

export default function AgentExecution() {
  const [progress, setProgress] = useState<ProgressInfo | null>(null);
  const [taskStartedAt, setTaskStartedAt] = useState<string>("");
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Restart state
  const [restarting, setRestarting] = useState(false);
  const [restartError, setRestartError] = useState<string | null>(null);

  // Cancel dialog state
  const [showCancelDialog, setShowCancelDialog] = useState(false);

  const { showToast } = useToast();

  const navigate = useNavigate();

  // WebSocket connection via hook — stop reconnecting once pipeline is done
  const { connected } = useWebSocket({
    taskId: "current",
    shouldStopReconnect: () => {
      // Stop reconnecting once the pipeline has reached a terminal state
      // and the WebSocket has delivered the final data
      return progress?.pipeline_running === false
        && (progress?.status === "COMPLETE" || progress?.status === "ERROR" || progress?.status === "INTERRUPTED");
    },
    onMessage: (data: ProgressInfo) => {
      setProgress(data);
      if (data.task_started_at) {
        setTaskStartedAt(data.task_started_at);
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

  // Derived pipeline state (defined early so useEffects can reference them)
  const currentStage = progress?.current_stage || "";
  const stageIndex = STAGE_ORDER.indexOf(currentStage);
  const pipelineFinished = !connected
    && progress?.pipeline_running === false
    && progress?.task_started_at
    && (progress?.status === "COMPLETE" || progress?.status === "ERROR");
  const pipelineRunning = progress?.pipeline_running === true;

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

  const handleCancel = async () => {
    setShowCancelDialog(false);
    try {
      await cancelSurvey();
      // Reset page state to show the default "no task running" view
      setProgress(null);
      setTaskStartedAt("");
      showToast("info", "Task cancelled");
    } catch {
      showToast("error", "Cancel failed");
    }
  };

  const renderDefaultPage = () => (
    <div>
      {/* Hero section */}
      <div style={{
        background: "linear-gradient(135deg, var(--color-bg-dark), #16213e)",
        color: "#fff", borderRadius: "var(--radius-lg)", padding: "2rem 1.5rem",
        marginBottom: "1.5rem", textAlign: "center",
      }}>
        <div style={{ fontSize: "3rem", marginBottom: "0.5rem" }}>🚀</div>
        <h2 style={{ margin: "0 0 0.3rem" }}>Agent Execution Pipeline</h2>
        <p style={{ margin: "0 0 0.5rem", opacity: 0.8, fontSize: "var(--font-size-sm)" }}>
          监控和管理你的文献综述自动化流程
        </p>
        <p style={{ margin: "0", opacity: 0.6, fontSize: "var(--font-size-xs)" }}>
          当前没有正在执行的任务
        </p>
      </div>

      {/* Pipeline overview */}
      <div style={{
        display: "flex", gap: "0.5rem", alignItems: "center",
        justifyContent: "center", flexWrap: "wrap", marginBottom: "2rem",
      }}>
        {[
          { icon: "📋", label: "Plan", desc: "制定检索计划" },
          { icon: "🔍", label: "Search", desc: "多源文献检索" },
          { icon: "📊", label: "Analyze", desc: "内容分析与提取" },
          { icon: "✍️", label: "Write", desc: "综述文章撰写" },
          { icon: "✅", label: "Validate", desc: "质量多维验证" },
        ].map((stage, i) => (
          <React.Fragment key={stage.label}>
            <div style={{ textAlign: "center", padding: "0.5rem 1rem" }}>
              <div style={{
                background: "var(--color-primary)", color: "#fff",
                borderRadius: "var(--radius-full)", padding: "0.5rem 1rem",
                fontWeight: 600, fontSize: "var(--font-size-sm)",
                whiteSpace: "nowrap", marginBottom: "0.3rem",
              }}>
                {stage.icon} {stage.label}
              </div>
              <div style={{ fontSize: "var(--font-size-xs)", color: "var(--color-text-secondary)" }}>
                {stage.desc}
              </div>
            </div>
            {i < 4 && (
              <div style={{ color: "#ccc", fontSize: "1.5rem", marginBottom: "1.2rem" }}>→</div>
            )}
          </React.Fragment>
        ))}
      </div>

      {/* Feature cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "var(--space-md)", marginBottom: "2rem" }}>
        <Card title="📡 实时监控">
          <p className="text-secondary" style={{ fontSize: "var(--font-size-sm)" }}>
            实时查看各阶段执行进度、当前消息和详细执行数据
          </p>
        </Card>
        <Card title="✅ 质量验证">
          <p className="text-secondary" style={{ fontSize: "var(--font-size-sm)" }}>
            5 维度质量验证与自动修正，确保综述质量
          </p>
        </Card>
      </div>

      {/* CTA button */}
      <div style={{ textAlign: "center" }}>
        <Button size="lg" onClick={() => navigate("/create")}>
          🚀 开始新的研究任务
        </Button>
      </div>
    </div>
  );

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
      {!connected && !progress && renderDefaultPage()}

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
                    <Button variant="danger" size="sm" onClick={() => setShowCancelDialog(true)}>
                      ⏹ Cancel
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

          <StageTimeline
            currentStage={currentStage}
            stageOrder={STAGE_ORDER}
            stageLabels={STAGE_LABELS}
            executionDetails={progress?.execution_details ?? null}
            currentMessage={progress?.current_message ?? ""}
            pipelineRunning={pipelineRunning}
            stageMessages={progress?.stage_messages ?? []}
            stageMetrics={progress?.stage_metrics ?? {}}
          />
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