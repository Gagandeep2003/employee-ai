import React, { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { H1, Card, Search, Row, Th, Td, Pill, fmtDT } from "./_ui";

export default function AuditLog() {
  const [items, setItems] = useState([]);
  const [q, setQ] = useState("");
  const load = () => api.get("/admin/audit", { params: q ? { q } : {} }).then(({ data }) => setItems(data));
  useEffect(() => { const t = setTimeout(load, 300); return () => clearTimeout(t); }, [q]);
  return (
    <div className="p-6 md:p-8 space-y-4">
      <H1 eyebrow="Security" title="Audit Log">
        <Search value={q} onChange={setQ} placeholder="Filter by action, target, user…" />
      </H1>
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-secondary/50"><tr>
              <Th>When</Th><Th>Actor</Th><Th>Action</Th><Th>Target</Th><Th>Details</Th><Th>IP</Th>
            </tr></thead>
            <tbody>
              {items.map((i) => (
                <Row key={i.id}>
                  <Td className="text-xs text-muted-foreground whitespace-nowrap">{fmtDT(i.created_at)}</Td>
                  <Td className="text-xs">{i.actor_email || i.actor_user_id}</Td>
                  <Td><Pill tone="accent">{i.action}</Pill></Td>
                  <Td className="text-xs">{i.target_type} · <span className="font-mono">{i.target_id}</span></Td>
                  <Td className="text-xs font-mono truncate max-w-xs">{JSON.stringify(i.details || {})}</Td>
                  <Td className="text-xs font-mono">{i.ip || "—"}</Td>
                </Row>
              ))}
              {!items.length && <tr><Td className="text-center text-muted-foreground py-8" colSpan={6}>No audit events yet.</Td></tr>}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
