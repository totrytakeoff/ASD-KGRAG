import { useEffect, useState } from "react";
import { Gauge, Loader2, Play, RefreshCw } from "lucide-react";
import {
  fetchLatencyBenchmark,
  fetchLatencyBenchmarks,
  startLatencyBenchmark,
} from "./api";

const DEFAULT_MODELS = [
  "Qwen/Qwen3.5-27B",
  "Qwen/Qwen3.5-9B",
  "deepseek-ai/DeepSeek-V4-Flash",
  "zai-org/GLM-4.5-Air",
];

export default function DashboardPerformance() {
  const [jobs, setJobs] = useState<any[]>([]);
  const [selected, setSelected] = useState<any>(null);
  const [running, setRunning] = useState(false);

  const load = async () => {
    const data = await fetchLatencyBenchmarks();
    setJobs(data);
    if (data[0]?.job_id) setSelected(await fetchLatencyBenchmark(data[0].job_id));
  };

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    if (!jobs.some((job) => job.status === "queued" || job.status === "running")) return;
    const timer = window.setInterval(load, 5000);
    return () => window.clearInterval(timer);
  }, [jobs]);

  const start = async (pipelines: Array<"standard" | "agent">, modelNames = DEFAULT_MODELS) => {
    setRunning(true);
    try {
      await startLatencyBenchmark({
        model_names: modelNames,
        profiles: ["balanced"],
        pipelines,
        question_limit: 5,
        repeats: 1,
      });
      await load();
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">模型性能</h1>
          <p className="mt-1 text-sm text-gray-500">SiliconFlow 模型的首字延迟、总耗时与质量门槛</p>
        </div>
        <div className="flex gap-2">
          <button onClick={load} title="刷新" className="flex h-9 w-9 items-center justify-center rounded-lg border border-gray-200 bg-white text-gray-500 hover:bg-gray-50">
            <RefreshCw size={15} />
          </button>
          <button onClick={() => start(["standard"])} disabled={running} className="flex items-center gap-2 rounded-lg bg-medical-600 px-4 py-2 text-sm font-medium text-white hover:bg-medical-700 disabled:opacity-50">
            {running ? <Loader2 size={15} className="animate-spin" /> : <Play size={15} />}
            运行模型基准
          </button>
          <button
            onClick={() => start(["standard", "agent"], [DEFAULT_MODELS[0]])}
            disabled={running}
            className="flex items-center gap-2 rounded-lg border border-medical-200 bg-white px-4 py-2 text-sm font-medium text-medical-700 hover:bg-medical-50 disabled:opacity-50"
          >
            <Gauge size={15} />
            Agent 门槛
          </button>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[260px_1fr]">
        <div className="space-y-2">
          {jobs.length === 0 && <div className="py-10 text-center text-sm text-gray-400">暂无基准记录</div>}
          {jobs.map((job) => (
            <button key={job.job_id} onClick={async () => setSelected(await fetchLatencyBenchmark(job.job_id))}
              className={`w-full rounded-lg border p-3 text-left ${selected?.job_id === job.job_id ? "border-medical-300 bg-medical-50" : "border-gray-200 bg-white hover:bg-gray-50"}`}>
              <div className="flex items-center justify-between text-sm font-medium text-gray-800">
                <span>{job.job_id}</span>
                {(job.status === "queued" || job.status === "running") && <Loader2 size={13} className="animate-spin text-medical-600" />}
              </div>
              <div className="mt-1 text-xs text-gray-400">{job.completed_runs || 0}/{job.total_runs || 0} · {job.status}</div>
            </button>
          ))}
        </div>

        <div className="min-w-0">
          {!selected ? (
            <div className="flex h-56 items-center justify-center text-sm text-gray-400"><Gauge size={18} className="mr-2" />选择一次基准记录</div>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-gray-200 bg-gray-50 text-xs text-gray-500">
                  <tr><th className="px-4 py-3">模型</th><th className="px-3 py-3">模式</th><th className="px-3 py-3">链路</th><th className="px-3 py-3">TTFT p50/p95</th><th className="px-3 py-3">总耗时 p50/p95</th><th className="px-3 py-3">成功</th><th className="px-3 py-3">质量</th></tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {(selected.summary || []).map((row: any) => (
                    <tr key={`${row.model}-${row.profile}-${row.pipeline}`}>
                      <td className="max-w-56 truncate px-4 py-3 font-medium text-gray-800" title={row.model}>{row.model}</td>
                      <td className="px-3 py-3 text-gray-600">{row.profile}</td>
                      <td className="px-3 py-3 text-gray-600">{row.pipeline === "agent" ? "Agent" : "标准"}</td>
                      <td className="px-3 py-3 text-gray-600">{row.ttft_p50 ?? "-"} / {row.ttft_p95 ?? "-"}s</td>
                      <td className="px-3 py-3 text-gray-600">{row.total_p50 ?? "-"} / {row.total_p95 ?? "-"}s</td>
                      <td className="px-3 py-3 text-gray-600">{row.successes}/{row.runs}</td>
                      <td className="px-3 py-3 text-gray-600">{row.quality_passes}/{row.runs}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {(selected.agent_gate || []).length > 0 && (
                <div className="border-t border-gray-200 px-4 py-3 text-sm text-gray-600">
                  {(selected.agent_gate || []).map((gate: any) => (
                    <div key={`${gate.model}-${gate.profile}`} className="flex flex-wrap items-center gap-2">
                      <span className={gate.passed ? "font-medium text-emerald-700" : "font-medium text-amber-700"}>
                        Agent 门槛：{gate.passed ? "通过" : "未通过"}
                      </span>
                      <span>{gate.model}</span>
                      <span>延迟开销 {gate.latency_overhead_rate == null ? "-" : `${(gate.latency_overhead_rate * 100).toFixed(1)}%`}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
