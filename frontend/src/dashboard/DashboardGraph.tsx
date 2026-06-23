import { useEffect, useRef, useState } from "react";
import { Loader2 } from "lucide-react";
import { fetchGraphData } from "./api";

const TYPE_COLORS: Record<string, string> = {
  Symptom: "#ef4444",
  Intervention: "#22c55e",
  AssessmentTool: "#3b82f6",
  Mechanism: "#a855f7",
  Condition: "#f97316",
  AgeStage: "#06b6d4",
  Comorbidity: "#ec4899",
  Risk: "#eab308",
  Task: "#6366f1",
  Setting: "#14b8a6",
  Claim: "#8b5cf6",
};

export default function DashboardGraph() {
  const chartRef = useRef<HTMLDivElement>(null);
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<{ nodes: any[]; edges: any[] } | null>(null);
  const [chart, setChart] = useState<any>(null);
  const [hoveredNode, setHoveredNode] = useState<any>(null);
  const [limitEntities, setLimitEntities] = useState(50);

  useEffect(() => {
    setLoading(true);
    fetchGraphData(limitEntities, limitEntities * 4)
      .then(setData)
      .finally(() => setLoading(false));
  }, [limitEntities]);

  useEffect(() => {
    if (!data || !chartRef.current || data.nodes.length === 0) return;
    let echartInstance: any = null;
    let resizeObserver: ResizeObserver | null = null;

    import("echarts").then((echarts) => {
      if (chart) chart.dispose();
      echartInstance = echarts.init(chartRef.current);
      setChart(echartInstance);

      const categories = [...new Set(data!.nodes.map((n) => n.type))];
      echartInstance.setOption({
        title: { text: `${data!.nodes.length} 节点 · ${data!.edges.length} 条关系`, textStyle: { fontSize: 12, color: "#9ca3af" }, top: 5, left: 10 },
        tooltip: { trigger: "item", formatter: (p: any) => p.dataType === "node" ? `<b>${p.name}</b><br/>类型: ${p.data.type}<br/>关联度: ${p.data.degree}` : `${p.data.source} → ${p.data.target}<br/>关系: ${p.data.relation}` },
        animationDuration: 800,
        animationDurationUpdate: 1500,
        animationEasingUpdate: "quinticInOut",
        series: [
          {
            type: "graph",
            layout: "force",
            force: { repulsion: 500, edgeLength: [120, 300], friction: 0.08, layoutAnimation: false },
            roam: true,
            draggable: true,
            data: data!.nodes.map((n) => ({
              id: n.id,
              name: n.name,
              value: n.degree,
              degree: n.degree,
              type: n.type,
              itemStyle: { color: TYPE_COLORS[n.type] || "#9ca3af" },
              symbolSize: Math.max(12, Math.min(45, (n.degree || 1) * 2.5)),
              label: { show: n.degree > 2, fontSize: 11, fontWeight: "bold" },
            })),
            edges: data!.edges.map((e) => ({
              source: e.source_id,
              target: e.target_id,
              relation: e.relation,
              lineStyle: { width: Math.max(1, Math.min(5, (e.support_count || 1) / 10)), curveness: 0.3, opacity: 0.6 },
              label: { show: e.support_count > 10, formatter: e.relation, fontSize: 9 },
            })),
            categories: categories.map((c) => ({ name: c })),
            edgeSymbol: ["none", "arrow"],
            edgeSymbolSize: [0, 8],
            lineStyle: { color: "source" },
            emphasis: { focus: "adjacency", lineStyle: { width: 3 } },
          },
        ],
      });

      echartInstance.on("mouseover", (p: any) => { if (p.dataType === "node") setHoveredNode(p.data); });
      echartInstance.on("mouseout", () => setHoveredNode(null));

      const onResize = () => echartInstance.resize();
      window.addEventListener("resize", onResize);
      resizeObserver = new ResizeObserver(onResize);
      resizeObserver.observe(chartRef.current!);
    });

    return () => {
      if (resizeObserver) resizeObserver.disconnect();
      if (echartInstance) echartInstance.dispose();
    };
  }, [data]);

  if (loading) {
    return <div className="flex items-center justify-center py-20"><Loader2 size={20} className="animate-spin text-medical-600" /></div>;
  }
  if (!data || data.nodes.length === 0) {
    return <div className="text-sm text-gray-500">暂无图谱数据</div>;
  }

  const typeCount = [...new Set(data.nodes.map((n) => n.type))].reduce(
    (acc, t) => ({ ...acc, [t]: data.nodes.filter((n) => n.type === t).length }), {} as Record<string, number>,
  );

  return (
    <div className="flex flex-col gap-6 min-h-[calc(100vh-130px)]">
      <div className="flex items-center justify-between shrink-0">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">知识图谱可视化</h1>
          <p className="mt-1 text-sm text-gray-500">力导向图 · 节点大小=关联度 · 拖拽浏览 · 滚轮缩放</p>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs text-gray-500">显示节点:</label>
          <select value={limitEntities} onChange={(e) => setLimitEntities(Number(e.target.value))} className="rounded-lg border border-gray-200 px-3 py-1.5 text-sm outline-none">
            <option value={20}>20</option>
            <option value={50}>50</option>
            <option value={80}>80</option>
            <option value={120}>120</option>
          </select>
        </div>
      </div>

      <div className="flex gap-6 flex-1 min-h-0">
        <div ref={chartRef} className="flex-1 min-w-0 rounded-xl border border-gray-200 bg-white shadow-sm" />
        <div className="w-56 shrink-0 space-y-4 overflow-y-auto">
          <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
            <h3 className="mb-3 text-xs font-semibold uppercase text-gray-400">图例</h3>
            <div className="space-y-1.5">
              {Object.entries(typeCount).map(([type, count]) => (
                <div key={type} className="flex items-center gap-2 text-xs">
                  <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: TYPE_COLORS[type] || "#9ca3af" }} />
                  <span className="flex-1 text-gray-600">{type}</span>
                  <span className="text-gray-400">{count}</span>
                </div>
              ))}
            </div>
          </div>

          {hoveredNode && (
            <div className="rounded-xl border border-medical-200 bg-medical-50 p-4 shadow-sm">
              <h3 className="mb-2 text-xs font-semibold text-medical-700">选中节点</h3>
              <div className="space-y-1 text-xs">
                <div><span className="text-gray-500">名称:</span> <span className="font-medium text-gray-800">{hoveredNode.name}</span></div>
                <div><span className="text-gray-500">类型:</span> {hoveredNode.type}</div>
                <div><span className="text-gray-500">关联度:</span> {hoveredNode.degree}</div>
              </div>
            </div>
          )}

          <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
            <h3 className="mb-2 text-xs font-semibold uppercase text-gray-400">统计</h3>
            <div className="space-y-1 text-xs text-gray-600">
              <div className="flex justify-between"><span>节点数</span><span className="font-medium">{data.nodes.length}</span></div>
              <div className="flex justify-between"><span>关系数</span><span className="font-medium">{data.edges.length}</span></div>
              <div className="flex justify-between"><span>类型数</span><span className="font-medium">{Object.keys(typeCount).length}</span></div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
