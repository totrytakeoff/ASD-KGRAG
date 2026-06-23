import { useEffect, useState } from "react";
import {
  BarChart3,
  BookOpen,
  CheckSquare,
  Database,
  Eye,
  FileText,
  GitBranch,
  LayoutDashboard,
  LogOut,
  Network,
  Settings,
} from "lucide-react";
import { fetchStats, logout } from "./api";

interface NavItem {
  id: string;
  label: string;
  icon: React.ReactNode;
}

const navItems: NavItem[] = [
  { id: "overview", label: "概览", icon: <LayoutDashboard size={16} /> },
  { id: "entities", label: "实体", icon: <Database size={16} /> },
  { id: "relations", label: "关系", icon: <GitBranch size={16} /> },
  { id: "chunks", label: "Chunk", icon: <FileText size={16} /> },
  { id: "graph", label: "图谱可视化", icon: <Eye size={16} /> },
  { id: "guide", label: "使用说明", icon: <BookOpen size={16} /> },
  { id: "divider1", label: "―", icon: <span /> },
  { id: "eval-questions", label: "评估题集", icon: <CheckSquare size={16} /> },
  { id: "eval-runs", label: "评估运行", icon: <BarChart3 size={16} /> },
  { id: "aliases", label: "别名管理", icon: <GitBranch size={16} /> },
  { id: "settings", label: "系统设置", icon: <Settings size={16} /> },
];

export default function DashboardLayout({
  activeNav,
  onNavChange,
  children,
}: {
  activeNav: string;
  onNavChange: (id: string) => void;
  children: React.ReactNode;
}) {
  const [stats, setStats] = useState<Record<string, any> | null>(null);

  useEffect(() => {
    fetchStats().then(setStats).catch(() => {});
  }, []);

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-gray-50 font-sans">
      <aside className="flex h-full w-60 flex-col border-r border-gray-200 bg-white">
        <div className="flex items-center gap-2 border-b border-gray-100 px-5 py-4">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-medical-600 text-white">
            <Network size={18} />
          </div>
          <div>
            <div className="text-sm font-semibold text-gray-900">KGRAG</div>
            <div className="text-xs text-gray-500">管理后台</div>
          </div>
        </div>

        <nav className="flex-1 space-y-1 px-3 py-4">
          {navItems.map((item) => {
            if (item.id === "divider1") {
              return <div key="divider1" className="my-2 border-t border-gray-100" />;
            }
            return (
              <button
                key={item.id}
                onClick={() => onNavChange(item.id)}
                className={`flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition ${activeNav === item.id ? "bg-medical-50 text-medical-700 font-medium" : "text-gray-600 hover:bg-gray-50"}`}
              >
                {item.icon}
                {item.label}
              </button>
            );
          })}
        </nav>

        {stats && (
          <div className="border-t border-gray-100 px-5 py-3">
            <div className="grid grid-cols-2 gap-2 text-xs text-gray-500">
              <div>
                <div className="font-medium text-gray-700">{stats.entity_count?.toLocaleString() || '-'}</div>
                <div>实体</div>
              </div>
              <div>
                <div className="font-medium text-gray-700">{stats.relation_count?.toLocaleString() || '-'}</div>
                <div>关系</div>
              </div>
              <div>
                <div className="font-medium text-gray-700">{stats.chunk_count?.toLocaleString() || '-'}</div>
                <div>Chunk</div>
              </div>
              <div>
                <div className="font-medium text-gray-700">{(stats.entity_type_distribution as any[] || []).length || '-'}</div>
                <div>类型</div>
              </div>
            </div>
          </div>
        )}

        <div className="border-t border-gray-100 px-3 py-3">
          <button
            onClick={() => logout()}
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-gray-500 transition hover:bg-gray-50 hover:text-gray-700"
          >
            <LogOut size={15} />
            退出登录
          </button>
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto">
        <div className="px-8 py-6">{children}</div>
      </main>
    </div>
  );
}
