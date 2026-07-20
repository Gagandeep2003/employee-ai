import React, { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { H1, Card, Row, Th, Td, Pill, fmtDate } from "./_ui";

export default function Referrals() {
  const [items, setItems] = useState([]);
  useEffect(() => { api.get("/admin/referrals").then(({ data }) => setItems(data)); }, []);
  const rewarded = items.filter(r => r.status === "rewarded").length;
  return (
    <div className="p-6 md:p-8 space-y-4">
      <H1 eyebrow="Growth" title="Referral Management" />
      <div className="grid grid-cols-3 gap-3">
        <div className="bg-card border border-border rounded-lg p-4"><div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">Total</div><div className="font-display text-2xl mt-1">{items.length}</div></div>
        <div className="bg-card border border-border rounded-lg p-4"><div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">Rewarded</div><div className="font-display text-2xl mt-1">{rewarded}</div></div>
        <div className="bg-card border border-border rounded-lg p-4"><div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">Conversion</div><div className="font-display text-2xl mt-1">{items.length ? Math.round(rewarded / items.length * 100) : 0}%</div></div>
      </div>
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-secondary/50"><tr>
              <Th>Referrer</Th><Th>Referred</Th><Th>Code</Th><Th>Status</Th><Th>Created</Th>
            </tr></thead>
            <tbody>
              {items.map((r) => (
                <Row key={r.id}>
                  <Td>{r.referrer_email}</Td>
                  <Td>{r.referred_email}</Td>
                  <Td className="font-mono text-xs">{r.code}</Td>
                  <Td><Pill tone={r.status === "rewarded" ? "ok" : "default"}>{r.status}</Pill></Td>
                  <Td className="text-xs text-muted-foreground">{fmtDate(r.created_at)}</Td>
                </Row>
              ))}
              {!items.length && <tr><Td className="text-center text-muted-foreground py-8" colSpan={5}>No referrals yet.</Td></tr>}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
