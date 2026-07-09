import { useEffect, useRef } from "react";
import * as echarts from "echarts";

interface Props {
  nodes: { id: string; name: string; type: string }[];
  edges: { source: string; target: string; relation: string }[];
}

const CATEGORY_COLORS: Record<string, string> = {
  Entity: "#0ea5e9",
  Condition: "#f43f5e",
  AssessmentTool: "#2563eb",
  Intervention: "#10b981",
  Symptom: "#f97316",
  Symptoms: "#f97316",
  Drug: "#8b5cf6",
  Comorbidity: "#ec4899",
  Risk: "#ef4444",
  Mechanism: "#14b8a6",
  Task: "#6366f1",
  Setting: "#06b6d4",
  AgeStage: "#84cc16",
  Claim: "#d946ef",
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
      symbolSize: 42,
      label: {
        show: true,
        formatter: (p: { name: string }) => {
          const name = p.name || "";
          return name.length > 16 ? `${name.slice(0, 16)}...` : name;
        },
        fontSize: 12,
        fontWeight: 600,
        color: "#0f172a",
        backgroundColor: "rgba(255,255,255,0.86)",
        borderColor: "rgba(148,163,184,0.28)",
        borderWidth: 1,
        borderRadius: 4,
        padding: [2, 4],
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
          color: "#334155",
          backgroundColor: "rgba(255,255,255,0.9)",
          borderColor: "rgba(37,99,235,0.18)",
          borderWidth: 1,
          borderRadius: 3,
          padding: [1, 3],
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
            repulsion: 280,
            edgeLength: 150,
            gravity: 0.08,
          },
          categories: CATEGORIES,
          data: seriesNodes,
          links: seriesEdges,
          lineStyle: { color: "#3b82f6", width: 2, opacity: 0.72, curveness: 0.14 },
          edgeSymbol: ["none", "arrow"],
          edgeSymbolSize: 10,
          itemStyle: {
            color: (p: { data: { category: number } }) =>
              CATEGORY_COLORS[CATEGORIES[p.data.category]?.name] || CATEGORY_COLORS.Entity,
            borderColor: "#ffffff",
            borderWidth: 3,
            shadowBlur: 12,
            shadowColor: "rgba(15,23,42,0.2)",
          },
          emphasis: {
            focus: "adjacency",
            lineStyle: { width: 3, opacity: 0.95 },
            itemStyle: { shadowBlur: 18, shadowColor: "rgba(37,99,235,0.35)" },
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
