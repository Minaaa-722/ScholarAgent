import React, { useEffect, useState, useCallback, useRef } from "react";
import { getPapers, getPaperGraph, getPaperDetail, PaperItem, GraphNode, GraphLink } from "../api/client";
import PaperTable from "../components/PaperTable";
import PaperGraph from "../components/PaperGraph";
import PaperDetail from "../components/PaperDetail";
import Card from "../components/Card";
import Button from "../components/Button";

export default function KnowledgeExplorer() {
  const [papers, setPapers] = useState<PaperItem[]>([]);
  const [papersLoading, setPapersLoading] = useState(true);
  const [papersError, setPapersError] = useState<string | null>(null);
  const [graphNodes, setGraphNodes] = useState<GraphNode[]>([]);
  const [graphLinks, setGraphLinks] = useState<GraphLink[]>([]);
  const [graphLoading, setGraphLoading] = useState(true);
  const [graphError, setGraphError] = useState<string | null>(null);
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [detailPaper, setDetailPaper] = useState<PaperItem | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

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
      if (paperResp.papers.length > 0 && pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
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

  useEffect(() => {
    loadData();
    return () => {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, [loadData]);

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
      <h2 className="page-title">Knowledge Explorer</h2>
      <p className="text-secondary mb-lg" style={{ fontSize: "var(--font-size-sm)" }}>
        Browse retrieved papers, explore the citation network, and view paper metadata.
      </p>

      {!papersLoading && papers.length > 0 && (
        <>
          <div className="flex justify-between mb-md" style={{ alignItems: "center" }}>
            {/* Summary bar */}
            <div className="flex" style={{ gap: "var(--space-md)", flex: 1 }}>
              <Card padding="var(--space-sm) var(--space-md)" style={{ flex: 1, textAlign: "center" }}>
                <div style={{ fontSize: "var(--font-size-xl)", fontWeight: "var(--font-weight-bold)", color: "var(--color-primary)" }}>{papers.length}</div>
                <div style={{ fontSize: "var(--font-size-xs)", color: "var(--color-text-secondary)" }}>Papers</div>
              </Card>
              <Card padding="var(--space-sm) var(--space-md)" style={{ flex: 1, textAlign: "center" }}>
                <div style={{ fontSize: "var(--font-size-xl)", fontWeight: "var(--font-weight-bold)", color: "var(--color-success)" }}>{graphNodes.length}</div>
                <div style={{ fontSize: "var(--font-size-xs)", color: "var(--color-text-secondary)" }}>Nodes</div>
              </Card>
              <Card padding="var(--space-sm) var(--space-md)" style={{ flex: 1, textAlign: "center" }}>
                <div style={{ fontSize: "var(--font-size-xl)", fontWeight: "var(--font-weight-bold)", color: "var(--color-warning)" }}>{graphLinks.length}</div>
                <div style={{ fontSize: "var(--font-size-xs)", color: "var(--color-text-secondary)" }}>Links</div>
              </Card>
            </div>
            <div className="ml-auto hide-mobile">
              <Button onClick={() => window.open("/api/survey/papers/export", "_blank")}>
                ⬇ Export CSV
              </Button>
            </div>
          </div>

          {/* Mobile export */}
          <div className="hide-desktop mb-md" style={{ display: "flex", justifyContent: "flex-end" }}>
            <Button size="sm" onClick={() => window.open("/api/survey/papers/export", "_blank")}>
              ⬇ Export CSV
            </Button>
          </div>
        </>
      )}

      {/* Three-column layout */}
      <div className="knowledge-grid" style={{
        display: "grid",
        gridTemplateColumns: "minmax(0, 2fr) minmax(0, 2fr) minmax(0, 1.5fr)",
        gap: "var(--space-lg)", alignItems: "start",
      }}>
        <PaperTable
          papers={papers}
          loading={papersLoading}
          error={papersError}
          onSelect={handleSelect}
          selectedIndex={selectedIndex}
        />
        <PaperGraph
          nodes={graphNodes}
          links={graphLinks}
          loading={graphLoading}
          error={graphError}
          onSelect={handleSelect}
          selectedId={selectedIndex}
        />
        <PaperDetail
          paper={detailPaper}
          loading={detailLoading}
          error={detailError}
          onClose={handleCloseDetail}
        />
      </div>

      {/* Responsive: collapse to single column on mobile */}
      <style>{`
        @media (max-width: 1024px) {
          .knowledge-grid { grid-template-columns: 1fr 1fr !important; }
        }
        @media (max-width: 640px) {
          .knowledge-grid { grid-template-columns: 1fr !important; }
        }
      `}</style>
    </div>
  );
}