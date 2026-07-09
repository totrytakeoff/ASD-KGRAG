import { useEffect, useRef } from "react";
import * as echarts from "echarts";

interface Props {
  nodes: { id: string; name: string; type: string }[];
  edges: { source: string; target: string; relation: string }[];
}

const CATEGORY_COLORS: Record<string, string> = {
  Entity: "#64748b",
  Condition: "#ef4444",
  AssessmentTool: "#2563eb",
  Intervention: "#10b981",
  Symptom: "#f59e0b",
  Symptoms: "#f59e0b",
  Drug: "#8b5cf6",
  Comorbidity: "#ec4899",
  Risk: "#dc2626",
  Mechanism: "#14b8a6",
  Task: "#6366f1",
  Setting: "#0ea5e9",
  AgeStage: "#84cc16",
  Claim: "#a855f7",
};

const CATEGORIES = [
  { name: "Entity" },
  { name: "Condition" },
  { name: "AssessmentTool" },
  { name: "Intervention" },
  { name: "Symptom" },
  { name: "Symptoms" },
  { name: "Drug" },
  { name: "Comorbidity" },
  { name: "Risk" },
  { name: "Mechanism" },
  { name: "Task" },
  { name: "Setting" },
  { name: "AgeStage" },
  { name: "Claim" },
];

const categoryIndex = (type?: string) => {
  const idx = CATEGORIES.findIndex((c) => c.name === type);
  return idx >= 0 ? idx : 0;
};

export default function GraphView({ nodes, edges }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    if (!chartRef.current) {
      chartRef.current = echarts.init(ref.current);
    }
    const nodeMap = new Map(nodes.map((n) => [n.id, n]));
    const seriesNodes = nodes.map((n) => ({
      id: n.id,
      name: n.name,
      category: categoryIndex(n.type),
      symbolSize: 34,
      label: {
        show: true,
        formatter: (p: { name: string }) => {
          const name = p.name || "";
          return name.length > 16 ? `${name.slice(0, 16)}...` : name;
        },
        fontSize: 11,
      },
    }));
    const seriesEdges = edges
      .filter((e) => nodeMap.has(e.source) && nodeMap.has(e.target))
      .map((e) => ({
        source: e.source,
        target: e.target,
        label: {
          show: true,
          formatter: e.relation,
          fontSize: 10,
          color: "#6b7280",
        },
      }));

    if (seriesNodes.length === 0 || seriesEdges.length === 0) {
      chartRef.current.clear();
      return;
    }

    chartRef.current.setOption({
      tooltip: {
        formatter: (p: any) => {
          if (p.dataType === "edge") return p.data.label?.formatter || "";
          return `${p.name}<br/>${CATEGORIES[p.data.category]?.name || "Entity"}`;
        },
      },
      legend: [
        {
          data: CATEGORIES.filter((_, i) => seriesNodes.some((n) => n.category === i)).map(
            (c) => c.name,
          ),
          bottom: 0,
          textStyle: { fontSize: 11 },
        },
      ],
      animationDuration: 800,
      series: [
        {
          type: "graph",
          layout: "force",
          roam: true,
          draggable: true,
          force: {
            repulsion: 220,
            edgeLength: 140,
            gravity: 0.1,
          },
          categories: CATEGORIES,
          data: seriesNodes,
          links: seriesEdges,
          lineStyle: { color: "#94a3b8", width: 1.5, curveness: 0.12 },
          edgeSymbol: ["none", "arrow"],
          edgeSymbolSize: 8,
          itemStyle: {
            color: (p: { data: { category: number } }) =>
              CATEGORY_COLORS[CATEGORIES[p.data.category]?.name] || "#6b7280",
          },
        },
      ],
    });

    const handleResize = () => chartRef.current?.resize();
    requestAnimationFrame(handleResize);
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [nodes, edges]);

  useEffect(() => {
    return () => {
      chartRef.current?.dispose();
      chartRef.current = null;
    };
  }, []);

  const nodeIds = new Set(nodes.map((n) => n.id));
  const validEdgeCount = edges.filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target)).length;

  if (nodes.length === 0 || validEdgeCount === 0) {
    return (
      <div className="flex h-32 w-full items-center justify-center rounded border border-dashed border-gray-200 bg-gray-50 text-xs text-gray-400">
        暂无可视化图谱边，仅展示上方文本证据路径
      </div>
    );
  }

  return <div ref={ref} className="h-72 w-full min-w-0" />;
}
