import React from "react";
import { Link, useLocation } from "react-router-dom";

const NAV_ITEMS = [
  { path: "/", label: "Dashboard", icon: "📊" },
  { path: "/create", label: "New Research", icon: "🔬" },
  { path: "/execution", label: "Execution", icon: "⚡" },
  { path: "/explorer", label: "Knowledge", icon: "🧠" },
  { path: "/review", label: "Review", icon: "📝" },
];

export default function Layout({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  return (
    <div style={{ display: "flex", minHeight: "100vh", fontFamily: "system-ui, sans-serif" }}>
      <nav style={{ width: 220, background: "#1a1a2e", color: "#fff", padding: "1rem" }}>
        <h2 style={{ fontSize: "1.2rem", marginBottom: "2rem" }}>ScholarAgent</h2>
        {NAV_ITEMS.map((item) => (
          <Link key={item.path} to={item.path}
            style={{
              display: "block", padding: "0.6rem 1rem",
              color: location.pathname === item.path ? "#4fc3f7" : "#ccc",
              textDecoration: "none", borderRadius: 6, marginBottom: "0.3rem",
              background: location.pathname === item.path ? "rgba(79,195,247,0.1)" : "transparent",
            }}>
            {item.icon} {item.label}
          </Link>
        ))}
      </nav>
      <main style={{ flex: 1, padding: "2rem", background: "#f5f5f5" }}>{children}</main>
    </div>
  );
}