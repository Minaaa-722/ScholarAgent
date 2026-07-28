import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { getSurveyStatus, restartSurvey, getHistory } from "../api/client";
import type { HistoryItem } from "../api/client";
import Card from "../components/Card";
import Button from "../components/Button";
import Badge from "../components/Badge";
import LoadingSkeleton from "../components/LoadingSkeleton";
import EmptyState from "../components/EmptyState";

export default function Dashboard() {
  const navigate = useNavigate();
  const [currentTask, setCurrentTask] = useState<any>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [restarting, setRestarting] = useState(false);
  const [restartError, setRestartError] = useState<string | null>(null);

  const handleRestart = async () => {
    setRestarting(true);
    setRestartError(null);
    try {
      await restartSurvey();
      setCurrentTask(null);
      const data = await getSurveyStatus();
      if (data.topic) setCurrentTask(data);
    } catch {
      setRestartError("重启失败，请稍后重试");
    } finally {
      setRestarting(false);
    }
  };

  useEffect(() => {
    getSurveyStatus()
      .then((data) => {
        if (data.topic) setCurrentTask(data);
      })
      .catch(() => {})
      .finally(() => setLoading(false));

    getHistory()
      .then((data) => setHistory(data))
      .catch(() => {})
      .finally(() => setHistoryLoading(false));
  }, []);

  if (loading) {
    return (
      <div>
        <h1 className="page-title">ScholarAgent</h1>
        <LoadingSkeleton variant="card" />
      </div>
    );
  }

  return (
    <div>
      <h1 className="page-title">ScholarAgent</h1>
      <p className="text-secondary mb-lg">Automated Literature Review Agent</p>

      {!currentTask ? (
        <EmptyState
          icon="🔬"
          title="Welcome to ScholarAgent"
          description="Your automated literature review assistant. Start by creating a new research task."
          actionLabel="+ New Research Task"
          onAction={() => navigate("/create")}
        />
      ) : (
        <Card
          title={currentTask.topic}
          headerRight={<Badge color={currentTask.status === "COMPLETE" ? "green" : currentTask.status === "ERROR" ? "red" : "blue"}>{currentTask.status}</Badge>}
        >
          {currentTask.status === "ERROR" && (
            <div style={{
              background: "var(--color-danger-light)", borderRadius: "var(--radius-md)", padding: "0.8rem",
              margin: "0.5rem 0", borderLeft: "3px solid var(--color-danger)",
            }}>
              <p style={{ margin: 0, color: "var(--color-danger-dark)", fontSize: "var(--font-size-sm)" }}>
                Error: {currentTask.error || "Unknown error"}
              </p>
              <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", marginTop: "0.5rem" }}>
                <Button variant="danger" size="sm" onClick={handleRestart} loading={restarting}>
                  🔄 一键重启
                </Button>
                {restartError && <span style={{ color: "var(--color-danger-dark)", fontSize: "var(--font-size-xs)" }}>{restartError}</span>}
              </div>
            </div>
          )}
          {currentTask.pipeline_running && (
            <p style={{ color: "var(--color-primary)" }}>
              ▶ {currentTask.current_message || "Running…"}
            </p>
          )}
          <div style={{ display: "flex", gap: "1rem", marginTop: "0.5rem" }}>
            {currentTask.pipeline_running && (
              <Link to="/execution" style={{ color: "var(--color-primary)" }}>View Progress →</Link>
            )}
            <Link to="/review" style={{ color: "var(--color-primary)" }}>View Report →</Link>
          </div>
        </Card>
      )}

      {/* Onboarding feature cards — shown when no task exists */}
      {!currentTask && (
        <div style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))",
          gap: "24px",
          width: "100%",
          margin: "12px 0 32px",
        }}>
          <div style={{ minHeight: "160px", height: "100%", boxSizing: "border-box" }}>
            <Card title="🔍 Multi-Source Search" style={{ marginBottom: 0 }}>
              <p className="text-secondary" style={{ fontSize: "var(--font-size-sm)" }}>
                Searches arXiv, Semantic Scholar, and Google Scholar automatically.
              </p>
            </Card>
          </div>
          <div style={{ minHeight: "160px", height: "100%", boxSizing: "border-box" }}>
            <Card title="✅ Quality Validation" style={{ marginBottom: 0 }}>
              <p className="text-secondary" style={{ fontSize: "var(--font-size-sm)" }}>
                5-dimension quality check with auto-correction.
              </p>
            </Card>
          </div>
          <div style={{ minHeight: "160px", height: "100%", boxSizing: "border-box" }}>
            <Card title="📝 CVPR Format" style={{ marginBottom: 0 }}>
              <p className="text-secondary" style={{ fontSize: "var(--font-size-sm)" }}>
                Outputs in CVPR LaTeX format with BibTeX references.
              </p>
            </Card>
          </div>
        </div>
      )}

      {currentTask && (
        <div style={{
          marginTop: "var(--space-lg)",
          marginBottom: "var(--space-lg)",
          display: "flex",
          justifyContent: "center",
          padding: "1.5rem 0",
          borderTop: "1px solid var(--color-border)",
          borderBottom: "1px solid var(--color-border)",
        }}>
          <Link to="/create">
            <Button size="lg">+ New Research Task</Button>
          </Link>
        </div>
      )}

      {/* History section */}
      {!historyLoading && history.length > 0 && (
        <div style={{ marginTop: "var(--space-lg)" }}>
          <h2 style={{ fontSize: "var(--font-size-lg)", marginBottom: "var(--space-sm)" }}>
            History ({history.length})
          </h2>
          <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))",
            gap: "24px",
            width: "100%",
            margin: "12px 0 32px",
          }}>
            {history.map((item) => (
              <div
                key={item.id}
                onClick={() => navigate(`/history/${item.id}`)}
                style={{ cursor: "pointer", minHeight: "160px", height: "100%", boxSizing: "border-box" }}
              >
                <Card
                  title={item.topic}
                  headerRight={
                    <Badge color={item.status === "complete" ? "green" : item.status === "error" ? "red" : item.status === "cancelled" ? "gray" : "gray"}>
                      {item.status === "cancelled" ? "已取消" : item.status}
                    </Badge>
                  }
                  style={{ marginBottom: 0 }}
                >
                  <p className="text-secondary" style={{ fontSize: "var(--font-size-sm)" }}>
                    {item.goal ? item.goal.slice(0, 100) + (item.goal.length > 100 ? "…" : "") : "No goal specified"}
                  </p>
                  <div style={{ display: "flex", gap: "0.8rem", marginTop: "0.3rem", fontSize: "var(--font-size-xs)", color: "var(--color-text-tertiary)" }}>
                    <span>{item.paper_count} papers</span>
                    <span>{item.rounds} round{item.rounds !== 1 ? "s" : ""}</span>
                    <span>{item.timestamp}</span>
                  </div>
                </Card>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}