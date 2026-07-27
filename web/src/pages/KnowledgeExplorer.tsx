import React, { useEffect, useState, useCallback, useRef } from "react";
import { getPapers, getPaperGraph, getPaperDetail, PaperItem, GraphNode, GraphLink } from "../api/client";
import PaperTable from "../components/PaperTable";
import PaperGraph from "../components/PaperGraph";
import PaperDetail from "../components/PaperDetail";
import Card from "../components/Card";
import Button from "../components/Button";

export default function KnowledgeExplorer() {
  // Papers state
  const [papers, setPapers] = useState<PaperItem[]>([]);
  const [papersLoading, setPapersLoading] = useState(true);
  const [papersError, setPapersError] = useState<string | null>(null);

  // Graph state
  const [graphNodes, setGraphNodes] = useState<GraphNode[]>([]);
  const [graphLinks, setGraphLinks] = useState<GraphLink[]>([]);
  const [graphLoading, setGraphLoading] = useState(true);
  const [graphError, setGraphError] = useState<string | null>(null);

  // Selection state
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [detailPaper, setDetailPaper] = useState<PaperItem | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  // Polling ref
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Load data (used both for initial load and polling)
  const loadData = useCallback(async () => {
    try {
      const [paperResp, graphResp] = await Promise.all([
        getPapers(),
        getPaperGraph(),
      ]);
      setPapers(paperResp.papers);
      setPapersLoading(false);
      setGraphNodes(graphResp.nodes);
      setGraphLinks(graphResp.links);
      setGraphLoading(false);
      // Stop polling once we have data
      if (paperResp.papers.length > 0 && pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
      // If no papers yet, start polling every 3s
      if (paperResp.papers.length === 0 && !pollTimerRef.current) {
        pollTimerRef.current = setInterval(loadData, 3000);
      }
    } catch (err) {
      setPapersError("Failed to load papers");
      setPapersLoading(false);
      setGraphError("Failed to load graph");
      setGraphLoading(false);
    }
  }, []);

  // Initial load + polling until papers arrive
  useEffect(() => {
    loadData();
    return () => {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, [loadData]);

  // Handle paper selection
  const handleSelect = useCallback(async (index: number) => {
    setSelectedIndex(index);
    setDetailLoading(true);
    setDetailError(null);
    try {
      const paper = await getPaperDetail(index);
      setDetailPaper(paper);
    } catch {
      setDetailError("Failed to load paper details");
      setDetailPaper(null);
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const handleCloseDetail = useCallback(() => {
    setSelectedIndex(null);
    setDetailPaper(null);
    setDetailError(null);
  }, []);

  return (
    <div>
      <h2>Knowledge Explorer</h2>
      <p style={{ color: "var(--color-text-secondary)", marginBottom: "var(--space-lg)", fontSize: "var(--font-size-sm)" }}>
        Browse retrieved papers, explore the citation network, and view paper metadata.
      </p>

      {/* Export button */}
      {!papersLoading && papers.length > 0 && (
        <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: "var(--space-md)" }}>
          <Button onClick={() => window.open("/api/survey/papers/export", "_blank")}>
            ⬇ Export CSV
          </Button>
        </div>
      )}

      {/* Summary bar */}
      {!papersLoading && papers.length > 0 && (
        <div style={{ display: "flex", gap: "var(--space-md)", marginBottom: "var(--space-lg)" }}>
          <Card padding="var(--space-sm) var(--space-md)" style={{ flex: 1, textAlign: "center" }}>
            <div style={{ fontSize: "var(--font-size-xl)", fontWeight: "var(--font-weight-bold)", color: "var(--color-primary)" }}>{papers.length}</div>
            <div style={{ fontSize: "var(--font-size-xs)", color: "var(--color-text-secondary)" }}>Papers</div>
          </Card>
          <Card padding="var(--space-sm) var(--space-md)" style={{ flex: 1, textAlign: "center" }}>
            <div style={{ fontSize: "var(--font-size-xl)", fontWeight: "var(--font-weight-bold)", color: "var(--color-success)" }}>{graphNodes.length}</div>
            <div style={{ fontSize: "var(--font-size-xs)", color: "var(--color-text-secondary)" }}>Graph Nodes</div>
          </Card>
          <Card padding="var(--space-sm) var(--space-md)" style={{ flex: 1, textAlign: "center" }}>
            <div style={{ fontSize: "var(--font-size-xl)", fontWeight: "var(--font-weight-bold)", color: "var(--color-warning)" }}>{graphLinks.length}</div>
            <div style={{ fontSize: "var(--font-size-xs)", color: "var(--color-text-secondary)" }}>Connections</div>
          </Card>
        </div>
      )}

      {/* Three-column layout */}
      <div style={{ display: "grid", gridTemplateColumns: "2fr 2fr 1.5fr", gap: "var(--space-lg)", alignItems: "start" }}>
        {/* Left: Paper Table */}
        <PaperTable
          papers={papers}
          loading={papersLoading}
          error={papersError}
          onSelect={handleSelect}
          selectedIndex={selectedIndex}
        />

        {/* Center: Citation Graph */}
        <PaperGraph
          nodes={graphNodes}
          links={graphLinks}
          loading={graphLoading}
          error={graphError}
          onSelect={handleSelect}
          selectedId={selectedIndex}
        />

        {/* Right: Paper Detail */}
        <PaperDetail
          paper={detailPaper}
          loading={detailLoading}
          error={detailError}
          onClose={handleCloseDetail}
        />
      </div>
    </div>
  );
}