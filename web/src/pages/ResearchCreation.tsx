import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { createSurvey, getAutoLoadPreferences } from "../api/client";
import Card from "../components/Card";
import Button from "../components/Button";
import LoadingSkeleton from "../components/LoadingSkeleton";

export default function ResearchCreation() {
  const navigate = useNavigate();
  const [topic, setTopic] = useState("");
  const [keywords, setKeywords] = useState("");
  const [goal, setGoal] = useState("");
  const [maxPapers, setMaxPapers] = useState(20);
  const [yearStart, setYearStart] = useState(2020);
  const [yearEnd, setYearEnd] = useState(2026);
  const [loading, setLoading] = useState(true);
  const [errors, setErrors] = useState<Record<string, string>>({});

  // Auto-load preferences
  useEffect(() => {
    getAutoLoadPreferences().then(data => {
      const p = data.preferences || {};
      if (p.year_start) setYearStart(Number(p.year_start));
      if (p.year_end) setYearEnd(Number(p.year_end));
      if (p.max_papers) setMaxPapers(Number(p.max_papers));
    }).catch(() => { /* use defaults */ }).finally(() => setLoading(false));
  }, []);

  const validate = (): boolean => {
    const e: Record<string, string> = {};
    if (!topic.trim()) e.topic = "Topic is required";
    if (yearStart < 2015 || yearStart > 2026) e.yearStart = "Year must be 2015-2026";
    if (yearEnd < 2015 || yearEnd > 2026) e.yearEnd = "Year must be 2015-2026";
    if (yearStart > yearEnd) e.yearEnd = "End year must be after start year";
    if (maxPapers < 5 || maxPapers > 100) e.maxPapers = "Must be 5-100";
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const handleStart = async () => {
    if (!validate()) return;
    await createSurvey({ topic, keywords, goal, max_papers: maxPapers });
    navigate("/execution");
  };

  if (loading) {
    return (
      <div>
        <h2 className="page-title">Research Configuration</h2>
        <LoadingSkeleton variant="card" lines={6} />
      </div>
    );
  }

  return (
    <div style={{ display: "flex", gap: "2rem" }}>
      <div style={{ flex: 1 }}>
        <h2 className="page-title">Research Configuration</h2>
        <Card>
          <div style={{ marginBottom: "1rem" }}>
            <label style={{ fontWeight: 600, fontSize: "var(--font-size-sm)", display: "block", marginBottom: "0.3rem" }}>
              Topic <span style={{ color: "var(--color-danger)" }}>*</span>
            </label>
            <input value={topic} onChange={(e) => setTopic(e.target.value)}
              placeholder="e.g., Large Language Models for Software Engineering"
              style={{ display: "block", width: "100%", padding: "0.5rem", borderRadius: "var(--radius-md)", border: errors.topic ? "1px solid var(--color-danger)" : "1px solid var(--color-border)" }} />
            {errors.topic && <p style={{ color: "var(--color-danger)", fontSize: "var(--font-size-xs)", marginTop: "0.2rem" }}>{errors.topic}</p>}
          </div>

          <div style={{ marginBottom: "1rem" }}>
            <label style={{ fontWeight: 600, fontSize: "var(--font-size-sm)", display: "block", marginBottom: "0.3rem" }}>Keywords</label>
            <input value={keywords} onChange={(e) => setKeywords(e.target.value)}
              placeholder="attention, transformer, BERT"
              style={{ display: "block", width: "100%", padding: "0.5rem", borderRadius: "var(--radius-md)", border: "1px solid var(--color-border)" }} />
          </div>

          <div style={{ marginBottom: "1rem" }}>
            <label style={{ fontWeight: 600, fontSize: "var(--font-size-sm)", display: "block", marginBottom: "0.3rem" }}>Research Goal</label>
            <textarea value={goal} onChange={(e) => setGoal(e.target.value)}
              placeholder="Survey transformer architectures..." rows={3}
              style={{ display: "block", width: "100%", padding: "0.5rem", borderRadius: "var(--radius-md)", border: "1px solid var(--color-border)" }} />
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "1rem", marginBottom: "1rem" }}>
            <div>
              <label style={{ fontWeight: 600, fontSize: "var(--font-size-sm)", display: "block", marginBottom: "0.3rem" }}>Year Start</label>
              <input type="number" value={yearStart} onChange={(e) => setYearStart(Number(e.target.value))}
                min={2015} max={2026}
                style={{ display: "block", width: "100%", padding: "0.5rem", borderRadius: "var(--radius-md)", border: errors.yearStart ? "1px solid var(--color-danger)" : "1px solid var(--color-border)" }} />
              {errors.yearStart && <p style={{ color: "var(--color-danger)", fontSize: "var(--font-size-xs)", marginTop: "0.2rem" }}>{errors.yearStart}</p>}
            </div>
            <div>
              <label style={{ fontWeight: 600, fontSize: "var(--font-size-sm)", display: "block", marginBottom: "0.3rem" }}>Year End</label>
              <input type="number" value={yearEnd} onChange={(e) => setYearEnd(Number(e.target.value))}
                min={2015} max={2026}
                style={{ display: "block", width: "100%", padding: "0.5rem", borderRadius: "var(--radius-md)", border: errors.yearEnd ? "1px solid var(--color-danger)" : "1px solid var(--color-border)" }} />
              {errors.yearEnd && <p style={{ color: "var(--color-danger)", fontSize: "var(--font-size-xs)", marginTop: "0.2rem" }}>{errors.yearEnd}</p>}
            </div>
            <div>
              <label style={{ fontWeight: 600, fontSize: "var(--font-size-sm)", display: "block", marginBottom: "0.3rem" }}>Paper Number</label>
              <input type="number" value={maxPapers} onChange={(e) => setMaxPapers(Number(e.target.value))}
                min={5} max={100}
                style={{ display: "block", width: "100%", padding: "0.5rem", borderRadius: "var(--radius-md)", border: errors.maxPapers ? "1px solid var(--color-danger)" : "1px solid var(--color-border)" }} />
              {errors.maxPapers && <p style={{ color: "var(--color-danger)", fontSize: "var(--font-size-xs)", marginTop: "0.2rem" }}>{errors.maxPapers}</p>}
            </div>
          </div>
        </Card>
      </div>
      <div style={{ flex: 1 }}>
        <h2 className="page-title">Agent Strategy</h2>
        <Card>
          {["Planning Agent", "Search Agent", "Analysis Agent", "Writing Agent"].map((name, i) => (
            <div key={name}>
              <div style={{ padding: "1rem", background: "var(--color-primary-light)", borderRadius: "var(--radius-md)", textAlign: "center", fontWeight: 600 }}>{name}</div>
              {i < 3 && <div style={{ textAlign: "center", padding: "0.3rem" }}>↓</div>}
            </div>
          ))}
        </Card>
        <Button onClick={handleStart} size="lg" style={{ marginTop: "1.5rem", width: "100%" }}>
          Start Agent
        </Button>
      </div>
    </div>
  );
}