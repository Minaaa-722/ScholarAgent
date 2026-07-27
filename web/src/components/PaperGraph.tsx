import React, { useEffect, useRef, useState } from "react";
import Card from "./Card";
import LoadingSkeleton from "./LoadingSkeleton";
import EmptyState from "./EmptyState";
import * as d3 from "d3";

interface GraphNode extends d3.SimulationNodeDatum {
  id: number;
  label: string;
  group: string;
  size: number;
}

interface GraphLink {
  source: number;
  target: number;
  weight: number;
}

interface PaperGraphProps {
  nodes: GraphNode[];
  links: GraphLink[];
  loading: boolean;
  error: string | null;
  onSelect: (id: number) => void;
  selectedId: number | null;
}

const GROUP_COLORS: Record<string, string> = {
  arxiv: "#1976d2",
  semantic_scholar: "#4caf50",
  unknown: "#999",
};

export default function PaperGraph({ nodes, links, loading, error, onSelect, selectedId }: PaperGraphProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 500, height: 400 });
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null);

  // Track dimensions on resize
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver(entries => {
      for (const entry of entries) {
        const { width } = entry.contentRect;
        setDimensions({ width: Math.max(300, width), height: Math.max(300, Math.min(500, width * 0.7)) });
      }
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // Draw graph
  useEffect(() => {
    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();
    if (nodes.length === 0) return;

    const { width, height } = dimensions;
    const color = (d: GraphNode) => GROUP_COLORS[d.group] || GROUP_COLORS.unknown;

    const g = svg.append("g");
    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.3, 3])
      .on("zoom", (event) => { g.attr("transform", event.transform); });
    (svg as any).call(zoom);

    const simulation = d3.forceSimulation<GraphNode>(nodes)
      .force("link", d3.forceLink<GraphNode, GraphLink>(links)
        .id(d => d.id)
        .distance(d => 150 - d.weight * 20)
        .strength(0.3))
      .force("charge", d3.forceManyBody().strength(-200))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collision", d3.forceCollide<GraphNode>().radius(d => d.size * 0.5 + 10));

    const link = g.append("g").selectAll("line").data(links).join("line")
      .attr("stroke", "#ccc")
      .attr("stroke-width", d => Math.max(1, d.weight))
      .attr("stroke-opacity", 0.6);

    const node = g.append("g").selectAll("circle").data(nodes).join("circle")
      .attr("r", d => Math.max(5, Math.min(d.size * 0.5 + 5, 30)))
      .attr("fill", d => color(d))
      .attr("stroke", d => d.id === selectedId ? "#fff" : "none")
      .attr("stroke-width", d => d.id === selectedId ? 3 : 0)
      .attr("cursor", "pointer")
      .on("click", (_event, d) => onSelect(d.id))
      .on("mouseenter", (_event, d) => setHoveredNode(d))
      .on("mouseleave", () => setHoveredNode(null))
      // @ts-expect-error d3 drag types
      .call(d3.drag<SVGCircleElement, GraphNode>()
        .on("start", (event, d) => {
          if (!event.active) simulation.alphaTarget(0.3).restart();
          d.fx = d.x; d.fy = d.y;
        })
        .on("drag", (event, d) => { d.fx = event.x; d.fy = event.y; })
        .on("end", (event, d) => {
          if (!event.active) simulation.alphaTarget(0);
          d.fx = null; d.fy = null;
        }));

    const label = g.append("g").selectAll("text").data(nodes).join("text")
      .text(d => d.label.length > 20 ? d.label.slice(0, 18) + "…" : d.label)
      .attr("font-size", "10px")
      .attr("dx", d => Math.max(5, Math.min(d.size * 0.5 + 5, 30)) + 3)
      .attr("dy", "0.35em")
      .attr("fill", "var(--color-text-secondary)")
      .attr("pointer-events", "none");

    simulation.on("tick", () => {
      link
        .attr("x1", d => (d.source as any).x)
        .attr("y1", d => (d.source as any).y)
        .attr("x2", d => (d.target as any).x)
        .attr("y2", d => (d.target as any).y);
      node.attr("cx", d => d.x!).attr("cy", d => d.y!);
      label.attr("x", d => d.x!).attr("y", d => d.y!);
    });

    return () => { simulation.stop(); };
  }, [nodes, links, dimensions, selectedId, onSelect]);

  if (loading) {
    return <LoadingSkeleton variant="card" lines={5} />;
  }

  if (error) {
    return (
      <Card title="Citation Network" borderColor="var(--color-danger)">
        <p style={{ color: "var(--color-danger)" }}>Failed to load graph: {error}</p>
      </Card>
    );
  }

  if (nodes.length === 0) {
    return (
      <EmptyState icon="🔗" title="No Graph Data" description="Papers will appear here as a citation network once retrieved." />
    );
  }

  return (
    <Card title="Citation Network">
      <div ref={containerRef} style={{ position: "relative", width: "100%" }}>
        <svg
          ref={svgRef}
          width={dimensions.width}
          height={dimensions.height}
          style={{ display: "block", background: "#fafafa", borderRadius: "var(--radius-md)" }}
        />
        {hoveredNode && (
          <div style={{
            position: "absolute", bottom: "var(--space-sm)", left: "var(--space-sm)",
            background: "rgba(0,0,0,0.8)", color: "#fff",
            padding: "var(--space-xs) var(--space-sm)", borderRadius: "var(--radius-sm)",
            fontSize: "var(--font-size-xs)", maxWidth: "80%", pointerEvents: "none",
          }}>
            {hoveredNode.label}
            <span style={{ opacity: 0.7 }}> — {hoveredNode.group}</span>
          </div>
        )}
        <div style={{
          position: "absolute", top: "var(--space-sm)", right: "var(--space-sm)",
          background: "rgba(255,255,255,0.9)", padding: "var(--space-xs) var(--space-sm)",
          borderRadius: "var(--radius-sm)", fontSize: "var(--font-size-xs)",
          display: "flex", flexDirection: "column", gap: "0.15rem",
        }}>
          {Object.entries(GROUP_COLORS).map(([key, color]) => (
            <div key={key} style={{ display: "flex", alignItems: "center", gap: "0.3rem" }}>
              <span style={{ width: 8, height: 8, borderRadius: "50%", background: color, display: "inline-block" }} />
              {key === "semantic_scholar" ? "Semantic Scholar" : key.charAt(0).toUpperCase() + key.slice(1)}
            </div>
          ))}
        </div>
        <div style={{
          position: "absolute", bottom: "var(--space-sm)", right: "var(--space-sm)",
          color: "var(--color-text-disabled)", fontSize: "var(--font-size-xs)",
        }}>
          Scroll to zoom · Drag to pan
        </div>
      </div>
    </Card>
  );
}