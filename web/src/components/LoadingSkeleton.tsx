import React from "react";

type SkeletonVariant = "text" | "card" | "table-row";

interface SkeletonProps {
  variant?: SkeletonVariant;
  lines?: number;
  width?: string;
  height?: string;
}

const SKELETON_STYLE: React.CSSProperties = {
  background: "linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%)",
  backgroundSize: "200% 100%",
  animation: "shimmer 1.5s infinite",
  borderRadius: "var(--radius-sm)",
};

export default function LoadingSkeleton({ variant = "text", lines = 3, width, height }: SkeletonProps) {
  if (variant === "card") {
    return (
      <div style={{ background: "var(--color-bg-card)", borderRadius: "var(--radius-lg)", padding: "var(--space-lg)", boxShadow: "var(--shadow-sm)", marginBottom: "var(--space-md)" }}>
        <div style={{ ...SKELETON_STYLE, height: 20, width: "60%", marginBottom: "var(--space-md)" }} />
        <div style={{ ...SKELETON_STYLE, height: 14, width: "100%", marginBottom: "var(--space-sm)" }} />
        <div style={{ ...SKELETON_STYLE, height: 14, width: "80%", marginBottom: "var(--space-sm)" }} />
        <div style={{ ...SKELETON_STYLE, height: 14, width: "90%" }} />
      </div>
    );
  }

  return (
    <div>
      {Array.from({ length: lines }).map((_, i) => (
        <div key={i} style={{
          ...SKELETON_STYLE,
          height: height || 14,
          width: width || (i === lines - 1 ? "60%" : "100%"),
          marginBottom: i < lines - 1 ? "var(--space-sm)" : 0,
        }} />
      ))}
    </div>
  );
}