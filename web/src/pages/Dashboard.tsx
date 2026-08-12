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
          style={{ maxWidth: 400 }}
        >
          {currentTask.status === "ERROR" && (
            <div className="error-block" style={{
              background: "var(--color-danger-light)", borderRadius: "var(--radius-md)", padding: "0.8rem",
              margin: "0.5rem 0", borderLeft: "3px solid var(--color-danger)",
            }}>
              <p style={{ margin: 0, color: "var(--color-danger-dark)", fontSize: "var(--font-size-sm)" }}>
                Error: {currentTask.error || "Unknown error"}
              </p>
              <div className="flex items-center" style={{ gap: "0.5rem", marginTop: "0.5rem" }}>
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
          <div className="flex" style={{ gap: "1rem", marginTop: "0.5rem" }}>
            {currentTask.pipeline_running && (
              <Link to="/execution">View Progress →</Link>
            )}
            <Link to="/review">View Report →</Link>
          </div>
        </Card>
      )}

      {/* Onboarding feature cards */}
      {!currentTask && (
        <div className="grid-3" style={{ gap: "var(--space-md)", marginTop: "var(--space-lg)" }}>
          <Card title="🔍 Multi-Source Search">
            <p className="text-secondary" style={{ fontSize: "var(--font-size-sm)" }}>
              Searches arXiv, Semantic Scholar, and Google Scholar automatically.
            </p>
          </Card>
          <Card title="✅ Quality Validation">
            <p className="text-secondary" style={{ fontSize: "var(--font-size-sm)" }}>
              5-dimension quality check with auto-correction.
            </p>
          </Card>
          <Card title="📝 CVPR Format">
            <p className="text-secondary" style={{ fontSize: "var(--font-size-sm)" }}>
              Outputs in CVPR LaTeX format with BibTeX references.
            </p>
          </Card>
        </div>
      )}

      {currentTask && (
        <div style={{ marginTop: "var(--space-lg)" }}>
          <Link to="/create">
            <Button>+ New Research Task</Button>
          </Link>
        </div>
      )}

      {/* History section */}
      {!historyLoading && history.length > 0 && (
        <div style={{ marginTop: "var(--space-lg)" }}>
          <h2 className="section-title">
            History ({history.length})
          </h2>
          <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: "var(--space-lg)" }}>
            {history.map((item) => (
              <Card
                key={item.id}
                hoverable
                onClick={() => navigate(`/history/${item.id}`)}
                title={item.topic}
                headerRight={
                  <Badge color={item.status === "complete" ? "green" : item.status === "error" ? "red" : "gray"}>
                    {item.status}
                  </Badge>
                }
              >
                <div className="flex flex-col" style={{ height: "100%" }}>
                  <p className="text-secondary" style={{ fontSize: "var(--font-size-sm)", flex: 1 }}>
                    {item.goal ? item.goal.slice(0, 100) + (item.goal.length > 100 ? "…" : "") : "No goal specified"}
                  </p>
                  <div className="flex" style={{ gap: "0.8rem", marginTop: "0.5rem", fontSize: "var(--font-size-xs)", color: "var(--color-text-tertiary)" }}>
                    <span>{item.paper_count} papers</span>
                    <span>{item.rounds} round{item.rounds !== 1 ? "s" : ""}</span>
                    <span>{item.timestamp}</span>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}