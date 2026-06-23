import { useEffect, useRef, useState } from "react";
import { CheckCircle, FileText, Loader2, Plus, Upload, XCircle } from "lucide-react";
import { uploadReturn, listReturns, deleteReturn, addEvalQuestion } from "./api";

const TASK_TYPE_LABELS: Record<string, string> = {
  QAQUESTION: "QA 问题收集",
  SAFETYQUESTION: "安全/负面问题收集",
  ALIAS: "实体别名候选收集",
  QAREVIEW: "QA 回答审核",
  CHUNKREVIEW: "Chunk 元数据复核",
};

function CSVImportTab({ onUploaded }: { onUploaded: () => void }) {
  const [files, setFiles] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [preview, setPreview] = useState<any>(null);
  const [msg, setMsg] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const load = async () => {
    setLoading(true);
    try {
      setFiles(await listReturns());
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setMsg("");
    setPreview(null);
    try {
      const result = await uploadReturn(file);
      setPreview(result);
      load();
      onUploaded();
    } catch (err: any) {
      setMsg("Error: " + err.message);
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const handleDelete = async (filename: string) => {
    try {
      await deleteReturn(filename);
      setFiles((prev) => prev.filter((f) => f.filename !== filename));
    } catch (err: any) {
      setMsg("Error: " + err.message);
    }
  };

  return (
    <div className="space-y-6">
      {msg && <div className="rounded-lg bg-medical-50 px-4 py-2 text-sm text-medical-700">{msg}</div>}

      <div className="rounded-xl border-2 border-dashed border-gray-200 bg-white p-8 text-center">
        <input ref={fileRef} type="file" accept=".csv" onChange={handleFileChange} className="hidden" id="return-file-input" />
        <label htmlFor="return-file-input" className="flex cursor-pointer flex-col items-center gap-2">
          {uploading ? (
            <Loader2 size={24} className="animate-spin text-medical-600" />
          ) : (
            <Upload size={24} className="text-gray-400" />
          )}
          <span className="text-sm font-medium text-gray-600">
            {uploading ? "正在上传解析..." : "点击选择 CSV 文件上传"}
          </span>
          <span className="text-xs text-gray-400">
            文件名必须以 QAQUESTION / SAFETYQUESTION / ALIAS / QAREVIEW / CHUNKREVIEW 开头
          </span>
        </label>
      </div>

      {preview && (
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div className="flex items-center gap-2 mb-4">
            <CheckCircle size={18} className="text-green-500" />
            <span className="font-semibold text-gray-800">验证通过</span>
          </div>
          <div className="space-y-2 text-sm text-gray-600">
            <div className="flex gap-2"><span className="font-medium text-gray-500">任务类型:</span><span>{TASK_TYPE_LABELS[preview.task_type] || preview.task_type}</span></div>
            <div className="flex gap-2"><span className="font-medium text-gray-500">文件名:</span><span className="font-mono">{preview.filename}</span></div>
            <div className="flex gap-2"><span className="font-medium text-gray-500">数据行数:</span><span>{preview.rows_count}</span></div>
            <div className="flex gap-2"><span className="font-medium text-gray-500">学生 ID:</span><span>{preview.student_id}</span></div>
            {preview.merge_result && (
              <div className="mt-3 rounded-lg bg-green-50 p-3 text-xs text-green-700">
                <div className="font-medium mb-1">合并结果:</div>
                {Object.entries(preview.merge_result).map(([k, v]) => <div key={k}>{k}: {String(v)}</div>)}
              </div>
            )}
          </div>
        </div>
      )}

      <div className="rounded-xl border border-gray-200 bg-white shadow-sm">
        <div className="border-b border-gray-100 px-5 py-3">
          <h2 className="text-sm font-semibold text-gray-800">已上传的文件</h2>
        </div>
        {loading ? (
          <div className="flex items-center justify-center py-10"><Loader2 size={18} className="animate-spin text-medical-600" /></div>
        ) : files.length === 0 ? (
          <div className="px-5 py-10 text-center text-sm text-gray-400">暂无已导入文件。</div>
        ) : (
          <div className="divide-y divide-gray-100">
            {files.map((f) => (
              <div key={f.filename} className="flex items-center gap-3 px-5 py-3 text-sm">
                <FileText size={16} className="text-gray-400" />
                <span className="text-xs text-gray-400">{TASK_TYPE_LABELS[f.task_type] || f.task_type}</span>
                <span className="flex-1 font-mono text-xs text-gray-700">{f.filename}</span>
                <span className="text-xs text-gray-400">{(f.size / 1024).toFixed(1)} KB</span>
                <button onClick={() => handleDelete(f.filename)} className="text-gray-300 hover:text-red-500" title="删除"><XCircle size={14} /></button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function ManualEntryTab({ onAdded }: { onAdded: () => void }) {
  const [form, setForm] = useState({
    id: "", category: "general", query: "", keywords: "",
    requires_guardrail: false, source_note: "",
  });
  const [adding, setAdding] = useState(false);
  const [msg, setMsg] = useState("");

  const handleAdd = async () => {
    if (!form.query.trim() || !form.id.trim()) return;
    setAdding(true);
    setMsg("");
    try {
      await addEvalQuestion({
        id: form.id,
        category: form.category,
        query: form.query,
        keywords: form.keywords.split(";").map((k: string) => k.trim()).filter(Boolean),
        requires_guardrail: form.requires_guardrail,
        source_note: form.source_note || undefined,
      });
      setForm({ id: "", category: "general", query: "", keywords: "", requires_guardrail: false, source_note: "" });
      setMsg("评估问题已添加");
      onAdded();
    } catch (err: any) {
      setMsg("Error: " + err.message);
    } finally {
      setAdding(false);
    }
  };

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
      {msg && <div className="mb-4 rounded-lg bg-medical-50 px-4 py-2 text-sm text-medical-700">{msg}</div>}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <label className="block text-xs font-medium text-gray-500 mb-1">问题 ID</label>
          <input type="text" value={form.id} onChange={(e) => setForm((p) => ({ ...p, id: e.target.value }))}
            placeholder="如: manual_Q001" className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-medical-400" />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-500 mb-1">分类</label>
          <select value={form.category} onChange={(e) => setForm((p) => ({ ...p, category: e.target.value }))}
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-medical-400">
            <option value="assessment">评估工具</option>
            <option value="intervention">干预方法</option>
            <option value="comorbidity">共病</option>
            <option value="risk">风险</option>
            <option value="safety">安全</option>
            <option value="general">通用</option>
          </select>
        </div>
        <div className="sm:col-span-2">
          <label className="block text-xs font-medium text-gray-500 mb-1">问题内容</label>
          <textarea value={form.query} onChange={(e) => setForm((p) => ({ ...p, query: e.target.value }))}
            placeholder="输入评估问题..."
            rows={2} className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-medical-400 resize-none" />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-500 mb-1">关键词 (分号分隔)</label>
          <input type="text" value={form.keywords} onChange={(e) => setForm((p) => ({ ...p, keywords: e.target.value }))}
            placeholder="ADOS;自闭症;诊断" className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-medical-400" />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-500 mb-1">来源备注</label>
          <input type="text" value={form.source_note} onChange={(e) => setForm((p) => ({ ...p, source_note: e.target.value }))}
            placeholder="如: 文献综述" className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-medical-400" />
        </div>
        <div className="sm:col-span-2">
          <label className="flex items-center gap-2 text-sm text-gray-600">
            <input type="checkbox" checked={form.requires_guardrail} onChange={(e) => setForm((p) => ({ ...p, requires_guardrail: e.target.checked }))}
              className="rounded border-gray-300" />
            需要护栏声明（涉及诊断/干预/用药的问题）
          </label>
        </div>
      </div>
      <div className="mt-4 flex justify-end">
        <button onClick={handleAdd} disabled={adding || !form.query.trim() || !form.id.trim()}
          className="flex items-center gap-2 rounded-lg bg-medical-600 px-4 py-2 text-sm font-medium text-white hover:bg-medical-700 disabled:opacity-50">
          {adding ? <Loader2 size={15} className="animate-spin" /> : <Plus size={15} />}
          添加评估问题
        </button>
      </div>
    </div>
  );
}

export default function DashboardReturns() {
  const [tab, setTab] = useState<"csv" | "manual">("csv");
  const [refreshKey, setRefreshKey] = useState(0);

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-gray-900">数据导入</h1>
        <p className="mt-1 text-sm text-gray-500">通过 CSV 批量导入或手动录入评估问题，系统自动校验并合并到项目数据中。</p>
      </div>

      <div className="flex items-center gap-2 border-b border-gray-200 pb-1">
        <button onClick={() => setTab("csv")}
          className={`px-4 py-2 text-sm font-medium transition border-b-2 -mb-px ${tab === "csv" ? "border-medical-600 text-medical-700" : "border-transparent text-gray-500 hover:text-gray-700"}`}>
          CSV 批量导入
        </button>
        <button onClick={() => setTab("manual")}
          className={`px-4 py-2 text-sm font-medium transition border-b-2 -mb-px ${tab === "manual" ? "border-medical-600 text-medical-700" : "border-transparent text-gray-500 hover:text-gray-700"}`}>
          手动录入
        </button>
      </div>

      {tab === "csv" && <CSVImportTab key={`csv-${refreshKey}`} onUploaded={() => setRefreshKey((k) => k + 1)} />}
      {tab === "manual" && <ManualEntryTab key={`manual-${refreshKey}`} onAdded={() => setRefreshKey((k) => k + 1)} />}
    </div>
  );
}
