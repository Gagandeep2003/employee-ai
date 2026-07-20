import React, { useEffect, useState } from "react";
import { api } from "../lib/api";

export default function Admin() {
  const [ov, setOv] = useState(null);
  const [biz, setBiz] = useState([]);
  const [users, setUsers] = useState([]);
  const [tab, setTab] = useState("overview");
  const [err, setErr] = useState(null);
  useEffect(() => {
    Promise.all([
      api.get("/admin/overview"),
      api.get("/admin/businesses"),
      api.get("/admin/users"),
    ]).then(([o,b,u]) => { setOv(o.data); setBiz(b.data); setUsers(u.data); })
      .catch(() => setErr("Admin access denied. Only the first-registered user or an admin can view this."));
  }, []);
  if (err) return <div className="p-8"><h1 className="font-display text-3xl">Admin</h1><div className="mt-4 text-sm text-muted-foreground">{err}</div></div>;
  if (!ov) return <div className="p-8">Loading…</div>;
  return (
    <div className="p-8 space-y-6">
      <div>
        <div className="text-[10px] uppercase tracking-[0.3em] text-muted-foreground">Platform admin</div>
        <h1 className="font-display text-4xl tracking-tight">System overview.</h1>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-6 gap-4">
        {[["Users",ov.users],["Businesses",ov.businesses],["Conversations",ov.conversations],["Messages",ov.messages],["Invoices",ov.invoices],["Revenue",`₹${ov.revenue_inr}`]].map(([k,v]) => (
          <div key={k} className="bg-card border border-border rounded-lg p-4">
            <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">{k}</div>
            <div className="font-display text-2xl mt-2">{v}</div>
          </div>
        ))}
      </div>
      <div className="flex gap-2">
        {["overview","businesses","users"].map(t => (
          <button key={t} onClick={() => setTab(t)} className={`px-3 py-1.5 text-xs rounded-md border transition-colors ${tab===t ? "bg-primary text-primary-foreground border-primary" : "border-border hover:bg-secondary"}`}>{t}</button>
        ))}
      </div>
      {tab === "businesses" && (
        <div className="bg-card border border-border rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-secondary text-xs uppercase tracking-[0.15em]"><tr><th className="text-left p-3">Name</th><th className="text-left p-3">Plan</th><th className="text-left p-3">Usage</th><th className="text-left p-3">Created</th></tr></thead>
            <tbody className="divide-y divide-border">
              {biz.map(b => <tr key={b.business_id}><td className="p-3">{b.name}</td><td className="p-3">{b.plan}</td><td className="p-3">{b.monthly_used}/{b.monthly_limit}</td><td className="p-3 text-muted-foreground text-xs">{new Date(b.created_at).toLocaleDateString()}</td></tr>)}
            </tbody>
          </table>
        </div>
      )}
      {tab === "users" && (
        <div className="bg-card border border-border rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-secondary text-xs uppercase tracking-[0.15em]"><tr><th className="text-left p-3">Email</th><th className="text-left p-3">Name</th><th className="text-left p-3">Role</th><th className="text-left p-3">Joined</th></tr></thead>
            <tbody className="divide-y divide-border">
              {users.map(u => <tr key={u.user_id}><td className="p-3">{u.email}</td><td className="p-3">{u.name}</td><td className="p-3">{u.role}</td><td className="p-3 text-muted-foreground text-xs">{new Date(u.created_at).toLocaleDateString()}</td></tr>)}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
