import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { createSurvey } from "../api/client";

export default function ResearchCreation() {
  const navigate = useNavigate();
  const [topic, setTopic] = useState("");
  const [keywords, setKeywords] = useState("");
  const [goal, setGoal] = useState("");
  const [maxPapers, setMaxPapers] = useState(20);

  const handleStart = async () => {
    if (!topic.trim()) return;
    await createSurvey({ topic, keywords, goal, max_papers: maxPapers });
    navigate("/execution");
  };

  return (
    <div style={{ display: "flex", gap: "2rem" }}>
      <div style={{ flex: 1 }}>
        <h2>Research Configuration</h2>
        <div style={{ marginBottom: "1rem" }}>
          <label>Topic</label>
          <input value={topic} onChange={(e) => setTopic(e.target.value)}
            placeholder="e.g., Large Language Models for Software Engineering"
            style={{ display: "block", width: "100%", padding: "0.5rem", marginTop: "0.3rem" }} />
        </div>
        <div style={{ marginBottom: "1rem" }}>
          <label>Keywords</label>
          <input value={keywords} onChange={(e) => setKeywords(e.target.value)}
            placeholder="attention, transformer, BERT"
            style={{ display: "block", width: "100%", padding: "0.5rem", marginTop: "0.3rem" }} />
        </div>
        <div style={{ marginBottom: "1rem" }}>
          <label>Research Goal</label>
          <textarea value={goal} onChange={(e) => setGoal(e.target.value)}
            placeholder="Survey transformer architectures..." rows={3}
            style={{ display: "block", width: "100%", padding: "0.5rem", marginTop: "0.3rem" }} />
        </div>
        <div style={{ marginBottom: "1rem" }}>
          <label>Paper Number</label>
          <input type="number" value={maxPapers} onChange={(e) => setMaxPapers(Number(e.target.value))}
            min={5} max={100}
            style={{ display: "block", width: 80, padding: "0.5rem", marginTop: "0.3rem" }} />
        </div>
      </div>
      <div style={{ flex: 1 }}>
        <h2>Agent Strategy</h2>
        <div style={{ background: "#fff", padding: "1.5rem", borderRadius: 8, boxShadow: "0 1px 3px rgba(0,0,0,0.1)" }}>
          {["Planning Agent", "Search Agent", "Analysis Agent", "Writing Agent"].map((name, i) => (
            <div key={name}>
              <div style={{ padding: "1rem", background: "#e3f2fd", borderRadius: 6, textAlign: "center", fontWeight: 600 }}>{name}</div>
              {i < 3 && <div style={{ textAlign: "center", padding: "0.3rem" }}>↓</div>}
            </div>
          ))}
        </div>
        <button onClick={handleStart} style={{ marginTop: "1.5rem", padding: "0.8rem 2rem",
          background: "#1976d2", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer",
          fontSize: "1rem", width: "100%" }}>Start Agent</button>
      </div>
    </div>
  );
}