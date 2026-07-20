import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useBiz } from "../components/AppShell";
import { api } from "../lib/api";
import { PaperPlaneRight, Sparkle } from "@phosphor-icons/react";

export default function DashboardHome() {
  const { current, refresh } = useBiz();
  const [summary, setSummary] = useState(null);
  const [q, setQ] = useState("");
  const [answer, setAnswer] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!current) return;
    api.get(`/analytics/business/${current.business_id}/summary`).then(({ data }) => setSummary(data));
  }, [current]);

  const ask = async (question) => {
    if (!current || busy) return;
    const query = question || q;
    if (!query.trim()) return;
    setBusy(true); setAnswer(""); setResult(null); setQ("");
    try {
      const { data } = await api.post("/owner-chat/ask", { business_id: current.business_id, question: query });
      setAnswer(data.answer);
      setResult(data.result);
      if (data.result?.ok) {
        // refresh business data if profile / widget changed
        if (["update_business","update_widget","add_knowledge","answer_unanswered","delete_knowledge"].includes(data.result.action)) {
          try { await refresh(); } catch {}
        }
      }
    } catch {
      setAnswer("Unable to reach the assistant right now.");
    }
    setBusy(false);
  };

  if (!current) return null;

  const suggestions = [
    "Summarize today's conversations",
    "What questions couldn't you answer?",
    "Change my widget primary color to navy blue",
    "Add knowledge: our new pricing is ₹499/month for Starter",
    "Update my phone to +91 98765 43210",
    "Teach the AI our refund policy is 7-day no-questions-asked",
  ];

  const freshDays = current.knowledge_last_updated_at
    ? Math.floor((Date.now() - new Date(current.knowledge_last_updated_at).getTime()) / 86400000)
    : null;

  return (
    <div className="p-8 space-y-8" data-testid="dashboard-home">
      <div>
        <div className="text-[10px] uppercase tracking-[0.3em] text-muted-foreground">{current.name}</div>
        <h1 className="font-display text-4xl tracking-tight">Good to see you.</h1>
      </div>

      {freshDays !== null && freshDays > 30 && (
        <div className="bg-accent/10 border border-accent/30 rounded-lg px-4 py-3 text-sm flex items-center justify-between" data-testid="staleness-banner">
          <span>It's been {freshDays} days since your AI's knowledge was updated -- anything changed?</span>
          <Link to="/settings" className="text-accent hover:underline text-xs whitespace-nowrap ml-4">Update quick facts →</Link>
        </div>
      )}

      {/* Owner AI chat */}
      <div className="bg-card border border-border rounded-lg p-6">
        <div className="flex items-center gap-2 mb-4">
          <Sparkle size={16} weight="fill" className="text-accent" />
          <div className="text-xs uppercase tracking-[0.2em]">Ask your AI ops assistant</div>
        </div>
        <div className="flex items-center gap-2">
          <input
            data-testid="owner-chat-input"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && ask()}
            placeholder={`e.g. "Summarize today's conversations"`}
            className="flex-1 px-3 py-3 rounded-md border border-border bg-background outline-none focus:ring-2 focus:ring-primary"
          />
          <button onClick={() => ask()} disabled={busy} data-testid="owner-chat-send" className="px-4 py-3 rounded-md bg-primary text-primary-foreground hover:bg-accent hover:text-accent-foreground transition-colors disabled:opacity-60">
            <PaperPlaneRight size={16} weight="fill" />
          </button>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          {suggestions.map((s) => (
            <button key={s} onClick={() => ask(s)} className="text-xs px-3 py-1.5 rounded-full border border-border hover:bg-secondary transition-colors">{s}</button>
          ))}
        </div>
        {(busy || answer) && (
          <div className="mt-5 p-4 bg-secondary rounded-md text-sm whitespace-pre-wrap leading-relaxed" data-testid="owner-chat-answer">
            {busy ? "Thinking…" : answer}
          </div>
        )}
        {result && (
          <div className={`mt-3 p-3 rounded-md text-xs border ${result.ok ? "border-accent/40 bg-accent/10" : "border-destructive/40 bg-destructive/10"}`} data-testid="owner-chat-result">
            <div className="font-mono uppercase tracking-[0.15em] text-[10px] opacity-70 mb-1">Action: {result.action}</div>
            {result.ok ? (
              <div>✓ Applied — {JSON.stringify(result.result)}</div>
            ) : (
              <div>✗ {result.error}</div>
            )}
          </div>
        )}
      </div>

      {/* Dual mode explainer */}
      <div className="grid md:grid-cols-2 gap-4">
        <div className="bg-card border border-border rounded-lg p-5">
          <div className="text-[10px] uppercase tracking-[0.2em] text-accent">For your customers</div>
          <div className="font-display text-lg mt-1">Read-only. Grounded in your knowledge.</div>
          <p className="text-sm text-muted-foreground mt-2">Your widget answers questions using only what you've taught. No hallucinations, no leaks.</p>
        </div>
        <div className="bg-card border border-border rounded-lg p-5">
          <div className="text-[10px] uppercase tracking-[0.2em] text-accent">For you (the owner)</div>
          <div className="font-display text-lg mt-1">Read + write. Runs your business.</div>
          <p className="text-sm text-muted-foreground mt-2">Ask it to update hours, change widget colors, add knowledge, or teach it new answers — all in natural language.</p>
        </div>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KPI label="Knowledge Score" value={summary?.knowledge_score ?? current.knowledge_score} suffix="/100" testid="kpi-score" />
        <KPI label="Conversations" value={summary?.total_conversations ?? 0} testid="kpi-conv" />
        <KPI label="Unanswered" value={summary?.unanswered ?? 0} testid="kpi-unanswered" />
        <KPI label="This month" value={`${summary?.monthly_used ?? 0}/${summary?.monthly_limit ?? current.monthly_limit}`} testid="kpi-usage" />
      </div>

      <div className="grid md:grid-cols-2 gap-4">
        <div className="bg-card border border-border rounded-lg p-6">
          <div className="text-xs uppercase tracking-[0.2em] text-muted-foreground mb-3">Crawl status</div>
          <div className="font-display text-xl">
            {current.crawl_status === "crawling" && "Reading your website…"}
            {current.crawl_status === "done" && "Ready to serve customers."}
            {current.crawl_status === "pending" && "Not started."}
            {current.crawl_status === "error" && "We hit an error. Try re-crawling."}
          </div>
          <div className="mt-4 text-sm text-muted-foreground">Plan: <span className="text-foreground font-medium">{current.plan}</span></div>
        </div>
        <div className="bg-card border border-border rounded-lg p-6">
          <div className="text-xs uppercase tracking-[0.2em] text-muted-foreground mb-3">Popular topics (last 500 msgs)</div>
          <div className="flex flex-wrap gap-2">
            {(summary?.top_topics || []).map((t) => (
              <span key={t.word} className="px-3 py-1.5 rounded-full bg-secondary text-xs">{t.word} <span className="opacity-60">{t.count}</span></span>
            ))}
            {!summary?.top_topics?.length && <div className="text-sm text-muted-foreground">No conversations yet.</div>}
          </div>
        </div>
      </div>
    </div>
  );
}

const KPI = ({ label, value, suffix, testid }) => (
  <div className="bg-card border border-border rounded-lg p-5" data-testid={testid}>
    <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">{label}</div>
    <div className="font-display text-3xl mt-2 tracking-tight">{value}{suffix}</div>
  </div>
);
