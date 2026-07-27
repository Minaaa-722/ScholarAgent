import React from "react";

interface CardProps {
  title?: React.ReactNode;
  headerRight?: React.ReactNode;
  borderColor?: string;
  children: React.ReactNode;
  padding?: string;
  style?: React.CSSProperties;
}

export default function Card({ title, headerRight, borderColor, children, padding, style }: CardProps) {
  return (
    <div style={{
      background: "var(--color-bg-card)",
      borderRadius: "var(--radius-lg)",
      boxShadow: "var(--shadow-sm)",
      borderLeft: borderColor ? `4px solid ${borderColor}` : undefined,
      padding: padding || "var(--space-md) var(--space-lg)",
      marginBottom: "var(--space-md)",
      ...style,
    }}>
      {title && (
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "var(--space-sm)" }}>
          <h4 style={{ margin: 0, fontSize: "var(--font-size-md)", fontWeight: "var(--font-weight-semibold)", color: "var(--color-text-primary)" }}>
            {title}
          </h4>
          {headerRight}
        </div>
      )}
      {children}
    </div>
  );
}