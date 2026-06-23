import { useEffect, useState, useCallback, useRef } from "react";
import { CheckCircle, Loader2, Plus, Trash2, Upload, XCircle } from "lucide-react";
import { fetchEvalQuestions, addEvalQuestion, updateEvalQuestion, deleteEvalQuestion, uploadReturn } from "./api";

const CATEGORIES = ["assessment", "intervention", "comorbidity", "risk", "safety", "general"];

function CSVImportSection({ onImported }: { onImported: () => void }) {
  const [uploading, setUploading] = useState(false);
  const [preview, setPreview] = useState<any>(null);
  const [msg, setMsg] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setMsg("");
    setPreview(null);
    try {
      const result = await uploadReturn(file);
      setPreview(result);
      onImported();
    } catch (err: any) {
      setMsg("Error: " + err.message);
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  return (
    <div className="rounded-lg border border-dashed border-gray-200 bg-gray-50/30 p-4">
      <div className="text-xs font-semibold text-gray-600 mb-3">CSV 批量导入</div>
      {msg && <div className="mb-3 rounded bg-medical-50 px-3 py-1.5 text-xs text-medical-700">{msg}</div>}
      <input ref={fileRef} type="file" accept=".csv" onChange={handleFile} className="hidden" id="batch-csv-input" />
      <label htmlFor="batch-csv-input" className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm text-gray-600 hover:bg-gray-50">
        {uploading ? <Loader2 size={15} className="animate-spin" /> : <Upload size={15} />}
        {uploading ? "上传中..." : "选择 CSV 文件"}
      </label>
      <span className="ml-2 text-xs text-gray-400">
        支持 QAQUESTION / SAFETYQUESTION 格式，自动合并到题集
      </span>
      {preview && (
        <div className="mt-3 rounded bg-green-50 p-3 text-xs text-green-700">
          <CheckCircle size={14} className="inline mr-1" />
          导入 {preview.rows_count} 条，{preview.merge_result?.added || 0} 条新增
        </div>
      )}
    </div>
  );
}

export default function DashboardEvalQuestions() {
  const [questions, setQuestions] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<string | null>(null);
  const [form, setForm] = useState<any>({ id: "", category: "general", query: "", keywords: [], expect_graph_terms: [], requires_guardrail: false });
  const [keywordInput, setKeywordInput] = useState("");
  const [graphTermInput, setGraphTermInput] = useState("");
  const [showCSV, setShowCSV] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try { setQuestions(await fetchEvalQuestions()); } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, []);

  const resetForm = () => {
    setForm({ id: "", category: "general", query: "", keywords: [], expect_graph_terms: [], requires_guardrail: false });
    setKeywordInput("");
    setGraphTermInput("");
    setEditing(null);
  };

  const handleSubmit = async () => {
    if (!form.id.trim() || !form.query.trim()) return;
    try {
      if (editing) {
        const updated = await updateEvalQuestion(editing, form);
        setQuestions(updated);
      } else {
        const updated = await addEvalQuestion(form);
        setQuestions(updated);
      }
      resetForm();
    } catch (e: any) { alert("Error: " + e.message); }
  };

  const handleEdit = (q: any) => {
    setForm({ ...q, keywords: [...(q.keywords || [])], expect_graph_terms: [...(q.expect_graph_terms || [])] });
    setEditing(q.id);
  };

  const handleDelete = async (id: string) => {
    try { setQuestions(await deleteEvalQuestion(id)); } catch (e: any) { alert("Error: " + e.message); }
  };

  const addKeyword = () => {
    if (keywordInput.trim()) {
      setForm((f: any) => ({ ...f, keywords: [...f.keywords, keywordInput.trim()] }));
      setKeywordInput("");
    }
  };
  const addGraphTerm = () => {
    if (graphTermInput.trim()) {
      setForm((f: any) => ({ ...f, expect_graph_terms: [...f.expect_graph_terms, graphTermInput.trim()] }));
      setGraphTermInput("");
    }
  };

  if (loading) return <div className="flex items-center justify-center py-20"><Loader2 size={20} className="animate-spin text-medical-600" /></div>;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-gray-900">评估题集</h1>
        <p className="mt-1 text-sm text-gray-500">{questions.length} 道题 · 支持手动录入和 CSV 批量导入</p>
      </div>

      {/* Toggle CSV import */}
      <div className="flex items-center gap-2">
        <button onClick={() => setShowCSV((v) => !v)}
          className="flex items-center gap-1.5 rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50">
          <Upload size={13} />
          {showCSV ? "收起批量导入" : "CSV 批量导入"}
        </button>
      </div>
      {showCSV && <CSVImportSection onImported={load} />}

      {/* Add / Edit form */}
      <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <h2 className="mb-4 text-sm font-semibold text-gray-700">{editing ? "编辑题目" : "新增题目"}</h2>
        <div className="grid grid-cols-3 gap-3">
          <div>
            <label className="block text-xs text-gray-500 mb-1">ID</label>
            <input type="text" value={form.id} onChange={(e) => setForm((f: any) => ({ ...f, id: e.target.value }))}
              className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-medical-400" />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">分类</label>
            <select value={form.category} onChange={(e) => setForm((f: any) => ({ ...f, category: e.target.value }))}
              className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-medical-400">
              {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div className="flex items-end">
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input type="checkbox" checked={form.requires_guardrail} onChange={(e) => setForm((f: any) => ({ ...f, requires_guardrail: e.target.checked }))} />
              需要护栏
            </label>
          </div>
          <div className="col-span-3">
            <label className="block text-xs text-gray-500 mb-1">问题</label>
            <textarea rows={2} value={form.query} onChange={(e) => setForm((f: any) => ({ ...f, query: e.target.value }))}
              className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-medical-400" />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">关键词</label>
            <div className="flex gap-1">
              <input type="text" value={keywordInput} onChange={(e) => setKeywordInput(e.target.value)} onKeyDown={(e) => e.key === "Enter" && addKeyword()}
                className="flex-1 rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-medical-400" />
              <button onClick={addKeyword} className="rounded-lg border border-gray-200 px-2 text-sm hover:bg-gray-50">+</button>
            </div>
            <div className="mt-1 flex flex-wrap gap-1">
              {form.keywords.map((k: string, i: number) => (
                <span key={i} className="inline-flex items-center gap-1 rounded bg-medical-50 px-2 py-0.5 text-xs text-medical-700">
                  {k} <button onClick={() => setForm((f: any) => ({ ...f, keywords: f.keywords.filter((_: any, j: number) => j !== i) }))} className="text-medical-400 hover:text-red-500">&times;</button>
                </span>
              ))}
            </div>
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">期望图谱术语</label>
            <div className="flex gap-1">
              <input type="text" value={graphTermInput} onChange={(e) => setGraphTermInput(e.target.value)} onKeyDown={(e) => e.key === "Enter" && addGraphTerm()}
                className="flex-1 rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-medical-400" />
              <button onClick={addGraphTerm} className="rounded-lg border border-gray-200 px-2 text-sm hover:bg-gray-50">+</button>
            </div>
            <div className="mt-1 flex flex-wrap gap-1">
              {form.expect_graph_terms.map((t: string, i: number) => (
                <span key={i} className="inline-flex items-center gap-1 rounded bg-amber-50 px-2 py-0.5 text-xs text-amber-700">
                  {t} <button onClick={() => setForm((f: any) => ({ ...f, expect_graph_terms: f.expect_graph_terms.filter((_: any, j: number) => j !== i) }))} className="text-amber-400 hover:text-red-500">&times;</button>
                </span>
              ))}
            </div>
          </div>
        </div>
        <div className="mt-4 flex gap-2">
          <button onClick={handleSubmit} disabled={!form.id.trim() || !form.query.trim()}
            className="flex items-center gap-1 rounded-lg bg-medical-600 px-4 py-2 text-sm font-medium text-white hover:bg-medical-700 disabled:opacity-50">
            <Plus size={14} /> {editing ? "保存修改" : "添加题目"}
          </button>
          {editing && <button onClick={resetForm} className="rounded-lg border border-gray-200 px-4 py-2 text-sm hover:bg-gray-50">取消</button>}
        </div>
      </div>

      {/* Questions list */}
      <div className="space-y-2">
        {questions.map((q) => (
          <div key={q.id} className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs text-gray-400">{q.id}</span>
                  <span className="rounded bg-medical-50 px-1.5 py-0.5 text-xs text-medical-700">{q.category}</span>
                  {q.requires_guardrail && <span className="rounded bg-amber-50 px-1.5 py-0.5 text-xs text-amber-700">护栏</span>}
                  {(q.keywords || []).map((k: string) => (
                    <span key={k} className="text-xs text-gray-400">#{k}</span>
                  ))}
                </div>
                <p className="mt-1 text-sm text-gray-800">{q.query}</p>
              </div>
              <div className="flex shrink-0 gap-1">
                <button onClick={() => handleEdit(q)} className="rounded-lg border border-gray-200 px-3 py-1 text-xs text-gray-500 hover:bg-gray-50">编辑</button>
                <button onClick={() => handleDelete(q.id)} className="rounded-lg border border-gray-200 px-3 py-1 text-xs text-red-400 hover:bg-red-50"><Trash2 size={12} /></button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
