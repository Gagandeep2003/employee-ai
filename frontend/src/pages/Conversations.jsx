import React, { useEffect, useState } from "react";
import { useBiz } from "../components/AppShell";
import { api } from "../lib/api";
import { toast } from "sonner";

const OUTCOMES = [
  [null, "Untagged", "border-border text-muted-foreground"],
  ["lead", "Lead", "border-accent text-accent"],
  ["booked", "Booked", "border-emerald-500 text-emerald-600"],
  ["resolved", "Resolved", "border-blue-500 text-blue-600"],
  ["lost", "Lost", "border-destructive text-destructive"],
];

export default function Conversations() {
  const { current } = useBiz();
  const [items, setItems] = useState([]);
  const [selected, setSelected] = useState(null);
  const [selectedConv, setSelectedConv] = useState(null);
  const [messages, setMessages] = useState([]);
  const [filter, setFilter] = useState("all"); // all | unanswered | escalated

  const refreshList = () => {
    if (!current) return;
    const params = {};
    if (filter === "unanswered") params.unanswered = true;
    if (filter === "escalated") params.status = "escalated";
    api.get(`/conversations/business/${current.business_id}`, { params }).then(({ data }) => setItems(data));
  };
  useEffect(refreshList, [current, filter]);

  const openConv = async (id) => {
    setSelected(id);
    const { data } = await api.get(`/conversations/${id}`);
    setMessages(data.messages);
    setSelectedConv(data.conversation);
  };

  const setOutcome = async (outcome) => {
    if (!selected) return;
    try {
      await api.patch(`/conversations/${selected}/outcome`, { outcome });
      setSelectedConv((c) => ({ ...c, outcome }));
      refreshList();
    } catch {
      toast.error("Couldn't update outcome");
    }
  };

  if (!current) return null;

  return (
    <div className="p-8 space-y-6">
      <div className="flex items-end justify-between gap-4">
        <div>
          <div className="text-[10px] uppercase tracking-[0.3em] text-muted-foreground">Conversations</div>
          <h1 className="font-display text-4xl tracking-tight">Every chat, every question.</h1>
        </div>
        <div className="flex gap-2">
          {["all","unanswered","escalated"].map(f => (
            <button key={f} onClick={() => setFilter(f)} data-testid={`filter-${f}`}
              className={`px-3 py-1.5 text-xs rounded-md border transition-colors ${filter===f ? "bg-primary text-primary-foreground border-primary" : "border-border hover:bg-secondary"}`}>{f}</button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 min-h-[500px]">
        <div className="bg-card border border-border rounded-lg overflow-hidden">
          <div className="divide-y divide-border max-h-[600px] overflow-y-auto">
            {items.map(c => (
              <button key={c.conversation_id} onClick={() => openConv(c.conversation_id)} data-testid={`conv-${c.conversation_id}`}
                className={`w-full text-left p-4 hover:bg-secondary transition-colors ${selected===c.conversation_id ? "bg-secondary" : ""}`}>
                <div className="flex justify-between items-center">
                  <div className="text-xs font-mono text-muted-foreground">{c.visitor_id}</div>
                  <div className="flex items-center gap-1">
                    {c.outcome && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded border border-border capitalize">{c.outcome}</span>
                    )}
                    {c.unanswered && <span className="text-[10px] px-1.5 py-0.5 rounded bg-accent text-accent-foreground">unanswered</span>}
                  </div>
                </div>
                <div className="text-sm mt-1">{c.message_count} msgs · {c.status}</div>
                <div className="text-[11px] text-muted-foreground mt-1">{new Date(c.last_message_at).toLocaleString()}</div>
              </button>
            ))}
            {!items.length && <div className="p-8 text-sm text-muted-foreground text-center">No conversations yet.</div>}
          </div>
        </div>
        <div className="md:col-span-2 bg-card border border-border rounded-lg p-4 overflow-y-auto max-h-[600px]">
          {selected ? (
            <div className="space-y-3">
              <div className="flex items-center gap-2 pb-3 border-b border-border">
                <span className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground mr-1">Outcome</span>
                {OUTCOMES.map(([val, label, cls]) => (
                  <button
                    key={label}
                    onClick={() => setOutcome(val)}
                    data-testid={`outcome-${val || "none"}`}
                    className={`text-[11px] px-2 py-1 rounded-md border transition-colors ${
                      (selectedConv?.outcome || null) === val ? cls + " bg-secondary" : "border-border text-muted-foreground hover:bg-secondary"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
              {messages.map(m => (
                <div key={m.id} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                  <div className={`max-w-[80%] px-3 py-2 rounded-md text-sm ${m.role === "user" ? "bg-primary text-primary-foreground" : "bg-secondary"}`}>
                    <div>{m.text}</div>
                    <div className="text-[10px] opacity-60 mt-1">{new Date(m.created_at).toLocaleString()}{m.confidence !== undefined ? ` · conf ${(m.confidence).toFixed(2)}` : ""}</div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="h-full flex items-center justify-center text-sm text-muted-foreground">Select a conversation</div>
          )}
        </div>
      </div>
    </div>
  );
}
