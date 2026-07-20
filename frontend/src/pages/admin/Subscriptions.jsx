import React, { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { toast } from "sonner";
import { H1, Card, Row, Th, Td, Btn, Pill, fmtDT } from "./_ui";

export default function Subscriptions() {
  const [items, setItems] = useState([]);
  const load = () => api.get("/admin/invoices").then(({ data }) => setItems(data));
  useEffect(load, []);
  const refund = async (id) => {
    const reason = window.prompt("Refund reason (optional):");
    if (reason === null) return;
    try { await api.post(`/admin/invoices/${id}/refund`, { reason }); toast.success("Refunded"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };
  const total = items.filter(i => i.status === "paid").reduce((s,i) => s + (i.amount_inr || 0), 0);
  const refunded = items.filter(i => i.status === "refunded").reduce((s,i) => s + (i.amount_inr || 0), 0);
  return (
    <div className="p-6 md:p-8 space-y-4">
      <H1 eyebrow="Financials" title="Subscriptions & Invoices" />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[["Total invoices", items.length],["Paid", items.filter(i=>i.status==="paid").length],
          ["Revenue", `₹${total.toLocaleString()}`],["Refunded", `₹${refunded.toLocaleString()}`]].map(([k,v]) => (
          <div key={k} className="bg-card border border-border rounded-lg p-4">
            <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">{k}</div>
            <div className="font-display text-2xl mt-1">{v}</div>
          </div>
        ))}
      </div>
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-secondary/50"><tr>
              <Th>Invoice</Th><Th>Business</Th><Th>Plan</Th><Th>Amount</Th><Th>Provider</Th><Th>Status</Th><Th>Date</Th><Th></Th>
            </tr></thead>
            <tbody>
              {items.map((i) => (
                <Row key={i.id}>
                  <Td className="font-mono text-xs">{i.id}</Td>
                  <Td>{i.business_name}</Td>
                  <Td><Pill tone="accent">{i.plan}</Pill></Td>
                  <Td>₹{i.amount_inr}</Td>
                  <Td className="text-xs text-muted-foreground">{i.provider}</Td>
                  <Td><Pill tone={i.status === "paid" ? "ok" : i.status === "refunded" ? "warn" : "default"}>{i.status}</Pill></Td>
                  <Td className="text-xs text-muted-foreground">{fmtDT(i.created_at)}</Td>
                  <Td className="text-right">{i.status === "paid" && <Btn variant="danger" onClick={() => refund(i.id)}>Refund</Btn>}</Td>
                </Row>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
