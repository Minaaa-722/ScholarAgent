import React from "react";
import Button from "./Button";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  loading?: boolean;
}

export default function ConfirmDialog({
  open, title, message, confirmLabel = "Confirm", cancelLabel = "Cancel",
  danger = false, onConfirm, onCancel, loading = false,
}: ConfirmDialogProps) {
  if (!open) return null;
  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 9998,
      background: "rgba(0,0,0,0.4)", display: "flex",
      alignItems: "center", justifyContent: "center",
    }} onClick={onCancel}>
      <div style={{
        background: "var(--color-bg-card)", borderRadius: "var(--radius-lg)",
        padding: "var(--space-xl)", maxWidth: 420, width: "90%",
        boxShadow: "var(--shadow-lg)",
      }} onClick={e => e.stopPropagation()}>
        <h3 style={{ margin: "0 0 var(--space-sm)" }}>{title}</h3>
        <p style={{ color: "var(--color-text-secondary)", margin: "0 0 var(--space-lg)" }}>{message}</p>
        <div style={{ display: "flex", gap: "var(--space-sm)", justifyContent: "flex-end" }}>
          <Button variant="ghost" onClick={onCancel} disabled={loading}>{cancelLabel}</Button>
          <Button variant={danger ? "danger" : "primary"} onClick={onConfirm} loading={loading}>{confirmLabel}</Button>
        </div>
      </div>
    </div>
  );
}