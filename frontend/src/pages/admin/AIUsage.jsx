import React, { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { H1, Card, Row, Th, Td, Pill } from "./_ui";

export default function AIUsage() {
  const [items, setItems] = useState([]);
  useEffect(() => { api.get("/admin/ai-usage").then(({ data }) => setItems(data)); }, []);
  const totalCost = items.reduce((s,i) => s + (i.est_cost_usd || 0), 0);
  const totalMsgs = items.reduce((s,i) => s + (i.messages || 0), 0);
  return (
    <div className="p-6 md:p-8 space-y-4">
      <H1 eyebrow="Gemini spend" title="AI Usage" />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[["Businesses", items.length],["Messages", totalMsgs],["Est tokens", (totalMsgs * 500).toLocaleString()],["Est cost", `$${totalCost.toFixed(3)}`]].map(([k,v]) => (
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
              <Th>Business</Th><Th>Plan</Th><Th>Messages</Th><Th>Est tokens</Th><Th>Est cost</Th><Th>Monthly usage</Th><Th>Avg confidence</Th>
            </tr></thead>
            <tbody>
              {items.map((b) => (
                <Row key={b.business_id}>
                  <Td>{b.name} <span className="text-[11px] text-muted-foreground">· {b.business_id}</span></Td>
                  <Td><Pill tone="accent">{b.plan}</Pill></Td>
                  <Td>{b.messages}</Td>
                  <Td className="text-xs">{b.est_tokens.toLocaleString()}</Td>
                  <Td className={b.est_cost_usd > 1 ? "text-orange-300" : ""}>${b.est_cost_usd}</Td>
                  <Td>{b.monthly_used}/{b.monthly_limit}</Td>
                  <Td>{(b.avg_confidence * 100).toFixed(0)}%</Td>
                </Row>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
