import React, { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { getInitStatus } from "../api/client";

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
  const [needsInit, setNeedsInit] = useState(false);
  const [initLoading, setInitLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      try {
        const status = await getInitStatus();
        if (!cancelled) {
          setNeedsInit(status.needs_initialization);
        }
      } catch {
        // Silently ignore — if the API is unavailable, don't block the UI
      } finally {
        if (!cancelled) {
          setInitLoading(false);
        }
      }
    };
    check();
    return () => { cancelled = true; };
  }, []);

  const isCredentialsPage = location.pathname === "/credentials";
  const showBanner = needsInit && !initLoading && !isCredentialsPage;

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
      <main style={{ flex: 1, padding: "var(--space-xl)", background: "var(--color-bg)" }}>
        {showBanner && (
          <div
            style={{
              padding: "0.75rem 1rem",
              marginBottom: "var(--space-lg, 16px)",
              background: "#fff3cd",
              border: "1px solid #ffc107",
              borderRadius: "var(--radius-md, 6px)",
              color: "#856404",
              fontSize: "var(--font-size-sm, 14px)",
              display: "flex",
              alignItems: "center",
              gap: "8px",
            }}
          >
            <span style={{ fontSize: "18px" }}>🔑</span>
            <span style={{ flex: 1 }}>
              LLM API Key 未配置。请先前往{" "}
              <Link
                to="/credentials"
                style={{ color: "#856404", fontWeight: 600, textDecoration: "underline" }}
              >
                凭据管理页面
              </Link>{" "}
              配置 API Key 后再开始使用。
            </span>
            <button
              onClick={() => setNeedsInit(false)}
              style={{
                background: "none", border: "none", cursor: "pointer",
                fontSize: "18px", color: "#856404", padding: "0 4px",
                lineHeight: 1,
              }}
              aria-label="关闭提示"
            >
              &times;
            </button>
          </div>
        )}
        {children}
      </main>
    </div>
  );
}