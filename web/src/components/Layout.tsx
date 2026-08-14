import React from "react";
import { Link, useLocation } from "react-router-dom";

const NAV_ITEMS = [
  { path: "/", label: "Dashboard", icon: "📊" },
  { path: "/create", label: "New Research", icon: "🔬" },
  { path: "/execution", label: "Execution", icon: "⚡" },
  { path: "/explorer", label: "Knowledge", icon: "🧠" },
  { path: "/review", label: "Review", icon: "📝" },
  { path: "/credentials", label: "Credentials", icon: "🔑" },
];

export default function Layout({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  return (
    <div style={{ display: "flex", minHeight: "100vh", fontFamily: "var(--font-family)" }}>
      <nav style={{ width: 220, background: "var(--color-bg-dark)", color: "#fff", padding: "var(--space-md)" }}>
        <h2 style={{ fontSize: "var(--font-size-lg)", marginBottom: "var(--space-xl)" }}>ScholarAgent</h2>
        {NAV_ITEMS.map((item) => (
          <Link key={item.path} to={item.path}
            style={{
              display: "block", padding: "0.6rem 1rem",
              color: location.pathname === item.path ? "#4fc3f7" : "#ccc",
              textDecoration: "none", borderRadius: "var(--radius-md)", marginBottom: "var(--space-xs)",
              background: location.pathname === item.path ? "rgba(79,195,247,0.1)" : "transparent",
            }}>
            {item.icon} {item.label}
          </Link>
        ))}
      </nav>
      <main style={{ flex: 1, padding: "var(--space-xl)", background: "var(--color-bg)" }}>{children}</main>
    </div>
  );
}