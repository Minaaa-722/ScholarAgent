import React from "react";

type ButtonVariant = "primary" | "danger" | "ghost" | "link";
type ButtonSize = "sm" | "md" | "lg";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  icon?: string;
}

const VARIANT_STYLES: Record<ButtonVariant, React.CSSProperties> = {
  primary: { background: "var(--color-primary)", color: "#fff", border: "none" },
  danger: { background: "var(--color-danger)", color: "#fff", border: "none" },
  ghost: { background: "transparent", color: "var(--color-text-primary)", border: "1px solid var(--color-border)" },
  link: { background: "transparent", color: "var(--color-primary)", border: "none", padding: 0, fontWeight: "var(--font-weight-normal)" },
};

const SIZE_STYLES: Record<ButtonSize, React.CSSProperties> = {
  sm: { padding: "0.3rem 0.8rem", fontSize: "var(--font-size-xs)" },
  md: { padding: "0.5rem 1.5rem", fontSize: "var(--font-size-sm)" },
  lg: { padding: "0.8rem 2rem", fontSize: "var(--font-size-md)" },
};

export default function Button({
  variant = "primary", size = "md", loading = false, icon, disabled, children, style, ...rest
}: ButtonProps) {
  return (
    <button
      disabled={disabled || loading}
      style={{
        borderRadius: "var(--radius-md)",
        cursor: (disabled || loading) ? "not-allowed" : "pointer",
        fontWeight: "var(--font-weight-semibold)",
        display: "inline-flex", alignItems: "center", gap: "0.4rem",
        opacity: (disabled && !loading) ? 0.5 : 1,
        transition: "all var(--transition-fast)",
        whiteSpace: "nowrap",
        ...VARIANT_STYLES[variant],
        ...SIZE_STYLES[size],
        ...style,
      }}
      {...rest}
    >
      {loading && <span style={{ animation: "spin 1s linear infinite", display: "inline-block" }}>⟳</span>}
      {!loading && icon && <span>{icon}</span>}
      {children}
    </button>
  );
}