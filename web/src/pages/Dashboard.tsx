import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getSurveyStatus } from "../api/client";

export default function Dashboard() {
  const [currentTask, setCurrentTask] = useState<any>(null);

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
          <Link to="/review" style={{ color: "#1976d2" }}>View Report →</Link>
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