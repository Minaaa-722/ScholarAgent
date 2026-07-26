import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getSurveyStatus, restartSurvey } from "../api/client";

export default function Dashboard() {
  const [currentTask, setCurrentTask] = useState<any>(null);
  const [restarting, setRestarting] = useState(false);
  const [restartError, setRestartError] = useState<string | null>(null);

  const handleRestart = async () => {
    setRestarting(true);
    setRestartError(null);
    try {
      await restartSurvey();
      setCurrentTask(null);
      // Re-fetch status
      const data = await getSurveyStatus();
      if (data.topic) setCurrentTask(data);
    } catch {
      setRestartError("重启失败，请稍后重试");
    } finally {
      setRestarting(false);
    }
  };

  useEffect(() => {
    getSurveyStatus().then((data) => { if (data.topic) setCurrentTask(data); });
  }, []);

  return (
    <div>
      <h1>ScholarAgent</h1>
      <p style={{ color: "#666", marginBottom: "2rem" }}>Automated Literature Review Agent</p>
      <h2>Recent Research Tasks</h2>
      {currentTask ? (
        <div style={{ background: "#fff", borderRadius: 8, padding: "1.5rem",
          boxShadow: "0 1px 3px rgba(0,0,0,0.1)", marginBottom: "1rem", maxWidth: 400 }}>
          <h3>{currentTask.topic}</h3>
          <p>Status: {currentTask.status}</p>
          {currentTask.status === "ERROR" && (
            <div style={{
              background: "#ffebee", borderRadius: 6, padding: "0.8rem",
              margin: "0.5rem 0", borderLeft: "3px solid #f44336",
            }}>
              <p style={{ margin: 0, color: "#c62828", fontSize: "0.85rem" }}>
                Error: {currentTask.error || "Unknown error"}
              </p>
              <button
                onClick={handleRestart}
                disabled={restarting}
                style={{
                  marginTop: "0.5rem", padding: "0.4rem 1rem",
                  background: restarting ? "#ccc" : "#f44336", color: "#fff",
                  border: "none", borderRadius: 4, cursor: restarting ? "not-allowed" : "pointer",
                  fontSize: "0.85rem",
                }}
              >
                {restarting ? "重启中…" : "🔄 一键重启"}
              </button>
              {restartError && <p style={{ color: "#b71c1c", fontSize: "0.8rem" }}>{restartError}</p>}
            </div>
          )}
          {currentTask.pipeline_running && (
            <p style={{ color: "#1976d2" }}>
              ▶ {currentTask.current_message || "Running…"}
            </p>
          )}
          <div style={{ display: "flex", gap: "1rem", marginTop: "0.5rem" }}>
            {currentTask.pipeline_running && (
              <Link to="/execution" style={{ color: "#1976d2" }}>View Progress →</Link>
            )}
            <Link to="/review" style={{ color: "#1976d2" }}>View Report →</Link>
          </div>
        </div>
      ) : (
        <p style={{ color: "#999" }}>No recent tasks. Start a new research project!</p>
      )}
      <Link to="/create">
        <button style={{ marginTop: "1rem", padding: "0.8rem 2rem", background: "#1976d2",
          color: "#fff", border: "none", borderRadius: 6, cursor: "pointer", fontSize: "1rem" }}>
          + New Research Task
        </button>
      </Link>
    </div>
  );
}