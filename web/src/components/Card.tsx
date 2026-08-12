import React from "react";

interface CardProps {
  title?: React.ReactNode;
  headerRight?: React.ReactNode;
  borderColor?: string;
  children: React.ReactNode;
  padding?: string;
  style?: React.CSSProperties;
  hoverable?: boolean;
  onClick?: () => void;
}

export default function Card({
  title, headerRight, borderColor, children, padding, style, hoverable, onClick,
}: CardProps) {
  return (
    <div
      onClick={onClick}
      style={{
        background: "var(--color-bg-card)",
        borderRadius: "var(--radius-lg)",
        boxShadow: "var(--shadow-sm)",
        borderLeft: borderColor ? `4px solid ${borderColor}` : undefined,
        padding: padding || "var(--space-md) var(--space-lg)",
        marginBottom: "var(--space-md)",
        transition: "box-shadow var(--transition-normal), transform var(--transition-normal)",
        cursor: onClick ? "pointer" : undefined,
        ...(hoverable ? {
          ":hover": { boxShadow: "var(--shadow-md)", transform: "translateY(-1px)" },
        } : {}),
        ...style,
      }}
    >
      {title && (
        <div className="flex justify-between items-center mb-sm" style={{ gap: "var(--space-sm)" }}>
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