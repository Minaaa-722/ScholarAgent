import React from "react";
import Button from "./Button";

interface EmptyStateProps {
  icon: string;
  title: string;
  description?: string;
  actionLabel?: string;
  onAction?: () => void;
}

export default function EmptyState({ icon, title, description, actionLabel, onAction }: EmptyStateProps) {
  return (
    <div style={{ textAlign: "center", padding: "var(--space-xl) var(--space-lg)", color: "var(--color-text-secondary)" }}>
      <div style={{ fontSize: "3rem", marginBottom: "var(--space-md)" }}>{icon}</div>
      <h3 style={{ margin: "0 0 var(--space-sm)", color: "var(--color-text-primary)" }}>{title}</h3>
      {description && <p style={{ margin: "0 0 var(--space-lg)", maxWidth: 400, marginInline: "auto" }}>{description}</p>}
      {actionLabel && onAction && <Button onClick={onAction}>{actionLabel}</Button>}
    </div>
  );
}