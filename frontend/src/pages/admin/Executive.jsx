import React, { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { LineChart, Line, XAxis, YAxis, ResponsiveContainer, Tooltip, CartesianGrid, Area, AreaChart, Bar, BarChart } from "recharts";
import { H1, KPI, Card, fmtINR, Pill, Btn } from "./_ui";
import { DownloadSimple } from "@phosphor-icons/react";

export default function Executive() {
  const [o, setO] = useState(null);
  const [ts, setTs] = useState([]);
  const [growth, setGrowth] = useState([]);
  const [churn, setChurn] = useState([]);
  useEffect(() => {
    api.get("/admin/overview").then(({ data }) => setO(data));
    api.get("/admin/revenue-timeseries?days=30").then(({ data }) => setTs(data));
    api.get("/admin/growth?months=6").then(({ data }) => setGrowth(data));
    api.get("/admin/churn?months=6").then(({ data }) => setChurn(data));
  }, []);
  if (!o) return <div className="p-8">Loading…</div>;

  const exportReport = (report, format) => {
    window.open(`${api.defaults.baseURL}/admin/${report}?format=${format}`, "_blank");
  };

  return (
    <div className="p-6 md:p-8 space-y-6">
      <H1 eyebrow="Platform Command" title="Executive Dashboard" />

      {/* Revenue KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
        <KPI label="MRR" value={fmtINR(o.revenue.mrr_inr)} sub="Monthly recurring" accent testid="kpi-mrr" />
        <KPI label="ARR" value={fmtINR(o.revenue.arr_inr)} sub="Annual recurring" testid="kpi-arr" />
        <KPI label="Today" value={fmtINR(o.revenue.today_inr)} sub="Revenue today" testid="kpi-today" />
        <KPI label="All-time" value={fmtINR(o.revenue.total_inr)} sub={`${o.revenue.invoices_paid} invoices`} />
        <KPI label="Businesses" value={o.businesses.total} sub={`${o.businesses.paid} paid · ${o.businesses.free} free`} />
        <KPI label="Users" value={o.users.total} sub={`${o.users.owners} owners`} />
      </div>

      {/* AI KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
        <KPI label="Conversations" value={o.ai.conversations_all} sub={`${o.ai.conversations_today} today`} />
        <KPI label="Messages" value={o.ai.messages_all} sub={`${o.ai.messages_today} today`} />
        <KPI label="AI cost today" value={`$${o.ai.estimated_cost_today_usd}`} sub="Gemini estimated" />
        <KPI label="KB chunks" value={o.knowledge.chunks} sub={`${o.knowledge.files} files`} />
        <KPI label="Active crawls" value={o.knowledge.active_crawls} sub="Background jobs" />
        <KPI label="Open tickets" value={o.support.open_tickets} sub="Handoff requests" />
      </div>

      {/* Charts */}
      <div className="grid md:grid-cols-2 gap-4">
        <Card title="Revenue · last 30 days">
          <div className="p-4 h-64">
            <ResponsiveContainer>
              <AreaChart data={ts}>
                <defs>
                  <linearGradient id="revg" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="hsl(var(--accent))" stopOpacity={0.6}/>
                    <stop offset="95%" stopColor="hsl(var(--accent))" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                <XAxis dataKey="date" stroke="hsl(var(--muted-foreground))" fontSize={10} tickFormatter={(d) => d?.slice(5)} />
                <YAxis stroke="hsl(var(--muted-foreground))" fontSize={10} />
                <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))" }} />
                <Area type="monotone" dataKey="revenue_inr" stroke="hsl(var(--accent))" fill="url(#revg)" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card title="Conversations · last 30 days">
          <div className="p-4 h-64">
            <ResponsiveContainer>
              <LineChart data={ts}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                <XAxis dataKey="date" stroke="hsl(var(--muted-foreground))" fontSize={10} tickFormatter={(d) => d?.slice(5)} />
                <YAxis stroke="hsl(var(--muted-foreground))" fontSize={10} />
                <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))" }} />
                <Line type="monotone" dataKey="conversations" stroke="hsl(var(--chart-1))" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      {/* Growth & Churn */}
      <div className="grid md:grid-cols-2 gap-4">
        <Card title="New signups & paying businesses · last 6 months" actions={
          <div className="flex gap-1">
            <Btn variant="ghost" onClick={() => exportReport("growth", "csv")} testid="export-growth-csv"><DownloadSimple size={12} className="inline mr-1" />CSV</Btn>
            <Btn variant="ghost" onClick={() => exportReport("growth", "xlsx")} testid="export-growth-xlsx"><DownloadSimple size={12} className="inline mr-1" />Excel</Btn>
          </div>
        }>
          <div className="p-4 h-56">
            <ResponsiveContainer>
              <BarChart data={growth}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                <XAxis dataKey="month" stroke="hsl(var(--muted-foreground))" fontSize={10} />
                <YAxis stroke="hsl(var(--muted-foreground))" fontSize={10} />
                <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))" }} />
                <Bar dataKey="new_signups" fill="hsl(var(--accent))" radius={[4, 4, 0, 0]} />
                <Bar dataKey="new_paying_businesses" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card title="Churn rate · last 6 months" actions={
          <div className="flex gap-1">
            <Btn variant="ghost" onClick={() => exportReport("churn", "csv")} testid="export-churn-csv"><DownloadSimple size={12} className="inline mr-1" />CSV</Btn>
            <Btn variant="ghost" onClick={() => exportReport("churn", "xlsx")} testid="export-churn-xlsx"><DownloadSimple size={12} className="inline mr-1" />Excel</Btn>
          </div>
        }>
          <div className="p-4 h-56">
            <ResponsiveContainer>
              <LineChart data={churn}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                <XAxis dataKey="month" stroke="hsl(var(--muted-foreground))" fontSize={10} />
                <YAxis stroke="hsl(var(--muted-foreground))" fontSize={10} unit="%" />
                <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))" }} />
                <Line type="monotone" dataKey="churn_rate_pct" stroke="hsl(var(--destructive))" strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <p className="px-4 pb-4 text-[11px] text-muted-foreground">
            {churn.some((r) => r.denominator_source === "approximation")
              ? "Some months above use an estimate (no paying-business snapshot exists yet for that month, so it's compared against total signups instead); months from when snapshotting started use an exact paying-business count taken on the 1st."
              : "Computed from an exact paying-business count taken on the 1st of each month."}
          </p>
        </Card>
      </div>

      {/* System health */}
      <Card title="System Health">
        <div className="p-4 grid grid-cols-2 md:grid-cols-4 gap-3">
          {Object.entries({ MongoDB: o.system.db, Backend: o.system.backend, Version: o.system.version, Suspended: o.businesses.suspended }).map(([k,v]) => (
            <div key={k} className="flex items-center justify-between bg-secondary rounded-md px-3 py-2">
              <div className="text-xs text-muted-foreground uppercase tracking-[0.15em]">{k}</div>
              {typeof v === "string" && v === "healthy" ? <Pill tone="ok">OK</Pill> : <span className="text-sm font-mono">{v}</span>}
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
