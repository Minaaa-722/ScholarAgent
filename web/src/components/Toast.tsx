import React, { createContext, useContext, useState, useCallback, useEffect } from "react";

type ToastType = "success" | "error" | "info" | "warning";

interface ToastItem {
  id: number;
  type: ToastType;
  message: string;
}

interface ToastContextValue {
  showToast: (type: ToastType, message: string) => void;
}

const ToastContext = createContext<ToastContextValue>({ showToast: () => {} });
export const useToast = () => useContext(ToastContext);

const TOAST_COLORS: Record<ToastType, { bg: string; border: string; icon: string }> = {
  success: { bg: "var(--color-success-light)", border: "var(--color-success)", icon: "✓" },
  error: { bg: "var(--color-danger-light)", border: "var(--color-danger)", icon: "✕" },
  info: { bg: "var(--color-info-light)", border: "var(--color-info)", icon: "ℹ" },
  warning: { bg: "var(--color-warning-light)", border: "var(--color-warning)", icon: "⚠" },
};

let nextId = 1;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const showToast = useCallback((type: ToastType, message: string) => {
    const id = nextId++;
    setToasts(prev => [...prev, { id, type, message }]);
  }, []);

  const removeToast = (id: number) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  };

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      <div style={{
        position: "fixed", top: 16, right: 16, zIndex: "var(--z-toast)",
        display: "flex", flexDirection: "column", gap: 8, pointerEvents: "none",
      }}>
        {toasts.map(toast => (
          <ToastItem key={toast.id} toast={toast} onDismiss={() => removeToast(toast.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

function ToastItem({ toast, onDismiss }: { toast: ToastItem; onDismiss: () => void }) {
  const c = TOAST_COLORS[toast.type];

  useEffect(() => {
    const timer = setTimeout(onDismiss, 4000);
    return () => clearTimeout(timer);
  }, [onDismiss]);

  return (
    <div
      onClick={onDismiss}
      role="alert"
      style={{
        background: c.bg, borderLeft: `4px solid ${c.border}`,
        borderRadius: "var(--radius-md)", padding: "0.8rem 1rem",
        boxShadow: "var(--shadow-md)", minWidth: 280, maxWidth: 400,
        display: "flex", alignItems: "center", gap: "0.5rem",
        cursor: "pointer", pointerEvents: "auto",
        animation: "slideIn 0.3s ease",
        transition: "opacity var(--transition-fast)",
      }}
    >
      <span style={{ flexShrink: 0 }}>{c.icon}</span>
      <span style={{ fontSize: "var(--font-size-sm)", color: "var(--color-text-primary)" }}>{toast.message}</span>
    </div>
  );
}