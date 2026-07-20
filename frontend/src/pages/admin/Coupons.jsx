import React, { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { toast } from "sonner";
import { H1, Card, Row, Th, Td, Btn, Pill, fmtDate } from "./_ui";

export default function Coupons() {
  const [items, setItems] = useState([]);
  const [form, setForm] = useState({ code: "", discount_pct: 20, max_redemptions: 100 });
  const load = () => api.get("/admin/coupons").then(({ data }) => setItems(data));
  useEffect(load, []);
  const create = async () => {
    if (!form.code) return toast.error("Code required");
    try { await api.post("/admin/coupons", form); toast.success("Coupon created"); setForm({ code: "", discount_pct: 20, max_redemptions: 100 }); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };
  const del = async (code) => {
    if (!window.confirm(`Delete ${code}?`)) return;
    await api.delete(`/admin/coupons/${code}`); toast.success("Deleted"); load();
  };
  return (
    <div className="p-6 md:p-8 space-y-4">
      <H1 eyebrow="Promotions" title="Coupons" />
      <Card title="New coupon">
        <div className="p-4 grid grid-cols-1 md:grid-cols-5 gap-3 items-end">
          <label><div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground mb-1">Code</div>
            <input value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })} placeholder="LAUNCH25" className="w-full px-3 py-2 rounded-md border border-border bg-background text-sm" /></label>
          <label><div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground mb-1">Discount %</div>
            <input type="number" min="1" max="100" value={form.discount_pct} onChange={(e) => setForm({ ...form, discount_pct: +e.target.value })} className="w-full px-3 py-2 rounded-md border border-border bg-background text-sm" /></label>
          <label><div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground mb-1">Max uses</div>
            <input type="number" min="1" value={form.max_redemptions} onChange={(e) => setForm({ ...form, max_redemptions: +e.target.value })} className="w-full px-3 py-2 rounded-md border border-border bg-background text-sm" /></label>
          <Btn onClick={create} className="h-10">Create coupon</Btn>
        </div>
      </Card>
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-secondary/50"><tr>
              <Th>Code</Th><Th>Discount</Th><Th>Redemptions</Th><Th>Max</Th><Th>Status</Th><Th>Created</Th><Th></Th>
            </tr></thead>
            <tbody>
              {items.map((c) => (
                <Row key={c.code}>
                  <Td className="font-mono">{c.code}</Td>
                  <Td>{c.discount_pct}%</Td>
                  <Td>{c.redemptions || 0}</Td>
                  <Td>{c.max_redemptions}</Td>
                  <Td>{c.active ? <Pill tone="ok">active</Pill> : <Pill>inactive</Pill>}</Td>
                  <Td className="text-xs text-muted-foreground">{fmtDate(c.created_at)}</Td>
                  <Td className="text-right"><Btn variant="danger" onClick={() => del(c.code)}>Delete</Btn></Td>
                </Row>
              ))}
              {!items.length && <tr><Td className="text-center text-muted-foreground py-8" colSpan={7}>No coupons yet.</Td></tr>}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
