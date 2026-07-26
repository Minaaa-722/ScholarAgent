import React, { useEffect, useState, useRef } from "react";
import { getPaper, getSurveyStatus, restartSurvey } from "../api/client";

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
}

export default function FinalReview() {
  const [result, setResult] = useState<PaperResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [taskInfo, setTaskInfo] = useState<any>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [restarting, setRestarting] = useState(false);
  const [restartError, setRestartError] = useState<string | null>(null);

  const handleRestart = async () => {
    setRestarting(true);
    setRestartError(null);
    try {
      await restartSurvey();
      setResult(null);
      setLoading(true);
      // Re-fetch
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

      // Stop polling when paper is ready AND pipeline is not running
      if (paperData?.paper && !statusData?.pipeline_running) {
        if (timerRef.current) {
          clearInterval(timerRef.current);
          timerRef.current = null;
        }
      }
    } catch {
      // ignore
    }
  };

  useEffect(() => {
    fetchData();
    // Poll every 3s while waiting for pipeline to complete
    timerRef.current = setInterval(fetchData, 3000);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  if (loading) {
    return <div><h2>Final Review</h2><p style={{ color: "#999" }}>Loading paper…</p></div>;
  }

  if (!result || !result.paper) {
    const topic = taskInfo?.topic;
    return (
      <div>
        <h2>Final Review</h2>
        {topic ? (
          <div>
            <div style={{
              background: "#fff3e0", borderRadius: 8, padding: "1.5rem",
              borderLeft: "4px solid #ff9800",
            }}>
              <p style={{ margin: 0, color: "#e65100" }}>
                The pipeline for <strong>"{topic}"</strong> is still running or has not produced a paper yet.
                {taskInfo?.pipeline_running ? " Auto-refreshing…" : ""}
              </p>
            </div>
            {taskInfo?.pipeline_running && (
              <div style={{ marginTop: "1rem", color: "#1976d2", textAlign: "center" }}>
                <p>Current stage: <strong>{taskInfo.current_stage}</strong> — {taskInfo.current_message}</p>
              </div>
            )}
          </div>
        ) : (
          <p style={{ color: "#999" }}>No research task has been started yet.</p>
        )}
      </div>
    );
  }

  if (result.status === "error") {
    return (
      <div>
        <h2>Final Review</h2>
        <div style={{
          background: "#ffebee", borderRadius: 8, padding: "1.5rem",
          borderLeft: "4px solid #f44336",
        }}>
          <h3 style={{ color: "#c62828", margin: 0 }}>Pipeline Error</h3>
          <p style={{ color: "#b71c1c" }}>{result.error}</p>
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
      </div>
    );
  }

  return (
    <div>
      <h2>Final Review</h2>

      {/* Summary banner */}
      <div style={{
        background: result.has_warnings ? "#fff3e0" : "#e8f5e9",
        borderRadius: 8, padding: "1rem 1.5rem", marginBottom: "1.5rem",
        borderLeft: `4px solid ${result.has_warnings ? "#ff9800" : "#4caf50"}`,
      }}>
        <p style={{ margin: 0, fontWeight: 600 }}>
          Status: {result.status === "complete" ? "Completed" : result.status}
          {result.has_warnings && " (with warnings)"}
        </p>
        <p style={{ margin: "0.3rem 0 0", color: "#666", fontSize: "0.9rem" }}>
          Writing rounds: {result.rounds ?? "—"} | Retries: {result.retry_count ?? "—"}
        </p>
      </div>

      {/* Paper content */}
      <div style={{
        background: "#fff", borderRadius: 8, padding: "1.5rem",
        boxShadow: "0 1px 3px rgba(0,0,0,0.1)", marginBottom: "1.5rem",
      }}>
        <div style={{
          fontFamily: "'Times New Roman', Times, serif",
          lineHeight: 1.6, fontSize: "0.95rem", whiteSpace: "pre-wrap",
          overflowX: "auto",
        }}>
          {result.paper}
        </div>
      </div>

      {/* Download button */}
      <button
        onClick={() => {
          const blob = new Blob([result.paper || ""], { type: "text/plain;charset=utf-8" });
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = `survey_${(result.task?.topic || "paper").replace(/\s+/g, "_")}.tex`;
          a.click();
          URL.revokeObjectURL(url);
        }}
        style={{
          padding: "0.8rem 2rem", background: "#1976d2", color: "#fff",
          border: "none", borderRadius: 6, cursor: "pointer", fontSize: "1rem",
        }}
      >
        Download .tex
      </button>
    </div>
  );
}