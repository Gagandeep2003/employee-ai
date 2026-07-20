import React, { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { toast } from "sonner";
import { PencilSimple, Trash, Check, X, ArrowClockwise } from "@phosphor-icons/react";

const CATEGORIES = ["Restaurant","Cafe","Doctor / Clinic","Gym / Studio","Salon / Spa","Retail Shop","Ecommerce","School / Coaching","Lawyer / CA","Hotel / BnB","Real Estate","Agency","Other"];
const COUNTRIES = ["India","United States","United Kingdom","Canada","Australia","UAE","Singapore","Germany","France","Other"];
const LANGS = [["en","English"],["hi","Hindi"],["es","Spanish"],["fr","French"],["de","German"],["ar","Arabic"],["pt","Portuguese"]];

export default function Onboarding() {
  const nav = useNavigate();
  const [step, setStep] = useState(1);
  const [f, setF] = useState({ name: "", website: "", email: "", phone: "", category: CATEGORIES[0], country: COUNTRIES[0], language: "en", timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC" });
  const [busy, setBusy] = useState(false);
  const [biz, setBiz] = useState(null);

  const submit = async () => {
    if (!f.name.trim()) { toast.error("Business name required"); return; }
    setBusy(true);
    try {
      const { data } = await api.post("/businesses", f);
      localStorage.setItem("current_biz", data.business_id);
      setBiz(data);
      setStep(2);
    } catch (e) {
      toast.error("Could not create business");
    }
    setBusy(false);
  };

  return (
    <div className="min-h-screen bg-background text-foreground flex items-center justify-center p-6">
      <div className="w-full max-w-2xl">
        {step === 1 ? (
          <>
            <div className="text-[10px] uppercase tracking-[0.3em] text-accent mb-3">Step 1 of 2</div>
            <h1 className="font-display text-4xl tracking-tight">Tell us about your business.</h1>
            <p className="text-muted-foreground mt-2">Only the essentials. Everything else, we learn from your site -- and you'll get to check it before it goes live.</p>

            <div className="mt-10 grid grid-cols-1 md:grid-cols-2 gap-5">
              <Field label="Business name *"><Input v={f.name} on={(v) => setF({ ...f, name: v })} test="ob-name" /></Field>
              <Field label="Website URL"><Input v={f.website} on={(v) => setF({ ...f, website: v })} placeholder="https://…" test="ob-website" /></Field>
              <Field label="Email"><Input v={f.email} on={(v) => setF({ ...f, email: v })} test="ob-email" /></Field>
              <Field label="Phone"><Input v={f.phone} on={(v) => setF({ ...f, phone: v })} test="ob-phone" /></Field>
              <Field label="Category"><Select v={f.category} on={(v) => setF({ ...f, category: v })} opts={CATEGORIES.map(c => [c, c])} test="ob-category" /></Field>
              <Field label="Country"><Select v={f.country} on={(v) => setF({ ...f, country: v })} opts={COUNTRIES.map(c => [c, c])} test="ob-country" /></Field>
              <Field label="Language"><Select v={f.language} on={(v) => setF({ ...f, language: v })} opts={LANGS} test="ob-language" /></Field>
              <Field label="Timezone"><Input v={f.timezone} on={(v) => setF({ ...f, timezone: v })} test="ob-timezone" /></Field>
            </div>

            <div className="mt-10 flex gap-3">
              <button onClick={submit} disabled={busy} data-testid="ob-submit" className="px-6 py-3 rounded-md bg-primary text-primary-foreground hover:bg-accent hover:text-accent-foreground transition-colors disabled:opacity-60">
                {busy ? "Creating…" : "Create AI Employee"}
              </button>
            </div>
          </>
        ) : (
          <ReviewStep biz={biz} onDone={() => nav("/dashboard")} />
        )}
      </div>
    </div>
  );
}

function ReviewStep({ biz, onDone }) {
  const [status, setStatus] = useState(biz);
  const [chunks, setChunks] = useState([]);
  const [editing, setEditing] = useState(null); // chunk id being edited
  const [editText, setEditText] = useState("");
  const [manual, setManual] = useState({ title: "", text: "" });
  const pollRef = useRef(null);

  const refreshChunks = () => {
    api.get(`/knowledge/${biz.business_id}/chunks`).then(({ data }) => setChunks(data)).catch(() => {});
  };

  useEffect(() => {
    refreshChunks();
    const poll = () => {
      api.get(`/businesses/${biz.business_id}`).then(({ data }) => {
        setStatus(data);
        if (data.crawl_status === "crawling") {
          pollRef.current = setTimeout(poll, 2000);
        } else {
          refreshChunks();
        }
      }).catch(() => {});
    };
    if (biz.crawl_status === "crawling") poll();
    return () => clearTimeout(pollRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [biz.business_id]);

  const deleteChunk = async (id) => {
    await api.delete(`/knowledge/chunks/${id}`);
    refreshChunks();
  };

  const startEdit = (chunk) => { setEditing(chunk.id); setEditText(chunk.text); };
  const saveEdit = async () => {
    await api.patch(`/knowledge/chunks/${editing}`, { text: editText });
    setEditing(null);
    refreshChunks();
  };

  const addManual = async () => {
    if (!manual.title.trim() || !manual.text.trim()) return;
    await api.post("/knowledge/manual", { business_id: biz.business_id, title: manual.title, text: manual.text });
    setManual({ title: "", text: "" });
    refreshChunks();
  };

  const regenerateSnapshot = async () => {
    await api.post(`/businesses/${biz.business_id}/generate-snapshot`);
    toast.success("Regenerating overview -- check back in a few seconds");
    setTimeout(() => api.get(`/businesses/${biz.business_id}`).then(({ data }) => setStatus(data)), 4000);
  };

  const crawling = status?.crawl_status === "crawling";

  return (
    <div>
      <div className="text-[10px] uppercase tracking-[0.3em] text-accent mb-3">Step 2 of 2</div>
      <h1 className="font-display text-4xl tracking-tight">Let's double-check what it learned.</h1>
      <p className="text-muted-foreground mt-2">
        {crawling ? "Reading your website now -- this usually takes under a minute…" : "Review, edit, or remove anything below, then go live."}
      </p>

      {status?.ai_snapshot && (
        <div className="mt-6 bg-card border border-border rounded-lg p-5">
          <div className="flex items-center justify-between mb-2">
            <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">AI overview of your business</div>
            <button onClick={regenerateSnapshot} data-testid="regen-snapshot" className="text-xs text-accent hover:underline flex items-center gap-1">
              <ArrowClockwise size={12} /> Regenerate
            </button>
          </div>
          <div className="text-sm whitespace-pre-line text-foreground/90">{status.ai_snapshot}</div>
        </div>
      )}

      <div className="mt-6 bg-card border border-border rounded-lg p-5">
        <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground mb-3">
          What your AI Employee knows {crawling && "(still loading…)"}
        </div>
        {chunks.length === 0 && !crawling && (
          <div className="text-sm text-muted-foreground">Nothing yet -- add something below, or your AI will politely say it doesn't know until you do.</div>
        )}
        <div className="space-y-2 max-h-80 overflow-y-auto">
          {chunks.map((c) => (
            <div key={c.id} className="bg-secondary rounded-md p-3 text-sm" data-testid={`chunk-${c.id}`}>
              <div className="text-[10px] text-muted-foreground mb-1">{c.source_title || c.source}</div>
              {editing === c.id ? (
                <div className="space-y-2">
                  <textarea value={editText} onChange={(e) => setEditText(e.target.value)} rows={3}
                    className="w-full text-sm px-2 py-1.5 rounded-md border border-border bg-background" />
                  <div className="flex gap-2">
                    <button onClick={saveEdit} data-testid={`save-chunk-${c.id}`} className="text-xs px-2 py-1 rounded-md bg-primary text-primary-foreground flex items-center gap-1"><Check size={12} /> Save</button>
                    <button onClick={() => setEditing(null)} className="text-xs px-2 py-1 rounded-md border border-border flex items-center gap-1"><X size={12} /> Cancel</button>
                  </div>
                </div>
              ) : (
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1">{c.text}</div>
                  <div className="flex gap-2 flex-shrink-0">
                    <button onClick={() => startEdit(c)} data-testid={`edit-chunk-${c.id}`} className="text-muted-foreground hover:text-foreground"><PencilSimple size={14} /></button>
                    <button onClick={() => deleteChunk(c.id)} data-testid={`delete-chunk-${c.id}`} className="text-muted-foreground hover:text-destructive"><Trash size={14} /></button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>

        <div className="mt-4 pt-4 border-t border-border space-y-2">
          <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">Add something it missed</div>
          <input value={manual.title} onChange={(e) => setManual((m) => ({ ...m, title: e.target.value }))}
            placeholder="Title, e.g. Refund policy" data-testid="ob-manual-title"
            className="w-full text-sm px-3 py-2 rounded-md border border-border bg-background" />
          <textarea value={manual.text} onChange={(e) => setManual((m) => ({ ...m, text: e.target.value }))}
            placeholder="What should the AI know?" rows={2} data-testid="ob-manual-text"
            className="w-full text-sm px-3 py-2 rounded-md border border-border bg-background" />
          <button onClick={addManual} data-testid="ob-manual-add" className="text-xs px-3 py-2 rounded-md border border-border hover:bg-secondary">Add</button>
        </div>
      </div>

      <div className="mt-8 flex gap-3">
        <button onClick={onDone} data-testid="ob-go-live" className="px-6 py-3 rounded-md bg-primary text-primary-foreground hover:bg-accent hover:text-accent-foreground transition-colors">
          Looks good -- go live
        </button>
      </div>
    </div>
  );
}

const Field = ({ label, children }) => (
  <label className="block">
    <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground mb-2">{label}</div>
    {children}
  </label>
);
const Input = ({ v, on, placeholder, test }) => (
  <input data-testid={test} value={v} onChange={(e) => on(e.target.value)} placeholder={placeholder}
    className="w-full px-3 py-2.5 rounded-md border border-border bg-card outline-none focus:ring-2 focus:ring-primary" />
);
const Select = ({ v, on, opts, test }) => (
  <select data-testid={test} value={v} onChange={(e) => on(e.target.value)}
    className="w-full px-3 py-2.5 rounded-md border border-border bg-card outline-none focus:ring-2 focus:ring-primary">
    {opts.map(([val, label]) => <option key={val} value={val}>{label}</option>)}
  </select>
);
