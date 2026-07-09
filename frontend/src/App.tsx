import { useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  ChevronDown,
  ChevronRight,
  Check,
  Edit3,
  Eraser,
  Loader2,
  MessageSquarePlus,
  Network,
  Search,
  Send,
  ShieldAlert,
  Stethoscope,
  Trash2,
  X,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import { BrowserRouter, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import remarkGfm from "remark-gfm";
import GraphView from "./GraphView";
import type { AiMessage, Conversation, Message } from "./types";
import Login from "./dashboard/Login";
import DashboardLayout from "./dashboard/DashboardLayout";
import DashboardOverview from "./dashboard/DashboardOverview";
import DashboardEntities from "./dashboard/DashboardEntities";
import DashboardRelations from "./dashboard/DashboardRelations";
import DashboardChunks from "./dashboard/DashboardChunks";
import DashboardGraph from "./dashboard/DashboardGraph";
import DashboardGuide from "./dashboard/DashboardGuide";
import DashboardSettings from "./dashboard/DashboardSettings";
import DashboardEvalQuestions from "./dashboard/DashboardEvalQuestions";
import DashboardEvalRuns from "./dashboard/DashboardEvalRuns";
import DashboardAliases from "./dashboard/DashboardAliases";
import { isAuthenticated, verifyAuth } from "./dashboard/api";

const nowISO = () => new Date().toISOString();

const uid = () => Math.random().toString(36).slice(2, 10);

const DEFAULT_CONVERSATION_TITLE = "新对话";
const CHAT_CONVERSATIONS_STORAGE_KEY = "kgrag_chat_conversations_v1";
const CHAT_ACTIVE_STORAGE_KEY = "kgrag_chat_active_id_v1";

function createConversation(title = DEFAULT_CONVERSATION_TITLE): Conversation {
  return {
    id: uid(),
    title,
    messages: [],
    updated_at: nowISO(),
  };
}

function isDefaultTitle(title: string) {
  return !title.trim() || title.trim() === DEFAULT_CONVERSATION_TITLE;
}

function generateConversationTitle(query: string) {
  const normalized = query
    .replace(/\s+/g, " ")
    .replace(/^[\s"'“”‘’]+|[\s"'“”‘’]+$/g, "")
    .replace(/[?？!！。.,，;；:：]+$/g, "");
  if (!normalized) return DEFAULT_CONVERSATION_TITLE;

  const withoutLeadIn = normalized.replace(
    /^(请问|请介绍一下|介绍一下|帮我分析一下|帮我看看|我想知道|想了解一下|能否说明|能不能说明|什么是|什么叫)/,
    "",
  );
  const title = withoutLeadIn || normalized;
  return title.length > 18 ? `${title.slice(0, 18)}...` : title;
}

function normalizeConversation(raw: any): Conversation | null {
  if (!raw || typeof raw !== "object" || typeof raw.id !== "string") return null;
  const messages = Array.isArray(raw.messages)
    ? raw.messages.filter(
        (m: any) =>
          m &&
          (m.role === "user" || m.role === "ai") &&
          typeof m.content === "string",
      )
    : [];
  return {
    id: raw.id,
    title:
      typeof raw.title === "string" && raw.title.trim()
        ? raw.title.trim()
        : DEFAULT_CONVERSATION_TITLE,
    messages,
    updated_at: typeof raw.updated_at === "string" ? raw.updated_at : nowISO(),
  };
}

function loadChatState() {
  if (typeof window === "undefined") {
    const fresh = createConversation();
    return { conversations: [fresh], activeId: fresh.id };
  }

  try {
    const stored = JSON.parse(localStorage.getItem(CHAT_CONVERSATIONS_STORAGE_KEY) || "[]");
    const conversations = Array.isArray(stored)
      ? stored.map(normalizeConversation).filter((c): c is Conversation => Boolean(c))
      : [];
    if (conversations.length > 0) {
      const storedActiveId = localStorage.getItem(CHAT_ACTIVE_STORAGE_KEY);
      const activeId = conversations.some((c) => c.id === storedActiveId)
        ? storedActiveId!
        : conversations[0].id;
      return { conversations, activeId };
    }
  } catch {
    localStorage.removeItem(CHAT_CONVERSATIONS_STORAGE_KEY);
    localStorage.removeItem(CHAT_ACTIVE_STORAGE_KEY);
  }

  const fresh = createConversation();
  return { conversations: [fresh], activeId: fresh.id };
}

async function askBackend(query: string): Promise<AiMessage | null> {
  try {
    const resp = await fetch("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query,
        dry_run: false,
        context_k: 6,
        graph_evidence_k: 4,
      }),
    });
    if (!resp.ok) return null;
    const data = await resp.json();
    if (!data?.answer) return null;
    const ctx = data.context || {};
    const relations = (ctx.relations || []).map((r: any) => ({
      source: r.source,
      target: r.target,
      relation: r.relation,
      support_count: r.support_count,
      confidence: r.confidence,
    }));
    const nodes = Array.from(new Set(relations.flatMap((r: any) => [r.source, r.target]))).map(
      (id: any) => ({ id, name: id, type: "Entity" }),
    );
    const citations = (ctx.contexts || []).map((c: any, i: number) => ({
      citation_id: c.citation_id || `C${i + 1}`,
      title: c.title,
      year: c.year,
      evidence_level: c.evidence_level,
      retrieval: c.retrieval,
      score: c.score,
    }));
    return {
      role: "ai",
      content: data.answer,
      relations,
      nodes,
      citations,
      retrieved_at: nowISO(),
    };
  } catch {
    return null;
  }
}

function Sidebar({
  conversations,
  activeId,
  onSelect,
  onNew,
  onDelete,
  onRename,
}: {
  conversations: Conversation[];
  activeId: string;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
  onRename: (id: string, title: string) => void;
}) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState("");

  const startRename = (conversation: Conversation) => {
    setEditingId(conversation.id);
    setEditingTitle(conversation.title);
  };

  const finishRename = () => {
    if (!editingId) return;
    onRename(editingId, editingTitle);
    setEditingId(null);
    setEditingTitle("");
  };

  const cancelRename = () => {
    setEditingId(null);
    setEditingTitle("");
  };

  return (
    <aside className="flex h-full w-72 flex-col border-r border-gray-200 bg-white">
      <div className="flex items-center gap-2 border-b border-gray-100 px-5 py-4">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-medical-600 text-white">
          <Stethoscope size={20} />
        </div>
        <div>
          <div className="text-sm font-semibold text-gray-900">ASD-KGRAG</div>
          <div className="text-xs text-gray-500">医疗知识图谱问答</div>
        </div>
      </div>

      <div className="px-3 py-3">
        <button
          onClick={onNew}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-medical-600 px-3 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-medical-700"
        >
          <MessageSquarePlus size={16} />
          新建问诊对话
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-2 pb-3">
        <div className="px-2 py-2 text-xs font-medium uppercase tracking-wider text-gray-400">
          历史对话
        </div>
        <ul className="space-y-1">
          {conversations.map((c) => (
            <li key={c.id}>
              <div
                className={`group flex cursor-pointer items-center gap-2 rounded-lg px-3 py-2 text-sm transition ${
                  c.id === activeId
                    ? "bg-medical-50 text-medical-700"
                    : "text-gray-700 hover:bg-gray-50"
                }`}
                onClick={() => onSelect(c.id)}
              >
                <Activity
                  size={14}
                  className={c.id === activeId ? "text-medical-600" : "text-gray-400"}
                />
                {editingId === c.id ? (
                  <input
                    value={editingTitle}
                    onChange={(e) => setEditingTitle(e.target.value)}
                    onClick={(e) => e.stopPropagation()}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        finishRename();
                      }
                      if (e.key === "Escape") {
                        e.preventDefault();
                        cancelRename();
                      }
                    }}
                    autoFocus
                    className="min-w-0 flex-1 rounded border border-medical-200 bg-white px-2 py-1 text-sm text-gray-800 outline-none focus:border-medical-500"
                  />
                ) : (
                  <span className="flex-1 truncate">{c.title}</span>
                )}
                {editingId === c.id ? (
                  <div className="flex items-center gap-1">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        finishRename();
                      }}
                      className="text-gray-400 transition hover:text-medical-600"
                      title="保存名称"
                    >
                      <Check size={14} />
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        cancelRename();
                      }}
                      className="text-gray-400 transition hover:text-gray-600"
                      title="取消重命名"
                    >
                      <X size={14} />
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      startRename(c);
                    }}
                    className="text-gray-300 opacity-0 transition hover:text-medical-600 group-hover:opacity-100"
                    title="重命名对话"
                  >
                    <Edit3 size={14} />
                  </button>
                )}
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onDelete(c.id);
                  }}
                  className="text-gray-300 opacity-0 transition hover:text-red-500 group-hover:opacity-100"
                  title="删除对话"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </li>
          ))}
        </ul>
      </div>

      <div className="border-t border-gray-100 px-5 py-3 text-xs text-gray-400">
        KGRAG v0.1 · Neo4j + Qdrant
      </div>
    </aside>
  );
}

function MessageBubble({ msg }: { msg: Message }) {
  if (msg.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-medical-600 px-4 py-3 text-sm text-white shadow-sm">
          <p className="whitespace-pre-wrap leading-relaxed">{msg.content}</p>
        </div>
      </div>
    );
  }
  return <AiBubble msg={msg} />;
}

function AiBubble({ msg }: { msg: AiMessage }) {
  const [showGraph, setShowGraph] = useState(false);
  const [showCitations, setShowCitations] = useState(false);
  const hasGraph = (msg.relations?.length ?? 0) > 0;
  const hasCitations = (msg.citations?.length ?? 0) > 0;

  return (
    <div className="flex justify-start">
      <div className="flex w-full max-w-[88%] gap-3">
        <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-medical-100 text-medical-700">
          <Stethoscope size={16} />
        </div>
        <div className="flex-1 space-y-2">
          <div className="rounded-2xl rounded-bl-sm border border-gray-100 bg-white px-4 py-3 shadow-sm">
            <div className="markdown-body text-sm text-gray-800">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
            </div>
          </div>

          {hasCitations && (
            <div className="rounded-lg border border-gray-100 bg-gray-50/60">
              <button
                onClick={() => setShowCitations((v) => !v)}
                className="flex w-full items-center gap-2 px-3 py-2 text-xs font-medium text-gray-600"
              >
                {showCitations ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                <Search size={13} />
                文献证据引用({msg.citations!.length})
              </button>
              {showCitations && (
                <div className="border-t border-gray-100 px-3 py-2">
                  <ul className="space-y-1">
                    {msg.citations!.map((c) => (
                      <li
                        key={c.citation_id}
                        className="flex items-start gap-2 text-xs text-gray-600"
                      >
                        <span className="mt-0.5 rounded bg-medical-50 px-1.5 py-0.5 font-mono text-medical-700">
                          {c.citation_id}
                        </span>
                        <span className="flex-1">
                          <span className="font-medium text-gray-700">
                            {c.title || "未命名文献"}
                          </span>
                          {c.year && <span className="text-gray-400"> · {c.year}</span>}
                          {c.evidence_level && (
                            <span className="ml-1 rounded bg-amber-50 px-1 text-amber-700">
                              证据 {c.evidence_level}
                            </span>
                          )}
                          {c.retrieval && (
                            <span className="ml-1 text-gray-400">· {c.retrieval}</span>
                          )}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {hasGraph && (
            <div className="rounded-lg border border-medical-100 bg-medical-50/30">
              <button
                onClick={() => setShowGraph((v) => !v)}
                className="flex w-full items-center gap-2 px-3 py-2 text-xs font-medium text-medical-700"
              >
                {showGraph ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                <Network size={13} />
                图谱证据路径(KGRAG)
                <span className="text-gray-400">· {msg.relations!.length} 条关系</span>
              </button>
              {showGraph && (
                <div className="space-y-3 border-t border-medical-100 px-3 py-3">
                  <ul className="space-y-1.5">
                    {msg.relations!.map((r, i) => (
                      <li
                        key={i}
                        className="flex flex-wrap items-center gap-1.5 text-xs text-gray-700"
                      >
                        <span className="rounded bg-red-50 px-1.5 py-0.5 text-red-700">
                          {r.source}
                        </span>
                        <span className="font-mono text-medical-600">({r.relation})</span>
                        <ChevronRight size={12} className="text-gray-400" />
                        <span className="rounded bg-blue-50 px-1.5 py-0.5 text-blue-700">
                          {r.target}
                        </span>
                        {r.support_count !== undefined && (
                          <span className="ml-1 text-gray-400">support={r.support_count}</span>
                        )}
                      </li>
                    ))}
                  </ul>
                  {msg.nodes && msg.nodes.length > 0 && (
                    <div className="rounded-lg border border-gray-100 bg-white p-2">
                      <GraphView nodes={msg.nodes!} edges={msg.relations!} />
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function LoadingBubble({ stage }: { stage: number }) {
  const stages = [
    "正在解析问题…",
    "正在检索医疗知识图谱…",
    "正在召回向量证据…",
    "正在合成医学回答…",
  ];
  return (
    <div className="flex justify-start">
      <div className="flex gap-3">
        <div className="mt-1 flex h-8 w-8 items-center justify-center rounded-lg bg-medical-100 text-medical-700">
          <Stethoscope size={16} />
        </div>
        <div className="flex items-center gap-2 rounded-2xl rounded-bl-sm border border-gray-100 bg-white px-4 py-3 shadow-sm">
          <Loader2 size={14} className="animate-spin text-medical-600" />
          <span className="text-sm text-gray-600">{stages[stage] ?? stages[0]}</span>
        </div>
      </div>
    </div>
  );
}

function InputArea({
  value,
  onChange,
  onSend,
  onClear,
  loading,
}: {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  onClear: () => void;
  loading: boolean;
}) {
  const taRef = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, 200)}px`;
  }, [value]);

  return (
    <div className="border-t border-gray-200 bg-white px-6 py-4">
      <div className="mx-auto flex max-w-4xl items-end gap-2">
        <div className="flex-1 rounded-2xl border border-gray-200 bg-white px-4 py-2 shadow-sm focus-within:border-medical-400">
          <textarea
            ref={taRef}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                onSend();
              }
            }}
            placeholder="输入医学问题,例如:ADOS 在 ASD 评估中有什么作用?"
            rows={1}
            className="block w-full resize-none bg-transparent text-sm leading-relaxed text-gray-800 outline-none placeholder:text-gray-400"
          />
        </div>
        <button
          onClick={onClear}
          disabled={loading}
          className="flex h-11 items-center gap-1.5 rounded-2xl border border-gray-200 bg-white px-3 text-sm text-gray-600 shadow-sm transition hover:bg-gray-50 disabled:opacity-50"
          title="清空当前对话上下文"
        >
          <Eraser size={15} />
        </button>
        <button
          onClick={onSend}
          disabled={loading || !value.trim()}
          className="flex h-11 items-center gap-1.5 rounded-2xl bg-medical-600 px-5 text-sm font-medium text-white shadow-sm transition hover:bg-medical-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />}
          发送
        </button>
      </div>
      <div className="mx-auto mt-2 flex max-w-4xl items-center gap-1.5 text-xs text-gray-400">
        <ShieldAlert size={12} />
        回答仅供知识参考,不能替代专业医疗评估或临床决策。Enter 发送,Shift+Enter 换行。
      </div>
    </div>
  );
}

function ChatApp() {
  const [initialChatState] = useState(loadChatState);
  const [conversations, setConversations] = useState<Conversation[]>(
    initialChatState.conversations,
  );
  const [activeId, setActiveId] = useState<string>(initialChatState.activeId);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadingStage, setLoadingStage] = useState(0);
  const [headerEditing, setHeaderEditing] = useState(false);
  const [headerTitle, setHeaderTitle] = useState("");

  const active = useMemo(
    () => conversations.find((c) => c.id === activeId) ?? conversations[0],
    [conversations, activeId],
  );

  const scrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [active?.messages, loading]);

  useEffect(() => {
    localStorage.setItem(CHAT_CONVERSATIONS_STORAGE_KEY, JSON.stringify(conversations));
  }, [conversations]);

  useEffect(() => {
    localStorage.setItem(CHAT_ACTIVE_STORAGE_KEY, activeId);
  }, [activeId]);

  useEffect(() => {
    if (!loading) return;
    setLoadingStage(0);
    const t = setInterval(() => {
      setLoadingStage((s) => Math.min(s + 1, 3));
    }, 900);
    return () => clearInterval(t);
  }, [loading]);

  const updateActive = (fn: (c: Conversation) => Conversation) => {
    setConversations((prev) => prev.map((c) => (c.id === activeId ? fn(c) : c)));
  };

  const renameConversation = (id: string, title: string) => {
    const nextTitle = title.trim() || DEFAULT_CONVERSATION_TITLE;
    setConversations((prev) =>
      prev.map((c) =>
        c.id === id ? { ...c, title: nextTitle, updated_at: nowISO() } : c,
      ),
    );
  };

  const startHeaderRename = () => {
    if (!active) return;
    setHeaderTitle(active.title);
    setHeaderEditing(true);
  };

  const finishHeaderRename = () => {
    if (!active) return;
    renameConversation(active.id, headerTitle);
    setHeaderEditing(false);
    setHeaderTitle("");
  };

  const handleSend = async () => {
    const q = input.trim();
    if (!q || loading) return;
    setInput("");
    updateActive((c) => ({
      ...c,
      title:
        isDefaultTitle(c.title) && c.messages.length === 0
          ? generateConversationTitle(q)
          : c.title,
      messages: [...c.messages, { role: "user", content: q }],
      updated_at: nowISO(),
    }));
    setLoading(true);
    const ai = await askBackend(q);
    setLoading(false);
    updateActive((c) => ({
      ...c,
      messages: [
        ...c.messages,
        ai ?? {
          role: "ai",
          content:
            "⚠️ 暂时无法连接后端 `/ask`。请确认 `scripts/qa/kgrag_api.py` 已在 8010 端口运行。当前显示的是 Mock 回答占位。\n\n若后端不可用,可参考侧边栏历史对话预览 KGRAG 效果。",
        },
      ],
      updated_at: nowISO(),
    }));
  };

  const handleNew = () => {
    const conv = createConversation();
    setConversations((prev) => [conv, ...prev]);
    setActiveId(conv.id);
    setHeaderEditing(false);
  };

  const handleClear = () => {
    updateActive((c) => ({
      ...c,
      messages: [],
      title: DEFAULT_CONVERSATION_TITLE,
      updated_at: nowISO(),
    }));
  };

  const handleDelete = (id: string) => {
    setConversations((prev) => {
      const next = prev.filter((c) => c.id !== id);
      if (next.length === 0) {
        const fresh = createConversation();
        setActiveId(fresh.id);
        return [fresh];
      }
      if (id === activeId) setActiveId(next[0].id);
      return next;
    });
  };

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-gray-50 font-sans">
      <Sidebar
        conversations={conversations}
        activeId={activeId}
        onSelect={setActiveId}
        onNew={handleNew}
        onDelete={handleDelete}
        onRename={renameConversation}
      />
      <main className="flex flex-1 flex-col">
        <header className="border-b border-gray-200 bg-white px-6 py-3">
          <div className="flex items-center justify-between">
            <div>
              <div className="flex items-center gap-2">
                {headerEditing ? (
                  <>
                    <input
                      value={headerTitle}
                      onChange={(e) => setHeaderTitle(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          finishHeaderRename();
                        }
                        if (e.key === "Escape") {
                          e.preventDefault();
                          setHeaderEditing(false);
                          setHeaderTitle("");
                        }
                      }}
                      autoFocus
                      className="h-8 min-w-64 rounded border border-medical-200 px-2 text-base font-semibold text-gray-900 outline-none focus:border-medical-500"
                    />
                    <button
                      onClick={finishHeaderRename}
                      className="text-gray-400 transition hover:text-medical-600"
                      title="保存名称"
                    >
                      <Check size={16} />
                    </button>
                    <button
                      onClick={() => {
                        setHeaderEditing(false);
                        setHeaderTitle("");
                      }}
                      className="text-gray-400 transition hover:text-gray-600"
                      title="取消重命名"
                    >
                      <X size={16} />
                    </button>
                  </>
                ) : (
                  <>
                    <h1 className="text-base font-semibold text-gray-900">{active?.title}</h1>
                    <button
                      onClick={startHeaderRename}
                      className="text-gray-300 transition hover:text-medical-600"
                      title="重命名对话"
                    >
                      <Edit3 size={15} />
                    </button>
                  </>
                )}
              </div>
              <div className="text-xs text-gray-500">KGRAG 检索增强生成 · 图谱 + 向量混合召回</div>
            </div>
            <div className="flex items-center gap-2 rounded-full bg-medical-50 px-3 py-1 text-xs font-medium text-medical-700">
              <span className="h-1.5 w-1.5 rounded-full bg-medical-500" />
              在线
            </div>
          </div>
        </header>

        <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-6">
          <div className="mx-auto flex max-w-4xl flex-col gap-5">
            {active?.messages.length === 0 && (
              <div className="mx-auto mt-20 max-w-md text-center">
                <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-medical-100 text-medical-700">
                  <Stethoscope size={28} />
                </div>
                <h2 className="text-lg font-semibold text-gray-800">ASD 领域 KGRAG 问答</h2>
                <p className="mt-2 text-sm text-gray-500">
                  基于知识图谱与向量证据的医学问答。输入问题开始,例如:
                </p>
                <div className="mt-4 space-y-2">
                  {[
                    "ADOS 是什么?它在 ASD 评估中有什么作用?",
                    "ABA 干预对孤独症孩子效果怎么样?",
                    "ASD 常见共病有哪些?",
                  ].map((s) => (
                    <button
                      key={s}
                      onClick={() => setInput(s)}
                      className="block w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-left text-sm text-gray-600 shadow-sm transition hover:border-medical-300 hover:bg-medical-50/40"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {active?.messages.map((m, i) => (
              <MessageBubble key={i} msg={m} />
            ))}
            {loading && <LoadingBubble stage={loadingStage} />}
          </div>
        </div>

        <InputArea
          value={input}
          onChange={setInput}
          onSend={handleSend}
          onClear={handleClear}
          loading={loading}
        />
      </main>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Dashboard wrapper with internal navigation state
// ---------------------------------------------------------------------------

function DashboardApp() {
  const navigate = useNavigate();
  const [activeNav, setActiveNav] = useState(() => {
    if (typeof window !== "undefined") {
      return window.location.hash.replace("#", "") || "overview";
    }
    return "overview";
  });

  const handleNavChange = (id: string) => {
    setActiveNav(id);
    window.location.hash = id;
  };

  const renderContent = () => {
    switch (activeNav) {
      case "entities":
        return <DashboardEntities />;
      case "relations":
        return <DashboardRelations />;
      case "chunks":
        return <DashboardChunks />;
      case "graph":
        return <DashboardGraph />;
      case "guide":
        return <DashboardGuide />;
      case "settings":
        return <DashboardSettings />;
      case "eval-questions":
        return <DashboardEvalQuestions />;
      case "eval-runs":
        return <DashboardEvalRuns />;
      case "aliases":
        return <DashboardAliases />;
      default:
        return <DashboardOverview />;
    }
  };

  return (
    <DashboardLayout activeNav={activeNav} onNavChange={handleNavChange}>
      {renderContent()}
    </DashboardLayout>
  );
}

// ---------------------------------------------------------------------------
// Route guard
// ---------------------------------------------------------------------------

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const [ok, setOk] = useState<boolean | null>(null);

  useEffect(() => {
    verifyAuth().then(setOk);
  }, []);

  if (ok === null) {
    return (
      <div className="flex h-screen items-center justify-center">
        <Loader2 size={20} className="animate-spin text-medical-600" />
      </div>
    );
  }
  if (!ok) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function LoginRoute() {
  const navigate = useNavigate();
  if (isAuthenticated()) return <Navigate to="/dashboard" replace />;
  return <Login onLogin={() => navigate("/dashboard")} />;
}

// ---------------------------------------------------------------------------
// Root App with routing
// ---------------------------------------------------------------------------

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginRoute />} />
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute>
              <DashboardApp />
            </ProtectedRoute>
          }
        />
        <Route path="/*" element={<ChatApp />} />
      </Routes>
    </BrowserRouter>
  );
}
