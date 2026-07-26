const API_BASE = "http://localhost:8000";

export async function createSurvey(data: {
  topic: string; keywords?: string; goal?: string; max_papers?: number;
}) {
  const res = await fetch(`${API_BASE}/api/survey`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return res.json();
}

export async function getSurveyStatus() {
  const res = await fetch(`${API_BASE}/api/survey/status`);
  return res.json();
}

export async function interruptSurvey() {
  const res = await fetch(`${API_BASE}/api/survey/interrupt`, { method: "POST" });
  return res.json();
}

export async function resumeSurvey() {
  const res = await fetch(`${API_BASE}/api/survey/resume`, { method: "POST" });
  return res.json();
}

export async function submitFeedback(data: { category: string; content: string }) {
  const res = await fetch(`${API_BASE}/api/feedback`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Feedback submission failed");
  return res.json();
}

export async function getPendingFeedback() {
  const res = await fetch(`${API_BASE}/api/feedback/pending`);
  return res.json();
}

export async function getPaper() {
  const res = await fetch(`${API_BASE}/api/survey/paper`);
  return res.json();
}

export async function getExecutionLog() {
  const res = await fetch(`${API_BASE}/api/survey/log`);
  return res.json();
}