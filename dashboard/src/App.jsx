import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Activity,
  Cpu,
  Database,
  Download,
  FlaskConical,
  Gauge,
  GitFork,
  LayoutDashboard,
  Lock,
  Network,
  RadioTower,
  RefreshCw,
  ShieldCheck,
  Terminal,
} from "lucide-react";
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const anomalyThreshold = 0.74;

const navItems = [
  { label: "Dashboard", icon: LayoutDashboard },
  { label: "Terminal Chat Mode", icon: Terminal },
  { label: "Research Agent", icon: FlaskConical },
  { label: "Mock Chain Analysis", icon: Network },
  { label: "Ethereum Telemetry", icon: RadioTower },
];

const artifacts = [
  {
    name: "latest_eth_run.json",
    path: "outputs/latest_eth_run.json",
    type: "Run index",
    size: "12.8 KB",
    updated: "Live",
  },
  {
    name: "eth_metrics_latest.csv",
    path: "data/eth_metrics_latest.csv",
    type: "Metrics CSV",
    size: "88.4 KB",
    updated: "2 min ago",
  },
  {
    name: "eth_detection_20260511.json",
    path: "outputs/eth_detection_20260511.json",
    type: "Detector output",
    size: "9.1 KB",
    updated: "5 min ago",
  },
  {
    name: "eth_report_20260511.md",
    path: "outputs/eth_report_20260511.md",
    type: "LLM report",
    size: "18.6 KB",
    updated: "7 min ago",
  },
];

const initialSeries = [
  { time: "13:00", block_time_sec_avg: 12.1, anomalyScore: 0.22 },
  { time: "13:05", block_time_sec_avg: 12.3, anomalyScore: 0.2 },
  { time: "13:10", block_time_sec_avg: 12.2, anomalyScore: 0.18 },
  { time: "13:15", block_time_sec_avg: 13.1, anomalyScore: 0.42 },
  { time: "13:20", block_time_sec_avg: 12.4, anomalyScore: 0.28 },
  { time: "13:25", block_time_sec_avg: 14.8, anomalyScore: 0.81 },
  { time: "13:30", block_time_sec_avg: 12.0, anomalyScore: 0.21 },
  { time: "13:35", block_time_sec_avg: 11.9, anomalyScore: 0.24 },
  { time: "13:40", block_time_sec_avg: 15.2, anomalyScore: 0.86 },
  { time: "13:45", block_time_sec_avg: 12.5, anomalyScore: 0.31 },
  { time: "13:50", block_time_sec_avg: 12.2, anomalyScore: 0.2 },
  { time: "13:55", block_time_sec_avg: 12.6, anomalyScore: 0.34 },
];

const commandResponses = {
  "analyze eth chain dryrun 100": [
    "Fetching recent canonical Ethereum block window: n=100",
    "Building detector-compatible telemetry report...",
    "Isolation Forest score: 0.81, threshold: 0.74",
    "LLM interpretation: elevated timing variance with proposer concentration proxy drift. Treat fork and orphan metrics as unavailable placeholders under canonical RPC-only visibility.",
    "Artifacts saved: outputs/latest_eth_run.json, outputs/eth_report_20260511.md",
  ],
  "collect eth metrics 500 data/eth_metrics_latest.csv": [
    "Streaming 500 recent Ethereum blocks from ETH_RPC_URL...",
    "Rolling windows built: 9, window_size=100, step_size=50",
    "CSV path: data/eth_metrics_latest.csv",
  ],
  "analyze eth detector": [
    "Loading training samples from data/eth_metrics_latest.csv",
    "Fitting Isolation Forest contamination=0.30",
    "Current window: anomalous, anomaly_score=0.77",
    "Recommendation: collect beacon-chain proposer telemetry before escalating this signal.",
  ],
};

function nextPoint(series) {
  const last = series[series.length - 1];
  const lastHour = Number(last.time.slice(0, 2));
  const lastMinute = Number(last.time.slice(3, 5));
  const totalMinutes = lastHour * 60 + lastMinute + 5;
  const hour = String(Math.floor(totalMinutes / 60) % 24).padStart(2, "0");
  const minute = String(totalMinutes % 60).padStart(2, "0");
  const anomalySpike = Math.random() > 0.78;
  const base = 12 + Math.random() * 0.8;

  return {
    time: `${hour}:${minute}`,
    block_time_sec_avg: Number((anomalySpike ? base + 2.4 + Math.random() * 0.9 : base).toFixed(2)),
    anomalyScore: Number((anomalySpike ? 0.76 + Math.random() * 0.16 : 0.16 + Math.random() * 0.28).toFixed(2)),
  };
}

function formatMetric(value, suffix = "") {
  return `${value.toFixed(2)}${suffix}`;
}

function App() {
  const [activeTab, setActiveTab] = useState("Dashboard");
  const [dryRun, setDryRun] = useState(true);
  const [series, setSeries] = useState(initialSeries);
  const [pulseKey, setPulseKey] = useState(0);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setSeries((current) => [...current.slice(1), nextPoint(current)]);
      setPulseKey((current) => current + 1);
    }, 3600);

    return () => window.clearInterval(timer);
  }, []);

  const currentMetrics = useMemo(() => {
    const latest = series[series.length - 1];
    const recent = series.slice(-6);
    const forkPressure = recent.filter((point) => point.anomalyScore > 0.68).length;

    return [
      {
        label: "Average Block Time",
        value: formatMetric(latest.block_time_sec_avg, "s"),
        delta: latest.block_time_sec_avg > 13.2 ? "+8.7%" : "+1.2%",
        state: latest.block_time_sec_avg > 13.2 ? "Watch" : "Nominal",
        icon: Gauge,
        accent: "cyan",
      },
      {
        label: "Fork Rate",
        value: `${(forkPressure * 0.08).toFixed(2)}%`,
        delta: forkPressure ? "+0.14%" : "0.00%",
        state: forkPressure ? "Elevated" : "Stable",
        icon: GitFork,
        accent: forkPressure ? "red" : "green",
      },
      {
        label: "Hashrate Concentration (Top 3)",
        value: `${(42 + latest.anomalyScore * 17).toFixed(1)}%`,
        delta: latest.anomalyScore > anomalyThreshold ? "+6.1%" : "+0.9%",
        state: latest.anomalyScore > anomalyThreshold ? "Anomaly" : "Proxy",
        icon: Cpu,
        accent: latest.anomalyScore > anomalyThreshold ? "red" : "cyan",
      },
      {
        label: "Miner Entropy",
        value: (3.9 - latest.anomalyScore * 0.6).toFixed(2),
        delta: latest.anomalyScore > anomalyThreshold ? "-0.31" : "-0.04",
        state: latest.anomalyScore > anomalyThreshold ? "Compressed" : "Healthy",
        icon: Activity,
        accent: latest.anomalyScore > anomalyThreshold ? "red" : "green",
      },
    ];
  }, [series]);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <div className="flex min-h-screen">
        <aside className="hidden w-72 shrink-0 border-r border-slate-800/80 bg-slate-950/92 px-4 py-5 lg:block">
          <div className="mb-8 flex items-center gap-3 px-2">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-cyan-400/40 bg-cyan-400/10 text-cyan-300 shadow-glow">
              <ShieldCheck className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-lg font-semibold tracking-wide text-white">ChainGuardian</h1>
              <p className="text-xs uppercase tracking-[0.28em] text-emerald-300">Consensus SecOps</p>
            </div>
          </div>

          <nav className="space-y-1">
            {navItems.map((item) => {
              const Icon = item.icon;
              const selected = activeTab === item.label;

              return (
                <button
                  key={item.label}
                  type="button"
                  onClick={() => setActiveTab(item.label)}
                  className={`flex w-full items-center gap-3 rounded-lg px-3 py-3 text-left text-sm transition ${
                    selected
                      ? "border border-cyan-400/40 bg-cyan-400/10 text-cyan-100 shadow-glow"
                      : "border border-transparent text-slate-400 hover:border-slate-700 hover:bg-slate-900 hover:text-slate-100"
                  }`}
                >
                  <Icon className="h-4 w-4" />
                  <span>{item.label}</span>
                </button>
              );
            })}
          </nav>

          <div className="mt-8 rounded-lg border border-slate-800 bg-slate-900/70 p-4">
            <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-[0.24em] text-slate-500">
              <Lock className="h-4 w-4 text-emerald-300" />
              Live Window
            </div>
            <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
              <StatusPill label="RPC" value="Connected" />
              <StatusPill label="IForest" value="Armed" />
            </div>
          </div>
        </aside>

        <main className="flex min-w-0 flex-1 flex-col">
          <Header dryRun={dryRun} setDryRun={setDryRun} activeTab={activeTab} />
          <MobileNav activeTab={activeTab} setActiveTab={setActiveTab} />
          {activeTab === "Dashboard" ? (
            <DashboardView
              metrics={currentMetrics}
              pulseKey={pulseKey}
              series={series}
            />
          ) : (
            <ModeView activeTab={activeTab} />
          )}
        </main>
      </div>
    </div>
  );
}

function Header({ dryRun, setDryRun, activeTab }) {
  return (
    <header className="flex flex-col gap-4 border-b border-slate-800 bg-slate-950/88 px-4 py-4 backdrop-blur md:flex-row md:items-center md:justify-between md:px-6">
      <div>
        <div className="text-xs uppercase tracking-[0.28em] text-cyan-300">{activeTab}</div>
        <h2 className="mt-1 text-2xl font-semibold text-white md:text-3xl">ChainGuardian</h2>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2 rounded-lg border border-emerald-400/30 bg-emerald-400/10 px-3 py-2 text-sm text-emerald-200">
          <span className="h-2.5 w-2.5 rounded-full bg-emerald-300 shadow-[0_0_16px_rgba(110,231,183,0.8)]" />
          ETH_RPC_URL Connected
        </div>

        <button
          type="button"
          onClick={() => setDryRun(!dryRun)}
          className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-sm transition ${
            dryRun
              ? "border-cyan-400/50 bg-cyan-400/10 text-cyan-100"
              : "border-slate-700 bg-slate-900 text-slate-300"
          }`}
          aria-pressed={dryRun}
        >
          <span
            className={`relative h-5 w-9 rounded-full transition ${
              dryRun ? "bg-cyan-400/80" : "bg-slate-700"
            }`}
          >
            <span
              className={`absolute top-1 h-3 w-3 rounded-full bg-white transition ${
                dryRun ? "left-5" : "left-1"
              }`}
            />
          </span>
          Dry-run Mode
        </button>
      </div>
    </header>
  );
}

function MobileNav({ activeTab, setActiveTab }) {
  return (
    <div className="border-b border-slate-800 bg-slate-950 px-4 py-3 lg:hidden">
      <div className="flex gap-2 overflow-x-auto pb-1">
        {navItems.map((item) => {
          const Icon = item.icon;
          const selected = activeTab === item.label;

          return (
            <button
              key={item.label}
              type="button"
              onClick={() => setActiveTab(item.label)}
              className={`flex shrink-0 items-center gap-2 rounded-lg border px-3 py-2 text-sm ${
                selected
                  ? "border-cyan-400/40 bg-cyan-400/10 text-cyan-100"
                  : "border-slate-800 bg-slate-900 text-slate-400"
              }`}
            >
              <Icon className="h-4 w-4" />
              {item.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function DashboardView({ metrics, pulseKey, series }) {
  return (
    <div className="flex flex-1 flex-col gap-5 overflow-hidden p-4 md:p-6">
      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {metrics.map((metric) => (
          <MetricCard key={`${metric.label}-${pulseKey}`} metric={metric} />
        ))}
      </section>

      <section className="grid min-h-0 flex-1 gap-5 xl:grid-cols-[minmax(0,1.5fr)_minmax(380px,0.9fr)]">
        <AnomalyChart series={series} />
        <ArtifactsTable />
      </section>

      <section className="min-h-[280px] basis-1/3">
        <TerminalWindow compact />
      </section>
    </div>
  );
}

function MetricCard({ metric }) {
  const Icon = metric.icon;
  const accentClasses = {
    cyan: "border-cyan-400/30 text-cyan-200 bg-cyan-400/10",
    green: "border-emerald-400/30 text-emerald-200 bg-emerald-400/10",
    red: "border-red-400/40 text-red-200 bg-red-400/10 shadow-alert",
  };

  return (
    <article className="metric-update rounded-lg border border-slate-800 bg-slate-900/80 p-4 transition">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-slate-500">{metric.label}</p>
          <div className="mt-3 flex items-end gap-2">
            <span className="text-3xl font-semibold text-white">{metric.value}</span>
            <span className="pb-1 text-sm text-slate-400">{metric.delta}</span>
          </div>
        </div>
        <div className={`rounded-lg border p-2 ${accentClasses[metric.accent]}`}>
          <Icon className="h-5 w-5" />
        </div>
      </div>
      <div className="mt-4 flex items-center justify-between border-t border-slate-800 pt-3">
        <span className="text-sm text-slate-400">Detector state</span>
        <span className={`text-sm font-medium ${metric.accent === "red" ? "text-red-300" : "text-emerald-300"}`}>
          {metric.state}
        </span>
      </div>
    </article>
  );
}

function AnomalyChart({ series }) {
  const anomalyPoints = series
    .filter((point) => point.anomalyScore > anomalyThreshold)
    .map((point) => ({ ...point, anomaly: point.block_time_sec_avg }));

  return (
    <section className="rounded-lg border border-slate-800 bg-slate-900/80 p-4">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold text-white">Anomaly Detection</h3>
          <p className="mt-1 text-sm text-slate-400">block_time_sec_avg with Isolation Forest anomaly markers</p>
        </div>
        <div className="flex items-center gap-2 rounded-lg border border-red-400/30 bg-red-400/10 px-3 py-2 text-sm text-red-200">
          <span className="h-2.5 w-2.5 rounded-full bg-red-400 shadow-[0_0_14px_rgba(248,113,113,0.8)]" />
          threshold &gt; {anomalyThreshold}
        </div>
      </div>

      <div className="h-[360px] min-h-[280px]">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={series} margin={{ top: 14, right: 18, bottom: 8, left: 0 }}>
            <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
            <XAxis
              dataKey="time"
              stroke="#64748b"
              tick={{ fill: "#94a3b8", fontSize: 12 }}
              tickLine={false}
              axisLine={{ stroke: "#334155" }}
            />
            <YAxis
              stroke="#64748b"
              tick={{ fill: "#94a3b8", fontSize: 12 }}
              tickLine={false}
              axisLine={{ stroke: "#334155" }}
              domain={[10.5, 16.5]}
              unit="s"
            />
            <Tooltip
              cursor={{ stroke: "#22d3ee", strokeDasharray: "4 4" }}
              contentStyle={{
                background: "#020617",
                border: "1px solid #334155",
                borderRadius: 8,
                color: "#e2e8f0",
              }}
              labelStyle={{ color: "#67e8f9" }}
            />
            <Line
              type="monotone"
              dataKey="block_time_sec_avg"
              stroke="#22d3ee"
              strokeWidth={3}
              dot={{ r: 3, fill: "#020617", stroke: "#22d3ee", strokeWidth: 2 }}
              activeDot={{ r: 6, fill: "#22d3ee", stroke: "#cffafe" }}
            />
            <Scatter
              name="Isolation Forest anomaly"
              data={anomalyPoints}
              dataKey="anomaly"
              fill="#f87171"
              shape={<AnomalyDot />}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}

function AnomalyDot(props) {
  const { cx, cy } = props;

  return (
    <g>
      <circle cx={cx} cy={cy} r="8" fill="rgba(248,113,113,0.22)" />
      <circle cx={cx} cy={cy} r="4.5" fill="#f87171" stroke="#fecaca" strokeWidth="1.5" />
    </g>
  );
}

function ArtifactsTable() {
  return (
    <section className="rounded-lg border border-slate-800 bg-slate-900/80 p-4">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold text-white">Recent Artifacts</h3>
          <p className="mt-1 text-sm text-slate-400">Generated outputs from Ethereum telemetry runs</p>
        </div>
        <Database className="h-5 w-5 text-cyan-300" />
      </div>

      <div className="overflow-hidden rounded-lg border border-slate-800">
        <table className="w-full min-w-[540px] border-collapse text-left text-sm">
          <thead className="bg-slate-950/70 text-xs uppercase tracking-[0.18em] text-slate-500">
            <tr>
              <th className="px-4 py-3 font-medium">Artifact</th>
              <th className="px-4 py-3 font-medium">Type</th>
              <th className="px-4 py-3 font-medium">Size</th>
              <th className="px-4 py-3 font-medium">Updated</th>
              <th className="px-4 py-3 text-right font-medium">Download</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {artifacts.map((artifact) => (
              <tr key={artifact.path} className="bg-slate-900/55 transition hover:bg-slate-800/70">
                <td className="px-4 py-3">
                  <div className="font-medium text-slate-100">{artifact.name}</div>
                  <div className="mt-1 font-mono text-xs text-slate-500">{artifact.path}</div>
                </td>
                <td className="px-4 py-3 text-slate-300">{artifact.type}</td>
                <td className="px-4 py-3 text-slate-400">{artifact.size}</td>
                <td className="px-4 py-3 text-slate-400">{artifact.updated}</td>
                <td className="px-4 py-3 text-right">
                  <button
                    type="button"
                    className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-cyan-400/30 bg-cyan-400/10 text-cyan-200 transition hover:bg-cyan-400/20"
                    aria-label={`Download ${artifact.name}`}
                    title={`Download ${artifact.name}`}
                  >
                    <Download className="h-4 w-4" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function TerminalWindow({ compact = false }) {
  const [command, setCommand] = useState("");
  const [logs, setLogs] = useState([
    { kind: "system", text: "Windows PowerShell" },
    { kind: "system", text: "ChainGuardian research shell initialized." },
    { kind: "prompt", text: "PS E:\\capstone\\ChainGuardian> analyze eth chain dryrun 100" },
    { kind: "output", text: "Dry-run report complete. Current window label: normal_like. Artifacts indexed in outputs/latest_eth_run.json." },
  ]);
  const scrollRef = useRef(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs]);

  const runCommand = (event) => {
    event.preventDefault();
    const normalized = command.trim();

    if (!normalized) {
      return;
    }

    const response = commandResponses[normalized.toLowerCase()] ?? [
      `Command accepted: ${normalized}`,
      "LLM interpretation: no critical consensus-security signal detected in the current mock session.",
    ];

    setLogs((current) => [
      ...current,
      { kind: "prompt", text: `PS E:\\capstone\\ChainGuardian> ${normalized}` },
      ...response.map((text) => ({ kind: text.startsWith("Artifacts") ? "artifact" : "output", text })),
    ]);
    setCommand("");
  };

  return (
    <section className="flex h-full min-h-[260px] flex-col rounded-lg border border-slate-800 bg-[#050b16] shadow-glow">
      <div className="flex items-center justify-between gap-3 border-b border-slate-800 px-4 py-3">
        <div className="flex items-center gap-3">
          <div className="flex gap-1.5">
            <span className="h-3 w-3 rounded-full bg-red-400" />
            <span className="h-3 w-3 rounded-full bg-amber-300" />
            <span className="h-3 w-3 rounded-full bg-emerald-400" />
          </div>
          <div className="flex items-center gap-2 text-sm font-medium text-slate-300">
            <Terminal className="h-4 w-4 text-cyan-300" />
            PowerShell
          </div>
        </div>
        <div className="flex items-center gap-2 text-xs uppercase tracking-[0.2em] text-emerald-300">
          <RefreshCw className="h-3.5 w-3.5" />
          Streaming
        </div>
      </div>

      <div
        ref={scrollRef}
        className={`terminal-scrollbar flex-1 overflow-y-auto px-4 py-3 font-mono text-sm leading-6 ${
          compact ? "max-h-[320px]" : "min-h-[520px]"
        }`}
      >
        {logs.map((log, index) => (
          <div
            key={`${log.text}-${index}`}
            className={
              log.kind === "prompt"
                ? "text-cyan-200"
                : log.kind === "artifact"
                  ? "text-emerald-300"
                  : log.kind === "system"
                    ? "text-slate-500"
                    : "text-slate-300"
            }
          >
            {log.text}
          </div>
        ))}
      </div>

      <form onSubmit={runCommand} className="flex items-center gap-2 border-t border-slate-800 px-4 py-3 font-mono text-sm">
        <span className="hidden shrink-0 text-cyan-200 sm:inline">PS E:\capstone\ChainGuardian&gt;</span>
        <input
          value={command}
          onChange={(event) => setCommand(event.target.value)}
          className="min-w-0 flex-1 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 placeholder:text-slate-600"
          placeholder="analyze eth chain dryrun 100"
          aria-label="PowerShell command"
        />
      </form>
    </section>
  );
}

function ModeView({ activeTab }) {
  const modeContent = {
    "Terminal Chat Mode": <TerminalWindow />,
    "Research Agent": (
      <ModePanel icon={FlaskConical} title="Research Agent" command="analyze eth detector" />
    ),
    "Mock Chain Analysis": (
      <ModePanel icon={Network} title="Mock Chain Analysis" command="analyze mock chain" />
    ),
    "Ethereum Telemetry": (
      <ModePanel icon={RadioTower} title="Ethereum Telemetry" command="collect eth metrics 500 data/eth_metrics_latest.csv" />
    ),
  };

  return (
    <div className="flex flex-1 flex-col gap-5 p-4 md:p-6">
      {modeContent[activeTab]}
    </div>
  );
}

function ModePanel({ icon: Icon, title, command }) {
  return (
    <section className="grid flex-1 gap-5 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
      <div className="rounded-lg border border-slate-800 bg-slate-900/80 p-5">
        <div className="flex items-center gap-3">
          <div className="rounded-lg border border-cyan-400/30 bg-cyan-400/10 p-2 text-cyan-200">
            <Icon className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-white">{title}</h3>
            <p className="mt-1 font-mono text-sm text-cyan-200">{command}</p>
          </div>
        </div>

        <div className="mt-6 grid gap-3 sm:grid-cols-3">
          <StatusPill label="Detector" value="Ready" />
          <StatusPill label="Window" value="100 blk" />
          <StatusPill label="Output" value="JSON" />
        </div>
      </div>

      <TerminalWindow compact />
    </section>
  );
}

function StatusPill({ label, value }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2">
      <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500">{label}</div>
      <div className="mt-1 text-sm font-medium text-emerald-300">{value}</div>
    </div>
  );
}

export default App;
