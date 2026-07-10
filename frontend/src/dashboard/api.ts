const API_BASE = "";

function getToken(): string | null {
  return localStorage.getItem("kgrag_dashboard_token");
}

function setToken(token: string) {
  localStorage.setItem("kgrag_dashboard_token", token);
}

function clearToken() {
  localStorage.removeItem("kgrag_dashboard_token");
}

async function api(path: string, options?: RequestInit): Promise<any> {
  const token = getToken();
  const resp = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options?.headers,
    },
  });
  if (resp.status === 401) {
    clearToken();
    window.location.href = "/login";
    throw new Error("Unauthorized");
  }
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${resp.status}`);
  }
  return resp.json();
}

export async function login(password: string): Promise<string> {
  const data = await api("/auth/login", {
    method: "POST",
    body: JSON.stringify({ password }),
  });
  setToken(data.token);
  return data.token;
}

export async function verifyAuth(): Promise<boolean> {
  try {
    await api("/auth/verify");
    return true;
  } catch {
    return false;
  }
}

export function logout() {
  clearToken();
  window.location.href = "/login";
}

export function isAuthenticated(): boolean {
  return !!getToken();
}

export async function fetchStats() {
  return api("/dashboard/stats");
}

export async function fetchEntities(params: {
  page?: number;
  page_size?: number;
  search?: string;
  type?: string;
}) {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== "") qs.set(k, String(v));
  });
  return api(`/dashboard/entities?${qs}`);
}

export async function fetchRelations(params: {
  page?: number;
  page_size?: number;
  entity?: string;
}) {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== "") qs.set(k, String(v));
  });
  return api(`/dashboard/relations?${qs}`);
}

export async function fetchChunks(params: {
  page?: number;
  page_size?: number;
  doc_id?: string;
  evidence_level?: string;
  search?: string;
}) {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== "") qs.set(k, String(v));
  });
  return api(`/dashboard/chunks?${qs}`);
}

export async function fetchGraphData(limitEntities = 50, limitRelations = 200) {
  return api(`/dashboard/graph-data?limit_entities=${limitEntities}&limit_relations=${limitRelations}`);
}

// Phase 2: Settings

export async function fetchSettings() {
  return api("/dashboard/settings");
}

export async function updateSettings(data: { active_model: Record<string, any> }) {
  return api("/dashboard/settings", {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export async function fetchEvalModels() {
  return api("/dashboard/eval-models");
}

export async function addEvalModel(data: Record<string, any>) {
  return api("/dashboard/eval-models", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updateEvalModel(index: number, data: Record<string, any>) {
  return api(`/dashboard/eval-models/${index}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function deleteEvalModel(index: number) {
  return api(`/dashboard/eval-models/${index}`, { method: "DELETE" });
}

// Phase 2: Eval Questions

export async function fetchEvalQuestions() {
  return api("/dashboard/eval-questions");
}

export async function addEvalQuestion(data: Record<string, any>) {
  return api("/dashboard/eval-questions", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updateEvalQuestion(id: string, data: Record<string, any>) {
  return api(`/dashboard/eval-questions/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function deleteEvalQuestion(id: string) {
  return api(`/dashboard/eval-questions/${encodeURIComponent(id)}`, { method: "DELETE" });
}

// Phase 2: Eval Runs

export async function triggerEvalRun() {
  return api("/dashboard/eval/run", { method: "POST" });
}

export async function fetchEvalRuns() {
  return api("/dashboard/eval/runs");
}

export async function fetchEvalRunDetail(runId: string) {
  return api(`/dashboard/eval/runs/${encodeURIComponent(runId)}`);
}

export async function startLatencyBenchmark(data: Record<string, any>) {
  return api("/dashboard/benchmarks", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function fetchLatencyBenchmarks() {
  return api("/dashboard/benchmarks");
}

export async function fetchLatencyBenchmark(jobId: string) {
  return api(`/dashboard/benchmarks/${encodeURIComponent(jobId)}`);
}

// Phase 2.5: Student Returns

export async function uploadReturn(file: File): Promise<any> {
  const token = getToken();
  const form = new FormData();
  form.append("file", file);
  const resp = await fetch("/dashboard/returns/upload", {
    method: "POST",
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: form,
  });
  if (resp.status === 401) {
    clearToken();
    window.location.href = "/login";
    throw new Error("Unauthorized");
  }
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${resp.status}`);
  }
  return resp.json();
}

export async function listReturns() {
  return api("/dashboard/returns");
}

export async function deleteReturn(filename: string) {
  return api(`/dashboard/returns/${encodeURIComponent(filename)}`, { method: "DELETE" });
}

// Phase 2.5: Alias Management

export async function fetchAliases() {
  return api("/dashboard/aliases");
}

export async function updateAliases(data: any) {
  return api("/dashboard/aliases", {
    method: "PUT",
    body: JSON.stringify(data),
  });
}
