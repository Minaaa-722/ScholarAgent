import React, { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { getInitStatus } from "../api/client";
import ConfirmDialog from "./ConfirmDialog";

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
  const navigate = useNavigate();
  const [showInitModal, setShowInitModal] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      try {
        const status = await getInitStatus();
        if (!cancelled) {
          // 仅在非Credentials页面且需要初始化时弹出引导弹窗
          if (status.needs_initialization && location.pathname !== "/credentials") {
            setShowInitModal(true);
          }
        }
      } catch {
        // Silently ignore — if the API is unavailable, don't block the UI
      }
    };
    check();
    return () => { cancelled = true; };
  }, [location.pathname]);

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
        {/* 初始化引导弹窗：仅在非 Credentials 页面且 needs_initialization 时弹出 */}
        <ConfirmDialog
          open={showInitModal}
          title="🔑 API Key 未配置"
          message="系统检测到尚未配置 LLM_API_KEY。请先前往凭据管理页面设置有效的 API Key 后再开始使用 ScholarAgent 的全部功能。"
          confirmLabel="前往 Credentials 页面"
          cancelLabel="稍后再说"
          onConfirm={() => {
            setShowInitModal(false);
            navigate("/credentials");
          }}
          onCancel={() => setShowInitModal(false)}
        />
        {children}
      </main>
    </div>
  );
}