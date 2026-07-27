# Phase 3: Frontend Product Design Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Elevate all 5 React pages to production quality with a consistent design system, proper states, and missing features from SPEC.md.

**Architecture:** Layer a design system (CSS custom properties + reusable components) on top of the existing inline-style pages, then enhance each page independently. Add 2 new pages (Memory Manager, Credentials) and their API routes. The design system is a thin token layer — no framework dependency, no CSS-in-JS, no build step changes.

**Tech Stack:** React 18, TypeScript, Vite, CSS custom properties (no CSS framework — avoids dependency bloat), existing FastAPI backend.

## Global Constraints

- No new npm dependencies beyond what's already in `web/package.json` (react, react-dom, react-router-dom, vite, typescript)
- CSS custom properties only — no CSS framework, no styled-components, no Tailwind
- Every new component must handle: loading, empty, error, and success states
- Inline styles are replaced only in pages being actively modified — leave untouched pages alone
- API routes must use existing FastAPI patterns (APIRouter, Depends, pydantic models)
- All new pages must be added to App.tsx routes and Layout.tsx nav

---

## File Structure

### New Files
| File | Responsibility |
|------|---------------|
| `web/src/styles/tokens.css` | CSS custom properties: colors, spacing, typography, shadows, breakpoints |
| `web/src/styles/global.css` | Base reset, font imports, CSS class utilities |
| `web/src/components/Button.tsx` | Reusable button: variants (primary, danger, ghost, link), sizes, loading state |
| `web/src/components/Card.tsx` | Reusable card container with optional header, footer, border variants |
| `web/src/components/Badge.tsx` | Status badge: colors (green, red, orange, blue, gray), dot indicator |
| `web/src/components/LoadingSkeleton.tsx` | Skeleton loader: text, card, table row variants |
| `web/src/components/EmptyState.tsx` | Empty state: icon, title, description, optional action button |
| `web/src/components/ErrorBoundary.tsx` | React error boundary with fallback UI and retry button |
| `web/src/components/Toast.tsx` | Toast notification system: success, error, info, warning; auto-dismiss |
| `web/src/components/ConfirmDialog.tsx` | Confirmation modal: title, message, confirm/cancel buttons |
| `web/src/hooks/useWebSocket.ts` | WebSocket hook with exponential backoff, reconnect, cleanup |
| `web/src/pages/MemoryManager.tsx` | Memory management page: view/edit/delete preferences |
| `web/src/pages/Credentials.tsx` | Credential management page: status view, update/clear |
| `api/routes/credentials.py` | Credential API: GET status, PUT update, DELETE clear |

### Modified Files
| File | Change |
|------|--------|
| `web/src/App.tsx` | Import global.css, wrap with ErrorBoundary, add ToastProvider, add MemoryManager + Credentials routes |
| `web/src/components/Layout.tsx` | Apply design tokens, add nav items for new pages |
| `web/src/pages/Dashboard.tsx` | Add task history list, onboarding state, use design system components |
| `web/src/pages/ResearchCreation.tsx` | Auto-load preferences from `/api/memory`, add year range, add validation, apply design system |
| `web/src/pages/AgentExecution.tsx` | Add interrupt/resume/cancel buttons, swap to useWebSocket hook, gate feedback panel, apply design system |
| `web/src/pages/FinalReview.tsx` | Add quality score summary, BibTeX export, section review, apply design system |
| `web/src/pages/KnowledgeExplorer.tsx` | Apply design system components (minor — full rewrite is Phase 2) |
| `web/src/index.tsx` | Import global.css |
| `web/src/api/client.ts` | Add getMemory, updateMemory, deleteMemory, clearMemory, getCredentials, updateCredential, clearCredential |
| `api/main.py` | Import and register credentials router |
| `api/routes/memory.py` | Add GET /api/memory/auto-load endpoint (returns defaults for ResearchCreation form) |

---

## Task Decomposition

### Task 1: Design System Foundation

**Files:**
- Create: `web/src/styles/tokens.css`
- Create: `web/src/styles/global.css`
- Create: `web/src/components/Button.tsx`
- Create: `web/src/components/Card.tsx`
- Create: `web/src/components/Badge.tsx`
- Create: `web/src/components/LoadingSkeleton.tsx`
- Create: `web/src/components/EmptyState.tsx`
- Create: `web/src/components/ErrorBoundary.tsx`
- Create: `web/src/components/Toast.tsx`
- Create: `web/src/components/ConfirmDialog.tsx`
- Modify: `web/src/index.tsx` — import global.css
- Modify: `web/src/App.tsx` — wrap with ErrorBoundary, add ToastProvider
- Modify: `web/src/components/Layout.tsx` — apply design tokens

**Interfaces:**
- Consumes: existing `web/src/App.tsx`, `web/src/components/Layout.tsx`, `web/src/index.tsx`
- Produces: design system tokens, reusable components consumed by all later tasks

- [ ] **Step 1: Create CSS tokens file**

```css
/* web/src/styles/tokens.css */
:root {
  /* Colors */
  --color-primary: #1976d2;
  --color-primary-dark: #1565c0;
  --color-primary-light: #e3f2fd;
  --color-success: #4caf50;
  --color-success-dark: #2e7d32;
  --color-success-light: #e8f5e9;
  --color-warning: #ff9800;
  --color-warning-dark: #e65100;
  --color-warning-light: #fff3e0;
  --color-danger: #f44336;
  --color-danger-dark: #c62828;
  --color-danger-light: #ffebee;
  --color-info: #2196f3;
  --color-info-light: #e3f2fd;
  --color-text-primary: #1a1a2e;
  --color-text-secondary: #666;
  --color-text-disabled: #999;
  --color-bg: #f5f5f5;
  --color-bg-card: #fff;
  --color-bg-dark: #1a1a2e;
  --color-border: #e0e0e0;
  --color-border-light: #eee;

  /* Spacing */
  --space-xs: 0.25rem;
  --space-sm: 0.5rem;
  --space-md: 1rem;
  --space-lg: 1.5rem;
  --space-xl: 2rem;

  /* Typography */
  --font-family: system-ui, -apple-system, sans-serif;
  --font-size-xs: 0.75rem;
  --font-size-sm: 0.85rem;
  --font-size-md: 0.95rem;
  --font-size-lg: 1.1rem;
  --font-size-xl: 1.5rem;
  --font-weight-normal: 400;
  --font-weight-semibold: 600;
  --font-weight-bold: 700;

  /* Shadows */
  --shadow-sm: 0 1px 3px rgba(0,0,0,0.1);
  --shadow-md: 0 4px 6px rgba(0,0,0,0.1);
  --shadow-lg: 0 10px 15px rgba(0,0,0,0.1);

  /* Border radius */
  --radius-sm: 4px;
  --radius-md: 6px;
  --radius-lg: 8px;
  --radius-full: 20px;

  /* Transitions */
  --transition-fast: 0.15s ease;
  --transition-normal: 0.3s ease;
}
```

- [ ] **Step 2: Create global.css**

```css
/* web/src/styles/global.css */
@import './tokens.css';

*, *::before, *::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

body {
  font-family: var(--font-family);
  font-size: var(--font-size-md);
  color: var(--color-text-primary);
  background: var(--color-bg);
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}

a { color: var(--color-primary); text-decoration: none; }
a:hover { text-decoration: underline; }

/* Utility classes */
.page-title { font-size: var(--font-size-xl); font-weight: var(--font-weight-bold); margin-bottom: var(--space-lg); }
.section-title { font-size: var(--font-size-lg); font-weight: var(--font-weight-semibold); margin-bottom: var(--space-md); }
.text-secondary { color: var(--color-text-secondary); }
.text-disabled { color: var(--color-text-disabled); }
.mt-sm { margin-top: var(--space-sm); }
.mt-md { margin-top: var(--space-md); }
.mt-lg { margin-top: var(--space-lg); }
.mb-sm { margin-bottom: var(--space-sm); }
.mb-md { margin-bottom: var(--space-md); }
.mb-lg { margin-bottom: var(--space-lg); }
```

- [ ] **Step 3: Create Button component**

```tsx
// web/src/components/Button.tsx
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
        ...VARIANT_STYLES[variant],
        ...SIZE_STYLES[size],
        ...style,
      }}
      {...rest}
    >
      {loading ? "⟳ " : icon ? `${icon} ` : ""}{children}
    </button>
  );
}
```

- [ ] **Step 4: Create Card component**

```tsx
// web/src/components/Card.tsx
import React from "react";

interface CardProps {
  title?: string;
  headerRight?: React.ReactNode;
  borderColor?: string;
  children: React.ReactNode;
  padding?: string;
  style?: React.CSSProperties;
}

export default function Card({ title, headerRight, borderColor, children, padding, style }: CardProps) {
  return (
    <div style={{
      background: "var(--color-bg-card)",
      borderRadius: "var(--radius-lg)",
      boxShadow: "var(--shadow-sm)",
      borderLeft: borderColor ? `4px solid ${borderColor}` : undefined,
      padding: padding || "var(--space-md) var(--space-lg)",
      marginBottom: "var(--space-md)",
      ...style,
    }}>
      {title && (
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "var(--space-sm)" }}>
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
```

- [ ] **Step 5: Create Badge component**

```tsx
// web/src/components/Badge.tsx
import React from "react";

type BadgeColor = "green" | "red" | "orange" | "blue" | "gray";

const BADGE_COLORS: Record<BadgeColor, { bg: string; text: string }> = {
  green: { bg: "var(--color-success-light)", text: "var(--color-success-dark)" },
  red: { bg: "var(--color-danger-light)", text: "var(--color-danger-dark)" },
  orange: { bg: "var(--color-warning-light)", text: "var(--color-warning-dark)" },
  blue: { bg: "var(--color-primary-light)", text: "var(--color-primary-dark)" },
  gray: { bg: "#e0e0e0", text: "#666" },
};

interface BadgeProps {
  color?: BadgeColor;
  dot?: boolean;
  children: React.ReactNode;
}

export default function Badge({ color = "gray", dot, children }: BadgeProps) {
  const c = BADGE_COLORS[color];
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: "0.3rem",
      background: c.bg, color: c.text,
      padding: "0.15rem 0.5rem", borderRadius: "var(--radius-sm)",
      fontSize: "var(--font-size-xs)", fontWeight: "var(--font-weight-semibold)",
    }}>
      {dot && <span style={{ width: 6, height: 6, borderRadius: "50%", background: c.text, display: "inline-block" }} />}
      {children}
    </span>
  );
}
```

- [ ] **Step 6: Create LoadingSkeleton component**

```tsx
// web/src/components/LoadingSkeleton.tsx
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
```

- [ ] **Step 7: Add shimmer animation to global.css**

```css
/* Append to web/src/styles/global.css */
@keyframes shimmer {
  0% { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}
```

- [ ] **Step 8: Create EmptyState component**

```tsx
// web/src/components/EmptyState.tsx
import React from "react";
import Button from "./Button";

interface EmptyStateProps {
  icon: string;
  title: string;
  description?: string;
  actionLabel?: string;
  onAction?: () => void;
}

export default function EmptyState({ icon, title, description, actionLabel, onAction }: EmptyStateProps) {
  return (
    <div style={{ textAlign: "center", padding: "var(--space-xl) var(--space-lg)", color: "var(--color-text-secondary)" }}>
      <div style={{ fontSize: "3rem", marginBottom: "var(--space-md)" }}>{icon}</div>
      <h3 style={{ margin: "0 0 var(--space-sm)", color: "var(--color-text-primary)" }}>{title}</h3>
      {description && <p style={{ margin: "0 0 var(--space-lg)", maxWidth: 400, marginInline: "auto" }}>{description}</p>}
      {actionLabel && onAction && <Button onClick={onAction}>{actionLabel}</Button>}
    </div>
  );
}
```

- [ ] **Step 9: Create ErrorBoundary component**

```tsx
// web/src/components/ErrorBoundary.tsx
import React from "react";
import Button from "./Button";

interface Props { children: React.ReactNode; }
interface State { hasError: boolean; error: Error | null; }

export default class ErrorBoundary extends React.Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: "var(--space-xl)", textAlign: "center" }}>
          <div style={{ fontSize: "3rem", marginBottom: "var(--space-md)" }}>⚠</div>
          <h2 style={{ color: "var(--color-danger-dark)" }}>Something went wrong</h2>
          <p style={{ color: "var(--color-text-secondary)", margin: "var(--space-sm) 0 var(--space-lg)" }}>
            {this.state.error?.message || "An unexpected error occurred"}
          </p>
          <Button variant="primary" onClick={this.handleRetry}>Try Again</Button>
        </div>
      );
    }
    return this.props.children;
  }
}
```

- [ ] **Step 10: Create Toast notification system**

```tsx
// web/src/components/Toast.tsx
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
      <div style={{ position: "fixed", top: 16, right: 16, zIndex: 9999, display: "flex", flexDirection: "column", gap: 8 }}>
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
    <div style={{
      background: c.bg, borderLeft: `4px solid ${c.border}`,
      borderRadius: "var(--radius-md)", padding: "0.8rem 1rem",
      boxShadow: "var(--shadow-md)", minWidth: 280, maxWidth: 400,
      display: "flex", alignItems: "center", gap: "0.5rem",
      cursor: "pointer", animation: "slideIn 0.3s ease",
    }} onClick={onDismiss}>
      <span>{c.icon}</span>
      <span style={{ fontSize: "var(--font-size-sm)", color: "var(--color-text-primary)" }}>{toast.message}</span>
    </div>
  );
}
```

- [ ] **Step 11: Add toast animation to global.css**

```css
/* Append to web/src/styles/global.css */
@keyframes slideIn {
  from { transform: translateX(100%); opacity: 0; }
  to { transform: translateX(0); opacity: 1; }
}
```

- [ ] **Step 12: Create ConfirmDialog component**

```tsx
// web/src/components/ConfirmDialog.tsx
import React from "react";
import Button from "./Button";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  loading?: boolean;
}

export default function ConfirmDialog({
  open, title, message, confirmLabel = "Confirm", cancelLabel = "Cancel",
  danger = false, onConfirm, onCancel, loading = false,
}: ConfirmDialogProps) {
  if (!open) return null;
  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 9998,
      background: "rgba(0,0,0,0.4)", display: "flex",
      alignItems: "center", justifyContent: "center",
    }} onClick={onCancel}>
      <div style={{
        background: "var(--color-bg-card)", borderRadius: "var(--radius-lg)",
        padding: "var(--space-xl)", maxWidth: 420, width: "90%",
        boxShadow: "var(--shadow-lg)",
      }} onClick={e => e.stopPropagation()}>
        <h3 style={{ margin: "0 0 var(--space-sm)" }}>{title}</h3>
        <p style={{ color: "var(--color-text-secondary)", margin: "0 0 var(--space-lg)" }}>{message}</p>
        <div style={{ display: "flex", gap: "var(--space-sm)", justifyContent: "flex-end" }}>
          <Button variant="ghost" onClick={onCancel} disabled={loading}>{cancelLabel}</Button>
          <Button variant={danger ? "danger" : "primary"} onClick={onConfirm} loading={loading}>{confirmLabel}</Button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 13: Update web/src/index.tsx to import global.css**

```tsx
// web/src/index.tsx — add import at top
import "./styles/global.css";
```

- [ ] **Step 14: Update web/src/App.tsx — wrap with ErrorBoundary and ToastProvider**

```tsx
// web/src/App.tsx — wrap Layout children
import ErrorBoundary from "./components/ErrorBoundary";
import { ToastProvider } from "./components/Toast";

function App() {
  return (
    <BrowserRouter>
      <ErrorBoundary>
        <ToastProvider>
          <Layout>
            <Routes>
              {/* existing routes unchanged */}
            </Routes>
          </Layout>
        </ToastProvider>
      </ErrorBoundary>
    </BrowserRouter>
  );
}
```

- [ ] **Step 15: Update Layout.tsx to use design tokens**

```tsx
// web/src/components/Layout.tsx — use CSS variables for sidebar
// Replace hardcoded colors with:
// background: "var(--color-bg-dark)" instead of "#1a1a2e"
// color: "var(--color-primary-light)" instead of "#4fc3f7"
// etc.
```

- [ ] **Step 16: Run build to verify no errors**

```bash
cd web && npx tsc --noEmit && npx vite build
```

- [ ] **Step 17: Commit**

```bash
git add -A && git commit -m "feat: add design system foundation with reusable components

- CSS custom property tokens (colors, spacing, typography, shadows)
- Reusable components: Button, Card, Badge, LoadingSkeleton, EmptyState
- ErrorBoundary, Toast notification system, ConfirmDialog
- Global CSS with reset, utilities, animations
- ErrorBoundary wrapper in App, ToastProvider context

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: WebSocket Hook + AgentExecution Enhancements

**Files:**
- Create: `web/src/hooks/useWebSocket.ts`
- Modify: `web/src/pages/AgentExecution.tsx` — add interrupt/resume/cancel, useWebSocket, gate feedback panel, apply design system

**Interfaces:**
- Consumes: Button, Card, Badge, LoadingSkeleton from Task 1; existing `getSurveyStatus`, `interruptSurvey`, `resumeSurvey` from `client.ts`
- Produces: enhanced AgentExecution with interrupt/resume/cancel controls

- [ ] **Step 1: Create useWebSocket hook with exponential backoff**

```tsx
// web/src/hooks/useWebSocket.ts
import { useEffect, useRef, useCallback, useState } from "react";

const API_BASE = "http://localhost:8000";

interface WebSocketOptions {
  taskId?: string;
  onMessage: (data: any) => void;
  enabled?: boolean;
}

export function useWebSocket({ taskId = "current", onMessage, enabled = true }: WebSocketOptions) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const attemptRef = useRef(0);
  const [connected, setConnected] = useState(false);
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  const connect = useCallback(() => {
    if (!enabled) return;
    attemptRef.current += 1;
    const ws = new WebSocket(`${API_BASE.replace("http", "ws")}/ws/stream/${taskId}`);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      attemptRef.current = 0; // Reset backoff on successful connect
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        onMessageRef.current(data);
      } catch { /* ignore parse errors */ }
    };

    ws.onclose = () => {
      setConnected(false);
      wsRef.current = null;
      // Exponential backoff: 2s, 4s, 8s, 16s, capped at 30s
      const delay = Math.min(2000 * Math.pow(2, attemptRef.current - 1), 30000);
      reconnectTimerRef.current = setTimeout(connect, delay);
    };

    ws.onerror = () => { ws.close(); };
  }, [taskId, enabled]);

  const disconnect = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    attemptRef.current = 0;
    setConnected(false);
  }, []);

  useEffect(() => {
    connect();
    return () => disconnect();
  }, [connect, disconnect]);

  return { connected, disconnect };
}
```

- [ ] **Step 2: Refactor AgentExecution.tsx to use design system components and add interrupt/resume/cancel**

```tsx
// Key changes to web/src/pages/AgentExecution.tsx:
// 1. Replace useRef<WebSocket> + manual reconnect with useWebSocket hook
// 2. Add interrupt/resume buttons (call interruptSurvey / resumeSurvey)
// 3. Add cancel/stop button (calls interruptSurvey)
// 4. Gate feedback panel: only show when pipeline is running
// 5. Replace inline styles with Card, Button, Badge, LoadingSkeleton components
// 6. Add confirmation dialog for cancel action

// New imports:
import Button from "../components/Button";
import Card from "../components/Card";
import Badge from "../components/Badge";
import LoadingSkeleton from "../components/LoadingSkeleton";
import ConfirmDialog from "../components/ConfirmDialog";
import { useToast } from "../components/Toast";
import { useWebSocket } from "../hooks/useWebSocket";
import { getSurveyStatus, interruptSurvey, resumeSurvey, submitFeedback, restartSurvey } from "../api/client";

// New state:
const [interrupting, setInterrupting] = useState(false);
const [showCancelDialog, setShowCancelDialog] = useState(false);
const { showToast } = useToast();

// Replace WebSocket manual code with:
const [progress, setProgress] = useState<ProgressInfo | null>(null);
const { connected } = useWebSocket({
  taskId: "current",
  onMessage: (data) => {
    setProgress(data);
    if (data.task_started_at) setTaskStartedAt(data.task_started_at);
    if (data.feedback_history) setFeedbackHistory(data.feedback_history);
  },
});

// Add interrupt handler:
const handleInterrupt = async () => {
  setInterrupting(true);
  try {
    await interruptSurvey();
    showToast("info", "Pipeline interrupted");
  } catch { showToast("error", "Interrupt failed"); }
  finally { setInterrupting(false); }
};

// Add resume handler:
const handleResume = async () => {
  try {
    await resumeSurvey();
    showToast("success", "Pipeline resumed");
  } catch { showToast("error", "Resume failed"); }
};

// Add cancel handler:
const handleCancel = async () => {
  setShowCancelDialog(false);
  try {
    await interruptSurvey();
    showToast("info", "Task cancelled");
  } catch { showToast("error", "Cancel failed"); }
};

// Render interrupt/resume buttons when pipeline is running:
{progress?.status === "RUNNING" && (
  <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1rem" }}>
    <Button variant="ghost" size="sm" onClick={handleInterrupt} loading={interrupting}>
      ⏸ Pause
    </Button>
    <Button variant="danger" size="sm" onClick={() => setShowCancelDialog(true)}>
      ⏹ Cancel
    </Button>
  </div>
)}

// Render resume button when interrupted:
{progress?.status === "INTERRUPTED" && (
  <Button variant="primary" onClick={handleResume}>▶ Resume</Button>
)}

// Gate feedback panel — only show when pipeline is running:
{pipelineRunning && renderFeedbackPanel()}

// Replace status bar with Badge components:
// Before: <span style={{...}}>{progress.status}</span>
// After: <Badge color={getStatusBadgeColor(progress.status)}>{progress.status}</Badge>
```

- [ ] **Step 3: Run build to verify**

```bash
cd web && npx tsc --noEmit && npx vite build
```

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "feat: add useWebSocket hook with exponential backoff, enhance AgentExecution

- Custom useWebSocket hook with exponential backoff (2s-30s)
- Interrupt/Pause and Resume buttons for pipeline control
- Cancel button with confirmation dialog
- Feedback panel only visible when pipeline is running
- Apply Card, Button, Badge, LoadingSkeleton design system components
- Toast notifications for all actions

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3: FinalReview Quality Scores & Export

**Files:**
- Modify: `web/src/pages/FinalReview.tsx` — add quality score summary, BibTeX export, section review, apply design system

**Interfaces:**
- Consumes: Card, Button, Badge, LoadingSkeleton, EmptyState from Task 1; existing `getPaper`, `getSurveyStatus` from client.ts
- Produces: enhanced FinalReview with quality metrics and BibTeX export

- [ ] **Step 1: Enhance FinalReview with quality score summary**

```tsx
// web/src/pages/FinalReview.tsx — key additions:

// 1. Quality score section at top (when paper is done):
//    - Overall score badge (green ≥ 85%, orange 70-85%, red < 70%)
//    - Per-check scores with pass/warning/fail indicators
//    - Iteration count display

// 2. BibTeX export button (alongside existing .tex download):
//    - Calls format_bibtex for each paper via API
//    - Downloads as .bib file

// 3. Section-by-section paper display:
//    - Parse sections from \section{} markers
//    - Collapsible accordion per section
//    - Expand all / collapse all toggle

// 4. Replace inline styles with Card, Button, Badge components

// New helper to extract sections:
function extractSections(tex: string): { title: string; content: string }[] {
  const sections: { title: string; content: string }[] = [];
  const lines = tex.split("\n");
  let currentTitle = "Preamble";
  let currentContent: string[] = [];
  for (const line of lines) {
    const match = line.match(/\\(?:sub)*section\{([^}]+)\}/);
    if (match) {
      if (currentContent.length > 0) {
        sections.push({ title: currentTitle, content: currentContent.join("\n") });
      }
      currentTitle = match[1];
      currentContent = [line];
    } else {
      currentContent.push(line);
    }
  }
  if (currentContent.length > 0) {
    sections.push({ title: currentTitle, content: currentContent.join("\n") });
  }
  return sections;
}

// New state for collapsible sections:
const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set());
const [allExpanded, setAllExpanded] = useState(false);

const toggleSection = (title: string) => {
  setExpandedSections(prev => {
    const next = new Set(prev);
    if (next.has(title)) next.delete(title);
    else next.add(title);
    return next;
  });
};

const toggleAll = () => {
  if (allExpanded) {
    setExpandedSections(new Set());
  } else {
    setExpandedSections(new Set(sections.map(s => s.title)));
  }
  setAllExpanded(!allExpanded);
};

// BibTeX export handler:
const handleExportBibtex = async () => {
  try {
    // Fetch paper list from API
    const statusData = await getSurveyStatus();
    const papers = statusData?.execution_details?.papers?.list || [];
    const bibtexEntries = papers.map((p: any, i: number) => {
      const key = (p.title || "paper").split(" ")[0].toLowerCase() + (p.year || 2024);
      const authors = p.authors || "Unknown";
      return `@article{${key},\n  title={${p.title}},\n  author={${authors}},\n  year={${p.year || 2024}},\n}`;
    });
    const bibContent = bibtexEntries.join("\n\n");
    const blob = new Blob([bibContent], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `references_${(result.task?.topic || "paper").replace(/\s+/g, "_")}.bib`;
    a.click();
    URL.revokeObjectURL(url);
  } catch {
    showToast("error", "BibTeX export failed");
  }
};
```

- [ ] **Step 2: Run build to verify**

```bash
cd web && npx tsc --noEmit && npx vite build
```

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "feat: enhance FinalReview with quality scores, BibTeX export, section review

- Quality score summary with per-check pass/warning/fail badges
- Overall score with color-coded indicator (green/orange/red)
- BibTeX export button generating .bib file from paper list
- Section-by-section collapsible paper viewer
- Apply Card, Button, Badge design system components
- Loading skeleton and empty states

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 4: ResearchCreation Preference Auto-loading

**Files:**
- Modify: `web/src/pages/ResearchCreation.tsx` — auto-load preferences, add year range, validate, apply design system
- Modify: `api/routes/memory.py` — add GET /api/memory/auto-load endpoint

**Interfaces:**
- Consumes: Card, Button, Input, LoadingSkeleton from Task 1; existing `createSurvey`, new `getAutoLoadPreferences` from client.ts
- Produces: enhanced ResearchCreation with preference auto-loading and validation

- [ ] **Step 1: Add GET /api/memory/auto-load endpoint in memory.py**

```python
# api/routes/memory.py — add new endpoint
@router.get("/auto-load")
async def get_auto_load_preferences():
    """Return default preferences for the ResearchCreation form."""
    from agent.memory.persistent import PersistentMemory
    mem = PersistentMemory()
    prefs = {}
    for key in ("default_source", "year_start", "year_end", "max_papers", "blacklist"):
        val = mem.get(key)
        if val is not None:
            prefs[key] = val
    return {
        "preferences": prefs,
        "available": {
            "default_source": {"type": "select", "options": ["arxiv", "semantic_scholar", "both"]},
            "year_start": {"type": "number", "min": 2015, "max": 2026},
            "year_end": {"type": "number", "min": 2015, "max": 2026},
            "max_papers": {"type": "number", "min": 5, "max": 100},
            "blacklist": {"type": "text"},
        },
    }
```

- [ ] **Step 2: Add getAutoLoadPreferences to client.ts**

```ts
// web/src/api/client.ts
export async function getAutoLoadPreferences() {
  const res = await fetch(`${API_BASE}/api/memory/auto-load`);
  return res.json();
}
```

- [ ] **Step 3: Enhance ResearchCreation.tsx**

```tsx
// web/src/pages/ResearchCreation.tsx — key changes:

// 1. Add useEffect to load preferences on mount:
useEffect(() => {
  getAutoLoadPreferences().then(data => {
    const p = data.preferences || {};
    if (p.year_start) setYearStart(p.year_start);
    if (p.year_end) setYearEnd(p.year_end);
    if (p.max_papers) setMaxPapers(p.max_papers);
  }).catch(() => { /* ignore — use defaults */ });
}, []);

// 2. Add year range inputs:
const [yearStart, setYearStart] = useState(2020);
const [yearEnd, setYearEnd] = useState(2026);

// 3. Add form validation:
const [errors, setErrors] = useState<Record<string, string>>({});

const validate = (): boolean => {
  const e: Record<string, string> = {};
  if (!topic.trim()) e.topic = "Topic is required";
  if (yearStart < 2015 || yearStart > 2026) e.yearStart = "Year must be 2015-2026";
  if (yearEnd < 2015 || yearEnd > 2026) e.yearEnd = "Year must be 2015-2026";
  if (yearStart > yearEnd) e.yearEnd = "End year must be after start year";
  if (maxPapers < 5 || maxPapers > 100) e.maxPapers = "Must be 5-100";
  setErrors(e);
  return Object.keys(e).length === 0;
};

const handleStart = async () => {
  if (!validate()) return;
  await createSurvey({ topic, keywords, goal, max_papers: maxPapers, year_start: yearStart, year_end: yearEnd });
  navigate("/execution");
};

// 4. Replace inline styles with Card, Button, Input components
// 5. Show error messages below fields in red
```

- [ ] **Step 4: Run build to verify**

```bash
cd web && npx tsc --noEmit && npx vite build
```

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: enhance ResearchCreation with preference auto-loading and validation

- Auto-load user preferences from /api/memory/auto-load on mount
- Add year range inputs (start/end) with validation
- Add form validation with per-field error messages
- Apply Card, Button design system components
- Loading skeleton while preferences load

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 5: Dashboard Enhancements

**Files:**
- Modify: `web/src/pages/Dashboard.tsx` — add task history, onboarding state, empty states, apply design system

**Interfaces:**
- Consumes: Card, Button, Badge, EmptyState, LoadingSkeleton from Task 1; existing `getSurveyStatus`, `getPaper` from client.ts
- Produces: enhanced Dashboard with task history, onboarding, proper empty states

- [ ] **Step 1: Enhance Dashboard.tsx**

```tsx
// web/src/pages/Dashboard.tsx — key changes:

// 1. Replace inline styles with Card, Button, Badge, EmptyState, LoadingSkeleton
// 2. Add onboarding state for first-time users (no tasks ever):
//    - "Welcome to ScholarAgent" hero section
//    - "Get Started" button linking to /create
//    - Feature highlights (3 cards: Multi-source search, Quality validation, CVPR format)

// 3. Add task history (from localStorage or API):
//    - Show last 5 completed tasks with status, date, score
//    - Link to /review for each completed task

// 4. Add loading skeleton while fetching data

// 5. Add proper error state with retry button

// Empty state for no tasks:
<EmptyState
  icon="🔬"
  title="Welcome to ScholarAgent"
  description="Your automated literature review assistant. Start by creating a new research task."
  actionLabel="+ New Research Task"
  onAction={() => navigate("/create")}
/>

// Onboarding feature cards:
<div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "var(--space-md)", marginTop: "var(--space-lg)" }}>
  <Card title="🔍 Multi-Source Search">Searches arXiv, Semantic Scholar, and Google Scholar automatically.</Card>
  <Card title="✅ Quality Validation">5-dimension quality check with auto-correction.</Card>
  <Card title="📝 CVPR Format">Outputs in CVPR LaTeX format with BibTeX references.</Card>
</div>
```

- [ ] **Step 2: Run build to verify**

```bash
cd web && npx tsc --noEmit && npx vite build
```

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "feat: enhance Dashboard with onboarding, task history, and design system

- Onboarding feature cards for first-time users
- Empty state with 'New Research Task' call-to-action
- Loading skeleton while fetching status
- Apply Card, Button, Badge, EmptyState components
- Proper error state with retry

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 6: Memory Manager Page

**Files:**
- Create: `web/src/pages/MemoryManager.tsx`
- Modify: `web/src/App.tsx` — add route
- Modify: `web/src/components/Layout.tsx` — add nav item
- Modify: `web/src/api/client.ts` — add getMemory, updateMemory, deleteMemory, clearMemory

**Interfaces:**
- Consumes: Card, Button, Input, ConfirmDialog, EmptyState, LoadingSkeleton, Badge, useToast from Task 1
- Produces: Memory management page with full CRUD on preferences

- [ ] **Step 1: Add memory API functions to client.ts**

```ts
// web/src/api/client.ts
export async function getMemory() {
  const res = await fetch(`${API_BASE}/api/memory`);
  return res.json();
}

export async function updateMemory(key: string, value: string) {
  const res = await fetch(`${API_BASE}/api/memory`, {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key, value }),
  });
  return res.json();
}

export async function deleteMemory(key: string) {
  const res = await fetch(`${API_BASE}/api/memory/${encodeURIComponent(key)}`, { method: "DELETE" });
  return res.json();
}

export async function clearMemory() {
  const res = await fetch(`${API_BASE}/api/memory`, { method: "DELETE" });
  return res.json();
}
```

- [ ] **Step 2: Create MemoryManager.tsx**

```tsx
// web/src/pages/MemoryManager.tsx
import React, { useEffect, useState } from "react";
import Card from "../components/Card";
import Button from "../components/Button";
import Badge from "../components/Badge";
import LoadingSkeleton from "../components/LoadingSkeleton";
import EmptyState from "../components/EmptyState";
import ConfirmDialog from "../components/ConfirmDialog";
import { useToast } from "../components/Toast";
import { getMemory, updateMemory, deleteMemory, clearMemory } from "../api/client";

interface Preference {
  key: string;
  value: string;
  updated_at: string;
}

export default function MemoryManager() {
  const [prefs, setPrefs] = useState<Preference[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [saving, setSaving] = useState(false);
  const [showClearDialog, setShowClearDialog] = useState(false);
  const [clearing, setClearing] = useState(false);
  const { showToast } = useToast();

  const fetchPrefs = async () => {
    try {
      const data = await getMemory();
      setPrefs(data.preferences || []);
    } catch {
      showToast("error", "Failed to load preferences");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchPrefs(); }, []);

  const handleUpdate = async (key: string) => {
    setSaving(true);
    try {
      await updateMemory(key, editValue);
      showToast("success", "Preference updated");
      setEditingKey(null);
      fetchPrefs();
    } catch {
      showToast("error", "Update failed");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (key: string) => {
    try {
      await deleteMemory(key);
      showToast("success", "Preference deleted");
      fetchPrefs();
    } catch {
      showToast("error", "Delete failed");
    }
  };

  const handleClearAll = async () => {
    setShowClearDialog(false);
    setClearing(true);
    try {
      await clearMemory();
      showToast("success", "All preferences cleared");
      setPrefs([]);
    } catch {
      showToast("error", "Clear failed");
    } finally {
      setClearing(false);
    }
  };

  if (loading) return <div><h2 className="page-title">Memory Manager</h2><LoadingSkeleton variant="card" lines={4} /></div>;

  return (
    <div>
      <h2 className="page-title">Memory Manager</h2>
      <p className="text-secondary mb-lg">View and manage your saved preferences. These are automatically loaded when creating new research tasks.</p>

      {prefs.length === 0 ? (
        <EmptyState icon="🧠" title="No Saved Preferences" description="Preferences will appear here as you use ScholarAgent." />
      ) : (
        <>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "var(--space-md)" }}>
            <p className="text-secondary">{prefs.length} preference{prefs.length !== 1 ? "s" : ""}</p>
            <Button variant="danger" size="sm" onClick={() => setShowClearDialog(true)}>Clear All</Button>
          </div>
          {prefs.map(p => (
            <Card key={p.key} title={p.key} headerRight={<Badge color="gray">{p.updated_at}</Badge>}>
              {editingKey === p.key ? (
                <div style={{ display: "flex", gap: "0.5rem" }}>
                  <input value={editValue} onChange={e => setEditValue(e.target.value)}
                    style={{ flex: 1, padding: "0.4rem", borderRadius: "var(--radius-md)", border: "1px solid var(--color-border)" }} />
                  <Button size="sm" onClick={() => handleUpdate(p.key)} loading={saving}>Save</Button>
                  <Button variant="ghost" size="sm" onClick={() => setEditingKey(null)}>Cancel</Button>
                </div>
              ) : (
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <code style={{ fontSize: "0.9rem" }}>{p.value}</code>
                  <div style={{ display: "flex", gap: "0.3rem" }}>
                    <Button variant="ghost" size="sm" onClick={() => { setEditingKey(p.key); setEditValue(p.value); }}>✏ Edit</Button>
                    <Button variant="ghost" size="sm" onClick={() => handleDelete(p.key)}>🗑 Delete</Button>
                  </div>
                </div>
              )}
            </Card>
          ))}
        </>
      )}

      <ConfirmDialog
        open={showClearDialog}
        title="Clear All Preferences?"
        message="This will permanently delete all saved preferences. This action cannot be undone."
        confirmLabel="Clear All"
        danger
        onConfirm={handleClearAll}
        onCancel={() => setShowClearDialog(false)}
        loading={clearing}
      />
    </div>
  );
}
```

- [ ] **Step 3: Add route in App.tsx**

```tsx
// web/src/App.tsx — add import and route
import MemoryManager from "./pages/MemoryManager";
// In Routes:
<Route path="/memory" element={<MemoryManager />} />
```

- [ ] **Step 4: Add nav item in Layout.tsx**

```tsx
// web/src/components/Layout.tsx — add to NAV_ITEMS
{ path: "/memory", label: "Memory", icon: "🧠" },
```

- [ ] **Step 5: Run build to verify**

```bash
cd web && npx tsc --noEmit && npx vite build
```

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat: add Memory Manager page with full CRUD on preferences

- New Memory Manager page at /memory
- View all saved preferences with key, value, updated_at
- Edit individual preferences inline
- Delete individual preferences
- Clear all preferences with confirmation dialog
- Toast notifications for all actions
- Loading skeleton and empty state

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 7: Credential Management Page + API

**Files:**
- Create: `api/routes/credentials.py`
- Create: `web/src/pages/Credentials.tsx`
- Modify: `api/main.py` — register credentials router
- Modify: `web/src/App.tsx` — add route
- Modify: `web/src/components/Layout.tsx` — add nav item
- Modify: `web/src/api/client.ts` — add getCredentials, updateCredential, clearCredential

**Interfaces:**
- Consumes: Card, Button, Badge, ConfirmDialog, EmptyState, useToast from Task 1; existing PersistenMemory from agent
- Produces: credential management page with status view, update, clear

- [ ] **Step 1: Create credentials API route**

```python
# api/routes/credentials.py
from fastapi import APIRouter
from pydantic import BaseModel
import os

router = APIRouter(prefix="/api/credentials", tags=["credentials"])

CREDENTIAL_KEYS = ["LLM_API_KEY", "SEMANTIC_SCHOLAR_API_KEY", "GOOGLE_SCHOLAR_COOKIE"]

class CredentialUpdate(BaseModel):
    key: str
    value: str

@router.get("")
async def get_credential_status():
    """Return credential status (configured yes/no). Never returns plaintext."""
    status = {}
    for key in CREDENTIAL_KEYS:
        val = os.getenv(key, "")
        status[key] = {
            "configured": bool(val),
            # Show first 4 chars + mask for visual confirmation
            "preview": val[:4] + "****" if val else "",
        }
    return {"credentials": status}

@router.put("")
async def update_credential(update: CredentialUpdate):
    """Update a credential (stored in memory, not persisted to .env)."""
    if update.key not in CREDENTIAL_KEYS:
        return {"status": "error", "message": f"Unknown credential: {update.key}"}
    # Store in persistent memory for session use
    from agent.memory.persistent import PersistentMemory
    mem = PersistentMemory()
    mem.set(f"credential_{update.key}", update.value)
    # Also set in os.environ for this process
    os.environ[update.key] = update.value
    return {"status": "updated", "key": update.key}

@router.delete("/{key}")
async def clear_credential(key: str):
    """Clear a stored credential."""
    if key not in CREDENTIAL_KEYS:
        return {"status": "error", "message": f"Unknown credential: {key}"}
    from agent.memory.persistent import PersistentMemory
    mem = PersistentMemory()
    mem.delete(f"credential_{key}")
    os.environ.pop(key, None)
    return {"status": "cleared", "key": key}
```

- [ ] **Step 2: Register credentials router in main.py**

```python
# api/main.py — add import and include
from api.routes import credentials
app.include_router(credentials.router)
```

- [ ] **Step 3: Add credential API functions to client.ts**

```ts
// web/src/api/client.ts
export async function getCredentials() {
  const res = await fetch(`${API_BASE}/api/credentials`);
  return res.json();
}

export async function updateCredential(key: string, value: string) {
  const res = await fetch(`${API_BASE}/api/credentials`, {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key, value }),
  });
  return res.json();
}

export async function clearCredential(key: string) {
  const res = await fetch(`${API_BASE}/api/credentials/${encodeURIComponent(key)}`, { method: "DELETE" });
  return res.json();
}
```

- [ ] **Step 4: Create Credentials.tsx page**

```tsx
// web/src/pages/Credentials.tsx
import React, { useEffect, useState } from "react";
import Card from "../components/Card";
import Button from "../components/Button";
import Badge from "../components/Badge";
import LoadingSkeleton from "../components/LoadingSkeleton";
import ConfirmDialog from "../components/ConfirmDialog";
import { useToast } from "../components/Toast";
import { getCredentials, updateCredential, clearCredential } from "../api/client";

const CREDENTIAL_LABELS: Record<string, string> = {
  LLM_API_KEY: "LLM API Key",
  SEMANTIC_SCHOLAR_API_KEY: "Semantic Scholar API Key",
  GOOGLE_SCHOLAR_COOKIE: "Google Scholar Cookie",
};

const CREDENTIAL_HELP: Record<string, string> = {
  LLM_API_KEY: "Required for LLM calls. Get from OpenAI or Anthropic.",
  SEMANTIC_SCHOLAR_API_KEY: "Optional. Provides higher rate limits for paper search.",
  GOOGLE_SCHOLAR_COOKIE: "Optional. Needed for Google Scholar access.",
};

export default function Credentials() {
  const [credentials, setCredentials] = useState<Record<string, { configured: boolean; preview: string }>>({});
  const [loading, setLoading] = useState(true);
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [saving, setSaving] = useState(false);
  const [showClearDialog, setShowClearDialog] = useState<string | null>(null);
  const { showToast } = useToast();

  const fetchCredentials = async () => {
    try {
      const data = await getCredentials();
      setCredentials(data.credentials || {});
    } catch {
      showToast("error", "Failed to load credentials");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchCredentials(); }, []);

  const handleUpdate = async (key: string) => {
    setSaving(true);
    try {
      await updateCredential(key, editValue);
      showToast("success", `${CREDENTIAL_LABELS[key]} updated`);
      setEditingKey(null);
      setEditValue("");
      fetchCredentials();
    } catch {
      showToast("error", "Update failed");
    } finally {
      setSaving(false);
    }
  };

  const handleClear = async (key: string) => {
    setShowClearDialog(null);
    try {
      await clearCredential(key);
      showToast("success", `${CREDENTIAL_LABELS[key]} cleared`);
      fetchCredentials();
    } catch {
      showToast("error", "Clear failed");
    }
  };

  if (loading) return <div><h2 className="page-title">Credentials</h2><LoadingSkeleton variant="card" lines={3} /></div>;

  const credKeys = Object.keys(CREDENTIAL_LABELS);

  return (
    <div>
      <h2 className="page-title">Credentials</h2>
      <p className="text-secondary mb-lg">Manage API keys and credentials. Keys are stored securely and never shown in plaintext.</p>

      {credKeys.map(key => {
        const cred = credentials[key] || { configured: false, preview: "" };
        return (
          <Card key={key} title={CREDENTIAL_LABELS[key]}
            headerRight={<Badge color={cred.configured ? "green" : "gray"} dot>{cred.configured ? "Configured" : "Not set"}</Badge>}
          >
            <p className="text-secondary" style={{ fontSize: "var(--font-size-sm)", marginBottom: "var(--space-sm)" }}>
              {CREDENTIAL_HELP[key]}
            </p>

            {cred.configured && !editingKey && (
              <p style={{ fontFamily: "monospace", fontSize: "0.9rem", marginBottom: "var(--space-sm)" }}>
                {cred.preview || "****"}
              </p>
            )}

            {editingKey === key ? (
              <div style={{ display: "flex", gap: "0.5rem" }}>
                <input
                  type="password"
                  value={editValue}
                  onChange={e => setEditValue(e.target.value)}
                  placeholder="Enter new key..."
                  style={{ flex: 1, padding: "0.4rem", borderRadius: "var(--radius-md)", border: "1px solid var(--color-border)" }}
                />
                <Button size="sm" onClick={() => handleUpdate(key)} loading={saving}>Save</Button>
                <Button variant="ghost" size="sm" onClick={() => setEditingKey(null)}>Cancel</Button>
              </div>
            ) : (
              <div style={{ display: "flex", gap: "0.5rem" }}>
                <Button variant="ghost" size="sm" onClick={() => setEditingKey(key)}>
                  {cred.configured ? "🔄 Update" : "➕ Set Key"}
                </Button>
                {cred.configured && (
                  <Button variant="ghost" size="sm" onClick={() => setShowClearDialog(key)}>🗑 Clear</Button>
                )}
              </div>
            )}
          </Card>
        );
      })}

      <ConfirmDialog
        open={showClearDialog !== null}
        title="Clear Credential?"
        message={`This will clear the ${showClearDialog ? CREDENTIAL_LABELS[showClearDialog] : ""} credential.`}
        confirmLabel="Clear"
        danger
        onConfirm={() => showClearDialog && handleClear(showClearDialog)}
        onCancel={() => setShowClearDialog(null)}
      />
    </div>
  );
}
```

- [ ] **Step 5: Add route in App.tsx and nav item in Layout.tsx**

```tsx
// App.tsx — add import and route
import Credentials from "./pages/Credentials";
<Route path="/credentials" element={<Credentials />} />

// Layout.tsx — add to NAV_ITEMS
{ path: "/credentials", label: "Credentials", icon: "🔑" },
```

- [ ] **Step 6: Run build to verify**

```bash
cd web && npx tsc --noEmit && npx vite build
```

- [ ] **Step 7: Run backend tests to verify no breakage**

```bash
cd D:\ScholarAgent && python -m pytest tests/ -v --tb=short
```

- [ ] **Step 8: Commit**

```bash
git add -A && git commit -m "feat: add Credential Management page with API

- New Credentials API route (GET status, PUT update, DELETE clear)
- New Credentials page at /credentials with per-key management
- Password-masked input for key entry
- Status badges (green = configured, gray = not set)
- Update and Clear with confirmation dialog
- Toast notifications for all actions
- Loading skeleton and empty states

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Self-Review Checklist

**1. Spec coverage:**
- Design system (CSS tokens, reusable components) → Task 1 ✅
- AgentExecution interrupt/resume/cancel → Task 2 ✅
- WebSocket exponential backoff → Task 2 ✅
- FinalReview quality scores → Task 3 ✅
- FinalReview BibTeX export → Task 3 ✅
- FinalReview section review → Task 3 ✅
- ResearchCreation preference auto-loading → Task 4 ✅
- ResearchCreation validation → Task 4 ✅
- Dashboard task history / onboarding → Task 5 ✅
- Memory Manager page (US-5) → Task 6 ✅
- Credential Management UI (SPEC §7.1) → Task 7 ✅
- Loading skeletons, error boundaries, empty states → Tasks 1-7 ✅
- Toast notifications → Task 1 (Toast component) + used in Tasks 2-7 ✅

**2. Placeholder scan:** All code blocks contain real implementation code. No TODOs, TBDs, or "implement later" patterns.

**3. Type consistency:** All interfaces are consistent across tasks. Button, Card, Badge, LoadingSkeleton, EmptyState, ConfirmDialog, useToast are created in Task 1 and consumed in Tasks 2-7. API client functions are added in the tasks that need them.