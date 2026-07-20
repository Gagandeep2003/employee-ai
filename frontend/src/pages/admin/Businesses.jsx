import React, { useEffect, useState } from "react";
import { api, setAuthToken } from "../../lib/api";
import { toast } from "sonner";
import { H1, Card, Search, Row, Th, Td, Btn, Pill, fmtDate } from "./_ui";

export default function Businesses() {
  const [items, setItems] = useState([]);
  const [q, setQ] = useState("");
  const [plan, setPlan] = useState("");
  const [detail, setDetail] = useState(null);

  const load = () => {
    const params = {};
    if (q) params.q = q;
    if (plan) params.plan = plan;
    api.get("/admin/businesses", { params }).then(({ data }) => setItems(data));
  };
  useEffect(load, [plan]);
  useEffect(() => { const t = setTimeout(load, 300); return () => clearTimeout(t); }, [q]);

  const openDetail = async (bid) => {
    const { data } = await api.get(`/admin/businesses/${bid}`);
    setDetail(data);
  };

  const doAction = async (bid, action, extra = {}) => {
    if (action === "delete" && !window.confirm("Permanently delete this business and ALL its data?")) return;
    try {
      await api.post(`/admin/businesses/${bid}/action`, { action, ...extra });
      toast.success(`Applied: ${action}`);
      load();
      if (detail?.business?.business_id === bid) openDetail(bid);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  const impersonate = async (bid, name) => {
    if (!window.confirm(`Log in as owner of "${name}"?  This will be recorded in the audit log.`)) return;
    try {
      const { data } = await api.post(`/admin/businesses/${bid}/impersonate`);
      setAuthToken(data.token);
      toast.success(`Impersonating ${data.user.email}`);
      window.location.href = "/dashboard";
    } catch { toast.error("Failed"); }
  };

  return (
    <div className="p-6 md:p-8 space-y-4">
      <H1 eyebrow="Master directory" title="Businesses">
        <Search value={q} onChange={setQ} placeholder="Search name, email, phone, id…" />
        <select value={plan} onChange={(e) => setPlan(e.target.value)} className="px-3 py-1.5 rounded-md border border-border bg-card text-sm">
          <option value="">All plans</option>
          <option value="free">Free</option>
          <option value="starter">Starter</option>
          <option value="pro">Pro</option>
        </select>
      </H1>

      <Card>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-secondary/50">
              <tr>
                <Th>Business</Th><Th>Owner</Th><Th>Plan</Th><Th>Usage</Th><Th>KB</Th><Th>Chats</Th><Th>Status</Th><Th>Created</Th><Th></Th>
              </tr>
            </thead>
            <tbody>
              {items.map((b) => (
                <Row key={b.business_id}>
                  <Td>
                    <button className="text-left hover:text-accent" onClick={() => openDetail(b.business_id)}>
                      <div className="font-medium">{b.name}</div>
                      <div className="text-[11px] text-muted-foreground">{b.business_id}</div>
                    </button>
                  </Td>
                  <Td><div>{b.owner_name || "—"}</div><div className="text-[11px] text-muted-foreground">{b.owner_email}</div></Td>
                  <Td><Pill tone={b.plan === "free" ? "default" : "accent"}>{b.plan}</Pill></Td>
                  <Td>{b.monthly_used}/{b.monthly_limit}</Td>
                  <Td>{b.kb_chunks}</Td>
                  <Td>{b.conversations}</Td>
                  <Td>{b.status === "suspended" ? <Pill tone="danger">suspended</Pill> : <Pill tone="ok">active</Pill>}</Td>
                  <Td className="text-xs text-muted-foreground">{fmtDate(b.created_at)}</Td>
                  <Td className="text-right whitespace-nowrap">
                    <Btn variant="ghost" onClick={() => impersonate(b.business_id, b.name)} testid={`imp-${b.business_id}`}>Login as</Btn>
                  </Td>
                </Row>
              ))}
              {!items.length && <tr><Td className="text-center text-muted-foreground py-8" colSpan={9}>No businesses</Td></tr>}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Detail drawer */}
      {detail && (
        <div className="fixed inset-0 bg-background/80 backdrop-blur-sm z-50 flex justify-end" onClick={() => setDetail(null)}>
          <div className="w-full max-w-xl bg-card border-l border-border h-full overflow-y-auto p-6" onClick={(e) => e.stopPropagation()}>
            <button onClick={() => setDetail(null)} className="text-xs text-muted-foreground hover:text-foreground mb-4">← Close</button>
            <div className="font-display text-2xl">{detail.business.name}</div>
            <div className="text-xs text-muted-foreground font-mono">{detail.business.business_id}</div>
            <div className="grid grid-cols-2 gap-3 mt-6">
              {[["Plan", detail.business.plan],["Usage", `${detail.business.monthly_used}/${detail.business.monthly_limit}`],
                ["Files", detail.stats.files],["KB chunks", detail.stats.kb_chunks],
                ["Conversations", detail.stats.conversations],["Messages", detail.stats.messages],
                ["Website", detail.business.website || "—"],["Category", detail.business.category || "—"],
                ["Country", detail.business.country || "—"],["Language", detail.business.language]].map(([k,v]) => (
                <div key={k} className="bg-secondary rounded-md p-3">
                  <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">{k}</div>
                  <div className="text-sm mt-1 truncate">{v}</div>
                </div>
              ))}
            </div>
            <div className="mt-6">
              <div className="text-xs uppercase tracking-[0.2em] text-muted-foreground mb-2">Owner</div>
              <div className="bg-secondary rounded-md p-3 text-sm">
                <div>{detail.owner?.name} · <span className="text-muted-foreground">{detail.owner?.email}</span></div>
                <div className="text-[11px] text-muted-foreground mt-1">Referral: {detail.owner?.referral_code}</div>
              </div>
            </div>
            <div className="mt-6 flex flex-wrap gap-2">
              {detail.business.status === "suspended"
                ? <Btn onClick={() => doAction(detail.business.business_id, "activate")}>Reactivate</Btn>
                : <Btn variant="ghost" onClick={() => doAction(detail.business.business_id, "suspend")}>Suspend</Btn>}
              <Btn variant="ghost" onClick={() => doAction(detail.business.business_id, "reset_usage")}>Reset usage</Btn>
              <select onChange={(e) => e.target.value && doAction(detail.business.business_id, "set_plan", { plan: e.target.value })} defaultValue=""
                className="text-xs px-2 py-1.5 rounded-md border border-border bg-card">
                <option value="" disabled>Set plan…</option>
                <option value="free">Free</option><option value="starter">Starter</option><option value="pro">Pro</option>
              </select>
              <Btn variant="ghost" onClick={() => doAction(detail.business.business_id, "extend", { extra_days: 30 })}>+30 days</Btn>
              <Btn variant="accent" onClick={() => impersonate(detail.business.business_id, detail.business.name)}>Login as owner</Btn>
              <Btn variant="danger" onClick={() => doAction(detail.business.business_id, "delete")}>Delete</Btn>
            </div>
            <div className="mt-6">
              <div className="text-xs uppercase tracking-[0.2em] text-muted-foreground mb-2">Invoices</div>
              <div className="space-y-1">
                {detail.invoices.map((i) => (
                  <div key={i.id} className="flex justify-between bg-secondary rounded-md p-2 text-xs">
                    <div className="font-mono">{i.id}</div>
                    <div>₹{i.amount_inr} · {i.plan} · {i.status}</div>
                  </div>
                ))}
                {!detail.invoices.length && <div className="text-xs text-muted-foreground">No invoices.</div>}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
