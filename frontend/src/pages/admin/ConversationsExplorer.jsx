import React, { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { H1, Card, Search, Row, Th, Td, Pill, fmtDT } from "./_ui";

export default function ConversationsExplorer() {
  const [items, setItems] = useState([]);
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState("all"); // all | unanswered | escalated
  const [detail, setDetail] = useState(null);
  const [msgs, setMsgs] = useState([]);

  const load = () => {
    const params = {};
    if (q) params.q = q;
    if (filter === "unanswered") params.unanswered = true;
    if (filter === "escalated") params.escalated = true;
    api.get("/admin/conversations", { params }).then(({ data }) => setItems(data));
  };
  useEffect(() => { const t = setTimeout(load, 300); return () => clearTimeout(t); }, [q, filter]);

  const openDetail = async (c) => {
    setDetail(c);
    const { data } = await api.get(`/conversations/${c.conversation_id}`);
    setMsgs(data.messages);
  };

  return (
    <div className="p-6 md:p-8 space-y-4">
      <H1 eyebrow="Global archive" title="Conversation Explorer">
        <Search value={q} onChange={setQ} placeholder="Search message text…" />
        <select value={filter} onChange={(e) => setFilter(e.target.value)} className="px-3 py-1.5 rounded-md border border-border bg-card text-sm">
          <option value="all">All</option><option value="unanswered">Unanswered</option><option value="escalated">Escalated</option>
        </select>
      </H1>
      <Card>
        <div className="divide-y divide-border max-h-[70vh] overflow-y-auto">
          {items.map((c) => (
            <button key={c.conversation_id} onClick={() => openDetail(c)}
              className="w-full text-left p-4 hover:bg-secondary transition-colors flex justify-between items-center">
              <div>
                <div className="text-sm font-medium">{c.business_name} <span className="text-muted-foreground">· {c.visitor_id}</span></div>
                <div className="text-xs text-muted-foreground mt-1">{c.message_count} msgs · {fmtDT(c.last_message_at)}</div>
              </div>
              <div className="flex gap-1">
                {c.unanswered && <Pill tone="warn">unanswered</Pill>}
                {c.status === "escalated" && <Pill tone="danger">escalated</Pill>}
              </div>
            </button>
          ))}
          {!items.length && <div className="p-8 text-center text-muted-foreground text-sm">No conversations match.</div>}
        </div>
      </Card>
      {detail && (
        <div className="fixed inset-0 bg-background/80 backdrop-blur-sm z-50 flex justify-end" onClick={() => setDetail(null)}>
          <div className="w-full max-w-xl bg-card border-l border-border h-full overflow-y-auto p-6" onClick={(e) => e.stopPropagation()}>
            <button onClick={() => setDetail(null)} className="text-xs text-muted-foreground hover:text-foreground mb-4">← Close</button>
            <div className="font-display text-xl">{detail.business_name}</div>
            <div className="text-xs text-muted-foreground font-mono">{detail.conversation_id}</div>
            <div className="mt-6 space-y-2">
              {msgs.map((m) => (
                <div key={m.id} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                  <div className={`max-w-[85%] px-3 py-2 rounded-md text-sm ${m.role === "user" ? "bg-primary text-primary-foreground" : "bg-secondary"}`}>
                    <div>{m.text}</div>
                    <div className="text-[10px] opacity-60 mt-1">
                      {fmtDT(m.created_at)}
                      {m.confidence !== undefined && m.role === "assistant" ? ` · confidence ${(m.confidence).toFixed(2)}` : ""}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
