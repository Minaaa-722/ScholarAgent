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

export async function restartSurvey() {
  const res = await fetch(`${API_BASE}/api/survey/restart`, { method: "POST" });
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

export async function getAutoLoadPreferences() {
  const res = await fetch(`${API_BASE}/api/memory/auto-load`);
  return res.json();
}

export async function getMemory() {
  const res = await fetch(`${API_BASE}/api/memory`);
  return res.json();
}

export async function updateMemory(key: string, value: string) {
  const res = await fetch(`${API_BASE}/api/memory`, {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key, value }),
  });
  return res.json();
}

export async function deleteMemory(key: string) {
  const res = await fetch(`${API_BASE}/api/memory/${encodeURIComponent(key)}`, { method: "DELETE" });
  return res.json();
}

export async function clearMemory() {
  const res = await fetch(`${API_BASE}/api/memory`, { method: "DELETE" });
  return res.json();
}

export interface PaperItem {
  title: string;
  authors: string;
  year: string;
  citations: number;
  source: string;
  paper_index: number;
}

export interface PaperListResponse {
  papers: PaperItem[];
  total: number;
}

export async function getPapers(): Promise<PaperListResponse> {
  const res = await fetch(`${API_BASE}/api/survey/papers`);
  if (!res.ok) throw new Error("Failed to fetch papers");
  return res.json();
}

export async function getPaperGraph(): Promise<{ nodes: GraphNode[]; links: GraphLink[] }> {
  const res = await fetch(`${API_BASE}/api/survey/papers/graph`);
  if (!res.ok) throw new Error("Failed to fetch paper graph");
  return res.json();
}

export interface GraphNode {
  id: number;
  label: string;
  group: string;
  size: number;
}

export interface GraphLink {
  source: number;
  target: number;
  weight: number;
}

export async function getPaperDetail(index: number): Promise<PaperItem> {
  const res = await fetch(`${API_BASE}/api/survey/papers/${index}`);
  if (!res.ok) throw new Error("Paper not found");
  return res.json();
}

export async function getCredentials() {
  const res = await fetch(`${API_BASE}/api/credentials`);
  return res.json();
}

export async function updateCredential(key: string, value: string) {
  const res = await fetch(`${API_BASE}/api/credentials`, {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key, value }),
  });
  return res.json();
}

export async function clearCredential(key: string) {
  const res = await fetch(`${API_BASE}/api/credentials/${encodeURIComponent(key)}`, { method: "DELETE" });
  return res.json();
}