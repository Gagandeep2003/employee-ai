import React, { useEffect, useState } from "react";
import { useBiz } from "../components/AppShell";
import { api } from "../lib/api";
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Tooltip, CartesianGrid } from "recharts";

export default function Analytics() {
  const { current } = useBiz();
  const [s, setS] = useState(null);
  useEffect(() => { if (current) api.get(`/analytics/business/${current.business_id}/summary`).then(({ data }) => setS(data)); }, [current]);
  if (!current || !s) return <div className="p-8">Loading…</div>;
  return (
    <div className="p-8 space-y-6">
      <div>
        <div className="text-[10px] uppercase tracking-[0.3em] text-muted-foreground">Analytics</div>
        <h1 className="font-display text-4xl tracking-tight">The signal in your chats.</h1>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          ["Conversations", s.total_conversations],
          ["Messages", s.total_messages],
          ["AI accuracy", `${s.accuracy_pct}%`],
          ["Escalated", s.escalated],
        ].map(([k,v]) => (
          <div key={k} className="bg-card border border-border rounded-lg p-5">
            <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">{k}</div>
            <div className="font-display text-3xl mt-2 tracking-tight">{v}</div>
          </div>
        ))}
      </div>
      <div className="grid md:grid-cols-2 gap-4">
        <div className="bg-card border border-border rounded-lg p-6">
          <div className="text-xs uppercase tracking-[0.2em] text-muted-foreground mb-3">Last 7 days</div>
          <div className="h-64">
            <ResponsiveContainer>
              <LineChart data={s.days}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                <XAxis dataKey="day" stroke="hsl(var(--muted-foreground))" fontSize={11} />
                <YAxis stroke="hsl(var(--muted-foreground))" fontSize={11} allowDecimals={false} />
                <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))" }} />
                <Line type="monotone" dataKey="conversations" stroke="hsl(var(--accent))" strokeWidth={2} dot={{ fill: "hsl(var(--accent))" }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="bg-card border border-border rounded-lg p-6">
          <div className="text-xs uppercase tracking-[0.2em] text-muted-foreground mb-3">Top topics</div>
          <div className="h-64">
            <ResponsiveContainer>
              <BarChart data={s.top_topics.slice(0, 8)}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                <XAxis dataKey="word" stroke="hsl(var(--muted-foreground))" fontSize={11} />
                <YAxis stroke="hsl(var(--muted-foreground))" fontSize={11} allowDecimals={false} />
                <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))" }} />
                <Bar dataKey="count" fill="hsl(var(--accent))" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  );
}
