import React, { useEffect, useState } from "react";
import Card from "../components/Card";
import Button from "../components/Button";
import Badge from "../components/Badge";
import LoadingSkeleton from "../components/LoadingSkeleton";
import EmptyState from "../components/EmptyState";
import ConfirmDialog from "../components/ConfirmDialog";
import { useToast } from "../components/Toast";
import { getMemory, updateMemory, deleteMemory, clearMemory } from "../api/client";

interface Preference {
  key: string;
  value: string;
  updated_at: string;
}

export default function MemoryManager() {
  const [prefs, setPrefs] = useState<Preference[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [saving, setSaving] = useState(false);
  const [showClearDialog, setShowClearDialog] = useState(false);
  const [clearing, setClearing] = useState(false);
  const { showToast } = useToast();

  const fetchPrefs = async () => {
    try {
      const data = await getMemory();
      setPrefs(data.preferences || []);
    } catch {
      showToast("error", "Failed to load preferences");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchPrefs(); }, []);

  const handleUpdate = async (key: string) => {
    setSaving(true);
    try {
      await updateMemory(key, editValue);
      showToast("success", "Preference updated");
      setEditingKey(null);
      fetchPrefs();
    } catch {
      showToast("error", "Update failed");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (key: string) => {
    try {
      await deleteMemory(key);
      showToast("success", "Preference deleted");
      fetchPrefs();
    } catch {
      showToast("error", "Delete failed");
    }
  };

  const handleClearAll = async () => {
    setShowClearDialog(false);
    setClearing(true);
    try {
      await clearMemory();
      showToast("success", "All preferences cleared");
      setPrefs([]);
    } catch {
      showToast("error", "Clear failed");
    } finally {
      setClearing(false);
    }
  };

  if (loading) {
    return (
      <div>
        <h2 className="page-title">Memory Manager</h2>
        <LoadingSkeleton variant="card" lines={4} />
      </div>
    );
  }

  return (
    <div>
      <h2 className="page-title">Memory Manager</h2>
      <p className="text-secondary mb-lg">View and manage your saved preferences. These are automatically loaded when creating new research tasks.</p>

      {prefs.length === 0 ? (
        <EmptyState icon="🧠" title="No Saved Preferences" description="Preferences will appear here as you use ScholarAgent." />
      ) : (
        <>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "var(--space-md)" }}>
            <p className="text-secondary">{prefs.length} preference{prefs.length !== 1 ? "s" : ""}</p>
            <Button variant="danger" size="sm" onClick={() => setShowClearDialog(true)}>Clear All</Button>
          </div>
          {prefs.map(p => (
            <Card key={p.key} title={p.key} headerRight={<Badge color="gray">{p.updated_at}</Badge>}>
              {editingKey === p.key ? (
                <div style={{ display: "flex", gap: "0.5rem" }}>
                  <input value={editValue} onChange={e => setEditValue(e.target.value)}
                    style={{ flex: 1, padding: "0.4rem", borderRadius: "var(--radius-md)", border: "1px solid var(--color-border)" }} />
                  <Button size="sm" onClick={() => handleUpdate(p.key)} loading={saving}>Save</Button>
                  <Button variant="ghost" size="sm" onClick={() => setEditingKey(null)}>Cancel</Button>
                </div>
              ) : (
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <code style={{ fontSize: "var(--font-size-sm)" }}>{p.value}</code>
                  <div style={{ display: "flex", gap: "0.3rem" }}>
                    <Button variant="ghost" size="sm" onClick={() => { setEditingKey(p.key); setEditValue(p.value); }}>✏ Edit</Button>
                    <Button variant="ghost" size="sm" onClick={() => handleDelete(p.key)}>🗑 Delete</Button>
                  </div>
                </div>
              )}
            </Card>
          ))}
        </>
      )}

      <ConfirmDialog
        open={showClearDialog}
        title="Clear All Preferences?"
        message="This will permanently delete all saved preferences. This action cannot be undone."
        confirmLabel="Clear All"
        danger
        onConfirm={handleClearAll}
        onCancel={() => setShowClearDialog(false)}
        loading={clearing}
      />
    </div>
  );
}