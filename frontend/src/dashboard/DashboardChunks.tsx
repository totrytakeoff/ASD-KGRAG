import { useEffect, useState, useCallback } from "react";
import { ChevronLeft, ChevronRight, Loader2, Search } from "lucide-react";
import { fetchChunks } from "./api";

interface Chunk {
  chunk_id: string;
  doc_id: string;
  title: string;
  year: number | null;
  evidence_level: string;
  source_type: string;
  page_start: number | null;
  page_end: number | null;
  text_preview: string;
  text_length: number;
}

interface PageResult {
  items: Chunk[];
  total: number;
  page: number;
  page_size: number;
}

export default function DashboardChunks() {
  const [data, setData] = useState<PageResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [docId, setDocId] = useState("");
  const [evLevel, setEvLevel] = useState("");
  const [page, setPage] = useState(1);
  const [jumpPage, setJumpPage] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await fetchChunks({ page, page_size: 20, search, doc_id: docId, evidence_level: evLevel });
      setData(result);
    } finally {
      setLoading(false);
    }
  }, [page, search, docId, evLevel]);

  useEffect(() => { load(); }, [load]);

  const totalPages = data ? Math.ceil(data.total / data.page_size) : 0;

  const evColors: Record<string, string> = {
    A: "bg-green-100 text-green-800",
    B: "bg-blue-100 text-blue-800",
    C: "bg-amber-100 text-amber-800",
    D: "bg-red-100 text-red-800",
  };
  const srcColors: Record<string, string> = {
    article: "bg-gray-100 text-gray-700",
    narrative_review: "bg-purple-100 text-purple-700",
    systematic_review_or_meta: "bg-indigo-100 text-indigo-700",
    trial: "bg-emerald-100 text-emerald-700",
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-gray-900">Chunk 浏览</h1>
        <p className="mt-1 text-sm text-gray-500">文献片段 ({data?.total?.toLocaleString() || "…"} 条)</p>
      </div>

      <div className="flex items-center gap-3">
        <div className="relative flex-1">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input type="text" placeholder="搜索 chunk 内容…" value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
            className="w-full rounded-lg border border-gray-200 py-2 pl-9 pr-3 text-sm outline-none focus:border-medical-400" />
        </div>
        <input type="text" placeholder="doc_id 过滤" value={docId}
          onChange={(e) => { setDocId(e.target.value); setPage(1); }}
          className="w-40 rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-medical-400" />
        <select value={evLevel} onChange={(e) => { setEvLevel(e.target.value); setPage(1); }}
          className="rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-medical-400">
          <option value="">全部等级</option>
          <option value="A">A</option>
          <option value="B">B</option>
          <option value="C">C</option>
          <option value="D">D</option>
        </select>
      </div>

      <div className="space-y-3">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 size={18} className="animate-spin text-medical-600" />
          </div>
        ) : (
          data?.items.map((c) => (
            <div key={c.chunk_id} className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <h3 className="truncate text-sm font-medium text-gray-900">{c.title}</h3>
                    <span className={`shrink-0 rounded px-1.5 py-0.5 text-xs font-medium ${evColors[c.evidence_level] || "bg-gray-100 text-gray-600"}`}>{c.evidence_level}</span>
                    <span className={`shrink-0 rounded px-1.5 py-0.5 text-xs ${srcColors[c.source_type] || "bg-gray-100 text-gray-600"}`}>{c.source_type}</span>
                  </div>
                  <div className="mt-1 flex items-center gap-3 text-xs text-gray-400">
                    <span>doc: <code className="font-mono">{c.doc_id}</code></span>
                    {c.year && <span>{c.year}</span>}
                    {c.page_start != null && <span>页 {c.page_start}–{c.page_end}</span>}
                    <span>{c.text_length} 字符</span>
                  </div>
                </div>
                <button onClick={() => setExpandedId(expandedId === c.chunk_id ? null : c.chunk_id)}
                  className="shrink-0 rounded-lg border border-gray-200 px-3 py-1 text-xs text-gray-500 hover:bg-gray-50">
                  {expandedId === c.chunk_id ? "收起" : "预览"}
                </button>
              </div>
              {expandedId === c.chunk_id && (
                <div className="mt-3 max-h-60 overflow-y-auto rounded-lg bg-gray-50 p-3 text-xs leading-relaxed text-gray-700">
                  {c.text_preview}
                </div>
              )}
            </div>
          ))
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
