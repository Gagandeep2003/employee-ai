import React, { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { toast } from "sonner";
import { H1, Card, Row, Th, Td, Btn, Pill, fmtDT } from "./_ui";

export default function Tickets() {
  const [items, setItems] = useState([]);
  const [filter, setFilter] = useState("open");
  const load = () => api.get("/admin/tickets", { params: { status: filter } }).then(({ data }) => setItems(data));
  useEffect(load, [filter]);
  const close = async (id) => {
    const note = window.prompt("Internal note (optional):") || "";
    await api.post(`/admin/tickets/${id}/action`, { status: "closed", note });
    toast.success("Closed"); load();
  };
  return (
    <div className="p-6 md:p-8 space-y-4">
      <H1 eyebrow="Support" title="Customer Support Tickets">
        <select value={filter} onChange={(e) => setFilter(e.target.value)} className="px-3 py-1.5 rounded-md border border-border bg-card text-sm">
          <option value="open">Open</option><option value="closed">Closed</option><option value="">All</option>
        </select>
      </H1>
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-secondary/50"><tr>
              <Th>Business</Th><Th>Visitor</Th><Th>Note</Th><Th>Created</Th><Th>Status</Th><Th></Th>
            </tr></thead>
            <tbody>
              {items.map((t) => (
                <Row key={t.id}>
                  <Td>{t.business_name}</Td>
                  <Td className="text-xs">{t.visitor_email || t.visitor_name || "anonymous"}</Td>
                  <Td className="max-w-md text-xs truncate">{t.note || t.conversation_id}</Td>
                  <Td className="text-xs text-muted-foreground">{fmtDT(t.created_at)}</Td>
                  <Td>{t.read ? <Pill tone="ok">closed</Pill> : <Pill tone="warn">open</Pill>}</Td>
                  <Td className="text-right">{!t.read && <Btn onClick={() => close(t.id)}>Close</Btn>}</Td>
                </Row>
              ))}
              {!items.length && <tr><Td className="text-center text-muted-foreground py-8" colSpan={6}>No tickets.</Td></tr>}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
