import { useEffect, useState } from "react";
import { Loader2, Plus, Save, Search, Trash2, X } from "lucide-react";
import { fetchAliases, updateAliases } from "./api";

function AliasGroupCard({
  group,
  index,
  onChange,
  onDelete,
}: {
  group: any;
  index: number;
  onChange: (i: number, g: any) => void;
  onDelete: (i: number) => void;
}) {
  const [aliasInput, setAliasInput] = useState("");

  const addAlias = () => {
    const alias = aliasInput.trim();
    if (!alias || group.aliases.includes(alias)) return;
    onChange(index, { ...group, aliases: [...group.aliases, alias] });
    setAliasInput("");
  };

  const removeAlias = (ai: number) => {
    const next = [...group.aliases];
    next.splice(ai, 1);
    onChange(index, { ...group, aliases: next });
  };

  return (
    <div className="rounded-lg border border-gray-100 bg-white p-4">
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="rounded bg-medical-50 px-2 py-0.5 text-xs font-medium text-medical-700">
            {group.type || "unknown"}
          </span>
          <span className="font-mono text-xs text-gray-400">{group.group_id}</span>
        </div>
        <button onClick={() => onDelete(index)} className="text-gray-300 hover:text-red-500">
          <Trash2 size={14} />
        </button>
      </div>

      <div className="space-y-1">
        <div className="text-xs font-medium text-gray-500">别名列表</div>
        <div className="flex flex-wrap gap-1.5">
          {group.aliases.map((a: string, ai: number) => (
            <span key={ai} className="inline-flex items-center gap-1 rounded bg-gray-50 px-2 py-0.5 text-xs text-gray-700">
              {a}
              <button onClick={() => removeAlias(ai)} className="text-gray-300 hover:text-red-500"><X size={12} /></button>
            </span>
          ))}
        </div>
      </div>

      <div className="mt-2 flex items-center gap-1">
        <input
          type="text"
          value={aliasInput}
          onChange={(e) => setAliasInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addAlias(); } }}
          placeholder="添加别名..."
          className="flex-1 rounded border border-gray-200 px-2 py-1 text-xs outline-none focus:border-medical-400"
        />
        <button onClick={addAlias} disabled={!aliasInput.trim()}
          className="rounded bg-medical-600 px-2 py-1 text-xs text-white hover:bg-medical-700 disabled:opacity-50">
          添加
        </button>
      </div>
    </div>
  );
}

function CandidateCard({
  candidate,
  onPromote,
  onDismiss,
}: {
  candidate: any;
  onPromote: () => void;
  onDismiss: () => void;
}) {
  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50/30 p-3">
      <div className="flex items-start justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="font-medium text-sm text-gray-800">{candidate.entity_name}</span>
          <span className="text-xs text-gray-400">({candidate.entity_type})</span>
        </div>
        <div className="flex gap-1">
          <button onClick={onPromote}
            className="rounded bg-green-600 px-2 py-0.5 text-xs text-white hover:bg-green-700">
            接纳
          </button>
          <button onClick={onDismiss}
            className="rounded bg-gray-300 px-2 py-0.5 text-xs text-gray-700 hover:bg-gray-400">
            忽略
          </button>
        </div>
      </div>
      {candidate.chinese_name && <div className="text-xs text-gray-500">中文: {candidate.chinese_name}</div>}
      {candidate.english_full_name && <div className="text-xs text-gray-500">英文: {candidate.english_full_name}</div>}
      <div className="mt-1 flex flex-wrap gap-1">
        {(candidate.aliases || []).map((a: string, i: number) => (
          <span key={i} className="rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-700">{a}</span>
        ))}
      </div>
      <div className="mt-1 text-xs text-gray-400">
        source: {candidate.source_note || "-"} | student: {candidate.student_id || "-"}
      </div>
    </div>
  );
}

export default function DashboardAliases() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");
  const [search, setSearch] = useState("");
  const [newGroup, setNewGroup] = useState({ type: "AssessmentTool", group_id: "", aliases: [""] });

  const load = async () => {
    setLoading(true);
    try {
      const d = await fetchAliases();
      setData(d);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);

  const handleSave = async () => {
    setSaving(true);
    setMsg("");
    try {
      const saved = await updateAliases(data);
      setData(saved);
      setMsg("保存成功");
    } catch (e: any) {
      setMsg("Error: " + e.message);
    } finally {
      setSaving(false);
    }
  };

  const handleGroupChange = (idx: number, group: any) => {
    const next = [...(data?.groups || [])];
    next[idx] = group;
    setData((d: any) => ({ ...d, groups: next }));
  };

  const handleGroupDelete = (idx: number) => {
    const next = [...(data?.groups || [])];
    next.splice(idx, 1);
    setData((d: any) => ({ ...d, groups: next }));
  };

  const handleAddGroup = () => {
    if (!newGroup.group_id.trim()) return;
    setData((d: any) => ({
      ...d,
      groups: [
        ...(d?.groups || []),
        { ...newGroup, aliases: newGroup.aliases.filter(Boolean) },
      ],
    }));
    setNewGroup({ type: "AssessmentTool", group_id: "", aliases: [""] });
  };

  const handlePromoteCandidate = (idx: number) => {
    const c = data?._candidates?.[idx];
    if (!c) return;
    const group = {
      type: c.entity_type || "unknown",
      group_id: c.entity_name?.toLowerCase().replace(/[\s/]+/g, "-") || `group_${Date.now()}`,
      aliases: c.aliases || [c.entity_name].filter(Boolean),
    };
    setData((d: any) => ({
      ...d,
      groups: [...(d.groups || []), group],
      _candidates: d._candidates.filter((_: any, i: number) => i !== idx),
    }));
  };

  const handleDismissCandidate = (idx: number) => {
    setData((d: any) => ({
      ...d,
      _candidates: d._candidates.filter((_: any, i: number) => i !== idx),
    }));
  };

  const filteredGroups = (data?.groups || []).filter((g: any) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      (g.group_id || "").toLowerCase().includes(q) ||
      g.aliases.some((a: string) => a.toLowerCase().includes(q))
    );
  });

  if (loading) return <div className="flex items-center justify-center py-20"><Loader2 size={20} className="animate-spin text-medical-600" /></div>;

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">实体别名管理</h1>
          <p className="mt-1 text-sm text-gray-500">管理图谱实体别名合并规则</p>
        </div>
        <button onClick={handleSave} disabled={saving}
          className="flex items-center gap-2 rounded-lg bg-medical-600 px-4 py-2 text-sm font-medium text-white hover:bg-medical-700 disabled:opacity-50">
          {saving ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />}
          保存
        </button>
      </div>

      {msg && (
        <div className="rounded-lg bg-medical-50 px-4 py-2 text-sm text-medical-700">{msg}</div>
      )}

      {/* Candidates */}
      {(data?._candidates || []).length > 0 && (
        <div className="rounded-xl border border-amber-200 bg-white p-5 shadow-sm">
          <h2 className="mb-3 text-sm font-semibold text-amber-800">
            待审核候选 ({data._candidates.length})
          </h2>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {data._candidates.map((c: any, i: number) => (
              <CandidateCard
                key={i}
                candidate={c}
                onPromote={() => handlePromoteCandidate(i)}
                onDismiss={() => handleDismissCandidate(i)}
              />
            ))}
          </div>
        </div>
      )}

      {/* Search + Add */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="搜索别名... (group_id / alias)"
            className="w-full rounded-lg border border-gray-200 px-9 py-2 text-sm outline-none focus:border-medical-400"
          />
        </div>
        <input
          type="text"
          value={newGroup.group_id}
          onChange={(e) => setNewGroup((p) => ({ ...p, group_id: e.target.value }))}
          placeholder="group_id"
          className="w-32 rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-medical-400"
        />
        <select
          value={newGroup.type}
          onChange={(e) => setNewGroup((p) => ({ ...p, type: e.target.value }))}
          className="rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-medical-400"
        >
          <option value="AssessmentTool">AssessmentTool</option>
          <option value="Intervention">Intervention</option>
          <option value="Symptom">Symptom</option>
          <option value="Diagnosis">Diagnosis</option>
          <option value="Medication">Medication</option>
        </select>
        <button onClick={handleAddGroup} disabled={!newGroup.group_id.trim()}
          className="flex shrink-0 items-center gap-1 rounded-lg bg-medical-600 px-3 py-2 text-sm font-medium text-white hover:bg-medical-700 disabled:opacity-50">
          <Plus size={14} /> 新增分组
        </button>
      </div>

      {/* Groups */}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        {filteredGroups.map((g: any, i: number) => (
          <AliasGroupCard
            key={g.group_id || i}
            group={g}
            index={i}
            onChange={handleGroupChange}
            onDelete={handleGroupDelete}
          />
        ))}
        {filteredGroups.length === 0 && (
          <div className="col-span-full rounded-lg border border-dashed border-gray-200 px-6 py-10 text-center text-sm text-gray-400">
            {search ? "无匹配别名分组" : "尚无别名分组，点击新增分组开始添加"}
          </div>
        )}
      </div>
    </div>
  );
}
