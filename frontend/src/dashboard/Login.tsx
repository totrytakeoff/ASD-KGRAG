import { useState } from "react";
import { Loader2, LogIn, ShieldAlert } from "lucide-react";
import { login } from "./api";

export default function Login({ onLogin }: { onLogin: () => void }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!password.trim()) return;
    setLoading(true);
    setError("");
    try {
      await login(password.trim());
      onLogin();
    } catch (err: any) {
      setError(err.message || "登录失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex h-screen w-screen items-center justify-center bg-gray-50">
      <div className="w-full max-w-sm rounded-2xl border border-gray-200 bg-white p-8 shadow-sm">
        <div className="mb-6 text-center">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-medical-600 text-white">
            <ShieldAlert size={24} />
          </div>
          <h1 className="text-lg font-semibold text-gray-900">ASD-KGRAG Dashboard</h1>
          <p className="mt-1 text-sm text-gray-500">知识图谱协作管理后台</p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700">管理员密码</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="请输入密码"
              className="mt-1 block w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-medical-400 focus:ring-1 focus:ring-medical-400"
              autoFocus
            />
          </div>
          {error && (
            <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{error}</div>
          )}
          <button
            type="submit"
            disabled={loading || !password.trim()}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-medical-600 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-medical-700 disabled:opacity-50"
          >
            {loading ? <Loader2 size={16} className="animate-spin" /> : <LogIn size={16} />}
            登录
          </button>
        </form>
      </div>
    </div>
  );
}
