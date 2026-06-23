import { useEffect, useState } from "react";
import { BarChart3, Database, GitBranch, FileText, Layers, Loader2 } from "lucide-react";
import { fetchStats } from "./api";

interface NamedCount {
  name: string;
  count: number;
}

interface Stats {
  entity_count: number;
  relation_count: number;
  chunk_count: number;
  entity_type_distribution: NamedCount[];
  evidence_level_distribution: NamedCount[];
  source_type_distribution: NamedCount[];
}

export default function DashboardOverview() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchStats()
      .then(setStats)
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 size={20} className="animate-spin text-medical-600" />
        <span className="ml-2 text-sm text-gray-500">加载中…</span>
      </div>
    );
  }
  if (!stats) return <div className="text-sm text-red-500">无法加载统计数据</div>;

  const cards = [
    { label: "实体总数", value: stats.entity_count?.toLocaleString() || "0", icon: <Database size={20} />, color: "bg-blue-50 text-blue-700" },
    { label: "关系总数", value: stats.relation_count?.toLocaleString() || "0", icon: <GitBranch size={20} />, color: "bg-emerald-50 text-emerald-700" },
    { label: "Chunk 数", value: stats.chunk_count?.toLocaleString() || "0", icon: <FileText size={20} />, color: "bg-amber-50 text-amber-700" },
    { label: "实体类型", value: (stats.entity_type_distribution?.length || 0).toString(), icon: <Layers size={20} />, color: "bg-purple-50 text-purple-700" },
  ];

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-xl font-semibold text-gray-900">图谱概览</h1>
        <p className="mt-1 text-sm text-gray-500">知识图谱内容总览与统计</p>
      </div>

      <div className="grid grid-cols-4 gap-4">
        {cards.map((card) => (
          <div key={card.label} className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
            <div className={`mb-3 inline-flex rounded-lg p-2.5 ${card.color}`}>{card.icon}</div>
            <div className="text-2xl font-bold text-gray-900">{card.value}</div>
            <div className="mt-1 text-sm text-gray-500">{card.label}</div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-3 gap-6">
        <DistributionCard title="实体类型分布" data={stats.entity_type_distribution} color="medical" />
        <DistributionCard title="证据等级分布" data={stats.evidence_level_distribution} color="emerald" />
        <DistributionCard title="来源类型分布" data={stats.source_type_distribution} color="amber" />
      </div>
    </div>
  );
}

function DistributionCard({ title, data, color }: { title: string; data: NamedCount[]; color: string }) {
  if (!data || data.length === 0) return null;
  const total = data.reduce((sum, d) => sum + d.count, 0);
  const maxCount = data[0]?.count || 1;

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <h3 className="mb-4 text-sm font-medium text-gray-700">{title}</h3>
      <div className="space-y-2">
        {data.slice(0, 8).map((item) => (
          <div key={item.name} className="flex items-center gap-2 text-xs">
            <span className="w-28 truncate text-gray-600" title={item.name}>{item.name}</span>
            <div className="flex-1">
              <div className="h-4 rounded bg-gray-100">
                <div
                  className="h-4 rounded bg-medical-500 transition-all"
                  style={{ width: `${(item.count / maxCount) * 100}%` }}
                />
              </div>
            </div>
            <span className="w-16 text-right text-gray-400">{item.count}</span>
            <span className="w-10 text-right text-gray-400">{((item.count / total) * 100).toFixed(0)}%</span>
          </div>
        ))}
      </div>
      {data.length > 8 && (
        <p className="mt-2 text-xs text-gray-400">…还有 {data.length - 8} 种</p>
      )}
    </div>
  );
}
