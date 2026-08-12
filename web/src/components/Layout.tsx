import React, { useState } from "react";
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
  const [sidebarOpen, setSidebarOpen] = useState(true);

  return (
    <div className="app-layout" style={{ display: "flex", minHeight: "100vh" }}>
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="hide-desktop"
          onClick={() => setSidebarOpen(false)}
          style={{
            position: "fixed", inset: 0, zIndex: 199,
            background: "var(--color-bg-overlay)",
          }}
        />
      )}

      {/* Sidebar */}
      <nav
        className="sidebar"
        style={{
          width: sidebarOpen ? "var(--sidebar-width)" : 0,
          background: "var(--color-bg-dark)", color: "#fff",
          padding: sidebarOpen ? "var(--space-md)" : 0,
          overflow: "hidden",
          transition: "width var(--transition-normal), padding var(--transition-normal)",
          display: "flex", flexDirection: "column",
          flexShrink: 0, zIndex: 200,
        }}
      >
        {/* Brand */}
        <div className="flex items-center" style={{
          marginBottom: "var(--space-xl)", minHeight: 32,
          justifyContent: "space-between",
        }}>
          {sidebarOpen && (
            <h2 style={{ fontSize: "var(--font-size-lg)", whiteSpace: "nowrap" }}>
              📚 ScholarAgent
            </h2>
          )}
        </div>

        {/* Nav items */}
        {sidebarOpen && (
          <nav style={{ flex: 1 }}>
            {NAV_ITEMS.map((item) => {
              const isActive = location.pathname === item.path;
              return (
                <Link
                  key={item.path}
                  to={item.path}
                  onClick={() => setSidebarOpen(false)}
                  className="sidebar-link"
                  style={{
                    display: "flex", alignItems: "center", gap: "0.5rem",
                    padding: "0.6rem 1rem",
                    color: isActive ? "var(--color-primary-dark)" : "#94a3b8",
                    textDecoration: "none", borderRadius: "var(--radius-md)",
                    marginBottom: "var(--space-xs)",
                    background: isActive ? "rgba(59,130,246,0.12)" : "transparent",
                    transition: "all var(--transition-fast)",
                    fontSize: "var(--font-size-sm)",
                    fontWeight: isActive ? 600 : 400,
                  }}
                >
                  <span style={{ fontSize: "1.1rem", flexShrink: 0 }}>{item.icon}</span>
                  <span className="sidebar-label">{item.label}</span>
                </Link>
              );
            })}
          </nav>
        )}

        {/* Sidebar footer */}
        {sidebarOpen && (
          <div className="sidebar-footer" style={{
            borderTop: "1px solid rgba(255,255,255,0.08)",
            paddingTop: "var(--space-sm)", marginTop: "auto",
            fontSize: "var(--font-size-xs)", color: "var(--color-text-tertiary)",
          }}>
            <p>ScholarAgent v1.0</p>
          </div>
        )}
      </nav>

      {/* Main content */}
      <main className="main-content" style={{
        flex: 1, padding: "var(--space-xl)", background: "var(--color-bg)",
        transition: "background var(--transition-normal)",
        minWidth: 0, /* prevent flex overflow */
        maxWidth: "var(--max-content-width)", margin: "0 auto",
        width: "100%",
      }}>
        {children}
      </main>

      {/* Mobile hamburger */}
      <button
        className="hamburger hide-desktop"
        onClick={() => setSidebarOpen(!sidebarOpen)}
        aria-label={sidebarOpen ? "Close menu" : "Open menu"}
        style={{
          position: "fixed", bottom: 16, right: 16,
          zIndex: 250, width: 44, height: 44,
          borderRadius: "50%", border: "none",
          background: "var(--color-primary)", color: "#fff",
          fontSize: "1.3rem", cursor: "pointer",
          boxShadow: "var(--shadow-lg)",
          display: "none", /* hidden by default, shown in media query */
          alignItems: "center", justifyContent: "center",
        }}
      >
        {sidebarOpen ? "✕" : "☰"}
      </button>

      {/* Responsive styles injected once */}
      <style>{`
        @media (max-width: 768px) {
          .sidebar { position: fixed !important; top: 0; left: 0; height: 100vh; }
          .sidebar-link { padding: 0.75rem 1rem !important; font-size: var(--font-size-md) !important; }
          .hamburger { display: flex !important; }
          .main-content { padding: var(--space-md) !important; }
        }
        @media (min-width: 769px) {
          .sidebar-link:hover { background: rgba(255,255,255,0.06) !important; color: #e2e8f0 !important; }
        }
      `}</style>
    </div>
  );
}