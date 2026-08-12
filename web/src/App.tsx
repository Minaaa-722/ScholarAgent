import React, { createContext, useContext, useState, useEffect, useCallback } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import ResearchCreation from "./pages/ResearchCreation";
import AgentExecution from "./pages/AgentExecution";
import KnowledgeExplorer from "./pages/KnowledgeExplorer";
import FinalReview from "./pages/FinalReview";
import Credentials from "./pages/Credentials";
import HistoryDetail from "./pages/HistoryDetail";
import Layout from "./components/Layout";
import ErrorBoundary from "./components/ErrorBoundary";
import { ToastProvider } from "./components/Toast";

/* ---- Theme Context ---- */
type Theme = "light" | "dark" | "system";

interface ThemeCtx {
  theme: Theme;
  resolved: "light" | "dark";
  setTheme: (t: Theme) => void;
  toggle: () => void;
}

const ThemeContext = createContext<ThemeCtx>({
  theme: "system", resolved: "light",
  setTheme: () => {}, toggle: () => {},
});

export const useTheme = () => useContext(ThemeContext);

function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(() => {
    const saved = localStorage.getItem("scholaragent-theme");
    return (saved === "light" || saved === "dark" || saved === "system") ? saved : "system";
  });

  const [systemDark, setSystemDark] = useState(
    () => window.matchMedia("(prefers-color-scheme: dark)").matches,
  );

  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = (e: MediaQueryListEvent) => setSystemDark(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);

  const resolved = theme === "system" ? (systemDark ? "dark" : "light") : theme;

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", resolved);
    localStorage.setItem("scholaragent-theme", theme);
  }, [resolved, theme]);

  const setTheme = useCallback((t: Theme) => setThemeState(t), []);
  const toggle = useCallback(() => {
    setThemeState(prev => {
      if (prev === "system") return systemDark ? "light" : "dark";
      return prev === "dark" ? "light" : "dark";
    });
  }, [systemDark]);

  return (
    <ThemeContext.Provider value={{ theme, resolved, setTheme, toggle }}>
      {children}
    </ThemeContext.Provider>
  );
}

function App() {
  return (
    <BrowserRouter>
      <ThemeProvider>
        <ErrorBoundary>
          <ToastProvider>
            <Layout>
              <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/create" element={<ResearchCreation />} />
                <Route path="/execution" element={<AgentExecution />} />
                <Route path="/explorer" element={<KnowledgeExplorer />} />
                <Route path="/review" element={<FinalReview />} />
                <Route path="/credentials" element={<Credentials />} />
                <Route path="/history/:id" element={<HistoryDetail />} />
                <Route path="*" element={<Navigate to="/" />} />
              </Routes>
            </Layout>
          </ToastProvider>
        </ErrorBoundary>
      </ThemeProvider>
    </BrowserRouter>
  );
}
export default App;