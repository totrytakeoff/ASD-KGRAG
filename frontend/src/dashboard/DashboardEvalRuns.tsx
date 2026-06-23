import { useEffect, useState, useCallback } from "react";
import { Archive, ChevronDown, ChevronUp, Eye, Loader2, Search, X } from "lucide-react";
import { fetchEvalRuns, fetchEvalRunDetail } from "./api";

const CHECK_LABELS: Record<string, string> = {
  retrieved_context: "上下文检索",
  retrieved_graph: "图谱检索",
  expected_term_seen: "预期术语匹配",
  answer_cited: "答案引用",
  guardrail_ok: "护栏声明",
};

const CHECK_DESCS: Record<string, string> = {
  retrieved_context: "是否成功检索到文献 Chunk",
  retrieved_graph: "是否成功检索到图关系路径",
  expected_term_seen: "预期术语是否出现在检索上下文中",
  answer_cited: "答案是否包含引用标记 [C*]/[G*]",
  guardrail_ok: "涉及诊断/干预的问题是否有护栏声明",
};

const FAILURE_STATUS_OPTIONS = [
  { value: "待修复", color: "bg-red-100 text-red-700" },
  { value: "已确认", color: "bg-amber-100 text-amber-700" },
  { value: "已修复", color: "bg-green-100 text-green-700" },
];

function statusKey(runId: string, qId: string) {
  return `kgrag_failure_status_${runId}_${qId}`;
}

function CheckRow({ name, ok }: { name: string; ok: boolean }) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className={ok ? "text-green-600" : "text-red-500"}>{ok ? "✅" : "❌"}</span>
      <span className="font-medium text-gray-700">{CHECK_LABELS[name] || name}</span>
      <span className="text-gray-400" title={CHECK_DESCS[name]}>
        ({CHECK_DESCS[name] || ""})
      </span>
    </div>
  );
}

function AnswerPanel({ result }: { result: any }) {
  const [open, setOpen] = useState(false);
  if (!result?.answer) return null;
  return (
    <div className="rounded-lg border border-gray-100">
      <button onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-xs font-medium text-gray-600 hover:bg-gray-50">
        {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        <Search size={13} />
        {"查看完整答案"}
      </button>
      {open && (
        <div className="border-t border-gray-100 px-3 py-3 text-xs text-gray-700 whitespace-pre-wrap leading-relaxed max-h-60 overflow-y-auto">
          {result.answer}
        </div>
      )}
    </div>
  );
}

function ContextPanel({ result }: { result: any }) {
  const [open, setOpen] = useState(false);
  const ctx = result?.context;
  if (!ctx) return null;
  const contexts = ctx.contexts || [];
  const relations = ctx.relations || [];
  return (
    <div className="rounded-lg border border-gray-100">
      <button onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-xs font-medium text-gray-600 hover:bg-gray-50">
        {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        <Eye size={13} />
        {"查看检索上下文"} ({contexts.length} Chunks, {relations.length} {"关系"})
      </button>
      {open && (
        <div className="border-t border-gray-100 px-3 py-3 space-y-3 max-h-80 overflow-y-auto">
          {contexts.length > 0 && (
            <div>
              <div className="text-xs font-semibold text-gray-600 mb-1">Chunks</div>
              {contexts.map((c: any, i: number) => (
                <div key={i} className="mb-2 rounded bg-gray-50 p-2 text-xs text-gray-700">
                  <div className="flex gap-2 mb-1">
                    <span className="rounded bg-medical-50 px-1 font-mono text-medical-700">{c.citation_id || `C${i+1}`}</span>
                    <span className="text-gray-500">{c.title || ""}</span>
                    {c.evidence_level && <span className="text-amber-600">E{c.evidence_level}</span>}
                    {c.score !== undefined && <span className="text-gray-400">score={c.score?.toFixed(3)}</span>}
                  </div>
                  <div className="text-gray-500 line-clamp-3">{c.retrieval || ""}</div>
                </div>
              ))}
            </div>
          )}
          {relations.length > 0 && (
            <div>
              <div className="text-xs font-semibold text-gray-600 mb-1">{"图谱关系"}</div>
              {relations.map((r: any, i: number) => (
                <div key={i} className="mb-1 flex items-center gap-1.5 text-xs text-gray-700">
                  <span className="rounded bg-red-50 px-1.5 py-0.5 text-red-700">{r.source}</span>
                  <span className="text-medical-600">({r.relation})</span>
                  <span className="rounded bg-blue-50 px-1.5 py-0.5 text-blue-700">{r.target}</span>
                  {r.confidence !== undefined && <span className="text-gray-400">conf={r.confidence?.toFixed(2)}</span>}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function MetricBadge({ label, value }: { label: string; value: any }) {
  if (value === null || value === undefined) return null;
  const display = typeof value === "boolean" ? (value ? "✅" : "❌") : value;
  return (
    <span className="inline-flex items-center gap-1 rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-600">
      {label}: {display}
    </span>
  );
}

function QuestionCard({
  item,
  runId,
  onStatusChange,
}: {
  item: any;
  runId: string;
  onStatusChange: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const checks = item.checks || {};
  const metrics = item.metrics || {};
  const hasError = !!item.error;
  const status = localStorage.getItem(statusKey(runId, item.id)) || "待修复";

  const setStatus = (s: string) => {
    localStorage.setItem(statusKey(runId, item.id), s);
    onStatusChange();
  };

  const statusColor =
    FAILURE_STATUS_OPTIONS.find((o) => o.value === status)?.color ||
    "bg-gray-100 text-gray-600";

  return (
    <div className={`rounded-lg border ${item.ok ? "border-gray-100" : "border-red-200"} bg-white`}>
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-gray-50"
      >
        <span className="mt-0.5 text-sm">{item.ok ? "✅" : "❌"}</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 text-xs text-gray-400">
            <span className="rounded bg-gray-100 px-1.5 py-0.5 font-mono">{item.id}</span>
            {item.category && (
              <span className="rounded bg-medical-50 px-1.5 py-0.5 text-medical-700">
                {item.category}
              </span>
            )}
            {metrics.elapsed_seconds !== undefined && (
              <span>{metrics.elapsed_seconds}s</span>
            )}
          </div>
          <div className="mt-1 text-sm font-medium text-gray-800 line-clamp-2">
            {item.query}
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {!item.ok && (
            <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${statusColor}`}>
              {status}
            </span>
          )}
          {expanded ? <ChevronUp size={16} className="text-gray-400" /> : <ChevronDown size={16} className="text-gray-400" />}
        </div>
      </button>

      {expanded && (
        <div className="border-t border-gray-100 px-4 py-3 space-y-3">
          {/* Checks */}
          {!hasError && Object.keys(checks).length > 0 && (
            <div className="space-y-1.5">
              <div className="text-xs font-semibold text-gray-600">检查项</div>
              {Object.entries(checks).map(([k, v]) => (
                <CheckRow key={k} name={k} ok={v as boolean} />
              ))}
            </div>
          )}

          {/* Error message */}
          {hasError && (
            <div className="rounded bg-red-50 p-2 text-xs text-red-700">
              <span className="font-semibold">错误:</span> {item.error}
            </div>
          )}

          {/* Metrics */}
          {!hasError && Object.keys(metrics).length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              {Object.entries(metrics).map(([k, v]) => (
                <MetricBadge key={k} label={k} value={v} />
              ))}
            </div>
          )}

          {/* Failure status */}
          {!item.ok && (
            <div className="flex items-center gap-2 text-xs text-gray-500">
              <span>状态:</span>
              <select
                value={status}
                onChange={(e) => setStatus(e.target.value)}
                className="rounded border border-gray-200 px-2 py-1 text-xs outline-none focus:border-medical-400"
              >
                {FAILURE_STATUS_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.value}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Answer + Context */}
          {item.result && (
            <div className="space-y-2">
              <AnswerPanel result={item.result} />
              <ContextPanel result={item.result} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

const ARCHIVE_KEY = "kgrag_archived_runs";

function getArchived(): Set<string> {
  try {
    return new Set(JSON.parse(localStorage.getItem(ARCHIVE_KEY) || "[]"));
  } catch { return new Set(); }
}

function toggleArchived(runId: string) {
  const archived = getArchived();
  if (archived.has(runId)) archived.delete(runId);
  else archived.add(runId);
  localStorage.setItem(ARCHIVE_KEY, JSON.stringify([...archived]));
}

export default function DashboardEvalRuns() {
  const [runs, setRuns] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedRun, setSelectedRun] = useState<string | null>(null);
  const [runDetail, setRunDetail] = useState<any>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [filter, setFilter] = useState<"all" | "failures">("all");
  const [refreshKey, setRefreshKey] = useState(0);
  const [showArchived, setShowArchived] = useState(false);

  useEffect(() => {
    setLoading(true);
    fetchEvalRuns()
      .then(setRuns)
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!selectedRun) {
      setRunDetail(null);
      return;
    }
    setDetailLoading(true);
    fetchEvalRunDetail(selectedRun)
      .then(setRunDetail)
      .finally(() => setDetailLoading(false));
  }, [selectedRun]);

  const triggerRefresh = useCallback(() => {
    setRefreshKey((k) => k + 1);
  }, []);

  const results = runDetail?.results || [];
  const displayResults =
    filter === "failures" ? results.filter((r: any) => !r.ok) : results;

  const archived = getArchived();
  const displayRuns = showArchived ? runs : runs.filter((r) => !archived.has(r.run_id));

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 size={20} className="animate-spin text-medical-600" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-gray-900">评估运行</h1>
        <p className="mt-1 text-sm text-gray-500">查看历史评估运行结果和详细检查日志</p>
      </div>

      {/* Archive toggle */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowArchived((v) => !v)}
            className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition ${
              showArchived
                ? "bg-gray-200 text-gray-700"
                : "text-gray-400 hover:text-gray-600"
            }`}
          >
            <Archive size={13} />
            显示已归档 ({archived.size})
          </button>
        </div>
        <div className="text-xs text-gray-400">
          {runs.length - archived.size} 条活跃 / {archived.size} 条已归档
        </div>
      </div>

      {/* Runs list */}
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {displayRuns.map((run) => (
          <div key={run.run_id} className="relative group">
            <button
              onClick={() => setSelectedRun(run.run_id)}
              className={`w-full rounded-lg border p-4 text-left transition ${
                selectedRun === run.run_id
                  ? "border-medical-300 bg-medical-50 shadow-sm"
                  : "border-gray-200 bg-white hover:border-medical-200 hover:shadow-sm"
              } ${archived.has(run.run_id) ? "opacity-50" : ""}`}
            >
              <div className="text-xs text-gray-400 font-mono">{run.run_id}</div>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="text-lg font-semibold text-gray-900">{run.ok ?? "-"}/{run.total ?? "-"}</span>
                <span className="text-sm font-medium text-gray-500">
                  {run.ok_rate != null ? `${(run.ok_rate * 100).toFixed(1)}%` : ""}
                </span>
              </div>
              <div className="mt-1 h-1.5 w-full rounded-full bg-gray-100 overflow-hidden">
                <div
                  className="h-full rounded-full bg-medical-500 transition-all"
                  style={{ width: `${((run.ok ?? 0) / (run.total || 1)) * 100}%` }}
                />
              </div>
            </button>
            <button
              onClick={(e) => {
                e.stopPropagation();
                toggleArchived(run.run_id);
                if (selectedRun === run.run_id) setSelectedRun(null);
                setRefreshKey((k) => k + 1);
              }}
              className="absolute right-2 top-2 rounded p-1 text-gray-300 opacity-0 transition hover:bg-gray-100 hover:text-gray-600 group-hover:opacity-100"
              title={archived.has(run.run_id) ? "恢复" : "归档"}
            >
              {archived.has(run.run_id) ? <X size={13} /> : <Archive size={13} />}
            </button>
          </div>
        ))}
        {displayRuns.length === 0 && (
          <div className="col-span-full rounded-lg border border-dashed border-gray-200 px-6 py-10 text-center text-sm text-gray-400">
            暂无评估运行记录。请在“评估运行”页面触发评估。
          </div>
        )}
      </div>

      {/* Run detail */}
      {selectedRun && (
        <div className="rounded-xl border border-gray-200 bg-white shadow-sm">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-gray-100 px-5 py-4">
            <div className="text-sm font-semibold text-gray-800">
              {runDetail?.summary?.total != null
                ? `详细结果 (总${runDetail.summary.total}题, 通过${runDetail.summary.ok}题)`
                : "详细结果"}
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setFilter("all")}
                className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                  filter === "all"
                    ? "bg-medical-600 text-white"
                    : "bg-gray-100 text-gray-600 hover:bg-gray-200"
                }`}
              >
                全部 ({results.length})
              </button>
              <button
                onClick={() => setFilter("failures")}
                className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                  filter === "failures"
                    ? "bg-red-600 text-white"
                    : "bg-gray-100 text-gray-600 hover:bg-gray-200"
                }`}
              >
                失败案例 ({results.filter((r: any) => !r.ok).length})
              </button>
            </div>
          </div>

          {/* Content */}
          <div className="p-5">
            {detailLoading ? (
              <div className="flex items-center justify-center py-10">
                <Loader2 size={18} className="animate-spin text-medical-600" />
              </div>
            ) : displayResults.length === 0 ? (
              <div className="py-10 text-center text-sm text-gray-400">
                {filter === "failures"
                  ? "暂无失败案例，全部通过！"
                  : "该次运行无结果数据。"}
              </div>
            ) : (
              <div className="space-y-3">
                {displayResults.map((item: any, i: number) => (
                  <QuestionCard
                    key={item.id || i}
                    item={item}
                    runId={selectedRun}
                    onStatusChange={triggerRefresh}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Select prompt when no run selected */}
      {!selectedRun && displayRuns.length > 0 && (
        <div className="rounded-xl border border-dashed border-gray-200 px-6 py-12 text-center text-sm text-gray-400">
          点击上方运行卡片查看详细结果
        </div>
      )}
      {!selectedRun && displayRuns.length === 0 && runs.length > 0 && (
        <div className="rounded-xl border border-dashed border-gray-200 px-6 py-12 text-center text-sm text-gray-400">
          所有运行记录已归档。点击"显示已归档"查看。
        </div>
      )}
    </div>
  );
}
