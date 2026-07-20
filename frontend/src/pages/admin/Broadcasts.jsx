import React, { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { toast } from "sonner";
import { H1, Card, Row, Th, Td, Btn, Pill, fmtDT } from "./_ui";

export default function Broadcasts() {
  const [items, setItems] = useState([]);
  const [form, setForm] = useState({ title: "", message: "", audience: "all", severity: "info" });
  const load = () => api.get("/admin/broadcasts").then(({ data }) => setItems(data));
  useEffect(load, []);
  const send = async () => {
    if (!form.title || !form.message) return toast.error("Title and message required");
    if (!window.confirm(`Send to ${form.audience} businesses?`)) return;
    try { await api.post("/admin/broadcasts", form); toast.success("Broadcast sent"); setForm({ title: "", message: "", audience: "all", severity: "info" }); load(); }
    catch { toast.error("Failed"); }
  };
  return (
    <div className="p-6 md:p-8 space-y-4">
      <H1 eyebrow="Announcements" title="Broadcast Center" />
      <Card title="Compose broadcast">
        <div className="p-4 space-y-3">
          <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="Title (e.g. Scheduled maintenance)" className="w-full px-3 py-2 rounded-md border border-border bg-background text-sm" />
          <textarea value={form.message} onChange={(e) => setForm({ ...form, message: e.target.value })} rows={3} placeholder="Message body…" className="w-full px-3 py-2 rounded-md border border-border bg-background text-sm" />
          <div className="flex flex-wrap gap-3">
            <select value={form.audience} onChange={(e) => setForm({ ...form, audience: e.target.value })} className="px-3 py-2 rounded-md border border-border bg-background text-sm">
              <option value="all">All businesses</option><option value="free">Free plan only</option><option value="paid">Paid plans only</option>
            </select>
            <select value={form.severity} onChange={(e) => setForm({ ...form, severity: e.target.value })} className="px-3 py-2 rounded-md border border-border bg-background text-sm">
              <option value="info">Info</option><option value="warning">Warning</option><option value="urgent">Urgent</option>
            </select>
            <Btn onClick={send}>Send broadcast</Btn>
          </div>
        </div>
      </Card>
      <Card title="History">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-secondary/50"><tr>
              <Th>Title</Th><Th>Audience</Th><Th>Recipients</Th><Th>Severity</Th><Th>Sent</Th>
            </tr></thead>
            <tbody>
              {items.map((b) => (
                <Row key={b.id}>
                  <Td><div className="font-medium">{b.title}</div><div className="text-[11px] text-muted-foreground truncate max-w-md">{b.message}</div></Td>
                  <Td className="text-xs">{b.audience}</Td>
                  <Td>{b.recipient_count}</Td>
                  <Td><Pill tone={b.severity === "urgent" ? "danger" : b.severity === "warning" ? "warn" : "default"}>{b.severity}</Pill></Td>
                  <Td className="text-xs text-muted-foreground">{fmtDT(b.created_at)}</Td>
                </Row>
              ))}
              {!items.length && <tr><Td className="text-center text-muted-foreground py-8" colSpan={5}>No broadcasts yet.</Td></tr>}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
