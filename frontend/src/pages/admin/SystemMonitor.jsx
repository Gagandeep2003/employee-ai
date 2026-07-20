import React, { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { H1, Card, Pill, fmtDT } from "./_ui";

export default function SystemMonitor() {
  const [s, setS] = useState(null);
  useEffect(() => {
    const load = () => api.get("/admin/system").then(({ data }) => setS(data));
    load(); const int = setInterval(load, 5000); return () => clearInterval(int);
  }, []);
  if (!s) return <div className="p-8">Loading…</div>;
  return (
    <div className="p-6 md:p-8 space-y-4">
      <H1 eyebrow="Infrastructure" title="System Monitoring" />
      <div className="grid md:grid-cols-4 gap-3">
        {[["CPU", `${s.system.cpu_pct}%`], ["Memory", `${s.system.mem_pct}%`],
          ["Mem used", `${s.system.mem_used_gb} / ${s.system.mem_total_gb} GB`],
          ["Disk", `${s.system.disk_pct}%`]].map(([k,v]) => (
          <div key={k} className="bg-card border border-border rounded-lg p-4">
            <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">{k}</div>
            <div className="font-display text-2xl mt-1">{v}</div>
          </div>
        ))}
      </div>
      <Card title="Services">
        <div className="p-4 grid md:grid-cols-4 gap-3">
          {Object.entries(s.services).map(([k,v]) => (
            <div key={k} className="flex items-center justify-between bg-secondary rounded-md p-3">
              <div className="text-sm uppercase tracking-[0.15em]">{k}</div>
              <Pill tone={v === "healthy" || v === "reachable" ? "ok" : "danger"}>{v}</Pill>
            </div>
          ))}
        </div>
      </Card>
      <Card title="Environment">
        <div className="p-4 grid md:grid-cols-3 gap-3 text-xs font-mono">
          <div>Version: {s.version}</div>
          <div>Platform: {s.system.platform}</div>
          <div>Python: {s.system.python}</div>
        </div>
      </Card>
      <div className="text-xs text-muted-foreground">Last check: {fmtDT(s.checked_at)} · refreshes every 5s</div>
    </div>
  );
}
