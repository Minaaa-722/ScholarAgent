import React, { useEffect, useState } from "react";
import Card from "../components/Card";
import Button from "../components/Button";
import Badge from "../components/Badge";
import LoadingSkeleton from "../components/LoadingSkeleton";
import ConfirmDialog from "../components/ConfirmDialog";
import { useToast } from "../components/Toast";
import { getCredentials, updateCredential, clearCredential } from "../api/client";

const CREDENTIAL_LABELS: Record<string, string> = {
  LLM_API_KEY: "LLM API Key",
  SEMANTIC_SCHOLAR_API_KEY: "Semantic Scholar API Key",
  GOOGLE_SCHOLAR_COOKIE: "Google Scholar Cookie",
};

const CREDENTIAL_HELP: Record<string, string> = {
  LLM_API_KEY: "Required for LLM calls. Get from OpenAI or Anthropic.",
  SEMANTIC_SCHOLAR_API_KEY: "Optional. Provides higher rate limits for paper search.",
  GOOGLE_SCHOLAR_COOKIE: "Optional. Needed for Google Scholar access.",
};

export default function Credentials() {
  const [credentials, setCredentials] = useState<Record<string, { configured: boolean; preview: string }>>({});
  const [loading, setLoading] = useState(true);
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [saving, setSaving] = useState(false);
  const [showClearDialog, setShowClearDialog] = useState<string | null>(null);
  const { showToast } = useToast();

  const fetchCredentials = async () => {
    try {
      const data = await getCredentials();
      setCredentials(data.credentials || {});
    } catch {
      showToast("error", "Failed to load credentials");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchCredentials(); }, []);

  const handleUpdate = async (key: string) => {
    setSaving(true);
    try {
      await updateCredential(key, editValue);
      showToast("success", `${CREDENTIAL_LABELS[key]} updated`);
      setEditingKey(null);
      setEditValue("");
      fetchCredentials();
    } catch {
      showToast("error", "Update failed");
    } finally {
      setSaving(false);
    }
  };

  const handleClear = async (key: string) => {
    setShowClearDialog(null);
    try {
      await clearCredential(key);
      showToast("success", `${CREDENTIAL_LABELS[key]} cleared`);
      fetchCredentials();
    } catch {
      showToast("error", "Clear failed");
    }
  };

  if (loading) {
    return (
      <div>
        <h2 className="page-title">Credentials</h2>
        <LoadingSkeleton variant="card" lines={3} />
      </div>
    );
  }

  const credKeys = Object.keys(CREDENTIAL_LABELS);

  return (
    <div>
      <h2 className="page-title">Credentials</h2>
      <p className="text-secondary mb-lg">Manage API keys and credentials. Keys are stored securely and never shown in plaintext.</p>

      {credKeys.map(key => {
        const cred = credentials[key] || { configured: false, preview: "" };
        return (
          <Card key={key} title={CREDENTIAL_LABELS[key]}
            headerRight={<Badge color={cred.configured ? "green" : "gray"} dot>{cred.configured ? "Configured" : "Not set"}</Badge>}
          >
            <p className="text-secondary" style={{ fontSize: "var(--font-size-sm)", marginBottom: "var(--space-sm)" }}>
              {CREDENTIAL_HELP[key]}
            </p>

            {cred.configured && !editingKey && (
              <p style={{ fontFamily: "monospace", fontSize: "var(--font-size-sm)", marginBottom: "var(--space-sm)" }}>
                {cred.preview || "****"}
              </p>
            )}

            {editingKey === key ? (
              <div style={{ display: "flex", gap: "0.5rem" }}>
                <input
                  type="password"
                  value={editValue}
                  onChange={e => setEditValue(e.target.value)}
                  placeholder="Enter new key..."
                  style={{ flex: 1, padding: "0.4rem", borderRadius: "var(--radius-md)", border: "1px solid var(--color-border)" }}
                />
                <Button size="sm" onClick={() => handleUpdate(key)} loading={saving}>Save</Button>
                <Button variant="ghost" size="sm" onClick={() => setEditingKey(null)}>Cancel</Button>
              </div>
            ) : (
              <div style={{ display: "flex", gap: "0.5rem" }}>
                <Button variant="ghost" size="sm" onClick={() => setEditingKey(key)}>
                  {cred.configured ? "🔄 Update" : "➕ Set Key"}
                </Button>
                {cred.configured && (
                  <Button variant="ghost" size="sm" onClick={() => setShowClearDialog(key)}>🗑 Clear</Button>
                )}
              </div>
            )}
          </Card>
        );
      })}

      <ConfirmDialog
        open={showClearDialog !== null}
        title="Clear Credential?"
        message={`This will clear the ${showClearDialog ? CREDENTIAL_LABELS[showClearDialog] : ""} credential.`}
        confirmLabel="Clear"
        danger
        onConfirm={() => showClearDialog && handleClear(showClearDialog)}
        onCancel={() => setShowClearDialog(null)}
      />
    </div>
  );
}