import { useEffect, useState, useCallback } from "react";
import { ChevronLeft, ChevronRight, Loader2, Search } from "lucide-react";
import { fetchEntities } from "./api";

interface Entity {
  entity_id: string;
  name: string;
  type: string;
  names: string[];
  synonyms: string[];
}

interface PageResult {
  items: Entity[];
  total: number;
  page: number;
  page_size: number;
}

export default function DashboardEntities() {
  const [data, setData] = useState<PageResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [page, setPage] = useState(1);
  const [jumpPage, setJumpPage] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await fetchEntities({ page, page_size: 20, search, type: typeFilter });
      setData(result);
    } finally {
      setLoading(false);
    }
  }, [page, search, typeFilter]);

  useEffect(() => {
    load();
  }, [load]);

  const totalPages = data ? Math.ceil(data.total / data.page_size) : 0;

  const entityTypes = [
    "Symptom",
    "Intervention",
    "AssessmentTool",
    "Mechanism",
    "AgeStage",
    "Condition",
    "Task",
    "Comorbidity",
    "Setting",
    "Risk",
    "Claim",
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-gray-900">实体浏览</h1>
        <p className="mt-1 text-sm text-gray-500">图谱中所有实体节点 ({data?.total?.toLocaleString() || "…"} 条)</p>
      </div>

      <div className="flex items-center gap-3">
        <div className="relative flex-1">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            placeholder="搜索实体名称…"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
            className="w-full rounded-lg border border-gray-200 py-2 pl-9 pr-3 text-sm outline-none focus:border-medical-400"
          />
        </div>
        <select
          value={typeFilter}
          onChange={(e) => { setTypeFilter(e.target.value); setPage(1); }}
          className="rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-medical-400"
        >
          <option value="">全部类型</option>
          {entityTypes.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
      </div>

      <div className="rounded-xl border border-gray-200 bg-white shadow-sm">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 size={18} className="animate-spin text-medical-600" />
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 text-left text-xs font-medium uppercase text-gray-400">
                <th className="px-5 py-3">名称</th>
                <th className="px-4 py-3">类型</th>
                <th className="px-4 py-3">别名</th>
                <th className="px-4 py-3">同义词</th>
                <th className="px-4 py-3">ID</th>
              </tr>
            </thead>
            <tbody>
              {data?.items.map((e) => (
                <tr key={e.entity_id} className="border-b border-gray-50 text-gray-700 last:border-0 hover:bg-gray-50/50">
                  <td className="px-5 py-3 font-medium">{e.name}</td>
                  <td className="px-4 py-3">
                    <span className="rounded bg-medical-50 px-2 py-0.5 text-xs text-medical-700">{e.type}</span>
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-400">{e.names?.join("; ") || "-"}</td>
                  <td className="px-4 py-3 text-xs text-gray-400">{e.synonyms?.join("; ") || "-"}</td>
                  <td className="px-4 py-3 font-mono text-xs text-gray-400">{e.entity_id}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm">
          <span className="text-gray-500">
            第 {data?.page || 1} / {totalPages} 页 (共 {data?.total || 0} 条)
          </span>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1.5">
              <span className="text-gray-400">跳转</span>
              <input
                type="number"
                min={1}
                max={totalPages}
                value={jumpPage}
                onChange={(e) => setJumpPage(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    const p = parseInt(jumpPage, 10);
                    if (p >= 1 && p <= totalPages) setPage(p);
                    setJumpPage("");
                  }
                }}
                className="w-16 rounded border border-gray-200 px-2 py-1 text-center text-sm outline-none focus:border-medical-400"
                placeholder=""
              />
              <button
                onClick={() => {
                  const p = parseInt(jumpPage, 10);
                  if (p >= 1 && p <= totalPages) setPage(p);
                  setJumpPage("");
                }}
                className="rounded-lg border border-gray-200 px-2.5 py-1.5 text-xs hover:bg-gray-50"
              >
                跳转
              </button>
            </div>
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1}
              className="flex items-center gap-1 rounded-lg border border-gray-200 px-3 py-1.5 text-sm disabled:opacity-40"
            >
              <ChevronLeft size={14} /> 上一页
            </button>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
              className="flex items-center gap-1 rounded-lg border border-gray-200 px-3 py-1.5 text-sm disabled:opacity-40"
            >
              下一页 <ChevronRight size={14} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
