import { useEffect, useState, useCallback } from "react";
import { ChevronLeft, ChevronRight, Loader2, Search } from "lucide-react";
import { fetchRelations } from "./api";

interface Relation {
  source: string;
  source_type: string;
  relation: string;
  target: string;
  target_type: string;
  support_count: number | null;
  confidence: number | null;
  qa_usage: string | null;
}

interface PageResult {
  items: Relation[];
  total: number;
  page: number;
  page_size: number;
}

export default function DashboardRelations() {
  const [data, setData] = useState<PageResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [entityFilter, setEntityFilter] = useState("");
  const [page, setPage] = useState(1);
  const [jumpPage, setJumpPage] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await fetchRelations({ page, page_size: 20, entity: entityFilter });
      setData(result);
    } finally {
      setLoading(false);
    }
  }, [page, entityFilter]);

  useEffect(() => { load(); }, [load]);

  const totalPages = data ? Math.ceil(data.total / data.page_size) : 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-gray-900">关系浏览</h1>
        <p className="mt-1 text-sm text-gray-500">实体间关系 ({data?.total?.toLocaleString() || "…"} 条)</p>
      </div>

      <div className="relative max-w-sm">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
        <input type="text" placeholder="按源或目标实体过滤…" value={entityFilter}
          onChange={(e) => { setEntityFilter(e.target.value); setPage(1); }}
          className="w-full rounded-lg border border-gray-200 py-2 pl-9 pr-3 text-sm outline-none focus:border-medical-400" />
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
                <th className="px-5 py-3">源实体</th>
                <th className="px-4 py-3">关系</th>
                <th className="px-4 py-3">目标实体</th>
                <th className="px-3 py-3 text-right">支持数</th>
                <th className="px-3 py-3 text-right">置信度</th>
                <th className="px-4 py-3">用途</th>
              </tr>
            </thead>
            <tbody>
              {data?.items.map((r, i) => (
                <tr key={i} className="border-b border-gray-50 text-gray-700 last:border-0 hover:bg-gray-50/50">
                  <td className="px-5 py-3">
                    <span className="rounded bg-red-50 px-2 py-0.5 text-xs text-red-700">{r.source}</span>
                    <span className="ml-1.5 text-xs text-gray-400">{r.source_type}</span>
                  </td>
                  <td className="px-4 py-3">
                    <span className="font-mono text-xs text-medical-600">({r.relation})</span>
                  </td>
                  <td className="px-4 py-3">
                    <span className="rounded bg-blue-50 px-2 py-0.5 text-xs text-blue-700">{r.target}</span>
                    <span className="ml-1.5 text-xs text-gray-400">{r.target_type}</span>
                  </td>
                  <td className="px-3 py-3 text-right font-mono text-xs">{r.support_count ?? "-"}</td>
                  <td className="px-3 py-3 text-right font-mono text-xs">{r.confidence != null ? r.confidence.toFixed(4) : "-"}</td>
                  <td className="px-4 py-3">
                    <UsageBadge usage={r.qa_usage} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm">
          <span className="text-gray-500">第 {data?.page || 1} / {totalPages} 页 (共 {data?.total || 0} 条)</span>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1.5">
              <span className="text-gray-400">跳转</span>
              <input type="number" min={1} max={totalPages} value={jumpPage}
                onChange={(e) => setJumpPage(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") { const p = parseInt(jumpPage, 10); if (p >= 1 && p <= totalPages) setPage(p); setJumpPage(""); }}}
                className="w-16 rounded border border-gray-200 px-2 py-1 text-center text-sm outline-none focus:border-medical-400" />
              <button onClick={() => { const p = parseInt(jumpPage, 10); if (p >= 1 && p <= totalPages) setPage(p); setJumpPage(""); }}
                className="rounded-lg border border-gray-200 px-2.5 py-1.5 text-xs hover:bg-gray-50">跳转</button>
            </div>
            <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1}
              className="flex items-center gap-1 rounded-lg border border-gray-200 px-3 py-1.5 text-sm disabled:opacity-40">
              <ChevronLeft size={14} /> 上一页
            </button>
            <button onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page >= totalPages}
              className="flex items-center gap-1 rounded-lg border border-gray-200 px-3 py-1.5 text-sm disabled:opacity-40">
              下一页 <ChevronRight size={14} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function UsageBadge({ usage }: { usage: string | null }) {
  if (!usage) return <span className="text-xs text-gray-400">-</span>;
  const colors: Record<string, string> = {
    standard: "bg-green-50 text-green-700",
    use_with_caution: "bg-amber-50 text-amber-700",
    research_context_only: "bg-red-50 text-red-700",
    guardrailed_clinical_context: "bg-purple-50 text-purple-700",
  };
  return <span className={`rounded px-1.5 py-0.5 text-xs ${colors[usage] || "bg-gray-50 text-gray-600"}`}>{usage}</span>;
}
