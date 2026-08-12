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
    <div className="flex flex-col items-center" style={{
      padding: "var(--space-3xl) var(--space-lg)", color: "var(--color-text-secondary)",
      animation: "fadeIn 0.3s ease",
    }}>
      <div style={{ fontSize: "3rem", marginBottom: "var(--space-md)", lineHeight: 1 }}>{icon}</div>
      <h3 style={{ margin: "0 0 var(--space-sm)", color: "var(--color-text-primary)" }}>{title}</h3>
      {description && (
        <p className="text-center" style={{ margin: "0 0 var(--space-lg)", maxWidth: 400, lineHeight: "var(--line-height-relaxed)", fontSize: "var(--font-size-sm)" }}>
          {description}
        </p>
      )}
      {actionLabel && onAction && <Button onClick={onAction}>{actionLabel}</Button>}
    </div>
  );
}