import { useEffect, useState } from "react";
import { Edit3, Loader2, Plus, Save, Trash2, X } from "lucide-react";
import {
  fetchSettings,
  updateSettings,
  fetchEvalModels,
  addEvalModel,
  updateEvalModel,
  deleteEvalModel,
} from "./api";

function EditModelDialog({
  model,
  index,
  onSave,
  onClose,
}: {
  model: any;
  index: number;
  onSave: (index: number, data: any) => Promise<void>;
  onClose: () => void;
}) {
  const [form, setForm] = useState({ ...model });
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      await onSave(index, form);
      onClose();
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={onClose}>
      <div className="w-full max-w-lg rounded-xl bg-white p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-semibold text-gray-800">编辑评估模型</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X size={18} /></button>
        </div>
        <div className="space-y-3">
          {[
            { key: "name", label: "模型名称", type: "text", placeholder: "deepseek-ai/DeepSeek-V4-Flash" },
            { key: "base_url", label: "API 地址", type: "text", placeholder: "https://api.openai.com/v1" },
            { key: "api_key", label: "API Key", type: "password", placeholder: "sk-..." },
            { key: "timeout", label: "超时(s)", type: "number" },
            { key: "max_tokens", label: "最大 Token", type: "number" },
          ].map((f) => (
            <div key={f.key}>
              <label className="block text-xs font-medium text-gray-500 mb-1">{f.label}</label>
              <input
                type={f.type || "text"}
                value={form[f.key] ?? ""}
                onChange={(e) =>
                  setForm((p: any) => ({
                    ...p,
                    [f.key]: f.type === "number" ? Number(e.target.value) : e.target.value,
                  }))
                }
                placeholder={f.placeholder}
                className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-medical-400"
              />
            </div>
          ))}
          <div className="flex items-center gap-2 pt-2">
            <label className="flex items-center gap-2 text-sm text-gray-600">
              <input
                type="checkbox"
                checked={form.enabled !== false}
                onChange={(e) => setForm((p: any) => ({ ...p, enabled: e.target.checked }))}
                className="rounded border-gray-300"
              />
              启用
            </label>
          </div>
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <button onClick={onClose} className="rounded-lg border border-gray-200 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50">取消</button>
          <button onClick={handleSave} disabled={saving || !form.name?.trim()}
            className="flex items-center gap-2 rounded-lg bg-medical-600 px-4 py-2 text-sm font-medium text-white hover:bg-medical-700 disabled:opacity-50">
            {saving ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />}
            保存
          </button>
        </div>
      </div>
    </div>
  );
}

export default function DashboardSettings() {
  const [settings, setSettings] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");
  const [models, setModels] = useState<any[]>([]);
  const [newModel, setNewModel] = useState({ name: "", base_url: "", api_key: "", timeout: 90, max_tokens: 1200, enabled: true });
  const [editIndex, setEditIndex] = useState<number | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const [s, m] = await Promise.all([fetchSettings(), fetchEvalModels()]);
      setSettings(s);
      setModels(m);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);

  const handleSaveActive = async () => {
    if (!settings?.active_model) return;
    setSaving(true);
    setMsg("");
    try {
      await updateSettings({ active_model: settings.active_model });
      setMsg("Active model saved.");
    } catch (e: any) {
      setMsg("Error: " + e.message);
    } finally {
      setSaving(false);
    }
  };

  const handleAddModel = async () => {
    if (!newModel.name.trim()) return;
    try {
      const updated = await addEvalModel(newModel);
      setModels(updated);
      setNewModel({ name: "", base_url: "", api_key: "", timeout: 90, max_tokens: 1200, enabled: true });
    } catch (e: any) {
      setMsg("Error: " + e.message);
    }
  };

  const handleToggleModel = async (idx: number) => {
    const m = models[idx];
    try {
      const updated = await updateEvalModel(idx, { enabled: !m.enabled });
      setModels(updated);
    } catch (e: any) {
      setMsg("Error: " + e.message);
    }
  };

  const handleEditModel = async (idx: number, data: any) => {
    try {
      const updated = await updateEvalModel(idx, data);
      setModels(updated);
    } catch (e: any) {
      setMsg("Error: " + e.message);
    }
  };

  const handleDeleteModel = async (idx: number) => {
    try {
      const updated = await deleteEvalModel(idx);
      setModels(updated);
    } catch (e: any) {
      setMsg("Error: " + e.message);
    }
  };

  if (loading) return <div className="flex items-center justify-center py-20"><Loader2 size={20} className="animate-spin text-medical-600" /></div>;

  return (
    <div className="mx-auto max-w-4xl space-y-8">
      {editIndex !== null && (
        <EditModelDialog
          model={models[editIndex]}
          index={editIndex}
          onSave={handleEditModel}
          onClose={() => setEditIndex(null)}
        />
      )}

      <div>
        <h1 className="text-xl font-semibold text-gray-900">系统设置</h1>
        <p className="mt-1 text-sm text-gray-500">问答模型配置与评估模型列表管理</p>
      </div>

      {msg && (
        <div className="rounded-lg bg-medical-50 px-4 py-2 text-sm text-medical-700">{msg}</div>
      )}

      {/* Active model config */}
      <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <h2 className="mb-4 text-base font-semibold text-gray-800">当前问答模型</h2>
        <div className="grid grid-cols-2 gap-4">
          {[
            { key: "name", label: "模型名称", placeholder: "deepseek-ai/DeepSeek-V4-Flash" },
            { key: "base_url", label: "API 地址", placeholder: "https://api.openai.com/v1" },
            { key: "api_key", label: "API Key", placeholder: "sk-..." },
          ].map((f) => (
            <div key={f.key}>
              <label className="block text-xs font-medium text-gray-500 mb-1">{f.label}</label>
              <input type={f.key === "api_key" ? "password" : "text"} value={settings?.active_model?.[f.key] || ""}
                onChange={(e) => setSettings((s: any) => ({ ...s, active_model: { ...s.active_model, [f.key]: e.target.value } }))}
                placeholder={f.placeholder}
                className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-medical-400" />
            </div>
          ))}
          {[
            { key: "timeout", label: "超时(s)", type: "number" },
            { key: "max_tokens", label: "最大 Token", type: "number" },
            { key: "max_retries", label: "最大重试", type: "number" },
          ].map((f) => (
            <div key={f.key}>
              <label className="block text-xs font-medium text-gray-500 mb-1">{f.label}</label>
              <input type={f.type || "text"} value={settings?.active_model?.[f.key] ?? ""}
                onChange={(e) => setSettings((s: any) => ({ ...s, active_model: { ...s.active_model, [f.key]: f.type === "number" ? Number(e.target.value) : e.target.value } }))}
                className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-medical-400" />
            </div>
          ))}
        </div>
        <button onClick={handleSaveActive} disabled={saving}
          className="mt-4 flex items-center gap-2 rounded-lg bg-medical-600 px-4 py-2 text-sm font-medium text-white hover:bg-medical-700 disabled:opacity-50">
          {saving ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />}
          保存配置
        </button>
        <p className="mt-2 text-xs text-gray-400">修改即时生效，无需重启服务。API Key 仅存储在配置文件中。</p>
      </div>

      {/* Eval models */}
      <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <h2 className="mb-4 text-base font-semibold text-gray-800">评估模型列表</h2>
        <p className="mb-4 text-sm text-gray-500">触发 CI/CD 评估时将依次测试列表中的所有已启用模型。</p>

        <div className="space-y-2">
          {models.map((m, i) => (
            <div key={i} className="flex items-center gap-3 rounded-lg border border-gray-100 bg-gray-50 px-4 py-3 text-sm">
              <button onClick={() => handleToggleModel(i)}
                className={`shrink-0 rounded px-2 py-0.5 text-xs font-medium ${m.enabled ? "bg-green-100 text-green-700" : "bg-gray-200 text-gray-500"}`}>
                {m.enabled ? "启用" : "禁用"}
              </button>
              <span className="font-medium text-gray-800 min-w-[140px]">{m.name}</span>
              <span className="text-xs text-gray-400 truncate max-w-[160px]">{m.base_url}</span>
              {m.api_key && <span className="text-xs text-gray-400">***</span>}
              {m.timeout != null && <span className="text-xs text-gray-400">{m.timeout}s</span>}
              <button onClick={() => setEditIndex(i)} title="编辑"
                className="text-gray-300 hover:text-medical-600"><Edit3 size={14} /></button>
              <button onClick={() => handleDeleteModel(i)} title="删除"
                className="text-gray-300 hover:text-red-500"><Trash2 size={14} /></button>
            </div>
          ))}
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <input type="text" placeholder="模型名称" value={newModel.name}
            onChange={(e) => setNewModel((p) => ({ ...p, name: e.target.value }))}
            className="w-40 rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-medical-400" />
          <input type="text" placeholder="API 地址" value={newModel.base_url}
            onChange={(e) => setNewModel((p) => ({ ...p, base_url: e.target.value }))}
            className="w-52 rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-medical-400" />
          <input type="password" placeholder="API Key" value={newModel.api_key}
            onChange={(e) => setNewModel((p) => ({ ...p, api_key: e.target.value }))}
            className="w-40 rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-medical-400" />
          <input type="number" placeholder="超时(s)" value={newModel.timeout}
            onChange={(e) => setNewModel((p) => ({ ...p, timeout: Number(e.target.value) }))}
            className="w-24 rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-medical-400" />
          <input type="number" placeholder="Max Tokens" value={newModel.max_tokens}
            onChange={(e) => setNewModel((p) => ({ ...p, max_tokens: Number(e.target.value) }))}
            className="w-28 rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-medical-400" />
          <button onClick={handleAddModel} disabled={!newModel.name.trim()}
            className="flex shrink-0 items-center gap-1 rounded-lg bg-medical-600 px-3 py-2 text-sm font-medium text-white hover:bg-medical-700 disabled:opacity-50">
            <Plus size={14} /> 添加
          </button>
        </div>
      </div>
    </div>
  );
}
