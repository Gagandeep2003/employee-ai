import React, { useEffect, useRef, useState } from "react";
import { useBiz } from "../components/AppShell";
import { api } from "../lib/api";
import { toast } from "sonner";
import { UploadSimple, Trash, ArrowClockwise } from "@phosphor-icons/react";

export default function KnowledgeBase() {
  const { current } = useBiz();
  const [chunks, setChunks] = useState([]);
  const [score, setScore] = useState(null);
  const [manual, setManual] = useState({ title: "", text: "" });
  const [unans, setUnans] = useState([]);
  const fileInput = useRef(null);
  const [uploading, setUploading] = useState(false);

  const refresh = () => {
    if (!current) return;
    api.get(`/knowledge/${current.business_id}/chunks`).then(({ data }) => setChunks(data));
    api.get(`/knowledge/${current.business_id}/score`).then(({ data }) => setScore(data));
    api.get(`/conversations/business/${current.business_id}/unanswered`).then(({ data }) => setUnans(data));
  };
  useEffect(refresh, [current]);

  const upload = async (file) => {
    if (!file || !current) return;
    setUploading(true);
    const fd = new FormData();
    fd.append("business_id", current.business_id);
    fd.append("file", file);
    try {
      const { data } = await api.post("/knowledge/upload", fd, { headers: { "Content-Type": "multipart/form-data" }});
      toast.success(`${data.filename}: ${data.chunks} chunks indexed`);
      refresh();
    } catch { toast.error("Upload failed"); }
    setUploading(false);
  };

  const addManual = async () => {
    if (!manual.title.trim() || !manual.text.trim()) return;
    try {
      await api.post("/knowledge/manual", { business_id: current.business_id, ...manual });
      toast.success("Added to knowledge base");
      setManual({ title: "", text: "" });
      refresh();
    } catch { toast.error("Failed"); }
  };

  const del = async (id) => {
    if (!window.confirm("Delete this chunk?")) return;
    await api.delete(`/knowledge/chunks/${id}`);
    refresh();
  };

  const recrawl = async () => {
    try {
      await api.post(`/businesses/${current.business_id}/recrawl`);
      toast.success("Re-crawling website…");
      setTimeout(refresh, 3000);
    } catch { toast.error("Failed"); }
  };

  if (!current) return null;

  return (
    <div className="p-8 space-y-6">
      <div>
        <div className="text-[10px] uppercase tracking-[0.3em] text-muted-foreground">Knowledge Base</div>
        <h1 className="font-display text-4xl tracking-tight">What your AI knows.</h1>
      </div>

      {/* Score */}
      <div className="bg-card border border-border rounded-lg p-6">
        <div className="flex items-end justify-between gap-4">
          <div>
            <div className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Knowledge Score</div>
            <div className="font-display text-5xl mt-1">{score?.score ?? 0}<span className="text-lg text-muted-foreground">/100</span></div>
            <div className="text-sm text-muted-foreground mt-1">{score?.chunks ?? 0} chunks · crawl: {score?.crawl_status}</div>
          </div>
          <button onClick={recrawl} data-testid="recrawl-btn" className="px-3 py-2 rounded-md border border-border text-xs hover:bg-secondary flex items-center gap-2"><ArrowClockwise size={14} /> Re-crawl website</button>
        </div>
        {!!score?.missing?.length && (
          <div className="mt-4 flex flex-wrap gap-2">
            <span className="text-xs uppercase tracking-[0.2em] text-muted-foreground mr-2">Missing:</span>
            {score.missing.map((m) => <span key={m} className="text-xs px-2 py-1 rounded bg-secondary">{m}</span>)}
          </div>
        )}
      </div>

      {/* Add */}
      <div className="grid md:grid-cols-2 gap-4">
        <div className="bg-card border border-border rounded-lg p-6">
          <div className="text-xs uppercase tracking-[0.2em] text-muted-foreground mb-3">Upload document</div>
          <input ref={fileInput} type="file" accept=".pdf,.docx,.txt,.md,.csv" hidden onChange={(e) => upload(e.target.files?.[0])} data-testid="kb-file-input" />
          <button onClick={() => fileInput.current?.click()} disabled={uploading} data-testid="kb-upload-btn" className="w-full py-8 border-2 border-dashed border-border rounded-md hover:border-primary transition-colors flex flex-col items-center gap-2">
            <UploadSimple size={22} />
            <div className="text-sm">{uploading ? "Uploading…" : "PDF, DOCX, TXT, MD, CSV — up to 15MB"}</div>
          </button>
        </div>
        <div className="bg-card border border-border rounded-lg p-6">
          <div className="text-xs uppercase tracking-[0.2em] text-muted-foreground mb-3">Add manually</div>
          <input placeholder="Title (e.g. Refund policy)" data-testid="kb-manual-title" value={manual.title} onChange={(e) => setManual({ ...manual, title: e.target.value })} className="w-full px-3 py-2 rounded-md border border-border bg-background text-sm mb-2" />
          <textarea placeholder="Answer or content…" data-testid="kb-manual-text" value={manual.text} onChange={(e) => setManual({ ...manual, text: e.target.value })} rows={4} className="w-full px-3 py-2 rounded-md border border-border bg-background text-sm" />
          <button onClick={addManual} data-testid="kb-manual-add" className="mt-3 px-4 py-2 rounded-md bg-primary text-primary-foreground hover:bg-accent hover:text-accent-foreground transition-colors text-sm">Add to knowledge</button>
        </div>
      </div>

      {/* Unanswered → learning loop */}
      {!!unans.length && (
        <div className="bg-card border border-border rounded-lg p-6">
          <div className="text-xs uppercase tracking-[0.2em] text-muted-foreground mb-3">Unanswered questions — teach your AI</div>
          <ul className="space-y-2">
            {unans.slice(0, 6).map((u) => (
              <li key={u.conversation_id} className="flex items-center justify-between gap-3">
                <div className="text-sm">{u.question}</div>
                <button onClick={() => setManual({ title: u.question, text: "" })} className="text-xs text-accent hover:underline">Answer</button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Chunks */}
      <div className="bg-card border border-border rounded-lg">
        <div className="p-4 border-b border-border text-xs uppercase tracking-[0.2em] text-muted-foreground">Indexed knowledge ({chunks.length})</div>
        <div className="divide-y divide-border max-h-[500px] overflow-y-auto">
          {chunks.map((c) => (
            <div key={c.id} className="p-4 flex gap-3">
              <div className="flex-1">
                <div className="text-xs text-accent uppercase tracking-[0.15em] mb-1">{c.source_title || c.source}</div>
                <div className="text-sm text-foreground/90 line-clamp-3">{c.text}</div>
              </div>
              <button onClick={() => del(c.id)} data-testid={`del-chunk-${c.id}`} className="text-muted-foreground hover:text-destructive"><Trash size={16} /></button>
            </div>
          ))}
          {!chunks.length && <div className="p-8 text-sm text-muted-foreground text-center">No knowledge yet. Upload a file or paste your website URL in Settings.</div>}
        </div>
      </div>
    </div>
  );
}
