import React, { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { LineChart, Line, XAxis, YAxis, ResponsiveContainer, Tooltip, CartesianGrid, Area, AreaChart } from "recharts";
import { H1, KPI, Card, fmtINR, Pill } from "./_ui";

export default function Executive() {
  const [o, setO] = useState(null);
  const [ts, setTs] = useState([]);
  useEffect(() => {
    api.get("/admin/overview").then(({ data }) => setO(data));
    api.get("/admin/revenue-timeseries?days=30").then(({ data }) => setTs(data));
  }, []);
  if (!o) return <div className="p-8">Loading…</div>;

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
