import React, { useEffect, useState, useCallback } from "react";
import { useBiz } from "../components/AppShell";
import { api } from "../lib/api";
import { toast } from "sonner";
import {
  PushPin, Archive, MagnifyingGlass, PencilSimple,
  Trash, DownloadSimple, Check, X,
} from "@phosphor-icons/react";

const OUTCOMES = [
  [null, "Untagged", "border-border text-muted-foreground"],
  ["lead", "Lead", "border-accent text-accent"],
  ["booked", "Booked", "border-emerald-500 text-emerald-600"],
  ["resolved", "Resolved", "border-blue-500 text-blue-600"],
  ["lost", "Lost", "border-destructive text-destructive"],
];

function RenameField({ conv, onRenamed }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(conv.title || "");

  const save = async () => {
    const title = value.trim();
    if (!title) { setEditing(false); return; }
    try {
      await api.patch(`/conversations/${conv.conversation_id}/title`, { title });
      onRenamed(title);
      setEditing(false);
    } catch { toast.error("Couldn't rename"); }
  };

  if (editing) {
    return (
      <div className="flex items-center gap-1">
        <input autoFocus value={value} onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") save(); if (e.key === "Escape") setEditing(false); }}
          aria-label="Conversation title" data-testid="rename-input" className="text-sm px-2 py-1 rounded border border-border bg-background flex-1 min-w-0" />
        <button onClick={save} aria-label="Save title" className="text-emerald-600 shrink-0"><Check size={14} /></button>
        <button onClick={() => setEditing(false)} aria-label="Cancel rename" className="text-muted-foreground shrink-0"><X size={14} /></button>
      </div>
    );
  }
  return (
    <button onClick={() => setEditing(true)} data-testid="rename-btn" className="flex items-center gap-1.5 text-left group min-w-0">
      <span className="text-sm font-medium truncate">{conv.title || "Untitled conversation"}</span>
      <PencilSimple size={12} className="opacity-0 group-hover:opacity-60 shrink-0" />
    </button>
  );
}

export default function Conversations() {
  const { current } = useBiz();
  const [items, setItems] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [selected, setSelected] = useState(null);
  const [selectedConv, setSelectedConv] = useState(null);
  const [messages, setMessages] = useState([]);
  const [filter, setFilter] = useState("all"); // all | unanswered | escalated
  const [showArchived, setShowArchived] = useState(false);
  const [search, setSearch] = useState("");

  const refreshList = useCallback(() => {
    if (!current) return;
    const params = {};
    if (filter === "unanswered") params.unanswered = true;
    if (filter === "escalated") params.status = "escalated";
    if (showArchived) params.archived = true;
    if (search.trim()) params.search = search.trim();
    api.get(`/conversations/business/${current.business_id}`, { params }).then(({ data }) => { setItems(data); setLoaded(true); });
  }, [current, filter, showArchived, search]);

  useEffect(refreshList, [refreshList]);
  useEffect(() => {
    const t = setTimeout(refreshList, search ? 300 : 0); // debounce typing, not the other filter changes
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

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
    } catch { toast.error("Couldn't update outcome"); }
  };

  const togglePin = async (conv, e) => {
    e.stopPropagation();
    try {
      await api.patch(`/conversations/${conv.conversation_id}/pin`, { pinned: !conv.pinned });
      refreshList();
      if (selected === conv.conversation_id) setSelectedConv((c) => ({ ...c, pinned: !conv.pinned }));
    } catch { toast.error("Couldn't update"); }
  };

  const toggleArchive = async (conv, e) => {
    e.stopPropagation();
    try {
      await api.patch(`/conversations/${conv.conversation_id}/archive`, { archived: !conv.archived });
      toast.success(conv.archived ? "Restored" : "Archived");
      if (selected === conv.conversation_id) { setSelected(null); setSelectedConv(null); }
      refreshList();
    } catch { toast.error("Couldn't update"); }
  };

  const removeConv = async (conv, e) => {
    e.stopPropagation();
    if (!window.confirm("Delete this conversation permanently? This can't be undone.")) return;
    try {
      await api.delete(`/conversations/${conv.conversation_id}`);
      if (selected === conv.conversation_id) { setSelected(null); setSelectedConv(null); }
      refreshList();
    } catch { toast.error("Couldn't delete"); }
  };

  const exportConv = async (format) => {
    if (!selected) return;
    try {
      const res = await api.get(`/conversations/${selected}/export`, { params: { format }, responseType: "blob" });
      const disposition = res.headers["content-disposition"] || "";
      const match = disposition.match(/filename="(.+)"/);
      const filename = match ? match[1] : `conversation.${format}`;
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement("a");
      a.href = url; a.download = filename; a.click();
      window.URL.revokeObjectURL(url);
    } catch { toast.error("Couldn't export"); }
  };

  if (!current) return null;

  return (
    <div className="p-8 space-y-6">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <div className="text-[10px] uppercase tracking-[0.3em] text-muted-foreground">Conversations</div>
          <h1 className="font-display text-4xl tracking-tight">Every chat, every question.</h1>
        </div>
        <div className="flex gap-2 flex-wrap">
          {["all", "unanswered", "escalated"].map((f) => (
            <button key={f} onClick={() => setFilter(f)} data-testid={`filter-${f}`}
              className={`px-3 py-1.5 text-xs rounded-md border transition-colors ${filter === f ? "bg-primary text-primary-foreground border-primary" : "border-border hover:bg-secondary"}`}>{f}</button>
          ))}
          <button onClick={() => setShowArchived((v) => !v)} data-testid="toggle-archived"
            className={`px-3 py-1.5 text-xs rounded-md border transition-colors inline-flex items-center gap-1.5 ${showArchived ? "bg-primary text-primary-foreground border-primary" : "border-border hover:bg-secondary"}`}>
            <Archive size={14} /> Archived
          </button>
        </div>
      </div>

      <div className="relative max-w-sm">
        <MagnifyingGlass size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
        <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search conversations…"
          aria-label="Search conversations" data-testid="conv-search" className="w-full pl-9 pr-3 py-2 rounded-md border border-border bg-background text-sm" />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 min-h-[500px]">
        <div className="bg-card border border-border rounded-lg overflow-hidden">
          <div className="divide-y divide-border max-h-[600px] overflow-y-auto">
            {items.map((c) => (
              <div key={c.conversation_id} onClick={() => openConv(c.conversation_id)} data-testid={`conv-${c.conversation_id}`}
                className={`group w-full text-left p-4 hover:bg-secondary transition-colors cursor-pointer ${selected === c.conversation_id ? "bg-secondary" : ""}`}>
                <div className="flex justify-between items-start gap-2">
                  <div className="flex items-center gap-1.5 min-w-0">
                    {c.pinned && <PushPin size={11} weight="fill" className="text-accent shrink-0" />}
                    <span className="text-sm font-medium truncate">{c.title || c.visitor_id}</span>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    {c.outcome && <span className="text-[10px] px-1.5 py-0.5 rounded border border-border capitalize">{c.outcome}</span>}
                    {c.unanswered && <span className="text-[10px] px-1.5 py-0.5 rounded bg-accent text-accent-foreground">unanswered</span>}
                  </div>
                </div>
                <div className="text-xs text-muted-foreground mt-1">{c.message_count} msgs · {c.status}</div>
                <div className="flex items-center justify-between mt-1.5">
                  <div className="text-[11px] text-muted-foreground">{new Date(c.last_message_at).toLocaleString()}</div>
                  <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 hover:opacity-100">
                    <button onClick={(e) => togglePin(c, e)} data-testid={`pin-${c.conversation_id}`} title={c.pinned ? "Unpin" : "Pin"}
                      aria-label={c.pinned ? "Unpin conversation" : "Pin conversation"}
                      className={`hover:text-accent ${c.pinned ? "text-accent" : "text-muted-foreground"}`}><PushPin size={13} weight={c.pinned ? "fill" : "regular"} /></button>
                    <button onClick={(e) => toggleArchive(c, e)} data-testid={`archive-${c.conversation_id}`} title={c.archived ? "Restore" : "Archive"}
                      aria-label={c.archived ? "Restore conversation" : "Archive conversation"}
                      className="text-muted-foreground hover:text-foreground"><Archive size={13} /></button>
                    <button onClick={(e) => removeConv(c, e)} data-testid={`delete-${c.conversation_id}`} title="Delete"
                      aria-label="Delete conversation"
                      className="text-muted-foreground hover:text-destructive"><Trash size={13} /></button>
                  </div>
                </div>
              </div>
            ))}
            {!items.length && (
              <div className="p-8 text-sm text-muted-foreground text-center">
                {!loaded ? "Loading…" : search ? "No conversations match your search." : showArchived ? "No archived conversations." : "No conversations yet."}
              </div>
            )}
          </div>
        </div>
        <div className="md:col-span-2 bg-card border border-border rounded-lg p-4 overflow-y-auto max-h-[600px]">
          {selected && selectedConv ? (
            <div className="space-y-3">
              <div className="flex items-center justify-between gap-3 pb-3 border-b border-border flex-wrap">
                <RenameField conv={selectedConv} onRenamed={(title) => { setSelectedConv((c) => ({ ...c, title, title_auto_generated: false })); refreshList(); }} />
                <div className="flex items-center gap-1">
                  <button onClick={() => exportConv("txt")} data-testid="export-txt" title="Export as text"
                    className="text-xs px-2 py-1 rounded border border-border hover:bg-secondary inline-flex items-center gap-1"><DownloadSimple size={12} /> .txt</button>
                  <button onClick={() => exportConv("json")} data-testid="export-json" title="Export as JSON"
                    className="text-xs px-2 py-1 rounded border border-border hover:bg-secondary inline-flex items-center gap-1"><DownloadSimple size={12} /> .json</button>
                </div>
              </div>
              <div className="flex items-center gap-2 pb-3 border-b border-border flex-wrap">
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
              {messages.map((m) => (
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
