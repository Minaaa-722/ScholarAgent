# Execution Page Default Landing Page

## Problem

The Execution page (`AgentExecution.tsx`) shows a `<LoadingSkeleton variant="card" />` shimmer placeholder when no task is actively executing (`!connected && !progress`). This is misleading — it looks like content is loading when actually the system is idle with no task to display.

## Goal

Replace the loading skeleton with a meaningful default initial page that informs the user about the Execution pipeline and encourages them to start a new task.

## Design

### Layout

1. **Hero Section** — Dark gradient banner (matching existing `progress.topic` banner style at line 416-452):
   - 🚀 Icon
   - Title: "Agent Execution Pipeline"
   - Subtitle: "监控和管理你的文献综述自动化流程"
   - Brief description of the pipeline's purpose

2. **Pipeline Overview** — Horizontal flow showing the 5 core stages as pill-shaped badges connected by arrows:
   - `📋 Plan` → `🔍 Search` → `📊 Analyze` → `✍️ Write` → `✅ Validate`
   - Each stage has a short description below it
   - Uses the same visual style as the existing `renderStageChain()` (rounded pills, arrow connectors)

3. **Feature Cards** — 3-column grid (matching Dashboard's onboarding pattern at line 101-118):
   - **📡 实时监控** — Real-time stage progress, current messages, and execution details
   - **💬 交互反馈** — Provide feedback to agents during execution to refine results
   - **✅ 质量验证** — 5-dimension quality validation with auto-correction

4. **CTA Button** — Centered "🚀 开始新的研究任务" primary button, navigates to `/create` via `useNavigate`

5. **Idle indicator** — Small text/tag: "当前没有正在执行的任务" (No task currently executing)

### State detection

| Condition | Current behavior | New behavior |
|---|---|---|
| `!connected && !progress` | Loading skeleton | Default landing page |
| `progress` | Execution UI (unchanged) | Execution UI (unchanged) |
| `!progress && connected` | "Waiting for execution data…" (unchanged) | "Waiting for execution data…" (unchanged) |

### Files changed

- `web/src/pages/AgentExecution.tsx` — Replace the loading skeleton with the default page; add `useNavigate` import

### No new components needed

The design is implemented inline within `AgentExecution.tsx` as a function `renderDefaultPage()`, keeping the change self-contained and consistent with the existing code style.

## Implementation

1. Add `useNavigate` to the import from `react-router-dom`
2. Add `renderDefaultPage()` function returning the hero section, pipeline overview, feature cards, and CTA
3. Replace `{!connected && !progress && (<LoadingSkeleton variant="card" />)}` with `{!connected && !progress && renderDefaultPage()}`