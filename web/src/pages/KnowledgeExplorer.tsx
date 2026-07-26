import React, { useEffect, useState, useRef } from "react";
import { getExecutionLog, getPaper, getSurveyStatus } from "../api/client";

interface LogEntry {
  stage: string;
  timestamp: string;
  [key: string]: unknown;
}

const STAGE_COLORS: Record<string, string> = {
  PLANNING: "#1976d2",
  RETRIEVAL: "#7b1fa2",
  ANALYSIS: "#e65100",
  WRITING: "#2e7d32",
  VALIDATION: "#c62828",
  FEEDBACK: "#f57f17",
  ERROR: "#b71c1c",
};

export default function KnowledgeExplorer() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [paper, setPaper] = useState<any>(null);
  const [taskInfo, setTaskInfo] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [selectedLog, setSelectedLog] = useState<LogEntry | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchData = async () => {
    try {
      const [logData, paperData, statusData] = await Promise.all([
        getExecutionLog(), getPaper(), getSurveyStatus(),
      ]);
      setLogs(logData.execution_log || []);
      setPaper(paperData);
      setTaskInfo(statusData);
      setLoading(false);

      // Stop polling when pipeline is done and paper is ready
      if (!statusData?.pipeline_running && paperData?.paper) {
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
    timerRef.current = setInterval(fetchData, 3000);

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  if (loading) {
    return <div><h2>Knowledge Explorer</h2><p style={{ color: "#999" }}>Loading execution data…</p></div>;
  }

  const topic = paper?.task?.topic || taskInfo?.topic;

  return (
    <div>
      <h2>Knowledge Explorer</h2>

      {!topic ? (
        <p style={{ color: "#999" }}>No research task has been started yet.</p>
      ) : (
        <>
          {/* Topic header */}
          <div style={{
            background: "linear-gradient(135deg, #1a1a2e, #16213e)",
            color: "#fff", borderRadius: 8, padding: "1rem 1.5rem", marginBottom: "1.5rem",
          }}>
            <h3 style={{ margin: 0 }}>{topic}</h3>
            <p style={{ margin: "0.3rem 0 0", opacity: 0.8, fontSize: "0.9rem" }}>
              Status: {taskInfo?.status || paper?.status || "—"}
              {taskInfo?.pipeline_running && (
                <span style={{ color: "#64b5f6" }}>
                  {" | "}Running: {taskInfo.current_stage} — {taskInfo.current_message}
                </span>
              )}
              {paper?.rounds != null && ` | Writing rounds: ${paper.rounds}`}
              {paper?.has_warnings && <span style={{ color: "#ffa726" }}> | Has warnings</span>}
            </p>
          </div>

          {/* Two-column layout */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.5rem" }}>
            {/* Left: Execution Log */}
            <div>
              <h3 style={{ marginTop: 0 }}>Execution Log</h3>
              {logs.length === 0 ? (
                <p style={{ color: "#999" }}>No execution log entries yet.</p>
              ) : (
                <div style={{ maxHeight: 500, overflowY: "auto" }}>
                  {logs.map((entry, i) => {
                    const color = STAGE_COLORS[entry.stage] || "#666";
                    const isSelected = selectedLog === entry;
                    return (
                      <div
                        key={i}
                        onClick={() => setSelectedLog(isSelected ? null : entry)}
                        style={{
                          padding: "0.6rem 0.8rem", marginBottom: "0.3rem",
                          borderRadius: 6, cursor: "pointer",
                          background: isSelected ? "#e3f2fd" : "#fafafa",
                          border: `1px solid ${isSelected ? "#1976d2" : "#eee"}`,
                          transition: "all 0.2s",
                        }}
                      >
                        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                          <span style={{
                            background: color, color: "#fff", borderRadius: 4,
                            padding: "0.15rem 0.5rem", fontSize: "0.75rem", fontWeight: 600,
                          }}>
                            {entry.stage}
                          </span>
                          <span style={{ color: "#999", fontSize: "0.8rem" }}>
                            {entry.timestamp}
                          </span>
                        </div>
                        {isSelected && (
                          <pre style={{
                            marginTop: "0.5rem", marginBottom: 0, fontSize: "0.8rem",
                            whiteSpace: "pre-wrap", color: "#333",
                            background: "#f5f5f5", padding: "0.5rem", borderRadius: 4,
                          }}>
                            {JSON.stringify(entry, null, 2)}
                          </pre>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Right: Paper Summary / Metadata */}
            <div>
              <h3 style={{ marginTop: 0 }}>Paper Summary</h3>
              {paper?.paper ? (
                <div style={{ background: "#fff", borderRadius: 8, padding: "1rem", boxShadow: "0 1px 3px rgba(0,0,0,0.1)" }}>
                  <p style={{ color: "#666", fontSize: "0.9rem", marginBottom: "0.5rem" }}>
                    Paper length: <strong>{(paper.paper.length / 1000).toFixed(1)}k chars</strong>
                  </p>
                  <p style={{ color: "#666", fontSize: "0.9rem", marginBottom: "0.5rem" }}>
                    Status: <strong>{paper.status}</strong>
                  </p>
                  {paper.rounds != null && (
                    <p style={{ color: "#666", fontSize: "0.9rem", marginBottom: "0.5rem" }}>
                      Writing rounds: <strong>{paper.rounds}</strong>
                    </p>
                  )}
                  <div style={{
                    background: "#f5f5f5", borderRadius: 6, padding: "0.8rem",
                    marginTop: "0.5rem", maxHeight: 300, overflowY: "auto",
                    fontFamily: "'Times New Roman', Times, serif",
                    fontSize: "0.85rem", lineHeight: 1.5, whiteSpace: "pre-wrap",
                  }}>
                    {paper.paper.substring(0, 2000)}
                    {paper.paper.length > 2000 && <span style={{ color: "#999" }}>… [truncated]</span>}
                  </div>
                </div>
              ) : (
                <div>
                  <p style={{ color: "#999" }}>Paper not yet generated.</p>
                  {taskInfo?.pipeline_running && (
                    <p style={{ color: "#1976d2", fontSize: "0.9rem" }}>
                      Pipeline is running — auto-refreshing…
                    </p>
                  )}
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}