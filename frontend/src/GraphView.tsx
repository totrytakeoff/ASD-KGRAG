import { useEffect, useRef } from "react";
import * as echarts from "echarts";

interface Props {
  nodes: { id: string; name: string; type: string }[];
  edges: { source: string; target: string; relation: string }[];
}

const CATEGORY_COLORS: Record<string, string> = {
  Condition: "#ef4444",
  AssessmentTool: "#2563eb",
  Intervention: "#10b981",
  Symptoms: "#f59e0b",
  Drug: "#8b5cf6",
  Comorbidity: "#ec4899",
  Risk: "#dc2626",
};

const CATEGORIES = [
  { name: "Condition" },
  { name: "AssessmentTool" },
  { name: "Intervention" },
  { name: "Symptoms" },
  { name: "Drug" },
  { name: "Comorbidity" },
  { name: "Risk" },
];

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
      category: CATEGORIES.findIndex((c) => c.name === n.type),
      symbolSize: 40,
      label: { show: true },
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

    chartRef.current.setOption({
      tooltip: {},
      legend: [
        {
          data: CATEGORIES.map((c) => c.name),
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
          lineStyle: { color: "#9ca3af", width: 1.5, curveness: 0.1 },
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
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [nodes, edges]);

  useEffect(() => {
    return () => {
      chartRef.current?.dispose();
    };
  }, []);

  return <div ref={ref} className="h-64 w-full" />;
}
