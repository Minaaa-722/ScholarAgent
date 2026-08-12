import React from "react";

type BadgeColor = "green" | "red" | "orange" | "blue" | "gray";

const BADGE_COLORS: Record<BadgeColor, { bg: string; text: string }> = {
  green: { bg: "var(--color-success-light)", text: "var(--color-success-dark)" },
  red: { bg: "var(--color-danger-light)", text: "var(--color-danger-dark)" },
  orange: { bg: "var(--color-warning-light)", text: "var(--color-warning-dark)" },
  blue: { bg: "var(--color-primary-light)", text: "var(--color-primary-dark)" },
  gray: { bg: "var(--color-border)", text: "var(--color-text-tertiary)" },
};

interface BadgeProps {
  color?: BadgeColor;
  dot?: boolean;
  children: React.ReactNode;
}

export default function Badge({ color = "gray", dot, children }: BadgeProps) {
  const c = BADGE_COLORS[color];
  return (
    <span className="flex items-center" style={{
      gap: "0.3rem",
      background: c.bg, color: c.text,
      padding: "0.15rem 0.5rem", borderRadius: "var(--radius-sm)",
      fontSize: "var(--font-size-xs)", fontWeight: "var(--font-weight-semibold)",
      lineHeight: "1.4",
    }}>
      {dot && <span style={{ width: 6, height: 6, borderRadius: "50%", background: c.text, display: "inline-block", flexShrink: 0 }} />}
      {children}
    </span>
  );
}